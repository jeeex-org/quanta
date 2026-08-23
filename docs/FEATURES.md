# Quanta — Features: Shipped vs. To-Do

Source-of-truth feature inventory for the Quanta x86 self-hosting compiler.
**Derived directly from the 0.0.55 source** (keyword table `ktext` in helpers.quanta,
87 builtins in `is_bltn`, parser dispatch in parse.quanta, 2026-08-17). No guesswork:
every row maps to a real token/builtin in source.

Status legend:
- ✅ done — implemented and exercised
- 🟡 partial — works in a limited form, or has a known bug/limitation, or lexed-but-not-parsed
- ❌ todo — not implemented (on the build-order queue to 1.0)

Test legend (the **Test?** column):
- ✅ gate — a test_suite in the gate (EXPECTED.tsv, 85 core tests) covers it
- 🟡 file-only — a test file exists but is NOT in the gate (e.g. std_* removed per rule "core only until 1.0", or feature unimplemented)
- ❌ none — no test exists

"Core" = the language itself. "Builtins" = inline-code primitives emitted by the compiler.

---

## A. Core — Keywords & Syntax (lexer `ktext` codes 1–57)
| Keyword | ktext | Status | Test? | Notes |
|---|---|---|---|---|
| fn | 1 | ✅ done | ✅ gate | func defs |
| let | 2 | ✅ done | ✅ gate | variable binding |
| if | 3 | ✅ done | ✅ gate | elseif_test |
| loop | 5 | ✅ done | ✅ gate | loop_test, parse_loop |
| while | 6 | ✅ done | ✅ gate | break_continue |
| for | 7 | ✅ done | ✅ gate | for-in (array) + C-style `for i=1;i<=n;i=i+1`; range `..` NOT parsed |
| break | 8 | ✅ done | ✅ gate | |
| continue | 9 | ✅ done | ✅ gate | |
| return | 16 | ✅ done | ✅ gate | |
| unsafe | 18 | ✅ done | ✅ gate | unsafe_block |
| match | 22 | 🟡 partial | ✅ gate | match_test rc=132 (gate GREEN); expression arms only (block arms TODO) |
| const | 57 | ✅ done | ✅ gate | const_test |
| defer | token | ✅ done | ✅ gate | defer_test |
| in | token | ✅ done | ✅ gate | for-in |
| alias | 17 | ✅ done | ✅ gate | alias_test (function alias newname=existingfn) |
| extern "C" | 19 | 🟡 partial | 🟡 file-only | funcscan extern; syscall_test exercises |
| struct | token | ✅ done | ✅ gate | struct_test, struct_methods_test, struct_literal_test (literal coverage present) |
| enum | 21 | ✅ done | ✅ gate | enum_test rc=42; Some/None match arms exercised |
| type | 23 | ❌ todo | ❌ none | lexed, unparsed |
| interface | 24 | 🟡 partial | ✅ gate | trait_test/trait_test2/trait_min rc=10 in gate; dispatch via trait methods |
| impl | 25 | 🟡 partial | ✅ gate | trait methods exercised (struct_methods_test rc=151) |
| trait | 26 | 🟡 partial | ✅ gate | trait_test rc=10 in gate; method dispatch works |
| where | 27 | ❌ todo | ❌ none | lexed, unparsed |
| Option/Some/None | 28/29/30 | ✅ done | ✅ gate | option_test/option_simple/option_ctor/option_tuple rc=42 in gate |
| Result/Ok/Err | 31/32/33 | ✅ done | ✅ gate | result_test rc=49 in gate |
| ref | 34 | ❌ todo | ❌ none | lexed, unparsed |
| mut | 35 | ❌ todo | ❌ none | lexed, unparsed |
| move | 36 | ❌ todo | ❌ none | lexed, unparsed |
| String | 37 | ❌ todo | ❌ none | lexed, unparsed |
| as | 41 | ❌ todo | ❌ none | lexed, unparsed |
| raw | 38/52 | ❌ todo | ❌ none | lexed, unparsed |
| asm | 40/53 | ❌ todo | 🟡 file-only | asm_test exists but NOT in gate |
| volatile | 39/54 | ❌ todo | ❌ none | lexed, unparsed |
| usize | 42/48 | 🟡 partial | ✅ gate | lexed; used as size type |
| u8 | 44 | ❌ todo | ❌ none | lexed, unparsed (mask builtin u8 exists) |
| u16 | 45 | ❌ todo | ❌ none | lexed, unparsed |
| u32 | 46 | 🟡 partial | ✅ gate | u32 mask builtin exists |
| u64 | 47 | 🟡 partial | ✅ gate | u64 mask builtin exists |
| bool | 49 | ❌ todo | ❌ none | lexed, unparsed |
| char | 50 | ❌ todo | ❌ none | lexed, unparsed |
| byte | 51 | ❌ todo | ❌ none | lexed, unparsed |
| int | 55 | ❌ todo | ✅ gate | signed default alias; bare literal type |
| and / or / not | 13/14/15 | ❌ todo | ❌ none | lexed, NOT parsed (use && / \|\| / !) |
| true / false | 10/11 | ❌ todo | ❌ none | lexed, NOT parsed (use 1/0) |
| global | 20 | ❌ todo | ❌ none | lexed, NOT parsed (use extern/let) |

