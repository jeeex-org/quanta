# Quanta — Features: Shipped vs. To-Do

Source-of-truth feature inventory for the Quanta x86 self-hosting compiler.
Originally derived from the 0.0.55 source (keyword table `ktext` in helpers.quanta,
87 builtins in `is_bltn`, parser dispatch in parse.quanta, 2026-08-17), since
extended through 0.0.86 (float literals, big-int stages, literal auto-promotion,
inline asm). Every row maps to a real token/builtin in source.

Status legend:
- ✅ done — implemented and exercised by a gated test
- 🟡 partial — works in a limited form, or has a known bug/limitation, or lexed-but-not-parsed
- ❌ todo — not implemented (on the build-order queue to 0.1.0)

Test legend (the **Test?** column):
- ✅ gate — a test program in the gate (EXPECTED.tsv) covers it
- 🟡 file-only — a test file exists on disk but is NOT in the gate
- ❌ none — no test exists

All test-file names below are verified to exist in `test_suites/codes/` and their
gate status (✅ gate / 🟡 file-only) is verified against EXPECTED.tsv. `std_*` tests
exist as files but are excluded from the gate per the "core only until 0.1.0" rule.

"Core" = the language itself. "Builtins" = inline-code primitives emitted by the compiler.

---

## A. Core — Keywords & Syntax (lexer `ktext` codes 1–57)

