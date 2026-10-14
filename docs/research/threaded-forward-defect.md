# The threaded-forward defect (A9) — silent death after one parallel forward

**Symptom as reported:** with `mm_set_workers(20)` set, the native LFM2 engine dies
after exactly one threaded forward pass, with exit status **0** and no message.
`stage1/par_test.quanta` writes a marker before the forward (111) and after it;
only the first file appeared.

**Status: ROOT-CAUSED, FIXED, MEASURED.** Defect number **A9** in `docs/plans/bugs.md`.
Everything below is from raw output in this session (golden compiler
`compiler/0.0.236/bin/x86/qc`, HEAD `9bd49b67`, VERSION 0.0.236).

---

## 1. Reproduction, exactly as reported

`stage1/par_test.quanta`, `ulimit -c 0 -v 4194304`:

```
$ rm -f stage1/logs/par_before.bin stage1/logs/par_after.bin
$ ulimit -c 0 -v 4194304; timeout 120 nice -n 19 ./stage1/bin/par_test.bin </dev/null
run_rc=0
--- before ---   o \0 \0 \0 \0 \0 \0 \0        (111 decimal = 0x6f = 'o')
--- after  ---   od: No such file or directory
```

3/3 identical. **`rc=0` with the "after" marker absent.**

The cap matters, and that is the first clue: the recorded reproduction in
`stage1/RESULTS.md` §2b used `-v 4194304`. Under the sanctioned ceiling
(`-v 8000000`) ONE forward *completes* (5/5 runs, `r=0` printed). So the engine
does not die "after one forward" in general -- it dies when the address space runs
out, and one forward is what it takes at 4 GB.

`tests/threaded_forward_twice.quanta` shows both faces of it (`tests/...` because
it needs the model and ~26 s; see §6):

| build | cap | rc | forward-1 marker | forward-2 marker | RSS |
|---|---|---|---|---|---|
| pre-fix | 4 GB | 0 | MISSING | MISSING | 178 MB |
| pre-fix | 8 GB | 0 | ok | **MISSING** | 369 MB |
| fixed | 4 GB | 7 | ok | ok | 154 MB |
| fixed | 8 GB | 7 | ok | ok | 116 MB |

The 8 GB row is the report verbatim: forward 1 fine, process gone during forward 2,
**status 0**.

## 2. Bisect: what actually happens

`strace -f -e trace=mmap,clone,exit,exit_group` over one forward at 20 workers:

* **2329 `clone()` calls** for a single 30-layer forward (`grep -c ' clone(' -> 2329`).
  `thread_create()` mmaps a fresh **1 MiB** child stack plus a page-rounded 24-byte
  join slot per call, and `thread_join()` never unmaps either -> **~2.33 GB of
  address space leaked per forward**, before counting the per-matvec worker scratch.
* The last syscalls of the dying run, on the **main thread**:

```
2219451 mmap(NULL, 1048576, PROT_READ|PROT_WRITE, MAP_PRIVATE|MAP_ANONYMOUS, -1, 0) = -1 ENOMEM
2219451 exit(1)                                                            = ?
2219451 +++ exited with 0 +++
```

That `exit(1)` is the emitter's MAP_FAILED guard for the child-stack mmap
(`compiler/0.0.236/src/x86/emitter.quanta`, thread_create, FIX-0.0.36 region):
`mov edi,1; mov eax,60; syscall`. It runs **before** `clone()`, i.e. on the thread
that called `thread_create` -- the main thread.

Why the reported status is 0 and not 1: the guard uses **`exit(60)`, not
`exit_group(231)`**. The 20 workers of the group are still running; they exit 0;
the group's final status comes out 0. strace confirms both halves
(`exit(1)` on the main pid, then `+++ exited with 0 +++`). The after-marker is never
written because the main thread is gone.

**So the single-forward death is: address-space exhaustion caused by a 1 MiB
per-thread stack leak, whose failure path is a silent `exit(1)` on the main thread
that the OS reports as 0.**

A second-order detail from the same trace: a worker of the *previous* matvec also
hit `mmap(65544) = -1 ENOMEM` and exited 1 (the emitter's mem_alloc MAP_FAILED
guard is the same shape), so a matvec partition could be silently dropped as well.