## B. Core — Types
| Type | Status | Test? | Notes |
|---|---|---|---|
| i64 (default integer) | ✅ done | ✅ gate | arithmetic, param* |
| f64 | ✅ done | ✅ gate | float_test rc=159, simple_fadd rc=7 |
| usize | 🟡 partial | ✅ gate | lexed; used as size type |
| u32 / u64 (masks) | 🟡 partial | ✅ gate | u32/u64 builtins; no native type keyword |
| u8 / u16 | ❌ todo | ❌ none | only mask builtins conceptually |
| bool | ❌ todo | ❌ none | lexed, unparsed |
| char | ❌ todo | ❌ none | lexed, unparsed |
| byte | ❌ todo | ❌ none | lexed, unparsed |
| float literals (`3.14`) | ❌ todo | ❌ none | lexer hard-errors "not supported" |
| string (real type) | ❌ todo | ❌ none | TT_STRING reserved; byte-buffer + print only |
| struct | ✅ done | ✅ gate | fields + `obj.method` + literal (struct_literal_test in gate) |
| enum (user-defined) | ✅ done | ✅ gate | enum_test rc=42 in gate |
| tuple `(T,U)` | ✅ done | ✅ gate | tuple_test rc=40 in gate (mk_any-based tuples) |
| typed array/slice | ❌ todo | ✅ gate | array_test/forin_* cover untyped `[...]` |

## C. Core — Control Flow
| Feature | Status | Test? | Notes |
|---|---|---|---|
| if/else | ✅ done | ✅ gate | elseif_test |
| while | ✅ done | ✅ gate | break_continue |
| loop | ✅ done | ✅ gate | parse_loop |
| for-in (array) | ✅ done | ✅ gate | forin_basic/break/nested/sum |
| match (expr arms) | ✅ done | ✅ gate | match_test rc=132 |
| break / continue | ✅ done | ✅ gate | |
| return / defer | ✅ done | ✅ gate | defer_test |
| for-range `for i in 0..n` | ❌ todo | ❌ none | `..` operator NOT parsed (verified) |
| match block arms `1 => { }` | ✅ done | ✅ gate | match_test covers block arms |
| `?` early-return propagation | ✅ done | ✅ gate | question_mark rc=0, option_test/result_test in gate |
| loop expressions / labeled break w/ value | ❌ todo | ❌ none | |
| try/catch | ❌ todo | ❌ none | only panic + `?` unwrap |

