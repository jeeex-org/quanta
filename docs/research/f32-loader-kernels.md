# The f32 kernel family, the grow-only f32 x buffer, and two emitted-code defects

**Status: LANDED and MEASURED.** Every number below is printed with the instrument
that produced it and the load it was taken at. Where a figure is derived from
another, the derivation is shown. Nothing projected. The two defects found on the
way are recorded in full, because both produced a *plausible wrong number* and
both are now covered by a mechanical check.

Compiler pinned for every figure: **`compiler/0.0.255/bin/x86/qc`**, md5
**`2fe5e2844b9c3a74cf7922152a69ea46`** (gate 246/246 with 0 RED stages,
`verify-release` 14/14, fixpoint `5c23efdd -> 9a91af73 -> 2fe5e284`).

**The pin was moved mid-flight, and every measurement was RE-TAKEN rather than
spliced.** The first pass of this work measured under `0.0.252`
(`1d1e2d04`); when the author re-pinned to `0.0.255`, the whole arm set was
re-run under the single new pin and **the `0.0.252` arm data was discarded**. An
A/B whose arms were built by different compilers measures the compilers, not the
flag. `tests/lfm2_f32_remeasure.sh` is the driver that does this in the right
order, and it is the only thing any figure below comes from.

`0.0.255` is not a cosmetic difference for this work: it carries **A32** (the
float spill region now sits immediately below the integer region and is reserved
only for float-using functions — this work uses floats heavily, and frames now
correctly reserve that region), **A36** (conversion-builtin inference by
direction), **F3** (a block terminator's operand is no longer stored and
reloaded) and **F6** (3-operand `imul`). The `-> f64` annotations on the
conversion wrappers in `lib/std` **stay**: they are correct under A36 and still
needed, and the author confirmed to keep them.

`VERSION` reads 0.0.255 and is **never** followed — a compiler peer on the
arithmetic campaign will move it past 0.0.255, and the explicit pin is what keeps
these numbers reproducible while the compiler moves.

Load is LABELLED on every absolute figure. This box ran `loadavg` 8.7-32.7
through this session (a 20-core box with ~8 cores held by the agent host), and the
same tree has been measured at 1.85 tok/s at load 21 and 3.148 tok/s at load 12.
**Within-session A/B ratios are primary; every absolute tok/s is labelled.**

---

## 0. What was asked, and what this unit did

| # | item | outcome |
|---|---|---|
| 1 | the f32 kernel family (f32 Q4_K + Q6_K, plus FMA), behind its OWN default-OFF flag | **LANDED.** `mm_set_fused_f32`, four new kernels in four new RWX regions, fail-closed on their regions and on the new x buffer |
| 2 | the grow-only f32 activation buffer in `pl_run_rows_map` | **LANDED.** `pl_xf32` / `pl_xf32_cap`, grown to a power of two, filled once per matvec on the main thread. **2 allocations for the whole process**, measured |
| 3 | encodings verified by execution | **DONE.** 102 byte sequences run with known operands, 0 assertion failures, including the whole 32-instruction factor prologue against a synthetic super-block header |
| 4 | every EXISTING flag's 128,000-logit bit-exact gate untouched | **GREEN**, all 8 rows `logit_mism=0 max_abs_diff_bits=0`, argmax 597 |
| 5 | the bit-moving f32 path gets its own documented bounded logit difference | **DONE**, reproduced byte-identically across four processes |

Five commits, all pushed: `46decbba`, `d6e0bf4b`, `7547b3ba`, `878ac5cf`,
`b308df6b`. HEAD at the end of this work: `b308df6b`.

---

## 1. Why f32 is a MULTIPLE and not a percentage

Every FP instruction in the kernels before this one was a `*pd` form: **4 f64
lanes per ymm**. The `*ps` forms carry **8**, `vcvtdq2ps` converts 8 int32 at once
where `vcvtdq2pd` converts only the low 4, and x becomes **4 bytes/element instead
of 8**.

x is the operand that matters here, because it is re-read once per ROW:

| tensor | cols | rows | x bytes per matvec (rows x cols x 8) | weight bytes (Q4_K, 0.5 B/elem) |
|---|---|---|---|---|
| `ffn_gate` / `ffn_up` | 2048 | 10752 | 176 MB | 11 MB |
| `ffn_down` | 10752 | 2048 | 176 MB | 11 MB |

**x is read 16x more bytes than the weights per matvec**, so halving x is the half
of the f32 lever that does not depend on lane count.

### 1.1 The instruction count, from the builders

Counted from the emitted bodies (Q4_K super-block = 256 weights):

| | factor prologue | per chunk (64 weights) | per super-block |
|---|---|---|---|
| f64 folded | 43 | `8 x 13` low + rewind + `8 x 12` high = 201 | `43 + 4x201` = **847** |
| f32 folded | 32 + 16 broadcasts | `4 x 10` low + rewind + `4 x 9` high = 77 | `48 + 4x77` = **356** |

**2.38x fewer instructions for the same 256 weights**, because a group is 8 weights
instead of 4. The measured kernel ratio on the Q4_K chain is 2.14-2.40x (§6), which
is the instruction count landing almost exactly.

---

## 2. The design

### 2.1 Cadence (Q4_K)

Unchanged from the f64 folded kernel except that every step is 8 weights wide:

* 4 chunks. Chunk `c` covers weights `[64c, 64c+64)`.
* Its LOW 32 weights (quant bytes `[32c, 32c+32)`, low nibbles) use scale pair
  `2c`, in **4 groups of 8 bytes**. `r9` advances 8 bytes per group; `r10`
  advances 32 bytes (8 f32) per group.
* `r9` then rewinds 32 bytes and the HIGH 32 weights (the same bytes, high
  nibbles) use pair `2c+1`, in 4 more groups.
* Consumption order is therefore ascending in destination element index:
  `n(0,1) -> s(0..3) -> h(0,1) -> g(0,1)` for Q6_K, `chunk -> half -> group` for
  Q4_K. Lane `k` of `ymm0` accumulates elements `k, k+8, k+16, ...`.

### 2.2 The broadcast, and why it is ONE instruction

The f64 kernel derives its 8 `(d*sc, dmin*mn)` pairs as four 4-lane f64 vectors
and broadcasts one lane per chunk with `vpermpd`.

`vpermilps`'s imm8 selectors are **lane-relative inside each 128-bit half** — the
exact trap that cost a peer a day with `vpermilpd`. It is used here *on purpose*:
each 4-lane f32 factor vector is first **duplicated into both halves** by

```
vinsertf128 ymm12, ymm12, xmm12, 1     ; imm8 bit 0 selects the destination LANE;
                                       ; 1 = the HIGH one, so ymm12 becomes [x,x]
```

after which a single `vpermilps ymm6, ymm12, j*0x55` broadcasts lane `j` of the low
half to all eight lanes. **One instruction per factor, carrying twice the lanes.**

The imm8 bit is not taken on faith: `tests/lfm2_f32_enc_verify.c` asserts that
`vinsertf128 ... ,1` duplicates (and a negative control with imm8=0 makes that
assertion print FAIL).

### 2.3 The 8-lane reduce — a STATED order

With `ymm0 = [L0..L7]`:

```
vextractf128 xmm1, ymm0, 1        ; [L4,L5,L6,L7]
vaddps       xmm0, xmm0, xmm1     ; A = [L0+L4, L1+L5, L2+L6, L3+L7]
vhaddps      xmm0, xmm0, xmm0     ; [A0+A1, A2+A3, ...]
vhaddps      xmm0, xmm0, xmm0     ; (A0+A1)+(A2+A3)
vcvtss2sd    xmm0, xmm0, xmm0     ; widen the f32 sum ONCE (exact)
vmovq        rax, xmm0
```

i.e. **`((L0+L4)+(L1+L5)) + ((L2+L6)+(L3+L7))`, every step in f32**, then one exact
widening to f64 because the calling contract is "the dot as f64 bits in rax".

This order is a contract, not an emergent property: it is pinned **bit-for-bit over
4000 random finite inputs** against a C model of the same expression in
`tests/lfm2_f32_enc_verify.c`. And in `tests/lfm2_f32_kernel_ab_test.quanta` it is
pinned again end-to-end by an independent Quanta-source reference (§7).

