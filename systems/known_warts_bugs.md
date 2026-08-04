## 10. Known Warts & Bugs

### 10.1 Resolved syntax tests (historical)

| Test | Symptom | Root cause | Status |
|------|---------|------------|--------|
| file_open_test | path `\37` instead of filename | String header pointer passed directly to syscall — fixed by `+ 8` offset | ✅ Fixed |
| enum_test | match result not returned | Captured match value with `let v = match ... return v` | ✅ Fixed (qc-0.0.4) |
| struct_test | struct constructor undefined | `parse_call_impl` lacked `findstruct` — added struct constructor IR | ✅ Fixed |
| option_test | `undeclared function: Some` | Recognized bare Some/None in parser | ✅ Fixed |
| result_test | `undeclared function: Ok/Err` | Recognized bare Ok/Err in parser | ✅ Fixed |
| ARM64 option_test | exit 0 instead of 42 | ARM64 bare variant pattern-match codegen bug | ✅ Fixed (qc-0.0.11/P7) |
| ARM64 result_test | exit 0 instead of 5 | ARM64 bare variant pattern-match codegen bug | ✅ Fixed (qc-0.0.11/P7) |
| trait_test | `undeclared variable: Drawable` | Full trait/impl system not implemented | ✅ Fixed (qc-0.0.13/P9) |
| struct_literal `Point { x: 3 }` | allocator-clobber in parse_primary | parse_primary must stay byte-identical; handled by token-level `rewrite_struct_literals()` | ✅ Fixed (qc-0.0.13/P9) |

### 10.2 OPEN issues

| Test / issue | Symptom | Root cause | Status |
|------|---------|------------|--------|
| generics_test | `error: undeclared variable: U` | `<T>` generic type-parameter syntax not implemented. Requires generic monomorphization. | 🔴 OPEN — P10 next pillar |
| `generics_test` | `error: undeclared variable: in` + "source too many tokens/IR limit" | generic fn signatures that reference for-in (`for item in arr`) — generics not wired | 🔴 OPEN — part of P10 |
| `let p: *u64 = &x` | "source too many tokens/IR limit" | Raw-pointer **type annotation** (`*T`) in a `let` explodes IR (type-annotation path for pointer types). `&x`/`*p` deref ops alone work. | 🔴 OPEN — P6.type-annotation gap |
| `let x: int = 42` | `undeclared variable: int` | `int` is not a recognized type keyword (only u8/u16/u32/u64/usize/bool/char/byte are). Use a bare literal (defaults to signed 64-bit). | 🔴 OPEN — advisory `-> int` only, no `int` keyword |
| **ARM64 for-in parity** | — | `IR_ARRAY_LEN` (op 69) ARM64 handler added to `arm_ci_func` (2026-08-04). All 5 for-in/arr[-1] tests pass on ARM64 under qemu-aarch64 (rc 42/10/66/3/3, matching x86). Native ARM64 compiler binary segfaults on-device (pre-existing, stable 0.0.12-0.0.13) — cross-compile is the supported ARM path. | ✅ CLOSED (for-in) |
| **ARM64 syscall numbers** | file I/O / stdout tests segfault under qemu-aarch64 | `sysc()` (line 3194) unconditionally emits x86-64 `int 0x80` (`eb(15);eb(5)`) — no `target_arch==1` branch for ARM64 `svc #0` with ARM syscall numbers (93=exit, 64=write, etc.). Affects file_io, file_open_test, prints_family, stdlib_test on ARM64 only. | 🔴 OPEN — separate ARM64 backend gap |

### 10.3 Known tooling traps (documentation of past debugging effort)

- **Fixed-point byte 303**: bootstrap-built vs self-hosted binary differ at byte 303 (ELF first-gen stamp, benign). Fixed-point of the wip's own self-host (`v2==v3`) is byte-identical.
- **BSS truncation diagnostic**: `readelf -l <bin> | grep -A1 RW` — correct = MemSiz page-rounded (0x2000); truncated = MemSiz==FileSiz (0x1038 → SIGBUS on globals). Root cause fixed in gsz bootstrap (7421bbb).
- **ktext hash collision trap**: never give new keywords a hash already used; collisions silently shrink `gvarc` → truncated BSS. Use a free hash (`in`=43). (2026-08-04, cfe47a3.)
- **Compiler source is self-hosting** — `parse_primary` must not gain new user-fn calls with live locals (allocator-clobber). Handle new syntax at token level (e.g. `rewrite_struct_literals()`).

---