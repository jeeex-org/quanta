# Quanta Programming Language

Quanta designed with simple syntax that supports multiple execution modes: Native compilation, Pre-compilation, Interpreter, JIT and WebAssembly

> **Vocabulary:** "frontend" / "backend" refer to *domain capability*
> (web UI vs server/systems). The compiler itself is organized by *stage*
> (core / scan / parse / opt / codegen / run). See
> [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Status (verified)

- **Native AOT compilation (`qc`)** — **ACTIVE, 0.0.21**. x86-64 only.
  Self-hosts with a **byte-identical fixed point** (the compiler fully
  regenerates itself), and passes **62/62** test_suites.
- **Interpreter (`qc --interp`)** — PLANNED (Stage 1). Not yet landed.
- **Pre-compilation (`go run` style)** — PLANNED (Stage 2).
- **WebAssembly** — PLANNED (Stage 3).
- **ARM64 backend** — PLANNED (Stage 4, clean rewrite from scratch).
- **JIT** — PLANNED (Stage 5).

Security: secure-by-default — signed-overflow and out-of-bounds traps
(`SIGILL`, exit 132), opt-out via `unsafe {}`.

## Architecture: one IR, N backends

The front-end (lexer → parser → IR) and the Tier-1 optimizer are written
**once**; every execution mode is a backend over the same IR. This is the
key design decision that makes multi-mode tractable and keeps all modes
behaviorally consistent (identical exit codes, traps, ABI).

```
source.quanta → core/scan/parse → IR → opt/ → backend (codegen/x86_64 | run/interp | run/wasm | ...)
```

Current source form: a single self-hosting file at
`compiler/0.0.21/src/x86/main.quanta`. The modular tree
(`core/ scan/ parse/ ir/ opt/ codegen/ run/`, capability libs in
`lib/<domain>/`) is the target structure — see `docs/ARCHITECTURE.md`.
Note: `#import` is **not yet functional**, so the split requires a module
system first (a future stage, not just file moves).

## Verification (the green-state invariant)

Every change is gated by:

```bash
# recompile the compiler with the bootstrap seed
./bootstrap/qc-bootstrap-0.0.20 compiler/0.0.21/src/x86/main.quanta compiler/0.0.21/bin/x86/qc
# self-host (must exit 0) + 62/62 regression
bash test_suites/scripts/run_tests.sh
```

Promotion history and rules live in `systems/PROMOTION_RULES.md` /
`systems/PROMOTION_VERSION_RULES.md`.

## Getting Started

```quanta
fn main() {
    prints("Hello, world!\n");
    return 0;
}
```

Compile and run (native AOT):

```bash
qc yourfile.quanta yourbinary
./yourbinary
```

## Documentation

- [`docs/SYNTAX.md`](docs/SYNTAX.md) — language syntax specification
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — SME handoff + design (read
  this to take over development)
- [`docs/LANGUAGE_DESIGN.md`](docs/LANGUAGE_DESIGN.md) — multi-mode architecture
  and staged roadmap

## Example Code

### Variables and basic arithmetic

```quanta
fn main() {
    let x = 10;
    let y = 20;
    let sum = x + y;
    prints("Sum: ");
    printi(sum);
    prints("\n");
    return 0;
}
```

### Loop

```quanta
fn main() {
    let i = 0;
    loop i < 5 {
        prints("i = ");
        printi(i);
        prints("\n");
        i = i + 1;
    }
    return 0;
}
```

### If-Else

```quanta
fn main() {
    let number = 7;
    if number % 2 == 0 {
        prints("Even number\n");
    } else {
        prints("Odd number\n");
    }
    return 0;
}
```

### Function with parameters and return

```quanta
fn factorial(n) {
    if n <= 1 { return 1; }
    return n * factorial(n - 1);
}

fn main() {
    let result = factorial(5);
    prints("Factorial of 5 is ");
    printi(result);
    prints("\n");
    return 0;
}
```
