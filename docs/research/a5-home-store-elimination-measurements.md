# A5 / home-store elimination (write-back on demand) — measurements and the policy decision

**Date:** 2026-10-16 · **HEAD at start:** `df0a69d5` · **Baseline:** `compiler/0.0.244/bin/x86/qc`
(md5 `886e36f8318aaae414e188e947d11c49`) · **Lever tree:** `compiler/0.0.245/`

This implements the lever queued in `a4-next-use-eviction-measurements.md` §9:
home-slot STORE traffic (39-71 stores per hot-loop body against gcc's 0), written
by `sdef()` at every definition and by `flush_all()` at every block boundary and
`IR_CALL`. Everything below is measured; the command that produced each number is
named. Wall-time figures appear only in §6, labelled weak, with the environment.

> Environment for every run on this box: governor `powersave` (~2.2-2.8 of
> 5.4 GHz), `Hermes` holding 664-1300 % CPU, load average 7-13. Load-independent
> metrics (instruction/frame/home-op counts via `objdump -d`) are the evidence.

---

## 1. The policy decision: store-on-use, not a caller-save split

Two policies were named as candidates. **Store-on-use (write-back)** was chosen:

* A caller-save/callee-save split addresses ONLY the `IR_CALL` subset of the
  flushes. The measured loops (`arith`, `div_const`, `heavy_int`) contain no
  calls at all — their store traffic is per-definition `sdef` stores and
  block-boundary flushes, which a call convention cannot touch.
* Write-back removes both writers with one invariant, and the unmap paths
  (flush_all, flush_clob, afree/afree_x/adistinct/ascratch evictions) already
  stored the register to the home slot — the mechanism was 90 % present.

**The new invariant:** *a vreg's home slot holds its current value whenever the
vreg is not mapped, and whenever the vreg's address has escaped (`vr_at`).* A
mapped vreg's register holds its value; the store happens at unmap. `sdef(vr,
reg)` marks `vr_init` and stores **iff the vreg is unmapped or address-taken**
— the unmapped case is load-bearing for ops that `aphys(res)` early and lose
the mapping to a mid-op `flush_clob` (§4).

## 2. What changed (compiler/0.0.245, two files)

| change | where |
|---|---|
| `sdef` = mark + conditional store (unmapped or `vr_at`); `sdefr` = old store+mark for the never-mapped defines | `emitter.quanta` |
| `loadhome(reg, vr)`: register-first home-read replacement | `emitter.quanta` |
| `vr_at` per-vreg address-escaped flag, cleared in `aclr()` | `emitter.quanta` |
| `argp8` syscall string args -> `loadhome` | `emitter.quanta` |
| div/mod operand loads (`emit_cdiv_core` + 8 sites), SHL/SHR -> `loadhome` | `codegen.quanta` |
| `IR_PARAM` / `IR_CATCH` / `IR_CAPREAD` / `IR_CAPWRITE`-bvr -> `sdefr` | `codegen.quanta` |
| IR_IDX packed mid-path `sdef(res,0)` deleted (common tail binds res) | `codegen.quanta` |
| closure-capture `leabp(&slot)` and `&local`: force-store + `vr_at` mark | `codegen.quanta` |
| A4 safety comment updated (eviction store is now load-bearing) | `emitter.quanta` |

The direct-reader audit was scripted: every `sdef` site checked for a preceding
`aphys`/`adistinct`/`aset` in its handler (73 raw flags, all resolved); every
remaining `rbp(..., spill_home(...))` read checked for flush/aphys interaction
(6 flags, all false positives). Post-`flush_all` readers (IR_CALL args, array
ops, builtins) are unchanged — the flush's stores are kept and are now the
write-back mechanism.

## 3. Re-baselined before/after (scripts/bench_instr.sh, fn=main)

Extended this version to report home STORES and LOADS separately, function-wide
and inside the hot loop (the largest backward-branch region). Baseline run and
after-run each one pass over all 38 cases; the TSVs are compared by script.

| case | loop instr 244->245 | loop home STORES | loop home LOADS | frame |
|---|---|---|---|---|
| arith | 111 -> 98 (−11.7 %) | **40 -> 27 (−32.5 %)** | 13 -> 13 | 1120 == 1120 |
| div_const | 98 -> 84 (−14.3 %) | **44 -> 30 (−31.8 %)** | 14 -> 14 | 1120 == 1120 |
| heavy_int | 75 -> 65 (−13.3 %) | **29 -> 19 (−34.5 %)** | 9 -> 9 | 1136 == 1136 |
| fileio | 123 -> 101 (−17.9 %) | **56 -> 34 (−39.3 %)** | 21 -> 21 | 1184 == 1184 |
| float | 155 -> 127 (−18.1 %) | **72 -> 44 (−38.9 %)** | 30 -> 30 | 1120 == 1120 |
| match | 174 -> 148 (−14.9 %) | **60 -> 34 (−43.3 %)** | 15 -> 15 | 1168 == 1168 |
| params8 | 104 -> 81 (−22.1 %) | **52 -> 29 (−44.2 %)** | 15 -> 15 | 1120 == 1120 |
| regpressure | 381 -> 310 (−18.6 %) | **173 -> 102 (−41.0 %)** | 33 -> 33 | 1136 == 1136 |

* **Every one of the 38 cases improved or held on every column; not one metric
  increased anywhere.**
* Function-wide home stores summed over the suite: **3395 -> 1963 (−42.2 %)**.
* Home LOADS unchanged by design. The remaining loop stores are the
  block-boundary flush of live AND dead mapped vregs — cross-block liveness is
  the next lever, not this one.
* Frames did not move (min_spill floor, as A4 recorded).
* gcc: 0 home stores/loads on every row.

## 4. The gate caught two defects in the first build — both are the lever's own audit paying off

1. **`divmod_floor_semantics_test` rc=101.** The div/mod paths `aphys(res)`
   before `flush_clob`, which unmaps res; the final `sdef(res, rd)` (then a
   pure mark) no longer stored, so the home kept the pre-correction quotient
   and every later reload read the TRUNCATED quotient (`7 / -2` -> -3, floor is
   -4). The fix is the precise invariant of §1 (store iff unmapped or
   address-taken), not a per-path patch. **This existing gate row is the
   red-first for the failure mode; no new row is needed or added.**
2. **Self-host gen2 SIGSEGV (`big_add_sign\x01\x00`).** gen1 compiled the 38
   benchmarks byte-identically but miscompiled the compiler's own source (same
   unmapped-sdef shape under pool pressure); the fixed point then looked up
   names past their terminator. The same fix removed it.

## 5. Verification (all commands run on this box)

| check | result |
|---|---|
| benchmark outputs, 38 cases, stdout+exit via `scripts/quanta_run.sh` | **byte-identical** 0.0.244 vs 0.0.245 |
| functional gate (`ulimit -c 0 -v 8000000; QC=.../0.0.245/bin/x86/qc bash test_suites/scripts/run_tests.sh`) | **229/229, 0 fail, 0 compile-fail, exit 0** |
| STDLIB | **112/112** (one peer row since the 111 baseline) |
| stages | **24/24 GREEN** |
| self-host | gen1 `534cb58b` -> gen2/3/4 `cbdd5c6f` (fixpoint, byte-stable ×3) |
| `verify-release.sh 0.0.245 0.0.244` (pre-promotion) | **14 passed / 0 failed** |
| 0.0.244 golden | md5 unchanged `886e36f8...` |

(A first gate run with `ulimit -v 6000000` — the figure in
`docs/plans/performance.md` §5 — produced 229 spurious compile-fails: 6.0 GB is
BELOW the compiler's ~6.2 GB address-space floor. Re-run at 8 GB per the
campaign protocol: all green. The §5 figure should be corrected by the docs
owner.)

## 6. Wall time — recorded, and weak (as A4 concluded)

`bash scripts/bench.sh --runs 3 --md` with `QC=.../0.0.245/bin/x86/qc`, interleaved
min-of-3, load 7-13, `Hermes` 664-1300 % CPU: the ratios move in the right
direction on the store-heavy rows but stay inside the noise band A4 measured for
BYTE-IDENTICAL binaries (−12.5 % to +20.0 %). **No wall-time claim is made**; the
instruction/store counts in §3 are the result. (Table in
`compiler/0.0.245/WIP.md` §2 if a later re-run wants a comparison point.)

## 7. Queued handoff (not this lever)

* **Cross-block liveness for flush_all** — the remaining loop stores (18-44 per
  body) are the boundary flush storing live AND dead mapped vregs; pruning dead
  ones needs next-use information ACROSS the back-edge, which A4's
  block-bounded window deliberately does not have.
* **Home-LOAD traffic** (7-33 per loop) — the reload-after-boundary cost; it
  falls out of the same liveness work (values kept mapped across a back-edge
  are never reloaded).
* **`min_spill = 1024`** — unchanged, different lever (recursion depth), has a
  documented SIGSEGV history.