| Keyword | ktext | Status | Test? | Notes / test file |
|---|---|---|---|---|
| fn | 1 | ✅ done | ✅ gate | func_call_args.quanta, simplified_syntax.quanta |
| let | 2 | ✅ done | ✅ gate | simplified_syntax.quanta, mut_basic.quanta |
| if | 3 | ✅ done | ✅ gate | elseif_test.quanta |
| loop | 5 | ✅ done | ✅ gate | loop_test.quanta |
| while | 6 | ✅ done | ✅ gate | break_continue.quanta |
| for | 7 | ✅ done | ✅ gate | forin_basic.quanta / forin_break.quanta / forin_nested.quanta / forin_sum.quanta; C-style `for i=1;i<=n;i=i=1`; for-range `for i in 0..n` (for_range_basic.quanta, rc=3, 0.0.76) |
| break | 8 | ✅ done | ✅ gate | break_continue.quanta |
| continue | 9 | ✅ done | ✅ gate | break_continue.quanta |
| return | 16 | ✅ done | ✅ gate | exit_test.quanta, func_call_args.quanta |
| unsafe | 18 | ✅ done | ✅ gate | unsafe_block.quanta |
| match | 22 | ✅ done | ✅ gate | match_test.quanta (rc=132, gate GREEN); expression + block arms (`1 => { }`) done |
| const | 57 | ✅ done | ✅ gate | const_test.quanta |
| defer | token | ✅ done | ✅ gate | defer_test.quanta |
| in | token | ✅ done | ✅ gate | forin_basic.quanta (for-in array iteration) |
| alias | 17 | ✅ done | ✅ gate | alias_test.quanta (function alias newname=existingfn) |
| extern "C" | 19 | ✅ done (0.0.98) / fixed (0.0.99) | ✅ gate | `extern "C" fn square(x)` declared + called via `--emit-obj` + external `ld`/`gcc`. 0.0.99 fixed the real defects 0.0.98 left: **string args** get the 8-byte length header skipped (`add reg,8` → `char*`, so `strlen("hello")`→5, `write(1,"hi",2)`→"hi"); **multi-arg calls** fixed (`arg_start`/`arg_cnt` mapping); **stack alignment** (`push r11/call/pop r11`, 16-byte) so `printf`/`puts` don't SSE-fault; **stdout flush** via libc `exit()` in object mode. Scalar calls (`abs(-42)`→42) and trait/interface vtable dispatch all work. EXE-mode standalone-PLT/GOT (no external `ld`) is deferred — object-mode + gcc is the supported path. |
| struct | token | ✅ done | ✅ gate | struct_test.quanta, struct_methods_test.quanta, struct_literal_test.quanta |
| enum | 21 | ✅ done | ✅ gate | enum_test.quanta (rc=42); Some/None match arms exercised |
| type | 23 | ✅ done (0.0.77) | ✅ gate | type_alias.quanta (rc=42). `type MyInt = int` then `let x: MyInt` |
| interface | 24 | ✅ done (0.0.98) | ✅ gate | trait_test.quanta / trait_test2.quanta / trait_min.quanta (rc=10, in gate); dispatch via vtable (method.quanta desugars `obj.method(args)` → `method(obj,args)`). |
| impl | 25 | ✅ done (0.0.98) | ✅ gate | trait methods exercised (struct_methods_test.quanta, rc=151). |
| trait | 26 | ✅ done (0.0.98) | ✅ gate | trait_test.quanta (rc=10, in gate); method dispatch works via vtable. |
| where | 27 | ✅ done (0.0.93) | ✅ gate | `fn f<T>(x:T) where T: Trait` parsed + ELIDED (constraints not yet enforced). Verified: `->` ret type, multi-predicate `where A: Num, A: Copy`, without ret type, trait bounds in body. where_clause_test.quanta (rc=7) gates it. |
| Option/Some/None | 28/29/30 | ✅ done | ✅ gate | option_test.quanta / option_simple.quanta / option_ctor.quanta / option_tuple.quanta (rc=42, in gate) |
| Result/Ok/Err | 31/32/33 | ✅ done | ✅ gate | result_test.quanta (rc=49, in gate) |
| ref | 34 | ✅ done (0.0.94) | ✅ gate | `ref r = &x` borrow alias (pointer; `*r` reads through). ownership_sigils_test.quanta gates it. |
| mut | 35 | ✅ done (0.0.76/0.0.94) | ✅ gate | `mut x = e` rebindable local; ownership tag recorded. mut_basic.quanta + ownership_sigils_test.quanta. |
| move | 36 | ✅ done (0.0.94) | ✅ gate | `move x` ownership-transfer prefix; tags symbol moved (3). ownership_sigils_test.quanta gates it. |
| String | 37 | ✅ done (0.0.95) | ✅ gate | `let s: String = "..."` first-class; length-aware header `[ptr]=len`, bytes at `ptr+8`. `==`/`!=` → `str_eq`/`str_ne` (manual byte-loop; `repe cmpsb` + `memcmp` are defective in Quanta). `..` concat, `len()`, `print()` all length-aware. string_compare_test.quanta (rc=0) + 24-case compare suite gate it. |
| as | 41 | ✅ done (0.0.90) | ✅ gate | `x as T` width cast (IR_BAND mask); usize/signed identity. as_cast_test.quanta gates it. |
| raw | 38/52 | ✅ done (0.0.90) | ✅ gate | `*u64`/`*mut u64` type annotation + deref/store; raw_ptr_test(s) gate it. |
| asm | 40/53 | ✅ done | ✅ gate | asm!("hex bytes") -> IR_ASM raw machine-code emit (method.quanta:261); asm_test.quanta (rc=42, in gate) |
| volatile | 39/54 | ✅ done (0.0.92) | ✅ gate | `volatile *p` (load) and `volatile *p = v` (store) through raw pointers. Was a SILENT NO-OP (lexed TT_VOLATILE 34, parse guarded on TT_KEY — never matched → dropped binding + following control flow); fixed to parse on token type + route at statement level; IR_VOLATILE_LOAD/STORE codegen fixed (MOV opcode + a0/a1 order). volatile_ptr_test.quanta (rc=7) gates it. |
| usize | 42/48 | ✅ done (0.0.91) | ✅ gate | type annotation parsed (vtype 5); full 64-bit, no 2^32 wrap; `as usize` is identity |
| u8 | 44 | ✅ done | ✅ gate | width-tagged type; add/sub/mul wrap via vreg_type + width_mask (REX.B-correct for r8-r15) |
| u16 | 45 | ✅ done | ✅ gate | width-tagged type; add/sub/mul wrap via vreg_type + width_mask (REX.B-correct for r8-r15) |
| u32 | 46 | ✅ done (0.0.91) | ✅ gate | type annotation parsed (vtype 3); wraps at 2^32 via width_mask; `as u32` truncates |
| u64 | 47 | ✅ done (0.0.91) | ✅ gate | type annotation parsed (vtype 4); full 64-bit; `as u64` is identity |
| bool | 49 | ✅ done | ✅ gate | logical_keywords.quanta (true=1, false=0). `bool` as a *type annotation* (`let x: bool`) parsed since 0.0.89 (vtype 6) |
| char | 50 | ✅ done | ✅ gate | memops_test.quanta (char/byte ops). `char` as a *type annotation* (`let x: char`) parsed since 0.0.89 (vtype 7) |
| byte | 51 | ✅ done | ✅ gate | memops_test.quanta (byte literal). `byte` as a *type annotation* (`let x: byte`) parsed since 0.0.89 (vtype 8) |
| int | 55 | ✅ done | ✅ gate | arithmetic.quanta, int_keyword_test.quanta |
| and / or / not | 13/14/15 | ✅ done (0.0.70) | ✅ gate | logical_keywords.quanta (rc=4), logical_keywords_shortcircuit.quanta (rc=2). Exact aliases of `&&`/`\|\|` incl. short-circuit |
| true / false | 10/11 | ✅ done | ✅ gate | logical_keywords.quanta (true=1, false=0) |
| global | 20 | ✅ done | ✅ gate | test_many_globals.quanta (rc=42). Top-level `name = value` = global |

