# Quanta Programming Language

Quanta designed with simple syntax that supports multiple execution modes: Native compilation, Pre-compilation, Interpreter, JIT and WebAssembly.

## Status (verified)

- **Native AOT compilation (`qc`)** — **ACTIVE, 0.0.134**. x86-64 only
  (AArch64 backend deferred POST-0.1.0).
  Bootstraps via a **self-host fixpoint**: the committed
  `compiler/${VERSION}/bin/x86/qc` compiles its own source to a byte-identical
  `qc` (verified fixed point). Full gate (all 11 layers GREEN): functional **163/163** (+ extern-c,
  extern-ld, security, perf 3/3, valgrind-clean, fuzz fail-closed 0 crashes,
  differential -O==no-O + vs-seed consistent, generics-negative, stdlib 9/9,
  multi-tu 3/3).
- **Interpreter (`qc --interp`)** — PLANNED (Stage 1). Not yet landed.
- **Pre-compilation (`go run` style)** — PLANNED (Stage 2).
- **WebAssembly** — PLANNED (Stage 3).
- **ARM64 backend** — PLANNED (Stage 4, clean rewrite from scratch).
- **JIT** — PLANNED (Stage 5).

Security: secure-by-default — signed-overflow and out-of-bounds traps
(`SIGILL`, exit 132), opt-out via `unsafe {}`.

## Syntax at a glance

Quanta has **no semicolons** — statements are separated by newlines (or spaces,
as in `x = 10 y = 20`). Blocks use `{ }`. Everything is an expression;
the last expression of a function body is its return value (so `return` is
optional). **`fn`, `let`, and `return` are all optional** — you can write a
complete program in the bare "simplified" surface, or use the explicit forms.

```quanta
// FULL form (explicit fn / let / return)
fn main() {
    let x = 10
    let y = 20
    return x + y
}

// SIMPLIFIED form (no fn, no let, no return — implicit) — byte-for-byte equivalent
main() {
    x = 10
    y = 20
    x + y
}
```

The simplified surface is bash-like and extremely low-ceremony:

| Surface | Optional keyword | What's implicit |
|---------|-----------------|----------------|
| Function def | `fn` | `name(params) { }` at top level already defines a function |
| Local binding | `let` | `name = expr` inside a function = a local |
| Return | `return` | the last expression of a block is the return value |
| Condition parens | `( )` | `if x > 0 { }` — no parens needed around the condition |

Bare `main()` / `init()` work with or without `fn`. Example with optional
parens:

```quanta
// all three are equivalent
if number % 2 == 0 { prints("even\n") }
if (number % 2 == 0) { prints("even\n") }
if number % 2 == 0 prints("even\n")
```

Accessing globals vs locals is explicit via **sigils** (this is the one place
Quanta is not "bare" — it borrows bash's `${}`/`$[]` idea so there is never
ambiguity about scope):

```quanta
global user = "admin"          // writable global (or: const for read-only)

greet() {                       // bare function (no fn)
    who = "James"               // bare local (no let)
    print("hi " .. $[who] .. " " .. ${user})   // $[local] and ${global} bare
    print("hi ${user}, welcome $[who]!")        // same sigils inside strings
}
```

Sigil rules:
- `${name}` → **global** (read from the global slot; `${name} = x` writes it).
- `$[]` → **local** (read a local; used inside strings for interpolation).
- Inside a string, `${global}` and `$[local]` interpolate directly — no
  concatenation needed.
- A bare `name` with no sigil resolves by normal scoping (local if inside a
  function, otherwise global).

Compile and run (native AOT):

```bash
qc yourfile.quanta yourbinary
./yourbinary
```

## Examples

### Variables, arithmetic, and printing

```quanta
fn main() {
    let x = 10
    let y = 20
    let sum = x + y
    prints("Sum: ")
    printi(sum)
    prints("\n")
    return 0
}
```

### Conditionals (if / else)

```quanta
fn main() {
    let number = 7
    if number % 2 == 0 {
        prints("Even number\n")
    } else {
        prints("Odd number\n")
    }
    return 0
}
```

### Loops: `loop` with `break` / `continue`

```quanta
fn main() {
    let i = 0
    let s = 0
    loop {
        i = i + 1
        if i > 10 { break }
        s = s + i
    }
    prints("Sum 1..10 = ")
    printi(s)        // 55
    prints("\n")
    return 0
}
```

### Loops: `while`

```quanta
fn main() {
    let i = 0
    let s = 0
    while i < 5 {
        prints("i = ")
        printi(i)
        prints("\n")
        i = i + 1
    }
    return 0
}
```

### Iteration: `for ... in` over an array literal

```quanta
fn main() {
    let s = 0
    for x in [1, 2, 3, 4] {
        s = s + x
    }
    prints("Sum = ")
    printi(s)        // 10
    prints("\n")
    return 0
}
```

### Functions, recursion, and return values

```quanta
fn factorial(n) {
    if n <= 1 { return 1 }
    return n * factorial(n - 1)
}

fn main() {
    let result = factorial(5)
    prints("Factorial of 5 is ")
    printi(result)   // 120
    prints("\n")
    return 0
}
```

### Arrays and indexing

```quanta
fn main() {
    let a = [100, 200, 300]
    let second = a.1          // 200
    prints("second = ")
    printi(second)
    prints("\n")
    return 0
}
```

