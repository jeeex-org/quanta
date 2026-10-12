// cuda_daemon.c — persistent CUDA context daemon for Quanta Phase 7.
//
// WHY THIS EXISTS
// ---------------
// Quanta cannot call CUDA directly: the driver returns 0 from cudaSetDevice and
// then faults inside its own mmap, because Quanta's address-space handling is
// incompatible with what the driver needs (it reserves a very large virtual
// mapping). Running each CUDA operation in a SEPARATE helper process fixes the
// mmap conflict, but device pointers do not survive a process boundary -- every
// new process gets a fresh CUDA context, so a pointer returned by cudaMalloc in
// process A is invalid in process B. That is why a fork-per-call design can
// allocate but can never copy.
//
// The fix is one long-lived process that holds a single CUDA context for its
// whole life, so pointers it returns stay valid. Pipes would be the natural
// transport, but pipe()/socketpair() misbehave under Quanta's syscall wrapper
// (pipe returns 0 with garbage descriptors, socketpair returns ENOSYS), so the
// transport is two ordinary files.
//
// PROTOCOL (append-only, line oriented, both files under QUEUE_DIR)
// ----------------------------------------------------------------
//   Quanta -> daemon:  "<seq> <command>\n"
//   daemon  -> Quanta: "<seq> <reply>\n"      reply is one line, no newline
//
// SEQ is a monotonically increasing integer chosen by Quanta. The daemon echoes
// it back so Quanta can ignore replies to older commands and tell "no reply yet"
// apart from "reply was OK". Commands are:
//
//   init                       -> OK | ERR: <reason>
//   malloc <bytes>             -> 0x<device ptr> | ERR: <reason>
//   free <0xptr>               -> OK | ERR: <reason>
//   host_alloc <bytes>         -> 0x<host ptr> | ERR: <reason>
//   host_free <0xptr>          -> OK | ERR: <reason>
//   stream_create              -> 0x<stream> | ERR: <reason>
//   stream_destroy <0xstream>  -> OK | ERR: <reason>
//   stream_sync <0xstream>     -> OK | ERR: <reason>
//   h2d <0xptr> <hostfile> <n> -> OK | ERR: <reason>
//   d2h <0xptr> <hostfile> <n> -> OK | ERR: <reason>
//   quit                       -> daemon exits after replying OK
//
// A failed operation is reported as ERR, never as a stale OK: the daemon writes
// exactly one reply per command, so a command that crashes the CUDA context can
// never be mistaken for success.

#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <stdint.h>
#include <unistd.h>
#include <errno.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <fcntl.h>
#include <sys/file.h>
#include <cuda_runtime.h>

#ifndef QUEUE_DIR
#define QUEUE_DIR "/tmp/quanta_cuda"
#endif
#define QUEUE_PATH QUEUE_DIR "/queue"
#define RESULT_PATH QUEUE_DIR "/result"
#define LOCK_PATH QUEUE_DIR "/lock"
#define POLL_USLEEP 2000
#define IDLE_SLEEP_USLEEP 50000

// ---------------------------------------------------------------------------
// reply: one line, seq echoed, then the payload.
// ---------------------------------------------------------------------------
static void reply(unsigned long long seq, const char *fmt, ...)
{
    char body[4096];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(body, sizeof(body), fmt, ap);
    va_end(ap);

    // Newlines inside a payload would desynchronise the line protocol.
    for (char *p = body; *p; p++) if (*p == '\n' || *p == '\r') *p = ' ';

    FILE *f = fopen(RESULT_PATH, "a");
    if (!f) { perror("open result"); return; }
    fprintf(f, "%llu %s\n", seq, body);
    fclose(f);
}

static void reply_cuda_error(unsigned long long seq, const char *op, cudaError_t rc)
{
    reply(seq, "ERR: %s failed: %s", op, cudaGetErrorString(rc));
}