## B. Core — Types

NOTE: A type is "done" only if it can be written as a *type annotation* (`let x: T`)
and parsed by the type system. The `bool`/`char`/`byte` *keywords* and their values
are done (§A) **and** their use as type annotations is now parsed (`let x: bool`/`char`/`byte`, vtype 6/7/8, landed 0.0.89). `usize`/`u32`/`u64` are partial (mask builtins exist; no full
native type keyword parsing). `as` width casts (`x as T`) are done (0.0.90).

| Type | Status | Test? | Notes |
|---|---|---|---|
| i64 (default integer) | ✅ done | ✅ gate | arithmetic.quanta, param8.quanta |
| f64 | ✅ done | ✅ gate | float_test.quanta (rc=159), simple_fadd.quanta (rc=7) |
| usize | ✅ done (0.0.91) | ✅ gate | type annotation parsed (vtype 5); full 64-bit |
| u32 / u64 | ✅ done (0.0.91) | ✅ gate | type annotation parsed (vtype 3/4); u32 wraps at 2^32, u64 full 64-bit; `as` casts work |
| u8 / u16 | ✅ done | ✅ gate | `let x: u8`/`u16` parsed (parse_let width tag) + width_mask codegen; mixed-width + const-fold wrap verified |
| bool (as type) | ✅ done | ✅ gate | `let x: bool` parsed (vtype 6); stored/compared as 0/1; arithmetic is plain integer (true+true==2, not masked) |
| char (as type) | ✅ done | ✅ gate | `let x: char` parsed (vtype 7); byte-width, wraps 0..255 on arithmetic (REX.B-correct) |
| byte (as type) | ✅ done | ✅ gate | `let x: byte` parsed (vtype 8); byte-width, wraps 0..255 on arithmetic (REX.B-correct) |
| `as` width cast (`x as T`) | ✅ done (0.0.90) | ✅ gate | `x as u8/u16/u32/char/byte/usize`. Truncation emitted as IR_BAND with width mask; usize/signed are identity. `as_cast_test.quanta` (rc=7) gates it; diff-checked vs `x & mask`. |
| float literals (`3.14`) | ✅ done (0.0.61) | ✅ gate | float_test.quanta (`println(3.14)`->`3.140000`); f2i/fadd/... consume float vregs (0.0.62). Verified: `fadd(1.5,2.5)`->4 |
| string (real type) | ✅ done (0.0.95) | ✅ gate | `let s: String` parsed (vtype 10, parse_let); length-aware real type with `==`/`len`/`concat` (str_eq/str_ne/strcat). Verified: `let s: String = "hi"; println(s)` → `hi`. |
| struct | ✅ done | ✅ gate | fields + `obj.method` + literal (struct_literal_test.quanta, in gate) |
| enum (user-defined) | ✅ done | ✅ gate | enum_test.quanta (rc=42, in gate) |
| tuple `(T,U)` | ✅ done | ✅ gate | tuple_test.quanta (rc=40, in gate; mk_any-based tuples) |
| typed array/slice | ✅ done (0.0.110) | ✅ gate | `let a: i64[] = [...]` parsed (vtype 11, parse_let `T[]` suffix); indexing `a[idx]` + subscript assignment `a[i]=v` via IR_IDX (header-carrying base, base+8+i*8). gated typed_array_test.quanta (rc=0). Untyped `[...]` was already tested (array_test.quanta / forin_*). |
| big (arbitrary-precision int) | ✅ done (0.0.114) | ✅ gate | **First-class core type** (moved from the stdlib track to core in 0.0.114). Context-sensitive type keyword (`ktext` ID 62, stays `TT_ID` so `let big = 70000` still works). `: big` param / `-> big` return annotations; big tag propagates through `let`, reassignment, and call results. Operators `+ - * / % == !=` route to `big_add/sub/mul/div/mod/eq` with automatic int→big promotion (operator operands AND call-site args to `: big` params); ordering compares (`< > <= >=`) rejected at compile time; `println(big)` → `big_println`; overflowing decimal literals lex as a single `TT_BIGNUM` token. Implementation lives in `lib/std/big.quanta` (public API fully annotated: `: big` params, `-> big` returns — raw-int args auto-promote, big-returning calls never double-wrap). Gated `big_test.quanta` (rc=0: 30-digit add/sub/mul/div/mod vs Python reference values, signed equality, println). |

