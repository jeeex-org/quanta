# Loader resource politeness — the parked pool blocks, and the default is capped

Defect **A19**. Source of truth: `lib/std/lfm2_mm.quanta` and
`test_suites/scripts/run_tests.sh` (this tree). Everything below is a number that
was **measured on this box**; where a value is derived rather than measured it is
labelled.

Box: 20 online CPUs (`nproc=20`), governor **`powersave`** (unchanged), 63 GB RAM.
Ambient load through every measurement: `Hermes` desktop app at ~**747 %** CPU
(≈7.5 cores) — that is the desktop app, NOT the loader, and it was never touched.
`load average` was 10–17 throughout because of it. **Every timing below carries
its load and top consumer**; numbers taken under a peer's load are labelled.

---

## 1. The decisive question: do parked workers spin or block?

**They block. Parked, the pool costs 0.00 % CPU.**

Method (`tests/park_cpu_probe.quanta`): set 8 workers, call `mm_pool_begin()` +
`mm_pool_ensure(8, 2048)` so the 8 workers are spawned, and then **never submit a
job** — the workers are inside `futex_wait(pl_genp, last)`. Sample the process's
own CPU time from `/proc/self/stat` fields 14/15 (utime/stime, USER_HZ ticks,
summed over all threads) across a fixed 8 s park. A second, independent external
sampler reads `/proc/<pid>/stat` of the same pid.

Raw output (`bash /tmp/park_measure.sh` / `/tmp/park_wchan.sh`):

```
gov=powersave load=13.63 nproc=20
top consumer before:  752 2971875 Hermes
pid=3695915 num_threads=9 t0_ticks=0
t1_ticks=0
external: 0 ticks over 5009.22s -> 0.00% CPU (100=1 core)
=== probe stdout (its own in-process measurement) ===
PID 3695915
PARK_SECS=8 cpu_ticks=0 wall_ms=8000 cpu_pct_x1000=0
```

`num_threads=9` = main thread + **8 live workers** (so they really are spawned,
not exited). Per-thread scheduler state while parked:

```
tid=3696300 state=S wchan=hrtimer_nanosleep   <- main, inside sleep(8)
tid=3696302 state=S wchan=futex_do_wait        <- worker
tid=3696303 state=S wchan=futex_do_wait        <- worker
... (6 more, all futex_do_wait) ...
```

All 8 workers are state **S**, blocked in **`futex_do_wait`**. The pool does not
spin. The `futex_wait` builtin compiles to the real `futex(2)` `FUTEX_WAIT`
syscall with `timeout=NULL` (`compiler/0.0.243/src/x86/emitter.quanta:2714-2740`),
and the wait is genuinely blocking.

**Consequence.** The CPU a run costs is the CPU its workers *spend*, not CPU they
*burn waiting*. The lever is the worker **count**, not a wait-loop change. The
hypothesis that "parked workers spin, and that explains 533 % at 8 workers" is
**disproven by measurement** — 533 % is 8 workers legitimately doing dequant +
dot product.

---

## 2. The politeness policy

Rule, applied to every worker count the loader will use through
`mm_set_workers` / `mm_set_embed_workers`:

```
ceiling = min(affinity_cores / 2, 8), floored at 1
```

`affinity_cores` is the popcount of `sched_getaffinity(0, len, mask)`
(syscall 204) — the CPUs this process may *actually* run on, which is correct
under a cpuset / `taskset` where `/sys/devices/system/cpu/online` is not. On this
box that is `min(20/2, 8) = 8`.

Explicit escapes (a benchmark that genuinely wants the whole box):

| escape | effect |
|---|---|
| `mm_set_workers_uncapped(n)` / `mm_set_embed_workers_uncapped(n)` | set exactly `n` (still bounded by the hard ceiling 512) |
| `QUANTA_MM_WORKERS=<n>` | ceiling becomes `n` |
| `QUANTA_MM_ALL_CORES=1` | ceiling becomes every affinity core |

The env vars are read from `/proc/self/environ` **by hand**, because `getenv()`
is a **stub** in this compiler — `emitter.quanta:3879` literally emits
`// getenv is complex - for now return 0`, so it always returns 0. (Same reason
`lib/std/config.quanta` reads a file instead of the environment.) Verified:

```
QUANTA_MM_ALL_CORES=1 /tmp/ecp.bin
  sched_getaffinity rc=8  -> cores=20
  online string bytes=5 : ----
  -> cores=20
  QUANTA_MM_ALL_CORES value_offset=20 value=1
```

Two more guards, independent of the politeness ceiling:

* **`MM_MAX_WORKERS = 512`** in `mm_pool_ensure` — no caller, clamped or
  uncapped, can ask the pool to spawn an absurd number of threads (a
  process-level refusal, in place of a fork bomb).
* **Fail-closed NULL checks** on the four protocol words the pool allocates: a
  NULL `pl_genp` would make `atomic_store()` write to address 0 (a bare process
  kill); `mm_pool_ensure` returns −1 instead.