## 3. Hypotheses tested and rejected

| hypothesis (from the task) | measurement | verdict |
|---|---|---|
| a trap swallowed by the exit path | `strace -e trace=signal,exit_group` shows **no signal**; the exit is an explicit `exit(1)` from a guard | rejected |
| missing per-thread initialisation (`fc_kv_init`, as `stage1/native_gen.quanta` needed) | `par_test` calls `fc_kv_init(256)` before the forward, and the same sequence works serially; `fc_kv_init` has no thread-local state | rejected |
| stack/memory corruption in a worker | pooled results are **bit-identical to the serial block path** element-wise at 2/4/8/20 workers (`std_matvec_par_test` rc=0; the new gate row rc=7) and argmax is 5922 at every worker count | rejected |
| bad worker count vs available cores | 20 workers on 20 cores completes fine once memory suffices (~12.6 s/token) | rejected |
| bad synchronisation between workers | static row slices, `pread`-based reads, no shared scratch; the leak is the only scaling problem | rejected |

`fc_kv_init`'s other half of the question: it **is** declared in `lib/std` and
nothing in `lib/std` calls it (`grep -rn fc_kv_init lib/std/` -> the definition
only); callers do it explicitly, which is documented behaviour
(`stage1/RESULTS.md` §1). The threaded path is not missing it -- the threaded
path's broken premise is **memory**, not initialisation.

Also ruled out as the mechanism: `print`/stdout loss. `par_test` prints `r=0`
normally on a run that completes; nothing survives a run that deadlocks the
forward.

## 4. The fix

`lib/std/lfm2_mm.quanta`: the row-parallel matvecs now share a **persistent worker
pool** instead of spawning `nworkers` threads per matvec call.

* Protocol (one job in flight; the driver is the only writer of `pl_gen`, so no CAS
  is needed): driver fills the `pl_*` job globals -> `fence()` -> `atomic_store(pl_gen,
  gen+1)` -> `futex_wake(gen)`; every worker wakes on the generation, runs its static
  row/vcount slice, stamps `done[t] = gen` (`atomic_store` + `futex_wake`); the driver
  waits for all stamps. `done[t]` is written by worker *t* only, so there is no shared
  counter to race on. The driver sleeps in `futex_wait` (it does not spin).
* Worker liveness: the driver's wait also reads the worker's join-slot tid
  (`0 = exited`, the same word `thread_join` uses) and returns **-1** rather than
  blocking forever if a worker died instead of stamping.
* Scratch (the `mm_scratch_new` cell) is allocated **once per worker** and reused,
  which also removes the per-matvec scratch leak.
* `mm_pool_begin()` / `mm_pool_end()` nest by depth;
  `fc_forward_token_ex` (renamed body = `fc_forward_token_body`) brackets one forward
  with them. The runtime ends `main` with `exit(60)`, **not** `exit_group(231)` --
  measured: a live worker thread after `main` returns hangs the process
  (`stage1/hang_probe.quanta`, rc=124) -- so the bracket guarantees no live worker is
  left at process exit. A generation loop can hold the pool across many forwards by
  bracketing the loop itself (`stage1/native_bench_w.quanta` does).

Effect, measured with `strace -f -e trace=clone`:

| | clones per 30-layer forward |
|---|---|
| pre-fix | **2329** |
| fixed | **20** |

and `par_test` under the recorded cap now completes:
`ulimit -c 0 -v 4194304 -> rc=0, before=ok, after=ok, r=0`.

## 5. Real parallel decode -- measured

`stage1/native_bench_w.quanta` (`stage1/bench_w.conf` = "NW NF"), same prompt token
(35808, pos 0, full-vocab logits), `ulimit -c 0 -v 8000000`, `NF=2`; machine load
11.27 11.42 10.87 on 20 cores (so these are under contention):

```
for nw in 1 2 4 8 20; do printf "$nw 2\n" > stage1/bench_w.conf; /tmp/bwf.bin </dev/null; done
```

