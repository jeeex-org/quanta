# 0.0.245 — WIP · **LEVER: home-store elimination / write-back on demand (the A4 §9 handoff)**

```
0.0.244 golden  md5 886e36f8318aaae414e188e947d11c49   (frozen baseline, untouched)
0.0.245 gen1    md5 534cb58b291e56362cc02037ea68c5fd   (0.0.244 golden compiling the edited source)
0.0.245 fixed   md5 cbdd5c6f02fb763a46e173fc1efe68e6   (the seed-chain FIXED POINT = shipped bin/x86/qc)
```

Two files changed: `src/x86/emitter.quanta` (sdef/sdefr split, loadhome, vr_at,
argp8, updated A4 safety comment) and `src/x86/codegen.quanta` (direct home
readers -> loadhome, sdefr at unmapped define sites, vr_at marking at closure
capture and `&local`). Everything else is the 0.0.244 snapshot copied verbatim;
imports resolve to the REPO `lib/std`, which is what the build and the gate use.

**Read `docs/research/a4-next-use-eviction-measurements.md` §5/§9 first** — that
is the measurement this lever implements, and §9 names the obstacle this design
had to clear.

---

## 1. The lever

The A4 measurement (0.0.244) established, by instruction counts, that home-slot
STORE traffic — 40 / 44 / 29 / 56 / 72 stores per hot-loop body (`arith` /
`div_const` / `heavy_int` / `fileio` / `float`, re-measured with the extended
`scripts/bench_instr.sh`) against gcc's ZERO — is the real Quanta-vs-C gap. Two
writers: `sdef()` stored the home slot at EVERY definition, and `flush_all()`
re-stored every live vreg at every block boundary and every `IR_CALL`. The pool
barely fills (A4 §4), so those stores are almost never read.

**Policy chosen: store-on-use (write-back), not a caller-save/callee-save split.**

* A caller-save split only addresses the `IR_CALL` subset of the flushes; the
  per-definition `sdef` stores — the dominant term in the measured loops, which
  contain no calls at all — would remain. Write-back removes both with one
  invariant.
* The new invariant is weaker but sufficient: **a vreg's home slot holds its
  current value whenever the vreg is NOT mapped.** Every path that un-maps a
  vreg already stored the register to the slot (flush_all, flush_clob, and the
  eviction branches of afree/afree_x/adistinct/ascratch) — those stores are kept
  and become the *only* home writes for mapped vregs. `sdef` becomes a pure
  mark (`vr_init=1`).

### The obstacle, and how it was cleared

§9 named the direct `spill_home()` readers in the SHL/SHR and `IR_CALL` paths.
The full audit found more: the division/modulo paths (`emit_cdiv_core` + 8
sites), `argp8` (syscall string args), and the emit_bltn fixed-register define
pattern `sdef(irres(ii), 0)` (≈20 builtin results bound to rax without aset —
the caller's `aphys(res)` reload at the IR_CALL tail depends on those home
writes). Resolution, per reader class:

| reader class | resolution |
|---|---|
| operand loads after `flush_clob` (div/mod/SHL/SHR) | new `loadhome(reg, vr)`: register-first (mapped -> `mov`), else load the (current) home |
| post-`flush_all` loads (IR_CALL args, IR_IDX/ISTORE, IR_FREE, closure fnb, IR_UNWRAP/TRY, emit_bltn arg marshalling) | unchanged — flush stores everything it unmaps, so homes are current |
| res-home hops inside the idiv sequences | unchanged — each read is preceded by an explicit `wbp(spill_home(res), ...)` |
| emit_bltn `sdef(irres(ii), 0)` defines | new `sdefr()` (store + mark) — the vreg is never mapped, so the home write is the binding |
| IR_PARAM / IR_CATCH / IR_CAPREAD / IR_CAPWRITE-bvr | `sdefr()` (same reason) |
| IR_IDX packed-field mid-path `sdef(res, 0)` | deleted — the common tail `aphys(res)+rr+sdef` binds res, and a mid-path vr_init would make that aphys reload an unwritten home |
| `argp8` (string pointer for syscalls) | `loadhome` |
| closure-capture `leabp(&slot)` | slot address escapes: force-store the current value, and mark the vreg `vr_at` so its LATER sdefs keep storing |
| `&local` (IR_PTR_CAST a2==1; that handler has NO flush) | same force-store + `vr_at` |

The audit is scripted, not eyeballed: every `sdef` site checked for a preceding
aphys/adistinct/aset in its enclosing handler (73 raw flags, all resolved to
mapped-context or converted to sdefr); every remaining
`rbp(..., spill_home(...))` read checked for flush/aphys interaction (6 flags,
all false positives: aphys's own reload reads only when unmapped; the idiv
res-reads follow an explicit `wbp`; UNWRAP/TRY re-read after a flush where home
== register by construction).

## 2. The measured result

`scripts/bench_instr.sh` (extended this version with home-store/home-load
columns, function-wide and hot-loop), all 38 cases, both compilers, one run
each, load 9.4 / 7.4, governor `powersave`, `Hermes` at 664-846 % CPU. This
metric does not move with load.

**Headline (0.0.244 -> 0.0.245):**

