# 0.0.236 — A6: the SSE operand load must not re-decide from the vfloat tag

## The defect (A6, confirmed and fixed)

`fn qmult(x) -> f64` — a parameter written **without `: f64`** — used in float arithmetic beside an f64
constant returned garbage:

| program | 0.0.235 | 0.0.236 |
|---|---|---|
| `println(f64bits(reduce(0.5)))` | `-4336984033343832063` | `4602678819172646912` |

The parameter never got tagged, so `fopld_rr` (`emitter.quanta:928-930`) picked `fi2f_gp` (`cvtsi2sd`) and
**converted** an f64 bit pattern instead of moving it (`fld_x`/`movq`). It looked like call-order sensitivity
because an unreachable call in another function happened to tag that vreg index by a different route. The full
trail — three hypotheses eliminated by measurement, two rejected fix locations — is in
`docs/research/call-order-f64-defect.md`.

## The fix

`src/x86/codegen.quanta`, at **both** SSE emit sites (`fopld_rr(a0, ...); fopld_rr(a1, ...)` before
`addsd`/`subsd` and before `mulsd`): tag both operands as float before loading them.

That branch is already the SSE form, so both operands *are* f64 by construction — the operation is only SSE
because one of them already is — and the operand load must therefore not re-decide from `vfloat`. Same rule the
`IR_PARAM` case follows for annotated parameters ("the declared type is the source of truth"), applied where the
emitter already has the evidence.

## Verification

- Saved repro correct: `tests/f64_call_order_defect.quanta` -> `4602678819172646912` (was `-4336984033343832063`)
- Untagged-conversion count for the failing program: **2 -> 1**, matching the correct program
- **Fixpoint holds**: 3 generations, all `08acae941891e1d387b550ca1d4a5554`, distinct = 1
- New gate row `test_suites/codes/f64_call_order_test.quanta` (EXPECTED 0), proven **RED on 0.0.235's golden**
  (rc=1) and **GREEN on 0.0.236** (rc=0)
- 0.0.235's tree was restored to exactly its promoted commit before this tree was opened

## NOT done yet (promotion is pending)

`VERSION` is still 0.0.235, and the §5 gate and §6 release verification have **not** been run on this tree. The
fix is verified at the functional level — repro, fixpoint, red-first gate row — and needs the ordinary promotion
pass before 0.0.236 becomes the golden.
