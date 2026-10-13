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

## MECHANISM CONFIRMED at the instruction level (0.0.235)

Two isolated programs, identical except that A contains an **unreachable** `qmult` call and B does not:

    A  fn main() { if 0 == 1 { println(f64bits(qmult(0.5))) } println(f64bits(reduce(0.5))) }
    B  fn main() { println(f64bits(reduce(0.5))) }

    A -> 4602678819172646912   (correct)      B -> -4336984033343832063   (garbage)

**The dead, never-executed call fixes it.** So the trigger is compile-time bookkeeping, not execution —
and the two binaries are the same size (8912 bytes, 835 differing bytes), so nothing is added, only
re-encoded. Diffing the instruction streams isolates the site:

    B : f2 48 0f 2a c0   cvtsi2sd %rax,%xmm0     <- CONVERTS the value (int -> double)
    A : 66 48 0f 6e c0   movq     %rax,%xmm0     <- MOVES the bits

The value here is an f64 **bit pattern already in a GPR** — exactly what `f64of(<bits>)` produces, and what
`return f64of(...)` bodies like `pio2_1()` return. The correct encoding is `movq`; B instead converts the bit
pattern as if it were an integer, which is where the garbage comes from. Which encoding is emitted is decided
by a GLOBAL flag reflecting whether a `-> f64` call has been compiled *somewhere in the program*, not by the
value's own `vfloat` tag — hence "first call wins", and hence why a dead call in an unrelated function changes
another function's arithmetic.

## Hypotheses ELIMINATED by reading the code (0.0.235) — do not re-test these

Both of the obvious "stale tag" explanations are wrong, and each cost one read:

1. **"`f64of` does not tag its result."** It does: the handler at `emitter.quanta:1259` ends with
   `sdef(irres(ii), 0)` and `w8(vfloat+irres(ii), 1)`, and it emits `fld_x(7,0)` / `fst_x(0,0)`
   (`movq`), with a comment saying it must be `0F 7E` and not `0F 2A` "which reinterprets the bits as an
   integer". The handler is correct.
2. **"`vclr()` does not clear `vfloat`."** It does (`helpers.quanta:586-587`), and correctly: every clearing
   loop in `vclr()` — `vreg_type`, `vfloat` (its own `w8` loop, since 0 is its unset value), and the four
   `-1`-sentinel tables — runs *before* `varc = 0; vreg_n = 0` on line 608, so the loops still see the
   previous function's range. Also correct.

## Where it is now narrowed to

- The wrong encoding is at an **early** instruction index (line 190 of the dump), i.e. inside a function
  emitted long before `main` — yet an unreachable call *in main* changes it. So the decision is fed by
  whole-program information gathered before codegen, not by the state at the emit site. `funcscan`'s
  type/tag pass is the place that sets `vfloat` for parameters and returns from whole-program evidence
  (`codegen.quanta:205-220` tags parameters after that pass).
- The site itself is the `movq`-vs-`cvtsi2sd` choice when a value that already IS an f64 bit pattern in a GPR
  is fed to an SSE operation — `fopld_rr`'s callers (`codegen.quanta:1418-1420`, `1647-1650`). The compiler's
  own comments record the same symptom in **both** directions (`803-805`: `movq` where `cvtsi2sd` was wanted;
  `1229`: `cvtsi2sd` where `movq` was wanted), so whatever selects between them is not a single missing tag.
- Next probe: print `vfloat[irres(...)]` for the operand at the emit site in both programs, and the same for
  the value in the funcscan pass. That distinguishes "tag never set" from "tag set to the wrong value", which
  the two reads above did not.

## THE DECISION, FOUND (0.0.235) — `fopld_rr`, `emitter.quanta:928-930`

    if r8(vfloat+a)==1 { fld_x(sc, xmm) } else { fi2f_gp(xmm, sc) }     // spilled case
    if r8(vfloat+a)==1 { fld_x(r,  xmm) } else { fi2f_gp(xmm, r)  }     // register case

`fld_x` is the `movq` (raw bits — correct when the value already is an f64 pattern); `fi2f_gp` is the
`cvtsi2sd` (int -> double, which mangles it). So the single question is whether **`vfloat[operand]` is 1**, and
in program B it is not.

That also frames the fix. The gate already has a layer for exactly this — `float-return : GREEN (a call to a
-> f64 function tags its result; fixed 0.0.220)` — so the mechanism exists and works for the simple case; A6's
shape is one where the tag does not reach the operand. The operand here is a value crossing a `-> f64`
**call boundary** inside the reduction (`pio2_1()`, and the result of `qmult`), which is what `as_f64_rdi()`
(0d7950b6) fixed for the *builtin* path and what has no equivalent for the *user-function* path.

Next probe (narrow, one build): print `a` and `r8(vfloat+a)` at those two lines for programs A and B, and the
same at the point where a `-> f64` user call's result vreg is bound. That says whether the tag is never set on
the call result or is set and then overwritten by the caller's own vreg churn.

## PROBE RESULT (0.0.235): the tag is NEVER SET on that operand

`dbg_num` instrumentation on `fopld_rr`'s register-case line, printing `a`, `r` and `r8(vfloat+a)` per decision,
run on the two isolated programs (same binary, same build):

    B (no qmult call):    X2 01   X4 1 1   X 0 0 0   X3 2 1   X15 0 1   X18 1 1
    A (dead qmult call):  X2 01   X4 1 1   X 0 0 1   X3 2 1   X15 0 1   X18 1 1

Exactly one decision differs, and it is the `movq`-vs-`cvtsi2sd` one: operand vreg 0, already in a register
(`r=0`, so not the spill path), tag **0** in B and **1** in A. So the answer to the previous open question is
"never set" — not "set to the wrong value" — for that value.

Note this is the *register* case (the second of the two lines); the spill case never fires here. The value is a
`-> f64` call result that the caller then consumes, which is what `as_f64_rdi()` covers for builtins and what
the gate's `float-return` layer covers for the simple user-function case (fixed 0.0.220).

Next step for the fix (narrow): instrument where a `-> f64` user call's result vreg is tagged float and check
whether it fires for the `pio2_1()` / `qmult()` calls in program B. If it does not fire, the fix is that missing
tag write; if it fires and is then lost, the caller's vreg churn is overwriting it.

## WHY THE TAG IS MISSING: two writers of `fn_retflt`, one erasing the other

The tagging at `codegen.quanta:1251` (`if ... r64(fn_retflt + tcf*8)==1 { w8(vfloat+tres,1) }`) is gated on
`fn_retflt[callee]`, and `fn_retflt` has **two writers that disagree**:

| writer | site | writes |
|---|---|---|
| declared return type (`-> f64`) | `helpers.quanta:441` (the 0.0.220 fix) | 1 for every function whose signature says `-> f64` |
| body inference (`return` analysis) | `funcscan.quanta:1396`, `1419-1438` | 1 if a `return` is a float literal / float expression / float-bound identifier, and **`0` on a conditional reset at 1396** |

`helpers.quanta:426` already carries the lesson from an earlier round in its own comment: an unconditional
`w64(fn_retflt + i*8, 0)` "silently erased that inference". The same hazard is still present from the other
direction — `fn_retflt` is a single slot per function, written by both passes, and the body-inference pass can
leave it 0 for a function whose signature says `-> f64`.

**And the index is the order dependence.** `fn_retflt` is indexed by function *index*, assigned during the
scan. Adding a call (even an unreachable one) can change which function index gets which slot when the passes
write at different times, which is exactly why a dead call in `main` changes an earlier function's arithmetic.

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