| workers | forward ms (run 0 / run 1) | s/token | tok/s | speedup |
|---|---|---|---|---|
| 1 (serial) | 72322 / 68727 | **70.5** | 0.0142 | 1.00x |
| 2 | 43229 / 40319 | 41.8 | 0.0239 | 1.69x |
| 4 | 24468 / 24484 | 24.5 | 0.0408 | 2.88x |
| 8 | 16778 / 16583 | **16.7** | 0.060 | 4.23x |
| 20 | 12555 / 13072 | **12.8** | 0.078 | 5.50x |

* `argmax = 5922` on **every** run at every worker count (equals the serial
  reference in `stage1/RESULTS.md` §1), and three consecutive 20-worker forwards in
  one process give 12643 / 12621 / 12403 ms, all 5922.
* Serial 70.5 s/token agrees with the doc's 69.4 s/token (and RESULTS.md's 77).
* **`docs/plans/lfm2-native-inference-perf.md`'s 25.8 s/token @8 workers is BEATEN:
  16.7 s/token measured.** The doc's parallel figure is real; the defect was hiding it.
* Above 8 the curve flattens hard: 8 -> 20 workers (2.5x the threads) buys only
  1.3x, which is the shape the doc predicts for a bandwidth-bound matvec. A separate
  pre-existing fact explains the ceiling better than thread count: the matvec reads
  each weight row with one `pread` + a scalar `mm_dot4` (see the two long comments in
  `lfm2_mm.quanta`); the win available is SIMD/blocked dot products, not more workers.

## 6. The red-first test

Two artifacts, because a single one cannot satisfy both the gate's 15 s cap and the
need to distinguish "died" from "ran":

**a) Gate row** `test_suites/codes/lfm2_threaded_pool_test.quanta` +
`test_suites/EXPECTED.tsv` (`lfm2_threaded_pool_test.quanta  7  <model>`).

* Runs **150 jobs at 20 workers** (and 4 jobs each at 8/4/2 for the identity check)
  under one held pool, then compares element-wise against the serial block reference,
  and encodes completion as **rc=7** -- deliberately not 0, because this defect's
  failure mode also reports 0 (rule #16: a rc=0 row would pass while dying).
* RED on the pre-fix tree: `qc` reports `call to undeclared function: mm_pool_begin`
  / `mm_pool_end` and exits **7** with no binary, so the gate's compile step fails it.
* GREEN post-fix: **rc=7 in 3.78 s** under the gate's 1536 MB / 15 s guards.
  It is also a genuine leak guard: if the pool regresses to per-call threads, this
  loop leaks 150x20 = 3000 stacks (~3 GB) and dies (measured: the row then
  **TIMEOUTS**, rc=124, i.e. still fails).

**b) The literal "runs a threaded forward twice" repro**
`tests/threaded_forward_twice.quanta` + `tests/run_threaded_forward_twice.sh`.

* Two full threaded forwards at 20 workers, rc=7 plus a marker file after each.
* A/B (raw output reproduced in §1): pre-fix 4 GB = dies in forward 1; pre-fix
  8 GB = dies in forward 2; fixed = rc=7 with both markers at 4 GB **and** 8 GB.
* Put in `tests/` rather than `EXPECTED.tsv` because (i) it needs the 1.67 GB model,
  (ii) two forwards take ~26 s > the gate's 15 s cap, and (iii) rc alone cannot detect
  this defect (the death reports 0), so the assertion needs the marker files and
  therefore a wrapper script.

## 7. Repro script (both directions)

```
# fixed (current tree)
cd /opt/tali/quanta && ulimit -c 0 -v 8000000
./compiler/0.0.236/bin/x86/qc tests/threaded_forward_twice.quanta /tmp/tft.bin
( ulimit -c 0 -v 4194304; timeout 300 /tmp/tft.bin </dev/null ); echo rc=$?
#  -> rc=7, stage1/logs/tft_forward1.bin and tft_forward2.bin both written

# pre-fix: swap HEAD's lib/std/lfm2_mm.quanta + lfm2_forward.quanta back in, recompile
git show HEAD:lib/std/lfm2_mm.quanta      > lib/std/lfm2_mm.quanta
git show HEAD:lib/std/lfm2_forward.quanta > lib/std/lfm2_forward.quanta
./compiler/0.0.236/bin/x86/qc tests/threaded_forward_twice.quanta /tmp/tft_old.bin
( ulimit -c 0 -v 4194304; timeout 300 /tmp/tft_old.bin </dev/null ); echo rc=$?
#  -> rc=0, no markers (died inside forward 1)
```

