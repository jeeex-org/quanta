## 1. Identity

Quanta is a self-hosting systems programming language: one source language that
compiles to every tier — bare-metal kernel, edge WASM, GPU kernel, cloud service.

| Property | Value |
|----------|-------|
| **Self-hosting** | Compiler in Quanta; fixed-point verified on x86-64 (self-host gen1→gen2 byte-identical; bootstrap-built vs self-hosted differ only at benign byte 303) |
| **Bootstrapping** | `bin/x86_64/qc-0.0.13` gsz-patched bootstrap (built from `src/qc-0.0.13.quanta`) |
| **Version** | `qc-0.0.14-wip` (P10: for-in loop done; generics next). Stable: `qc-0.0.13` (P9 traits). |
| **Optimizer** | Tier-1 IR passes (const fold, DCE, tail-call, loop strength), ON by default |
| **Memory model** | Ownership-by-default (compiler-inserted `free` at scope exit), no GC |
| **Secure by default** | Overflow/shift/bounds traps ON; `unsafe {}` marks opt-out regions |
| **Tests** | 39 exit-code–gated tests, deterministic, full regression on every change (plus untracked feature fixtures — see test_suite.md §8) |
| **Backends** | x86-64 (native ELF ET_EXEC) + ARM64 (static-PIE ET_DYN, cross-compile; on-device verified) |

---