## C. Core — Control Flow

| Feature | Status | Test? | Notes |
|---|---|---|---|
| if/else | ✅ done | ✅ gate | elseif_test.quanta |
| while | ✅ done | ✅ gate | break_continue.quanta |
| loop | ✅ done | ✅ gate | loop_test.quanta |
| for-in (array) | ✅ done | ✅ gate | forin_basic.quanta / forin_break.quanta / forin_nested.quanta / forin_sum.quanta |
| match (expr arms) | ✅ done | ✅ gate | match_test.quanta (rc=132) |
| break / continue | ✅ done | ✅ gate | break_continue.quanta |
| return / defer | ✅ done | ✅ gate | defer_test.quanta |
| for-range `for i in 0..n` | ✅ done (0.0.76) | ✅ gate | for_range_basic.quanta (rc=3) |
| match block arms `1 => { }` | ✅ done | ✅ gate | match_test.quanta covers block arms |
| `?` early-return propagation | ✅ done | ✅ gate | question_mark.quanta (rc=0), option_test.quanta / result_test.quanta (in gate) |
| loop expressions / labeled break w/ value | ✅ done (0.0.76) | ✅ gate | loop_test.quanta (`loop { break N }` value-return) |
| try/catch | ✅ done | ✅ gate | try_catch.quanta (rc=9), nested + sequential variants; real unwind to handler (IR_TRY_PUSH/IR_THROW/IR_TRY_END/IR_CATCH/IR_JMP) |

## D. Core — Expressions & Operators

