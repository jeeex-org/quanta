# Phase 4 — A32 (0.0.253): the `fspill_home` frame/offset mismatch

Lever: **A32** — a latent OUT-OF-FRAME WRITE in the float spill region, and the
hard prerequisite for F4 (xmm-resident FP) and the 32-byte-aligned vector spill
region. One lever, one version. Golden `47c96a073f903c14bc7ffcee1abc5a8a`.

Every number below is MEASURED in this run against `compiler/0.0.25{2,3}/`.

---

## 1. The invariant that was broken

`codegen.quanta` sized a function's frame from the INTEGER spill extent only:

```
spill_region = max(48 + vreg_n*8, 1024)
frame_size   = spill_region + total_str + 80
```

but `emitter.quanta` addressed a FLOAT home at a CONSTANT far below it:

```
fspill_home(v) = -(48 + 8192 + (v+1)*8)     // ~ -8248
```

For a function with a 1120-byte frame (the common `min_spill` floor case) the
first write to a float home lands **~7 KB below the frame — in the caller's
frame**. The audit that found it (`arithmetic-codegen-defects-0.0.247.md` §D2)
called it a "latent landmine" for one reason only: the FP register allocator was
dead code. Measured again here on 0.0.252: `fphys(` has **0 call sites** anywhere
in `src/x86/`; a float value lives in a GPR and spills to its INTEGER home
(`spill_home`). So the corrupted address was never written — until F4.

## 2. The fix

Re-base the float region INTO the frame, immediately below the integer region, in
a disjoint index range (the option `phase2-vector-design.md` §3.3 names), and
derive both regions from one place:

```quanta
fn int_spill_size() { return SPILL_BASE + vreg_n * 8 }          // integer region magnitude
fn fspill_home(v)   { return -(int_spill_size() + (v + 1) * 8) } // float region, disjoint
fn fspill_size()    { return vreg_n * 8 }                        // float region magnitude
```

`codegen` reserves `fspill_size()` for a float-using function only, with an
explicit containment bound so the guarantee does not ride on `min_spill`:

```quanta
let flt_region = 0
if fn_has_float==1 { flt_region = vreg_n * 8 }
...
if flt_region > 0 {
    let need = 48 + vreg_n*8 + vreg_n*8          // magnitude of the deepest fspill_home
    if spill_region + flt_region < need { flt_region = need - spill_region }
}
let frame_size = spill_region + flt_region + total_str + 80
```

### 2.1 `fn_has_float` — the non-obvious part

`vfloat[]` is the float tag table, but it CANNOT be read at the prologue: the
float fixpoint's tags are **deliberately discarded** immediately before the
prologue (the "Discard the fixpoint's float tags" block) and re-populated during
the EMIT pass by each float producer. Reading `vfloat` after the discard would
under-count; the snapshot is taken just BEFORE it:

```quanta
let fn_has_float = 0
{ let qf=0
  while qf<vreg_n { if r8(vfloat+qf)==1 { fn_has_float=1 }; qf=qf+1 } }
```

The fixpoint is conservative (starts from every float producer and propagates
through IR_MOV chains), so a function that truly uses floats always sets a tag; an
over-tag over-reserves the frame, which is the safe direction. Empirically
correct: the four float benchmark rows grew and the other 34 did not (§3).

## 3. Measured effect (instrument of record: `scripts/bench_instr.sh`)

| row | q_frame 0.0.252 | q_frame 0.0.253 | delta |
|---|---|---|---|
| `float` | 1120 | **1472** | +352 (= vreg_n*8, vreg_n=44) |
| `heavy_float` | 1136 | **1408** | +272 |
| `heavy_float2` | 1136 | **1408** | +272 |
| `float_ops` | 1184 | **1632** | +448 |
| other 34 rows | — | unchanged | 0 |

`q_instr`, `q_loop`, `q_st`, `q_ld`, `q_lst`, `q_lld` **identical on all 38
rows**. The lever is a frame-size change and nothing else.

## 4. Red-first row

`spillframe-guard` (run_tests.sh), reading `main`'s PROLOGUE FRAME from the
`--emit-obj` object plus the deepest `-0xNNN(%rbp)` operand:

| compiler | float probe `main` frame | int probe `main` frame | verdict |
|---|---|---|---|
| 0.0.252 (pre-A32) | **1104** | 1104 | **FAIL** (`1104 < 1200`) |
| 0.0.253 (A32) | **1376** | 1104 | PASS |

The int probe (`arith_deadstore_probe.quanta`) must NOT grow — the no-bloat half.

**Honest scope.** Because `fphys` is still dead, 0.0.253 emits NO float-home
instruction; the deepest `%rbp` reference in the float probe is 320 (the integer
home). So this row proves the frame RESERVES the region, not that a float home was
materialised inside it. That stronger claim is observable only after F4 wires the
allocator, and belongs to F4's version. Consequently no byte-scan of 0.0.252 could
be RED here — and a naive "deepest displacement <= frame" scan would pass
vacuously on BOTH versions, the exact trap the withdrawn `objdump` multiset oracle
already cost this campaign.

## 5. Byte-identity — 192/243, and every difference is one immediate

`test_suites/scripts/byte_identity.sh` (both compilers, `-O`, byte compare) over
all 243 rows: **identical 192, differing 51, compile-fail 0**.

The 51 are exactly the float-using rows. Mechanically verified that the ONLY
difference in each is the frame-size immediate: for all 51, both compilers were
re-run with `--emit-obj`, both disassemblies were reduced to instruction text
(addresses stripped) and diffed — every differing line is a `sub $0xNNN,%rsp` or
`add $0xNNN,%rsp`, with **0** other differences:
`checked=51 rows whose diff is NOT exclusively a sub/add-rsp frame immediate: 0`.

That is the strongest available statement for a frame-size lever, and it is why
the behavioural oracle set is trusted here rather than a byte count.

## 6. Verification

| check | result |
|---|---|
| gate (`run_tests.sh`, QC=0.0.253) | **243/243 pass, 0 fail, 0 compile-fail**, 0 RED stages, `GATE_RC=0` |
| new stage | `PASS spillframe-guard: float main frame=1376 (>= 1200) deep=320; int main frame=1104 (<= 1152)` |
| fixpoint (from 0.0.252 golden) | `1d1e2d04 -> 47c96a07 -> 47c96a07 -> 47c96a07 -> 47c96a07`; distinct(g1..g4)==1 |
| `bench.sh` | 38/38 compiled, **0 MISMATCH**, `BENCH_RC=0` |
| `verify-release.sh 0.0.253 0.0.252` | **14 passed, 0 failed** |

## 7. The fourth flush-order invariant — looked for, not found in A32's scope

A32 does not reorder anything around `flush_all()`: the `fn_has_float` snapshot
runs before the body (no flush interaction), the frame formula runs in the
prologue (no flush interaction), and `fspill_home` is reachable only from the
still-dead FP allocator. So no new invariant was exposed.

Deliberate look, nonetheless: every `flush_all(); aphys(...)` adjacency in
`codegen.quanta` (13 sites: 2551, 2582, 2661, 3341, 3348, 3442, 3451, 3460, 3534,
3542, 3607, 3617, and the guarded IR_RET at 2809) was enumerated. All but the
IR_RET early-return use flush_all's **STORE** side effect (home stays current so
the following reload is correct) — not its emptied-register-map side effect. The
only site that relies on the emptied map is IR_RET's early-return, which is already
known and guarded by `if f2_ok == 1` (0.0.252), with IR_PARAM documented in the
skill. No fourth, undocumented invariant was found in this lever's surface; the
search is stated so the next reorderer does not have to redo it blind.

## 8. What A32 leaves ready for the vector region

- One home class, one base function, one size function (`int_spill_size`,
  `fspill_home`/`fspill_size`) — the vector region becomes a third, appended below
  the float region with its own base.
- The frame already reserves by region; the vector version adds its size the same
  way.
- STILL TO DO in the vector version: 32-byte ALIGNMENT of a vector home needs
  `%rsp` aligned to 32 in the prologue (`%rbp` after `push rbp` is only 16-byte
  aligned). A32 deliberately does not touch global frame alignment, because that
  would change every frame and destroy the 192/243 identity above for no benefit
  until a vector type exists.