| case | loop instr | loop home STORES | loop home LOADS | frame |
|---|---|---|---|---|
| arith | 111 -> 98 (−11.7 %) | **40 -> 27 (−32.5 %)** | 13 -> 13 | 1120 == 1120 |
| div_const | 98 -> 84 (−14.3 %) | **44 -> 30 (−31.8 %)** | 14 -> 14 | 1120 == 1120 |
| heavy_int | 75 -> 65 (−13.3 %) | **29 -> 19 (−34.5 %)** | 9 -> 9 | 1136 == 1136 |
| fileio | 123 -> 101 (−17.9 %) | **56 -> 34 (−39.3 %)** | 21 -> 21 | 1184 == 1184 |
| float | 155 -> 127 (−18.1 %) | **72 -> 44 (−38.9 %)** | 30 -> 30 | 1120 == 1120 |
| regpressure | 381 -> 310 (−18.6 %) | **173 -> 102 (−41.0 %)** | 33 -> 33 | 1136 == 1136 |
| match | 174 -> 148 (−14.9 %) | 60 -> 34 (−43.3 %) | 15 -> 15 | 1168 == 1168 |
| params8 | 104 -> 81 (−22.1 %) | 52 -> 29 (−44.2 %) | 15 -> 15 | 1120 == 1120 |

* **Every one of the 38 cases improved or held on every column; not one metric
  increased anywhere** (scripted check over the two TSVs).
* Function-wide home stores across the suite: **3395 -> 1963 (−42.2 %)**.
* Home LOADS are unchanged by design (write-back does not touch reload
  traffic; the block-boundary reload cost is the queued next lever).
* Frames did not move on any case (min_spill floor, as A4 recorded).
* gcc's `c_st`/`c_ld` are 0 on every row (1 stray stack-arg load on three
  cases) — the store side of the measured gap is now 18-44 per hot loop
  instead of 29-72, all of it block-boundary flush traffic of live-and-dead
  mapped vregs (cross-block liveness is the follow-on lever, not this one).

**The 12 parity cases** (`nested_calls`, `recursion`, `float_ops`, `match`,
`mem_ops`, `file_io`, `fib`, `q4k_matmul`, `string`, `big_array`, `q4k`,
`mem`): every one improved or held (e.g. match 174->148 loop instr,
q4k_matmul 67->55), none regressed — the hard requirement holds. All 38
benchmark binaries produce **byte-identical stdout and exit codes** under
0.0.244 and 0.0.245 (scripted comparison through `scripts/quanta_run.sh`).

### The two defects the gate caught in this lever's own first build

1. **`divmod_floor_semantics_test` rc=101 (WRONG VALUES).** The div/mod paths
   call `aphys(res)` BEFORE `flush_clob`, which then evicts res (unmaps it) —
   and the final `sdef(res, rd)` no longer stored, because sdef had become a
   pure mark. The home slot kept the PRE-correction quotient `q_t`, so every
   later reload read the truncated quotient: `7 / -2` printed -3 instead of
   -4. Fix: **sdef stores iff the vreg is unmapped (home is the only copy) or
   address-taken (`vr_at`)** — a mapped vreg's register holds the value and
   its unmap store is the write-back. This is the precise invariant, not a
   patch over one path.
2. **Self-host gen2 SIGSEGV + `big_add_sign\x01\x00` (COMPILER MISCOMPILED
   ITSELF).** gen1 compiled the benchmarks correctly but miscompiled the
   compiler's own source (same unmapped-sdef shape under pool pressure), so
   the fixed-point binary looked up function names past their terminator and
   crashed. The same sdef fix eliminated it; gen2==gen3==gen4 now.

## 3. Verification

| check | result |
|---|---|
| functional gate (`QC=./compiler/0.0.245/bin/x86/qc`, ulimit -v 8000000) | **229/229 pass, 0 fail, 0 compile-fail**, exit 0 |
| STDLIB | **112/112 GREEN** (was 111; one peer row landed since the baseline — not a regression) |
| stages | **24/24 GREEN**, no RED |
| benchmark outputs (38 cases, quanta_run.sh, stdout+rc) | **byte-identical** to 0.0.244 on every case |
| self-hosting | gen1 `534cb58b` -> gen2 `cbdd5c6f` -> gen3 `cbdd5c6f` -> gen4 `cbdd5c6f` (fixpoint from gen2, byte-stable through gen4; 2 distinct binaries) |
| verify-release.sh (pre-promotion, VERSION=0.0.244) | **14 passed / 0 failed**, incl. baseline bit-for-bit rebuild and seed-chain fixed-point identity |
| 0.0.244 golden untouched | md5 still `886e36f8318aaae414e188e947d11c49` |
| new gate rows | **none** — no red-first row is possible (semantics-preserving), and the defect this lever's first build had is already pinned by the existing `divmod_floor_semantics_test` row, which is exactly what caught it. `EXPECTED.tsv` row count unchanged: **229 rows**; `EXPECTED_STDLIB.tsv` grew by one peer row (111 -> 112), not this unit's. |

## 4. What is NOT here

* No change to `flush_all`'s stores at block boundaries / IR_CALL (they are the
  write-back mechanism now — removing them needs cross-block liveness, a
  different lever).
* No change to the frame layout, `min_spill`, or the eviction policy (A4 keeps
  working on top: its evictions store, which is now the load-bearing store).
* No wall-time claim beyond what §2 labels.

## 5. Red-first

There is **no functional red-first row for this lever, and there cannot be one**:
the change is semantics-preserving by construction (it moves stores, it does not
change any computed value), so no program's *result* differs between 0.0.244 and
0.0.245. Stating the red-first evidence honestly:

* the **codegen** red-first is measured, not asserted — the loop-body home-store
  counts in §2 (before/after table) and instruction deltas;
* any new `EXPECTED.tsv` row added for this version is a **coverage** row (it
  must also pass under 0.0.244 — verified before landing), labelled as such,
  rows and sources in ONE commit.