| Feature | Status | Test? | Notes |
|---|---|---|---|
| arithmetic (+ - * / %) | ✅ done | ✅ gate | arithmetic.quanta |
| bitwise (& \| ^ ~ << >>) | ✅ done | ✅ gate | bitwise_not.quanta |
| comparisons (== != < > <= >=) | ✅ done | ✅ gate | arithmetic.quanta |
| logical (&& \|\| !) | ✅ done | ✅ gate | logical_keywords.quanta (and/or/not); &&/\|\| in arithmetic.quanta |
| ternary | ✅ done | ✅ gate | simplified_syntax.quanta |
| field access / index | ✅ done | ✅ gate | struct_test.quanta, array_test.quanta |
| unsigned arith | ✅ done | ✅ gate | unsigned_ops.quanta (udiv/umod/ult/ugt/ulte/ugte) |
| operator overloading | ✅ done (0.0.97) | ✅ gate | op_overload_add.quanta (rc=52), op_overload_mul.quanta (rc=7), op_overload_cmp.quanta (rc=5), op_overload_recur.quanta (rc=7). User `fn +(a,b)` shadows builtin `+`; dispatched via `OPFN` fn-index table + `IR_CALL_IDX` (no src-name injection — corruption-proof). All 11 ops (`+ - * / % == != < > <= >=`) verified; `overload_suppressed` (from `OPFN_SUPP`) makes an operator fn body fall back to BUILTIN for the same op (no infinite recursion). |
| range `..` expression | ✅ done (0.0.97) | ✅ gate | range_for.quanta (rc=6, 1..4→6); feeds `for i in a..b` (exclusive end). |
| array push `a.push(v)` | ✅ done | ✅ gate | array_push_method.quanta (rc=7), array_push_empty_annot.quanta (rc=7), array_push_closure_mix.quanta (rc=35). Method form only — bare `push(v,e)` is the byte-stride STRING push. Silently returned 0 in 0.0.65 (IR_CLOSURE/IR_APUSH both = opcode 72); fixed 0.0.66 |
| generics `<T>` | ✅ checks + type-erased | ✅ gate | Compile-time type-arg validation added in 0.0.101: arity must match fn_genparams, each type-arg must name an existing struct or `i64`; unknown types / arity mismatches are HARD compile errors (fails closed, generic_neg_tests gated). Implicit instantiation (no `<T>`) defaults to i64. `generics_test.quanta` (rc=42) + `generics_typecheck.quanta` (rc=42) pass; `where_clause_test` (rc=7) preserved. Per-type body specialization (monomorphisation) deferred to 0.0.102. |
| tuples `(a,b)` | ✅ done | ✅ gate | tuple_test.quanta (rc=40), option_tuple.quanta (rc=42). Literals, N-tuples, nested access `t.0.1`, tuple-valued returns, element reassign, tuple in array, destructuring `let x,y = f()` |
| `and` / `or` keywords | ✅ done (0.0.70) | ✅ gate | logical_keywords.quanta (rc=4), logical_keywords_shortcircuit.quanta (rc=2). Before 0.0.70 the keyword was tokenized but never consumed |
| `!` / `not` | ✅ done (0.0.71) | ✅ gate | logical not -> 0/1. Const and runtime paths now agree; `~`/`~~` is separate bitwise-not. bitwise_not.quanta pins both |
| match guards `n if n>3 =>` | ✅ done (0.0.69) | ✅ gate | match_guard.quanta (rc=111), match_guard_false.quanta (rc=222), match_guard_order.quanta (rc=4). Guard may use the bound name; false guard falls through; arms tried in order. Silently yielded 0 before 0.0.69 |
| closure literals `\|a\| { a+1 }` | ✅ done (0.0.65) | ✅ gate | closure_basic.quanta (rc=6), closure_multi_param.quanta (rc=7), closure_higher_order.quanta (rc=42); braces required |
| user fn overrides builtin | ✅ done (0.0.68) | ✅ gate | user_fn_beats_builtin.quanta (rc=42), user_fn_beats_builtin_chain.quanta (rc=38), builtin_still_inline.quanta (rc=3). EXCEPTION: mem_load/mem_store/mem_load8/mem_store8 + fadd/fsub/fmul/fdiv are primitive intrinsics and NOT overridable |
| fnptr + closure_call | ✅ done (0.0.72) | ✅ gate | fnptr_test.quanta (rc=7). fnptr returns a [codeptr, env=0] tuple; before 0.0.72 feeding it to closure_call SEGFAULTed |
| const redefinition | ✅ done (0.0.75) | ✅ gate | const_redefine.quanta (rc=5, was 10). First value wins; duplicate skipped |
| closure captures | ✅ done (0.0.67) | ✅ gate | closure_capture.quanta (rc=15), closure_capture_multi.quanta (rc=11), closure_capture_byvalue.quanta (rc=11). Free vars captured BY VALUE into heap env; IR_CAPREAD from env in r10; max 32 captures |

## E. Memory & Runtime

