# 0.0.251 — A33: the dead `loop_depth` guard is deleted, and the escape hatch is tested

Phase 3, lever two. `VERSION` 0.0.250 -> **0.0.251**. Source changed:
`src/x86/codegen.quanta` (the `let loop_depth = 0` declaration and the four
`if loop_depth == 0 { ovf_trap_emit(ii) }` guards). Gate: two new rows.

```
0.0.250 golden  md5 e2f04027d8b87623da94d7df0245573b   (frozen baseline, untouched)
0.0.251 g1      md5 cd0fc7bf61e066b731a533c1bd3589ea   (0.0.250 golden building the edited source)
0.0.251 g2      md5 cd0fc7bf61e066b731a533c1bd3589ea   (COMMITTED GOLDEN, = fixpoint)
0.0.251 g3      md5 cd0fc7bf61e066b731a533c1bd3589ea
0.0.251 g4      md5 cd0fc7bf61e066b731a533c1bd3589ea   (distinct(g2,g3,g4) == 1)
```

---

## 1. The finding this version acts on

`let loop_depth = 0` was declared once per function and **nothing ever incremented
it**, so the four guards around the integer add/sub/mul/neg overflow trap were
constant-true: they suppressed nothing. They were worse than dead — they read as
"the overflow trap is skipped inside loops", which is not a behaviour this compiler
has ever had, and the obvious "fix" (wire it up) is the one change this campaign
forbids, because it would silently remove overflow detection from every loop in every
program, which is the opposite of what the guard's author intended.

The opt-out the guard was groping for **already exists**, and it is per-operation, not
per-loop: `unsafe { }` records `unsafe_depth` for every IR op inside it
(`helpers.quanta:420`) and all three trap emitters are gated on
`r8(ir_unsafe+ii)==0` — `ovf_trap_emit` (`emitter.quanta:250`), `shl_trap_emit`
(`:256`), `idx_trap_emit` (`:322`). It is load-bearing today: the compiler's own
`compute_magic()` is wrapped in `unsafe { }` because its signed-division magic-number
recovery does deliberate 64-bit wraparound.

So A33 was never "the language cannot express this". A33 was (a) a guard that lies
about the compiler, and (b) **a load-bearing capability with no test at all**.

## 2. What landed, in the order the resolution required

### (a) Test the capability first — both directions

Two new gate rows, deliberately complementary so that neither can be satisfied by
breaking the other:

| row | source | expected exit | what it proves |
|---|---|---|---|
| `unsafe_ovf_suppressed_test.quanta` | `i64::MAX` added five times inside `unsafe { }` | **0** | no SIGILL fired, AND the arithmetic wrapped to the documented value |
| `unsafe_ovf_trap_test.quanta` | the identical statement, NOT wrapped | **132** (SIGILL) | the trap is on by default |

The first row's golden is exact, not approximate: `i64::MAX = 2^63-1`, and adding it
five times gives `2^63-1`, `-2`, `2^63-3`, `-4`, `2^63-5` = **9223372036854775803**; the
program returns `s - 9223372036854775803`, so an exit of 0 proves both the absence of a
trap *and* the exact two's-complement result.

Both rows can FAIL, in the direction that matters:

- if the `unsafe { }` suppression regressed, row 1 SIGILLs -> 132 instead of 0;
- if someone WIRED `loop_depth` up (the forbidden change), row 2's loop would have its
  trap skipped -> 0 instead of 132.

MEASURED on the 0.0.250 golden (i.e. these are capability regression guards, not
red-on-the-previous-version rows — the capability already exists, which is the whole
finding): `suppressed exit=0`, `trap exit=132 (SIGILL)`.

### (b) Delete the constant-true guard

- `let loop_depth = 0` deleted (replaced by a comment recording why, and what the
  correct opt-out is).
- the four sites are now plain `ovf_trap_emit(ii)`:
  `IR_ADD`, `IR_SUB`, `IR_MUL` and the integer branch of `IR_NEG`.

**Proven a no-op on codegen, the only way it can be:** every one of the **242** gate
rows was compiled with both the 0.0.250 golden and the fixed-point 0.0.251 binary and
byte-compared — **242 identical / 0 differing / 0 compile-fail**, and the opcode-multiset
comparison agrees (242 identical). Instrument of record `scripts/bench_instr.sh` on all
38 benchmark rows:

| metric | 0.0.250 | 0.0.251 | delta |
|---|---|---|---|
| `q_instr` | 8420 | 8420 | **0** |
| `q_loop` | 1926 | 1926 | **0** |
| `q_mem` / `q_hst` / `q_hld` / `q_lst` / `q_lld` | 2240 / 1454 / 785 / 458 / 273 | identical | **0** |

**0 rows changed any `q_*` column.** That is the required result: a constant-true
condition cannot change emitted code, so if any row had differed the guard was not
constant-true and the change would not have been the cleanup it claims to be.

### (c) `unchecked { }` as a second spelling — deliberately NOT added

The design doc left this open. It is a language-surface decision (two spellings for one
IR flag) that the author has not asked for, and the existing `unsafe { }` already covers
the narrow arithmetic case per operation. Recorded, not built. The warning stands:
**never wire `loop_depth` up.**

## 3. Verification

- **Gate** on the committed golden: `=== Results: 242/242 pass, 0 fail (incl. 0
  compile-fail) [rows: EXPECTED.tsv] ===` (239 -> 240 in 0.0.250, -> 242 here), every
  stage GREEN.
- **Fixpoint** from the frozen 0.0.250 golden: the lever is a codegen no-op, so the
  fixpoint is immediate — `g1 == g2 == g3 == g4 == cd0fc7bf`;
  `distinct(g2,g3,g4) == 1`.
- **`scripts/verify-release.sh 0.0.251 "$(cat VERSION)"`**: 13 passed, 1 failed — the
  one failure is the `official gate returned non-zero` check, and the gate is non-zero
  only because the `stdlib` stage is RED from the loader peer's **uncommitted**
  `lib/std` edits (measured: the three failing rows return rc=1 under the frozen 0.0.249
  and 0.0.250 goldens too, and the stage was GREEN four hours earlier). See WIP.md §4.
- **`scripts/bench.sh`**: 0 MISMATCH, 38/38 outputs equal their C twins (identical
  codegen to 0.0.250, so this is expected, and is checked rather than assumed).

## 4. Why this is a real lever despite moving no number

It removes a lie from the compiler and buys the *proof* for a capability three other
open items depend on: the vector-type design states that a vector lane's arithmetic is
not trapped and that `unchecked` must therefore be a prerequisite, and the A33
resolution's whole content is that the escape hatch exists and now has evidence. A
capability with no test is a capability that is not known to exist; 0.0.251 is where it
becomes known.
