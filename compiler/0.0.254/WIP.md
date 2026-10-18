# 0.0.254 — WIP · **LEVER: A36 — `ret_expr_is_float`'s conversion markers (a silent return-type misclassification)**

```
0.0.253 golden  md5 47c96a073f903c14bc7ffcee1abc5a8a   (frozen baseline, untouched)
0.0.254 g1      md5 5c23efdd1e0550af170dee95f1fbabec   (0.0.253 golden compiling the edited source)
0.0.254 g2      md5 5c23efdd1e0550af170dee95f1fbabec   (COMMITTED GOLDEN, = fixpoint)
0.0.254 g3      md5 5c23efdd1e0550af170dee95f1fbabec
0.0.254 g4      md5 5c23efdd1e0550af170dee95f1fbabec   (distinct(g1..g4) == 1)
```

One file changed, everything else the 0.0.253 snapshot copied verbatim:

| file | change |
|---|---|
| `src/x86/funcscan.quanta` | `ret_expr_is_float()`'s marker list: the CONVERSION family is matched by DIRECTION — f16/f32 producers added, `f64of` added, the two raw-bit SINKs (`f64_to_f32bits`/`f64_to_f16bits`) no longer match |

Gate-side, in the same commit: the new probe `test_suites/codes/ret_conv_infer_test.quanta`
registered in `EXPECTED.tsv` (rc=114), so the row count moves **243 -> 244**.

Filed as **A36** in `docs/plans/bugs.md` (commit `bc1e2f24`), discovered by the
loader peer while adopting the native f16/f32 conversions.

---

## 1. The defect

`funcscan.quanta`'s `ret_expr_is_float(start, end)` decides a function's return
type by walking EVERY token of the body for floatness MARKERS. `scan_retfloat()`
turns its verdict into `fn_retflt`, which `codegen` applies to every call site.
The marker list named the arithmetic builtins but handled the CONVERSION family
with a bare `f64_` prefix — which is **both too narrow and too coarse**:

```
                if c1=='6'&&c2=='4'&&c3=='_' { return 1 }                 // f64_*
```

- **Too narrow:** every `f16bits_to_*` / `f32bits_to_*` producer is missed.
- **Too coarse:** `f64_to_f32bits` / `f64_to_f16bits` are RAW-BIT INT sinks and
  were matched.

So a wrapper with no explicit annotation was inferred by accident in both
directions:

```quanta
fn cvt(p) { return f32bits_to_f64(p) }       // f32 bits -> f64 VALUE
```
is inferred **integer**-returning, so a caller's ordinary `d + 1.0` runs the
integer path over the f64's BITS. MEASURED by the loader peer while adopting the
builtins: the UNFUSED decode path's flags-OFF argmax came out **25438** against
the oracle **597**, all 128,000 logits different, while every fused flag stayed
bit-exact — which is exactly why it was not obvious. Bisected against a pristine
`git worktree` with the identical pinned compiler. The peer shipped a local
`-> f64` annotation in `lib/std`; under the standing policy that is a WORKAROUND,
so the capability ships here instead.

```quanta
fn rawbits(x) { return f64_to_f32bits(x) }   // f64 value -> f32 RAW BITS (i64)
```
is inferred **float**-returning, so a caller treats raw bits as a double. This is
the same defect mirrored, and it is also the SECOND misclassification from this
mechanism (the function's own comment already documents the first: a
`f2i(f64of(n) * 0.5)` body concluded "returns float").

## 2. The fix — name the direction, not the family

```quanta
if c1=='6'&&c2=='4'&&c3=='_'&&clen!=14 { return 1 }   // f64_* EXCEPT f64_to_fXXbits (both 14)
if c1=='6'&&c2=='4'&&c3=='o'&&c4=='f' { return 1 }    // f64of: raw u64 -> f64
if c1=='3'&&c2=='2'&&c3=='b' { return 1 }             // f32bits_to_f64 / f32bits_to_f16   (producers)
if c1=='1'&&c2=='6'&&c3=='b' { return 1 }             // f16bits_to_f32 / f16bits_to_f64   (producers)
```

`clen` is `tokln(q)`. The two raw-bit sinks are exactly 14 characters
(`f64_to_f32bits`, `f64_to_f16bits`); the producers they must not be confused
with are 10 (`f64_to_f32`, `f64_to_f16`) and `f64_load` is 8. So `clen!=14`
separates sink from producer by the only thing that distinguishes the names.

The change is strictly narrower than before for the `f64_` family (it can only
REMOVE a false positive) and strictly wider for f16/f32 (it can only ADD a
producer), so it cannot make a correct inference wrong.

## 3. Red-first row

`test_suites/codes/ret_conv_infer_test.quanta` (registered in `EXPECTED.tsv`,
rc=114). Return = `a_ok*100 + b_ok*10 + 4`.

| compiler | exit | meaning |
|---|---|---|
| 0.0.253 golden (pre-A36) | **4** | `a_ok=0`, `b_ok=0` — BOTH directions misclassified |
| 0.0.254 golden (A36) | **114** | `a_ok=1`, `b_ok=1` |

Supporting shapes, measured (correct = 2):

