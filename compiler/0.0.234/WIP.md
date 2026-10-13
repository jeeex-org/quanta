# 0.0.234 — WIP

**Lever for this version: A1 — kill the compiler crash on a capturing closure plus a branch.**

## What landed

- `src/x86/codegen.quanta`: the two `fnptr()` cases inside `ci_func()` declared `let fi=a0`, which **shadowed
  the function's own `fi` parameter** for the rest of the body (block bindings are never popped — see
  `docs/research/let-scope-inventory.md`). The `IR_CAPREAD`/`IR_CAPWRITE` handlers then computed
  `cap_bodyvreg + (fi*CAP_MAX + a0)*8` with `fi` holding an operand value (measured: 140,483,158,344,240) and
  stored through a wild address. Both locals renamed to `ftgt`. Nothing else changed.
- `test_suites/codes/closure_capture_branch_test.quanta` + an `EXPECTED.tsv` row (exit 23): **red on 0.0.233**
  (rc=139), green here. Rule #16 satisfied — the row was proven failing before the fix.
- `docs/RELEASE_CHECKLIST.md`: §5 gate cap `-v 6000000` → `-v 8000000` (measured: the compiler fails at
  6200000 KB and succeeds at 6300000 KB — **the old cap had already crossed the threshold and made every
  compile layer fail silently** (`rc=1`, empty stderr, no binary), identically for the 0.0.233 golden, so this
  was not a change regression). §4 smoke now converts explicitly (`exit(f2i(p))`) — as written it asserted
  nothing, because `exit(p)` with `p: f64` silently exits 0. Row-count note corrected 143 → 820.
- `docs/plans/bugs.md`: A1 root-caused, fixed, verified; new **A1b** (block bindings are never popped — a
  language-semantics decision, inventory in `docs/research/let-scope-inventory.md`); A2 extended with the
  `exit(f64)` finding.

## Verification (all measured at 0.0.234)

| check | result |
|---|---|
| fixpoint, 3 generations | `md5 4d08aaac7e3e27f199f6700fdc3fe7f0`, distinct md5 = **1** |
| §2 self-host consistency | **7/7** |
| §4 smoke (`exit(f2i(p))`) | rc **20** |
| §5 full gate | **820/820 functional, 0 fail, 0 skip, 0 compile-fail**; all 24 layers GREEN |
| §6 verify-release | **14 passed, 0 failed** |
| A1 probe matrix | 7 previously-crashing probes now compile and return correct values; control unchanged |
| A1 repro runtime | prints **8** (correct) |

## Not in this version

A2 (`print`/`exit` on `f64`), A1b (block scoping), A3–A7, and the Severity B accuracy tier. Per the standing
order: defects first, then `docs/plans/performance.md`, then `docs/plans/lfm2-native-inference-perf.md`.
