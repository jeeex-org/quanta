# Quanta Programming Language

Quanta designed with simple syntax that supports multiple execution modes: Native compilation, Pre-compilation, Interpreter, JIT and WebAssembly

## Status
- Native compilation (`qc`) — [Active] (qc-0.0.14-wip: P10 for-in loops working — nested for-in, `arr[-1]` array-length, unsafe blocks; 39/39 tests pass + for-in regression tests; self-host fixed-point verified; P10 generics next. Stable: qc-0.0.13 P9 traits/impl/vtable dispatch/struct literals on x86_64 and ARM64)
- Pre-compilation (`qc run`) — [Planned]
- Interpreter (`qc --mode int`) — [Planned]
- JIT (`qc --mode jit`) — [Planned]
- WebAssembly (`qc --mode wasm`) — [Planned]

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