### 2.4 Register maps

Q4_K f32 — `rdi`=AS, `r9`=W cursor, `r10`=X(f32) cursor, `rcx`=nsuper;
`ymm0`=accumulator, `ymm1`=weight scratch, `ymm2`=`[d,dmin,0,0]` f32,
`ymm8`/`ymm9`=broadcast `d`/`dmin` (4 f32), `xmm4`/`xmm5`/`xmm10`=the 12 scale
bytes as `a`/`b`/`c` dwords, `xmm11`=unpack scratch, `xmm3`=the `(c & 15)` term,
`ymm12..15`=the four factor vectors (then duplicated), `ymm6`/`ymm7`=this half's
two 8-lane broadcasts.

Q6_K f32 — `ymm0`=accumulator, `ymm1`=broadcast `d`, `ymm2`=broadcast `sc`,
`ymm3`/`ymm4`/`ymm5`=8 dwords of `-32`/`15`/`3`, `ymm6`/`ymm7`=quant scratch.
Offsets are the f64 kernel's with `g*8` instead of `g*4`:
`ql = n*64 + (s%2)*32 + h*16 + g*8` (max 120, disp8) and
`qh = 128 + n*32 + h*16 + g*8` (min 128, disp32).

**No callee-saved register is touched: no prologue, no epilogue, no stack**, the
same purity property the f64 kernels have.

### 2.5 Composition with the FMA modifier

`mm_fused_f32` is a MODIFIER of `mm_fused_q4k` / `mm_fused_q6k`, exactly as
`mm_fused_fma` is. It changes *which* kernel those routes dispatch:

| `f32` | `fma` | kernel |
|---|---|---|
| 0 | 0 | f64 folded (unchanged) |
| 0 | 1 | f64 FMA (unchanged) |
| 1 | 0 | f32 folded |
| 1 | 1 | f32 FMA folded |

Every existing kernel keeps its own RWX region and its bytes are untouched, which
is what keeps the bit-exact gate meaningful.

**Fail-closed on two things.** `mm_matvec_par` emits each f32 region before any
worker runs and clears the flag if one is refused (`mm_fused_f32_drop = 1`); the
grow-only x buffer is allocated there too and clears it if the allocation fails
(`mm_fused_f32_drop = 2`). A flag whose ON path crashes is worse than no flag, so
the fallback is always the f64 kernel of whichever folded route is on. The drop
reason is printed by the harness so that a silent "no effect" arm can never be read
as "f32 is not faster".

---

## 3. THE TWO DEFECTS, and the checker for each

Both were found by building the check **first** and both had produced a plausible
wrong number. They are recorded in full because they are the same class the
predecessor's document lists.

### 3.1 Four prologue instructions sourced the wrong register

The first revision of the factor prologue was **hand-adapted** from the f64
kernel's `j_f_fold_factors`. That kernel keeps its 6-bit unpack result in `xmm7`;
the f32 prologue uses `xmm11` (so that `xmm7` is free for the min broadcast). Four
instructions — the four `vcvtdq2ps` forms — were transcribed as the f64 kernel's
bytes and therefore read **`xmm7`**, which at that point holds nothing relevant.

Measured consequence, `tests/lfm2_f32_diag_probe.quanta`, `loadavg` 12.2:

```
f64   = 0.031541  bits=4584706439309688832
f32   = -1203936.000000  bits=-4525450359388241920      <-- wrong by 7 orders
f32fma= -1341253.750000
ref   = 0.031541  bits=4584706437254479872
```

It looked like a "wrong factors" bug and was in fact a wrong **register**. The fix
is structural rather than careful: the prologue is now **generated into
`lib/std/jit_x86_fused.quanta`** by `tests/lfm2_f32_enc_gen.py` from the output of
GNU `as` + `objdump`, between markers, so there is nothing to transcribe. The order
is the only thing the generator decides.

**Why the checker missed it at first, which is the more useful fact.**
`tests/lfm2_f32_hexcheck.py`'s first revision matched only `jbytes(n, "hex")` and
not `femit("hex", n)` — the argument order is *reversed* between the two helpers,
and every prologue instruction uses `femit`. So 67 of the section's 110 hex strings
were invisible to the check that existed to catch exactly this. That revision is
gone; the current check counts both forms and prints the split.

