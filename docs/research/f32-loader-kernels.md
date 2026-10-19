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
instead of 4. The measured kernel ratio on the Q4_K chain is **2.14-2.39x** (§6),
which is the instruction count landing almost exactly.

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

Measured consequence, `tests/lfm2_f32_diag_probe.quanta`, `loadavg` 12.2, under the
earlier 0.0.252 pin — the defect lived in a **hand-written hex string**, not in
compiler output, so the value is not compiler-dependent; it was found and fixed
before the re-pin, and the *fixed* value (0.031541 / bits `4584706437254479872`) is
what every run since asserts:

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

Three separate processes under the single 0.0.255 pin, `loadavg` **24.49** for all
three (they ran back to back; the 1-minute average did not move between them):

| tensor | dtype | cols | f64/f32 min (3 runs) | f64/f32 sum | f64/f32fma min | f64/f32fma sum |
|---|---|---|---|---|---|---|
| `ffn_gate.0` | Q4_K | 2048 | **2.384 / 2.144 / 2.281** | 2.340 / 2.103 / 2.270 | 2.140 / 2.290 / 2.599 | 2.075 / 2.311 / 2.615 |
| `ffn_up.0` | Q4_K | 2048 | **2.385 / 2.152 / 2.388** | 2.361 / 2.310 / 2.329 | 2.137 / 2.288 / 2.142 | 2.271 / 2.434 / 2.121 |
| `ffn_down.3` | Q6_K | 10752 | **1.848 / 1.852 / 1.853** | 1.833 / 1.853 / 1.834 | 1.945 / 1.952 / 1.957 | 1.908 / 1.973 / 1.977 |
| `attn_v.2` | Q6_K | 2048 | **1.712 / 1.702 / 1.704** | 1.447 / 1.705 / 1.585 | 1.788 / 1.786 / 1.786 | 1.730 / 1.785 / 1.782 |

**Read honestly:**

* **The Q4_K chain is 2.14-2.39x faster in f32**, against the 2.38x the instruction
  count predicts (§1.1). That is the strongest agreement available and it is the
  number to quote: the Q4_K chain is **78.69%** of the model's matvec elements.
* **Q6_K is 1.70-1.85x faster**, well short of its ~2.4x instruction prediction.
  The emitted bodies halve the FP vector-op count (10 per 8 elements -> 5), and
  that halving is the ceiling the Q6_K kernel actually reaches; the Q4_K kernel
  also halves the *dependency* structure of the fold, which is why it gets closer.
  **`ffn_down.3` is the most trustworthy row in the table**: its min estimator reads
  1.848 / 1.852 / 1.853 across the three runs, a **0.3% spread over three separate
  processes**, and its sum estimator agrees with it to 0.2% in runs 2 and 3. The
  two `attn_v.2` sum readings that disagree (1.447, 1.585) are interference bursts
  in one estimator only.
* **f32+FMA vs plain f32.** On Q6_K it is consistently faster in **all six**
  samples: `ffn_down.3` 1.945-1.957 against 1.848-1.853 (**+5.2% to +5.7%**), and
  `attn_v.2` 1.786-1.788 against 1.702-1.712 (**+4.6% to +5.0%**). On Q4_K it is
  **inconclusive**: the sign flips between runs in both directions (`ffn_up.0`
  run 1 2.385 plain vs 2.137 FMA, run 2 2.152 plain vs 2.288 FMA, run 3 2.388
  plain vs 2.142 FMA). No claim is made for Q4_K.
* The **sum** estimator is the noisier of the two on this box at `loadavg` 24.5;
  on `ffn_down.3` and `attn_v.2` (run 2) the two agree to 0.2-0.3%, which is the
  internal consistency check the row needs.

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