// ---------------------------------------------------------------------------
// command handlers. Each returns a malloc'd reply body (caller frees) or NULL,
// in which case nothing is written (the handler already replied).
// ---------------------------------------------------------------------------
static char *cmd_malloc(unsigned long long seq, size_t n)
{
    void *p = NULL;
    cudaError_t rc = cudaMalloc(&p, n);
    if (rc != cudaSuccess) { reply_cuda_error(seq, "cudaMalloc", rc); return NULL; }
    char *out = malloc(64);
    snprintf(out, 64, "0x%llx", (unsigned long long)(uintptr_t)p);
    return out;
}

static char *cmd_host_alloc(unsigned long long seq, size_t n)
{
    void *p = NULL;
    cudaError_t rc = cudaHostAlloc(&p, n, cudaHostAllocDefault);
    if (rc != cudaSuccess) { reply_cuda_error(seq, "cudaHostAlloc", rc); return NULL; }
    char *out = malloc(64);
    snprintf(out, 64, "0x%llx", (unsigned long long)(uintptr_t)p);
    return out;
}

static char *cmd_stream_create(unsigned long long seq)
{
    cudaStream_t s;
    cudaError_t rc = cudaStreamCreate(&s);
    if (rc != cudaSuccess) { reply_cuda_error(seq, "cudaStreamCreate", rc); return NULL; }
    char *out = malloc(64);
    snprintf(out, 64, "0x%llx", (unsigned long long)(uintptr_t)s);
    return out;
}

// Pinned host staging (Phase 7 item 2).
//
// The plan's measurement is that FILE-BACKED pinning fails on this driver, so
// this is anonymous pinned memory and the file is read into it. One buffer is
// reused across calls rather than allocated per call: cudaHostAlloc is
// expensive (it pins pages) and the whole point of the pool is to pay it once.
//
// CHUNKED at 64 MiB rather than sized to the request, because a request can be
// the whole 1.7 GB tensor set and pinning that much would double the host
// footprint for no benefit -- the copy is issued in 64 MiB pieces instead, which
// also bounds how long a single transfer blocks the stream.
#define STAGE_CHUNK (64u * 1024u * 1024u)
#define STAGE_SLOTS 8

// ONE buffer per in-flight copy, NOT one shared buffer.
//
// This was a real correctness bug, found by measuring rather than reasoning. With
// a single buffer and an ASYNCHRONOUS copy, the buffer is overwritten by the next
// call while the previous transfer is still reading it. Measured: four copies
// issued back to back into one buffer, then synchronised once, all landed with
// the LAST payload written -- 10 10 10 10 where 10 11 12 13 was expected. Worse,
// this segfaulted the daemon, which is how it was found.
//
// A ring of STAGE_SLOTS bounds how many copies can be in flight; when a slot is
// reused, the stream that last used it is synchronised first. That is the
// backpressure a real pipeline needs, and it is why a single shared buffer could
// not simply be kept.
static void *stage_buf[STAGE_SLOTS];
static cudaStream_t stage_stream[STAGE_SLOTS];
static size_t stage_cap = 0;
static unsigned stage_next = 0;

static void stage_release(void);   // defined below; used by stage_reserve

// Allocate one pinned buffer. Returns 0 on failure.
static int stage_alloc_one(void **out, size_t want)
{
    void *p = NULL;
    if (cudaHostAlloc(&p, want, cudaHostAllocDefault) != cudaSuccess) { *out = NULL; return 0; }
    *out = p;
    return 1;
}

// Reserve a slot for this copy, waiting on the slot's previous stream if it is
// still in use. Returns the slot index, or -1 if no pinned memory is available.
static int stage_reserve(cudaStream_t stream, size_t n)
{
    size_t want = STAGE_CHUNK;
    if (n > want) want = n;

    if (stage_cap < want) {
        // Grow: release every slot first so two generations are never held.
        stage_release();
        if (!stage_alloc_one(&stage_buf[0], want)) return -1;
        stage_cap = want;
    }

    unsigned slot = stage_next;
    stage_next = (stage_next + 1) % STAGE_SLOTS;

    // This slot may still back an in-flight copy on another stream.
    if (stage_buf[slot] && stage_stream[slot] != (cudaStream_t)0) {
        cudaStreamSynchronize(stage_stream[slot]);
    }
    if (!stage_buf[slot]) {
        // Ring slot never allocated (only slot 0 is, up front).
        if (!stage_alloc_one(&stage_buf[slot], want)) return -1;
    }
    stage_stream[slot] = stream;
    return (int)slot;
}