**What is deliberately NOT clamped:** the per-call entry points
`mm_matvec_par(idx,x,rows,cols,y,nw)` and `mm_embed_logits_par(...)` keep their
explicit `nw`. An explicit per-call count is itself an explicit override, and the
A9 gate row (`test_suites/codes/lfm2_threaded_pool_test.quanta`) depends on
passing `20` there — its leak guard (150 jobs × 20 workers) must stay a real
20-way exercise, or clamping would silently weaken it.

The politeness unit test, three environments (`tests/run_lfm2_polite_pool_test.sh`):

```
nproc=20 expected_ceiling_default=8
--- case: default (want ceiling=8) ---        CEILING 8    BAD_TOTAL 0  POLITE PASS
--- case: all_cores (want ceiling=20) ---     CEILING 20   BAD_TOTAL 0  POLITE PASS
--- case: workers_13 (want ceiling=13) ---    CEILING 13   BAD_TOTAL 0  POLITE PASS
POLITE POOL TEST: PASS
```

(`mm_set_workers(9999)` → 8; `mm_set_workers(-7)` → 0; `mm_set_workers_uncapped(9999)`
→ 512; `mm_set_workers_uncapped(13)` → 13; `mm_pool_ensure(0/-3/513)` → −1.)

---

## 3. Before / after — CPU % and wall, default vs all-cores

Driver: `tests/lfm2_polite_bench.quanta` — 4 × `fc_forward_token(35808, i)`
on the Q4_K_M model, bracketed by `mm_pool_begin/end`, timed with
`/usr/bin/time -v` at **`nice 0`** (a throughput measurement cannot run at
`nice -n 19` — that starves it, as the brief notes). "Before" is the **HEAD-lib
binary** (`git archive HEAD lib …` → `/tmp/oldtree`), same source, same golden
`qc`. RSS stayed **112–115 MB** (low hundreds of MB, as required).

| case | effective workers | wall (s) | **% CPU this job got** | user+sys / wall |
|---|---|---|---|---|
| **BEFORE** (HEAD lib, asked 20) | 20 | 21.01 | **831 %** | 174.7 / 21.0 = 8.3 cores |
| **AFTER** polite default (asked 20 → clamped) | **8** | 26.95 | **563 %** | 151.9 / 27.0 = 5.6 cores |
| **AFTER** all-cores (`QUANTA_MM_ALL_CORES=1`) | 20 | 21.22 | **827 %** | 175.6 / 21.2 = 8.3 cores |

Load/top beside each: `load=12.91 top=746 Hermes` (polite), `load=15.32 top=746
Hermes` (all-cores), `load=17.47 top=746 Hermes` (before). Sample verdicts:
`argmax_last=35808` in all three.

Reading it:

* The **default** costs ~5.6 cores instead of ~8.3 — **2.7 cores less**, for
  1.28× more wall time. That is the politeness trade, and it is the point: an
  unattended default now leaves ~2.7 more cores for everything else.
* The all-cores **escape** reproduces the before number to within noise (827 % vs
  831 %, 21.2 s vs 21.0 s), so the override really does hand back the old
  behaviour.
* **The 533 % / 818–892 % figures in the brief reproduce here (563 % / 827 %)**.
  Nothing about them was a spin: they are legitimate parallel work.

**Why it cannot take a 20-core box, even at 20 workers.** 20 workers use ~8.3
cores, not 20 — the workload is **memory-bandwidth-bound** (A9 already noted
8 → 20 workers buys only 1.3× on 2.5× the threads). So `% CPU` plateaus near the
bandwidth ceiling regardless of worker count. The politeness cap lowers the
plateau further and, importantly, bounds it on a *smaller* box, where
`min(cores/2, 8)` is what stops an unattended run from wanting every core.

---

## 4. Good citizenship — a concurrent task still makes progress

The property the author asked for, as a number. A trivial single-threaded
CPU-bound task (`python3 /tmp/spin.py 24000000`, ~2.3 s standalone) was timed in
six successive samples in three states (`bash /tmp/citizen.sh`):

| state | spin wall, n=6 (median) | min | max | slowdown vs idle |
|---|---|---|---|---|
| idle (ambient Hermes only) | **2.334 s** | 2.298 | 2.487 | 1.00× |
| loader polite 8 workers | **3.055 s** | 2.878 | 4.026 | **1.31×** |
| loader all-cores 20 workers | **3.731 s** | 3.190 | 3.899 | **1.60×** |

The loader each time ran 12 forwards (8 w: `wall_ms=79781`; 20 w:
`wall_ms=66640`). Load/top: `load≈12 top=747 Hermes` (idle), `load≈12 top=747`
(8 w), `load≈15 top=747` (20 w).

Reading it:

* The concurrent task **completed every sample in every state** — it is not
  starved. Median progress under the loader is **63–76 % of its idle speed**, on
  a box already carrying ~7.5 cores of Hermes.
* The **polite default is measurably kinder**: the neighbour is **1.31× slower**
  under 8 workers vs **1.60× slower** under 20 — ~18 % faster to the neighbour,
  for the 1.28× wall cost the loader itself pays. That is the whole trade in one
  pair of numbers.
