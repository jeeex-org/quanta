# Quanta 0.0.103 — Release State

- **Version:** 0.0.103
- **Date:** 2026-08-27
- **Source entry:** `compiler/0.0.103/src/x86/main.quanta` (16 modules)
- **Build seed:** 0.0.102 (`compiler/0.0.102/bin/x86/qc`)
- **Compiler binary:** `compiler/0.0.103/bin/x86/qc`
- **Self-host fixpoint:** byte-identical `qc_self == qc`, md5 `1458d4683ff3bc5097fb0e2ab0de43e1` (3-stage boot→self→qc verified 2026-08-27).

## What landed in 0.0.103

GATE-ONLY release. No compiler source changes from 0.0.102 — this version exists so the
ROADMAP ✅ for "float math (sin/cos/tan/pow/log/min/max)" maps to a real, verifiable
release folder (per the rule: every version gets its own folder copied from the previous
stable, regardless of source changes).

The float builtins (`sin/cos/tan/pow/log/min/max/sqrt/floor/ceil/abs`) were already
implemented in `emit_bltn` (P6.1a) and are exercised by the core float_arith test
(`float_test.quanta`, `simple_fadd.quanta`, etc.) in the gate. `std_math_test.quanta`
remains at the stdlib stage (EXPECTED_STDLIB.tsv), not in the core gate.

## Gate status (verified, all GREEN)
- functional: 136/136 core (EXPECTED.tsv; std_* kept separate in EXPECTED_STDLIB.tsv at stdlib stage)
- extern-c: GREEN · security 8/8 GREEN · perf 3/3 GREEN
- valgrind: clean (0 errors) · fuzz: fail-closed (0 crashes) · differential: consistent
- generics-negative: GREEN (both negative cases fail closed)

## ROADMAP / FEATURES sync
ROADMAP 0.0.103 → ✅ (real folder now exists; previously a doc-only ✅).
FEATURES §F/§G: float builtins ✅ shipped (core gated via float_arith; std_math_test deferred to stdlib).
