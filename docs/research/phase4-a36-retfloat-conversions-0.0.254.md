# Phase 4 — A36 (0.0.254): `ret_expr_is_float`'s conversion markers

Lever: **A36** — `funcscan.quanta`'s return-type marker list misclassified the
conversion-builtin family in BOTH directions. Filed by the loader peer in
`docs/plans/bugs.md` (commit `bc1e2f24`). Golden `5c23efdd1e0550af170dee95f1fbabec`.

Every number below is MEASURED in this run against `compiler/0.25{3,4}/`.

---

## 1. The mechanism

`ret_expr_is_float(start, end)` walks EVERY token of a function body looking for
floatness MARKERS; `scan_retfloat()` records its verdict in `fn_retflt`, which
`codegen` applies at every call site (`IR_CALL` result tagging) and which
`is_float_vr()` consults for operand marshalling. The conversion family was
handled by one bare prefix:

```
if c1=='6'&&c2=='4'&&c3=='_' { return 1 }        // f64_*
```

which is **too narrow** (no `f16bits_*`/`f32bits_*` producer) and **too coarse**
(it matched `f64_to_f32bits`/`f64_to_f16bits`, which return RAW BITS — an i64, an
INT sink). Both errors are silent.

## 2. Measurement of the defect

`test_suites/codes/ret_conv_infer_test.quanta` (registered in `EXPECTED.tsv`,
rc=114) returns `a_ok*100 + b_ok*10 + 4`:

| compiler | exit | meaning |
|---|---|---|
| 0.0.253 (pre-A36) | **4** | `a_ok=0`, `b_ok=0` |
| 0.0.254 (A36) | **114** | `a_ok=1`, `b_ok=1` |

Supporting shapes (correct = 2 for the first two, 6 for the control):

| probe | 0.0.253 | 0.0.254 |
|---|---|---|
| `fn cvt(p){return f32bits_to_f64(p)}`, caller `d + 1.0` | **0** | **2** |
| same via a `let` (`let t = f32bits_to_f64(p) return t`) | **0** | **2** |
| control `fn cvt3(p){return i2f(p)}` (`i2f` IS a marker) | 6 | 6 |

The consequence the loader peer measured (this is the real-world impact): adopting
the native conversions during loader adoption made the UNFUSED decode path —
flags-OFF — produce argmax **25438** against the oracle **597**, with all 128,000
logits different, while every fused flag stayed bit-exact. Bisected against a
pristine `git worktree` with one pinned compiler. The local mitigation was an
explicit `-> f64` on the wrappers; under the standing policy that is a
workaround, so the capability ships here.

## 3. Two probe shapes that do NOT expose it (recorded so the next run does not burn time on them)

1. `fsubf(cvt(p), i2f(1))` — the `*f` builtins bit-move their operand regardless
   of the tag, so an FP builtin is INSENSITIVE to it. The plain `d + 1.0`
   (arithmetic operator) form is the sensitive one.
2. `f2i(rb)` as a discriminator for direction (b) — `f2i` ALWAYS bit-moves (it
   assumes f64 bits), so `f2i(1065353216)` is 0 whether or not `rb` is tagged. The
   sensitive form is an integer-context op: `rb + 7`.

A third, vivid symptom: `printi(rb)` with `rb` wrongly float-tagged is a COMPILE
ERROR on 0.0.253 (the 0.0.235 float-print rule) — the over-match can turn a valid
program into a non-compiling one, which is a different failure signature from the
producer direction.

## 4. The fix

Name the DIRECTION, not the family:

```quanta
if c1=='6'&&c2=='4'&&c3=='_'&&clen!=14 { return 1 }   // f64_* EXCEPT the raw-bit sinks
if c1=='6'&&c2=='4'&&c3=='o'&&c4=='f' { return 1 }    // f64of: raw u64 -> f64
if c1=='3'&&c2=='2'&&c3=='b' { return 1 }             // f32bits_to_f64 / f32bits_to_f16
if c1=='1'&&c2=='6'&&c3=='b' { return 1 }             // f16bits_to_f32 / f16bits_to_f64
```

`f64_to_f32bits` and `f64_to_f16bits` are exactly 14 characters; the producers
they must not be confused with are 10 (`f64_to_f32`, `f64_to_f16`) and
`f64_load` is 8. `clen` is `tokln(q)`.

**Monotonicity:** for the `f64_` family the change can only REMOVE a match (fixing
the sink over-match), and for f16/f32 it can only ADD one (fixing the missing
producers). It cannot turn a correct inference into a wrong one.

## 5. Verification

| check | result |
|---|---|
| gate (`run_tests.sh`, QC=0.0.254) | **244/244 pass, 0 fail, 0 compile-fail**, 0 RED stages, `GATE_RC=0` |
| fixpoint (from 0.0.253 golden) | `47c96a07 -> 5c23efdd -> 5c23efdd -> 5c23efdd -> 5c23efdd`; distinct(g1..g4)==1 |
| src/bin lockstep after a later comment edit | rebuilt: md5 UNCHANGED (`5c23efdd`), so the committed bin is the fixpoint of the committed source |
| byte-identity vs 0.0.253 | **243 / 244 identical, 1 differing, 0 compile-fail** — and the one differing row IS the new `ret_conv_infer_test.quanta` |
| `bench.sh` | 38/38 compiled, **0 MISMATCH**, `BENCH_RC=0` |
| `verify-release.sh 0.0.254 0.0.253` | **14 passed, 0 failed** |

The byte-identity result is the tightest of the campaign so far: the change only
alters codegen for functions whose return type was MISINFERRED, and the only gate
row containing such a function is the new probe. Everything else is
byte-identical.

## 6. Is a marker list the right shape? (asked, answered: no)

This is the **third** failure of the same mechanism: (i) a `f2i(f64of(n) * 0.5)`
body concluding "returns float" (already documented above the function), (ii) the
missing conversion producers, (iii) the over-matched raw-bit sinks. Each was
silent, and each was found from a symptom rather than from the list.

The correct source of truth already exists: `emitter.quanta`'s
`ft_isnew(nm, nl)` (line ~5278) does exact, length-aware matching and returns a
KIND CODE that **already encodes direction** — `f32bits_to_f64`=1,
`f64_to_f32bits`=2, `f16bits_to_f32`=3, `f32bits_to_f16`=4, `f16bits_to_f64`=5,
`f64_to_f16bits`=6, `f64_to_f32`=7, `f64_to_f16`=8 — and `ft_emit(kind, ii)`
consumes it. A `ret_expr_is_float` that resolved its head-call token through that
one table (with a float-valued flag per kind) would be correct by construction.
This version deliberately does NOT do that refactor (one lever per version); it is
the recorded follow-up.

Also found while auditing, NOT fixed: `floor`/`ceil`/`abs`/`fmin`/`fmax`/`sin`/
`cos`/`tan`/`log`/`pow` are float producers and are absent from the marker list
too (only `sqrt` is present). Same class, wider set, deserves its own red-first
row.

## 7. An unrelated stale comment found in passing

`emitter.quanta` ~5243 still documents the f16 conversions as using the hardware
pair `vcvtph2ps`/`vcvtps2ph` (F16C). **0.0.248 removed the F16C dependency** in
favour of integer bit manipulation, and the `f16c-indep` gate stage proves an f16
program carries 0 F16C opcodes. The comment contradicts both the source and the
gate; it is a documentation defect (docs are derived from source, per the standing
rule) and is left for a version whose lever is documentation.
