# Compiler flags

`qc [flags] <source.quanta> <output>`

The default is a statically linked native executable with no libc dependency.
Everything below is optional.

## Native (default)

No flags. Strings, byte indexing, NUL termination, raw syscalls, raw memory and
the native allocator all work without linking anything. A native program must
compile with no flags and come out statically linked; the gate's `native` stage
asserts exactly that.

```sh
qc prog.quanta out          # native, static, no libc
qc -O prog.quanta out       # same, explicit optimisation
```

## Interop — optional

Quanta is native first. These exist for the cases native code genuinely cannot
cover, and nothing in the language requires them.

### `--emit-obj` — relocatable object

Emits a `.o` with `R_X86_64_PLT32` relocations for the system linker to resolve.
`extern "C"` works here, which is how the multi-TU tests link.

```sh
qc --emit-obj a.quanta a.o
ld a.o b.o -o out          # or: qc --link a.o out
```

### `--emit-dynamic` — dynamically linked executable

Adds `PT_INTERP` and `PT_DYNAMIC` so the runtime loader resolves `extern "C"`
calls. Off by default. Produces a binary that needs `ld.so` and libc present.

```sh
qc --emit-dynamic prog.quanta out
```

### `--lib <soname>` — depend on a named shared library

Repeatable and additive, for use with `--emit-dynamic`. Without it a dynamic
binary could only ever need `libc.so.6`; this is how you reach `libcuda.so.1`,
`libm`, `libstdc++`, `libssl` or anything else.

```sh
qc --emit-dynamic --lib libcuda.so.1 prog.quanta out
qc --emit-dynamic --lib libm.so.6 --lib libssl.so.3 prog.quanta out
```

`libc.so.6` is always seeded, so `--emit-dynamic` alone behaves as before. Each
`--lib` adds one `DT_NEEDED` in the order given.

### `--emit-dynamic` without `--lib` in EXEC mode

An `extern "C"` in static EXEC mode is a hard error:

```
error: extern "C" needs --emit-dynamic
```

It used to emit a binary that segfaulted on the first call, which reads as though
the user's program were broken. `--emit-obj` is exempt: it emits relocations for
the system linker, and the multi-TU tests depend on that.

## Other flags

| flag | effect |
|---|---|
| `-O` | optimise (currently explicit-opt-in) |
| `--no-overflow-trap` | turn the overflow trap OFF. Trapping is ON by default (secure by default); disable only for code relying on two's-complement wraparound that has not been ported |
| `--no-start` | secondary object TU; omit the `_start` stub |
| `--emit-qobj` | emit a `.qobj` module cache instead of an executable |
| `--link <in.o> <out>` | link an object file with libc |

## Known gaps

- **No indirect call.** `f(x)` where `f` is a runtime value is a compile error
  (`call to undeclared function: f`). `closure_call` takes a `[codeptr, env]`
  tuple, not a bare pointer. This is why `dlopen`/`dlsym` are not currently
  reachable natively — they are libc *functions*, not syscalls, so `syscall()`
  cannot reach them either. Until indirect call exists, `extern "C"` is the only
  way out of the language.
- **Float return values look wrong.** `fn half(x: f64) -> f64 { return x / 2.0; }`
  called as `half(10.0)` does not compare equal to `5.0`, and `let b = r;
  printi(b)` prints the bit pattern of the *argument*. This reproduces with a
  purely native function, so it is in codegen, not in the linking or extern
  path. Not yet diagnosed.