### Structs

```quanta
struct Point { x y }

fn make(a, b) {
    return Point(a, b)
}

fn main() {
    let p = make(3, 4)
    prints("x + y = ")
    printi(p.x + p.y)     // 7
    prints("\n")
    return 0
}
```

### Enums and `match`

```quanta
enum Color {
    Red,
    Green,
    Blue,
}

fn main() {
    let c = Color.Green
    let v = match c {
        Color.Red   => 42,
        Color.Green => 2,
        Color.Blue  => 3,
    }
    prints("value = ")
    printi(v)            // 2
    prints("\n")
    return 0
}
```

`match` also works on integers and supports a `_` catch-all arm:

```quanta
fn main() {
    let x = 5
    let n = match x {
        1 => 10,
        2 => 20,
        _ => 30,
    }
    return n            // 30
}
```

### `const` (compile-time constants)

```quanta
const A = 3
const B = A * 4       // 12
const C = B + 2       // 14

fn main() {
    let y = A + B + C
    printi(y)          // 29
    prints("\n")
    return 0
}
```

### `defer` (runs at function exit, LIFO)

```quanta
global counter = 0

fn get() -> i64 {
    defer { counter = counter + 1 }
    defer { counter = counter + 2 }
    counter = counter + 8
    return 1
}

fn main() {
    get()
    exit(counter)      // 8 + 2 + 1 = 11
}
```

### `unsafe` blocks (opt out of overflow/bounds traps)

```quanta
fn main() {
    unsafe {
        return 42
    }
}
```

### Closures and function pointers

```quanta
fn add(a, b) {
    return a + b
}

fn main() {
    let f = mk_any(fnptr(add), 0)
    let r = closure_call(f, 3, 4)
    printi(r)          // 7
    prints("\n")
    return 0
}
```

### File I/O

> Quanta strings are length-prefixed (`[8-byte len][data]`). Syscalls that take
> a C string expect the data pointer, so pass `string + 8` to skip the prefix.

```quanta
fn main() {
    let path = "test_suites/codes/simple.quanta" + 8
    let fd = file_open(path, 0)
    printi(fd)         // a valid file descriptor (> 0)
    prints("\n")
    return 0
}
```

### Floating-point math

> **Float literals are now parsed** (since 0.0.61): `3.14`, `-0.5`, `123.456` compile to float
> values and `println(3.14)` prints `3.140000`. They flow through `i2f`/`f2i` and the
> `println` float path like any other float. As of 0.0.62, float literals (and any float
> vreg) are correctly consumed by the float builtins directly — `f2i(3.14)` prints `3`,
> `fadd(1.5, 2.5)` prints `4`, `fmul(2.5, 4.0)` prints `10`, etc. (int args to those
> builtins still work, e.g. `fadd(3, 4)` prints `7`).

```quanta
fn main() {
    let a = i2f(25)
    let b = i2f(10)
    let eq = feq(a, b)        // 0 (false)
    let gt = fgt(a, b)        // 1 (true)
    let root = sqrt(i2f(144)) // i2f(12)
    printi(gt)
    prints("\n")
    return 0
}
```

### Low-level: syscalls and memory

```quanta
fn main() {
    let buf = mem_alloc(64)
    let n = getrandom(buf, 16, 0)
    printi(n == 16)     // 1 on success
    prints("\n")
    return 0
}
```

## Architecture: one IR, N backends

The front-end (lexer → parser → IR) and the Tier-1 optimizer are written
**once**; every execution mode is a backend over the same IR. This is the
key design decision that makes multi-mode tractable and keeps all modes
behaviorally consistent (identical exit codes, traps, ABI).

```
source.quanta → core/scan/parse → IR → opt/ → backend (codegen/x86_64 | run/interp | run/wasm | ...)
```

Current source form: a multi-file self-hosting tree at
`compiler/0.0.74/src/x86/` (`main.quanta` + `helpers`/`lexer`/`parse`/
`codegen`/`emitter`/`elf`/`globals`/`features.quanta`). The modular split
is DONE. `#import` is still not functional (a future stage).

## Verification (the green-state invariant)

Every change is gated by:

```bash
# self-host fixpoint: committed compiler/${VERSION}/bin/x86/qc compiles its own source byte-identically
cd compiler/$(cat VERSION)/src/x86
SEED=../../../../compiler/$(cat VERSION)/bin/x86/qc
$SEED main.quanta qc && ./qc main.quanta qc2 && ./qc2 main.quanta qc3   # qc == qc2 == qc3 (fixed point)
# full gate (all 8 layers)
bash test_suites/scripts/run_tests.sh
```

Promotion history and version-bump rules are maintained in-repo
(see `docs/ROADMAP.md` for the public promotion timeline).

## Documentation

- [`docs/SYNTAX.md`](docs/SYNTAX.md) — language syntax specification
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — SME handoff + design (read
  this to take over development)
- [`docs/LANGUAGE_DESIGN.md`](docs/LANGUAGE_DESIGN.md) — multi-mode architecture
  and staged roadmap
- [`docs/FEATURES.md`](docs/FEATURES.md) — shipped vs. to-do feature inventory
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — consolidated roadmap
- [`docs/SPEC.md`](docs/SPEC.md) — formal language specification (tool-qualification)
