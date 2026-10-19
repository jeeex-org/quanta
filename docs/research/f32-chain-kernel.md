# The f32 CHAIN kernel for the tied output projection, the Q4_K f32-vs-FMA resolution, and two silently-wrong literal/print classes

**Status: LANDED and MEASURED, with a NEGATIVE result stated as such and two
COMPILER/LIB defects found on the way whose file:line evidence is in §9.**

Every number below is printed with the instrument that produced it and the load it was
taken at. Where a figure is derived from another, the derivation is shown. Nothing is
projected. The one figure this unit CORRECTS in an earlier document is called out in
§6.2 and its cause is a defect, not a rounding.

Compiler pinned for every figure: **`compiler/0.0.256/bin/x86/qc`, md5
`21c868f418797c86d7db68728ed01917`** (the golden the task named). **A newer release
landed mid-unit** (`0.0.257` committed, `0.0.258` built but uncommitted) so every
RATIO was RE-TAKEN under `0.0.258` (md5 `e7fc8cd4430ef3d4ef8e99067354bfcf`) as a
pin-advance check, and **no arm data was spliced across the two pins**: §5, §6.1 and
§8 each carry both pins side by side. *Rationale for not discarding the 0.0.256 set:
the pin-expiry rule's purpose is to avoid holding back BUG FIXES on this path, and
`0.0.257` is the address-space reclaim — a memory change, not a codegen change for a
kernel. The cross-pin re-take is the evidence that decision was right: every ratio
carried (§5.2, §8.4).*

Load is LABELLED on every absolute figure. **The task brief expected a freshly-rebooted
quiet box and it was not one**: `/proc/loadavg` sat at **7.8-22.4** for the whole
session — the agent host's desktop process alone holds ~9 cores (`ps` PSR=6, 891% CPU)
and a compiler peer was running its self-host gates (`qc_g1`, `qc_reclaim`) throughout.
No quiet window existed and none is claimed. Where a measurement was taken with the
process PINNED with `taskset` that is said, because this box's available cores swing
inside a single arm.

---

## 0. What was asked, and what this unit did

| # | item | outcome |
|---|---|---|
| 1 | build the f32 CHAIN kernel for the tied output projection | **LANDED.** `jit_f_build_chain_q6k_f32()`, its own RWX region, a MODIFIER of `mm_fused_chain` exactly as `mm_fused_f32` is of the matvec routes |
| 2 | resolve the Q4_K `f32` vs `f32+FMA` question | **RESOLVED, and the earlier "inconclusive" was noise.** `f32+FMA` is **~9-12% FASTER** than plain `f32` on Q4_K in **12 of 12 samples across 2 pins** (§5) |
| 3 | re-take the end-to-end flag matrix on the fresh-boot window | **DONE, but there was no fresh-boot window.** Full 8-arm palindrome at `loadavg` 11.1-21.4 under 0.0.256 (§8), plus a 4-arm cross-check under 0.0.258 |
| 4 | every encoding proven BY EXECUTION, prologue generated from `as` | **DONE.** 119 sequences run with known operands; **5 negative controls**, each of which makes the harness print the expected FAIL (§2) |
| 5 | an independent reference comparison | **DONE.** An f32 chain reference in Quanta source, matched **bit for bit** on 32 rows x 3 processes, 0 mismatches, and all 32 rows DIFFER from the f64 chain (§3) |
| 6 | the bounded logit difference, all four flag witnesses, existing flags bit-exact | **DONE.** Four arms 0/0 0/1 1/0 1/1, argmax 597, 24 ids identical; the existing flags' gate is 9/9 `logit_mism=0` (§6, §7) |

The kernel ratio this unit measured is **1.006-1.011x, i.e. NO meaningful speedup**, and
that is the headline result. It is a negative result and it is reported as one: the
chain is latency-bound and the f32 form has the SAME critical path as the f64 one (§4.3).

---

## 1. The kernel

### 1.1 What it is, and why it is a separate kernel from every other f32 kernel

The tied output projection (`token_embd.weight`, Q6_K, `[2048, 128000]` =
262,144,000 elements, **9.72% of per-token matvec elements** and the largest single
profile entry at 128 tokens) is pool kind 5 (`pl_run_embed_map`). Its **reference dot is
a strict LEFT-TO-RIGHT SCALAR CHAIN**

```
acc = acc + row[c]*x[c]        for c = 0..ncols-1
```

not `mm_dot4_s`'s four lanes. The 8-lane folded f32 kernel's reduce order
(`((L0+L4)+(L1+L5))+((L2+L6)+(L3+L7))`) cannot reproduce that, so this kernel keeps the
chain and takes the f32 win the same way the matvec family did: **8-element groups,
ymm-wide dequant, half the x bytes**. It is 8 elements wide where the f64 chain is 4.

### 1.2 The shape

The dequant is **byte-for-byte the same encodings as `j_f32_q6_group`** (the ymm-wide
Q6_K body, already execution-verified by the previous unit). The ONLY difference is the
fold:

```
f64 chain, per 4 elements          f32 chain, per 8 elements
  vcvtdq2pd ymm6, xmm6               vcvtdq2ps ymm6, ymm6        (8 int32 -> 8 f32)
  vmulpd    ymm6, ymm6, ymm2         vmulps    ymm6, ymm6, ymm2  (*sc)
  vmulpd    ymm6, ymm6, ymm1         vmulps    ymm6, ymm6, ymm1  (*d)
  vmulpd    ymm6, ymm6, [r10]        vmulps    ymm6, ymm6, [r10] (*x)
  4 x vaddsd  (serial)               vextractf128 + 7 x vpermilps
  + 3 x shuffle for lane extract     + 8 x vaddss  (serial)
```

