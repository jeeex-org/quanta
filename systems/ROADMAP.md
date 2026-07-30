## 1. Identity

Quanta is a self-hosting systems programming language: one source language that
compiles to every tier — bare-metal kernel, edge WASM, GPU kernel, cloud service.

| Property | Value |
|----------|-------|
| **Self-hosting** | Compiler in Quanta; byte-identical fixed-point on x86-64 |
| **Bootstrapping** | `qc-bootstrap-0.0.0` seed binary |
| **Version** | `qc-0.0.6` (bare Some/None/Ok/Err + enum/match; x86_64 self-host verified; ARM64 bare-variant bug) |
| **Optimizer** | Tier-1 IR passes (const fold, DCE, tail-call, loop strength), ON by default since 1.0.12 |
| **Memory model** | Ownership-by-default (compiler-inserted `free` at scope exit), no GC |
| **Secure by default** | Overflow/shift/bounds traps ON; `unsafe {}` marks opt-out regions |
| **Tests** | 39 exit-code–gated tests, deterministic, full regression on every change |

---


## 2. Language Syntax

### 2.1 Program structure

```
<program>  ::= { <function-def> | <struct-def> }
```

Execution starts at `fn main()`; return value is the process exit code
(default `0` if no explicit `return`).

> **P6 status:** `enum` and `match` **implemented (qc-0.0.4)**; `trait`, `impl`, generics `<T>` tokens exist but parser/codegen NOT wired. Examples below describe target syntax.

### 2.2 Functions

```
fn name(p1, p2, ...) -> type { statements }
```

- Up to 6 args in registers (SysV: rdi, rsi, rdx, rcx, r8, r9); args 7+ on stack.
- Return type annotation optional and advisory (`-> int`).
- All functions top-level. Forward references allowed.
- Variadic: `fn f(a, b, ...)` — use `argc()` / `arg(i)`.
- Default args: `fn f(a, b = 8, c = 9)` — omitted trailing args fill defaults.
- Named args: `f(b: 2, a: 1)`.
- Multi-return: `return a, b, c` → packs tuple; `let x, y = f()` destructures.

```
fn add(a, b) -> int { return a + b }
fn f(a, b = 8, c = 9) { return a + b + c }
fn main() { let x, y = divmod(17, 5); return x }  // x=3
```

### 2.3 Methods

```
obj.method(args)      // desugars to method(obj, args...)
```

`self` is convention (first param receives object). No receiver-type check.

```
fn area(self) { return self.w * self.h }
let r = (3, 4); return r.area()    // 12
```

### 2.4 Structs

```
struct Name { f0, f1: TypeA, f2: TypeB }
```

- Constructor: `Name(a, b, c)` — IR_TALLOC + field stores.
- Field access: `obj.field` — compile-time field index.
- `: Type` annotation marks nested structs for chain access.
- Chain: `obj.field.subfield`.

```
struct Point { x y }
fn make(a, b) { return Point(a, b) }
fn main() { let p = make(3, 4); return p.x + p.y }  // 7
```

### 2.5 Enums (implemented qc-0.0.4)

```quanta
enum Color { Red, Green, Blue }
let c = Color.Red
```

### 2.6 Match (implemented qc-0.0.4 for enum patterns)

```quanta
match c {
    Color.Red => 1,
    Color.Green => 2,
    Color.Blue => 3,
}
```

### 2.7 Option / Result (built-in enums; bare constructors compile but match limited)

```quanta
let x = Some(42)
let y: Option<int> = None

fn divide(a, b) -> Result<int, string> {
    if b == 0 { return Err("div by zero") }
    return Ok(a / b)
}
```
- `Option` and `Result` are built-in enum types with compiler support for `Some`/`None` and `Ok`/`Err` constructors.
- **Note**: Bare `Some(val)`, `None`, `Ok(val)`, `Err(val)` expressions compile but pattern matching on them requires the `match` implementation (qc-0.0.4+). Currently they work as expressions but `match` on built-in enum variants is partially implemented.
- See `option_test.quanta` / `result_test.quanta` for status.

### 2.8 Generics (P6 WIP — not wired)