* This is the honest ceiling on the claim: on a 20-core box *even the all-cores
  setting does not starve the neighbour*, because the loader is bandwidth-bound
  (§3). The politeness cap is what extends that guarantee to smaller boxes and to
  a busier machine.

---

## 5. The failure / OOM path audit (what was found and fixed)

* **Division by zero (the SIGFPE class).** Every parallel entry point guards
  *before* dividing: `mm_matvec_par` (`nworkers <= 1`), `mm_embed_logits_par`
  (`nworkers <= 1 || vcount <= 0`), `mm_matmul` (`mm_workers <= 1` then
  `per < 1`), `mm_embed_logits_batch` (`mm_embed_workers <= 1` then `per < 1`),
  `mm_matvec` (`mm_workers > 1`), `mm_embed_logits` (`mm_embed_workers > 1`).
  Read at source; the `mm_workers == 0` batched-path SIGFPE was already fixed
  (A12) and is pinned by `tests/lfm2_mm_workers_zero_test.quanta`, which
  **still passes** with this change (`WORKERS0 PASS`, `TOTAL_MISMATCH=0`).
* **Worker count zero / negative.** `mm_set_workers`/`mm_set_embed_workers`
  clamp negatives to 0 (serial); `mm_pool_ensure` returns −1 for `n <= 0`.
  Confirmed by the politeness test (`ensure_zero`, `ensure_neg` → −1).
* **Absurd worker count (new).** `mm_pool_ensure` now returns −1 for
  `n > MM_MAX_WORKERS (512)`. Previously a caller could ask for any `n` and the
  pool would try to `thread_create` that many times — a route to exhausting the
  machine's threads/PIDs rather than failing the process. Fixed
  (`ensure_absurd` → −1).
* **Allocation failure in the pool (new).** The four protocol words are now
  NULL-checked; a failure returns −1 instead of letting `atomic_store` write to
  address 0.
* **Thread-creation failure — NOT fixable from the lib, reported.** The
  `thread_create` emitter path `exit(1)`s **on the main thread** when its child
  stack `mmap` fails (`emitter.quanta`), so the group's status can come out 0 —
  the silent-death shape of A9. A library cannot intercept it. The politeness cap
  and `MM_MAX_WORKERS` make it much less likely; the complete fix is in the
  emitter (round-trip an error rather than `exit(1)`), which is compiler work and
  out of this unit's scope.
* **OOM that could take the machine down.** The historical machine-killer was the
  address-space leak (2329 `clone()`s / ~2.3 GB per forward), fixed in A9 by the
  single-spawn pool. Post-fix the pool allocates once: `n × (~28 KB scratch for a
  2048-wide row)` plus four protocol words — bounded and small (RSS 112–115 MB
  measured). The loader itself has **no unbounded allocation** in the pool path.
  The remaining machine-level guard is the caller's `ulimit -v`
  (`scripts/quanta_run.sh` caps at 1–1.5 GB); the loader does not set one.
* **`fc_attn_workers` (parallel attention body) — REMOVED.** It defaulted 0 and had
  **no setter** in the tree (`grep` found only reads), so nothing ever reached the
  per-call `thread_create` attention body. It was **removed** in `21a7be4b` (A21)
  rather than left as-is: enabling it was a leak bomb — ~1.35x faster at
  `pos=1600`, but 64 MB of address space leaked per forward token (8 layers x 8
  threads x 1 MB, the retired per-call `thread_create` pattern), dead at ~128
  tokens under the 8 GB cap. The re-add is queued through the persistent pool (the
  same pool treatment as A9). See `docs/research/fc-attn-workers-removal.md`.

---

## 6. Adjacent finding (NOT fixed — out of scope, reported)

`tests/lfm2_prefill_bench.quanta` — the realistic-prompt prefill driver — **has
not returned in 240 s** on this box: it prints through `prompt_bytes=10890`, then
sits in `chat_build` / `bpe_encode_special` over the 10,890-byte SI-loop prompt
and never reaches the timed prefill region. Reproduced on **both** the HEAD-lib
and current binaries, so it is **independent of the A19 change** and predates it.
That is why this measurement uses `tests/lfm2_polite_bench.quanta` (fixed token
ids, no tokenizer) instead. The tokenizer cost (or a hang) on a 10 KB prompt is a
real item for whoever owns the BPE path.

---

## 7. Gate integrity — a check whose colour the exit ignored

`test_suites/scripts/run_tests.sh` **printed** `gguf-corrupt` and `float-print`
in the `GATE SUMMARY`, but `GGUF_RC` and `FPR_RC` were **absent from the exit
condition** (the old line 888). Every other stage's RC folds into
`FUNCTIONAL_RC` at its definition (`:`156, `190`, `241`, `273`, `296`, `329`,
`364`) or is named in the exit test; **these two did neither** — so a RED
gguf-corrupt or float-print stage could not turn the gate red. A check that
cannot fail is worse than no check. Fix: name `GGUF_RC` and `FPR_RC` in the exit
condition. Red-first demonstration in the accompanying message/log.
