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
#include <cuda_runtime.h>

#ifndef QUEUE_DIR
#define QUEUE_DIR "/tmp/quanta_cuda"
#endif
#define QUEUE_PATH QUEUE_DIR "/queue"
#define RESULT_PATH QUEUE_DIR "/result"
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

// h2d <0xptr> <hostfile> <n>
static char *cmd_h2d(unsigned long long seq, uintptr_t dp, const char *file, size_t n)
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
    void *buf = malloc(n ? n : 1);
    if (fread(buf, 1, n, f) != n) { fclose(f); free(buf); reply(seq, "ERR: short read"); return NULL; }
    fclose(f);

    cudaError_t rc = cudaMemcpyAsync((void *)dp, buf, n, cudaMemcpyHostToDevice, 0);
    if (rc != cudaSuccess) { free(buf); reply_cuda_error(seq, "cudaMemcpyAsync H2D", rc); return NULL; }
    rc = cudaDeviceSynchronize();
    free(buf);
    if (rc != cudaSuccess) { reply_cuda_error(seq, "cudaDeviceSynchronize", rc); return NULL; }
    return strdup("OK");
}

// d2h <0xptr> <hostfile> <n>
static char *cmd_d2h(unsigned long long seq, uintptr_t dp, const char *file, size_t n)
{
    void *buf = malloc(n ? n : 1);
    cudaError_t rc = cudaMemcpyAsync(buf, (void *)dp, n, cudaMemcpyDeviceToHost, 0);
    if (rc != cudaSuccess) { free(buf); reply_cuda_error(seq, "cudaMemcpyAsync D2H", rc); return NULL; }
    rc = cudaDeviceSynchronize();
    if (rc != cudaSuccess) { free(buf); reply_cuda_error(seq, "cudaDeviceSynchronize", rc); return NULL; }

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

    // Start from empty queues so a restarted daemon cannot answer for a command
    // issued to the previous instance.
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
                // h2d <0xdp> <file> <n>
                char *end = NULL;
                uintptr_t dp = (uintptr_t)strtoull(rest + 4, &end, 16);
                while (end && *end == ' ') end++;
                char file[512];
                int fi = 0;
                while (end && *end && *end != ' ' && fi < (int)sizeof(file) - 1) file[fi++] = *end++;
                file[fi] = 0;
                while (end && *end == ' ') end++;
                size_t n = (size_t)strtoull(end ? end : "0", NULL, 10);
                body = cmd_h2d(seq, dp, file, n);
            }
            else if (strncmp(rest, "d2h ", 4) == 0) {
                char *end = NULL;
                uintptr_t dp = (uintptr_t)strtoull(rest + 4, &end, 16);
                while (end && *end == ' ') end++;
                char file[512];
                int fi = 0;
                while (end && *end && *end != ' ' && fi < (int)sizeof(file) - 1) file[fi++] = *end++;
                file[fi] = 0;
                while (end && *end == ' ') end++;
                size_t n = (size_t)strtoull(end ? end : "0", NULL, 10);
                body = cmd_d2h(seq, dp, file, n);
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