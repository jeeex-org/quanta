# Quanta Language Specification (v0.0.55)

> Status: DRAFT / WORKING SPECIFICATION. Derived from the self-hosting
> compiler source at `compiler/0.0.55/` (x86-64 native AOT; AArch64 backend planned POST-1.0).
> This document is the authoritative definition of Quanta semantics for
> the purpose of tool qualification (ISO/IEC 26262-8, IEC 61508-3).
> Where the prose and the compiler diverge, the compiler is currently
> authoritative and the discrepancy is a SPEC BUG to be filed.

Last updated: 2026-08-22. Scope: native AOT backend (x86-64; AArch64 backend planned POST-1.0).
Interpreter/JIT/WASM backends are NOT specified here (see LANGUAGE_DESIGN.md
Stages 1/3/5 — not yet built).

---

## 1. Lexical structure

### 1.1 Tokens
- **Identifiers**: `[A-Za-z_][A-Za-z0-9_]*` (keywords are a subset; the lexer
  resolves keywords by djb2 hash fold — see §1.3).
- **Int literals**: decimal `[0-9]+`, hex `0[xX][0-9a-fA-F]+`.
  Negative integers are encoded as unary-minus applied to a positive literal
  (`-5` = `unary_minus(5)`); there is no negative-int token.
- **Char literals**: `'<c>'` where `<c>` is any single char or escape `\<x>`
  (e.g. `'v'`, `'\n'`). Used in comparison chains (e.g. `r8(nm)=='v'`).
- **String literals**: `"..."` with `\` escapes.
- **Comments**: `//` to end-of-line, `/* ... */` block, `#` to end-of-line.
  Comments are whitespace for the purpose of token separation.
- **Statement separator**: BOTH `;` and newline separate statements. `;` is
  optional; a `let`/`return`/expression statement may be newline-terminated.
  (Verified: grammar `tree-sitter-quanta` parses all 15 module files with
  0 errors at v0.0.53.)

### 1.2 Operators (precedence, high→low)
| Precedence | Operators | Assoc |
|-----------|-----------|-------|
| 1 (highest) | unary `!` `~` `-` | right |
| 2 | `*` `/` `%` `&` `<<` `>>` | left |
| 3 | `+` `-` `\|` `^` | left |
| 4 | `==` `!=` `<` `>` `<=` `>=` | none |
| 5 | `&&` | left |
| 6 | `\|\|` | left |
| 7 (lowest) | `=` (assignment) | right |

`=?` is the `?` propagation operator (IR_TRY early-return on Err/None).
Assignment (`=`) binds LESS tightly than binary operators, so `a = b + 1`
parses as `a = (b + 1)`, not `(a = b) + 1`. (Precedence verified by grammar
at v0.0.53 after the assignment-vs-binary conflict was resolved.)

### 1.3 Keyword hashing (lexer contract)
Keywords are NOT matched by string compare in the hot path; the lexer folds
each identifier through a djb2-style hash:
`h = (((c0*31 + c1)*31 + c2) ... )` and compares the integer.
**The hash constants are a STABLE CONTRACT.** At v0.0.53 the following were
verified paren-balanced (a prior imbalance caused silent wrong-hash bugs,
fixed in 0.0.53):
- `H_ENUM` (enum), `H_MATCH` (match), `H_MUT` (mut), `H_MOVE` (move),
  `H_REF` (ref), `H_TYPE` (type), `H_INTERFACE` (interface),
  `H_OK` (Ok), `H_ERR` (Err), `H_STRING` (string), `H_RAW` (raw),
  plus single-char/short hashes `H_CHAR`, `H_BYTE`, `H_BOOL`.
Any change to a keyword spelling MUST update the corresponding `H_`
constant with a balanced paren fold; an imbalance is a silent lexer
correctness defect (see SAFETY_MANUAL.md §4.1).

---

## 2. Syntax (grammar summary)

Program = sequence of top-level items:
- `fn` decl, `struct` decl, `enum` decl, `interface` decl, `impl` decl,
  `extern "C"` decl, `alias` decl, `let` (global), `const`, `unsafe` block,
  `defer` stmt, bare expression statement, `include` directive.
- **`fn` is OPTIONAL**: a top-level `name(params) { body }` is a function
  definition with or without `fn`. (SIMPLE-SURFACE: the compiler rewrites
  bare `name(){}` to `fn name(){}` before parsing; `init()`/`main()` bare work.)
- **`let` is OPTIONAL**: a top-level `name = expr` declares a global; a
  bare `name = expr` inside a function declares/assigns a local. `global name`
  marks a writable global, `const name` a read-only one.
- **`return` is OPTIONAL**: the last expression of a function body is its
  return value (early `return` still available).
- Condition parentheses are optional: `if cond`, `while cond`, `for ...`.

Statement (block-internal):
- `let [mut] name [: type] = expr [;]`   (or bare `name = expr`)
- `return [expr] [;]`                     (or implicit: last expr)
- `if cond { ... } [else if ...] [else { ... }]`   (`cond` parens optional)
- `while cond { ... }`, `for`, `loop`
- `match expr { arm => stmt|block, ... }`
- `break [;]`, `continue [;]`, `defer expr`, `unsafe { ... }`
- bare `{ ... }` block (scoping), bare expression (call) `[;]`

Variable references (disambiguate scope explicitly):
- `${name}` — read a **global** (resolves via the global table; undeclared →
  compile error). Writing `${name} = x` is forbidden.
- `$[]` — read a **local** (resolves to the current function's local;
  undeclared → compile error). Writing `$[name] = x` is forbidden.
  Both forms work bare (combined with `..`) and inside string literals.