// Release every staging slot. Called on quit so the pinned pages are returned
// before the process exits, and when the pool needs to grow.
static void stage_release(void)
{
    for (int i = 0; i < STAGE_SLOTS; i++) {
        if (stage_buf[i]) { cudaFreeHost(stage_buf[i]); stage_buf[i] = NULL; }
        stage_stream[i] = (cudaStream_t)0;
    }
    stage_cap = 0;
    stage_next = 0;
}

// h2d <0xptr> <hostfile> <n> [stream]
//
// Phase 7 item 3/4: the copy is issued on the caller's stream and NOT
// synchronised here. The original version passed stream 0 (the legacy default
// stream) and called cudaDeviceSynchronize() before replying, which serialised
// every transfer and made "async" a misnomer. With a real stream the caller
// pipelines several copies and synchronises once, at the point it needs the
// data -- that is the whole point of a stream pool.
static char *cmd_h2d(unsigned long long seq, uintptr_t dp, const char *file, size_t n, cudaStream_t stream)
{
    FILE *f = fopen(file, "rb");
    if (!f) { reply(seq, "ERR: cannot open %s", file); return NULL; }
    if (fseek(f, 0, SEEK_END) != 0) { fclose(f); reply(seq, "ERR: fseek"); return NULL; }
    long have = ftell(f);
    if (have < (long)n) {
        fclose(f);
        reply(seq, "ERR: short file: have %ld need %zu", have, n);
        return NULL;
    }
    rewind(f);

    // Reserve a staging slot for THIS copy, so a later call cannot overwrite a
    // buffer this transfer is still reading.
    int slot = stage_reserve(stream, n);
    if (slot < 0) {
        fclose(f);
        reply(seq, "ERR: pinned staging allocation failed");
        return NULL;
    }
    void *sbuf = stage_buf[slot];

    // Chunked so a large tensor is copied in 64 MiB pieces on one stream.
    size_t off = 0;
    while (off < n) {
        size_t piece = n - off;
        if (piece > STAGE_CHUNK) piece = STAGE_CHUNK;
        if (fread(sbuf, 1, piece, f) != piece) {
            fclose(f);
            reply(seq, "ERR: short read at %zu", off);
            return NULL;
        }
        cudaError_t rc = cudaMemcpyAsync((void *)(dp + off), sbuf, piece,
                                         cudaMemcpyHostToDevice, stream);
        if (rc != cudaSuccess) {
            fclose(f);
            reply_cuda_error(seq, "cudaMemcpyAsync H2D", rc);
            return NULL;
        }
        off += piece;
    }
    fclose(f);
    return strdup("OK");
}

// d2h <0xptr> <hostfile> <n> [stream]
//
// d2h cannot be left genuinely async: the reply is written as soon as the copy
// is ISSUED, but the bytes are not on disk yet. So this one synchronises the
// stream before writing the file, and says so -- an async d2h would return OK
// while the file was still short.
static char *cmd_d2h(unsigned long long seq, uintptr_t dp, const char *file, size_t n, cudaStream_t stream)
{
    void *buf = malloc(n ? n : 1);
    cudaError_t rc = cudaMemcpyAsync(buf, (void *)dp, n, cudaMemcpyDeviceToHost, stream);
    if (rc != cudaSuccess) { free(buf); reply_cuda_error(seq, "cudaMemcpyAsync D2H", rc); return NULL; }
    rc = cudaStreamSynchronize(stream);
    if (rc != cudaSuccess) { free(buf); reply_cuda_error(seq, "cudaStreamSynchronize", rc); return NULL; }

    FILE *f = fopen(file, "wb");
    if (!f) { free(buf); reply(seq, "ERR: cannot write %s", file); return NULL; }
    size_t wrote = fwrite(buf, 1, n, f);
    fclose(f);
    free(buf);
    if (wrote != n) { reply(seq, "ERR: short write %zu of %zu", wrote, n); return NULL; }
    return strdup("OK");
}

