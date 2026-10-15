# 0.0.244 — WIP · **LEVER: A4 / next-use eviction — implemented as specified, and it does NOT close the C gap**

```
0.0.243 golden  md5 26430066a4e04f61a687ccf6291b61d7   (frozen baseline, untouched)
0.0.244 shipped md5 886e36f8318aaae414e188e947d11c49   (the seed-chain FIXED POINT)
```

Two files changed: `src/x86/emitter.quanta` (the A4 victim selector) and
`src/x86/codegen.quanta` (publish the next-use context from the emit loop).
Everything else in `compiler/0.0.244/` is the 0.0.243 snapshot copied verbatim
(the same stale-snapshot situation 0.0.239-0.0.243 recorded); imports resolve to
the REPO `lib/std`, which is what the build and the gate use.

**Read `docs/research/a4-next-use-eviction-measurements.md` for the evidence.**
This file states the result.

---

## 1. What landed

`afree()` and `afree_x()` used to evict the LAST entry of the allocator map — the
most recently allocated value, i.e. the one most likely to be needed again. They now
evict the vreg whose **next use is farthest away**, and a vreg with **no use left in
the block** (it is dead) is the best victim of all. Ties keep the LIFO choice, so a
function where the two rules agree emits byte-identical code.

* `emitter.quanta:312-331` — `a4_at` / `a4_end` / `A4_WINDOW=64` / `A4_FAR`
* `emitter.quanta:343-361` — `a4_reads(k, vr)`, the read-set of an IR op
* `emitter.quanta:365-376` — `a4_next_use(vr, from, lim)`, bounded + block-aware
* `emitter.quanta:381-396` — `a4_pick(ex)`, the selector
* `emitter.quanta:574-600` / `434-460` — `afree()` / `afree_x(ex)` victim choice
* `codegen.quanta:1437-1438,1440,3285-3289` — publish / advance / withdraw the context

Safety argument, in full:

1. **Any victim is value-correct.** `sdef(vr, reg)` writes the home slot at every
   definition (`emitter.quanta:1102`) and a mapped register is never modified in
   place, so an evicted vreg is always reloadable. `a4_reads` therefore only has to
   rank victims; it can be imprecise without being wrong. This is what makes the
   read-set safe to write without a full liveness framework.
2. **The scan stops at a block boundary.** Codegen calls `flush_all()` at `IR_LABEL`,
   `IR_JMP`, `IR_BR` and `IR_RET` (`codegen.quanta:2344-2359`), so the allocator map
   is empty at any block boundary — a value live past one is spilled and reloaded
   whatever register held it. Within a block the scan is exact.
3. **It is inert with no context.** `a4_pick()` returns -1 when `a4_at < 0` and the
   caller keeps the original LIFO branch; `a4_at` is -1 before the loop, after the
   loop, and outside `ci_func`'s emit loop entirely.

## 2. The measured result — and the premise it refutes

`scripts/bench_ab.sh` (best-of-8, interleaved, load 11.4-12.0) and the new
`scripts/bench_instr.sh` (load-independent), all 38 cases:

* **37 of 38 cases emit byte-identical code** — every instruction, frame and
  spill-count column equal, and 36 of 39 A/B rows report `IDENTICAL-CODE`.
* The rows whose code changes are **`file_io`, `params8`** and the purpose-built
  `regpressure` — and `file_io`/`params8` are **exactly the two cases** an
  instrumented build counts evictions in. Predictor and A/B agree row for row.
* On `regpressure`, the hot-loop body drops **401 -> 381 instructions (-5.0 %)** and
  **259 -> 239 frame-relative memory operations (-7.7 %)**. That is the lever, and
  it is real — it just has almost nothing to work on.
* **No parity case regressed.** All 12 (`nested_calls`, `recursion`, `float_ops`,
  `match`, `mem_ops`, `file_io`, `fib`, `q4k_matmul`, `string`, `big_array`, `q4k`,
  `mem`) are `IDENTICAL-CODE` with identical counters.
* **Frame bytes did not move on any case.**

**The premise is refuted.** An instrumented scratch build (counters only, never
committed) shows the eviction branch of `afree()` is reached **5 times in the whole
benchmark suite** (2 in `file_io`, 3 in `params8`) and **462 times in the
compiler's own 427-function self-build** — against 144 484 allocations and 115 427
`sdef` stores. The pool is a 13-register pool that is **never full on the suite**:
`arith`'s `main` maps at most **3** registers at once and evicts **zero** times.
So victim selection cannot be the dominant cost of the 6-32x cases, and the written
plan's `work()` = 254-instructions-vs-gcc's-9 framing pointed at the wrong knob.

Where the loop instructions actually are (largest backward-branch region of `main`,
golden compiler, `objdump -d --no-show-raw-insn`):

| case | loop instr | home **loads** | home **stores** | arith/cmp |
|---|---:|---:|---:|---:|
| arith | 111 | 13 | **39** | 39 |
| div_const | 98 | 14 | **43** | 23 |
| heavy_int | 75 | 9 | **28** | 23 |
| fileio | 123 | 21 | **55** | 23 |
| float | 155 | 30 | **71** | 8 |