## D. Core — Expressions & Operators
| Feature | Status | Test? | Notes |
|---|---|---|---|
| arithmetic (+ - * / %) | ✅ done | ✅ gate | arithmetic |
| bitwise (& | ^ ~ << >>) | ✅ done | ✅ gate | bitwise_not |
| comparisons (== != < > <= >=) | ✅ done | ✅ gate | |
| logical (&& \|\| !) | ✅ done | ✅ gate | (and/or/not keywords unparsed; use symbols) |
| ternary | ✅ done | ✅ gate | |
| field access / index | ✅ done | ✅ gate | struct_test, array_test |
| unsigned arith | ✅ done | ✅ gate | unsigned_ops (udiv/umod/ult/ugt/ulte/ugte) |
| operator overloading | ❌ todo | ❌ none | |
| range `..` expression | ❌ todo | ❌ none | needed by for-range |
| array push `a.push(v)` | ✅ done | ✅ gate | array_push_method rc=7, array_push_empty_annot rc=7, array_push_closure_mix rc=35. Method form only — bare `push(v,e)` is the byte-stride STRING push. Silently returned 0 in 0.0.65 (IR_CLOSURE/IR_APUSH both = opcode 72); fixed 0.0.66 |
| generics `<T>` | 🟡 type-erased | ✅ gate | generics_test rc=42; `map<T,U>` example returns 12. Parsed and erased at codegen — no monomorphisation, no compile-time constraint checking |
| tuples `(a,b)` | ✅ done | ✅ gate | tuple_test rc=40, option_tuple rc=42. Literals, N-tuples, nested access `t.0.1`, tuple-valued returns, element reassign, tuple in array, destructuring `let x,y = f()`. Was listed as "remaining" in ROADMAP until a 0.0.70 audit found 13/13 probes already passing |
| `and` / `or` keywords | ✅ done (0.0.70) | ✅ gate | logical_keywords rc=4, logical_keywords_shortcircuit rc=2. Exact aliases of `&&`/`\|\|` incl. short-circuit. Before 0.0.70 the keyword was tokenized but never consumed, so only the FIRST operand was evaluated and the rest silently discarded |
| `!` / `not` | ✅ done (0.0.71) | ✅ gate | logical not -> 0/1. Const and runtime paths now agree (both logical); `~`/`~~` is separate bitwise-not. Before 0.0.71 they silently disagreed. `bitwise_not.quanta` rewritten to pin both |
| match guards `n if n>3 =>` | ✅ done (0.0.69) | ✅ gate | match_guard rc=111, match_guard_false rc=222, match_guard_order rc=4. Guard may use the bound name; false guard falls through to the next arm; arms tried in order. Silently yielded 0 before 0.0.69 (the `if` was never consumed) |
| closure literals `\|a\| { a+1 }` | ✅ done (0.0.65) | ✅ gate | closure_basic rc=6, closure_multi_param rc=7, closure_higher_order rc=42; braces required |
| user fn overrides builtin | ✅ done (0.0.68) | ✅ gate | user_fn_beats_builtin rc=42 (was 0), user_fn_beats_builtin_chain rc=38 (was SIGILL 132), builtin_still_inline rc=3. One guard in emit_bltn/emit_bltn2 (was enforced in only 2 of 86 branches). EXCEPTION: mem_load/mem_store/mem_load8/mem_store8 + fadd/fsub/fmul/fdiv are primitive intrinsics and NOT overridable — the compiler's own w64↔mem_store wrappers are mutually recursive, so user-wins there is infinite recursion and breaks the self-host |
| fnptr + closure_call | ✅ done (0.0.72) | ✅ gate | fnptr_test rc=7. fnptr now returns a [codeptr, env=0] tuple (same layout as IR_FNVAL), so it can be passed directly to closure_call. Before 0.0.72 fnptr emitted a raw pointer and feeding it to closure_call dereferenced it as a tuple → SEGFAULT |
| const redefinition | ✅ done (0.0.75) | ✅ gate | const_redefine rc=5 (was 10). First value wins; duplicate silently skipped. Scanner phase (`features.quanta:scan_globals`) registers consts before the parser runs, so the dup check had to go there |
| closure captures | ✅ done (0.0.67) | ✅ gate | closure_capture rc=15, closure_capture_multi rc=11, closure_capture_byvalue rc=11. Free variables of the enclosing fn captured BY VALUE into a heap env array at construction; body reads them via IR_CAPREAD from env in r10. Repeat references share one slot; max 32 captures |