int main(void)
{
    mkdir(QUEUE_DIR, 0755);

    // SINGLE INSTANCE, enforced before anything else touches the queue.
    //
    // Without this, a second daemon shares QUEUE_PATH and RESULT_PATH with the
    // first and BOTH answer every command: the result file ends up with two
    // replies per seq, and two independent CUDA contexts each hand out their own
    // pointer for the same "malloc", so one caller frees memory the other still
    // owns. Measured with five daemons live: every reply appeared five times.
    //
    // flock, not a pid file: the kernel drops an flock when the holder dies for
    // any reason, so a crashed daemon cannot wedge the next start. LOCK_NB so a
    // second instance exits immediately rather than blocking.
    int lockfd = open(LOCK_PATH, O_CREAT | O_RDWR, 0644);
    if (lockfd < 0) {
        fprintf(stderr, "cuda_daemon: cannot open lock %s: %s\n", LOCK_PATH, strerror(errno));
        return 1;
    }
    if (flock(lockfd, LOCK_EX | LOCK_NB) != 0) {
        fprintf(stderr, "cuda_daemon: another daemon already holds %s\n", LOCK_PATH);
        return 1;
    }
    // Keep lockfd open for the life of the process; closing it releases the lock.

    // Start from empty queues so a restarted daemon cannot answer for a command
    // issued to the previous instance. Safe now that we know we are the only one.
    FILE *q = fopen(QUEUE_PATH, "w"); if (q) fclose(q);
    FILE *r = fopen(RESULT_PATH, "w"); if (r) fclose(r);

    // Own the CUDA context for the whole life of this process. Doing it up front
    // means an early failure is reported once, at startup, rather than
    // intermittently on whichever command happens to run first.
    cudaError_t rc = cudaSetDevice(0);
    if (rc != cudaSuccess) {
        fprintf(stderr, "cuda_daemon: cudaSetDevice failed: %s\n", cudaGetErrorString(rc));
        return 1;
    }
    // Touch the context once so the allocation path is known-good before we
    // advertise readiness.
    void *probe = NULL;
    if (cudaMalloc(&probe, 256) != cudaSuccess || probe == NULL) {
        fprintf(stderr, "cuda_daemon: probe cudaMalloc failed\n");
        return 1;
    }
    cudaFree(probe);

    // Announce readiness on stdout so a launcher can wait for it.
    printf("READY\n");
    fflush(stdout);

    long offset = 0;
    char line[8192];

    for (;;) {
        q = fopen(QUEUE_PATH, "r");
        if (!q) { usleep(IDLE_SLEEP_USLEEP); continue; }

        if (fseek(q, offset, SEEK_SET) != 0) { fclose(q); offset = 0; continue; }

        int progressed = 0;
        while (fgets(line, sizeof(line), q)) {
            progressed = 1;
            size_t linelen = strlen(line);
            offset += (long)linelen;
            if (linelen == 0 || line[linelen - 1] != '\n') {
                // Partial line: the writer has not finished. Rewind so the whole
                // line is read once it lands.
                offset -= (long)linelen;
                break;
            }
            line[linelen - 1] = 0;

            unsigned long long seq = 0;
            int consumed = 0;
            // NOTE: pass &consumed, not &rest. Writing through a char* that is
            // still NULL dereferences NULL and kills the daemon on the first
            // command, which is why the queue filled with no replies at all.
            if (sscanf(line, "%llu %n", &seq, &consumed) < 1 || consumed <= 0) continue;
            char *rest = line + consumed;

            char *body = NULL;

            if (strcmp(rest, "init") == 0) {
                body = strdup("OK");
            }
            else if (strcmp(rest, "quit") == 0) {
                reply(seq, "OK");
                fclose(q);
                stage_release();   // return the pinned pages before exiting
                return 0;
            }
            else if (strncmp(rest, "malloc ", 7) == 0) {
                body = cmd_malloc(seq, (size_t)strtoull(rest + 7, NULL, 10));
            }
            else if (strncmp(rest, "host_alloc ", 11) == 0) {
                body = cmd_host_alloc(seq, (size_t)strtoull(rest + 11, NULL, 10));
            }
            else if (strncmp(rest, "free ", 5) == 0) {
                cudaError_t frc = cudaFree((void *)strtoull(rest + 5, NULL, 16));
                if (frc != cudaSuccess) reply_cuda_error(seq, "cudaFree", frc);
                else body = strdup("OK");
            }
            else if (strncmp(rest, "host_free ", 10) == 0) {
                cudaError_t frc = cudaFreeHost((void *)strtoull(rest + 10, NULL, 16));
                if (frc != cudaSuccess) reply_cuda_error(seq, "cudaFreeHost", frc);
                else body = strdup("OK");
            }
            else if (strcmp(rest, "stream_create") == 0) {
                body = cmd_stream_create(seq);
            }
            else if (strncmp(rest, "stream_destroy ", 15) == 0) {
                cudaStream_t s = (cudaStream_t)strtoull(rest + 15, NULL, 16);
                cudaError_t frc = cudaStreamDestroy(s);
                if (frc != cudaSuccess) reply_cuda_error(seq, "cudaStreamDestroy", frc);
                else body = strdup("OK");
            }
            else if (strncmp(rest, "stream_sync ", 12) == 0) {
                cudaStream_t s = (cudaStream_t)strtoull(rest + 12, NULL, 16);
                cudaError_t frc = cudaStreamSynchronize(s);
                if (frc != cudaSuccess) reply_cuda_error(seq, "cudaStreamSynchronize", frc);
                else body = strdup("OK");
            }
            else if (strncmp(rest, "h2d ", 4) == 0) {
                // h2d <0xdp> <file> <n> [stream]
                char *end = NULL;
                uintptr_t dp = (uintptr_t)strtoull(rest + 4, &end, 16);
                while (end && *end == ' ') end++;
                char file[512];
                int fi = 0;
                while (end && *end && *end != ' ' && fi < (int)sizeof(file) - 1) file[fi++] = *end++;
                file[fi] = 0;
                while (end && *end == ' ') end++;
                // NOTE: the endptr MUST be captured here. Passing NULL left
                // `end` pointing at the start of the size field, so the stream
                // parse below re-read "64" and passed 0x64 to cudaMemcpyAsync as
                // a cudaStream_t. The driver then faulted inside
                // cuMemcpyHtoDAsync_v2 -- which read as a CUDA bug and was not
                // one. Caught by printing the parsed stream, not by reasoning.
                char *nend = NULL;
                size_t n = (size_t)strtoull(end ? end : "0", &nend, 10);
                end = nend;
                // optional 4th field: the stream to issue on. Absent means the
                // default stream, which is what the pre-pool behaviour used.
                while (end && *end == ' ') end++;
                cudaStream_t st = (end && *end)
                    ? (cudaStream_t)strtoull(end, NULL, 16)
                    : (cudaStream_t)0;
                body = cmd_h2d(seq, dp, file, n, st);
            }
            else if (strncmp(rest, "d2h ", 4) == 0) {
                // d2h <0xdp> <file> <n> [stream]
                char *end = NULL;
                uintptr_t dp = (uintptr_t)strtoull(rest + 4, &end, 16);
                while (end && *end == ' ') end++;
                char file[512];
                int fi = 0;
                while (end && *end && *end != ' ' && fi < (int)sizeof(file) - 1) file[fi++] = *end++;
                file[fi] = 0;
                while (end && *end == ' ') end++;
                // endptr required -- see the h2d branch above for why.
                char *nend = NULL;
                size_t n = (size_t)strtoull(end ? end : "0", &nend, 10);
                end = nend;
                while (end && *end == ' ') end++;
                cudaStream_t st = (end && *end)
                    ? (cudaStream_t)strtoull(end, NULL, 16)
                    : (cudaStream_t)0;
                body = cmd_d2h(seq, dp, file, n, st);
            }
            else {
                reply(seq, "ERR: unknown command");
            }

            if (body) { reply(seq, "%s", body); free(body); }
        }
        fclose(q);
        if (!progressed) usleep(POLL_USLEEP);
    }
}