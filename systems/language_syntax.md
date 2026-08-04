## 2. Language Syntax

### 2.1 Program structure

```
<program>  ::= { <function-def> | <struct-def> }
```

Execution starts at `fn main()`; return value is the process exit code
(default `0` if no explicit `return`).

> **Status:** `enum` + `match`, and `Option`/`Result` are implemented (qc-0.0.7);
> `trait`/`impl` are implemented (qc-0.0.13). **Generics `<T>` remains NOT
> implemented** (see 2.8). `interface`, associated types and `where` clauses are
> placeholder targets only.

### 2.2 Functions

```
fn name(p1, p2, ...) -> type { statements }
```

- Up to 6 args in registers (SysV: rdi, rsi, rdx, rcx, r8, r9); args 7+ on stack.
- Return type annotation optional and advisory (`-> int`).
> ⚠️ **Type keywords:** only `u8` / `u16` / `u32` / `u64` / `usize` / `bool` /
> `char` / `byte` are recognized type keywords. The token `int` is **not** a
> type keyword — untyped literals default to signed. `-> int` annotations in
> this doc are advisory return annotations only, and are not type-checked.
- All functions top-level. Forward references allowed.
- Variadic: `fn f(a, b, ...)` — use `arg(i)` (reads the i-th arg; returns 0 out of range). `argc()` is **not** a builtin.
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

### 2.5 Enums (implemented — qc-0.0.7)

```q
enum Color { Red, Green, Blue }
let c = Color.Red
```

Enum variants are accessible via `Color.Red`. Verified working (`run=1`).

### 2.6 Match (implemented — qc-0.0.7)

```q
match c {
    Color.Red => 1,
    Color.Green => 2,
    Color.Blue => 3,
}
```

Pattern arms are `variant => expr`; the match evaluates to the chosen arm's
value. Verified working (`match c { Color.Red => 1 }` → `1`).

### 2.7 Option / Result (implemented — qc-0.0.7)

```q
let a = Some(42)
let b = None
let ok = Ok(a)
let err = Err("msg")
let v = a.1        // payload access: v = 42
```

`Some(v)` / `None` and `Ok(v)` / `Err(v)` are enum variants. Payload is carried
in index 1, accessed via `.1` (e.g. `let v = Some(42); v.1 == 42`). `arg(i)`
returns `0` for out-of-range indices.

### 2.8 Generics (not implemented)

```q
fn first<T>(arr: [T]) -> T { return arr[0] }

fn map<T, U>(arr: [T], f: fn(T) -> U) -> [U] {
    let result = [U]()
    for item in arr { result.push(f(item)) }
    return result
}
```

NOT implemented. `fn map<T, U>(...)` fails at compile time with
`undeclared variable: U` — there is no generic type-parameter resolution yet.
These examples describe the target syntax only.

### 2.9 Traits / Interfaces (implemented — qc-0.0.13)

```q
trait Drawable {
    fn draw(self) -> int
}
impl Drawable for Circle {
    fn draw(self) -> int { return self.radius * 2 }
}
```

Working: `trait` + `impl ... for ...`, dispatch through a trait-typed
parameter (`fn draw_shape(d: Drawable) { ... d.draw() ... }`). Note: direct
method-call dispatch (`c.draw()`) is NOT yet verified — use trait-typed params.
`interface`, associated types, and `where` clauses remain NOT implemented.

### 2.10 Declarations & assignment

```
let x = 10            // new binding
x = x + 1             // assign to existing
```

`let` shadows previous bindings (newest wins). Type inferred from RHS.

### 2.11 Control flow

```q
if cond { ... } else if cond { ... } else { ... }
loop { ... break continue }
while cond { ... }
for i = start; cond; step { ... }
for x in [1, 2, 3, 4] { ... }    // for-in over array
```

- `cond` truthy when non-zero.
- `&&`, `||`, `and`, `or` short-circuit.
- `break`/`continue` target innermost loop.
- For-in: `for x in arr { ... }` iterates array elements; nested for-in works.
  In a `for x in arr` loop, `arr[-1]` evaluates to the array length
  (IR_ARRAY_LEN), e.g. `for i in [0 .. arr[-1]]`-style indexing. Verified:
  for-in sum=10, nested=66, arrlen=3, break=3.

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

```q
unsafe { ... }
```

Opts OUT of overflow/shift/bounds traps. Counted globally; audit report on
success when count>0. Malformed (no `{`) → compile error.

Raw pointers work at the op level inside `unsafe`: `&x` takes an address and
`*p` dereferences it. ⚠️ Known gap: a raw-pointer **type annotation**
(`let p: *u64 = &x`) explodes the IR — do not annotate pointer types; let
`&x` / `*p` infer. `unsafe` blocks compile and run correctly.

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