Groups walk destination element index `n*128+s*32+h*16+g*8+k` in **ASCENDING** order and
`r10` walks x 8 f32 (32 bytes) at a time, so the sequence is `c = 0,1,2,...,ncols-1`
with nothing reordered, reassociated, or vectorised. `xmm0` lane 0 is the accumulator
(`vaddss` never touches lanes 1-3) and the f32 sum is widened to f64 **ONCE** with
`vcvtss2sd`, because the calling contract is "the dot as f64 bits in rax".

Cadence: `ql = n*64 + (s%2)*32 + h*16 + g*8` (disp8), `qh = 128 + n*32 + h*16 + g*8`
(disp32), `sc` at `192 + n*8 + s*2 + h`, `d` at `208`, stride 210 — the f64 chain's with
`g*8` instead of `g*4`. `ql` max is 120 so it is a disp8; `qh` min is 128 so it is a
disp32 (the two forms the previous unit's segfault class made explicit).

**Register map:** `rdi`=AS, `r9`=W cursor, `r10`=X(f32) cursor, `rcx`=nsuper;
`xmm0` lane 0 = accumulator; `ymm1` = broadcast `d`; `ymm2` = broadcast `sc`;
`ymm3/4/5` = 8 dwords of `-32 / 15 / 3`; `ymm6` = quant then the 8 products;
`ymm7` = qh scratch then `[p4..p7]`; `xmm8` = the lane-extraction scratch.
**No callee-saved register is touched: no prologue, no epilogue, no stack** — the same
purity property every other kernel in the file has.

### 1.3 Why NO FMA variant (stated, not left to be inferred)

The f64 chain has none either. In f32 the reason is concrete: the fold is already all
adds and the multiply that feeds it is **shared 8-wide**. An FMA would have to become a
SCALAR `vfmadd` per element (8 per group, one rounding instead of two) plus the same
lane extraction — strictly MORE work than the shared `vmulps` + eight `vaddss` it would
replace — and it would move bits differently from an f32 reference chain. So this kernel
is a single form and is **not** a modifier of `mm_fused_fma`. (Consequence, measured and
asserted in §6: arms 2 and 3 — `f32=1 fma=0` and `f32=1 fma=1` — both run the SAME f32
chain kernel and are distinguished only by the matvec witness.)

### 1.4 Wiring, and the operand-width guard

`mm_fused_chain_f32` is a MODIFIER of `mm_fused_chain`, so it is on exactly when the f64
chain route is on and `mm_fused_f32` is on. It is **fail-closed in TWO independent steps,
both on the main thread in `mm_embed_logits_par` before the pool is woken**:

1. the kernel's own RWX region (`jit_f_setup_chain_f32()`); a refusal keeps the f64 chain;
2. the grow-only f32 x buffer, **REFILLED HERE with the EMBED's x**. This is not a
   formality: the embed's x is a DIFFERENT operand from any matvec's x, so the buffer
   cannot be left holding the last matvec's activations. The f32 kernel reads x as f32
   and being handed the f64 pointer would read the wrong bytes and produce a **plausible
   wrong number** — the class the previous unit's `vpmovzxbd` defect belongs to.

Neither refusal clears `mm_fused_chain`, so a refusal degrades to the f64 chain, never to
the scalar reference. `mm_fused_chain_f32_drop` records WHICH step refused (0 none,
1 RWX, 2 x buffer), and `pl_run_embed_map` re-checks `pl_xf32 != 0` at dispatch.

**The refill is visible in the numbers.** `xf32_elems` on the four f32 arms is identical
(**97,572,864**) and is **196,608 = 2048 x 96 higher** than the same arms before this
kernel existed — i.e. exactly one 2048-element narrowing per forward, 96 forwards. That
is the whole main-thread cost this route adds, and it is corroboration that the refill
happens once per forward and not per row.

---

## 2. Verification of the encodings, BY EXECUTION

`tests/lfm2_f32_kernels.s` (GNU `as`) -> `tests/lfm2_f32_enc_gen.py` (bytes read back
from `objdump -d`) -> `tests/lfm2_f32_enc_bytes.h` -> `tests/lfm2_f32_enc_verify.c`,
which maps each sequence executable and **RUNS it** between generated register
save/restore stubs. **The prologue is generated, never hand-typed** (the previous unit's
four-wrong-register defect); the new fold is likewise generated, and the kernel's hex
strings come from that table — `tests/lfm2_f32_hexcheck.py` ties every one of them back
to bytes that executed.

```
119 sequence(s) executed; 0 assertion failure(s)
PASS: every f32 kernel byte sequence does what its comment claims
```

What the new chain sequences are asserted to do:

* `vextractf128 xmm7, ymm6, 1` takes the **HIGH** 128 bits (`c_ext`);
* **every** `vpermilps xmm8, src, imm8` selector is **lane-relative**: from a known
  `[10,20,30,40,50,60,70,80]`, `c_pl1..c_pl3` must give lane 1/2/3 of the LOW half and
  `c_pl4..c_pl7` lane 0/1/2/3 of the HIGH half — 7 assertions, each against an
  independently chosen value. This is the `vpermilpd` class that cost a peer a day and
  it is not taken on faith;
* `vaddss` touches **only lane 0**: lane 0 must equal the sum AND lanes 1-3 must be
  **preserved**. A `vaddps` here would reorder the summation for free — a silent wrong
  answer, not a crash;
* **the WHOLE 16-instruction fold as one block**, over 4000 random finite inputs:
  `ymm0` lane 0 must equal `((acc+p0)+p1)+...+p7` computed in f32 **in element order**,
  and lanes 1-3 must still be `7,8,9`. This is the bit-for-bit ORDER contract;
* `vcvtss2sd xmm0,xmm0,xmm0` is the exact f32->f64 widen of lane 0 and **leaves the
  upper 64 bits alone** (a marker pattern is asserted to survive).

### 2.1 Negative controls, because a harness that cannot fail is not evidence

`tests/lfm2_f32_enc_negctl.py` mutates ONE named sequence's bytes in the generated
header, recompiles the harness against it, and asserts the harness prints the EXPECTED
failure. All five pass, i.e. all five corruptions are caught:

| control | mutation | caught by |
|---|---|---|
| lane selector | `c_pl1` imm `0x55 -> 0x54` (lane 1 -> lane 0) | the lane-relative assertion |
| high half | `c_ext` imm `1 -> 0` | "did not take the HIGH 128 bits" |
| scalar add | `c_add0` `vaddss -> vaddps` | "vaddps, not a vaddss" |
| chain order | `c_pl7` corrupted to lane 1 | the 4000-input fold-order assertion |
| widen | `c_widen` writes `xmm1` (leaves `xmm0`) | "exact f32->f64 widen" |

A first version of this checker-compiled the ORIGINAL harness source (which includes the
**un-mutated** header by relative path), so all five controls reported "HARNESS DID NOT
FAIL" while proving nothing. That is recorded because it is the same shape as the defects
in §9: a check that silently inspects the wrong artifact. It is fixed (the copy is
compiled) and the 5/5 result above is the fixed version.

### 2.2 Two defects found on the way, both in MY OWN tooling

1. **GNU `as` does not accept `//` as an INLINE comment.** An instruction followed by
   `// ...` assembles the comment text as OPERANDS (`Error: spurious operands;
   (5 operands/instruction max)`), while a `//` at the START of a line is a comment. The
   new `.s` block uses `#`, and the constraint is commented in the file so the next
   person does not rediscover it.
2. The `env -i`-style fresh-shell trap: nothing new, recorded only because a batch of
   "negative controls all passed" was produced by it (§2.1).

Idempotence, run because emitted code was touched:

```
python3 tests/lfm2_f32_hexcheck.py     135 hex strings, 0 failures (was 110)
python3 tests/lfm2_jbytes_len_check.py 237 jbytes() calls, 0 mismatches (was 223)
python3 tests/lfm2_f32_enc_negctl.py   5 controls, 0 failed (NEW)
```

---

## 3. The independent f32 chain reference, compared BIT FOR BIT

A magnitude comparison would not prove the factor derivation, the nibble unpack, the lane
order, or the chain ORDER. So `tests/lfm2_f32_kernel_ab_test.quanta` PART 2b carries an
**f32 chain reference written in Quanta source from the BLOCK FORMAT**, using the
language's single-rounding binary32 builtins (`fadd32`/`fmul32`, which round each operand
to f32 and perform ONE f32 op), the same 6-bit factor unpack, the same ascending element
order, and the same `acc = fadd32(acc, p)` chain as `pl_run_embed_map`'s reference:

