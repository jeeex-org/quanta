# Quanta Language Syntax Reference

Quanta is designed to be simple and supports multiple modes—interpreter, WASM, JIT, pre‑compiler (e.g., `quanta run`), and native compilation to binary (`qc`).

This document describes the language as implemented by the current compiler in
`compiler/` (x86-64; AArch64 deferred POST-1.0). It is a description of the
language surface only — it carries no version or gate numbers, because those
rot. For what landed when, and the current gate status, see `docs/ROADMAP.md`;
for per-feature implementation status and the tests covering each, see
`docs/FEATURES.md`.

---

## 1. Lexical Structure

### Comments
- `//` – line comment (until end of line)
- `/* … */` – block comment (can span multiple lines)

### Whitespace
Space (` `), horizontal tab (`\t`), newline (`\n`), carriage return (`\r`) are whitespace and separate tokens unless otherwise noted.

### Identifiers
- Start with a letter (`A‑Z a‑z`) or underscore (`_`)
- Followed by zero or more letters, digits (`0‑9`) or underscore
- Case‑sensitive

### Keywords
Reserved tokens (cannot be used as identifiers):

```
fn   let   if   else   loop   while   for   break   continue   return
unsafe   extern   alias   global   // (see additional keywords below)
```

**Additional keywords** (recognized; enum and match are implemented):
```
enum   match   type   interface   impl   where   Option   Some   None   Result   Ok   Err   ref   mut   move   String
```

### Literals

| Kind   | Syntax                              | Notes |
|--------|-------------------------------------|-------|
| Integer| `42`, `-7`, `0xFF` (hex)            | Signed 64‑bit two’s complement |
| Float  | `3.14`                              | IEEE‑754 binary64 |
| Char   | Not a distinct type; use `u8` values| – |
| String | `"hello\n"`                         | UTF‑8 bytes with a length prefix (see §4) |
| Boolean| `true`, `false`                     | Stored as `1` / `0` |
| Unit   | `()` (implicitly `none`)            | Represents no value |

### Operators
Operators are single or double character punctuation.  See §6 for precedence.

---

## 2. Types

All runtime values are 64‑bit words.  Types are *compile‑time* annotations that guide code generation and optional runtime checks.

### Primitive Types
| Alias | Meaning                              | Storage |
|-------|--------------------------------------|---------|
| (default) | Signed 64‑bit integer               | i64 |
| `u8`  | Unsigned 8‑bit                       | u8 |
| `u16` | Unsigned 16‑bit                     | u16 |
| `u32` | Unsigned 32‑bit                     | u32 |
| `u64` | Unsigned 64‑bit                     | u64 |
| `usize`| Pointer‑sized unsigned (same as u64 on current targets) | usize |
| `bool`| Boolean (`true`/`false`)            | 0/1 |
| `char`| Unicode code point (stored as u32)  | u32 |
| `byte`| Synonym for `u8`                     | u8 |
| `string`| Heap‑allocated UTF‑8 buffer with length header `[8:len][bytes]` | ptr+len |
| `ref` | Raw pointer (no ownership)          | ptr |
| `mut` | Mutable qualifier (used with `ref`) | – |
| `move`| Move‑only qualifier (used with `ref`) | – |

*Note*: The compiler inserts implicit `free` for values owned via `mem_alloc` (see Ownership §5).

### Composite Types
- **Tuple**: `(T0, T1, …)` – fixed size, fields accessed by index.
- **Array**: `[T; N]` – fixed‑size contiguous storage (currently only via literals `[a,b,c]`; length is part of type).
- **Struct**: `struct Name { f0: T0, f1: T1, … }` – named fields, layout‑compatible with tuple; field access `obj.field`.
- **Enum (sum type)**: `enum Name { V0, V1(T), V2(T,U), … }` – discriminant stored in first word, payload follows.
- **Function pointer**: `fnptr(FNAME)` – code pointer, callable via `closure_call`.
- **Closure**: a closure literal `|params| { body }` evaluates to a
  16-byte `[codeptr, env]` value. Call it directly by name, pass it to an
  fn-typed parameter, or invoke a hand-built one with `closure_call(fnb, args…)`.
  See §Closure literals below.

