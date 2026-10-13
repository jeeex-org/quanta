# 0.0.236 — A6: DO NOT PROMOTE AS IS — the fix passes the repro but FAILS the gate

## Status: gate RED. This tree must not become the golden in its current state.

`VERSION` is still 0.0.235 and that is intentional. The fix in this tree makes the A6 repro correct, but the §5
gate on this tree returns **rc=1**:

| gate result | count |
|---|---|
| functional | **821/822 pass, 1 fail (1 compile-fail)** — RED |
| stdlib | **RED** — 4 rows: `stdlib_lfm2_mm_test`, `stdlib_lfm2_attn_test`, `embedding_test`, `q4k_matvec_test` (expected rc=0, got rc=1) |

0.0.235's gate was 820/820 with STDLIB 108/108, so the four stdlib failures are **new**.

## Regressions attributed

- `recv_loop_test.quanta` `rc=14` with empty stderr reproduces on **0.0.235 as well** -> **pre-existing /
  environmental** (a silent compiler failure at the memory cap, the same failure mode the cap had at 6200000 KB).
  Not caused by this patch.
- `embedding_test.quanta`: **0.0.235 compile=0 run=0 (pass); 0.0.236 compile=0 run=1 (fail)** — a clean A/B, so
  the patch causes a real regression. The other three stdlib rows are the same float-heavy family.

## Why it regresses, and what the next attempt must do differently

The patch tags *both* operands as float at the two SSE emit sites, reasoning that "the branch is SSE, so both
operands are f64 by construction". That reasoning is unsound: **which branch is taken is itself decided by the
`vfloat` tag**, so if the tag that selected the SSE branch was wrong (stale, or mis-inferred), the patch cements
the error and now marks a genuinely-integer operand as float — propagating the mistake further than the original
bug did. That is the circularity to avoid.

A correct fix must tag from evidence that is **independent of the tag that chose the branch** — the declared or
annotated type, the constant operand's own type as the parser knows it, or a value *proven* float. That is the
shape 0.0.220 used when it made the declared-return-type case authoritative. Do not repeat the other rejected
attempt either: a rule inside the `changed=1` tag pass produced a byte-identical binary, because the pass has no
float evidence to propagate from.

## What still holds (verified, keep it)

- `tests/f64_call_order_defect.quanta` -> `4602678819172646912` (was `-4336984033343832063`)
- the failing program's untagged-conversion count 2 -> 1
- fixpoint stable: 3 generations, all `08acae941891e1d387b550ca1d4a5554`, distinct = 1
- `test_suites/codes/f64_call_order_test.quanta` (EXPECTED 0) RED on 0.0.235 (rc=1), GREEN on 0.0.236 (rc=0)
- gate rows `recursion_depth_test` (A4) and the A2 float-print stage both GREEN in this gate run
- the root cause is confirmed independent of the fix: an **untyped parameter** used as a float; annotating
  `x: f64` alone fixes the repro (see `docs/research/call-order-f64-defect.md`)
