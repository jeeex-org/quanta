# Quanta 0.0.108 — Release State

- **Version:** 0.0.108
- **Date:** 2026-08-27
- **Source entry:** `compiler/0.0.108/src/x86/main.quanta` (16 modules)
- **Build seed:** 0.0.107 (`compiler/0.0.107/bin/x86/qc`)
- **Self-host fixpoint:** stage2 == stage3, md5 `d89cd1e7c44899a01f054f2caec7c4ea` (byte-identical)
- **Promoted from:** 0.0.108 (this version; copied from 0.0.107)

## What changed
Built-ins: CPU intrinsics (hints + memory fences). Added 5 void builtins:
- `prefetch(addr)` — `prefetchnta [rax]` (0F 18 08); addr loaded from its spill-home (register-allocation-independent, same pattern as `bitfield`/`stat`).
- `pause()` — spin-wait hint (`F3 90`).
- `fence()` — full memory fence `mfence` (`0F AE F0`).
- `lfence()` — `lfence` (`0F AE E8`).
- `sfence()` — `sfence` (`0F AE F8`).

Branch-hint intrinsics (`likely`/`unlikely`) were scoped OUT: conditional jumps are
emitted centrally in the shared `IR_BR` backend, not at call sites, so a builtin cannot
prefix a following conditional branch. `prefetch`/`pause`/`fence`/`lfence`/`sfence` need
no such wiring and are real, verifiable instructions.

## Fixpoint / lineage note
0.0.108 = 0.0.107 (bit/byte extras) + intrinsics. It also carries the fs-metadata fix
(bitops_test, fs_meta_test, intrinsic_test all gate). 0.0.109 was rebuilt from this
version so the SEQUENCE stays intact (each version is a copy of the previous).

## Tests
- `intrinsic_test.quanta` (rc=0): prefetch/pause/lfence/sfence/fence emit correctly and
  the program runs without faulting; verifies prefetch does not corrupt a later mem_load.
- `bitops_test.quanta` (rc=0) carried over from 0.0.107.
- `fs_meta_test.quanta` (rc=11) carried over.
- Full gate: 142/142 functional + extern-c/security/performance/valgrind/fuzz/
  differential/generics-negative all GREEN.

## Gate result
- functional : GREEN (142/142)
- extern-c   : GREEN
- security   : GREEN (fail-closed)
- performance: GREEN
- valgrind   : GREEN
- fuzz       : GREEN
- differential: GREEN
- generics    : GREEN
- self-host   : byte-identical (stage2 == stage3, md5 d89cd1e7c44899a01f054f2caec7c4ea)