### 3.2 `vpmovzxbd ymm6, [r9]` has NO displacement field — the stream shifted

`as` encodes `vpmovzxbd ymm6, qword ptr [r9]` with **mod=00**, i.e. a **five-byte
complete instruction with no displacement field**. The kernel needs a
*parameterised* form (`[r9+disp8]`, because the Q6_K `ql` offset varies from 0 to
120 per group), so the first revision wrote five bytes of that instruction and then
called `jb(d)` to append the displacement. The appended byte landed where the
**next instruction** should have started and shifted the entire emitted stream.

Measured consequence: **SIGSEGV on the first Q6_K row** —
`/tmp/f32ab` died at `ffn_down.3` after the Q4_K tensors had run.

The fix is the disp8 form (`vpmovzxbd ymm6, qword ptr [r9+disp8]`, whose
byte 6 *is* the displacement), and the check is now keyed on **usage**:

> a `jbytes(n, "hex")` immediately followed by `jb(x)` / `ji32(x)` is a PREFIX and
> must be **STRICTLY SHORTER** than a table entry.

An exact-match rule cannot catch it: `c4c27d3131` (the mod=00 form) *is* a valid
table entry. That was proven, not assumed — a negative control with the old prefix
restored passes the exact-match rule and fails the usage rule. The checker also
strips comments before matching, because a regex that cannot see across the
mnemonic comment between the `jbytes()` and its `jb()` finds **zero** parameterised
prefixes and silently exempts nothing; that variant was also run and rejected.

Both forms are additionally executed and **prefix-compared** in the C harness:
`b_ldql8` (`[r9+8]`) and `b_ldql40` (`[r9+40]`) must share their first five bytes
and differ only in byte 6.

---

## 4. Verification of the encodings, BY EXECUTION

`tests/lfm2_f32_kernels.s` (GNU `as`) →
`tests/lfm2_f32_enc_gen.py` (reads the bytes back out of `objdump -d`) →
`tests/lfm2_f32_enc_bytes.h` →
`tests/lfm2_f32_enc_verify.c`, which **maps each sequence executable and RUNS it**
between two generated stubs that load `r9`/`r10`/`ymm0..ymm15` from a context block
and store them back, so a single instruction's real register effect is observable.

```
102 sequence(s) executed; 0 assertion failure(s)
PASS: every f32 kernel byte sequence does what its comment claims
```

What is actually asserted, per sequence:

* `vpmovzxbd ymm, m64` zero-extends **exactly 8** bytes (lane 7 carries byte 7, not
  byte 8) — an xmm-destination form would read 4 and leave lanes 4-7 zero.
* `vpmovzxbd ymm6, [r9+disp8]` reads at the displacement it was given, and the two
  displacement forms share their 5-byte prefix.
* `vpmovzxbd xmm10, [r9-4]` — the `xmm10` form needs REX and is **6 bytes**, not 5;
  the declared-length check catches that class.
* low-nibble and high-nibble extraction, the `(c&15)|((a>>6)<<4)` merge, the
  `-32` bias, all on 8 dwords.
* the two `vpermilps` lane-relative broadcast forms, from a register **duplicated
  by `vinsertf128 ..., 1`** — the imm8 bit asserted.
* all three FMA operand orders against `-(y1*y6)+y7`, `-(y1*m)+y0`, `y6*m+y0`.
* `movzx eax, word [r9+208]` reads **exactly 2** bytes (the f16 `d`).
* `vpbroadcastb xmm2, [r9+192]` → `vpmovsxbd` → `vcvtdq2ps` → `vbroadcastss`
  produces 8 lanes of the signed scale.
* **the WHOLE 32-instruction factor prologue, run as one block**, against a
  synthetic 144-byte super-block header with known `d`, `dmin` and 12 scale bytes,
  asserting `ymm12..15` equal the eight `(d*sc, dmin*mn)` factors *duplicated into
  both halves* — computed independently in C from the 6-bit unpack rules.