## E. Memory & Runtime
| Feature | Status | Test? | Notes |
|---|---|---|---|
| mem_alloc/free/mmap/realloc | ✅ done | ✅ gate | mem_test, test_mmap |
| memcpy/memcmp/memmove | ✅ done | ✅ gate | memops_test |
| mem_load/mem_store(+8) | ✅ done | ✅ gate | raw_ptr_test |
| defer (LIFO replay) | ✅ done | ✅ gate | defer_test |
| unsafe blocks | ✅ done | ✅ gate | unsafe_block |
| real allocator (free-list/GC) | ❌ todo | ❌ none | bump mmap only |
| callee load-store-to-same-addr aliasing | ✅ done | ✅ gate | reg_alias/alias_derive_loop/alias_loadstore_loop pass (fixed in 0.0.43–0.0.46 debt window) |
| stack unwind / destructors / RAII | ❌ todo | ❌ none | defer is manual |
| ref/mut/move (ownership) | ❌ todo | ❌ none | tokens reserved |

## F. Builtins — Already Shipped (87 registered, prefixes expanded)
| Group | Items | Test? |
|---|---|---|
| syscall family | syscall(1–6) | ✅ gate (syscall_test) |
| exit / panic | exit, panic | ✅ gate (exit_test) |
| memory map | mmap | ✅ gate (test_mmap) |
| heap | mem_alloc/free/realloc | ✅ gate (mem_test) |
| mem ops | memcpy, memcmp, memmove, mem_load, mem_store(+8) | ✅ gate (memops_test, raw_ptr_test) |
| file I/O | file_open, file_read, file_write, file_close | ✅ gate (file_open_test rc=3, file_io, file_write_test) |
| print | print, printi, println, prints, printsp, newline | ✅ gate (prints_family) |
| container | len, str, push, pop, vec_get, vec_set, vec_load, vec_store, vec_add, vec_sub, vec_mul, vec_div | ✅ gate (array_test, etc.) |
| variadic / any | arg, mk_any | ✅ gate (arg_or rc=1, arg_test rc=40) |
| closures | closure literal `\|a\| { … }`, fnptr, closure_call | ✅ gate (closure_basic rc=6, closure_multi_param rc=7, closure_higher_order rc=42, fnptr_test rc=7) |
| float arith | fadd, fsub, fmul, fdiv (int args → int result), i2f, f2i | ✅ gate (float_test rc=159, simple_fadd rc=7) |
| float compare | feq, flt, fgt, fle, fge, fisnan, fisinf (f64 bit-pattern args → 0/1) | ✅ gate (float_test rc=159) |
| float math | sqrt, floor, ceil, abs (f64 bit-pattern in/out) | ✅ gate (float_test rc=159) |
| process / env | getpid, getppid, arg_count, environ (getenv is a STUB: returns 0) | ✅ gate (getpid_test, getppid_test, argc_test) |
| stdin I/O | getc (getline untested-in-gate) | ✅ gate (getc_test) |
| fs metadata | stat, fstat, lseek, unlink, mkdir, chdir, rename | 🟡 PARTIAL — fstat/lseek work; stat/unlink/mkdir/chdir/rename BROKEN (path-string remap returns -ENOENT, see §I) |
| introspection | abort, debugbreak | ✅ gate (abort_test rc=134; debugbreak = int3 → rc=133) |
| random | getrandom | ✅ gate (getrandom_test rc=1) |
| unsigned arith | udiv, umod, ult, ugt, ulte, ugte, u8, u32, u64 | ✅ gate (unsigned_ops) |
| byte/endianness | bswap, popcount, clz, ctz, rotl, rotr | ✅ gate (bits_test) |
| time | gettimeofday, nanosleep, sleep | ✅ gate (time_test) |

## G. Builtins — To-Do
| Group | Items | Test? |
|---|---|---|
| float math (remaining) | sin, cos, tan, pow, log, min, max | ❌ none (planned: math_test) |
| string ops | strcat, substr, strcmp, str_split, utf8 | ❌ none (planned: strtest) |
| atomics | atomic_load/store/add/cmpxchg + futex | ❌ none (planned: atomic_test) |
| networking | socket/connect/bind/listen/accept | ❌ none (planned: net_test) |
| introspection (remaining) | stack-trace | ❌ none (planned: abort_test) |
| random (remaining) | rand | ❌ none (planned: rand_test) |
| bit/byte extras | parity, bitfield insert/extract, per-size swap | ❌ none |
| intrinsics | prefetch, fence, branch hints | ❌ none |

