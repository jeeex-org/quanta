# 0.0.251 — WIP · **LEVER: A33 — delete the dead constant-true `loop_depth` guard; test the escape hatch**

```
0.0.250 golden  md5 e2f04027d8b87623da94d7df0245573b   (frozen baseline, untouched)
0.0.251 g1      md5 cd0fc7bf61e066b731a533c1bd3589ea   (0.0.250 golden compiling the edited source)
0.0.251 g2      md5 cd0fc7bf61e066b731a533c1bd3589ea   (COMMITTED GOLDEN, = fixpoint)
0.0.251 g3      md5 cd0fc7bf61e066b731a533c1bd3589ea
0.0.251 g4      md5 cd0fc7bf61e066b731a533c1bd3589ea   (distinct(g2,g3,g4) == 1)
```

One file changed, everything else the 0.0.250 snapshot copied verbatim:

| file | change |
|---|---|
| `src/x86/codegen.quanta` | `let loop_depth = 0` deleted; the four `if loop_depth == 0 { ovf_trap_emit(ii) }` sites are plain `ovf_trap_emit(ii)` (integer add/sub/mul/neg) |

Gate-side, in the same commit: `test_suites/codes/unsafe_ovf_suppressed_test.quanta` and
`test_suites/codes/unsafe_ovf_trap_test.quanta` (new rows; `EXPECTED.tsv` 240 -> 242).

---

## 1. What landed

`let loop_depth = 0` was declared once per function and **nothing ever incremented it**,
so the four guards around the integer overflow trap were constant-true — they suppressed
nothing, and they read as "the trap is skipped inside loops", which this compiler has
never done. The four conditions and the declaration are gone.

Wiring the flag up instead would have silently disabled overflow detection in every loop,
which is the change this campaign forbids; the opt-out the guard was reaching for already
exists and is **per operation**: `unsafe { }` records `unsafe_depth` for every IR op
inside it and all three trap emitters are gated on `r8(ir_unsafe+ii)==0`.

## 2. Red-first / capability proof — both directions

| row | source | expected | 0.0.250 measured |
|---|---|---|---|
| `unsafe_ovf_suppressed_test.quanta` | `i64::MAX` added five times inside `unsafe { }` | **0** | **0** (no SIGILL, and the wrap is exactly 9223372036854775803) |
| `unsafe_ovf_trap_test.quanta` | the same statement NOT wrapped | **132** (SIGILL) | **132** |

Honest framing: these are **capability regression guards, not red-on-0.0.250 rows** — the
capability already exists, which is the entire finding of the A33 resolution. They can
each fail in the direction that matters: remove the `unsafe { }` suppression and row 1
SIGILLs; wire `loop_depth` up (the forbidden change) and row 2's loop loses its trap and
returns 0 instead of 132.

## 3. The guard deletion is proven a no-op on codegen

Instrument of record `scripts/bench_instr.sh`, all 38 benchmark rows, 0.0.250 vs 0.0.251:

| metric | 0.0.250 | 0.0.251 | delta |
|---|---|---|---|
| `q_instr` | 8420 | 8420 | **0** |
| `q_loop` | 1926 | 1926 | **0** |
| `q_mem` | 2240 | 2240 | **0** |
| `q_hst` | 1454 | 1454 | **0** |
| `q_hld` | 785 | 785 | **0** |
| `q_lst` | 458 | 458 | **0** |
| `q_lld` | 273 | 273 | **0** |

**0 of 38 rows changed any `q_*` column.**

Byte-identity across the gate rows, all **242** of them compiled with both compilers and
byte-compared (`test_suites/scripts/byte_identity.sh`):

| | count |
|---|---|
| **byte-identical** | **242 / 242** |
| differing | **0** |
| compile-fail | 0 |

and `test_suites/scripts/objdump_multiset_diff.py` agrees (242 identical). This is the
one lever in the campaign where byte-identity is the REQUIRED oracle rather than a
description: a constant-true condition cannot change emitted code, so any differing row
would have falsified the claim that the guard was constant-true.

## 4. Gate, fixpoint, verification

- **Gate** on the committed golden: **`=== Results: 242/242 pass, 0 fail (incl. 0
  compile-fail) [rows: EXPECTED.tsv] ===`**, and the two new rows reported
  `PASS unsafe_ovf_suppressed_test.quanta (rc=0)` /
  `PASS unsafe_ovf_trap_test.quanta (rc=132)`.
  **One stage is RED and it is NOT this change:** `stdlib` reports
  `FAIL q4k_matvec_test.quanta / std_awq_test.quanta / std_nf4_test.quanta (expected
  rc=0, got rc=1)`. MEASURED: those same three rows return **rc=1 under the frozen
  0.0.249 golden and the 0.0.250 golden as well**, so the failure is independent of this
  version. Cause, measured: the loader peer is mid-edit in `lib/std/`
  (`git status` -> `M lib/std/fs.quanta`, `M lib/std/gguf.quanta`, ~72 insertions /
  214 deletions uncommitted, plus `gguf_mm.quanta` earlier) and all three rows
  `import std`. The stage was GREEN at 21:2x on this box (0.0.250 gate run, stdlib GREEN)
  and RED at 23:1x, i.e. it follows the peer's edit, not this commit. Every other stage
  is GREEN, including the new `deadstore-guard` and `marshal-guard`.
  A byte-level no-op cannot cause a behavioural failure in the first place: see §3.
- **Fixpoint**: the lever is a codegen no-op, so convergence is immediate —
  `g1 == g2 == g3 == g4 == cd0fc7bf`; `distinct(g2,g3,g4) == 1`.
- **`scripts/verify-release.sh 0.0.251 "$(cat VERSION)"`**: **13 passed, 1 failed** —
  the failure is the `official gate returned non-zero` check, and it is non-zero for
  exactly the one reason above (`stdlib` RED from the peer's uncommitted `lib/std`
  edits). The checks that matter for this version all PASS, including
  `compiler/0.0.251/WIP.md exists`, `<NEXT> src/bin lockstep` and
  `self-host fixed point: gen0==gen1==gen2==released binary`.
- **`scripts/bench.sh`**: 0 MISMATCH, 38/38 outputs equal their C twins.

## 5. What this version does NOT do

`unchecked { }` was **not** added as a second spelling of the same IR flag: that is a
language-surface decision (two spellings for one flag) the author has not asked for, and
`unsafe { }` already covers the narrow arithmetic case per operation. Still open: **F3**
(the comparison round trip), **A32** (`fspill_home` frame/offset mismatch — the
prerequisite for xmm-resident FP and for the 32-byte-aligned vector spill region),
**F4**, **F5**, **F6**, **F7**, **F8**, and the vector types under the `@isa(avx2)`
compile-error contract.
