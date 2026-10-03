# Compiler defect: first-call-wins on `-> f64` calls in std/math

Found 0.0.222, while implementing fdlibm argument reduction for `sinf`/`cosf`/
`tanf`. The reduction itself is correct and was verified bit-exact; it cannot be
shipped because of the defect below, which makes any `-> f64` function's result
depend on what else the program called first.

## Symptom

`reduce(0.5)` returns the right bits in some programs and a constant wrong value
in others, with no difference in the source of `reduce` itself.

    // program A                          // program B
    println(f64bits(reduce(0.5)))         println(f64bits(qmult(0.5)))
                                          println(f64bits(reduce(0.5)))

    A -> -4336984033343832063             B -> 4602678819172646912   (correct)
         (uninitialised / garbage)

The wrong value is stable across runs and across recompiles, so it is not
uninitialised memory in the ordinary sense -- it is a deterministic codegen
mistake keyed on call ORDER.

## The rule

`reduce` is correct if and only if `qmult` is called somewhere in the program
BEFORE it. `reduce` calls `qmult` itself, so an extra explicit earlier call
"fixes" it.

    reduce only                          -> wrong
    qmult then reduce                    -> correct
    pio2_1 then reduce                   -> wrong
    pio2_1t then reduce                  -> wrong
    qmult + pio2_1 then reduce           -> correct
    qmult + pio2_1t then reduce          -> correct
    pio2_1 + pio2_1t then reduce         -> wrong

Only `qmult` matters. It is the one callee whose body contains the 2^52 magic
constant and a pair of guarded early returns; `pio2_*` are single-expression
`return f64of(...)` bodies.

## What is NOT the cause

Ruled out by direct test, so nobody repeats it:

- not the argument-passing ABI: `qmult(x)` with a local float and with a literal
  both return 0 correctly;
- not untyped-float-return: every helper here carries `-> f64`;
- not the number of call sites in the callee body: a 1-stage `reduce` with two
  call sites is wrong the same way a 4-stage one is;
- not function definition order in the module: moving `reduce` earlier changes
  nothing;
- not stack depth: a chain of 8 nested `-> f64` calls is correct;
- not `floor()`, which is simply not a builtin -- calling it returns its
  argument unchanged, which is a separate trap;
- not `mem_alloc` inside the callee: removing it entirely changed nothing.

Every individual step is correct when executed alone:

    qmult(0.5)            -> 0                     correct
    pio2_1()              -> 4609753056924401664   correct
    0.5 - q*a - q*b       -> 4602678819172646912   correct, in main
    reduce(0.5)           -> wrong                 in the same program

So the arithmetic is right and the codegen loses it.

## Suspected cause

A float vreg is being coalesced or reused across call boundaries when the callee
is a `-> f64` function reached by call, and the first call in the program is the
one that establishes -- or fails to establish -- the register class. The fact
that a prior `qmult` call fixes it says the register class is decided once and
then not revisited.

`-> f64` on a USER function is a distinct path from the builtin path: the six
builtin integer-argument fix (sqrt/log/sin/cos/tan/abs, commit 0d7950b6) added
`as_f64_rdi()` on the emitter's builtin dispatch. Nothing equivalent exists for
user `-> f64` calls, and that is where to look.

## Where the sin work is

`/tmp/negctl/math.sin-attempt` holds the fdlibm implementation: the 3x33-bit
pi/2 table (generated from fdlibm's literals, with PIO2_1 + PIO2_1T == pi/2
exactly), `qmult`, `quadrant`, and `reduce`. Every step is verified correct in
isolation. It is not in the tree because the defect above makes `reduce` -- and
therefore `sinf` -- unreliable, and shipping a transcendental that is right only
in some programs is worse than the x87 one whose worst case is 57 ULP.

Once the defect is fixed, re-applying that file is the whole change; the
accuracy claim to verify afterwards is `sin(x)` near pi, which x87 got 19558 ULP
out of, and 1e15, which it got 7.7e-7 relative out of.