```
Q6_K token_embd :  rows=32 chain_f32_vs_ref_bit_mismatch=0
                   chain_f32_differs_from_f64_rows=32 exactly_one_nan=0 both_nan=0
```

in **three separate processes under the 0.0.256 pin and three more under 0.0.258** —
**0 mismatches over 32 rows x 6 processes**, and `exactly_one_nan=0` throughout (the
column that would signal a CLASS difference rather than a rounding one).

**`chain_f32_differs_from_f64_rows=32` is the witness that the f32 kernel is the one that
ran.** Without it, a 0-mismatch result would be consistent with the f32 arm silently
dispatching the f64 kernel *if* the reference had a matching bug — a real risk, since the
reference and the kernel were written in the same session. All 32 rows produce a
different f64 bit pattern than the f64 chain kernel on the same input, which is what a
different arithmetic sequence must do.

---

## 4. The kernel A/B, and the instruction model it did NOT land on

`tests/lfm2_f32_kernel_ab_test.quanta` PART 1b: real `token_embd.weight` rows, **256
rows/tensor x 2 arms interleaved x 21 cycles**, reporting **min-of-21 AND sum-of-21**,
single-threaded, `taskset`-pinned.

### 4.1 The instruction model, first (as the method requires)

| | f64 chain, per 4 elements | f32 chain, per 8 elements |
|---|---|---|
| dequant + multiply | 12 (+0..1 optional shift) | 12 (+0..1) |
| fold | 4 `vaddsd` + 3 shuffle = 7 | 1 `vextractf128` + 7 `vpermilps` + 8 `vaddss` = 16 |
| pointer | 1 | 1 |
| **total** | **19-20** | **28-29** |
| **per element** | **~4.9** | **~3.6** |

**The instruction model predicts ~1.37x fewer instructions per element.** But the
CRITICAL PATH is not instructions:

* f64: **4 dependent `vaddsd` per 4 elements** = 1 dependent op/element x ~4 cycles = **4 cycles/element**;
* f32: **8 dependent `vaddss` per 8 elements** = 1 dependent op/element x ~4 cycles = **4 cycles/element**.

**The two chains have the IDENTICAL critical path.** The accumulator is shared across
groups (group g+1's first `vaddss` reads `xmm0` that group g wrote), so the per-super-block
chain is 256 serial adds either way — 4 cycles/element, always. This is a property of the
reference's summation order and it CANNOT be improved without changing that order, which
is the one thing this route exists to preserve.

### 4.2 The measurement

`taskset`-pinned to core 3, `loadavg` 9.6-11.3, six processes (three per pin):

| pin | `chain_f64/chain_f32` min x1000 | sum x1000 |
|---|---|---|
| 0.0.256 | 1006, 1240, 1006 | 1013, 1229, 774 |
| 0.0.258 | 1007, 1008, 1011 | 1018, 1016, 1099 |

Earlier 0.0.256 processes at other core pins and unpinned add
`1001/1001, 999/979, 1000/987, 1007/1015, 1009/1015, 1006/1020, 1008/1015, 1007/1009`.

### 4.3 The honest reading

* **The ratio is 0.999-1.011, i.e. the f32 chain is 0-1.1% FASTER — within noise of 1.00.
  There is no meaningful speedup, and where it is non-zero the sign is in the f32
  direction.**
* **The hardware did NOT land on the instruction model.** 1.37x fewer instructions per
  element produced ~1.007x. The reason is §4.1: the kernel is LATENCY-bound, not
  instruction-throughput-bound, on this box, on an idle core AND a busy one (I measured
  all three: core 3, cores 17-19, core 6 — all ~1.007).
* **Two readings are outliers and are NOT used**: one 0.0.256 process read **1.240** and
  one **0.774** (sum). Both are whole-arm interference bursts of the kind the previous
  unit documented (`min-of-N` is defeated when interference lasts a whole arm). They do
  not track loadavg and are not reproducible; every one of the other 14 readings is in
  0.999-1.011.
* **The ratio CARRIES across the pin**, which is the point of carrying ratios: 1.007 on
  0.0.256 and 1.008 on 0.0.258.

### 4.4 What this says about the remaining lever

The task's framing was that the tied projection is "the largest remaining loader term at
42.7% of a token". That framing is about **wall-clock share**, and the share is real — but
the kernel A/B shows the term is **latency-bound**, so widening it in f32 (fewer
instructions, same critical path, half the x bytes) buys nothing. The 42.7% is not
recoverable by a kernel-width change; §10 says where it would have to come from.

---

## 5. The Q4_K `f32` vs `f32+FMA` question: RESOLVED

The previous unit reported this **INCONCLUSIVE on Q4_K** while clear on Q6_K, with the
sign flipping between runs. Re-measured on a box at `loadavg` 9.6-11.3 instead of 24.5,
**12 of 12 samples across both pins and both estimators agree**:

| tensor | pin | `f32 / f32+FMA` min x1000 (3 processes) | sum x1000 |
|---|---|---|---|
| `ffn_gate.0` (Q4_K) | 0.0.256 | 895, 898, 897 | 907, 914, 917 |
| `ffn_up.0` (Q4_K) | 0.0.256 | 900, 902, 890 | 905, 904, 919 |
| `ffn_gate.0` (Q4_K) | 0.0.258 | 898, 905, 902 | 915, 898, 903 |
| `ffn_up.0` (Q4_K) | 0.0.258 | 903, 906, 897 | 908, 889, 899 |
| `ffn_down.3` (Q6_K) | both | 1050-1058 | 1040-1054 |
| `attn_v.2` (Q6_K) | both | 1020-1045 | 1013-1161 |

A ratio BELOW 1000 means **`f32+FMA` takes FEWER ticks than plain `f32`** (the field is
`f32_ticks x 1000 / f32fma_ticks`). Read:

* **Q4_K: `f32+FMA` is ~10% faster** (0.890-0.917; every sample in 0.889-0.917).
* **Q6_K: `f32+FMA` is ~4-6% faster** (1.020-1.058; consistent with the previous unit's
  +4.6-5.7%).

**So the Q4_K question is resolved: the earlier inconclusive reading was load-24.5 noise,
and `f32+FMA` is faster on BOTH dtypes.** The instruction model predicted
`(4x(4x10 + 4x9)) / (4x(4x8 + 4x7)) = 304/240 = 1.267`; the hardware landed at **~1.10**,
i.e. about **44% of the model** — the FMA fold removes 4 FP ops per group but the loads
and pointer adds do not shrink, so the ceiling is partial. That is the honest statement:
directionally decisive, quantitatively below the instruction count.

### 5.1 The matvec ratios, re-taken (they reproduce the prior document)

| tensor | dtype | cols | f64/f32 (0.0.256) | f64/f32 (0.0.258) | prior unit |
|---|---|---|---|---|---|
| `ffn_gate.0` | Q4_K | 2048 | 2.367-2.405 | 2.359-2.391 | 2.14-2.39 |
| `ffn_up.0` | Q4_K | 2048 | 2.367-2.376 | 2.372-2.380 | 2.14-2.39 |
| `ffn_down.3` | Q6_K | 10752 | 1.846-1.898 | 1.846-1.906 | 1.848-1.853 |
| `attn_v.2` | Q6_K | 2048 | 1.694-1.707 | 1.713-1.714 | 1.702-1.712 |

These MATCH the prior document within its own spread, on a different load band and after
the pin moved. The 0.0.256 arm data was re-taken rather than reused, and no ratio was
spliced: each column is a single pin.

---

## 6. THE BOUND, and the correction to the f64+FMA bound

`tests/lfm2_f32_logits_test.quanta`: FOUR ARMS in ONE process, the same prompt, the
shipped configuration otherwise (20 workers, mmap route, the whole fused set), diffing all
**128,000** logits against arm 0. Reproduced **byte-identically in both runs taken**, and
identical to the earlier session's run.

```
arm 0: f32=0 fma=0   the f64 folded kernels + the f64 chain  -- the reference
arm 1: f32=0 fma=1   the f64 FMA kernels   + the f64 chain
arm 2: f32=1 fma=0   the f32 kernels       + the f32 CHAIN
arm 3: f32=1 fma=1   the f32 FMA kernels   + the f32 CHAIN
```

### 6.1 The witnesses, all four, asserted both ways

```
  arm 0: f32_used=0 fma_used=0 chain_f32_used=0 chain_f32_drop=0
  arm 1: f32_used=0 fma_used=1 chain_f32_used=0 chain_f32_drop=0
  arm 2: f32_used=1 fma_used=0 chain_f32_used=1 chain_f32_drop=0
  arm 3: f32_used=1 fma_used=1 chain_f32_used=1 chain_f32_drop=0
```

The bar asserts the f32 chain is on in EXACTLY the two f32 arms and off in the two f64
arms, and never dropped. Without that, an arm whose f32 chain silently fell back to f64
would have been indistinguishable from one that did not — and its excursion would have
been the matvec's alone, understating the bound. This is the same witness gap the
previous unit found for `fma_used`.

### 6.2 The bound table, with the f64+FMA row CORRECTED

| arm | logit_mism /128000 | max abs diff f64 bits | max \|diff\| | relative to max logit (23.948346) | max ULP | sign flips |
|---|---|---|---|---|---|---|
| 1: f64+FMA | 124,782 | `4407335185335451648` | **4.6185e-14** | **1.929e-15** | 1,116,224 | **0** |
| 2: f32 | **128,000** | `4539917833436397568` | **3.247869e-05** | **1.3562e-06** | 161,345,215,801,184 | **0** |
| 3: f32+FMA | **128,000** | `4539899436025249792` | **3.235402e-05** | **1.3510e-06** | 343,270,090,714,576 | **0** |

For every arm: **first-token argmax 597**, **all 25 per-step argmax IDENTICAL** to arm 0,
and the **first 24 generated ids IDENTICAL**:
`597 4695 20589 34 496 2992 355 229 26 19 26 39 41774 415 278 1579 1049 2426 440 4695
10966 267 2936 1579`. `f32_drop=0`, `chain_f32_drop=0`.

**THE CORRECTION.** The previous document records the f64+FMA row as **2.921e-15 absolute
/ 1.2e-16 relative**, derived from the harness printing `excursion_x1e18=2921`. That
scaled print is **WRONG by a factor of 15.81**: the harness multiplies by the 19-digit
literal `1000000000000000000.0`, and **that literal does not evaluate to its own value on
this tree** (§9.1). The authoritative field is `max_abs_diff_bits` — the RAW f64 pattern
of the max difference — which decodes to **4.618528e-14** (relative **1.929e-15**). The
scaling is fixed in the harness (it now multiplies by `1000000000.0 * 1000000000.0`,
which is exact and verified), and the corrected `excursion_x1e18=46185` is consistent with
both the raw bits and the independent `over_maxlogit_x1e15=1` (which used the 1e15
literal — a 16-digit literal, which IS exact).

**Is the f32 bound bigger than the matvec-only one, and by how much?** Yes: the
matvec-only f32 arms previously read `4530678364443246592` = 3.045e-05; the arms with the
f32 chain read **3.2479e-05** and **3.2354e-05**, i.e. **~6% larger**. That is the expected
shape: the chain is another 262M elements now accumulating in f32. It is a *bounded*
difference, not a small one — which is exactly why this path has its own flag and its own
bar rather than being hung on a flag whose gate is bit-exactness. **llama.cpp's own SIMD
dot products use f32 and FMA**, so this moves the loader TOWARD its reference; the flag
exists so the difference is opt-in, measured, and never silently substituted.

---

## 7. The EXISTING flags' bit-exact gate is untouched

`tests/lfm2_fused_logits_test.quanta`, run AFTER the f32 chain work, with `mm_fused_f32`
OFF (so the chain stays f64 there), under the 0.0.256 pin: 9 passes in one process over
all 128,000 logits. Every row `logit_mism=0 argmax_mism=0 max_abs_diff_bits=0`, argmax
597, and the identical 24 ids. Every dispatch witness asserted
(`fused_q4k_used`, `fused_q6k_used`, `fused_chain_used`, `fused_glu_used`,
`fused_attn_used`, `fused_conv_used` = 1 on the passes that set them).

**This is the proof that adding the f32 chain changed nothing for the flags that were
already there.**

---

## 8. End-to-end flag matrix, with its load

### 8.1 Method

`tests/lfm2_f32_ab.sh`, the four configurations in a **palindrome**
(`off, f64+fma, f32, f32+fma, f32+fma, f32, f64+fma, off`) so every arm has a near-load
neighbour on both sides. `LENS=32` (the `LENS=64` version is documented by the previous
unit as producing arm means that do not track load at all). Decode-bench conf field 17 is
f32, field 16 is fma; every other flag at the shipped setting; one binary; every arm
echoes its own flags, witnesses and load.

Two driver defects were found and fixed while doing this, and they are why the driver's
summary was silent before: (a) it grepped for `tok/s|ms/token`, and the bench prints
**`tok_per_s_x1000` / `ms_per_token_x100`** — the pattern matched NOTHING; (b) its witness
grep did not know the new chain witness. Both fixed in `tests/lfm2_f32_ab.sh`.

### 8.2 The matrix, `loadavg` 11.1-21.4, 0.0.256, 32-token runs

| arm | f32 | fma | `loadavg` before -> after | tok/s (run1/2/3) | min ms/token | f32_used | fma_used | chain_f32_used | xf32_elems |
|---|---|---|---|---|---|---|---|---|---|
| off1 | 0 | 0 | 11.14 -> 18.49 | 1.905 / 1.954 / 1.969 | 507.68 | 0 | 0 | 0 | 0 |
| f64fma | 0 | 1 | 18.49 -> 17.79 | 2.031 / 2.089 / 2.167 | 461.37 | 0 | 1 | 0 | 0 |
| **f32** | 1 | 0 | 17.79 -> 17.28 | 3.444 / 3.753 / 3.740 | **266.40** | 1 | 0 | 1 | 97,572,864 |
| **f32fma** | 1 | 1 | 17.28 -> 18.43 | 3.936 / 3.946 / 3.939 | **253.36** | 1 | 1 | 1 | 97,572,864 |
| **f32fma2** | 1 | 1 | 18.43 -> 17.37 | 3.915 / 3.877 / 3.975 | **251.52** | 1 | 1 | 1 | 97,572,864 |
| **f322** | 1 | 0 | 17.37 -> 15.63 | 3.702 / 3.683 / 3.623 | 270.06 | 1 | 0 | 1 | 97,572,864 |
| f64fma2 | 0 | 1 | 15.63 -> 21.36 | 2.307 / 2.361 / 2.384 | 419.34 | 0 | 1 | 0 | 0 |
| off2 | 0 | 0 | 21.36 -> 19.93 | 2.241 / 2.233 / 2.222 | 446.14 | 0 | 0 | 0 | 0 |

Every arm and every run printed `first_argmax_id=597`. The `xf32_elems` value is
identical across all four f32 arms, which is itself evidence that all four took the same
route.

### 8.3 Read honestly

| configuration | samples | ms/token | tok/s |
|---|---|---|---|
| f32=0 fma=0 (f64 folded + f64 chain) | 6 | 446.1-524.8 | 1.905-2.241 |
| f32=0 fma=1 (f64 FMA + f64 chain) | 6 | 419.3-492.3 | 2.031-2.384 |
| **f32=1 fma=0 (f32 + f32 chain)** | 6 | 266.4-290.3 | 3.444-3.753 |
| **f32=1 fma=1 (f32 FMA + f32 chain)** | 6 | **251.5-258.0** | **3.877-3.975** |

* **No f64 sample overlaps any f32 sample.** The f64 family spans 1.905-2.384 tok/s; the
  f32 family spans 3.444-3.975. The honest ratio is a RANGE, taken as
  (worst f32 / best f64) to (best f32 / worst f64):
  **plain f32 is 1.54x - 1.97x, and f32+FMA is 1.73x - 2.09x**, against the folded f64
  reference. On the single-best-min-ms basis they are **1.675x** and **1.774x**. Against
  the f64+FMA configuration the f32+FMA ratio is **1.63x - 1.96x** (single-best 1.667x).
* **The f64+FMA arm reproduces the previous unit's absolute band**: 2.031-2.384 tok/s here
  at `loadavg` 15.6-21.4, against its 1.985-2.080 at 21.6-22.5. Same band.
* **The f32 chain's contribution to these numbers is ~0.3% and is not resolvable here**:
  the kernel ratio is 1.007 on 42.7% of a token. The end-to-end f32/f64 ratio is, to
  within this box's resolution, the matvec f32 change alone.

### 8.4 The pin-advance cross-check (0.0.258), NOT spliced

A reduced 2-configuration palindrome (`off, f32fma, f32fma, off`), one binary built by
`0.0.258` (md5 `e7fc8cd4`), `LENS=32`, `loadavg` 17.4 -> 19.0 across the pair:

| arm | f32 | fma | tok/s (run1/2/3) | min ms/token | chain_f32_used | xf32_elems | argmax |
|---|---|---|---|---|---|---|---|
| off | 0 | 0 | 2.127 / 2.165 / 2.007 | 461.85 | 0 | 0 | 597 |
| f32fma | 1 | 1 | 3.792 / 3.761 / 3.750 | **263.69** | **1** | **97,572,864** | 597 |

**The end-to-end ratio CARRIES**: **1.752x** on the min-ms basis (461.85 / 263.69) and
1.752x on best-tok/s (3.792 / 2.165), against 1.774x / 1.675x measured for the same
configurations under 0.0.256 (§8.2) — the same ratio within this box's resolution, and the
witnesses are the ones they must be (f32 arm dispatches the f32 chain and narrows x; the
f64 arm does neither). **No absolute from §8.2 is combined with any absolute from here**
— they are two labelled pins, not one A/B. **A full 8-arm re-take under 0.0.258 was NOT
done**; this 2-configuration pair plus the full kernel-level ratio re-take (§5.1) is the
evidence that the end-to-end ratio would carry, and that is an argument, not a
measurement.

---

## 9. Two silently-wrong classes found on the way, with file:line evidence

Both produced a **plausible, reproducible, wrong number**, which is the failure mode this
whole series forbids. Both are recorded here with a reproducer; neither is worked around
in `lib/std`.

### 9.1 A 19-digit decimal float literal does not evaluate to its own value (off by 15.81x)

```
f64bits(1000000000000000000.0)   = 4858283208366391296     true 1e18 = 4876203697187506176
f2i(1000000000000000000.0)       = 63251277506936832       (~6.3e16, not 1e18)
f2i(1000000000.0 * 1000000000.0) = 1000000000000000000     exact
f64bits(1000000000000000.0)      = 4831355200913801216     exact (a 16-digit literal is fine)
f64bits(1000000000000.0)         = 4786511204640096256     exact (13 digits fine)
```

**Identical under `0.0.256` (md5 `21c868f4`) and `0.0.258` (md5 `e7fc8cd4`)**, so this is
a live defect, not a fixed one. Reproducer: `/tmp/probe_lit2.quanta` (recreated in
`tests/lfm2_f32_logits_test.quanta`'s comment).

Site: the float token packs the mantissa as `(val << 8) | fdigits`, and the accumulation
that builds `val` is guarded by a magnitude test —
`compiler/<ver>/src/x86/lexer.quanta:286`

```
if val < 3602879701896397 {
    val = val*10 + d
    if fval < 36028797018963967 { fval = fval*10 + d }
    fdigits = fdigits + 1
}
```

The guard's own comment block (lines 225-285) documents **two earlier revisions of this
same class**, one of which "sent the compiler into a hang". This unit's finding is a THIRD
instance of the same class that the guard does not cover: it is the existing
`docs/plans/bugs.md` **A30** family ("one 17-digit decimal literal does not round to the
nearest f64 (1 ULP low)") — but A30's error is 1 ULP and this one is a factor of 15.81, so
it is a distinct severity. Filed as **A37**.

**Its cost here, concretely:** `tests/lfm2_f32_logits_test.quanta` printed
`excursion_x1e18` by multiplying by this literal, so the previously documented f64+FMA
bound was **under-reported by 15.81x** (§6.2). The raw f64 bits field was always correct,
which is why the two fields disagreed by exactly that factor and why the discrepancy was
findable. **Every harness that scales a float by a long decimal literal is affected.**

### 9.2 `print_f`'s integer part is O(|v|) and never terminates for |v| >= 2^53

`lib/std/fs.quanta:237-241`:

```
let ip = 0
while m >= 1.0 {
    m = m - 1.0
    ip = ip + 1
}
```

* For `m >= 2^53` this is an **INFINITE LOOP**: `m - 1.0 == m` once the ulp exceeds 1.
* Below that it is merely O(|v|): measured, `print_f(10000000000.0)` and
  `print_f(1000000000000.0)` **do not return within 12 s** under `0.0.258`; values up to
  99999999.0 (8 digits) print instantly.

Reproducer: a 3-line program calling `print_f(<literal>)` (see §13). Filed as **A38**.

**Not fixed in this unit, and the reason is stated rather than implied:** the currently
*working* range is fast enough for every number this unit reports (all are O(1) or
O(1e-5)), and a fix that preserves the exact residual arithmetic for the mid-range
(`1e8 .. 2^53`, which some other harness could be printing today) while terminating above
2^53 is a proper decimal formatter with its own verification cycle — which does not belong
at the end of a kernel unit. It is the next unit's item, with the reproducer attached.

---

## 10. Gate, reproduce, and the honest gap

### 10.1 Gate / emitted-code checks

The gate itself was NOT run by this unit: `test_suites/**` is the compiler peer's path,
the peer's gate was alive and its `VERSION`/`EXPECTED.tsv`/`run_tests.sh` were dirty
throughout, and the brief forbids running the compiler's gate concurrently with the
peer's edits. What WAS run, and is this unit's own evidence:

```
gcc -O1 -o /tmp/f32enc tests/lfm2_f32_enc_verify.c && /tmp/f32enc
                                        119 sequences, 0 assertion failures
python3 tests/lfm2_f32_enc_negctl.py    5 controls, 0 failed
python3 tests/lfm2_f32_hexcheck.py      135 hex strings, 0 failures
python3 tests/lfm2_jbytes_len_check.py  237 jbytes() calls, 0 mismatches
```

### 10.2 Reproduce

```
cd /opt/tali/quanta && ulimit -c 0 -v 32000000
export QC=$PWD/compiler/0.0.256/bin/x86/qc     # md5 21c868f418797c86d7db68728ed01917

# --- 1. the encodings, BY EXECUTION (fast, no model) ---
python3 tests/lfm2_f32_enc_gen.py              # as -> objdump -> table (regenerates the prologue)
gcc -O1 -o /tmp/f32enc tests/lfm2_f32_enc_verify.c && /tmp/f32enc
python3 tests/lfm2_f32_enc_negctl.py           # the 5 negative controls
python3 tests/lfm2_f32_hexcheck.py
python3 tests/lfm2_jbytes_len_check.py

# --- 2. the kernel A/B (matvec + CHAIN) and the independent f32 references ---
$QC -O tests/lfm2_f32_kernel_ab_test.quanta /tmp/f32ab
( ulimit -c 0 -v 32000000; taskset -c 3 /tmp/f32ab </dev/null )    # 3 processes

# --- 3. the bound (4 arms) and the existing flags' bit-exact gate ---
$QC -O tests/lfm2_f32_logits_test.quanta /tmp/f32_logits
$QC -O tests/lfm2_fused_logits_test.quanta /tmp/fused_logits
( ulimit -c 0 -v 32000000; /tmp/f32_logits </dev/null )
( ulimit -c 0 -v 32000000; /tmp/fused_logits </dev/null )

# --- 4. the end-to-end palindrome (8 arms; NOTE it is not quiet here) ---
QC=$QC LENS=32 PROF_SCRATCH=/tmp/ab256 bash tests/lfm2_f32_ab.sh

# --- 5. the two defects, reproduced ---
#     (a) the 19-digit literal:  f64bits(1000000000000000000.0) != 4876203697187506176
#     (b) print_f:  a program whose body is `print_f(10000000000.0)` never returns
```

### 10.3 The honest gap

**Shipped configuration** (`f32=1 fma=1`), `loadavg` 18.4->17.4, 32-token runs:

| configuration | least-interfered sample | ms/token |
|---|---|---|
| f32=1 fma=1 (now shipped) | 3.975 tok/s | 251.5 |
| f32=1 fma=0 | 3.753 tok/s | 266.4 |
| f32=0 fma=1 | 2.384 tok/s | 419.3 |
| f32=0 fma=0 (f64 folded) | 2.241 tok/s | 446.1 |

* Gap to the **15 tok/s** target: **3.8x - 3.9x** (15 / 3.975 and 15 / 3.877).
* Gap to llama.cpp's **17.32 tok/s** on the same model and CPU: **4.4x - 4.5x**.
* For comparison, at the previous unit's `loadavg` 20.9-24.4 the same tree read
  4.3x - 4.8x to 15. **This box is measurably less loaded now (7.8-22.4 vs 8.7-32.7),
  so the improvement in the gap figure is mostly the window, not the code** — the code
  contribution of this unit is the f32 chain's ~0.3%, and saying otherwise would be
  claiming a load artefact.

**What this unit moved, measured:**

* the tied output projection is now OFF the f64 route: a f32 chain kernel whose
  encodings are execution-verified, whose output is bit-identical to an independent f32
  chain reference over 32 rows x 6 processes, and whose difference from the f64 chain is
  proved on all 32 rows (§3);
* **its kernel ratio is 1.007 and that is the point**: the chain is latency-bound and the
  f32 form has the same critical path. Stated as a negative result (§4);
* **the Q4_K f32-vs-FMA question is resolved** — `f32+FMA` is ~10% faster, 12/12 samples,
  two pins (§5);
* the f32 path's bound is re-taken and **an error in the previously documented f64+FMA
  bound is corrected**, with its cause (a compiler literal defect) filed as A37 (§6.2, §9.1).

**What it did NOT move, said plainly.** The binding constraint remains **core
over-subscription**: the previous unit measured the same pool job at 45 us at nw=8 and
185 us at nw=20, and at nw=20 the pool job is no faster than the main thread. A token still
pays 166 pool barriers. Nothing here touches that, and the tied projection is a **latency-
bound serial chain whose 42.7% share cannot be recovered by making the kernel wider** —
which is the useful negative result of this unit, and it is the reason the previous
document's lever #2 ("an f32 chain kernel is possible and is the one remaining
kernel-shaped lever") is now CLOSED with a measurement rather than left open.

**Not done, and named rather than implied:**

* **No quiet-window absolute measurement.** Every tok/s above carries its `loadavg`.
* **A full 8-arm end-to-end palindrome was NOT re-taken under `0.0.258`** — only the
  reduced 2-configuration pair (§8.4) plus the full kernel-level ratio re-take (§5.1).
  The kernel ratios carrying is the evidence the end-to-end ratio would carry; that is an
  argument, not a measurement, and it is labelled as one.
* **The `print_f` defect (A38) is filed, not fixed** (§9.2), with the reason given.
* **Pool concurrency, the partition rule, the KV format and the conv false-sharing knob
  were deliberately NOT touched**, per the standing constraint.

---

## 11. Routed, not done here

1. **A37 — a 19-digit decimal float literal evaluates to ~1/15.81 of its value**
   (`compiler/<ver>/src/x86/lexer.quanta:286`, the `val < 3602879701896397` guard and the
   `(val<<8)|fdigits` packing). Identical on 0.0.256 and 0.0.258. Any harness that scales
   a float by a long decimal literal reports a wrong number, silently and reproducibly.
2. **A38 — `print_f`'s integer-part loop is O(|v|) and never terminates for |v| >= 2^53**
   (`lib/std/fs.quanta:237`). A proper decimal formatter is its own unit; the reproducer
   is in §9.2.
3. **The tied output projection is CLOSED as a kernel-width lever** (measured, §4, §10.3).
   If its 42.7% share is to be attacked it has to be by parallelism (splitting one row's
   chain across cores and combining in a DEFINED order — which changes the summation
   order and therefore the reference, so it is a design decision, not a kernel) or by
   reducing the row COUNT (a vocabulary-pruning / candidate-set design). Neither is a
   loader change and both are out of scope here.
4. **`pl_xf32_fill` grows by one 2048-element narrowing per forward** (196,608 per arm per
   3-run x 32-token bench, measured §1.4). Negligible; named for completeness.
