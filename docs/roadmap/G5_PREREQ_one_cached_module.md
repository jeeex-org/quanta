# G5 prerequisite: one cached module must compile to a working binary

## Status: OPEN. Not fixed.

## Minimal deterministic reproducer

The cleanest reduction found so far. No ASLR trick, no multi-module
matrix, no 9378-file `lib/std`:

```
proj/
  lib/std/m.quanta   fn h(x) { return x + 1 }
  main.quanta        import std/m
                     fn main() { printi(h(41)) return 0 }
```

| condition                          | result                     |
|------------------------------------|----------------------------|
| no `lib/std/m.qobj`                 | rc=0, prints `42`          |
| `lib/std/m.qobj` present (401 B)    | rc=-4 (SIGILL), no binary  |

The source path is sound. The failure is entirely inside the cache path.

## Facts established by measurement

1. The cache file is **well-formed**. Parsed field by field with the
   correct record layout (`op@0, res@8, a0@16, a1@24, a2@32`), the IR for
   `fn h(x) { return x + 1 }` is exactly right:
   `PARAM res=0`, `CONST res=3 a0=1`, `ADD res=2 a0=0 a1=3`,
   `RET res=0 a0=2`. Writer and reader agree on every offset. G1/G2 hold.

2. Object mode (`--emit-obj`) crashes identically, so this is **not** the
   linker or the exec-mode PLT path. It is in compilation proper.

3. Failure does not depend on the imported function's *body*:

   | module                    | fault                    |
   |---------------------------|--------------------------|
   | `fn h(x){return x+1}`     | SIGILL @ 0x42886c        |
   | `fn h(){return 7}`        | SIGILL @ 0x42886c        |
   | `fn h(x){return 0}`       | SIGILL @ 0x42886c        |
   | `fn h(x){return x}`       | SEGV @ 0x7f...0018       |
   | 2 functions               | SEGV @ 0x42886c          |

   So it is not about calling a cached function, or its parameters, or
   its body. **Any** cached function breaks it.

4. All three `src` appends in the reader write a NUL terminator and are
   bounded by `SRC_CAP`. The function name, the return-type name, the
   param names and the string-pool entries are all well-formed.

5. `fns` layout is consistent: reader and `sfn()` both use offsets
   0/8/16/24/32/40/48 against `FNS = 56`. Not a stride bug.

6. `qimp_slot[i] = fnc` (local -> global map) is used consistently by the
   writer and the IR-stamping loop. Not an index-space mixup.

## What the fault actually is

gdb, breakpoint on the faulting instruction:

```
0x4271b1:  mov (%rdi), %rax      rdi = 0x7fffda400018
retaddr on stack = (nil)
#1  0x0000000000000000
```

The **return address on the stack is 0**. The function was entered with a
corrupted or absent return address -- a stack-frame imbalance, or a jump
into the function rather than a call. It is not a bad pointer argument.

The other variant (`0x42886c`) is `ovf_trap_emit`'s `ud2`:

```
mov  $0xa,%eax
imul %rax,%rdx      <- X * 10
jno  +2
ud2                 <- X overflowed
```

That is `val*10 + d` in the number lexer, i.e. the compiler lexing a
numeric literal with a garbage accumulator.

## The recurring defect class

Across this whole investigation almost every bug has been one shape:
**state the source path establishes as a side effect of parsing, which a
cache-imported function skips** because it reuses numbers baked into
serialised IR instead of allocating them. Already fixed:

- `opt_func` liveness scans bounded by global `irc` (`61f341e6`)
- `ir_unsafe` per IR record
- per-vreg tables: `vreg_is_str`, `vreg_is_big`, `vreg_clo`,
  `vreg_to_param`, `vreg_type`
- per-function tables: `fn_defargs`, `fn_generic`, `fn_genparam_base`,
  `fn_genparam_names`, `fn_parfn`, `fn_pdfixed`
- the dead `gpatches_a` arena feeding uninitialised relocations
- `meta_bytes` counted from `fn_count` when only IR-bearing fns are written
- the `(fn*200 + k)` param-table overrun

Each was real. None closed this. Nine instances of the same family have
now been found and fixed, and the fault persists -- which is the signal
that the remaining one is not in that family.

## Why static reading stopped working

Valgrind reports none of this: every instance is an in-bounds read of
memory that was never written, or a write inside a mapping the allocator
had reserved. Valgrind's replacement allocator returns zeroed pages,
which makes the bad values self-consistent. 12 consecutive valgrind runs
came back clean while the plain build failed 11 times in 20.

Six further hypotheses were found by reading code, fixed, and measured as
not moving the failure. Reading is exhausted for this bug.

## Next step

Not another in-source initialisation -- nine of those have each moved the
symptom without closing it. The next step is to make the *self-hosting
compiler* carry the missing state instead:

The root asymmetry is that a `.qobj` serialises **IR only**. The source
path gets its per-function and per-vreg tables from the parser as a side
effect; a cache carries none of them. Every fix so far re-creates a few of
those tables by hand at import time, which is why the list never ends.
The structural fix is either to serialise the tables in the cache, or to
make the cache path allocate vregs the same way the parser does
(assign `nv()` for each vreg the IR references, in order) so the tables
are populated by the same code that populates them for source functions.

## Test that must pass before G5 starts

```
lib/std/m.qobj present, m.quanta ABSENT
main.quanta = import std/m + call
=> rc=0, prints 42
```

Run it 8 times, require 8/8. Then the G5 matrix proper: multiple cached
modules, nested dependencies, cross-module calls, all imported sources
removed.
