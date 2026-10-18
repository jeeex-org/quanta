# 0.0.253 — WIP · **LEVER: A32 — the `fspill_home` frame/offset mismatch (a latent out-of-frame write)**

```
0.0.252 golden  md5 1d1e2d04a2acc5cdaabcd23e26fdf354   (frozen baseline, untouched)
0.0.253 g1      md5 47c96a073f903c14bc7ffcee1abc5a8a   (0.0.252 golden compiling the edited source)
0.0.253 g2      md5 47c96a073f903c14bc7ffcee1abc5a8a   (COMMITTED GOLDEN, = fixpoint)
0.0.253 g3      md5 47c96a073f903c14bc7ffcee1abc5a8a
0.0.253 g4      md5 47c96a073f903c14bc7ffcee1abc5a8a   (distinct(g1..g4) == 1)
```

Two files changed, everything else the 0.0.252 snapshot copied verbatim:

| file | change |
|---|---|
| `src/x86/emitter.quanta` | `fspill_home` re-based from the fixed `-(48 + 8192 + (v+1)*8)` to `-(int_spill_size() + (v+1)*8)`; new `int_spill_size()` / `fspill_size()` |
| `src/x86/codegen.quanta` | `fn_has_float` snapshot (taken from the float fixpoint BEFORE its tags are discarded) + the frame formula reserves `fspill_size()` for a float-using function, with an explicit containment bound |

Gate-side, in the same commit: the new `spillframe-guard` stage in
`test_suites/scripts/run_tests.sh` (+ its summary line, folded into the exit status)
and the new probe `test_suites/codes/arith_float_probe.quanta`, registered in
`EXPECTED.tsv` (rc=164), so the row count moves **242 -> 243**.

---

## 1. The defect, stated as an invariant

The frame formula (`codegen.quanta`) reserved, for a function with `vreg_n` vregs:

```
spill_region = max(48 + vreg_n*8, 1024)        // ~1 KB for a small function
frame_size   = spill_region + total_str + 80
```

but a FLOAT home was addressed at a FIXED displacement far below that:

```
fspill_home(v) = -(48 + 8192 + (v + 1) * 8)     // ~ -8248, i.e. ~8 KB below %rbp
```

So for a function with a 1120-byte frame, the first write to a float home would
land **~7 KB below the frame — inside the caller's frame**. This is a CORRUPTION
bug, not a missing optimisation. It was latent only because the FP register
allocator was dead code: `fphys()` / `fdef()` / `fflush_all()` had **zero call
sites**, so a float value lived in a GPR and spilled to its INTEGER home
(`spill_home`). The audit (`docs/research/arithmetic-codegen-defects-0.0.247.md`
§D2) flagged it as a "latent landmine"; it is the stated prerequisite for **both**
F4 (xmm-resident FP) and the 32-byte-aligned vector spill region, because those
are the first things that will actually write a float/vector home.

## 2. The fix

