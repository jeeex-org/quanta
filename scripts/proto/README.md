# Threading prototype (Phase 7a) — ⚠️ NOT RELIABLE, see below

`parallel_matvec_proto.quanta` was written to prove that Quanta can thread a
matvec with raw `clone(2)`. It does run threads and it does go faster, but **the
result is intermittently wrong**, so the prototype is not usable.

    SERIAL   115-125 ms
    PARALLEL  35-54 ms
    MISMATCHES 0 on most runs, 153 observed on one run (first_row=8)

Run it with the compile-and-run wrapper:

    QUANTA_TIME_S=300 bash scripts/qcrun.sh --ccrun \
        scripts/proto/parallel_matvec_proto.quanta --no-overflow-trap

## Root cause: the child starts mid-function, with the PARENT's rbp

This is the whole problem, and it is not fixable from Quanta source.

`clone(2)` gives the child a new stack **pointer** (rsp) but the same instruction
**pointer** (rip), so the child resumes executing inside `spawn_worker` — the
function that called clone. It has not run that function's prologue, so **rbp is
still the parent's rbp**.

Quanta's register allocator spills to `spill_home(v) = -(SPILL_BASE + (v+1)*8)`,
which is **rbp-relative**. So every spill the child performs before it reaches a
frame of its own is written into the *parent's* stack frame — the parent's own
spilled variables and return addresses.

That is why the failure is intermittent and why it moves: whether a child clobbers
a parent slot depends on which vregs are live and which the allocator chose to
spill at that moment.

An earlier version of this README claimed "bit-identical, 0 mismatches, 2.42x".
That was measured on runs that happened to pass. It was wrong and is corrected
here.

## Why the obvious workarounds do not work

- **Baking the worker id in as a literal** (what the current proto does) stops the
  child *reading* the clobbered frame, so the ids and the row partition are right.
  It does not stop the child *spilling into* that frame.
- **An ack handshake** (child reads its id, publishes an ack, parent waits before
  returning) has a circular dependency: to write the ack the child must know
  *where* the ack is, which is a frame read — the very race it is trying to avoid.
  Measured: 0 mismatches but 93 s of spinning, i.e. the acks never landed.
- **Inline `asm` to set rbp** — Quanta has no inline-asm construct, so the child
  cannot repair its own frame.

## The correct fix: a `clone` builtin that emits a trampoline

Threads need a compiler-emitted entry trampoline, exactly as `pthread_create`
does: the child must land on a small stub that (a) establishes rbp for its own
frame and (b) reads its argument from the child stack (or a register) rather than
from the parent's frame.

That is a compiler change in `emitter.quanta` — the same class of work as the
existing `clock()` / `syscall()` builtins — and it is the prerequisite for any
threading in Quanta. Until it exists, `clone` must not be used for parallelism.

## What IS verified and reusable

- `syscall(56, flags, sp, 0, 0, 0)` with flags `0x10f00`
  (VM|FS|FILES|SIGHAND|THREAD) starts a real thread that shares memory. The child
  can write globals the parent observes — verified in a minimal case where the
  child only set a flag (parent saw it after 465 spins).
- `syscall(17, fd, buf, count, off, 0, 0)` is `pread64`. The generic `syscall()`
  builtin maps argument 4 to **r10**, exactly where `pread64` wants the offset.
  **Mandatory for any threaded read**: the fd is shared, so `lseek`+`read`
  interleaves and threads read each other's offsets.
- `clock()` (CLOCK_MONOTONIC ns), `rsp()` and `fnptr(fn)` all work.
- **No atomic means no work-stealing counter.** Read-increment-write let two
  workers claim the same row: 931/2048 rows wrong. A re-read "check-and-set" still
  left 500 wrong. Quanta exposes no xchg/lock-xadd, so use a **static partition**
  (`[w*chunk, (w+1)*chunk)`) — contention-free and deterministic.
- **Joining is mandatory.** The parent finishing its own partition says nothing
  about the children. One done-flag slot per worker, written only by that worker.
- Even when the result is correct, scaling was 2.4-3.4x on 4 workers, not 4x:
  workers contend on memory bandwidth (every row re-reads the same shared x
  vector) and on the fd.

## Order of work

1. Emit a thread-entry trampoline in the compiler (rbp + argument passing).
2. Only then: per-thread scratch for `mm_matvec` / `fc_layer`, which currently use
   module globals (`mm_rowbuf`, `fc_sc_*`, `fc_at_*`, `fc_fw_*`) that are a race
   by construction.
3. Invariant before it ships: **thread count must not change the result**,
   verified 1/2/4/20 against the existing llama.cpp oracle — and run it enough
   times to catch an intermittent fault, because that is exactly what this one
   was.