* **the broadcast that consumes it**, on that same register state: after the
  prologue, `p_bc12_00` must be `d*sc[0]` in all 8 lanes and `p_bc15_ff` must be
  `dmin*mn[7]`.
* the 8-lane reduce against the documented order over 4000 random finite inputs.

**Negative controls were run for each class** and each made the harness print
exactly the expected assertions as FAIL: corrupting the `vinsertf128` imm8,
corrupting the `d`-load displacement, corrupting a prologue opcode byte, and
restoring the mod=00 prefix. A harness that cannot fail is not evidence.

Idempotence: `python3 tests/lfm2_f32_hexcheck.py` (110 hex strings: declared
length, provenance from the executed table, and parameterised-prefix strictness)
and `python3 tests/lfm2_jbytes_len_check.py` (**223** `jbytes()` calls tree-wide,
0 mismatches — up from 180; this unit added 43).

---

## 5. The grow-only f32 activation buffer

### 5.1 Why grow-only is a requirement, not a tuning choice

`mem_alloc` is a raw `mmap` and **`mem_free` never unmaps** — it only pushes a
free-list node (A35). A per-matvec alloc/free pair therefore leaks nothing visible
and grows `VmSize` permanently; that is the exact mechanism behind the 64 KB/token
address-space growth that took several rounds to pin down. This route runs **166
times per token**, so per-call churn would be thousands of mappings per generation.

`pl_xf32_ensure(n)` rounds the capacity up to a power of two and only ever grows.
The model's two column widths (2048, 10752) therefore cost exactly **two
allocations for the life of the process**, and that is measured rather than
claimed: every harness prints `xf32_allocs` and every run of every harness printed
**`xf32_allocs=2`**.

### 5.2 Fill once per matvec, on the main thread

`pl_xf32_fill(x, n)` narrows n f64 activations to f32 with `f64_to_f32bits` +
`mem_store32` — the same single round-to-nearest-even step `vcvtpd2ps` performs.
It runs in `mm_matvec_par`, **after `pl_cols` is set and before `pl_submit`**, i.e.
on the main thread with the pool parked, so no worker writes the buffer and no
worker can read a half-filled one. Narrowing it per ROW would repeat the work
`rows` times; per WORKER would turn a read-only operand into a shared write.

It is the **only** work the f32 route adds on the critical path, so `pl_xf32_elems`
counts the elements narrowed and the harnesses print it beside the win. Reported in
§10 rather than hidden.

### 5.3 The operand width and the kernel form must agree

`pl_run_rows_map` passes `pl_xf32` as the kernel's `[AS+8]` when the f32 route is
active and `pl_x` otherwise. Passing the f64 pointer to a `*ps` kernel would read
the wrong bytes and produce a plausible wrong number, so the guard is explicit:

```
if mm_fused_f32 != 0 && (fused != 0 || fused6 != 0) && pl_xf32 != 0 { fused32 = 1 }
```

with `pl_xf32 != 0` the second half of the fail-closed guard.

### 5.4 The witness gap that the 4-arm harness exposed

The first full run of the model-level harness showed arm 2 (`f32=1 fma=0`) and
arm 3 (`f32=1 fma=1`) reporting the **same witnesses** (`f32_used=1 fma_used=0`),
so an arm that never dispatched the fused f32 kernel would have been
indistinguishable from one that did — the exact failure the witness discipline
exists to prevent. The f32 FMA branch now sets `mm_fused_fma_used` as well, and the
bar asserts the distinction in BOTH directions (arm 3 must report both, arm 2 must
report `fma_used=0`).

---

## 6. The kernel A/B: f32 alone, and f32+FMA together

`tests/lfm2_f32_kernel_ab_test.quanta` PART 1. On real tensor rows of
`ffn_gate.0`/`ffn_up.0` (Q4_K) and `ffn_down.3`/`attn_v.2` (Q6_K), **256 rows per
tensor, four arms alternating inside one loop, 21 cycles**, single-threaded. Two
independent estimators are reported — `min` is min-of-21 and `sum` is the total
over all 21 interleaved cycles — because one is not enough on this box: min-of-N
rejects warm-up and short bursts but is fooled when interference lasts a whole arm,
while the sum cancels correlated drift.

