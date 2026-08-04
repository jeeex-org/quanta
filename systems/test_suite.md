## 8. Test Suite

53 programs gated by exit code in `test_suites/EXPECTED.tsv` (untracked working copy, run via `QC=<compiler> bash test_suites/scripts/run_tests.sh`). **Current baseline (qc-0.0.14-wip, 2026-08-04): 53/53 x86_64 runtime pass, 1 expected compile-fail (generics_test = P10 monomorphization gap).**

| Test | Expect | Status (x86_64) | Notes |
|------|--------|-----------------|-------|
| arithmetic | 30 | ✅ | |
| fib | 55 | ✅ | recursion |
| struct_test | 7 | ✅ | P8 structs |
| struct_literal_test | 7 | ✅ | P9 struct literal (not gated in EXPECTED.tsv — see below) |
| enum_test | 42 | ✅ | P7 enums |
| match_test | 55 | ✅ | P7 match |
| option_test | 42 | ✅ | P7 |
| result_test | 5 | ✅ | P7 |
| trait_test | 0 | ✅ | P9 trait/impl dispatch |
| file_open_test | 3 | ✅ | |
| float_test | 159 | ✅ | P6.1a floats |
| unsigned_ops | 0 | ✅ | udiv/umod/ult/... |
| prints_family | 0 | ✅ | |
| mem_test | 42 | ✅ | |
| bitwise_not | 0 | ✅ | |
| break_continue | 0 | ✅ | |
| exit/file_io/mmap | 0/42 | ✅ | |
| param8/9/12 | 36/0/0 | ✅ | |
| arg/elseif/pcheck | varied | ✅ | |
| stdlib_test | 0 | ✅ | |
| test_many_globals | 42 | ✅ | |
| builtins_test | 198 | ✅ | |
| array_test | 200 | ✅ | |
| tuple_test | 40 | ✅ | |
| fnptr_test | 0 | ✅ | |
| closure_test | 7 | ✅ | |
| **generics_test** | 12 | ❌ compile-fail | P10 `<T>` generics not implemented (expected) |

> 53/53 pass, 0 fail, 1 expected compile-fail (generics). ARM64: cross-compiled suite runs on device except features not yet ported to the ARM backend (for-in / `arr[-1]` — see known_warts_bugs.md §10.2).

### Coverage gaps (fixtures in `codes/` NOT gated in EXPECTED.tsv)

| Test | Expect | Status | Notes |
|------|--------|--------|-------|
| raw_ptr_test | 42 | ❌ compile-fail | `let p: *u64 = &x` — raw-pointer type annotation explodes IR (open bug, §10.2). `&`/`*` without annotation works. |
| bench_fib | 0 | ✅ works | performance fixture (duplicates fib) — intentionally ungated |
| mtu_* (multi-TU) | — | manual | need two-stage `--no-start` + link workflow; not single-file exit-code tests |

### For-in regression tests (ADDED to suite, 2026-08-04)

Dedicated for-in / `arr[-1]` / unsafe regression tests are now gated in EXPECTED.tsv (commit in progress) so future changes cannot silently break P10 for-in:

| Test | Code | Expect |
|------|------|--------|
| forin_basic | `fn main() { for x in [42] { return x } return 99 }` | 42 |
| forin_sum | `fn main() { let s=0; for x in [1,2,3,4] { s=s+x }; return s }` | 10 |
| forin_nested | `fn main() { let s=0; for i in [1,2] { for j in [10,20] { s=s+i+j } }; return s }` | 66 |
| arrlen_neg1 | `fn main() { let a=[5,6,7]; return a[-1] }` | 3 |
| forin_break | `fn main() { let s=0; for i in [1,2,3,4,5] { if i==3 { break }; s=s+i }; return s }` | 3 |
| unsafe_block | `fn main() { unsafe { return 42 } }` | 42 |

Also gated (previously ungated working fixtures): struct_literal_test (7), trait_min/trait_only/trait_test2 (0), option_simple (42), option_ctor (0), option_tuple (42), simple_min (0).

---