## I. Known issues (tracked, not blocking promotion)
- **fs-meta path-string remap (stat/unlink/mkdir/chdir/rename): BROKEN.** These
  builtins call `newfstatat`/`unlinkat`/etc. with the path pointer taken from the
  string *length-prefix base* (off by 8) and/or a faulty `rr`-based register
  remap that ends up passing the buffer as the path → kernel returns `-ENOENT`
  (rc=254). `fstat(fd,buf)` and `lseek(fd,off,whence)` work (no path string, no
  remap). Quanta strings are length-prefixed `[8-byte len][null-term data]`; the
  syscall ABI needs `base + 8`. `file_open` works only when called as
  `file_open(path + 8, flags)` (see `file_open_test.quanta`). Fix: correct the
  path-pointer offset / remap in `emit_bltn2` (compiler/0.0.66/src/x86/emitter.quanta).
- **`getenv(name)` is a STUB** — returns `0` unconditionally (environment parsing
  not yet implemented). Documented as such; `getenv_test.quanta` pins the stub
  behaviour so a future real implementation is caught by the gate.
- **`debugbreak()` = `int3`** → SIGTRAP (rc=133). Works but not in the gate
  (would need a harness that tolerates the trap). `abort()` → `exit(134)` is gated.

## H. Tooling
| Item | Status | Test? | Notes |
|---|---|---|---|
| Quanta-native code-writing tool | ❌ todo | ❌ none | user-stated goal — edit Quanta source reliably without external scripting |
| debugger/objdump integration | ❌ todo | ❌ none | |
| package manager | ❌ todo | ❌ none | |
| build system (beyond `qc src bin`) | ❌ todo | ❌ none | |

---

## Summary counts (source-derived)
- **Keywords (ktext): 57 codes defined; ~19 parsed, ~13 lexed-only gaps, rest partial.**
- **Builtins registered: 87 (prefixes expanded).**
- **Core tests in gate: 88** (EXPECTED.tsv, 88 rows). `std_*` tests exist as files but
  removed from gate (core-only rule); `mtu_*` multi-translation-unit experiments are
  also file-only. So ~12 code files are file-only (not in the gate count).
- **0.0.46 session fixes (2026-08-15):** (1) BUG #3 — `mmap` builtin emitted a fixed
  address hint `0x60000000` in `rdi`; under Valgrind that address is reserved, so `mmap`
  returned `-22` (EINVAL) for small allocations (REGS/FREGS) and the `-22` was used as a
  table base → `Invalid write of size 8` SIGSEGV. Fixed by passing `rdi=0` (kernel chooses);
  same fix applied to `sleep`'s inline mmap. Verified: Valgrind 0 errors, full gate green.
  (2) `emitter.quanta` contained the ENTIRE emitter duplicated (block 1 lines 1–430 and
  block 2 lines 431–1600 redeclared every fn/let); only block 2 was live (last-definition
  wins, confirmed via a printi sentinel that fired once). Block 1 removed (430 lines dead code).
- **Test framework note:** tests `return`/`exit` a *computed value* (not just 0); EXPECTED.tsv's
  `expected_rc` is that computed answer. So non-zero expected_rc entries are correct results, not
  hidden failures. Verified by reading test bodies (e.g. array_test returns 200 = a.1; simple_fadd
  returns 7 = 3.0+4.0). The gate is genuinely green.

## Build order & sequencing

The authoritative build order to 1.0 (debt window → P2 builtins → P3
language → P4 tooling → 1.0) now lives in **`docs/ROADMAP.md` §3** (single
source of truth, consolidated 2026-08-17). It is no longer duplicated here
to prevent version-number drift.

Key invariants (unchanged): one feature per WIP version; debt window
(0.0.43–0.0.50) closed before new features; gate green before promotion;
0.0.90 reserved for the Quanta-native code-writing tool; ARM64 backend
deferred to POST-1.0.