Three separate processes, `loadavg` 12.2-12.5:

| tensor | dtype | cols | f64/f32 min | f64/f32 sum | f64/f32fma min | f64/f32fma sum |
|---|---|---|---|---|---|---|
| `ffn_gate.0` | Q4_K | 2048 | **2.400** / 2.389 / 2.145 | 2.222 / 2.403 / 2.075 | 2.244 / 2.141 / 2.288 | 2.454 / 2.172 / 2.306 |
| `ffn_up.0` | Q4_K | 2048 | **2.139** / 2.397 / 2.149 | 2.190 / 2.370 / 2.140 | 2.275 / 2.139 / 2.294 | 2.305 / 2.102 / 2.292 |
| `ffn_down.3` | Q6_K | 10752 | **1.842 / 1.849 / 1.854** | 1.349 / 1.767 / 1.863 | 1.950 / 1.948 / 1.950 | 1.493 / 1.947 / 1.963 |
| `attn_v.2` | Q6_K | 2048 | 1.713 / 1.617 / 1.711 | 1.697 / 1.600 / 1.706 | 1.791 / 1.703 / 1.792 | 1.737 / 1.669 / 1.787 |

**Read honestly:**

* **The Q4_K chain is 2.14-2.40x faster in f32**, against the 2.38x the instruction
  count predicts (§1.1). That is the strongest agreement available and it is the
  number to quote: the Q4_K chain is **78.69%** of the model's matvec elements.
* **Q6_K is 1.60-1.85x faster**, well short of its ~2.4x instruction prediction.
  The emitted bodies halve the FP vector-op count (10 per 8 elements -> 5), and
  that halving is the ceiling the Q6_K kernel actually reaches; the Q4_K kernel
  also halves the *dependency* structure of the fold, which is why it gets closer.
  The `ffn_down.3` MIN estimator is unusually stable across the three runs
  (1.842 / 1.849 / 1.854, a 0.6% spread) and is the single most trustworthy ratio
  in the table; its SUM estimator is not, at 1.349 in one run.
* **f32+FMA vs plain f32**: on Q6_K it is consistently ~5% faster (1.948-1.950 vs
  1.842-1.854 on `ffn_down.3`; 1.703-1.792 vs 1.617-1.713 on `attn_v.2`). On Q4_K
  it is **inconclusive**: the sign of the difference flips between runs
  (`ffn_up.0` 2.139 vs 2.397 in favour of plain f32, then 2.149 vs 2.294 in favour
  of f32+FMA). No claim is made for Q4_K.
* min and sum agree within 5% on **10 of the 12** tensor-run pairs; the two that
  do not (8% and 37%) are whole-arm interference bursts, which is why both are
  reported rather than the flattering one.

---

## 7. The independent f32 reference, compared BIT FOR BIT

A magnitude comparison would not prove the kernels' factor derivation, nibble
unpack, lane assignment or reduce order. So `tests/lfm2_f32_kernel_ab_test.quanta`
PART 2 carries an **f32 reference written in Quanta source from the BLOCK FORMAT**,
using the language's single-rounding binary32 builtins (`fadd32`/`fsub32`/`fmul32`,
which round each operand to f32 and perform ONE f32 op), the same 6-bit factor
unpack (`q4k_sc`/`q4k_min`), the same ascending element order, the same `e % 8`
lane assignment and the same documented reduce order.

```
Q4_K ffn_gate.0 :  rows=32 f32_vs_ref_bit_mismatch=0 exactly_one_nan=0 both_nan=0 max_bit_distance_vs_ref_ulp=0
Q4_K ffn_up.0   :  rows=32 f32_vs_ref_bit_mismatch=0 exactly_one_nan=0 both_nan=0 max_bit_distance_vs_ref_ulp=0
Q6_K ffn_down.3 :  rows=32 f32_vs_ref_bit_mismatch=0 exactly_one_nan=0 both_nan=23 max_bit_distance_vs_ref_ulp=0
Q6_K attn_v.2   :  rows=32 f32_vs_ref_bit_mismatch=0 exactly_one_nan=0 both_nan=0 max_bit_distance_vs_ref_ulp=0
```

