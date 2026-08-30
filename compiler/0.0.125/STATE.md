# Quanta 0.0.125 — Release State

- **Version:** 0.0.125
- **Date:** 2026-08-30
- **Source entry:** `compiler/0.0.125/src/x86/main.quanta` (16 modules)
- **Build seed:** 0.0.124 (`compiler/0.0.124/bin/x86/qc`)
- **Self-host fixpoint:** BYTE-VERIFIED — md5 `350e156a7e4d5615f9df4e3780151010`.
  gen1==gen2==gen3 byte-identical (qc_boot==qc_self==qc).
- **Promoted from:** 0.0.125 (copied from 0.0.124 per FOCUS rule; WIP edited, not the stable)

## 0.0.125 — `time` core completion

0.0.125 completes the `time` core: the syscall-backed time builtins
(`clock_gettime`, `gettimeofday`, `nanosleep`, `sleep`) shipped earlier
(0.0.116 era, gated by `time_test.quanta`), and this version adds the missing
zero-arg nanosecond wrappers:

- **`clock()`** — CLOCK_MONOTONIC time in nanoseconds (zero-arg). Internal
  mmap(16) timespec, `clock_gettime(1, buf)`, combine `sec*1_000_000_000 + nsec`,
  munmap, return in rax. Monotonic — safe for measuring elapsed time
  (deltas unaffected by wall-clock changes).
- **`now()`** — CLOCK_REALTIME epoch time in nanoseconds (zero-arg). Same
  shape, `clock_gettime(0, buf)`. Wall-clock — for timestamps/dates.

### Verification

- Emitted code verified byte-level: `imul rcx,rax,0x3B9ACA00` (ModRM C8 =
  reg=rcx, rm=rax), result staged in callee-saved r13 across the munmap
  syscall (r12 holds buf), reload via `ldx` (r12%8==4 → SIB escape hazard,
  plain `rmr` would emit garbage).
- `clock_now_test.quanta` gated (EXPECTED.tsv row): monotonic positive,
  epoch > 2020, both advance across `sleep(1)`, deltas ≥ 0.9e9 ns — 6/6 checks.
- Full gate on the 0.0.125 binary: functional 158/158, stdlib 7/7, multi-TU
  3/3, valgrind/fuzz/differential/security/perf GREEN, exit 0.
- First-build gen1 (0.0.124 seed) itself passed the full gate BEFORE any
  clock/now edit — the scaffold copy was clean (no unverified seed-compile
  drift); fixpoint md5 above is post-edit.

### Roadmap position

First core of the resumed 0.0.x core chain (post-2026-08-30 re-plan): 0.0.125
`time` → 0.0.126 `process` → 0.0.127 PTY → 0.0.128 `big` div-guard → … → 0.0.138
borrow-check → 0.1.0 STABLE. One feature per version, fixpoint-verified.
