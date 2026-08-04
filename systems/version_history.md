## 9. Version History

| Version | Date | What |
|---------|------|------|
| **0.0.14-wip** | **2026-08-04** | **P10 for-in loop (CURRENT WIP). For-in (`for x in arr`), `arr[-1]` array-length, nested for-in fixed. gsz BSS bootstrap fix committed (7421bbb). 39/39 tests (generics = P10 monomorphization, next). Cross-compiles to ARM64 (see ARM parity note in §10).** |
| **0.0.13** | **2026-08-02** | **P9 traits/impl/vtable dispatch/struct literals STABLE. trait_test passes, self-host fixed-point, ARM device verified (300f977).** |
| **0.0.12** | **2026-08-01** | **P8 structs: declaration, constructor, field access (66b7dd2).** |
| **0.0.11** | **2026-08-01** | **P7 Option/Result/Enum match fully working x86_64 + ARM64; both backends 38/38; ARM64 device-verified; self-host fixed-point (7d1ad36).** |
| **0.0.10** | **2026-07-31** | **Batch 2 P6: FFI calls + SIMD + inline asm + unsafe blocks; both backends 38/38 (91d7053).** |
| **0.0.9** | **2026-07-31** | **Batch 1 P6: pointer ops (deref, ptr arithmetic, null check, volatile) + mut type; both backends 38/38 (2499b9e).** |
| **0.0.8** | **2026-07-31** | **P6 type annotations + raw ptr/volatile/asm keywords; type-annotation bug fixed; both backends 38/38 (a7a824e).** |
| **0.0.7** | **2026-07-31** | **ARM64 self-host fixed, both backends 38/38 (255ef41).** |
| **0.0.6** | **2026-07-30** | **Bare Some/None/Ok/Err + enum/match (x86_64 self-host, 7a91423). ARM64 bare-variant bug BLOCKED promotion (fixed in 0.0.11).** |
| **0.0.5** | **2026-07-30** | **Bare Some/None/Ok/Err support (expressions + match patterns). x86_64 self-host verified, 39/39 x86_64 tests pass. ARM64 bare-variant pattern match broken (exit 0) — BLOCKED ARM64 promotion (fix landed in 0.0.11).** |
| **0.0.4** | **2026-07-30** | **Enum support + self-host verified. Enum declarations, constructors, match expressions. 37/39 (trait, generics not implemented).** |
| **0.0.3** | **2026-07-30** | **P6 low-level features: raw pointers, volatile, inline asm, FFI, SIMD128, unsafe (dc307b6).** |
| **0.0.2** | **2026-07-29** | **WIP. option_test + result_test fixed. 38/39 compile, 38/38 runtime. 2 remaining: trait, generics.** |
| **0.0.1** | **2026-07-29** | **Initial self-host baseline: ARM64 3-char fn-name bug fixed; host intrinsics mem_load/mem_store added.** |
| — legacy 1.x — | — | — |
| 1.1.0 | 2026-07-20 | Security review + F1/F2 fixes (STABLE) |
| 1.1.1 | 2026-07-20 | Unsigned builtins (udiv/umod/ult/...) |
| 1.1.2 | 2026-07-20 | G1: `unsafe {}` block |
| 1.1.3 | 2026-07-20 | G2 part 1: overflow trap (opt-in) |
| 1.1.4 | 2026-07-20 | G2 part 2: overflow trap ON by default |
| 1.1.5 | 2026-07-20 | G2 part 3: shift-count UB trap |
| 1.1.6 | 2026-07-20 | Parenthesized-expr parse fix |
| 1.1.7 | 2026-07-20 | G2 containers + subscript-assign + string stride |
| 1.1.8 | 2026-07-21 | P2 ownership: compiler-inserted free |
| 1.1.9 | 2026-07-22 | P3 FFI: `extern "C"` |
| 1.1.10–1.33 | — | ARM64 backend, P6 scaffolding, bug fixes |
| 1.1.34-wip | current (historic) | P6 enum/match/generics/type-system tokens (superseded by 0.0.x line) |

---