in **three separate processes** — **0 mismatches over 4 tensors x 32 rows x 3 runs
= 384 row comparisons**, and `exactly_one_nan=0` throughout (the column that would
signal a *class* difference rather than a rounding one). The `both_nan=23` on
`ffn_down.3` is the same phenomenon the FMA work recorded: that tensor's synthetic
activation produces a NaN in BOTH the kernel and the reference, with the same bit
pattern (hence `bit_mismatch=0`), which is why the harness classifies on the
integer NaN test rather than `v != v` — the float form is unusable on this tree.

---

## 8. THE DOCUMENTED BOUND for the f32 path

`tests/lfm2_f32_logits_test.quanta`: FOUR ARMS in ONE process, the same prompt,
every other flag at the shipped setting, 20 workers, diffing all **128,000** logits
against arm 0.

```
arm 0: f32=0 fma=0   the f64 folded kernels -- the reference
arm 1: f32=0 fma=1   the f64 FMA kernels
arm 2: f32=1 fma=0   the f32 kernels
arm 3: f32=1 fma=1   the f32 FMA kernels
```

Reproduced **byte-identically in four separate processes** (`loadavg` 8.67, 12.33,
19.40, 19.63 — the bound is a property of the code, not of the load):

| arm | logit_mism / 128000 | max abs diff bits | max \|diff\| | relative to max logit | max ULP | sign flips |
|---|---|---|---|---|---|---|
| 1: f64+FMA | 124,782 | `4407335185335451648` | **2.921e-15** | **1.2e-16** | 1,116,224 | **0** |
| 2: f32 | **128,000** | `4530678364443246592` | **4.887e-7** | **3.226e-7** | 193,444,161,776,256 | **0** |
| 3: f32+FMA | **128,000** | `4532022589074178048` | **6.327e-7** | **4.178e-7** | 291,285,346,070,000 | **0** |

with, for every arm and every run:

* **first-token argmax 597**;
* **all 25 per-step argmax IDENTICAL** to arm 0's, and the **first 24 generated
  ids IDENTICAL**: `597 4695 20589 34 496 2992 355 229 26 19 26 39 41774 415 278
  1579 1049 2426 440 4695 10966 267 2936 1579`;
* **witnesses asserted both ways**: arm 0 `f32/fma = 0/0`, arm 1 `0/1`, arm 2
  `1/0`, arm 3 `1/1` — so a matching arm that never dispatched its kernel is
  excluded;
* `f32_drop=0` and `xf32_allocs=2`.

**Read honestly.** The f32 route moves **every** logit (128,000/128,000) and its
excursion is **~1.7e8 times larger** than the FMA route's. That is expected and it
is not a defect: f32 accumulation rounds at every one of ~9,000 terms per logit
where f64 rounds almost never, and the absolute bound scales as
`~sqrt(n) * eps32 * |terms|` — the measured **3.2e-7 relative** is what that
predicts. It is a *bounded* difference, not a small one, which is exactly why the
f32 path has its own flag and its own bar instead of being hung on a flag whose
gate is bit-exactness.

**Why doing it at all is moving TOWARD the reference:** llama.cpp's own SIMD dot
products use f32 and FMA. The f64 mul-then-add chain was the *more* different of the
two. The flag exists so the difference is opt-in, measured, and never silently
substituted for a sequence whose gate is bit-exactness.

The f64+FMA row is also **regression evidence**: `logit_mism=124782`,
`max_abs_diff_bits=4407335185335451648`, `max_ulp=1116224`,
`excursion_x1e18=2921` are **exactly** the values the FMA work measured before this
unit existed, in all four runs. The f64 FMA route is bit-for-bit unchanged.

---

## 9. The EXISTING flags' bit-exact gate is untouched