```quanta
fn first<T>(arr: [T]) -> T { return arr[0] }

fn map<T, U>(arr: [T], f: fn(T) -> U) -> [U] {
    let result = [U]()
    for item in arr { result.push(f(item)) }
    return result
}
### 2.10 Associated Types & Where Clauses
Not yet implemented.

```
let x = 10            // new binding
x = x + 1             // assign to existing
```

`let` shadows previous bindings (newest wins). Type inferred from RHS.

### 2.11 Control flow

```
if cond { ... } else if cond { ... } else { ... }
loop { ... break continue }
while cond { ... }
for i = start; cond; step { ... }
```

- `cond` truthy when non-zero.
- `&&`, `||`, `and`, `or` short-circuit.
- `break`/`continue` target innermost loop.

### 2.12 Operators (precedence low→high)

```
||  or            (short-circuit)
&&  and           (short-circuit)
|   ^   &
==  !=  <  >  <=  >=
<<  >>
+  -
*  /  %
-  !  ~  not      (unary prefix)
```

### 2.13 Unsafe

```
unsafe { ... }
```

Opts OUT of overflow/shift/bounds traps. Counted globally; audit report on
success when count>0. Malformed (no `{`) → compile error.

### 2.14 Extern FFI

```
extern "C" fn name(params...) -> type { }
```

Declares external C-ABI function. Emits unresolved call (PLT/GOT future).

### 2.15 Include / Module system

```
include "path/file.q"     // resolved relative to including file's dir
include io                 // bare: searches cwd/std/ext prefixes
```

Dedup by resolved-path hash; recursion depth <9. Cycle-safe.

### 2.16 Cross-TU globals

DATA globals referenced across `include` boundaries. Enables shared mutable
state across modules.

### 2.17 Literals

| Kind | Example | Notes |
|------|---------|-------|
| Integer | `42`, `0`, `12345` | Signed 64-bit |
| Hex | `0xFF` | ≥1 digit after `0x` |
| Float | `3.14` | P6.1a (in progress) |
| String | `"hello\n"` | Header `[8: len][bytes at +8]`; escapes `\n \t \\ \" \xNN` |
| Bool | `true`, `false` | `true`=1, `false`=0 |
| None | `none` | Value 0 |
| Tuple | `(10, 20, 30)` | IR_TALLOC |
| Array | `[100, 200, 300]` | IR_TALLOC, qword stride |
| Struct | `Point(3, 4)` | Constructor per struct def |

### 2.18 Subscript

```
a[i]       // qword stride read (arrays of 64-bit ints)
a[i] = v   // subscript-assignment
s[i]       // byte stride (strings, via vreg_is_str tag)
```

Bounds-check trap ON by default (i ≥ len → SIGILL rc=132).

### 2.19 Function pointers / Closures

```
let f = fnptr(add)                        // code pointer
let r = closure_call(f, 3, 4)            // env in rdi, codeptr in r11
```

Limits: ≤5 caller args per closure_call (stack-arg path future).

### 2.20 Ownership (compiler-inserted free)

```
let p = mem_alloc(n)    // p is OWNED on `mem_alloc()` call
```

`IR_FREE` (munmap) emitted at every scope exit. Manual `free()` also works
(munmap reentrant, no harm from double-free on page-granular allocs).

---


## 3. Types

> All values are 64-bit words at runtime. "Types" are compile-time annotations.

| Type | Token | Status |
|------|-------|--------|
| Signed integer | default/all literals | ✅ |
| u8 | `TT_U8=8` | ✅ via builtin `u8(x)` |
| u16 | `TT_U16=9` | ✅ |
| u32 | `TT_U32=10` | ✅ via builtin `u32(x)` |
| u64 | `TT_U64=11` | ✅ via builtin `u64(x)` |
| usize | `TT_USIZE=12` | token exists |
| bool | `TT_BOOL=13` | ✅ `true`/`false` literals |
| char | `TT_CHAR=14` | token exists |
| byte | `TT_BYTE=15` | token exists |
| string | `TT_STRING=29` | header-based `IR_STR` |
| ref | `TT_REF=30` | token exists |
| mut | `TT_MUT=31` | token exists |
| move | `TT_MOVE=32` | token exists |

Float operations via builtins: `fadd`, `fmul`, `fsub`, `fdiv`.

---


## 4. Built-in Functions

All emit inline (no call overhead). SysV/ABI (rdi, rsi, rdx, rcx, r8, r9).

### 4.1 Memory

| Builtin | Description |
|---------|-------------|
| `mmap(size)` | Allocate `size` bytes RW |
| `mem_alloc(n)` | Allocate `n*8+8` bytes with header |
| `free(ptr)` | `munmap(ptr, header_len)` |
| `mem_load(ptr)` | Load 8 bytes |
| `mem_load8(ptr)` | Load 1 byte (zero-extended) |
| `mem_store(ptr, val)` | Store 8 bytes |
| `mem_store8(ptr, val)` | Store 1 byte (skipped if ptr==0) |

### 4.2 File I/O

| Builtin | Description |
|---------|-------------|
| `file_open(path, flags, mode)` | `open` syscall |
| `file_read(fd, buf, count)` | `read` syscall |
| `file_write(fd, buf, count)` | `write` syscall |
| `file_close(fd)` | `close` syscall |
| `exit(code)` | `exit` (60 x86 / 93 ARM64) |

### 4.3 Output

| Builtin | Description |
|---------|-------------|
| `print(buf, len)` | Write bytes to stdout |
| `printi(val)` | Signed decimal to stdout |
| `prints(str)` | String header bytes to stdout |
| `println(val)` | Integer + newline (0x0A) |
| `printsp(val)` | Integer + space |
| `newline()` | 0x0A byte |
| `print_f(fval)` | Float print |

### 4.4 Collections

| Builtin | Description |
|---------|-------------|
| `len(v)` | 8-byte length header |
| `str(a, b)` | Concatenate byte buffers |
| `push(v, e)` | Append byte |
| `pop(v)` | Remove last byte (0 if empty) |
| `mk_any(tag, val)` | Tagged tuple `(tag, payload)` |
| `fnptr(FNAME)` | Code pointer of function |
| `closure_call(fnb, args...)` | Indirect closure call |

### 4.5 Type / arithmetic

| Builtin | Description |
|---------|-------------|
| `u8(x)` | Truncate to 8-bit unsigned |
| `u32(x)` | Truncate to 32-bit unsigned |
| `u64(x)` | Identity |
| `udiv(a, b)` | Unsigned division |
| `umod(a, b)` | Unsigned modulo |
| `ult(a, b)` | Unsigned < |
| `ugt(a, b)` | Unsigned > |
| `ulte(a, b)` | Unsigned ≤ |
| `ugte(a, b)` | Unsigned ≥ |
| `fadd(a, b)` | Float addition |
| `fmul(a, b)` | Float multiplication |
| `fsub(a, b)` | Float subtraction |
| `fdiv(a, b)` | Float division |
| `argc()` | Variadic arg count |
| `arg(i)` | Variadic arg by index |

---


## 5. Standard Library

### 5.1 std/string

`strlen`, `str_len`, `strcmp`, `str_concat`, `str_substr`, `str_contains`.

### 5.2 std/io

`print`, `prints`, `println`, `printsp`, `printsln`, `newline`, `readln`.

### 5.3 std/array

`arr_len`, `arr_get`, `arr_set` (in-place), `arr_push`, `arr_pop`, `arr_last`,
`arr_sort` (insertion sort, ascending, stable).

### 5.4 std/math

`abs`, `min`, `max`, `pow(b, e)` (integer, e≥0), `sqrt(n)` (floor via binary
search). All integer-only (no float).

### 5.5 std/file

`write_file(path, data)` (O_CREAT|WRONLY|TRUNC), `read_file(path)` (cap 1 MiB).

---


## 6. Architecture

### 6.1 Pipeline

```
Source (.quanta) → Lexer → Parser → IR (flat per-function) →
Optimizer (Pass A/B/C/D) → Register allocator → Code generator →
ELF/object writer → Binary
```

### 6.2 IR ops

| Op | # | Description | Op | # | Description |
|----|---|-------------|----|---|-------------|
| IR_CONST | 0 | Load constant | IR_LOAD | 20 | Load from ptr |
| IR_MOV | 1 | Move vreg | IR_STORE | 21 | Store to ptr |
| IR_ADD | 2 | Add | IR_LOADG | 22 | Load global |
| IR_SUB | 3 | Subtract | IR_STOREG | 23 | Store global |
| IR_MUL | 4 | Multiply | IR_ARG | 24 | Call argument |
| IR_DIV | 5 | Divide | IR_PARAM | 25 | Param binding |
| IR_MOD | 6 | Modulo | IR_STR | 26 | String const |
| IR_CMP | 7 | Compare | IR_IDX | 32 | Field/array read |
| IR_NEG | 8 | Negate | IR_ISTORE | 33 | Field/array write |
| IR_NOT | 9 | Bitwise NOT | IR_TALLOC | 34 | Tuple/array alloc |
| IR_BAND | 10 | AND | IR_FNPTR | 35 | Function pointer |
| IR_BOR | 11 | OR | IR_CLOSURE_CALL | 36 | Indirect closure |
| IR_BXOR | 12 | XOR | IR_FREE | 37 | Ownership free |
| IR_SHL | 13 | Shift left | IR_RET | 16 | Return |
| IR_SHR | 14 | Shift right | IR_BR | 17 | Branch (cond) |
| IR_CALL | 15 | Function call | IR_JMP | 18 | Jump |
| | | | IR_LABEL | 19 | Label |

Each instruction: 5-word slot (40 B): `op, result-vreg, arg0, arg1, padding`.

### 6.3 Optimizer

| Pass | Function | Description |
|------|----------|-------------|
| A | Const-fold | Constant expression evaluation; algebraic id (`x*1`, `x+0`, `x& -1`) |
| B | Tail-call | Call → jmp for tail position |
| C | DCE | Dead code elimination (unreachable branches, dead stores) |
| D | Loop strength | Closed-form sum reduction |

Default ON since 1.0.12. Verified 286× speedup on arithmetic-progression loop.

### 6.4 Code generation — x86-64

- ABI: args RDI, RSI, RDX, RCX, R8, R9; return RAX; callee-saved RBX, RBP, R12–R15
- vregs → scratch regs (RAX, RCX, RDX, RSI, RDI, R8–R11); spill to `[rbp - offset]`
- Prologue: `push rbp; mov rbp, rsp; sub rsp, <frame_size>`
- Epilogue: `mov rsp, rbp; pop rbp; ret`
- 16-byte stack alignment before calls

### 6.5 Code generation — ARM64

- ABI: args X0–X5; return X0; callee-saved X19–X30
- Frame: X29, link register X30
- Prologue: `stp x29, x30, [sp, #-16]!; mov x29, sp; sub sp, sp, <frame_size>`
- Epilogue: `ldp x29, x30, [sp], #16; ret`
- Static PIE ELF output; `.o` object emission supported

### 6.6 Binary format

**x86-64:** Standard ELF64 ET_EXEC — `\x7fELF` class 2, one PT_LOAD at vaddr
`0x400000` (R+X), code+data appended. Mode 0755. Requires `setarch -R`.

**ARM64:** Static PIE ELF (position-independent). Tested on real Android devices
(Termux SSH port 8022) + qemu-aarch64.

### 6.7 Syscalls (Linux)

| Op | x86-64 | ARM64 |
|----|--------|-------|
| read | 0 | 63 |
| write | 1 | 64 |
| open | 2 | 56 |
| close | 3 | 57 |
| exit | 60 | 93 |
| mmap | 9 | 222 |
| munmap | 11 | 215 |

---


## 7. Security (Secure-by-Default)

All ON by default. Suppressed inside `unsafe {}`. Disable with
`--no-overflow-trap`.

| Guard | Trigger | Result |
|-------|---------|--------|
| Signed overflow (G2) | `INT_MAX+1`, `INT_MIN-1`, `NEG(INT_MIN)` | SIGILL rc=132 |
| Shift count (G2.3) | `x << 64`, `x >> 100` | SIGILL rc=132 |
| Container bounds (G2) | `a[i]` where `i ≥ len(a)` | SIGILL rc=132 |
| Unsafe blocks (G1) | `unsafe { }` counted; audit report on stderr | Marker + count |
| Emission bounds (F1) | Token/IR/var/fn/alloc overflow → exit(17) | Clean abort |

---


## 8. Test Suite

39 programs gated by exit code in `test_suites/EXPECTED.tsv`. **0.0.4 baseline: all 39 tests compile, 37 runtime correct, 2 compile-fail (trait, generics).**

| Test | Expect | Status |
|------|--------|--------|
| arithmetic | 30 | ✅ |
| fib | 55 | ✅ |
| struct_test | 7 | ✅ |
| enum_test | 42 | ✅ |
| match_test | 55 | ✅ |
| file_open_test | 3 | ✅ |
| float_test | 159 | ✅ |
| unsigned_ops | 0 | ✅ |
| prints_family | 0 | ✅ |
| mem_test | 42 | ✅ |
| bitwise_not | 0 | ✅ |
| break_continue | 0 | ✅ |
| exit/file_io/mmap | 0/42 | ✅ |
| param8/9/12 | 36/0/0 | ✅ |
| arg/elseif/pcheck | varied | ✅ |
| stdlib_test | 0 | ✅ |
| test_many_globals | 42 | ✅ |
| builtins_test | 198 | ✅ (pre-existing) |
| **option_test** | 42 | ❌ bare Some/None compile but match on built-in variants not fully implemented |
| **result_test** | 5 | ❌ bare Ok/Err compile but match on built-in variants not fully implemented |
| **trait_test** | 0 | ❌ compile error — trait/impl system not implemented |
| **generics_test** | 12 | ❌ compile error — `<T>` generics not implemented |

> 37 file-io/arithmetic/memory/enum tests pass. 2 aspirational tests (trait, generics) compile-fail. 2 built-in enum tests (option, result) compile but match incomplete.

---


## 9. Version History

| Version | Date | What |
|---------|------|------|
|| **0.0.5** | **2026-07-30** | **Bare Some/None/Ok/Err support (expressions + match patterns). x86_64 self-host verified (stage2==stage3), 39/39 x86_64 tests pass. ARM64 cross-compile works but ARM64 bare-variant pattern match broken (exit 0) — BLOCKS ARM64 promotion.** |
| **0.0.4** | **2026-07-30** | **Enum support + self-host verified. Enum declarations, constructors, match expressions working. 37/39 tests pass (trait, generics not implemented; option/result match on built-ins incomplete).** |
| **0.0.2** | **2026-07-29** | **WIP. option_test + result_test fixed (bare Some/None/Ok/Err). struct_test regression + enum_test match capture + file_open_test string-header all fixed. 38/39 compile, 38/38 runtime pass. 2 remaining: trait, generics.** |
| — legacy 1.x — | — | — |
| 1.1.0 | 2026-07-20 | Security review + F1/F2 fixes (STABLE) |
| 1.1.1 | 2026-07-20 | Unsigned builtins (udiv/umod/ult/...) |
| 1.1.2 | 2026-07-20 | G1: `unsafe {}` block |
| 1.1.3 | 2026-07-20 | G2 part 1: overflow trap (opt-in) |
| 1.1.4 | 2026-07-20 | G2 part 2: overflow trap ON by default |
| 1.1.5 | 2026-07-20 | G2 part 3: shift-count UB trap |
| 1.1.6 | 2026-07-20 | Parenthesized-expr parse fix |
| 1.1.7 | 2026-07-20 | G2 containers + subscript-assign + string stride |
| 1.1.8 | 2026-07-21 | P2 ownership: compiler-inserted free |
| 1.1.9 | 2026-07-22 | P3 FFI: `extern "C"` |
| 1.1.10–1.33 | — | ARM64 backend, P6 scaffolding, bug fixes |
| 1.1.34-wip | current | P6 enum/match/generics/type-system tokens |

---