in **three separate processes under the 0.0.255 pin, `loadavg` 24.49** — **0
mismatches over 4 tensors x 32 rows x 3 runs = 384 row comparisons**, and
`exactly_one_nan=0` throughout (the column that would
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

Reproduced **byte-identically in every one of the seven runs it was taken** — four
under the earlier 0.0.252 pin (`loadavg` 8.67, 12.33, 19.40, 19.63) and three under
the final 0.0.255 pin (`loadavg` 24.29, 16.85, 14.19). **The bound is a property of
the arithmetic, not of the compiler and not of the load**, which is why re-pinning
did not change a bit of it while every *timing* figure had to be re-taken:

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
excursion is **~1.9e8 times larger** than the FMA route's. That is expected and it
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
unit existed, in all seven runs and under both compilers. The f64 FMA route is
bit-for-bit unchanged.

The witnesses are also the check that the arms are the arms: arm 0 `f32/fma =
0/0`, arm 1 `0/1`, arm 2 `1/0`, arm 3 `1/1`, asserted in the bar every run.

---

## 9. The EXISTING flags' bit-exact gate is untouched

`tests/lfm2_fused_logits_test.quanta`, run AFTER the f32 work, with
`mm_fused_f32` off, and **under the 0.0.255 pin**: 9 passes in one process over
all 128,000 logits (`loadavg` 20.9 -> 22.5):

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

All figures under the single final pin, `compiler/0.0.255/bin/x86/qc` (md5
`2fe5e2844b9c3a74cf7922152a69ea46`). **Two rounds of the palindrome = 8 samples
per configuration.** `LENS=32` (not 64): an arm whose own three runs take 2.5
minutes cannot resolve an effect on a box whose available cores swing 2.5x *inside
one arm* — measured, the LENS=64 version produced arm means of 1.93-4.96 tok/s that
did not track `loadavg` at all, and **those arms were thrown away rather than
compared**.

| arm | f32 | fma | round | `loadavg` before | tok/s (run1/2/3) | min ms/token |
|---|---|---|---|---|---|---|
| off1 | 0 | 0 | 1 | 14.23 | 1.94 / 1.85 / 1.80 | 516.6 |
| off1 | 0 | 0 | 2 | 24.40 | 1.97 / 1.92 / 1.81 | 508.3 |
| off2 | 0 | 0 | 1 | 23.02 | 1.76 / 1.59 / 1.79 | 556.8 |
| off2 | 0 | 0 | 2 | 22.23 | 1.83 / 1.91 / 1.84 | 523.4 |
| f64fma | 0 | 1 | 1 | 20.41 | 2.02 / 2.05 / 2.01 | 488.4 |
| f64fma | 0 | 1 | 2 | 24.10 | 1.84 / 1.82 / 1.81 | 543.2 |
| f64fma2 | 0 | 1 | 1 | 22.97 | 1.92 / 1.82 / 1.86 | 522.1 |
| f64fma2 | 0 | 1 | 2 | 23.16 | 1.83 / 2.00 / 1.93 | 501.2 |
| **f32** | 1 | 0 | 1 | 22.36 | **3.20 / 3.08 / 3.21** | 311.7 |
| **f32** | 1 | 0 | 2 | 20.89 | **2.93 / 2.83 / 2.92** | 341.3 |
| **f322** | 1 | 0 | 1 | 22.78 | **2.21 / 2.97 / 3.05** | 327.9 |
| **f322** | 1 | 0 | 2 | 21.38 | **2.96 / 2.56 / 2.75** | 338.4 |
| **f32fma** | 1 | 1 | 1 | 22.77 | **3.37 / 3.50 / 3.34** | 285.4 |
| **f32fma** | 1 | 1 | 2 | 22.76 | **3.13 / 3.12 / 3.24** | 308.9 |
| **f32fma2** | 1 | 1 | 1 | 21.62 | **3.07 / 3.17 / 3.13** | 315.6 |
| **f32fma2** | 1 | 1 | 2 | 23.71 | **3.10 / 3.14 / 3.02** | 318.7 |

Witnesses were asserted per run: every f64 arm printed `fused_f32_used=0` and
`fma_used=0` or `1`, and every f32 arm printed `fused_f32_used=1` with the
matching `fma_used`; `xf32_elems` was 0 on the f64 arms and
**155,080,704** on every f32 arm (identical across all four f32 arms, which is
itself evidence that all four took the same route). Every arm and every run
printed `first_argmax_id=597`.

**The separation is clean, and this is the result:**

| configuration | least-interfered arm sample | ms/token | vs f64 |
|---|---|---|---|
| f32=0 fma=0 (f64 folded) | 1.967 tok/s | 508.3 | — |
| f32=0 fma=1 (f64 FMA) | 2.047 | 488.4 | **+4.1%** |
| **f32=1 fma=0** | **3.207** | **311.7** | **+63.0%** |
| **f32=1 fma=1** | **3.504** | **285.4** | **+78.1%** |

* **No f64 sample overlaps any f32 sample.** The eight f64-family arm samples span
  1.795-2.047 tok/s; the eight f32-family arm samples span 2.929-3.504. The
  ratio therefore has a *range* and not a point, and the honest statement is:
  **plain f32 is 1.43x to 1.79x, and f32+FMA is 1.53x to 1.95x**, taken as
  (worst f32 sample / best f64 sample) to (best f32 sample / worst f64 sample).
  The min-ms single-best basis is 1.63x and 1.78x.
* **The f64+fma arm reproduces the previous unit's absolute numbers**: it reads
  1.840-2.047 tok/s here at `loadavg` 20.4-24.1, against that unit's **1.985-2.080
  at `loadavg` 21.6-22.5** for the same shipped configuration. That is a cross-check
  that the 0.0.255 pin did not move the f64 path, and that this box's band is the
  same band.
* **The f32 route's cost is visible and small.** The only work it adds on the
  critical path is the narrowing (§5.2), measured in `f32_elems`:
  **~198,060 element-narrowings per token-forward** (155,080,704 per arm over three
  64-token runs with a 23-token prompt = 3 x 87 forwards). At the fill's measured
  **5.24-6.61 ns/element** that is **~1.2 ms/token**, about 0.4% of the 285-340 ms
  token. **The design document's estimate of "~340K per token, which is noise" was
  the right order and the right conclusion; the element COUNT is ~198K, and the
  cost is 1.2 ms.**
* `xf32_allocs=2` on every f32 arm in every run (§5.1).


---

## 11. Gate

```
QC=$PWD/compiler/0.0.255/bin/x86/qc bash test_suites/scripts/run_tests.sh
md5 2fe5e2844b9c3a74cf7922152a69ea46      (the pin every figure in this file used)
```

```
=== Results: 246/246 pass, 0 fail (incl. 0 compile-fail) [rows: EXPECTED.tsv] ===
=== Security: 8 passed, 0 failed, 0 known issues ===
=== Perf: 3 passed, 0 failed (baseline 4000ms) ===
  STDLIB: 114/114 GREEN
```

**0 RED stages.** `bang test_suites/scripts/run_tests.sh` was run with no peer gate
alive first (`pgrep -af run_tests.sh` empty).

Worth recording, because it is the version-artefact class the brief warned about:
under the earlier **0.0.252** pin the same tree showed two RED rows —
`deadstore-guard` (a 0.0.250 F2 loop-shape row) and `terminator-guard` (0.0.252 F3)
— which *cannot* pass under a compiler older than the feature they assert. Under
0.0.255 both are GREEN, together with the new `spillframe-guard` (0.0.253 A32) and
`constmul-guard` (0.0.255 F6) rows. The re-pin resolved that class rather than
arguing about it; nothing in this unit's own paths was ever one of those rows.

Emitted-code helpers, run because emitted code was touched:

```
python3 tests/lfm2_f32_hexcheck.py     110 hex strings, 0 failures
python3 tests/lfm2_jbytes_len_check.py 223 jbytes() calls, 0 mismatches (was 180)
gcc -O1 -o /tmp/f32enc tests/lfm2_f32_enc_verify.c && /tmp/f32enc
                                       102 sequences executed, 0 assertion failures
```


---

## 12. The honest gap

**The recommended shipped *setting* is `mm_fused_f32=1` (with `mm_fused_fma=1` as
well it is the fastest measured arm). The FLAG itself remains default-OFF in
`lib/std`, as required** — nothing in the tree changes behaviour unless a caller or
a bench conf asks for it, and every existing flag's gate keeps its meaning. Both anchors below are `loadavg`-labelled, and no
quiet window was available: this session's `/proc/loadavg` ran **8.7 to 32.7**, with
one brief excursion to 7.2 that was **not** caught by an A/B, so the quiet-window
figure is not measured and is not claimed.

**At `loadavg` 20.9-24.4 (the band every f32 arm's samples sat in), 32-token runs,
shipped flags otherwise:**

| configuration | tok/s (least-interfered sample) | ms/token |
|---|---|---|
| f32=0 fma=1 — the configuration the previous unit shipped | 1.840-2.047 | 488-543 |
| **f32=1 fma=0** | **2.929-3.207** | 312-341 |
| **f32=1 fma=1 (now shipped)** | **3.138-3.504** | 285-319 |

* Gap to the **15 tok/s** target: **4.3x - 4.8x** (15 / 3.504 and 15 / 3.138).
* Gap to llama.cpp's **17.32 tok/s** on the same model and CPU: **4.9x - 5.5x**.
* For comparison, the previous unit measured **7.3x - 7.6x** to 15 and **8.3x -
  8.7x** to llama.cpp at `loadavg` 21.6-22.5, for the same tree with
  `fused_fma=1` and no f32 route. **The gap roughly halved**, and the f64+fma arm
  measured here (1.840-2.047) reproduces that unit's absolute band (1.985-2.080),
  so the two sessions are comparing the same box in the same load band.

**What this unit moved, measured:**

* the folded Q4_K matvec kernel **2.14-2.39x** and Q6_K **1.70-1.85x** faster,
  from 8 f32 lanes per ymm instead of 4 and half the x traffic;
* **end-to-end +43% to +79%** for plain f32 and **+53% to +95%** for f32+FMA,
  across the eight arm samples per configuration, with no f64/f32 overlap;
* a grow-only f32 x buffer that costs **two mappings for the whole process** and
  **~1.2 ms/token** of main-thread work;
* two emitted-code defects found, fixed, and covered by mechanical checks
  (§3) — one of which (`vpmovzxbd ymm6,[r9]` having no displacement field)
  segfaulted the kernel outright.

**What it did NOT move, said plainly.** The binding constraint is still **core
over-subscription** and nothing here touches it. The previous unit's verdict stands
unchallenged: the same pool job is 45 us at nw=8 and 185 us at nw=20, and at nw=20
the pool job is no faster than the main thread. A token still pays 166 pool
barriers. The f32 kernel makes each worker's slice cheaper; it does not give the
workers more cores. **Closing 4.3x to 15 tok/s is not a matvec-kernel job from
here** either — the kernels are now within ~1.2-1.5x of what 8-lane f32 SIMD can do
for this layout, so no further multiple is hiding in them.

**Levers that remain, ranked by what is measured about them:**

1. **Core availability / pool sizing.** Unchanged and untouched. Nothing here moves
   it. This is where the 4.3x lives.
2. **The tied output projection** (pool kind 5, `token_embd.weight`, Q6_K,
   `[2048, 128000]`, **9.72%** of per-token matvec elements) is still on the f64
   scalar-chain route, because its reference dot is a strict left-to-right chain
   that a lane-based kernel cannot reproduce. An f32 **chain** kernel is possible
   (four serial `vaddss` per 4 elements, the f64 chain kernel's shape with `ss`
   opcodes and half the x bytes) and is the one remaining kernel-shaped lever.
   Not done here.
3. **`pl_xf32_fill` is still a scalar Quanta loop.** It is now measured at ~1.2
   ms/token, so it is not worth an eight-wide `vcvtpd2ps`+`vinsertf128` JIT'd
   converter until something makes it show up.
4. **The per-row invariant arg stores in `pl_run_rows_map`** — still the smallest
   lever, still an unmeasured estimate (<0.5%).

**Not done, and named rather than implied:**

* **No quiet-window absolute measurement.** Every absolute tok/s above carries its
  `loadavg`; the low-load anchor is quoted from the previous unit, not re-taken.
* **The Q4_K `f32+FMA` vs plain-`f32` comparison is inconclusive** and is reported
  as inconclusive rather than resolved in either direction (§6).
* **An f32 chain kernel for the tied output projection** (lever 2 above) — designed
  nowhere, done nowhere.
* **Pool concurrency, the partition rule, the KV format and the conv
  false-sharing knob were deliberately NOT touched**, per the standing constraint;
  all four are settled on prior measurement.


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
