## 9. Version History

| Version | Date | What |
|---------|------|------|
| **0.0.6** | **2026-07-30** | **Bare Some/None/Ok/Err support (expressions + match patterns). x86_64 self-host verified (stage2==stage3), 39/39 x86_64 tests pass. ARM64 cross-compile works but ARM64 bare-variant pattern match broken (exit 0) — BLOCKS ARM64 promotion.** |
| **0.0.5** | **2026-07-30** | **Bare Some/None/Ok/Err support (expressions + match patterns). x86_64 self-host verified (stage2==stage3), 39/39 x86_64 tests pass. ARM64 cross-compile works but ARM64 bare-variant pattern match broken (exit 0) — BLOCKS ARM64 promotion.** |
| **0.0.4** | **2026-07-30** | **Enum support + self-host verified. Enum declarations, constructors, match expressions working. 37/39 tests pass (trait, generics not implemented; option/result match on built-ins incomplete).** |
| **0.0.2** | **2026-07-29** | **WIP. option_test + result_test fixed (bare Some/None/Ok/Err). struct_test regression + enum_test match capture + file_open_test string-header all fixed. 38/39 compile, 38/38 runtime pass. 2 remaining: trait, generics.** |
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
| 1.1.34-wip | current | P6 enum/match/generics/type-system tokens |

---