Expressions: primary (ident, int, char, string, bool, `( )`, array,
Option/Result literals), unary, binary, call `f(a,b)`, index `a[i]`,
field `a.b`, assignment `a = b`, closure, `mk_any`.

(Exact grammar: `tree-sitter-quanta/grammar.js`. All 15 compiler modules
parse with 0 errors at v0.0.53.)

---

## 3. Type system (current)

- **Scalars**: `i64` (default integer), `u64`, `u8`, `u32`, `f64` (float ops
  exist in IR; float literals/syntax land in a later version per ROADMAP).
- **Composite**: `struct` (value type, field access `.`), arrays
  (`[T]` heap-allocated via `mem_alloc`, index `a[i]` with bounds trap),
  `Option<T>` (`Some`/`None`), `Result<T,E>` (`Ok`/`Err`).
- **Mutability**: `let` is immutable by default; `let mut` allows reassignment.
- **No implicit numeric conversions**; casts are explicit builtins
  (`u8`/`u32`/`u64`/`i2f`/`f2i`).
- **Generics**: `optional($.generic_params)` syntax exists; full generic
  instantiation is a later-stage feature.

---

## 4. Memory model (CRITICAL for safety)

Quanta's native backend emits raw machine code with **manual memory
management**. This is the primary safety-relevant surface.

### 4.1 Manual regions
- **Code buffer**: `mmap(33554432)` (32 MB) at a NULL hint; grows by
  appending emitted bytes (`codelen` cursor).
- **Patch buffer**: `mmap(8000000)` (8 MB) for deferred relocations.
- **GDATA**: fixed-base global data region (x86: `0x42200000`).
- **Heap**: `mem_alloc(n)` / `mem_free(p)` builtins over `mmap`.

### 4.2 Runtime traps (fail-closed, not prove-safe)
The compiler inserts traps so that out-of-contract operations FAIL SECURE
rather than corrupt silently:
- **Integer overflow**: `ud2` -> SIGILL, process exit rc=132.
  Opt-out: `unsafe { }` block (the overflow trap is suppressed inside
  `unsafe`; the `ir_unsafe` flag gates this — verified in self-host).
- **Out-of-bounds array access**: `a[idx]` with `idx >= len` (or negative,
  read as huge unsigned) falls through to `ud2` -> SIGILL rc=132. Also
  suppressed inside `unsafe{}`.
- **Stack/heap exhaustion**: `mmap` failure is checked (see §4.3).

### 4.3 `mmap` failure handling (fail-closed — ADDED 0.0.49)
Every `mmap` call site (code buffer, patch buffer, GDATA, `mem_alloc`,
spill regions) checks the return: on `MAP_FAILED` (rax < 0) the compiler
aborts with exit code **1** (was: unchecked -> SIGSEGV rc=139 under
`ulimit -v`). This is the defined fail-closed behavior for OOM.
(Verified: `ulimit -v 60000 ./qc ...` -> rc=1, not 139.)

### 4.4 Bounds-check elision
Bounds checks may be elided inside `unsafe{}` (parity with Rust's unsafe).
The `unsafe` block count is reported at compile time ("N unsafe block(s)
parsed") as an audit signal.

---

## 5. IR contract (stability boundary)

All backends agree on IR semantics. Ops (from `main.quanta`, IRS=40-byte
record): CONST, MOV, ADD, SUB, MUL, DIV, MOD, NEG, NOT, BNOT, AND, OR,
BAND, BOR, BXOR, EQ, NE, LT, GT, LE, GE, SHL, SHR, LOADG, STOREG, LOAD,
STORE, CALL, RET, LABEL, JMP, BR, PARAM, STR, FREE, ASM, FFI_CALL, plus
float ops and ownership ops (IR_FREE for compiler-inserted free).

Security gates (overflow trap, bounds trap, unsafe opt-out) are IR-level
properties, so every backend inherits them by construction.

---

## 6. Compilation & execution model

- **Self-hosting**: the compiler is written in Quanta and bootstraps via
  `qc-bootstrap-0.0.45` seed: 3-stage (`qc_boot -> qc_self -> qc`),
  byte-identical fixed point (verified at v0.0.53).
- **Output**: ELF (x86-64 / AArch64) emitted with mode `0755` (executable)
  via `file_open(path, O_WRONLY|O_CREAT|O_TRUNC, 0755)`.
- **Exit codes**: 0 = success; 1 = internal/memory failure (MAP_FAILED);
  7 = compile error (undelegated fn, cyclic struct, etc.); 132 = runtime
  overflow/bounds trap (SIGILL).

---

## 7. Open specification gaps (tracked)

1. Formal denotational/operational semantics for the IR (currently defined
   by emitter behavior, not axioms).
2. Float literal syntax (`3.14`) is still NOT parsed (lexer hard-errors). The
   `feq`/`flt`/`fgt`/`fle`/`fge`/`fisnan`/`fisinf` comparison builtins and
   `sqrt`/`floor`/`ceil`/`abs` math builtins ARE shipped at 0.0.55 (operate on
   f64 bit-patterns via `i2f`/`f2i`); see §6 and `float_test.quanta`.
3. Generic instantiation semantics (syntax present, instantiation deferred).
4. `match` exhaustiveness rules (parser accepts; semantic exhaustiveness
   check not yet specified).
5. Concurrency / atomics memory model (atomics builtins land later).

These gaps are QUALIFICATION BLOCKERS for ISO/IEC 26262 ASIL C/D and
IEC 61508 SIL 3/4 until closed. See SAFETY_MANUAL.md §6.

---

## 8. Version

Spec corresponds to compiler `0.0.55` (commit chain `...4653d32`).
Update this document in lockstep with any semantic change; every change
MUST reference the committing version and the test that proves it.