### Type Aliases
`alias NewName = ExistingType;` – creates a compile‑time synonym.

---

## 3. Declarations and Bindings

### Variables
```quanta
let x = 42               // immutable binding (explicit)
x = 42                   // also valid — `let` is OPTIONAL; bare name = new binding
x = x + 1                // reassignment to a local declared without `let`
```
- `let` is **optional**. A bare `name = expr` at function-top-level or in a block
  introduces a new local binding (same as `let name = expr`). Inside a function,
  `name = expr` with an existing local assigns; `name = expr` with no existing
  local declares a new one.
- At **top level** (outside any function), a bare `name = expr` declares a
  **global** binding. Use `global name` for an explicit writable global, or
  `const name` for a read-only one.
- The initializer is an expression; its type may be omitted and inferred.

### Constants
- `const name = expr` — read-only top-level binding (compile-time-constant).
- `let name = expr` with a compile-time-known initializer is also treated as a
  constant.

### Global / local variable references
Two explicit sigils disambiguate scope inside expressions and string literals:
- `${name}` — read a **global** binding (resolves to a `global`/`const`/`top-level
  bare declaration via the global table; undeclared global → compile error).
- `$[]` — read a **local** binding (resolves to the current function's local;
  undeclared local → compile error).
```quanta
global user = "admin"
fn greet() {
    let who = "James"
    print("hi " .. $[who] .. " " .. ${user})   // bare form: .. + sigils
    print("hi ${user}, welcome $[who]!")        // inside-string interpolation
}
```
Both forms work **bare** (combined with `..`) and **inside string literals**.
Writing to a sigil (`${name} = x`, `$[name] = x`) is forbidden — assign via the
plain name or `global`.

### Functions
```quanta
// `fn` is OPTIONAL. All of these are equivalent function definitions:
fn add(a, b) { return a + b }      // canonical
add(a, b) { return a + b }         // bare form (no `fn`)
init() { print("boot") }           // bare init (runs before main if present)
main() {                            // bare main
    let r = add(3, 4)
    return r
}
```
- **`fn` is optional.** A top-level `name(params) { body }` is a function
  definition with or without `fn`. Mixing is fine: `fn main() { helper() }`
  alongside bare `helper() { ... }`.
- **Condition parentheses are optional.** `if x > 5`, `while i < n`, `for i = 0; i < n; i = i + 1` — no parens needed (and `if (x > 5)` also works).
- **`return` is optional.** The last expression of a function body is its
  return value (Rust/ML style). `return` is still available for early exit.
- **Parameters**
  - Positional, separated by commas.
  - Optional default value after `=` (only for trailing parameters).
  - Named‑argument call: `f(b: 2, a: 1)` – order does not matter.
  - Variadic: `fn f(a, b, ...)` – inside the function use `arg(i)` to access extra arguments. There is no `argc()`; for the process argument count use the `arg_count()` builtin (`argc()` compiles but always returns 0).
- **Return type**
  - If omitted, defaults to `i64` (but treated as advisory).
  - Multiple values can be returned via a tuple: `return a, b, c;` → caller can destructure with `let x, y = f()`.
- **Extern linkage** (C ABI): `extern "C" fn name(...) -> Rt;` – see §9.
- **Function attributes** (via tokens): `unsafe`, `alias`, etc.

### Closure literals

A closure literal is an anonymous function value written `|params| { body }`.
The braces are required.

```quanta
fn main() {
    let f = |x| { x + 1 }
    return f(5)                  // 6
}
```

Multiple parameters are comma-separated:

```quanta
let g = |x, y| { x + y }
g(3, 4)                          // 7
```

A closure can be passed to a function whose parameter carries an **fn type
annotation** — the annotation is what makes the callee dispatch indirectly
instead of resolving a direct symbol:

```quanta
fn apply(f: fn(i64) i64, x) { return f(x) }

fn main() {
    let doubler = |x| { x * 2 }
    return apply(doubler, 21)    // 42
}
```

**Representation.** A closure literal evaluates to a 16-byte value laid out as
`[codeptr, env]` — the same layout `fnptr`/`mk_any` produce — so a closure is
interchangeable with a hand-built function value and may also be invoked with
`closure_call(fnb, args…)`. Calls use the standard SysV argument registers, with
`env` passed in `r10`. Up to 5 arguments are supported.

**Not yet implemented: captures.** `env` is currently always 0, so a closure
body may only reference its own parameters. Referring to a local from the
enclosing scope is a compile error:

```quanta
fn main() {
    let y = 10
    let f = |x| { x + y }        // error: undeclared variable: y
    return f(5)
}
```

Capturing closures are a planned increment (see ROADMAP).

---

## 4. Expressions

### Primary Expressions
- Literals (`42`, `"hi"`, `true`)
- Variables (`x`)
- Function calls (`foo(1,2,3)`)
- Method‑style call (`obj.method(args)`) – desugars to `method(obj, args)`
- Tuple construction: `(a, b, c)`
- Array literal: `[a, b, c]`
- Struct construction: `Point{ x: 1, y: 2 }` or `Point(1,2)` (positional)
- Enum construction: `Color::Red` or `Color::Green(42)` (payload optional)
- `none` – the unit value (`0`)
- `some(expr)` and `err(expr)` – constructors for `Option` and `Result` (see below)
- `fnptr(func_name)` – yields a function pointer
- `closure_call(fnptr, args…)` – indirect call with captured environment

### Operators (precedence high → low)

| Level | Operator(s) | Associativity |
|-------|-------------|---------------|
| 1     | `a[i]`, `a[i] = v`, `a.field`, `a.method(...)`, `fnptr(...)`, `closure_call(...)`, `(a)`, `[a; n]` | Left |
| 2     | `!a`, `~a`, `-a` (negate), `*a` (deref not needed – use `mem_load`) | Right |
| 3     | `*`, `/`, `%` (including unsigned versions `udiv`, `umod`) | Left |
| 4     | `+`, `-` | Left |
| 5     | `<<`, `>>` (logical shift) | Left |
| 6     | `<`, `>`, `<=`, `>=`, `==`, `!=` (ult, ugt, ulte, ugte) | Left |
| 7     | `&` (bitwise AND), `|` (OR), `^` (XOR) | Left |
| 8     | `&&` (logical AND), `||` (logical OR) | Left |
| 9     | `=` (assignment) | Right |
| 10    | `,` (sequence, tuple element separator) | Left |

*Note*: Bitwise operators (`&`, `|`, `^`, `~`, `<<`, `>>`) are exposed as surface syntax (parsed to `IR_BAND`/`IR_BOR`/`IR_BXOR`/`IR_BNOT`/`IR_SHL`/`IR_SHR`).  Logical `&&`/`||` (also `and`/`or`) are short‑circuit.

### Control‑Flow Expressions
- `if cond { then } else { else }` – yields the value of the chosen branch (if both sides produce a value).
- `loop { … }` – infinite loop; use `break` to exit with a value: `break expr`.
- `while cond { … }`
- `for i = start; cond; step { … }` – classic C‑style loop.
- `for x in arr { … }` – iterates over an array (implemented); elements are 0‑indexed. Use `len(arr)` for the element count.
- `match disc { pat => expr, … }` – pattern‑matching expression (see §7).

---

## 5. Ownership and Memory Management

Quanta uses **ownership‑by‑default**:
- Any value obtained from `mem_alloc(n)` (or `mmap`) is **owned** by the binding that received it.
- When the binding leaves its scope (normal fall‑through, `break`, `continue`, `return`), the compiler automatically inserts `IR_FREE` (which calls `munmap`) for each owned binding.
- Manual `free(ptr)` is also allowed and is a no‑op for already‑freed pages (munmap is reentrant).

### Built‑in memory functions
| Builtin | Signature | Description |
|---------|-----------|-------------|
| `mmap(size)` | `-> ptr` | Allocate `size` bytes RW (anonymous). |
| `mem_alloc(n)` | `-> ptr` | Allocate `n*8+8` bytes (header + payload). |
| `free(ptr)` | `()` | `munmap(ptr, header_len)`. |
| `mem_load(ptr)` | `-> i64` | Load 8‑byte word. |
| `mem_load8(ptr)` | `-> u8` (zero‑extended) | Load byte. |
| `mem_store(ptr, val)` | `()` | Store 8‑byte word. |
| `mem_store8(ptr, val)` | `()` | Store byte (skip if `ptr==0`). |

### Example
```
fn fib(n) {
    if n < 2 { return n }
    return fib(n - 1) + fib(n - 2)
}

fn main() {
    return fib(10)
}
```

---

## 6. Standard Built‑ins (intrinsics)

All builtins are emitted inline; they have no call overhead.

### Memory (see §5)

### File I/O (thin syscall wrappers)
| Builtin | Signature | Description |
|---------|-----------|-------------|
| `file_open(path, flags, mode)` | `-> fd` | `open` syscall |
| `file_read(fd, buf, count)` | `-> bytes_read` | `read` |
| `file_write(fd, buf, count)` | `-> bytes_written` | `write` |
| `file_close(fd)` | `()` | `close` |

### Output
| Builtin | Signature | Description |
|---------|-----------|-------------|
| `print(buf, len)` | `()` | Write raw bytes to stdout |
| `printi(val)` | `()` | Signed decimal to stdout |
| `prints(str)` | `()` | Write string header bytes to stdout |
| `println(val)` | `()` | Integer + newline |
| `printsp(val)` | `()` | Integer + space |
| `newline()` | `()` | Output `\n` |


### Conversions & Helpers
| Builtin | Signature | Description |
|---------|-----------|-------------|
| `u8(x)`, `u16(x)`, `u32(x)`, `u64(x)` | `-> truncated` | Bit‑mask to width |
| `udiv(a,b)`, `umod(a,b)` | `-> unsigned` | Unsigned division/modulo |
| `ult(a,b)`, `ugt(a,b)`, `ulte(a,b)`, `ugte(a,b)` | `-> 0/1` | Unsigned comparisons |
| `fadd(a,b)`, `fsub(a,b)`, `fmul(a,b)`, `fdiv(a,b)` | `-> i64` | Float arithmetic; takes **int** args, computes `(double)a OP (double)b`, returns **int** (truncated). `fadd(3,4)=7`. |
| `i2f(x)`, `f2i(x)` | `-> f64 bit-pattern` / `-> i64` | Int↔f64 bit-pattern conversion (no rounding). `i2f(3)` is the f64 bits of `3.0`. |
| `feq(a,b)`, `flt(a,b)`, `fgt(a,b)`, `fle(a,b)`, `fge(a,b)` | `-> 0/1` | Float comparisons; args are f64 **bit-patterns** (pass `i2f(x)`). `feq(i2f(25),i2f(10))=0`, `fgt(i2f(25),i2f(10))=1`. |
| `fisnan(a)`, `fisinf(a)` | `-> 0/1` | Float introspection on f64 bit-pattern. |
| `sqrt(a)`, `floor(a)`, `ceil(a)`, `abs(a)` | `-> f64 bit-pattern` | Float math on f64 bit-pattern in/out. `sqrt(i2f(144))=i2f(12)`. |

| `arg(i)` | `-> i64` | i‑th variadic argument (0‑based) |
| `len(v)` | `-> i64` | Length prefix of string/array/slice |
| `str(a,b)` | `-> string` | Concatenate two byte buffers |
| `push(v, e)` | `()` | Append byte to buffer |
| `pop(v)` | `()->byte` | Remove and return last byte |
| `mk_any(tag, val)` | `-> tuple` | Tagged tuple `(tag, payload)` |
| `fnptr(FNAME)` | `-> fnptr` | Code pointer of function |
| `closure_call(fnb, args…)` | `-> ret` | Indirect call with captured environment |

### Miscellaneous
| Builtin | Signature | Description |
|---------|-----------|-------------|
| `exit(code)` | `()` | Terminate process with given code |
| `malloc`/`mmap` aliases – see memory section |

---

## 7. Pattern Matching (`match`) (implemented)

### Patterns
| Pattern | Meaning |
|---------|---------|
| `ident` | Binds the matched value to a new identifier (shadows outer). |
| `_` | Wildcard – matches anything, discards value. |
| `literal` | Matches exact literal value (int, bool, etc.). |
| `struct_name { field: pat, … }` | Matches a struct and recursively matches fields. |
| `enum_name::Variant` | Matches an enum variant (with optional payload). |
| `enum_name::Variant(pat1, pat2, …)` | Matches variant and binds its fields. |
| `Some(pat)` / `None` | Shorthand for `Option` variants. |
| `Ok(pat)` / `Err(pat)` | Shorthand for `Result` variants. |
| `(pat1, pat2, …)` | Tuple pattern. |
| `[pat, …, pat]` | Slice/array pattern (fixed length). |

### Guards
**Not implemented.** A guarded arm (`n if n > 3 => …`) is *parsed* but the guard
is not honoured: the `match` falls through every arm and yields `0` rather than
raising a diagnostic. Do not use guards; test the condition with an `if` instead.

```
let x = Some(5);
match x {
    Some(v) => println(v),
    None    => println(0)
}
```

---

## 8. Aggregates

### Structs
```
// Declares a struct, constructs it, and reads both fields.
struct Point { x y }

fn make(a, b) {
    return Point(a, b)
}

fn main() {
    let p = make(3, 4)
    return p.x + p.y   // 3 + 4 = 7
}
```
- Constructor can also be positional: `Point(1,2)`.
- Fields may have a `: Type` annotation; if omitted, the type is inferred from the initializer (if any) or left generic.
- Struct literal syntax `Point { x: 3, y: 4 }` is also supported (rewritten to a constructor call).

### Enums (implemented)

```quanta
enum Color {
    Red,
    Green,
    Blue,
}

fn main() {
    let c = Color.Red
    let v = match c {
        Color.Red => 42,
        Color.Green => 2,
        Color.Blue => 3,
    }
    return v
}
```
- Discriminant is stored in the first word (0‑based variant index).
- Payload follows the discriminant, laid out as a tuple.

### Option & Result (built‑in enums; constructors + match implemented)

```quanta
enum Option<T> { None, Some(T) }
enum Result<T, E> { Err(E), Ok(T) }
```
Constructors:
- `none` → `Option::None`
- `some(expr)` → `Option::Some(expr)`
- `err(expr)` → `Result::Err(expr)`
- `ok(expr)` → `Result::Ok(expr)`

**Note**: Bare `Some(val)`, `None`, `Ok(val)`, `Err(val)` expressions and `match` on them are supported.

```quanta
let some_val = Some(42)
let none_val = None

match some_val {
    Some(x) => x,
    None => 0,
}

fn divide(a, b) -> Result<int, string> {
    if b == 0 { return Err("division by zero") }
    return Ok(a / b)
}

fn main() {
    let result = divide(10, 2)
    match result {
        Ok(value) => value,
        Err(e) => 0,
    }
}
```

---
```
// Tuple literal (a,b) + .N field access. Exercises IR_TALLOC + IR_IDX
// (qword stride) on both backends.
fn main() {
    let t = (10, 20, 30)
    return t.0 + t.2   // 10 + 30 = 40
}
```
- Tuple elements accessed via `.0`, `.1`, … (or by destructuring).
- Array length is part of the type; indexing uses `a[i]` (bounds‑checked by default, traps on out‑of‑range).  Use `len(a)` for the element count — a negative index such as `a[-1]` is out of range and **traps** (SIGILL, rc=132), it is not a length shorthand.

---

## 9. Foreign Function Interface (FFI)

### Declaring external C functions
```
extern "C" fn putchar(c: i64) -> i64;
```
- The `extern "C"` modifier tells the code generator to emit a plain C‑call symbol (no name mangling).
- The function can then be called like any other Quanta function.

### Calling from C
Exported symbols are not yet implemented; the focus is on importing C functions.

---

## 10. Module / Include System

Quota supports a simple textual inclusion mechanism (similar to C `#include`).

```
include "path/file.q"   // relative to the including file’s directory
include std/io          // bare name: searches ./std, ./, /usr/local/quanta/std, etc.
```
- The resolver deduplicates based on the absolute path hash.
- Nesting depth is limited to avoid stack overflow (currently 9).

---

## 11. Generics, Traits, and Implementations

Generic type parameters `<T>` are **not usable** (parsed, but silently produce wrong results — see §Generic Functions).  Traits, impls, and struct literals **are** implemented.

### Generic Functions
```
fn map<T, U>(arr: [T], f: fn(T) -> U) -> [U] {
    let result = [U]()
    for item in arr {
        result.push(f(item))
    }
    return result
}

fn double(x: int) -> int {
    return x * 2
}

fn main() {
    let arr = [1, 2, 3]
    let doubled = map(arr, double)
    return doubled[0] + doubled[1] + doubled[2]
}
```
- **Not usable.** Type parameters are *parsed* — the example above compiles
  without error — but they are not implemented semantically: it returns `0`
  instead of `12`. A generic signature is accepted and then produces wrong
  results rather than a diagnostic, so do not rely on generics. Trivial cases
  where the parameter is only passed through (e.g. `fn id<T>(x: T) -> T`) do
  happen to work, which makes the gap easy to miss.

### Traits (interfaces)

Implemented: trait declarations, `impl Trait for Struct` blocks, and dispatch through trait‑typed parameters.

```

trait Drawable {
    fn draw(self) -> int
}

struct Circle {
    radius: int
}

impl Drawable for Circle {
    fn draw(self) -> int {
        self.radius * 2
    }
}

fn draw_shape(d: Drawable) {
    d.draw()
}

fn main() {
    let c = Circle { radius: 5 }
    draw_shape(c)
    return 0
}
```
- A trait defines a set of method signatures.

### Implementations
```
impl Drawable for Circle {
    fn draw(self) -> i64 {
        return self.radius * 2;
    }
}
```
- Instances of `Circle` can be passed wherever a `Drawable` trait‑typed parameter is expected; dispatch resolves the (single) impl method.  Multi‑impl vtable dispatch is not yet implemented — a second `impl Trait for OtherStruct` declaring the same method name is rejected at compile time with `error: duplicate function definition`.

### Associated Types & Where Clauses
Not yet implemented.

---

## 12. Safety and `unsafe`

- By default, integer overflow, shift‑out‑of‑range, and array bounds are **trapped** (SIGILL, rc=132).
- Inside an `unsafe { … }` block:
  - Overflow and shift traps are **disabled**.
  - Raw pointer arithmetic and foreign calls are allowed.
  - The block is counted for audit purposes (`unsafe_count` global).
- The compiler itself wraps its own deliberate‑overflow checks in `unsafe{}` to keep the self‑host build “green”.

---

## Minimal “Hello, World”

```quanta
// output builtins: prints(str), printsp(int), println(int),
// newline(), print(buf,len), printi(int).
fn main() {
  prints("AB")      // string bytes: "AB"
  printi(42)        // "42"
  newline()         // "\n"
  printsp(7)        // "7 "
  println(9)        // "9\n"
  print("X"+8, 1)   // "X"
  exit(0)
}
```

## Using Ownership

```quanta
fn main() {
    let addr = mmap(4096)
    mem_store(addr, 42)
    let val = mem_load(addr)
    return val
}
```

## Pattern Matching with Enum

```quanta
fn divide(a, b) {
    if b == 0 {
        return Err("division by zero")
    }
    return Ok(a / b)
}

fn main() {
    let result = divide(10, 2)
    match result {
        Ok(value) => value,
        Err(e) => 0,
    }
}
```

## Break and Continue

```quanta
// break/continue in while and for, including nested loops.
fn main() {
  let s=0 let i=0
  while i<10 { i=i+1; if i%2==0 { continue }; s=s+i }
  if s!=36 { return 1 }
  let j=0
  while 1==1 { j=j+1; if j==5 { break } }
  if j!=5 { return 2 }
  let c=0 let a=0
  while a<3 { a=a+1; let b=0; while b<10 { b=b+1; if b==2 { break }; c=c+1 } }
  if c!=3 { return 3 }
  let t=0
  for k=1; k<=6; k=k+1 { if k==3 { continue }; t=t+k }
  if t!=18 { return 4 }
  return 0
}
```

## File I/O

```quanta
// file_io: file_open/file_read/file_write/file_close round-trip.
// Creates a temp file, writes 26 bytes, reads back, verifies contents.
fn r8x(p) { unsafe { return mem_load8(p) } }
fn w8x(p,v) { unsafe { mem_store8(p,v) } }
fn main() {
  let path = mmap(64)
  // "qfio_test.bin" (cwd-relative: writable on host AND Termux device;
  // /tmp is not app-writable under Android's sandbox)
  let s = "qfio_test.bin"
  let sl = len(s)
  let i=0
  while i<sl { w8x(path+i, r8x(s+8+i)); i=i+1 }
  w8x(path+sl, 0)
  // write: O_WRONLY|O_CREAT|O_TRUNC = 577, mode 420
  let wfd = file_open(path, 577, 420)
  if wfd < 0 { return 1 }
  let buf = mmap(64)
  i=0
  while i<26 { w8x(buf+i, 65+i); i=i+1 }
  let wn = file_write(wfd, buf, 26)
  file_close(wfd)
  if wn != 26 { return 2 }
  // read back
  let rfd = file_open(path, 0)
  if rfd < 0 { return 3 }
  let rbuf = mmap(64)
  let rn = file_read(rfd, rbuf, 64)
  file_close(rfd)
  if rn != 26 { return 4 }
  i=0
  while i<26 { if r8x(rbuf+i) != 65+i { return 5 }; i=i+1 }
  return 0
}
```

## Function Pointers

```quanta
// fnptr(FNAME) -> code pointer as a runtime value. Exercises the t10 fnptr
// codegen on both backends.
fn add(a, b) {
    return a + b
}

fn main() {
    let p = fnptr(add)
    return 0   // just verify fnptr() constructs without error
}
```

## Arithmetic

```quanta
fn main() {
    let a = 10
    let b = 20
    let c = a + b
    let d = a * b
    let e = b - a
    let f = b / a
    return c
}
```

## Builtins

```quanta
fn main() {
    let addr = mmap(64)
    mem_store8(addr, 65)
    mem_store8(addr + 1, 66)
    mem_store8(addr + 2, 67)
    let b0 = mem_load8(addr)
    let b1 = mem_load8(addr + 1)
    let b2 = mem_load8(addr + 2)
    let val = b0 + b1 + b2
    mem_store(addr, val)
    let loaded = mem_load(addr)
    return loaded
}
```

---
