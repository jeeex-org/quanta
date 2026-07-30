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
## 10. Known Warts & Bugs

### 10.1 P6 — 2 syntax tests fail at compile time

| Test | Symptom | Root cause |
|------|---------|------------|
| file_open_test (fixed) | path `\37` instead of filename | String header pointer passed directly to syscall — fixed by `+ 8` offset |
| enum_test | match result not returned | Captured match value with `let v = match ... return v` | ✅ Fixed (qc-0.0.4) |
| struct_test (fixed) | struct constructor undefined | `parse_call_impl` lacked `findstruct` — added struct constructor IR | ✅ Fixed |
| option_test (fixed x86_64) | `undeclared function: Some` | Recognized bare Some/None in `parse_call_impl` + `parse_match` + `parse_primary` | ✅ Fixed (x86_64) |
| result_test (fixed x86_64) | `undeclared function: Ok/Err` | Recognized bare Ok/Err in `parse_call_impl` + `parse_match` | ✅ Fixed (x86_64) |
| **ARM64 option_test** | **exit 0 instead of 42** | **ARM64 backend: cset/IR_IDX bugs for bare variant pattern match** | 🔴 OPEN |
| **ARM64 result_test** | **exit 0 instead of 5** | **ARM64 backend: cset/IR_IDX bugs for bare variant pattern match** | 🔴 OPEN |
| generics_test | `undeclared variable: U` | `<T>` generic type parameter syntax not parsed. Requires generic type system. |
| trait_test | `undeclared variable: Drawable` | `trait`/`impl`/self/method dispatch — full trait system not implemented |

### 10.1.1 ARM64 Bare Variant Pattern Match Bug (qc-0.0.6)

**Symptom**: x86_64 qc-0.0.6 compiles and runs `option_test.quanta` → exit 42, `result_test.quanta` → exit 5. ARM64 cross-compiled binary runs same tests → exit 0 for both.

**Root cause**: The ARM64 backend's `cset` condition code mapping and `IR_IDX` (op 32) handling don't correctly translate the IR generated for bare `Some`/`None`/`Ok`/`Err` pattern matching. The IR uses tag extraction via `IR_IDX` (index 0 of enum) followed by `IR_EQ`/`IR_BR` — both work on x86_64 but ARM64's `cset` was using inverted conditions and `IR_IDX` may have register allocation issues.

**Fix attempted**: Updated `cset` to correctly map IR condition codes (0=EQ, 1=NE, 2=LT, 3=GT, 4=LE, 5=GE) to ARM64 condition codes (0,1,11,12,13,10). Partially fixed but still returns 0.

**Files to investigate**:
- `arm_ci_func` — bare variant pattern branch
- `cset` function — condition code mapping
- `IR_IDX` handler (op 32) — ARM64 register allocation for enum tag extraction

**Status**: Blocked ARM64 promotion for qc-0.0.6. Must fix before qc-0.0.7 promotion.
