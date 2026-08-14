# Quanta Programming Language

Quanta designed with simple syntax that supports multiple execution modes: Native compilation, Pre-compilation, Interpreter, JIT and WebAssembly

> **Vocabulary:** "frontend" / "backend" refer to *domain capability*
> (web UI vs server/systems). The compiler itself is organized by *stage*
> (core / scan / parse / opt / codegen / run). See
> [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Status (verified)

- **Native AOT compilation (`qc`)** — **ACTIVE, 0.0.46**. x86-64 only.
  Self-hosts with a **byte-identical fixed point** (3-stage: qc_boot → qc_self
  → qc, all identical), and passes **81/81** test_suites (+ 6/6 security,
  3/3 perf). Valgrind-clean (the mmap address-hint crash is fixed).
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

Current source form: a multi-file self-hosting tree at
`compiler/0.0.46/src/x86/` (`main.quanta` + `helpers`/`lexer`/`parse`/
`codegen`/`emitter`/`elf`/`globals`/`features.quanta`). The modular split
is DONE. `#import` is still not functional (a future stage).

## Verification (the green-state invariant)

Every change is gated by:

```bash
# recompile the compiler with the bootstrap seed (3-stage self-host)
cd compiler/0.0.46/src/x86
SEED=/opt/tali/quanta/bootstrap/qc-bootstrap-0.0.45
$SEED main.quanta qc_boot && ./qc_boot main.quanta qc_self && ./qc_self main.quanta qc
# self-host fixed point (qc_boot == qc_self == qc) + 81/81 regression
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