## 8. What this does NOT fix (stated, not hidden)

1. **Residual leak.** `thread_create` still never unmaps its 1 MiB child stack, so
   every *pool* leaks `nworkers` stacks. `fc_forward_token_ex` brackets one forward,
   so a naive forward loop still leaks ~20 MB/forward (down from ~2.33 GB/forward,
   ~116x). Holding the pool across a loop (`mm_pool_begin` before / `mm_pool_end`
   after) makes it 20 MB **per process**. The complete fix is an emitter change --
   `thread_join` munmapping the child stack and join slot, which needs the stack base
   recorded in the join slot -- and that is a compiler change; `compiler/0.0.237/**`
   is another unit's tree, so it is left as the follow-up A9 records.
2. **Bare `mm_matvec_par` callers outside a bracket** still get a pool created and
   torn down per call (i.e. `nworkers` thread spawns per call, no improvement).
   Bracket the loop to benefit. The forward does it for you.
3. **`fc_attn_workers`** (the parallel attention body in `lfm2_forward.quanta`) still
   spawns per-call threads. Nothing sets it (default 0), so it is unexercised -- a
   latent copy of the same leak.
4. **A worker that traps mid-slice** blocks the driver. The slice allocates nothing,
   so this needs a trap; the pre-fix design would have reported a silently wrong
   result instead, so this is not obviously worse, but it is not fixed.
5. **A timed `futex_wait` was tried and REVERTED.** A raw
   `syscall(202, uaddr, FUTEX_WAIT, val, &timespec, 0, 0)` in the driver made the token
   stream diverge (argmax 5922 -> 35808 / 8696, varying run to run) while the same
   binary with the untimed wait was stable at 5922 across repeats. Do not reintroduce
   it without a determinism check.
6. **`test_suites/codes/std_matvec_par_test.quanta` exists but has no
   `EXPECTED.tsv` row** -- the parallel-vs-serial identity test was never gated. It
   passes (rc=0, 1/2/4/8 workers, 0 mismatches) and is exercised manually here; the
   new row covers 2/4/8/20 workers in the gate.
7. **The full gate was not run** (load-sensitive, and `lib/std/gguf.quanta` carries
   another unit's uncommitted A1b change in this tree). Instead the 11 model/lfm2
   adjacent rows were run individually: `gguf_forward_pass_test`, `stdlib_lfm2_mm_test`,
   `stdlib_lfm2_attn_test`, `stdlib_lfm2_conv_test`, `stdlib_lfm2_rope_test`,
   `stdlib_lfm2_bpe_test`, `stdlib_lfm2_pretok_test`, `stdlib_lfm2_chat_test`,
   `embedding_test`, `gguf_fp_inference_test`, `gguf_general_test` -- all rc=0 after the
   change, plus the new row rc=7 and `std_matvec_par_test` rc=0.

## 9. Files

| path | change |
|---|---|
| `lib/std/lfm2_mm.quanta` | worker pool; `mm_matvec_par` / `mm_embed_logits_par` route through it |
| `lib/std/lfm2_forward.quanta` | `fc_forward_token_body` + bracketing `fc_forward_token_ex` |
| `test_suites/codes/lfm2_threaded_pool_test.quanta` | new gate row (rc=7) |
| `test_suites/EXPECTED.tsv` | +1 row (model prerequisite in SKIP_IF_MISSING) |
| `tests/threaded_forward_twice.quanta`, `tests/run_threaded_forward_twice.sh` | new red-first two-forward repro |
| `stage1/native_bench_w.quanta`, `stage1/bench_w.conf` | worker-count benchmark |
| `stage1/clone_probe.quanta`, `stage1/hang_probe.quanta` | mechanism probes (clone+wait reuse; live-thread-at-exit hang) |
| `docs/plans/bugs.md` | A9 appended |

`stage1/` is scratch and is **gitignored** on this machine (`git check-ignore -v
stage1/native_bench_w.quanta` -> `.gitignore:19:/*`), exactly like the rest of the
stage1 workstream (`par_test.quanta`, `native_bench.quanta`, `RESULTS.md`). The files
are on disk; the commands above recreate them anywhere.
