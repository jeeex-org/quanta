# Quanta Language Syntax Reference

Quanta is designed to be simple and supports multiple modes—interpreter, WASM, JIT, pre‑compiler (e.g., `quanta run`), and native compilation to binary (`qc`).

This document describes the language as implemented in the current stable compiler (`src/qc-0.0.11.quanta`).

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
unsafe   extern   alias   global   // (see below for P6 keywords)
```

**P6‑phase keywords** (recognized; enum and match now implemented):
```
enum   match   type   interface   impl   where   Option   Some   None   Result   Ok   Err   ref   mut   move   String
```

### Literals

| Kind   | Syntax                              | Notes |
|--------|-------------------------------------|-------|
| Integer| `42`, `-7`, `0xFF` (hex)            | Signed 64‑bit two’s complement |
| Float  | `3.14`                              | IEEE‑754 binary64 (WIP) |
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
- **Closure**: Created implicitly when a function captures environment; invoked with `closure_call(fnb, args…)`.

### Type Aliases
`alias NewName = ExistingType;` – creates a compile‑time synonym.

---

## 3. Declarations and Bindings

### Variables
```
let x = 42               // immutable binding
let mut x = 42           // mutable (explicit mut keyword)
x = x + 1                // reassignment (only if mutable)
```
- `let` introduces a new binding; it **shadows** any previous binding with the same name in the same scope.
- The initializer is an expression; its type may be omitted and inferred.

### Constants
Not a separate syntax; use `let` with an initializer that is known at compile time (the compiler treats it as a constant).

### Functions
```

// closure_call(fnb, args...) — indirect call through a mk_any(fnptr, env) tuple.
// Exercises the closure_call ABI fix: caller args must land in STANDARD arg
// registers (rdi/x0..), with env in a scratch reg the callee ignores.
fn add(a, b) {
    return a + b
}

fn main() {
    let f = mk_any(fnptr(add), 0)
    let r = closure_call(f, 3, 4)
    return r   // 3 + 4 = 7
}
```
- **Parameters**
  - Positional, separated by commas.
  - Optional default value after `=` (only for trailing parameters).
  - Named‑argument call: `f(b: 2, a: 1)` – order does not matter.
  - Variadic: `fn f(a, b, ...)` – inside the function use `argc()` and `arg(i)` to access extra arguments.
- **Return type**
  - If omitted, defaults to `i64` (but treated as advisory).
  - Multiple values can be returned via a tuple: `return a, b, c;` → caller can destructure with `let x, y = f()`.
- **Extern linkage** (C ABI): `extern "C" fn name(...) -> Rt;` – see §9.
- **Function attributes** (via tokens): `unsafe`, `alias`, etc.

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

*Note*: Bitwise operators (`&`, `|`, `^`, `~`, `<<`, `>>`) are present in the IR but currently **not** exposed as surface syntax in the WIP compiler (they appear as builtins).  Logical `&&`/`||` are short‑circuit.

### Control‑Flow Expressions
- `if cond { then } else { else }` – yields the value of the chosen branch (if both sides produce a value).
- `loop { … }` – infinite loop; use `break` to exit with a value: `break expr`.
- `while cond { … }`
- `for i = start; cond; step { … }` – classic C‑style loop.
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
| `print_f(fval)` | `()` | Float output (WIP) |

### Conversions & Helpers
| Builtin | Signature | Description |
|---------|-----------|-------------|
| `u8(x)`, `u16(x)`, `u32(x)`, `u64(x)` | `-> truncated` | Bit‑mask to width |
| `udiv(a,b)`, `umod(a,b)` | `-> unsigned` | Unsigned division/modulo |
| `ult(a,b)`, `ugt(a,b)`, `ulte(a,b)`, `ugte(a,b)` | `-> 0/1` | Unsigned comparisons |
| `fadd(a,b)`, `fsub(a,b)`, `fmul(a,b)`, `fdiv(a,b)` | `-> f64` | Float arithmetic (WIP) |
| `i2f(x)`, `f2i(x)` | `-> f64/i64` | Float/int conversion |
| `argc()` | `-> i64` | Variadic argument count |
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
Not yet implemented in the WIP compiler.

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
// P4.3 struct feature test. Declares a struct, constructs it, reads both
// fields. Verifies the ARM struct base-pointer / field-stride codegen.
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

### Option & Result (built‑in enums; bare constructors + match working on x86_64, ARM64 backend bug)

```quanta
enum Option<T> { None, Some(T) }
enum Result<T, E> { Err(E), Ok(T) }
```
Constructors:
- `none` → `Option::None`
- `some(expr)` → `Option::Some(expr)`
- `err(expr)` → `Result::Err(expr)`
- `ok(expr)` → `Result::Ok(expr)`

**Note**: Bare `Some(val)`, `None`, `Ok(val)`, `Err(val)` expressions compile and work correctly on x86_64. Pattern matching on them via `match` is fully implemented on x86_64 (qc-0.0.5). ARM64 cross-compilation works but ARM64 backend has a register emission bug causing bare variant pattern matches to return 0 — fix tracked for qc-0.0.6.

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
- Array length is part of the type; indexing uses `a[i]` (bounds‑checked by default, traps on out‑of‑range).

---

## 9. Foreign Function Interface (FFI)

### Declaring external C functions
```
extern "C" fn putchar(c: i64) -> i64;
```
- The `extern "C"` modifier tells the code generator to emit a plain C‑call symbol (no name mangling).
- The function can then be called like any other Quanta function.

### Calling from C
Exported symbols are not yet implemented in the WIP; the focus is on importing C functions.

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

## 11. Generics, Traits, and Implementations (WIP)

The parser recognises the following tokens, but code generation for generics and trait dispatch is **not yet complete**.

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
- Type parameters are substituted at compile time (monomorphisation).

### Traits (interfaces)
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
- Instances of `Circle` can be used wherever a `Drawable` is expected (via vtable‑based dispatch).

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
// prints_family: output builtins prints(str), printsp(int), println(int),
// newline(), print(buf,len), printi(int). Golden stdout captured from x86 and
// asserted equal on ARM.
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
// break_continue: break/continue in while and for, nested loops.
// Golden values captured from verified 1.1.9-lineage x86 output; ARM must match.
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
