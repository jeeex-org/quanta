# Quanta 0.0.102 — Release State

- **Version:** 0.0.102
- **Date:** 2026-08-27
- **Source entry:** `compiler/0.0.102/src/x86/main.quanta` (16 modules)
- **Build seed:** 0.0.101 (`compiler/0.0.101/bin/x86/qc`)
- **Compiler binary:** `compiler/0.0.102/bin/x86/qc`
- **Self-host fixpoint:** byte-identical `qc_self == qc`, md5 `1458d4683ff3bc5097fb0e2ab0de43e1` (3-stage boot→self→qc verified 2026-08-27).

## What landed in 0.0.102

Language/compiler source changes (all in `compiler/0.0.102/src/x86/`):
- `features.quanta` `is_bltn`: registered 3 new builtins — `substr` (nl==6), `strcat` (nl==6), `rand` (nl==4).
- `emitter.quanta` `emit_bltn`:
  - `substr(s, start, len)`: allocate `len+9` bytes via mmap, copy `len` bytes from `s+8+start`, set header=`len`, NUL-terminate.
  - `strcat(a, b)`: string concat (same heap-alloc pattern as the `str` builtin).
  - `rand()`: mmap 8 bytes, `getrandom(buf, 8, 0)` (sc 318), return the 8-byte i64.
  - `is_float_vr`: added a fast-path that consults the `vfloat` table (`if r8(vfloat+vr)==1 return 1`) — this is the legit mechanism; `i2f`/`fconst` populate `vfloat` via `w8(...)`. (The `fadd`/`fsub`/`fmul`/`fdiv` ops return *truncated integers* by design — they end with `cvttsd2si`, so they do NOT tag `vfloat`.)
- Float arithmetic builtins (`i2f, f2i, fadd, fsub, fmul, fdiv, fconst, sin/cos/tan/pow/log/min/max/sqrt/floor/ceil/abs`) were already implemented (emit_bltn P6.1a); 0.0.102 adds gated coverage for them.

## Semantics note (critical — do not "fix" without intent)
`fadd`/`fsub`/`fmul`/`fdiv` perform float math internally but **return the truncated integer**. So `exit(fadd(i2f(2), i2f(3)))` = 5, and `exit(fmul(fadd(i2f(2), i2f(3)), i2f(4)))` = 20. Only `i2f`/`fconst` produce float bit-patterns; `f2i` round-trips them. Chained float math loses fractional precision at each op boundary — this is BY DESIGN (documented in ROADMAP 0.0.102 + FEATURES §F).

## Gate status (verified, all GREEN)
- functional: 136/136 core (EXPECTED.tsv; std_* kept separate in EXPECTED_STDLIB.tsv at stdlib stage)
- extern-c: GREEN · security 8/8 GREEN · perf 3/3 GREEN
- valgrind: clean (0 errors) · fuzz: fail-closed (0 crashes) · differential: consistent
- generics-negative: GREEN (both negative cases fail closed)

## Deferred (NOT claimed done)
- `str_split` / `utf8` / `strcmp`: need a string-array runtime; tracked in 0.0.104.
- Per-type generics body specialization (monomorphisation): tracked from 0.0.101.
- stdlib-module tests (big/quantum/linalg, std_math_test): stdlib stage, not a released core feature.

## ROADMAP / FEATURES sync
ROADMAP 0.0.102 → ✅. 0.0.103 (float math sin/cos/...) marked ✅ already-landed. 0.0.104 string ops → 🟡 partial. FEATURES §F/§G updated: `rand`, `substr`/`strcat` ✅ gated; `sin/cos/tan/pow/log/min/max` ✅ shipped.
