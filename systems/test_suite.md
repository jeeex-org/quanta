## 8. Test Suite

39 programs gated by exit code in `test_suites/EXPECTED.tsv`. **0.0.6 baseline: all 39 compile, 37 x86_64 runtime correct, 2 expected compile-fail (trait, generics). ARM64: 35/37 runtime correct (option_test, result_test broken — bare variant pattern match bug).**

| Test | Expect | Status (x86_64) | Status (ARM64) |
|------|--------|-----------------|----------------|
| arithmetic | 30 | ✅ | ✅ |
| fib | 55 | ✅ | ✅ |
| struct_test | 7 | ✅ | ✅ |
| enum_test | 42 | ✅ | ✅ |
| match_test | 55 | ✅ | ✅ |
| file_open_test | 3 | ✅ | ✅ |
| float_test | 159 | ✅ | ✅ |
| unsigned_ops | 0 | ✅ | ✅ |
| prints_family | 0 | ✅ | ✅ |
| mem_test | 42 | ✅ | ✅ |
| bitwise_not | 0 | ✅ | ✅ |
| break_continue | 0 | ✅ | ✅ |
| exit/file_io/mmap | 0/42 | ✅ | ✅ |
| param8/9/12 | 36/0/0 | ✅ | ✅ |
| arg/elseif/pcheck | varied | ✅ | ✅ |
| stdlib_test | 0 | ✅ | ✅ |
| test_many_globals | 42 | ✅ | ✅ |
| builtins_test | 198 | ✅ | ✅ |
| **option_test** | 42 | ✅ | ❌ exit 0 (ARM64 bare variant bug) |
| **result_test** | 5 | ✅ | ❌ exit 0 (ARM64 bare variant bug) |
| **trait_test** | 0 | ❌ compile error — trait/impl not implemented | ❌ |
| **generics_test** | 12 | ❌ compile error — `<T>` generics not implemented | ❌ |

> 37 x86_64 tests pass. 2 aspirational tests (trait, generics) compile-fail by design. 2 ARM64 tests fail due to bare variant pattern match codegen bug (tracking in known_warts_bugs.md §10.1.1).

---
