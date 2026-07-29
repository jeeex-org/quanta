## 10. Known Warts & Bugs

### 10.1 P6 — 2 syntax tests fail at compile time

| Test | Symptom | Root cause |
|------|---------|------------|
| file_open_test (fixed) | path `\37` instead of filename | String header pointer passed directly to syscall — fixed by `+ 8` offset |
| enum_test | match result not returned | Captured match value with `let v = match ... return v` | ✅ Fixed (qc-0.0.4) |
| struct_test (fixed) | struct constructor undefined | `parse_call_impl` lacked `findstruct` — added struct constructor IR | ✅ Fixed |
| option_test (fixed) | `undeclared function: Some` | Recognized bare Some/None in `parse_call_impl` + `parse_match` + `parse_primary` | ✅ Fixed (x86_64) |
| result_test (fixed) | `undeclared function: Ok/Err` | Recognized bare Ok/Err in `parse_call_impl` + `parse_match` | ✅ Fixed (x86_64) |
| **ARM64 option_test** | **exit 0 instead of 42** | **ARM64 backend: bare Some/None pattern match IR emits wrong registers** | 🔴 OPEN |
| **ARM64 result_test** | **exit 0 instead of 5** | **ARM64 backend: bare Ok/Err pattern match IR emits wrong registers** | 🔴 OPEN |
| generics_test | `undeclared variable: U` | `<T>` generic type parameter syntax not parsed. Requires generic type system. |
| trait_test | `undeclared variable: Drawable` | `trait`/`impl`/self/method dispatch — full trait system not implemented |

### 10.1.1 ARM64 Bare Variant Pattern Match Bug (qc-0.0.5)

**Symptom**: x86_64 qc-0.0.5 compiles and runs `option_test.quanta` → exit 42, `result_test.quanta` → exit 5. ARM64 cross-compiled binary runs same tests → exit 0 for both.

**Root cause hypothesis**: The new IR handlers for bare enum variants (`Some`, `None`, `Ok`, `Err`) in pattern matching emit x86_64 register sequences that don't translate correctly to ARM64. The pattern match capture logic likely uses x86_64-specific register conventions (rax, rdi, etc.) instead of the ARM64 ABI (x0-x7).

**Files to investigate**:
- `parse_match` — bare variant pattern branch
- ARM64 IR emission for `IR_ENUM_VARIANT` / match capture
- `arm_emit_*` functions handling enum variant patterns

**Status**: Blocked ARM64 promotion for qc-0.0.5. Must fix before qc-0.0.6 promotion.

### 10.2 Pre-existing (non-P6)

- `main` with no `return` → leftover rax (rc=1), not 0.
- `name[idx]` on undeclared name → yields 0 silently.
- Double-free (manual + auto scope free) → harmless (munmap reentrant).
- No static borrow checker (deferred until generics).
- Expression nesting cap = 30.
- 1 MB source limit.

### 10.3 Known gaps

- No string/array operators in the language (use builtins).
- Single runtime value type (64-bit word).
- No nested function definitions.
- No block comments.

---
