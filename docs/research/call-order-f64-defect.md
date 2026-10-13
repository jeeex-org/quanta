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

## ELIMINATED: `fn_retflt` is NOT the difference (0.0.235)

Instrumented both writers of `fn_retflt` — the declared `-> f64` scan (`helpers.quanta:441`, marker `D`), the
per-function reset (`funcscan.quanta:1396`, marker `R` with the prior value), and the float-literal inference
(`funcscan.quanta:1419`, marker `F1`) — and ran both isolated programs:

    events: A=37  B=37      diff: EMPTY (identical event streams, identical values)

So the flag ends up the same for every function in both programs, and the "two writers disagree / order changes
which index holds what" theory is **wrong**. The declared pass tags function indices 0-8 in both, and the
guarded resets behave identically.

That leaves the consumers rather than the flag: the three `w8(vfloat+...)` tagging sites in codegen
(`codegen.quanta:205/210/220` parameters, `382`, `981/989`, `1251` call result). The next probe is to instrument
those sites and print `(function index, result vreg, tag after the write)` — in particular whether 1251 fires for
the `pio2_1()`/`qmult()` calls in B, and whether `vclr()`'s per-function `vfloat` clear runs *between* the write
and the read of that same vreg index (the tag is written while emitting one function, and `vclr()` wipes
`vfloat` when the next function starts, so a tag that must survive into a later function's emit cannot).

## ROOT CAUSE CLASS FOUND (0.0.235): the tagging pass and the emitter disagree on the vreg INDEX

Instrumented every `w8(vfloat+...)` tagging site (markers P1-P13) plus `vclr()`'s clear (CLR) and ran both
isolated programs. The streams are 198 events each, in identical order, with the same 188 CLR events — and the
ONLY difference is which vreg index one tagging site fires on:

    B: 1 P5 5    1 P5 0        <- IR_CALL float-result tagging lands on vreg 0
    A: 1 P5 5    1 P5 6        <- ... and on vreg 6 when a dead call exists in main

So the tag is not missing by accident: it is written against a **different vreg index than the one the emitter
reads** at `fopld_rr` (`emitter.quanta:928-930`). The tagging pass works in the index space of the scan, while
codegen's emit assigns vreg numbers itself (`vreg_n` reset per function by `vclr()`, indices reused by the next
function), so the two only agree when the program's vreg layout happens to line up. Adding an unreachable call
in `main` shifts the numbering enough to break the coincidence — which is precisely why the defect looks like
"a call elsewhere changes this function's arithmetic".

This is the per-function vreg-index reuse hazard already recorded for other side tables (see the
`quanta-vreg-tag-recycling` skill). The fix is not another tag write but making the two agree on the index: tag
by the same numbering the emit uses (write the tag where the result vreg is bound during emit), or key the
propagation on something stable across the reset.

## THE FIX SITE, NARROWED TO THE PROPAGATION PASS (0.0.235)

The tag pass is the `changed=1` fixpoint walking each function's IR (`codegen.quanta:1053-1122`), and its own
comments state the governing rule: a tag has to be (re)asserted **after** the per-function clear, because
"tagging at parse time is wiped before the emit pass runs" (`1124-1126`). It handles the cases it knows:

| IR op | code | tags |
|---|---|---|
| `IR_RET` in a `-> f64` function | `1120-1122` | `ira0(mp)` |
| `IR_PARAM` declared `: f64` | `1123-1137` | via `fn_parflt` |
| call result of a `-> f64` callee | `1251` (site P5) | `tres` |
| **move** | `1015`, `1098` | `ira0(mp)` -> `irres(mp)` |

That last row is the gap to check first: `vfloat` is propagated through a move only when the source is in
**`ira0`**. The measured symptom is that the tag lands on a *different vreg index* than the one the consumer
reads, so the value reaching `fopld_rr` is very plausibly a **copy** of the tagged vreg that the pass did not
follow — either because the copy's source sits in `ira1`, or because the op carrying it is not one of the four
handled above.

Next step is therefore a read, not a build: instrument `1015`/`1098` and the `fopld_rr` operand to print
`(op, ira0, ira1, irres)` and see which op produced the untagged value in program B. That names the missing
case, and the fix is to add it to this pass — extending the propagation, not writing a one-off tag.

## ROOT CAUSE (0.0.235): an UNTYPED parameter used as a float — and two failed fix locations

**Confirmed root cause.** `fn qmult(x) -> f64 { let y = x * (2.0 / 3.14159265358979323846) ... }` — the parameter
is written **without `: f64`**. Annotating it `: f64` alone makes the failing program print the correct
4602678819172646912, and drops the untagged-conversion count from 2 to 1 (matching the program that works). The
parameter-tagging case at `codegen.quanta:1123-1137` only covers parameters **declared** `: f64`, and nothing
else supplies the tag, so `x` reaches the SSE multiply with `vfloat[x]==0` and `fopld_rr` emits `cvtsi2sd` over an
f64 bit pattern. The "call-order sensitivity" was a red herring: an unreachable call in another function
happened to tag that vreg index by a different route.

Instrumented proof of which site fires: `fopld_rr`'s register-case decision printed an untagged conversion
**inside `qmult`** on operand vreg 0, once in the working program and **twice** in the failing one.

### Fix location 1 — REJECTED (the tag pass is the wrong place)

Added the natural inference rule to the `changed=1` pass (`ira0`/`ira1` one-sided float evidence for
IR_ADD/IR_SUB/IR_MUL). Result: **byte-identical output for the failing program** (0 differing bytes, same
`cvtsi2sd` count of 2), i.e. the rule never fired. The reason is in the trace: the f64 **constant** beside `x` is
not tagged at that point either, so "one operand is an f64" has no evidence to propagate from. A pass-level rule
cannot infer from information the pass does not have. Patch reverted.

### Fix location 2 — the SSE operand load (where the fix belongs)

The op itself is already being emitted as SSE, so the emitter **knows** the operation is float while only one
operand carries the tag. The load that must not re-decide from `vfloat` is the `fopld_rr` call in the SSE path
(`codegen.quanta:1418-1420`, `1647-1650`): when one operand is known to be an f64, the other must be loaded as a
raw bit pattern (`fld_x`), not converted. Equivalent statement: the declared type is the source of truth — the
rule the IR_PARAM case already follows for annotated parameters.

Cheapest first step for it: tag the sibling operand at the SSE emit site (one line beside each `fopld_rr` call),
then confirm with the same binary-diff probe used above — the `cvtsi2sd` count for the failing program must drop
from 2 to 1 and the saved repro must print 4602678819172646912 without the dead call.

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
