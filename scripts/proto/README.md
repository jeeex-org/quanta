# Threading prototype (Phase 7a)

`parallel_matvec_proto.quanta` is the working proof that Quanta can thread a
matvec with raw `clone(2)`, plus the serial reference and a bit-for-bit
comparison. Run it with the compile-and-run wrapper:

    QUANTA_TIME_S=300 bash scripts/qcrun.sh --ccrun         scripts/proto/parallel_matvec_proto.quanta --no-overflow-trap

Measured on the 2048x2048 Q4_K tensor, 4 workers, 20-core box:

    SERIAL   122.9 ms
    PARALLEL  50.8 ms    2.42x
    MISMATCHES 0

## What works

- `syscall(56, flags, sp, 0, 0, 0)` with flags `0x10f00`
  (VM|FS|FILES|SIGHAND|THREAD) starts a real thread. The child resumes in the
  CALLER's context and shares memory, so it can write globals the parent sees.
- `syscall(17, fd, buf, count, off, 0, 0)` is pread64. The generic `syscall()`
  builtin maps argument 4 to `r10`, which is exactly where pread64 wants the
  offset. **This is mandatory for any threaded file read**: the fd is shared, so
  `lseek`+`read` interleaves and threads read each other's offsets.
- `clock()` (CLOCK_MONOTONIC ns) and `rsp()` work.

## Three traps, each measured

1. **The child runs in the parent's stack frame.** Raw `clone` gives the child a
   new stack pointer but the same instruction pointer, so it resumes inside the
   spawn function and any value it reads from that frame is clobbered when the
   parent returns and calls the spawner again. Symptom: one wrong row, and the
   done flags never landed (parent spun its full 2e9 bound, 125 s). The prototype
   works around it by giving each spawner a LITERAL worker id. The general fix is
   a real entry trampoline that reads arguments off the child's own stack, like
   `pthread_create` does.
2. **No atomic means no work-stealing counter.** Read-increment-write on a shared
   counter let two workers claim the same row: 931 of 2048 rows wrong. Adding a
   re-read "check-and-set" still left 500 wrong. Quanta exposes no
   xchg/lock-xadd, so the prototype uses a STATIC PARTITION instead --
   contention-free, deterministic, and correct.
3. **Joining is not optional.** The parent finishing its own partition says
   nothing about the children. Comparing before they finish reads half-written
   rows. The prototype uses one done-flag slot per worker, each written only by
   that worker, so the flags themselves do not race.

## Scaling

2.42x on 4 workers, not 4x. The workers contend on memory bandwidth (all 2048
rows read the same shared 2048-element x vector per row) and on the shared fd
for pread. Both are worth attacking before scaling the worker count.

## Not yet done

- A real entry trampoline (removes the literal-id workaround).
- Wiring this into `mm_matvec` / `fc_layer`: those currently use module-global
  scratch (`mm_rowbuf`, `fc_sc_*`, `fc_at_*`, `fc_fw_*`), which is a race by
  construction. Each worker needs its own, as this prototype does via
  `worker_scratch(w)`.
- Required invariant before it ships: thread count must not change the result.
  Enforced by running 1/2/4/20 workers and comparing logits bit-for-bit against
  the existing llama.cpp oracle.
