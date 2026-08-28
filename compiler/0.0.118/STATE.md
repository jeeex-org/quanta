# Quanta 0.0.116 — Release State

- **Version:** 0.0.116
- **Date:** 2026-08-28
- **Source entry:** `compiler/0.0.116/src/x86/main.quanta` (16 modules)
- **Build seed:** 0.0.115 (`compiler/0.0.115/bin/x86/qc`)
- **Self-host fixpoint:** BYTE-VERIFIED — md5 `662de43a69d848581774e81f01703456`.
  The promoted binary compiles its own source to a byte-identical binary
  (verified stage1==stage2==stage3).
- **Promoted from:** 0.0.116 (this version; copied from 0.0.115)

## Audit close-off #2 (0.0.116)

0.0.116 is the **AUDIT_ROADMAP round-2 close-off** for the gate-hygiene and
correctness findings (FIX-0.0.31–35), plus six additional implementation bugs
the new gate tests exposed (FIX-0.0.40–45). See `docs/AUDIT_ROADMAP.md`.

### Compiler fixes
- **FIX-0.0.31 (HIGH):** `rsp()` emitted `mov rsp,rsp` (ModR/M 0xE4, a no-op)
  instead of `mov rax,rsp` (0xE0). Any `rsp() <op> local` miscompiled to
  `local <op> local`. Fixed the ModR/M byte (eb(228)→eb(224)).
- **FIX-0.0.40 (HIGH):** hex literals ≥ 0x8000000000000000 were rejected as
  i64 overflow. Now span the full 64-bit two's-complement range (like C),
  built from two 32-bit halves via `(hi<<32)+lo` to avoid the G2 overflow trap.
- **FIX-0.0.45 (HIGH):** `sin`/`cos`/`tan` reloaded arg0 from the wrong vreg
  (`irres(ira2(ii))`) → always returned 0. Now use rdi directly (the codegen
  already loads arg0 into rdi), matching the proven `sqrt` pattern. Verified
  bit-exact against libm.

### Stdlib fixes (exposed by the new gate tests)
- **FIX-0.0.41 (HIGH):** quantum Keccak rho+pi table had wrong lane
  assignments + invalid rotation offsets → all SHA3/SHAKE digests wrong.
  Rewritten with the official KeccakRhoOffsets.
- **FIX-0.0.42 (HIGH):** quantum sponge absorbed a phantom zero block for
  short messages and wrote only the first 8 output bytes. Rewritten; verified
  against OpenSSL (`openssl dgst -sha3-*`).
- **FIX-0.0.43 (MED):** linalg `mat_from_flat` read the input array at +16;
  Quanta array literals have an 8-byte header (elements at +8). Fixed to +8.
- **FIX-0.0.44 (MED):** linalg `mat_det` used truncated integer division in
  Gaussian elimination (invalid). Rewritten with Bareiss fraction-free
  elimination (exact integer arithmetic).

### New gate coverage
- **FIX-0.0.32:** `quantum_test.quanta` — 5 NIST/OpenSSL-verified SHA3/SHAKE
  vectors (rc=0).
- **FIX-0.0.33:** `linalg_test.quanta` — mat_mul/transpose/add/sub/scal/det/
  identity vs hand-computed values (rc=0).
- **FIX-0.0.34:** `trig_test.quanta` — sin/cos/tan of 0,1,2 vs libm
  bit-patterns, 8-ULP tolerance (rc=0).
- **FIX-0.0.35:** MULTI-TU gate layer — `test_suites/scripts/multi_tu_tests.sh`
  compiles the `mtu_*` fixtures as separate TUs (`--emit-obj`, `--no-start`),
  links via `gcc -nostartfiles`, runs both pairs (rc=49, rc=25). Wired into
  run_tests.sh + gate summary + promotion gate.

## Tests
- EXPECTED.tsv: 151 rows (was 148; + quantum_test, linalg_test, trig_test).
- Full gate: **151/151 functional** + extern-c, security, perf 3/3,
  valgrind-clean, fuzz fail-closed 0 crashes, differential -O==no-O + vs-seed,
  generics-negative, stdlib 7/7, **multi-tu 3/3** — all GREEN (10 layers).

## Gate result
- functional  : GREEN (151/151)
- extern-c    : GREEN
- security    : GREEN (fail-closed; overflow traps fire as designed)
- performance : GREEN (3/3, baseline 4000ms)
- valgrind    : GREEN (0 errors)
- fuzz        : GREEN (fail-closed on all fuzzed inputs)
- differential: GREEN (optimizer differential + vs-seed consistent)
- generics    : GREEN (negative compile-time checks)
- stdlib      : GREEN (7/7)
- multi-tu    : GREEN (3/3)
- self-host   : BYTE-VERIFIED (md5 662de43a69d848581774e81f01703456)