**The store side dominates.** The cost is that `sdef()` stores the home slot on
every definition and `flush_all()` stores every live value again at every block
boundary and every `IR_CALL`, while gcc's equivalent loops contain zero
frame-relative operands. That is the next lever and it is queued in
`docs/research/a4-next-use-eviction-measurements.md` §9 with the obstacle named.

## 3. Verification

| check | result |
|---|---|
| functional gate (`QC=./compiler/0.0.244/bin/x86/qc`) | **229/229 pass, 0 fail, 0 compile-fail**, exit 0 |
| STDLIB | **111/111 GREEN** |
| stages | **24/24 GREEN**, no RED |
| valgrind / fuzz / differential | GREEN / GREEN / GREEN |
| new gate row `regpressure_eviction_test.quanta` | compiles OK, **PASS rc=42** |
| self-hosting | shipped binary **rebuilds itself bit-for-bit** (`886e36f8` -> `886e36f8`) |
| seed chain from the 0.0.243 golden | `1c23a94c` -> `7bdf8d37` -> `886e36f8` -> `886e36f8` -> ... (byte-stable from generation 3; verified through generation 6) |
| determinism control | the same compiler run twice on the same source gives identical output |
| 0.0.243 golden untouched | md5 still `26430066a4e04f61a687ccf6291b61d7` |

Gate log: `/home/tali/.hermes/cache/scratch/a4/gate3.txt`. The runner was the
concurrently-peer-modified `test_suites/scripts/run_tests.sh`
(md5 `fb957cfedd6779217effca749e98bf54`) — that file is NOT owned by this unit and
was not touched.

**The "one binary, two generations" note.** The seed chain reaches its fixed point
from generation **3** here, where `scripts/verify-release.sh`'s check 6 walks only
3 generations and `docs/RELEASE_CHECKLIST.md`'s convention is "the fixpoint is the
SECOND generation". This is **not** an A4 effect: for `benchmark_mem` the object
files emitted by generation 1 and generation 3 are **byte-identical**
(`md5 2c8f8e2c4788a25b0b19a7cb53c6ad10`, and likewise for `arith` and `heavy_int`),
while their *executables* differ in exactly **two bytes** — a program-header size
field at offset 208 (0x2f0 vs 0x170) — plus 384 bytes of trailing padding. Both run
and print identically. So exec-mode ELF emission carries a size that feeds back from
the emitting compiler, and a lever that changes the compiler's own codegen shifts it
by one extra generation.

## 4. What is NOT here

* **No home-slot reuse, and no frame change.** `frame_size = spill_region +
  total_str + 80` with `spill_region = 48 + vreg_n*8` (`codegen.quanta:1374-1385`),
  but `min_spill = 1024` clamps it: `arith`'s 1120 bytes is the floor + alignment,
  and its `vreg_n` reserves 124 slots for at most 12 live values. Reusing home slots
  would not move the frame for these cases, and the ~8 000-vs-~262 000 recursion
  depth is set by `min_spill`, not by the one-slot-per-vreg layout. Left alone: it
  is a different lever, and `min_spill` has a documented SIGSEGV history
  (`codegen.quanta:1376-1383`).
* **No wall-time claim.** 36 byte-identical rows swung -12.5 % to +20.0 % in the
  A/B; `heavy_div2` measured 32.85x vs gcc at load 17-20 and 21.68x at load 12 on
  the same binary. Any wall-clock claim here would be unfalsifiable.
* **Nothing in `docs/plans/bugs.md`, `lib/std/**`, `compiler/0.0.242/**` or
  `compiler/0.0.243/**`.** The premise correction belongs in `docs/plans/performance.md`
  §3 and `docs/plans/next-queue.md` item 2, which are NOT owned by this unit; it is
  recorded in `benchmarks/BENCHMARK.md`, `docs/research/a4-next-use-eviction-measurements.md`
  and here for the owner to promote.

## 5. Red-first

There is **no functional red-first row for A4, and there cannot be one**: the
change is semantics-preserving by construction, so no program's *result* differs
between 0.0.243 and 0.0.244. Stating the red-first evidence honestly:

* the **codegen** red-first is measured, not asserted —
  `benchmarks/benchmark_regpressure.quanta` emits a 401-instruction loop under
  0.0.243 and a 381-instruction loop under 0.0.244, and
  `test_suites/codes/regpressure_eviction_test.quanta` goes 939 -> 899 instructions
  and 522 -> 482 home memory ops;
* `test_suites/codes/regpressure_eviction_test.quanta` + its `EXPECTED.tsv` row is a
  **coverage** row (it passes under 0.0.243 too — verified), and it is labelled as
  such in its own header. It pins the failure a wrong eviction policy *would* cause:
  16 live values against a 13-register pool, definition order opposed to
  consumption order, hand-derived expected values (`80012800000`, `333493367200000`).
  New row count: **EXPECTED.tsv 228 -> 229**.
