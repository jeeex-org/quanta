## 8. Test Suite

39 programs gated by exit code in `test_suites/EXPECTED.tsv` (untracked working copy, run via `QC=<compiler> bash test_suites/scripts/run_tests.sh`). **Current baseline (qc-0.0.14, 2026-08-05): 39/39 x86_64 runtime pass, 1 expected compile-fail (generics_test = P10 monomorphization gap).**

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
| **generics_test** | 12 | ❌ compile-fail | P10 `<T>` generics not implemented (expected) |

> 39/39 pass, 0 fail, 1 expected compile-fail (generics). ARM64: cross-compiled suite runs on device except features not yet ported to the ARM backend (see known_warts_bugs.md §10.2).

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

### Pillar → Test Mapping (Corrected 2026-08-05)

| Pillar | Feature | Tests | Status |
|--------|---------|-------|--------|
| P1 | Core types/control flow | arithmetic, fib, break_continue, param*, arg*, elseif* | ✅ 12/12 |
| P2 | Memory/ownership | mem_test, mmap1, test_mmap, test_many_globals, exit/file_io | ✅ 4/4 |
| P3 | FFI/fnptr | fnptr_test | ✅ 1/1 |
| P4 | Multi-backend | cross-compile (manual) | ✅ |
| P5 | ELF/BSS | self-host fixed-point | ✅ |
| **P6 (CLOSED)** | **Raw ptr deref/arith/cast/null, unsafe** | unsafe_block, raw_ptr* (no annotation) | ✅ |
| P7 | Option/Result/Enum/Match | option_test, result_test, enum_test, match_test, option_* | ✅ 6/6 |
| **P8** | **Structs** | **struct_test, struct_literal_test** | ✅ **2/2** |
| **P9** | **Traits/impl/vtable** | **trait_test, trait_min, trait_only, trait_test2** | ✅ **4/4** |
| **P10** | **For-in / arr[-1]** | **forin_basic, forin_sum, forin_nested, arrlen_neg1, forin_break** | ✅ **5/5** |
| **P10** | **Generics** | **generics_test** | ❌ **0/1** (expected) |
| **P11** | **P6 stubs** | raw_ptr_test (type annotation), volatile, asm, SIMD | ❌ **0/4** |
| **P12** | **GPU/PTX/SPIR-V/WASM** | — | — |

**Key corrections from prior version:**
- P8 was **Structs** (not concurrency — concurrency never existed)
- P9 was **Traits/impl/vtable** 
- P10 = For-in (DONE) + Generics (NEXT)
- P11 = P6 stub cleanup (type annotation, ARM volatile, inline asm, SIMD)
- P12 = GPU/PTX/SPIR-V/WASM (future)