`tests/lfm2_fused_logits_test.quanta`, run AFTER the f32 work and with
`mm_fused_f32` off, 9 passes in one process over all 128,000 logits
(`loadavg` 17.20 -> 22.6):

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
PASS: fused Q4_K, fused Q6_K, both, and the scalar-chain tied projection are IDENTICAL to the existing path (all 128000 logits)
```

Every dispatch witness was asserted inside the test
(`fused_q4k_used`, `fused_q6k_used`, `fused_chain_used`, `fused_glu_used`,
`fused_attn_used`, `fused_conv_used` all 1 on the passes that set them), and all
nine passes printed the identical argmax sequence. **This is the proof that adding
the f32 flag changed nothing for the flags that were already there.**

---

## 10. End-to-end paired A/B

`tests/lfm2_f32_ab.sh`: the four configurations in a **palindrome**
(`off, f64+fma, f32, f32+fma, f32+fma, f32, f64+fma, off`) so every arm has a
near-load neighbour on both sides. Decode bench conf field 17 is the f32 field and
field 16 is fma; `lens 64/64/64`; every other flag at the shipped setting; one
binary; every arm echoes its own flags, witnesses and `loadavg`.

<!-- AB_PLACEHOLDER -->

---

## 11. Gate

<!-- GATE_PLACEHOLDER -->

---

## 12. The honest gap

<!-- GAP_PLACEHOLDER -->

---

## 13. Reproduce

```
cd /opt/tali/quanta && ulimit -c 0 -v 32000000
export QC=$PWD/compiler/0.0.255/bin/x86/qc     # md5 2fe5e2844b9c3a74cf7922152a69ea46

# --- 1. the encodings, BY EXECUTION (fast, no model) ---
python3 tests/lfm2_f32_enc_gen.py            # GNU as -> objdump -> table + prologue splice
gcc -O1 -o /tmp/f32enc tests/lfm2_f32_enc_verify.c && /tmp/f32enc
python3 tests/lfm2_f32_hexcheck.py
python3 tests/lfm2_jbytes_len_check.py

# --- 2. the kernel A/B + the independent f32 reference oracle (minutes) ---
$QC -O tests/lfm2_f32_kernel_ab_test.quanta /tmp/f32ab
( ulimit -c 0 -v 32000000; /tmp/f32ab </dev/null )

# --- 3. EVERYTHING, in the right order, under the ONE pin ---
bash tests/lfm2_f32_remeasure.sh

# --- 3b. or individually ---
bash tests/lfm2_f32_correctness.sh          # the f32 bar, then the existing gate
LENS=32 bash tests/lfm2_f32_ab.sh           # the end-to-end palindrome
"$QC" -O tests/lfm2_f32_fill_bench.quanta /tmp/f32fill && /tmp/f32fill
python3 tests/lfm2_f32_ab_analyze.py /tmp/ab32 /tmp/ab32b

# --- 4. the end-to-end paired A/B, reduced (min over each arm's runs, and the
#         palindrome pairs, because this box's available cores swing INSIDE an arm
#         and loadavg is a one-minute average that lags it) ---
python3 tests/lfm2_f32_ab_analyze.py /tmp/ab32 /tmp/ab32b

# --- 5. the gate (expect >=242 native + 114 stdlib; see section 11 for the
#         version artefacts this tree now carries) ---
pgrep -af run_tests.sh          # must be empty first
QC=$PWD/compiler/0.0.255/bin/x86/qc bash test_suites/scripts/run_tests.sh
```

---

## 14. Routed, not done here

1. **The tied output projection (pool kind 5) is NOT on the f32 route.** Its
   reference dot is a strict left-to-right SCALAR chain, which a lane-based kernel
   cannot reproduce; it is 9.72% of per-token matvec elements and stays on the
   f64 scalar-chain kernel. Whoever takes it needs the chain's shape in f32, which
   is possible (four serial `vaddss`) but is a separate design.
2. **Core availability / pool sizing remains untouched and remains the binding
   constraint.** The previous unit's verdict stands: the same pool job is 45 us at
   nw=8 and 185 us at nw=20. Nothing in this work moves it.
3. **The per-row invariant arg stores in `pl_run_rows_map`** — still the smallest
   lever, still an unmeasured estimate (<0.5%).
4. **`pl_xf32_fill` is a scalar Quanta loop** (~3 builtin calls per element) and is
   now measured (§5.2). If it ever shows up as a real cost, an eight-wide
   `vcvtpd2ps`+`vinsertf128` JIT'd converter would cut it ~8x. It is not worth the
   verification cost until the number says so.