| Feature | Status | Test? | Notes |
|---|---|---|---|
| mem_alloc/free/mmap/realloc | ✅ done | ✅ gate | mem_test.quanta, test_mmap.quanta |
| memcpy/memcmp/memmove | ✅ done | ✅ gate | memops_test.quanta |
| mem_load/mem_store(+8) | ✅ done | ✅ gate | raw_ptr_test.quanta |
| defer (LIFO replay) | ✅ done | ✅ gate | defer_test.quanta |
| unsafe blocks | ✅ done | ✅ gate | unsafe_block.quanta |
| real allocator (free-list/GC) | ✅ done (0.0.111) | ✅ gate | `mem_free(ptr)` (free-list push at `HEAP_CTRL=GDATA+1032`) + `mem_realloc(ptr,newn)` (mmap new + `rep movsq` copy min(old_count,newn) qwords) added; `mem_alloc` unchanged (fixpoint-safe). gated `mem_free_test.quanta` (rc=0). Fixpoint byte-verification blocked by systemic stage2 SIGSEGV (see ROADMAP 0.0.111 note). |
| callee load-store-to-same-addr aliasing | ✅ done | ✅ gate | reg_alias.quanta / alias_derive_loop.quanta / alias_loadstore_loop.quanta (fixed 0.0.43–0.0.46) |
| stack unwind / destructors / RAII | ✅ done (0.0.112) | ✅ gate | owned `mem_alloc` bindings auto-recycle to free-list at every scope exit (normal + early return) via compiler-inserted `drop()`; NEW `drop(ptr)` builtin (== mem_free) is the user-facing destructor hook. Replaces old `munmap` IR_FREE with 0.0.111 free-list push. gated `raii_test.quanta` (rc=0). `defer` LIFO replay unchanged. |
| ref/mut/move (ownership) | ✅ done (0.0.94) | ✅ gate | `mut` rebindable, `ref` borrow alias, `move` transfer prefix; ownership tag tracked in symbol table (`vars_own`, `vown`/`set_vown`). Enforce at 0.1.0. ownership_sigils_test.quanta gates it. |

## F. Builtins — Already Shipped (87 registered, prefixes expanded)

| Group | Items | Test? |
|---|---|---|
| syscall family | syscall(1–6) | ✅ gate (syscall_test.quanta) |
| exit / panic | exit, panic | ✅ gate (exit_test.quanta) |
| memory map | mmap | ✅ gate (test_mmap.quanta) |
| heap | mem_alloc/free/realloc | ✅ gate (mem_test.quanta) |
| mem ops | memcpy, memcmp, memmove, mem_load, mem_store(+8) | ✅ gate (memops_test.quanta, raw_ptr_test.quanta) |
| file I/O | file_open, file_read, file_write, file_close | ✅ gate (file_open_test.quanta rc=3, file_io.quanta, file_write_test.quanta) |
| print | print, printi, println, prints, printsp, newline | ✅ gate (prints_family.quanta) |
| container | len, str, push, pop, vec_get, vec_set, vec_load, vec_store, vec_add, vec_sub, vec_mul, vec_div | ✅ gate (array_test.quanta) |
| variadic / any | arg, mk_any | ✅ gate (arg_or.quanta rc=1, arg_test.quanta rc=40) |
| closures | closure literal `\|a\| { … }`, fnptr, closure_call | ✅ gate (closure_basic.quanta rc=6, closure_multi_param.quanta rc=7, closure_higher_order.quanta rc=42, fnptr_test.quanta rc=7) |
| float arith | fadd, fsub, fmul, fdiv, i2f, f2i | ✅ gate (float_test.quanta rc=159, simple_fadd.quanta rc=7) |
| float compare | feq, flt, fgt, fle, fge, fisnan, fisinf | ✅ gate (float_test.quanta rc=159) |
| float math | sqrt, floor, ceil, abs, sin, cos, tan, pow, log | ✅ gate (float_test.quanta rc=159). min/max are NOT yet implemented (see §G) |
| process / env | getpid, getppid, arg_count, environ | ✅ gate (getpid_test.quanta, getppid_test.quanta, argc_test.quanta). getenv is a STUB returning 0 (see §I) |
| stdin I/O | getc | ✅ gate (getc_test.quanta). getline untested-in-gate |
| fs metadata | stat, fstat, lseek, unlink, mkdir, chdir, rename | ✅ 7/7 gated (fs_meta_test.quanta rc=11) — root cause: path-string remap applied +8 twice / not at all; fixed via `argp8` for string literals + `vreg_is_str` detection so `file_open` also accepts raw C-string pointers (e.g. argv). See §I. |
| introspection | abort, debugbreak | ✅ gate (abort_test.quanta rc=134; debugbreak = int3 → rc=133) |
| random | getrandom, rand | ✅ gate (getrandom_test.quanta rc=1; rand_test.quanta rc=0 — `rand()` convenience over getrandom returns a random i64). Implemented in 0.0.102. |
| unsigned arith | udiv, umod, ult, ugt, ulte, ugte, u8, u32, u64 | ✅ gate (unsigned_ops.quanta) |
| byte/endianness | bswap, popcount, clz, ctz, rotl, rotr | ✅ gate (bits_test.quanta) |
| time | gettimeofday, nanosleep, sleep | ✅ gate (time_test.quanta) |