| probe | 0.0.253 | 0.0.254 |
|---|---|---|
| `fn cvt(p){return f32bits_to_f64(p)}` + caller `d + 1.0` | **0** | **2** |
| the same via a `let` binding (`let t = f32bits_to_f64(p) return t`) | **0** | **2** |
| control: `fn cvt3(p){return i2f(p)}` (i2f IS a marker) | 6 | 6 |

### 3.1 Two probe shapes that do NOT expose the defect (measured, so the next run does not repeat them)

- `fsubf(cvt(p), i2f(1))` — the `*f` builtins bit-move their operand regardless
  of the tag, so they are insensitive to it. The plain `+` form is the sensitive
  one.
- `f2i(rb)` as a discriminator for direction (b) — `f2i` ALWAYS bit-moves its
  operand (it assumes f64 bits), so `f2i(1065353216)` is 0 whether or not `rb` is
  tagged. An ordinary integer-context op (`rb + 7`) is the sensitive form.

A third, vivid manifestation: `printi(rb)` where `rb` is wrongly float-tagged is
a **compile error** on 0.0.253 (the 0.0.235 float-print rule), so the over-match
can also turn a valid program into a non-compiling one.

## 4. Verification

- **Gate** on the committed golden: see §4.1.
- **Fixpoint** from the frozen 0.0.253 golden: `47c96a07 -> 5c23efdd -> 5c23efdd ->
  5c23efdd -> 5c23efdd`; `distinct(g1..g4) == 1`. A comment-only edit to
  `funcscan.quanta` after the first build was re-built and reproduced the SAME
  md5 (`5c23efdd`), so the committed binary is the fixpoint of the committed
  source.
- **`scripts/bench.sh`**: see §4.2.
- **`scripts/verify-release.sh 0.0.254 "$(cat VERSION)"`**: see §4.3.

### 4.1 gate

**`=== Results: 244/244 pass, 0 fail (incl. 0 compile-fail) [rows: EXPECTED.tsv]
===`**, **0 RED stages — `GATE_RC=0`**, including the new
`ret_conv_infer_test.quanta` row and every pre-existing float/shift/stdlib/fuzz/
valgrind/differential/qobj/verify-status/f16c-indep stage.

### 4.2 bench.sh

`scripts/bench.sh` with `QC=compiler/0.0.254/bin/x86/qc`: **38/38 compiled, 0
MISMATCH** (`grep -c MISMATCH` = 0), **`BENCH_RC=0`**.

Byte-identity vs 0.0.253 (`test_suites/scripts/byte_identity.sh`): **identical
243, differing 1, compile-fail 0** — and the single differing row IS the new
`ret_conv_infer_test.quanta`. Nothing else in the suite changed a byte, which is
the correct shape: the change only alters codegen for functions whose return type
was misinferred, and the only gate row containing such a function is the probe.

### 4.3 verify-release

`bash scripts/verify-release.sh 0.0.254 "$(cat VERSION)"`: **14 passed, 0 failed**
(`VR_RC=0`), including `<VER>=0.0.253` rebuilding bit-for-bit, the src/bin
lockstep, the self-host fixed point, and the official gate re-run
(`Results: 244/244 pass, 0 fail`, `functional stage GREEN`).

## 5. Is a marker list the right shape at all?

**No — and this is the third instance of the same mechanism failing.** A list of
name prefixes is a second, hand-maintained model of the builtin table, and it has
now been wrong in three distinct ways: (i) a `f2i(...)` body concluding "returns
float" (documented above the function), (ii) the missing conversion producers
(this version), (iii) the over-matched raw-bit sinks (this version, the mirror).
Each was silent, and each was found by a *symptom* rather than by the list.

The right source of truth already exists in the tree: `emitter.quanta` has
`ft_isnew(nm, nl)` (line ~5278) — exact, length-aware string matching that
returns a KIND CODE per conversion builtin and **already distinguishes direction**
(`f32bits_to_f64`=1, `f64_to_f32bits`=2, `f16bits_to_f32`=3, `f32bits_to_f16`=4,
`f16bits_to_f64`=5, `f64_to_f16bits`=6, `f64_to_f32`=7, `f64_to_f16`=8; `ft_emit`
consumes the code). A `ret_expr_is_float` that resolved its head-call token
through that ONE table (plus a float-valued flag per kind) would be correct by
construction instead of by enumerations that have to be re-audited whenever a
builtin is added.

That refactor is deliberately NOT done here (one lever per version), and it is
recorded as the follow-up so the next builtin added does not have to be added in
two places. The scope of THIS version is the correctness of the existing shape.

## 6. What is still open

- The `bltn_kind()`-backed refactor of §5 (own version).
- The math builtins `floor`/`ceil`/`abs`/`fmin`/`fmax`/`sin`/`cos`/`tan`/`log`/
  `pow` are ALSO float producers and are NOT in the marker list (only `sqrt` is).
  Found while auditing for this version; not fixed here — same class, wider set,
  and it deserves its own red-first row per builtin family.
- **F4** (xmm-resident FP), **F5** (opt-in FMA), **F6** (`i*8` is still
  `imul $0x8`), **F7** (LICM), **F8** (constant shift-range), and the vector types.