The float region is RE-BASED to sit immediately below the integer region, inside
the frame, in a disjoint index range — the option the vector design doc names
(`phase2-vector-design.md` §3.3: *"re-base every home (int, float, vector) into
one region at disjoint index ranges"*):

```
int_spill_size() = 48 + vreg_n*8                       // integer region magnitude
fspill_home(v)   = -(int_spill_size() + (v+1)*8)       // float region starts at its bottom
fspill_size()    = vreg_n*8                            // float region magnitude
```

`codegen` reserves `fspill_size()` **only for a function that uses floats**
(`fn_has_float`), with an explicit containment bound so the guarantee does not
depend on the `min_spill` floor arithmetic:

```
let flt_region = 0
if fn_has_float==1 { flt_region = vreg_n * 8 }
...
if flt_region > 0 {
    let need = 48 + vreg_n*8 + vreg_n*8     // magnitude of the deepest fspill_home
    if spill_region + flt_region < need { flt_region = need - spill_region }
}
```

### 2.1 Where `fn_has_float` comes from — and why the obvious source is wrong

`vfloat[]` is the float tag table, but it CANNOT be read at the prologue: the
float fixpoint's tags are **deliberately discarded** just before the prologue
(`codegen.quanta` "Discard the fixpoint's float tags...") and re-populated during
the EMIT pass by each float producer. So the snapshot is taken *before* the
discard:

```
let fn_has_float = 0
{ let qf=0
  while qf<vreg_n { if r8(vfloat+qf)==1 { fn_has_float=1 }; qf=qf+1 } }
```

The fixpoint is **conservative** (it starts from every float producer and
propagates), so a function that truly uses floats always sets a tag; an
over-tag only over-reserves the frame, which is safe. `fn_has_float` is stored in
a plain local for the duration of `ci_func` (the same function that computes
`frame_size`).

## 3. Measured effect (instrument of record: `scripts/bench_instr.sh`)

`float`'s and `heavy_float`'s loop/instruction columns are **untouched** — the
lever changes the frame SIZE only. Every row whose `main` uses floats grew its
frame by exactly `vreg_n*8`; every other row is **byte-identical**.

| row | q_frame 0.0.252 | q_frame 0.0.253 | delta |
|---|---|---|---|
| `float` | 1120 | **1472** | +352 |
| `heavy_float` | 1136 | **1408** | +272 |
| `heavy_float2` | 1136 | **1408** | +272 |
| `float_ops` | 1184 | **1632** | +448 |
| every other row (34) | — | **unchanged** | 0 |

`q_instr`, `q_loop`, `q_st`, `q_ld`, `q_lst`, `q_lld` are **identical on all 38
rows** — the lever is a frame-size change and nothing else. Full table:
`/tmp/a32.tsv` for this run; the frozen before/after is
`docs/research/phase2-baseline-before.tsv` / `-after.tsv` for the campaign.

## 4. Red-first row — proven RED on the previous version

New stage `spillframe-guard`: reads `main`'s PROLOGUE FRAME from the emitted
object (`--emit-obj` + `objdump -d`; the frame is the first `sub $0xNNN,%rsp`,
the containment bound is the deepest `-0xNNN(%rbp)` operand) of two probes. Exact
emitted bytes, load-independent, no tolerance — the same instrument as
`deadstore-guard` / `terminator-guard`.

| compiler | float probe `main` frame | int probe `main` frame | verdict |
|---|---|---|---|
| 0.0.252 golden (pre-A32) | **1104** | 1104 | **FAIL** (`1104 < 1200`) |
| 0.0.253 golden (A32) | **1376** | 1104 | PASS |

The int probe is `arith_deadstore_probe.quanta` (integer only): its frame must
NOT grow, which is the no-bloat half — a fix that reserved the float region
unconditionally would inflate every frame (the class of change that underflowed
the stack on low-ASLR binaries when a 16 KB floor was tried; see the `min_spill`
comment). Measured identical at 1104 on both compilers.

**Honest note on the shape of this row.** Every count here is emitted bytes, but
the *containment* of a float home cannot yet be observed in emitted code: because
`fphys` is dead, 0.0.253 still emits NO float-home instruction (deepest `%rbp`
reference in the float probe is 320, the integer home). So the row proves the
frame RESERVES the region (frame grew to cover `need`), not that a float home was
materialised inside it. That second claim becomes observable only when F4 wires
the allocator, and F4's own version adds the byte-scan row for it. The
containment bound in `codegen` makes the reservation exactly sufficient, so no
byte-scan of 0.0.252 could ever have been RED here — a vacuous-pass trap this
campaign has already paid for once (the withdrawn `objdump` multiset oracle).

## 5. Gate, fixpoint, verification

- **Gate** on the committed golden: **`=== Results: 243/243 pass, 0 fail (incl. 0
  compile-fail) [rows: EXPECTED.tsv] ===`**, **0 RED stages — GATE_RC=0**, including the
  new `spillframe-guard` (`PASS float main frame=1376 (>= 1200) deep=320; int main
  frame=1104 (<= 1152)`), and `marshal-guard`, `deadstore-guard`,
  `terminator-guard`, `stdlib`, `valgrind`, `fuzz` (fail-closed, 0 crashes),
  `differential` (`-O` == no-`-O` + vs-seed), `security`, `performance`, `qobj`,
  `verify-status`, `f16c-indep`. (242 rows + the new `arith_float_probe.quanta`.)
- **Fixpoint** from the frozen 0.0.252 golden: `1d1e2d04 -> 47c96a07 -> 47c96a07 ->
  47c96a07 -> 47c96a07`; `distinct(g1..g4) == 1`; the committed golden is g2==g4.
- **`scripts/bench.sh`** (0.0.253 golden): see §5.1 — 0 `MISMATCH`.
- **`scripts/verify-release.sh 0.0.253 "$(cat VERSION)"`**: see §5.2.

### 5.1 bench.sh

`scripts/bench.sh` with `QC=compiler/0.0.253/bin/x86/qc`: **38/38 rows compiled, 0
MISMATCH** — every row's output still equals its C twin's (`grep -c MISMATCH` = 0),
**`BENCH_RC=0`**. (Note: bench.sh's trailing `# OK` line only covers structural
failures — compile failures / folded twins — NOT output mismatches, which are
flag-per-row; the count was measured on the row notes directly, and is 0.)

### 5.2 verify-release

`bash scripts/verify-release.sh 0.0.253 "$(cat VERSION)"`: **14 passed, 0 failed**
(`VR_RC=0`), including `<VER>=0.0.252` rebuilding bit-for-bit, `<NEXT>` src/bin
lockstep (`47c96a07` IS the seed-chain fixed point), the self-host fixed point, and
the official gate re-run (`Results: 243/243 pass, 0 fail`, `functional stage GREEN`).

## 6. Byte-identity — and what the equivalence rests on

Every one of the 243 `EXPECTED.tsv` rows compiled with both compilers (`-O`, byte
compare of the emitted executables):

| | count |
|---|---|
| byte-identical | **192 / 243** |
| differing | **51 / 243** |
| compile-fail | 0 |

The 51 differing rows are exactly the rows that use floats (`float_*`,
`gguf_*`, `simd*`, `trig`, `linalg`, `sampling*`, `kv_cache`, `q6k_dequant_ref`,
`fp16f32_*`, `f32_*`, `f16_*`, `a26_*`, `a1b_*`, `const_float`, and the
`std_*_const_test` rows, which parse float constants transitively).

**The difference in every one of the 51 is the frame-size immediate and NOTHING
else.** Verified mechanically: for all 51 rows, both compilers were run with
`--emit-obj` and the two disassemblies compared instruction-by-instruction after
stripping addresses — every differing line is a `sub $0xNNN,%rsp` or `add
$0xNNN,%rsp`, with zero other differences (`checked=51 rows whose diff is NOT
exclusively a sub/add-rsp frame immediate: 0`). That is the strongest possible
statement for a frame-size lever: 192 rows untouched, 51 rows touched in exactly
one immediate.

Equivalence for this version rests on the behavioural oracles, all measured in
this run: the gate's **243/243** exit-code match, all 38 benchmark outputs
matching their C twins (`bench.sh` 0 MISMATCH — §5.1), `differential` (`-O` ==
no-`-O` and vs-seed), `fuzz` fail-closed with 0 crashes, `valgrind` clean, and the
self-host fixpoint `g2 == g3 == g4`.

## 7. What is still open

- **F4** (xmm-resident FP) — now unblocked by A32. It must (a) wire `fphys()`
  into the FP arithmetic paths, (b) reconcile the float allocator's
  `fvr_init`/`vfloat` tagging with `is_float_vr`, and (c) add the byte-scan row
  that observes a float home INSIDE the frame (the claim A32 could not yet make
  observable).
- **F5** (opt-in FMA), **F6** (`i*8` is still `imul $0x8`), **F7** (LICM),
  **F8** (constant shift-range).
- **The vector spill region** — A32 leaves the layout ready (one region per home
  class, magnitudes derived from one place); the vector version still needs to
  make the region 32-byte aligned (which likely means aligning `rsp` in the
  prologue) and to enforce the `@isa(avx2)` compile-error contract.
- **A36** (filed by the loader peer, `docs/plans/bugs.md`) — the conversion
  builtins (`f16bits_to_f64`, `f32bits_to_f64`, `f32_to_f64`) are missing from
  `ret_expr_is_float`'s marker list, so `fn cvt(p) { return f32bits_to_f64(p) }`
  is inferred integer-returning. Its own version.
