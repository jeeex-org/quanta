# Quanta Programming Language

Quanta designed with simple syntax that supports multiple execution modes: Native compilation, Pre-compilation, Interpreter, JIT and WebAssembly

## Status
- **Native compilation (`qc`)** — [Active] **qc-0.0.19 promoted** (x86_64 self-host fixed-point + ARM64 cross-compile 61/61 device tests verified). Stable base: qc-0.0.18 (P11 SIMD vec128).
- Pre-compilation (`qc run`) — [Planned]
- Interpreter (`qc --mode int`) — [Planned]
- JIT (`qc --mode jit`) — [Planned]
- WebAssembly (`qc --mode wasm`) — [Planned]

## Promotion Workflow (Guarded)
Promotions are **not manual** — they use `scripts/promote.sh` with hard regression guards:

```bash
./scripts/promote.sh <version> <wip_source>
# Example: ./scripts/promote.sh 0.0.19 src/qc-0.0.19-wip.quanta
```

**Guards enforced (fail fast, leave repo clean):**
1. **x86 self-host fixed-point** — stage1 == stage2 byte-identical
2. **ARM64 cross-compile 61/61** — all 61 tests compile cleanly
3. **ARM-01 hardware 61/61** — all 61 tests PASS on device (no "known gaps" allowed)
4. **Old version removed from git** — stale binaries/source deleted before commit
5. **bin/qc symlink updated** — points to new x86_64 binary

If ANY guard fails, script exits non-zero, no partial commit.

## Getting Started
```quanta
qc example/hello-work.quanta -o hello-world
./hello-world
```

## Documentation

The complete Quanta language specification is available in [`docs/SYNTAX.md`](docs/SYNTAX.md).

## Example Code

Here's a simple "Hello, World!" example:

```quanta
fn main() {
    prints("Hello, world!\n");
    return 0;
}
```

### Variables and basic arithmetic

```quanta
fn main() {
    let x: i32 = 10;
    let y: i32 = 20;
    let sum: i32 = x + y;
    prints("Sum: ");
    printi(sum);
    prints("\n");
    return 0;
}
```

### Loop (for loop)

```quanta
fn main() {
    let mut i: i32 = 0;
    loop i < 5 {
        prints("i = ");
        printi(i);
        prints("\n");
        i = i + 1;
    }
    return 0;
}
```

### If-Else statement

```quanta
fn main() {
    let number: i32 = 7;
    if number % 2 == 0 {
        prints("Even number\n");
    } else {
        prints("Odd number\n");
    }
    return 0;
}
```

### Array usage

```quanta
fn main() {
    let numbers: [i32; 5] = [1, 2, 3, 4, 5];
    let mut sum: i32 = 0;
    let mut i: i32 = 0;
    loop i < 5 {
        sum = sum + numbers[i];
        i = i + 1;
    }
    prints("Sum of array: ");
    printi(sum);
    prints("\n");
    return 0;
}
```

### Function with parameters and return

```quanta
fn factorial(n: i32) -> i32 {
    if n <= 1 {
        return 1;
    }
    return n * factorial(n - 1);
}

fn main() {
    let n: i32 = 5;
    let result: i32 = factorial(n);
    prints("Factorial of ");
    printi(n);
    prints(" is ");
    printi(result);
    prints("\n");
    return 0;
}
```