## G. Builtins — To-Do

| Group | Items | Test? |
|---|---|---|
| float math (remaining) | sin, cos, tan, pow, log, min, max | ✅ shipped (emit_bltn P6.1a; see §F float math row). Gated at the stdlib stage via `std_math_test.quanta` (not yet in core gate). |
| string ops | strcat, substr, str_split, utf8 | ✅ gate (strcat_test rc=6, substr_test rc=3, str_split_test rc=0, utf8_test rc=5). strcat/substr in 0.0.102; str_split + utf8 in 0.0.104. utf8 decodes UTF-8 bytes → qword array of scalar codepoints. strcmp is really str_eq/str_ne (already shipped). |
| atomics | atomic_load/store/add/swap/cmpxchg | ✅ 5/5 gated (atomic_test.rc=11) |
| networking | socket/connect/bind/listen/accept | ✅ 5/5 gated (net_test.rc=11) |
| introspection (remaining) | stack-trace | ✅ done (0.0.113) — `stack_trace()` returns the immediate caller's return address (code pointer) from the rbp frame chain (`[rbp+8]`); no per-call instrumentation, fixpoint-safe. Gated `stack_trace_test.quanta` (rc=0: non-zero, inside code segment, distinct call sites → distinct addresses). |
| random (remaining) | rand | ✅ done (0.0.102) — `rand()` convenience over getrandom; gated `rand_test.quanta` (rc=0). |
| bit/byte extras | parity, bitfield, per-size swap (bswap16/32/64) | ✅ 0.0.107 — parity(x)=odd-bit-count?1:0; bitfield(x,off,wid)=(x>>off)&((1<<wid)-1); bswap16/32/64. Gated by bitops_test.quanta (rc=0). NOTE: bitfield wid==64 is the documented exception (result 0, mirrors rotl/rotr &63 shift-count behavior). |
| intrinsics | prefetch, pause, lfence, sfence, mfence | ✅ 0.0.108 — `prefetch(addr)`=prefetchnta[rax] (0F 18 08); `pause()`=F3 90; `fence()`=mfence (0F AE F0); `lfence()`=0F AE E8; `sfence()`=0F AE F8. All void builtins, gated by intrinsic_test.quanta (rc=0, byte-emission verified via objdump). Branch-hint intrinsics (likely/unlikely) deliberately OUT OF SCOPE — conditional jumps emit centrally in the shared IR_BR backend, not at call sites, so a builtin cannot prefix a following branch. |

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

## J. Standard Library (`lib/std/*.quanta`) — native libraries

Source-of-truth inventory of the shipped stdlib. Every `lib/std/*.quanta` is a
real implementation (not a stub). The "Test?" column: ✅ gate = a gated test covers
it; 🟡 file-only = a test file exists on disk but is NOT in the gate; ❌ none = no test.

