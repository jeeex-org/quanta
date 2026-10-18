# f16/f32 conversion adoption, the FMA folded kernels, and the f32 kernel that was NOT landed

**Status: MEASURED, with one item DESIGNED-NOT-LANDED and labelled as such.** Every
number below is printed with the instrument that produced it and the load it was
taken at. Where a figure is derived from another the derivation is shown. Nothing
projected.

Compiler pinned for every figure: `compiler/0.0.249/bin/x86/qc`, md5
`14fd1086617bb1b37a502a33c624c802` (the golden the task named). Note the tree moved
under this work — peers landed `0.0.250/0.0.251/0.0.252` and their codegen commits
during it — so the pin is stated rather than read from `VERSION`.

Load is LABELLED on every absolute figure. This box ran at `loadavg` 8-24 through
this session (a 20-core box with ~8 cores held by the agent host), and the earlier
loader audit measured the SAME tree at 3.148 tok/s at load 12 and 1.85 tok/s at
load 21. **No measurement here is taken across load bands without saying so, and
where two arms could not be interleaved the load of each is printed.**

---

## 0. What was asked, and what this unit actually did

| # | item | outcome |
|---|---|---|
| 1 | adopt the language's native f16/f32 conversions in `lib/std`, delete the hand-rolled ones | **LANDED.** `f32_to_f64` and BOTH copies of `f16_to_f64`. Exhaustive agreement evidence, and it unblocked a compiler landmine on the way (§1) |
| 2 | an f32 variant of the fused Q4_K / Q6_K kernels behind its own default-OFF flag | **NOT LANDED.** Design complete and recorded in §3 with its exact encodings and the caller change it needs; it was deliberately not shipped unverified. This is the honest gap in this unit |
| 3 | FMA in the kernels | **LANDED** with its own flag, its own bar, and a measured bound (§2) |
| 4 | the per-row invariant arg stores in `pl_run_rows_map` | **NOT TOUCHED.** 1 and 3 consumed the budget and 4 is the smallest lever on the list (the previous unit's estimate was <0.5%, explicitly unmeasured) |

The three commits: `d8e7b5fb` (1), and the FMA commit (3).

---

## 1. A34 — the native conversions, and the float-inference landmine under them

### 1.1 What changed

`lib/std/gguf.quanta`'s `f32_to_f64` was a software conversion in Quanta source:
four `mem_load8`s, sign/exponent/mantissa reassembly, and a `while` loop whose trip
count was the exponent magnitude. Measured by the previous unit at **78 ns/element
at 64 elements and 363 ns/element at 6144** — ~100x a single `cvtss2sd`, and a
landmine under every f32/f16 path. `f16_to_f64` was the same shape, and was
**defined twice in the tree** (`lib/std/gguf.quanta:1719`, `lib/std/fs.quanta:196`).

All three now call the language's own conversion builtins:

```
fn f32_to_f64(ptr) -> f64 { … return f32bits_to_f64(b) }     // movd + cvtss2sd
fn f16_to_f64(ptr) -> f64 { … return f16bits_to_f64(b) }     // integer f16->f32 + cvtss2sd
```

The byte gather is four/two `mem_load8` rather than `mem_load32`/`mem_load16` for a
concrete reason: **`std/fs` defines functions with those exact names, and a
user-defined name shadows the builtin** — which is how `fs`'s own `mem_load16` works
today. Four `movzx` + adds is still two orders of magnitude under the loop it
replaces; it is not the bottleneck.

**Which copy binds was measured, not assumed.** By Quanta's first-definition-wins
rule for duplicate names — verified with a three-file probe (`import a; import b;
fn foo(){…}` then `foo(1)` still calls `a`'s, and a local definition does NOT
override an import) — and because `gguf.quanta` imports `std/fs` before defining its
own `f16_to_f64`, the **std/fs copy is the one a program compiles to**. Both were
replaced with the identical native form and both are covered by the agreement row,
so which one binds does not change the result. (This is recorded because it is the
kind of fact a reader would otherwise have to re-derive.)

### 1.2 Agreement with the deleted bodies — measured, exhaustively

`tests/lfm2_f32conv_agree_test.quanta` carries **verbatim copies of the deleted
bodies** (extracted from git, renamed `old_*`) and compares them against the shipped
form. The criterion is applied to the **INPUT pattern**, not to classifying the
outputs, so it does not depend on either converter's behaviour:

* an input is a NaN iff its own exponent field is all ones and its mantissa is
  non-zero (pure integer arithmetic on the pattern);
* **non-NaN input** → the two must be bit-identical;
* **NaN input** → reported separately.

| sweep | non-NaN inputs | result |
|---|---|---|
| f16, **all 65,536 patterns**, vs gguf's copy | 63,490 | **0 bit-diffs** |
| f16, **all 65,536 patterns**, vs fs's copy | 63,490 | **0 bit-diffs** |
| f32, structured (all 512 sign×exponent × 4,096 strided + 13 boundary mantissas = 2,103,808 cases) | 2,095,594 | **0 bit-diffs** |
| f32, **FULL, all 2^32 = 4,294,967,296 patterns** | 4,278,190,082 | **0 bit-diffs** |

Raw output of the full sweep (background run, `tests/lfm2_f32conv_agree_test.conf` = `1`):

```
f16 exhaustive 65536: non-NaN-input bit-diffs: gguf=0 fs=0  | NaN inputs=2046 differing=2045 where the OLD result is NOT a NaN=1023
f32 structured: cases=2103808 non-NaN-input bit-diffs=0 | NaN inputs=8214 differing=8212 where the OLD result is NOT a NaN=0
f32 FULL 2^32 starting...
f32 FULL 2^32: patterns=4294967296 non-NaN-input bit-diffs=0 | NaN inputs=16785428 differing=16785425 where the OLD result is NOT a NaN=0
RESULT PASS: every non-NaN input is bit-identical old-vs-native
```

So: **every finite value, both zeros, every subnormal and both infinities convert
bit-identically.** Only NaN inputs move, and there the deleted code was wrong in a
way worth recording: its f16 NaN branch did `f64of(0 - 0x7FF8000000000000)`, and
`0 - pattern` is a **two's-complement negation, not a sign-bit set** — it yields
`0x8008000000000000`, exponent 0, mantissa 0x8000000000000, i.e. a **subnormal of
value 2^-1023, for every one of the 1,023 negative-NaN patterns.** A NaN weight
silently became a finite one. The f32 body synthesised `Inf - Inf`, which is x87's
"indefinite" value — always the *negative* quiet NaN — so a positive NaN weight came
back with its sign flipped.

**None of that is a rounding difference and none of it is a regression**: adopting
the builtin fixes both. No finite weight moves, which is why the loader's
bit-exact gate is unaffected (§4).

**Two probe faults were found and fixed on the way, and both had produced a
plausible wrong number**, so they are recorded: (a) classifying NaN with `v != v`,
which on this tree returns **false even for a NaN** — it reported all 2,046 f16 NaN
patterns as value failures; (b) extracting a float exponent with floor division on a
*signed* carrier, where `-0xFFF8000000000000 / 2^52` floors to -2048 so the exponent
mask returned 0 for every negative pattern — it reported 1,023 negative f16 NaNs as
"the old conversion produced a subnormal". The second reading was **right by
accident**; the first was simply wrong.

### 1.3 THE LANDMINE: the compiler does not know the new builtins are floats

This is the part worth the most to anyone reading this file.

The first version of the adoption **silently broke the unfused decode path**. With
all fused flags OFF the loader's first-token argmax became **25,438** against the
oracle **597**, and all 128,000 logits differed; with the fused flags ON it was
correct. Nothing about the conversions' *values* explains that asymmetry — and the
exhaustive sweep above says the values are identical for every non-NaN input.

Root cause, in the compiler:

`compiler/src/x86/funcscan.quanta: ret_expr_is_float()` infers whether a function
returns a float by scanning its return expression's tokens for a fixed marker list:
`i2f`, `fadd`, `fsub`, `fmul`/`fmadd`, `fdiv`, `fconst`, `f64_*`, `fq*`, `sqrt` (or
a float literal). **`f16bits_to_f64` and `f32bits_to_f64` are not in it.** A body
whose only float evidence is the new builtin is therefore inferred
**integer-returning**, and callers mistreat the returned f64 — exactly the class the
comment above that function already documents for a hand-rolled body
("`f16_to_f64(p) * 50.0 -> 2.27e+20` instead of `0.0042`, because the raw
`0x3F1644…` pattern was multiplied"). The old bodies contained `fmul`/`fdiv`/
`f64of`, so they matched the list by accident.

Why the flag-ON arm was unaffected: the folded kernels decode f16 **in-kernel**
(`vcvtph2ps` on the raw bytes) and never call `f16_to_f64`. Only the unfused
dequant path does.

The proof is a bisect, not an argument, and it was run against a **pristine
`git worktree` of HEAD with the byte-identical pinned compiler** and the identical
probe source, so no other difference existed:

```
arm                                            first_argmax   logits_xor_bits
mine (fs + gguf adopted, no annotation)            25438        9146771536547989141   WRONG
fs reverted, gguf adopted                           597       -47059246578783917     correct
both reverted (pristine HEAD)                       597       -47059246578783917     correct
```

and the value hypothesis was killed separately: re-running with the deleted body's
`exp==31` behaviour restored verbatim ("native except exp==31") was **still**
25438 — so it was never a changed value, it was the *inference*.

**The fix, inside this unit's ownership:** declare the return type explicitly.

```
fn f16_to_f64(p) -> f64 { … }
fn f32_to_f64(ptr) -> f64 { … }
```

After that: `first_argmax=597` with the digest identical to pristine, in **both** the
flags-OFF and flags-ON configurations. There is no remaining difference between this
tree's loader and pristine HEAD's on any configuration measured.

**ROUTED TO THE COMPILER OWNER (one line, and it removes the trap for everyone):**
add the four conversion builtins — `f16bits_to_f64`, `f32bits_to_f64`,
`f16bits_to_f32`, `f32bits_to_f16` — to the marker list in `ret_expr_is_float()`, or
better, treat a call to any builtin the emitter tags float as float evidence.
`f64_to_f16bits`/`f64_to_f32bits` already match by prefix (`f64_*`). Until that
lands, wrapping any of these conversions in a helper requires an explicit `-> f64`,
and the failure mode is a silent numeric difference in an unrelated path.

---

## 2. FMA in the folded kernels — landed, with its own flag and its own bar

### 2.1 Design

`lib/std` contained **no `vfmadd` anywhere** while `/proc/cpuinfo` reports `fma`.
Every multiply-accumulate was a separate `vmulpd` + `vaddpd`. The FMA variants are
new builders emitted into their **own RWX regions**, selected by
`mm_set_fused_fma` (default OFF), which is a **modifier** of `mm_fused_q4k` /
`mm_fused_q6k`: it changes which kernel those routes dispatch, it does not add a
route. The f64 kernels are untouched and their bytes are unchanged.

Per 4-weight group:

* **Q4_K** (`j_f_low_fma` / `j_f_high_fma`), **4 FP ops → 2**:

  ```
  vmulpd  ymm1, ymm1, ymm6            q*K
  vsubpd  ymm1, ymm1, ymm7            w = q*K - M
  vmulpd  ymm1, ymm1, [r10]           w*x
  vaddpd  ymm0, ymm0, ymm1
      becomes
  vfnmadd213pd ymm1, ymm6, ymm7       ymm1 = -(q*K) + M   = -w
  vfnmadd231pd ymm0, ymm1, [r10]      ymm0 = -((-w)*x) + ymm0 = ymm0 + w*x
  ```
  This also halves the fold's **dependency chain** (2 dependent ops instead of 4),
  which matters more than the instruction count: the seven dequant ops above it are
  independent and issue underneath it.

* **Q6_K** (`q6_group_fma`), **4 FP ops → 3**:

  ```
  vmulpd ymm6, ymm6, ymm2             *sc   (exact)
  vmulpd ymm6, ymm6, ymm1             *d    (rounds -- MUST stay a separate
                                             multiply: it is where the reference rounds)
  vfmadd231pd ymm0, ymm6, [r10]       acc += (q*sc*d)*x, ONE rounding
  ```

* **The chain kernel is deliberately NOT fused.** `jit_f_build_chain_q6k()` keeps the
  reference's strict left-to-right scalar accumulation; its fold is four SERIAL
  `vaddsd` whose operands are already-computed products. There is nothing an FMA can
  fuse that the reference has not already rounded, so it would gain **zero**
  instructions and move bits for no speed. It stays on the f64 route even with the
  flag on. (This is why the tied output projection, 7.4% of a token, does not move.)

**Encodings verified by EXECUTION.** The three forms were assembled *and run* in a C
harness with known operands, asserting on all four lanes that
`vfnmadd213pd y1,y6,y7 == -(y1*y6)+y7`, `vfnmadd231pd y0,y1,m == -(y1*m)+y0` and
`vfmadd231pd y0,y6,m == y6*m+y0`. All 16 lane assertions MATCH. A previous unit lost
a day to `vpermilpd`'s lane-relative imm8 selectors, so no FMA operand-order
assumption was taken on faith.

Checked for the two known traps in this file: every `jbytes(n,hex)` call uses the
correct byte count (`tests/lfm2_jbytes_len_check.py`), and no `vpermilpd` is
introduced (the factor broadcasts reuse the existing verified `vpermpd`).

### 2.2 Kernel-level A/B — interleaved, one process, 21 cycles

`tests/lfm2_fma_kernel_ab_test.quanta` PART 1, on real tensor rows, both kernels
alternating inside one loop, `clock()` unit unverified repo-wide so only the RATIO
is read. **`loadavg` 11.4-17.4.** Two independent estimators are reported: `min` is
min-of-21 and `sum` is the total over all 21 interleaved cycles.

| tensor | dtype | cols | f64 best-of-21 | FMA best-of-21 | **f64/FMA min** | **f64/FMA sum** |
|---|---|---|---|---|---|---|
| `ffn_gate.0` | Q4_K | 2048 | 320,186 | 272,626 | **1.174x** | **1.174x** |
| `ffn_up.0` | Q4_K | 2048 | 329,435 | 281,416 | **1.170x** | **1.170x** |
| `ffn_down.3` | Q6_K | 10752 | 1,347,054 | 1,284,653 | **1.048x** | **1.067x** |
| `attn_v.2` | Q6_K | 2048 | 416,420 | 389,876 | **1.068x** | **1.086x** |

(Raw, exactly as the harness printed it: `f64_best=320186 fma_best=272626
f64_over_fma_min_x1000=1174 f64_over_fma_sum_x1000=1174`, and the analogous lines
for the other three. The cycle SUMS are not quoted because the harness prints the
sum *ratio* and the per-arm minima, not the totals — reporting totals it did not
print would be exactly the fabricated-number failure this series forbids.)

**The two estimators agreeing to 0.1% on the Q4_K rows is the reproducibility check
this measurement needed**, and it is exactly what was missing earlier. So: the FMA
form is **~17.4% faster on the Q4_K chain** (78.7% of the model's matvec elements)
and **4.8-8.6% on Q6_K** — which is where the instruction counts predicted it: Q4_K
drops 4 FP ops to 2 of an 11-instruction body, Q6_K 4 to 3 of 14.

**Three revisions of this row are worth recording, because each produced a plausible
wrong number and the box is the reason:**

1. A single un-interleaved sample said **1.176x** for Q4_K.
2. min-of-5 over 256 rows said **1.025x** for the same tensor.
3. min-of-11 over 512 rows said 1.178x — and a *fourth* run of the same binary at
   `loadavg` 11.7 said **1.401x** for `ffn_gate` and **1.027x** for `ffn_up`.
4. min-of-21 over 256 rows with the sum estimator added: stable at 1.174/1.170x,
   and the first three are noise.

The 1.401 outlier is why the `sum` estimator exists: a whole-arm interference burst
defeats min-of-N, and interleaving alone does not fix that. Nothing in this document
quotes revisions 1-3.

**Corroboration, a second process of the same binary** (`loadavg` 11.7-13.7):
`ffn_gate.0` 1.174x / 1.185x, `ffn_up.0` 1.176x / 1.168x, `ffn_down.3` 1.059x /
1.060x, `attn_v.2` 1.054x / 1.086x. So across two runs the Q4_K chain is
**1.170-1.176x** and Q6_K is **1.048-1.086x**; those ranges are what §7.3 quotes.

### 2.3 The bound the FMA path is allowed, MEASURED

`tests/lfm2_fma_kernel_ab_test.quanta` PART 2 — two full sequences in ONE process,
fma=0 then fma=1, all 128,000 logits diffed. `loadavg` at the run: 12-17.
Witnesses: `fma_used` runA=**0**, runB=**1** (so the second arm really dispatched
the FMA kernel, and a "matching" arm that never ran it is excluded).

```
EXCURSION logit_mism=124782  max_abs_diff_bits=4407335185335451648
          max_abs_diff=0.000000  max_ulp=1116224  sign_flips=0
max logit |ref|=23.948346  excursion_x1e18=2921  excursion_over_maxlogit_x1e15=1
argmax_mism=0
first_argmax fma=0=597 fma=1=597
ids fma=0: 597 4695 20589 34 496 2992 355 229 26 19 26 39 41774 415 278 1579 1049 2426 440 4695 10966 267 2936 1579
ids fma=1: 597 4695 20589 34 496 2992 355 229 26 19 26 39 41774 415 278 1579 1049 2426 440 4695 10966 267 2936 1579
PASS
```

**The documented bound, stated exactly:**

* **argmax IDENTICAL for all 25 steps** (the prefill-token argmax plus 24 generated),
  and **the first 24 generated ids IDENTICAL**. First-token argmax 597 in both arms.
* **124,782 of 128,000 logits (97.5%) differ in their low bits.**
* **max |difference| = 2.921e-15** (`excursion_x1e18 = 2921`; exact bits
  `4407335185335451648`). Against the reference's largest logit, 23.948346, that is
  **~1.2e-16 relative** — under 1 ULP of an O(1) logit, accumulated over ~9,000
  terms per logit.
* max ULP distance 1,116,224 and **0 sign flips** — the ULP column is large only
  because it is dominated by logits near zero, where 1 ULP is ~1e-320; the absolute
  bound above is the one that means something.
* `print_f` has six fractional digits, so a 1e-15 excursion renders as `0.000000`.
  The harness therefore **also** prints the scaled integers and the raw bits, and
  this document quotes the scaled form. Reporting `0.000000` alone would have been
  the "close enough" failure the brief forbids.

**Reproduced three times, byte-identical**: `logit_mism=124782`, `max_abs_diff_bits=4407335185335451648`,
`max_ulp=1116224`, `excursion_over_maxlogit_x1e15=1`, `argmax_mism=0` — in three
separate processes (`loadavg` 12-17). That is what makes it a *bound* rather than a
sample.

Kernel level (PART 1, every timed row through both kernels, 256 rows per tensor):
`rows_bit_different = 0` for `ffn_gate.0`, `ffn_up.0` and `attn_v.2`; for
`ffn_down.3`, 85 of 256 rows differ in **bits** while every float comparison in the
magnitude column stays false — `d < 0`, `d > prev` AND `d == 0` all false is the
signature of `d` being **NaN**, i.e. both kernels returned a NaN with different bit
patterns on those rows of that tensor under this harness's SYNTHETIC activation. The
harness therefore classifies by the **bit pattern** (an integer NaN test; the float
`v != v` is unusable on this tree) and reports `both_results_nan` /
`exactly_one_nan` separately from the value bound — an `exactly_one_nan` count
would be a class difference and is the column that must stay 0.

An earlier revision of this paragraph attributed those rows to `+0.0` vs `-0.0`
differences; that was **wrong and is recorded as wrong**: the `+0.0/-0.0` reading
came from a run whose magnitude accumulator was itself broken, and the
memory-resident accumulator plus integer NaN classification above is the version
that stands. It is a reminder that a column reading 0 next to a nonzero "rows
differ" count is a contradiction to be explained, never averaged over.

### 2.4 End-to-end paired A/B, with its load on every arm

`tests/lfm2_fma_ab.sh`, arms interleaved **off, on, on, off** in one session, the
decode bench driven by conf field 16, `lens 64/64/64`, every other flag at the
shipped setting, one binary, `fused_fma_used`/`fused_fma_active` echoed per arm.

| arm | `fused_fma` | `loadavg` before -> after | tok/s (run1/2/3) | ms/token (run1/2/3) | first_argmax |
|---|---|---|---|---|---|
| off1 | 0 | 10.49 -> 21.92 | 1.949 / 1.981 / 1.955 | 513.0 / 504.7 / 511.2 | 597 |
| on1  | 1 | 21.92 -> 21.77 | 2.010 / 1.999 / 1.985 | 497.3 / 500.0 / 503.7 | 597 |
| on2  | 1 | 21.77 -> 21.56 | 2.056 / 2.080 / 2.022 | 486.2 / 480.7 / 494.5 | 597 |
| off2 | 0 | 21.56 -> 22.53 | 1.937 / 1.928 / 1.918 | 516.2 / 518.5 / 521.3 | 597 |

**Read honestly, and this is a load-confounded A/B, stated rather than dressed up:**

* The three arms that ran in the **same** band (`on1`, `on2` at ~21.6-21.9, `off2`
  at ~21.6-22.5) do favour FMA: `on1` mean 1.998 tok/s, `on2` mean 2.053, against
  `off2` mean 1.928 — **+3.6% and +6.5%**. The nearest-load pairing available is
  `on1` (1.998) against `off2` (1.928): **+3.6%**.
* **`off1` is NOT a comparator and is not used as one.** Its `loadavg` started at
  10.49 and reached 21.92 before the arm ended, so its three runs straddled a load
  doubling; it read 1.949-1.981, *below* both FMA arms, which is a load artefact and
  not evidence against the flag.
* So: the end-to-end effect is **between +3.6% and +6.5%**, which is inside the load
  swing's reach on this box and is **not** resolvable to better than that here. The
  attributable number is the kernel-level one in §2.2 (1.174x on the Q4_K chain,
  stable to 0.1% between two estimators), because the chain is 56.4% of a token and
  the end-to-end ratio is diluted by everything else that did not change.
* All four arms printed `first_argmax_id=597` and the same 24 ids, and the
  generated text ends in the oracle answer.

### 2.4b Why this moves TOWARD the reference, not away

llama.cpp's own SIMD dot products use FMA and f32. Single-rounding is what the
reference does; the f64 mul-then-add chain was the *more* different of the two. The
flag exists so that the difference is opt-in, measured, and never silently
substituted for a sequence whose gate is bit-exactness.

---

## 3. The f32 kernels — DESIGNED, NOT LANDED (the gap in this unit)

This is the larger of the two kernel levers and it is **not in the tree**. Stated
plainly rather than half-done, and with the design complete enough to execute.

### 3.1 Why it is the bigger lever

The instruction census of the emitted kernels (`docs/plans/performance.md`) is
**26 `vmulpd` / 25 `vcvtdq2pd` / 15 `vaddpd` / 14 `vaddsd`** — every FP instruction is
`*pd`. The `*ps` forms carry **8 lanes per ymm instead of 4**, `vcvtdq2ps` converts 8
int32 at once where `vcvtdq2pd` converts 4, and **x becomes 4 bytes/element instead
of 8**, halving the one operand that is re-read once per ROW.

The tensors, in this loader's convention (`cols = gguf_tensor_dim(idx,0) = ne[0]`,
the contiguous row length; `rows = nelements / cols`):

| tensor | cols | rows | x bytes read per matvec (rows x cols x 8) | weights |
|---|---|---|---|---|
| `ffn_gate` / `ffn_up` | 2048 | 10752 | 176 MB | 11 MB (Q4_K, 0.5 B/elem) |
| `ffn_down` | 10752 | 2048 | 176 MB | 11 MB |

So **x is read 16x more bytes than the weights**, per matvec. (Whether that is
actually paid depends on whether x stays resident: 2048 f64 = 16 KB is L1-sized,
10752 f64 = 86 KB is L2-sized, and both are re-read by every worker. The point
stands that x is the dominant byte stream and halving it is the half of the f32
lever that does not depend on lane count.)

### 3.2 The design, concretely

* **Group becomes 8 weights, not 4.** `vpmovzxbd ymm1, qword [r9]` reads 8 quant
  bytes; low nibbles are weights `[i..i+7]`, high are `[32+i..39+i]` (Q4_K's layout
  is unchanged, only the step is 8 bytes wide instead of 4). 32 groups per super-block
  instead of 64. `r10` still advances 32 bytes per group, because 8 f32 = 32 bytes.
* **Q4_K per group:** `vcvtdq2ps ymm1, ymm1`; factors as f32
  (`vcvtph2ps` gives f32 directly for `d`, `vcvtdq2ps` for the 6-bit scales,
  `vmulps` for `d*Kn`); `vmulps`/`vsubps`/`vmulps [r10]`/`vaddps` — or the FMA form
  `vfnmadd213ps`/`vfnmadd231ps`, same structure as §2.1 with the `ps` opcodes.
* **Q6_K per group:** `vpmovzxbd ymm6, qword [r9]`, the `|((qh>>2s)&3)<<4` merge and
  `-32` bias on 8 dwords, `vcvtdq2ps ymm6, ymm6`, `vmulps` by `sc` and `d` (f32),
  `vmulps [r10]`, `vaddps`.
* **Accumulator is 8 f32 lanes**, reduced at the end (`vextractf128` + `vaddps` +
  a 4-lane horizontal reduce). The lane→element mapping must be re-derived and
  documented: for the f64 kernels element k of a group lands in ymm0 lane k and the
  reduction order is `((l0+l1)+(l2+l3))`; the 8-lane version needs the analogous
  derivation or it changes the summation order for free.
* **The caller must supply f32 x.** This is the real cost of the change and the
  reason it was not rushed: `pl_run_rows_map` passes `pl_x` as f64 and every one of
  the 49 `mem_alloc` sites is `x8`. It needs a **grow-only module-global f32 buffer**
  of `pl_cols` elements, filled once per matvec on the main thread before the pool is
  woken — `pl_cols` conversions per matvec, ~340K per token over 166 matvecs, which
  is noise against 2.43e9 weight elements. **Do not add a per-call `mem_alloc`/`mem_free`**:
  `mem_free` never unmaps (A35), so per-call churn is permanent VA growth.

### 3.3 Why it was not landed

Two honest reasons, in order:

1. **Budget.** Items 1 and 3, plus the bisect that item 1 turned out to require
   (§1.3), consumed the session. Building and *verifying* a second kernel family with
   a new operand format is a multi-hour item on a box where every verification cycle
   is a compile plus a ~50 s model run.
2. **Risk, and the standing rule that a flag whose ON path crashes is worse than no
   flag.** The JIT emits raw bytes, and the history of this file is a list of exactly
   this class of defect: a `vcvtdq2pd` whose destination overlapped the dwords it was
   converting (which produced `1072693248` out of an `x` of 1.0), a `jbytes(4, …)`
   that declared five bytes and dropped a ModRM byte, a `vpermilpd` broadcast that
   assembled and disassembled perfectly and still produced the wrong factors. A
   half-verified second kernel family is the worst of both worlds.

**What f32 would be worth is NOT stated here**, because it was not measured and this
document does not carry unmeasured numbers. What *is* measured is the ceiling of the
same idea where it can be isolated: the FMA form alone, which halves the dependency
chain without touching the lane count, is 1.178x on the Q4_K chain.

---

## 4. The EXISTING flags' bit-exact gate is untouched

`tests/lfm2_fused_logits_test.quanta`, run AFTER the adoption and with the pinned
0.0.249 compiler, 9 passes in one process over all 128,000 logits:

```
CONTROL pass1-vs-pass0 : logit_mism=0 argmax_mism=0
Q4K     pass2-vs-pass0 : logit_mism=0 argmax_mism=0 max_abs_diff_bits=0
Q6K     pass3-vs-pass0 : logit_mism=0 argmax_mism=0 max_abs_diff_bits=0
BOTH    pass4-vs-pass0 : logit_mism=0 argmax_mism=0 max_abs_diff_bits=0
CHAIN   pass5-vs-pass0 : logit_mism=0 argmax_mism=0 max_abs_diff_bits=0
GLU     pass6-vs-pass0 : logit_mism=0 argmax_mism=0 max_abs_diff_bits=0
ATTN    pass7-vs-pass0 : logit_mism=0 argmax_mism=0 max_abs_diff_bits=0
CONV    pass8-vs-pass0 : logit_mism=0 argmax_mism=0 max_abs_diff_bits=0
pass0_argmax0=597
pass4 first 24 ids: 597 4695 20589 34 496 2992 355 229 26 19 26 39 41774 415 278 1579 1049 2426 440 4695 10966 267 2936 1579
PASS: fused Q4_K, fused Q6_K, both, and the scalar-chain tied projection are IDENTICAL to the existing path (all 128000 logits)
DONE  EXIT=0
```

Every dispatch witness was asserted inside the test (`fused_q4k_used`, `fused_q6k_used`,
`fused_chain_used`, `fused_glu_used`, `fused_attn_used`, `fused_conv_used` all 1 on
the passes that set them). **Worth recording: this gate was RED before the `-> f64`
annotation of §1.3** — pass0 gave 25438 and Q4K/BOTH/CHAIN/GLU/ATTN/CONV showed
`logit_mism=128000 max_abs_diff_bits=4626850878725524093`. The green above is the
state after the fix, and it is a stronger statement than the previous unit's because
the pristine-vs-mine probe digests also match (§1.3).

---

## 5. Memory

`tests/lfm2_argmax_probe.quanta` reports `/proc/self/status` fields for the shipped
configuration (`loadavg` 16.6):

```
vm_start_kb=5930404 vmpeak_start_kb=5930404 rss_start_kb=1742684
vm_end_kb=5965896   rss_end_kb=1752584   (prefill + 24 steps)
```

VmSize grows by 35,492 KB over the whole run and RSS by 9,900 KB. **This is NOT a
per-token leak and it is not attributable to this unit's changes**: the loader audit
already measured the forward at exactly 0 bytes/token after the norm-cache fix, and
the residual here is the probe's own `mem_alloc(4096)`-sized `/proc` read buffer
(allocated once) plus the model page-in. The two new FMA kernels map two further
64 KB RWX regions per process when the flag is on — a one-time, bounded cost, and
they are allocated from the same `jit_f_alloc` path the existing kernels use.

`mem_alloc` is a raw `mmap` and `mem_free` never unmaps, so nothing in this unit adds
per-call alloc/free churn. The FMA kernels are emitted once, lazily, behind the same
fail-closed `if table != 0 { return 0 }` guard the existing kernels use.

---

## 6. Gate

See §7 for the run and its counts.

---

## 7. Gate, reproduce, and the honest gap

### 7.1 Gate

```
QC=$PWD/compiler/0.0.249/bin/x86/qc bash test_suites/scripts/run_tests.sh
md5 14fd1086617bb1b37a502a33c624c802        (the compiler every number here was measured with;
                                             NOT derived from VERSION, which peers are moving)
```

```
=== Results: 242/242 pass, 0 fail (incl. 0 compile-fail) [rows: EXPECTED.tsv] ===
=== Security: 8 passed, 0 failed, 0 known issues ===
=== Perf: 3 passed, 0 failed (baseline 4000ms) ===
  STDLIB: 114/114 GREEN
```

`EXPECTED.tsv` is now **242** rows (the loader audit saw 239, 0.0.248 saw 238 — peers keep growing
the suite; a rising row count is not a regression). Every stage is GREEN with **two** exceptions, both
version artefacts and both the compiler peer's own feature rows for compilers NEWER than the one pinned
here:

```
  deadstore-guard  : RED  (0.0.250 F2: the block-boundary flush stops storing dead temporaries)
  terminator-guard : RED  (0.0.252 F3: a block terminator's operand is not stored-and-reloaded)
GATE_EXIT=1
```

Both are `emitted loop SHAPE, from the object bytes` rows for 0.0.250/0.0.252 codegen features, so they
cannot pass under a 0.0.249 compiler. The row the task warned about (`marshal-guard`, 0.0.249 F1) is
**GREEN**. `native`, `stdlib`, `security`, `performance`, `valgrind`, `fuzz`, `differential`, `qobj`,
`gguf-corrupt`, `multi-tu`, `bare-metal` and the rest are all GREEN.

`tests/lfm2_jbytes_len_check.py`: **180** `jbytes()` calls (up from 159 — the FMA builders added 21),
**0 mismatches, PASS**. This was run because emitted code was touched.

### 7.2 Reproduce

```
cd /opt/tali/quanta && ulimit -c 0 -v 32000000
export QC=$PWD/compiler/0.0.249/bin/x86/qc        # md5 14fd1086617bb1b37a502a33c624c802

# --- 1. the conversion agreement (f16 exhaustive + f32 structured) ---
$QC -O tests/lfm2_f32conv_agree_test.quanta /tmp/fagree
printf '0\n' > tests/lfm2_f32conv_agree_test.conf && /tmp/fagree     # ~1.2 s
printf '1\n' > tests/lfm2_f32conv_agree_test.conf && /tmp/fagree     # FULL 2^32, ~1 h 55 m

# --- 2. the fast single-answer harness: argmax + logits digest + ids + witnesses ---
#     conf: <nw> <f4> <f6> <fch> <fglu> <fattn> <fcv> <ffma> <ff32>
$QC -O tests/lfm2_argmax_probe.quanta /tmp/ap
printf '20 1 1 1 1 1 1 0 0\n' > tests/lfm2_argmax_probe.conf && ( ulimit -c 0 -v 32000000; /tmp/ap </dev/null )

# --- 3. the FMA flag: kernel A/B (PART 1) + its model-level bar (PART 2) ---
$QC -O tests/lfm2_fma_kernel_ab_test.quanta /tmp/fab && ( ulimit -c 0 -v 32000000; /tmp/fab </dev/null )

# --- 4. the EXISTING flags' bit-exact gate ---
$QC -O tests/lfm2_fused_logits_test.quanta /tmp/ex && ( ulimit -c 0 -v 32000000; /tmp/ex </dev/null )

# --- 5. emitted-code helper check (run after touching any jbytes) ---
python3 tests/lfm2_jbytes_len_check.py
```

### 7.3 The honest gap

Two anchors, both LABELLED by load. **No quiet window was available in this session**: `/proc/loadavg`
sat between 8.5 and 24 the entire time (a 20-core box with ~8 cores held by the agent host), so the
low-load anchor the previous unit used (3.148 tok/s at `loadavg` ~12) could not be re-taken and is
quoted from that unit, not re-measured here.

**At `loadavg` 21.6-22.5 (the band all four A/B arms' last three sat in), 64-token runs, shipped config
(`fused_fma=1`):**

| arm | tok/s (run1/2/3) | ms/token |
|---|---|---|
| on1 | 2.010 / 1.999 / 1.985 | 497.3 / 500.0 / 503.7 |
| on2 | 2.056 / 2.080 / 2.022 | 486.2 / 480.7 / 494.5 |

* Gap to the **15 tok/s** target: **7.3x - 7.6x** (on the 1.985-2.080 band).
* Gap to llama.cpp's **17.32 tok/s** on the same model and CPU: **8.3x - 8.7x**.

For reference, the same tree at `loadavg` ~12 measured 3.148 tok/s in the previous unit's session and
1.85 tok/s at `loadavg` 21 — so the 7.3x above is a **contended-window** figure and the 4.8x that unit
reported at load 12 is the same tree's quiet-window figure. **Neither is a code regression; they are
two points on the box's load curve, and the load curve is 1.7x wide.**

**What this unit moved, measured:**

* the hand-rolled float widening replaced by the native conversions, agreed **bit-for-bit on every
  non-NaN input over all 65,536 f16 and all 2^32 f32 patterns** (§1.2);
* a silent trap disarmed — adopting them *without* the `-> f64` annotation broke the unfused decode
  path (first-token argmax 25438 vs 597) with no diagnostic at all (§1.3);
* **1.170-1.176x on the Q4_K chain** (78.7% of the model's matvec elements) and 1.048-1.086x on Q6_K,
  from FMA alone, behind a default-OFF flag, with a measured logit bound of **2.921e-15 absolute /
  ~1.2e-16 relative and identical argmax and ids** (§2).

**What it did NOT move, said plainly:** the loader is still not where the remaining gap lives. The
previous unit's verdict stands unchallenged — the binding constraint is **core over-subscription**
(the same pool job is 45 us at nw=8 and 185 us at nw=20, and at nw=20 the pool job is no faster than the
main thread). A 17% kernel win on 56.4% of a token is a ~9.6% ceiling on the token, and on this box a
9.6% effect is at the edge of what an end-to-end A/B can resolve (§2.4). Closing 7.3x to 15 tok/s is
**not** a loader-side job from here.

**Three levers remain, ranked by what is measured about them:**

1. **Core availability / pool sizing.** Unchanged and untouched by this unit. Nothing here moves it.
2. **The f32 kernel family (§3, not landed).** The one lever with a *multiple*, not a percentage, as its
   ceiling: 8 lanes instead of 4 plus half the x traffic. Its prerequisite is now done.
3. **The per-row invariant arg stores in `pl_run_rows_map`** — the only item of the brief not touched at
   all. Still an estimate (<0.5%), still unmeasured, and now further down the list than the f32 work.

---

## 8. Routed, not done here

0. **A float local does not survive `closure_call`.** While building PART 1 of the
   FMA harness, a `let maxd: f64 = 0.0` accumulator read back exactly `0.0` at the
   end of a loop that had counted 85 differing rows in the same call — i.e. it was
   destroyed. Moving the identical accumulator into MEMORY made the column report a
   real value on the next run. A control settled the scope: **an ordinary Quanta
   function call DOES preserve a live f64 local across it** (verified with a
   two-function probe), so the loss is specific to the `closure_call` path. It does
   **not** affect the shipped loader — every kernel call there writes its result
   straight to memory (`mem_store(pl_y + r*8, jit_f_apply_folded(fargs))`) and keeps
   no float live across the call — and it does not affect the model-level bound,
   whose loop has no call in it. It is routed because it is a silent-wrong-number
   class for anyone who does keep one: the fix belongs in the emitter's flush for
   `CLOSURE_CALL`, and it should pour any live float vregs to their home slots the
   way a normal call does.


1. **`ret_expr_is_float()` does not know the f16/f32 conversion builtins**
   (`compiler/src/x86/funcscan.quanta`). One line: add `f16bits_to_f64`,
   `f32bits_to_f64`, `f16bits_to_f32`, `f32bits_to_f16` to the marker list, or treat
   any float-tagged builtin's call as float evidence. Until then, a wrapper around
   one of them needs an explicit `-> f64` and the failure is a silent numeric
   difference in an unrelated path. This unit worked around it in `lib/std`; the
   compiler-side fix belongs to the arithmetic campaign, which already owns F5.
2. **The f32 kernel family (§3)** — designed, not landed. Its prerequisite (the
   conversion adoption) is done, so the follow-on starts from a tree where an f32
   path is no longer a conversion benchmark.
3. **f32 x for the pool** — the caller-side half of §3: a grow-only f32 activation
   buffer filled once per matvec in `pl_run_rows_map`. Independent of the kernel, and
   worth doing first because it is testable on its own (`pl_x` converted twice and
   compared bit-for-bit).
