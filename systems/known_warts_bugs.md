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

### 10.2 OPEN / CLOSED status (verified against code + hardware 2026-08-10)

| Test / issue | Symptom | Status |
|------|---------|--------|
| generics_test | `<T>` monomorphization | ✅ **DONE** — compiles + runs rc=12 on x86 AND ARM64 hardware. P10 generics complete. |
| `let p: *u64 = &x` | raw-ptr type annotation | ✅ **DONE** — compiles + runs rc=42. P11. |
| `let x: int = 42` | `int` keyword | ✅ **DONE** (qc-0.0.20-wip) — `int` now maps to signed default (vtype 0). Test: int_keyword_test (rc=42). |
| ARM64 for-in parity | — | ✅ CLOSED (for-in) |
| ARM64 volatile barrier | `dmb ish` | ✅ **DONE** — emitted at lines 7011/7019. P11. |
| Inline asm | hex template | ✅ **DONE** — real hex-byte emitter (line 7060+). P11. |
| SIMD vec128 | SSE2/NEON | ✅ **DONE** — real `addpd`/`mulpd`/`fadd v0.2d` etc. `simd_test` rc=52 x86+ARM. P11. (The `IR_VEC128` op at 5796/7051 is dead `nop` stub — builtins bypass it and emit SIMD directly.) |
| **ARM64 syscalls** | `svc #0` | ✅ **DONE** — ARM64 backend emits `asvc()` (svc #0) with correct AArch64 syscall numbers (64=write, 93=exit, 222=mmap, 56=openat) via the `asvc()` helper (line 5978). The x86 `int 0x80` (`sysc()`) is only used on `target_arch==0`. Cross-compile + native paths both correct; full 62/62 suite passes on ARM-01 including `file_io`/`file_open_test`. (Prior docs claiming this was OPEN were stale.) |
| **ARM64 native self-host** | Stage-2 SIGSEGV rc=139 on real hw | 🔴 OPEN (P12) — reproduced on ARM-01: `qc-0.0.19-arm /tmp/qc_src.quanta /tmp/out.bin` → segfault (rc=139) at stage-2 self-host. Cross-compile path is the supported/full-working path (62/62 on hw). |

### 10.3 Known tooling traps (documentation of past debugging effort)

- **Fixed-point byte 303**: bootstrap-built vs self-hosted binary differ at byte 303 (ELF first-gen stamp, benign). Fixed-point of the wip's own self-host (`v2==v3`) is byte-identical.
- **BSS truncation diagnostic**: `readelf -l <bin> | grep -A1 RW` — correct = MemSiz page-rounded (0x2000); truncated = MemSiz==FileSiz (0x1038 → SIGBUS on globals). Root cause fixed in gsz bootstrap (7421bbb).
- **ktext hash collision trap**: never give new keywords a hash already used; collisions silently shrink `gvarc` → truncated BSS. Use a free hash (`in`=43). (2026-08-04, cfe47a3.)
- **Compiler source is self-hosting** — `parse_primary` must not gain new user-fn calls with live locals (allocator-clobber). Handle new syntax at token level (e.g. `rewrite_struct_literals()`).

---

**Pillar mapping (verified 2026-08-11):**
- P10: Generics monomorphization — ✅ DONE (generics_test rc=12 x86+ARM)
- P11: P6 stub cleanup + `int` keyword — ✅ CLOSED (raw-ptr type anno, ARM `dmb ish`, inline asm, SIMD vec128, `int` all working on hw)
- P12: ARM64 backend hardening — 🔴 OPEN (native self-host SIGSEGV rc=139 reproduced on ARM-01; ARM syscalls already correct)
- P13: GPU/PTX/SPIR-V/WASM/bare-metal — ❌ NOT STARTED