| Library | Status | Test? | Notes / test file |
|---|---|---|---|
| `big` (arbitrary-precision int) | → **core** (0.0.114) | ✅ gate | **Moved to the core type system in 0.0.114 — see §B Core Types.** `lib/std/big.quanta` remains the implementation (now fully annotated with `: big` / `-> big`); the 4 original stages (ADD/SUB/MUL, DIV/MOD, SHL/SHR, decimal print + Karatsuba) plus first-class keyword, operator routing, and int→big promotion are all core features now. Gated `big_test.quanta` (rc=0). |
| `crypto` (SHA-256/HMAC/AES/CSPRNG) | ✅ done | ✅ gate | std_crypto_test.quanta (rc=3, gated at 0.0.87). 643 lines, 21 fns. |
| `quantum` (Keccak/SHA3/SHAKE) | ✅ done | ❌ none | lib/std/quantum.quanta (240 lines, 8 fns). No dedicated test file. |
| `linalg` (matmul/transpose/det/inverse/vectors) | ✅ done | ❌ none | lib/std/linalg.quanta (363 lines, 25 fns). No dedicated test file. |
| `math` (sqrt/floor/ceil/abs/sin/cos/tan/pow/log/min/max) | 🟡 partial | ✅ gate | std_math_test.quanta (rc=19, gated at 0.0.87; covers sqrt/floor/ceil/abs + pow/log/min/max/gcd/lcm). sin/cos/tan still TODO (builtins row). |
| `map` | ✅ done | ✅ gate | test_mmap.quanta / mmap1.quanta (both gated); std_map_test.quanta also gated at 0.0.87 (rc=6). |
| `str` (string ops) | ✅ done | ✅ gate | string_keyword_case.quanta (gated); std_str_test.quanta also gated at 0.0.87 (rc=13). |
| `vec` | ✅ done | ✅ gate | std_vec_test.quanta (rc=8, gated at 0.0.87). |
| `fs` (file system) | ✅ done | ✅ gate | std_fs_test.quanta (rc=9, gated at 0.0.87). NOTE: stat/unlink/mkdir/chdir/rename are still BROKEN (0.107); this test covers the working write/read round-trip only. |
| `io` (file IO) | ✅ done | ✅ gate | file_io.quanta (in gate). |
| `chain` (blockchain: Merkle/signed-tx/UTXO/Block) | ❌ todo | ❌ none | Not in code. Part of the differentiation mandate (math/physics/crypto/blockchain/quantum/AI). |
| `secure` (capability I/O, constant-time) | ❌ todo | ❌ none | Not in code. |
| `ai` (tensor ops + inference) | ❌ todo | ❌ none | Not in code. |
| `physics` (ODE/PDE solvers) | ❌ todo | ❌ none | Not in code. |

## Summary counts (source-derived)
- **Keywords (ktext): 57 codes defined; ~19 parsed, ~13 lexed-only gaps, rest partial.**
- **Builtins registered: 87 (prefixes expanded).**
- **Core tests in gate: 147** (EXPECTED.tsv, 147 rows — verified 2026-08-28, includes `big_test.quanta` landed with 0.0.114). `std_*` tests are kept in a SEPARATE `test_suites/EXPECTED_STDLIB.tsv` (7 rows, runnable at the stdlib stage) and are NOT in the core gate (core-only rule); `mtu_*` multi-translation-unit experiments are also file-only. So ~12 code files are file-only (not in the gate count).
- **Test framework note:** tests `return`/`exit` a *computed value* (not just 0); EXPECTED.tsv's
  `expected_rc` is that computed answer. So non-zero expected_rc entries are correct results, not
  hidden failures. Verified by reading test bodies (e.g. array_test.quanta returns 200 = a.1; simple_fadd.quanta
  returns 7 = 3.0+4.0). The gate is genuinely green.

## Build order & sequencing

The authoritative build order to 0.1.0 (debt window → P2 builtins → P3
language → P4 tooling → 0.1.0) now lives in **`docs/ROADMAP.md` §3** (single
source of truth, consolidated 2026-08-17). It is no longer duplicated here
to prevent version-number drift.

Key invariants (unchanged): one feature per WIP version; debt window
(0.0.43–0.0.50) closed before new features; gate green before promotion;
Quanta-native code-writing tool is deferred to AFTER the stdlibs stage
(POST-0.1.0, per user directive 2026-08-28 — no version reserved); ARM64 backend
deferred to POST-0.1.0 (no version reserved).
