# Native inference — implementation spec

Reviewed spec for the remaining native inference work, written 2026-10-05 against
`lib/std/gguf.quanta` (the verified loader) and the real model. Supersedes the
stale "blocking defect" and "order of work" sections of `NATIVE_INFERENCE.md`,
which are corrected below.

**Status of `lib/std/native_inference.quanta`: dead code.** Nothing imports it. It
does not compile (`cannot resolve imported module 'std/mem'` — the module does not
exist), its `tokenizer_encode` returns placeholder IDs, its `q4k_dequant_block`
uses a 136-byte block that is wrong for Q4_K's 144, and it is referenced only in
compiler comments and old research notes. It is **not** the loader. The loader is
`lib/std/gguf.quanta`. Stage 0 below removes it so it stops reading as live code.

---

## Correction to the previous status doc

`NATIVE_INFERENCE.md` claims `TensorInfo` is `[TensorInfo; 128]` and that 266
tensors do not fit, calling it a blocking defect. **That is wrong for the real
loader.** `lib/std/gguf.quanta:96` already does:

```
gguf_tensor_data = mem_alloc(gguf_n_tensors * TINFO_SIZE)
```

The table is sized from the header count, 40 bytes per record, and holds all 266.
`gguf_num_tensors()` returns 266 in every test run to date. The 128-entry array is
in `native_inference.quanta`, which nothing imports.

So planned stage 1 ("raise the 128 capacity") has no defect to fix. The real
constraint is different and harder, and it is described below.

---

## Verified facts this spec is built on

Measured from the model with an independent Python parser
(`scripts/audit/read_formats_oracle.py`), cross-checked against native Quanta.

| Fact | Value |
|---|---|
| Tensors | 266 |
| Metadata KVs | 37 |
| Dtypes | F32 ×99, Q4_K ×148, Q6_K ×19 (Q2_K ×0) |
| Params | 2.697 B |
| Layers | 30 |
| hidden | 2048 |
| ffn | 10752 |
| heads | 32 (q proj 2048, kv proj 512) |
| head_dim | 64 |
| conv layers | 8 attention layers, **22 conv-only** |
| `l_cache` | 3 |
| rope base | 1e7 |
| rms eps | 1e-5 |
| context | 131072 |
| vocab | 128000 |

### Layer split — corrected

Previous notes said "8 attention layers and 22 short-conv layers" from a
`head_count_kv` array. Confirmed exactly by grouping descriptors, which is the
authoritative source:

```
ATTN layers (11 tensors) = [2, 5, 9, 13, 17, 21, 24, 27]
CONV layers (8 tensors)  = [0, 1, 3, 4, 6, 7, 8, 10, 11, 12, 14, 15, 16,
                            18, 19, 20, 22, 23, 25, 26, 28, 29]
```

These match `lfm2.attention.head_count_kv`, which is 0 at each conv layer and
non-zero at each attention layer.

### Attention layer tensors (11)

```
attn_norm.weight     [2048]        ffn_gate.weight    [2048,10752]  Q4_K
attn_q.weight        [2048,2048]   ffn_norm.weight    [2048]
attn_k.weight        [2048,512]    ffn_down.weight    [10752,2048]  Q6_K
attn_v.weight        [2048,512]    shortconv.*         -- absent
attn_q_norm.weight   [64]
attn_k_norm.weight   [64]
attn_output.weight   [2048,2048]
ffn_up.weight        [2048,10752]
```

### Conv-only layer tensors (8)

```
ffn_gate.weight            [2048,10752]  Q4_K     attn_norm.weight   [2048]
ffn_down.weight            [10752,2048]  Q6_K     ffn_norm.weight    [2048]
ffn_up.weight              [2048,10752]  Q4_K
shortconv.conv.weight      [3,2048]      F32
shortconv.in_proj.weight   [2048,6144]   Q4_K
shortconv.out_proj.weight  [2048,2048]   Q4_K
```

### Architecture facts that were wrong in the earlier notes

1. **There is no output head.** No `output.weight`, no `lm_head`. `token_embd.weight`
   `[2048, 128000]` Q6_K is the output projection — it is tied to the input
   embedding. The final norm is `token_embd_norm.weight` `[2048]`.
2. **Attention layers have no conv.** Layers with `attn_q` have no `shortconv.*`;
   conv-only layers have no `attn_*`. The split is exclusive, not additive.
3. **`attn_k`/`attn_v` are 512 wide, not 2048** — 8 KV heads × 64, i.e. GQA at
   ratio 4 against 32 query heads. The earlier `[2048,512]` note had these
   transposed.
4. **Conv-only layers still carry an `attn_norm.weight` [2048]** even though they
   have no attention at all. Most likely it is the pre-block residual norm with a
   reused name, but that is a guess and must be confirmed against the reference
   implementation before stage 4 is written. Flagged as an open question below —
   getting it wrong silently changes every layer's residual stream.

---

### Per-layer dtype map — measured, not uniform

Two roles are **not** the same dtype on every layer. Asserting one global dtype
per role is wrong and produced 20 bogus test failures before this was measured:

| Role | Q4_K | Q6_K | F32 |
|---|---|---|---|
| `ffn_gate` | 30 | — | — |
| `ffn_up` | 30 | — | — |
| `ffn_down` | 16 | 14 | — |
| `ffn_norm` | — | — | 30 |
| `attn_norm` | — | — | 30 |
| `attn_q` | 8 | — | — |
| `attn_k` | 8 | — | — |
| `attn_v` | 4 | 4 | — |
| `attn_q_norm` | — | — | 8 |
| `attn_k_norm` | — | — | 8 |
| `attn_output` | 8 | — | — |
| `shortconv.conv` | — | — | 22 |
| `shortconv.in_proj` | 22 | — | — |
| `shortconv.out_proj` | 22 | — | — |

```
ffn_down Q6_K : [0,1,2,5,8,11,14,17,20,23,26,27,28,29]
ffn_down Q4_K : [3,4,6,7,9,10,12,13,15,16,18,19,21,22,24,25]
attn_v   Q6_K : [2,13,24,27]
attn_v   Q4_K : [5,9,17,21]
```

Practical consequence: a matvec kernel must dispatch on
`gguf_tensor_dtype(idx)` **per tensor**, never on a compile-time constant derived
from the role. This is already how `read_tensor_f64()` works.

---

## GGML format coverage — the full 43-type taxonomy

Verified against `/opt/ai/llama.cpp/ggml/src/ggml-common.h`, whose
`static_assert(sizeof(block_x) == ...)` lines state each block's true size.

### Uniform-scale — dequantize is self-contained, verifiable per type

| Format | dtype | bytes | block | dequantizer | wired |
|---|---|---|---|---|---|
| F32 | 0 | 4 | 1 | yes | yes |
| F16 | 1 | 2 | 1 | yes | yes |
| Q4_0 | 2 | 18 | 32 | — | no |
| Q4_1 | 3 | 20 | 32 | — | no |
| Q5_0 | 6 | 22 | 32 | — | no |
| Q5_1 | 7 | 24 | 32 | — | no |
| Q8_0 | 8 | 34 | 32 | **exists, unwired** | no |
| Q8_1 | 9 | 36 | 32 | — | no |
| Q2_K | 10 | 84 | 256 | — | no |
| Q3_K | 11 | 110 | 256 | — | no |
| Q4_K | 12 | 144 | 256 | yes | yes |
| Q5_K | 13 | 176 | 256 | **exists, unwired, unverified** | no |
| Q6_K | 14 | 210 | 256 | yes | yes |
| Q8_K | 15 | 292 | 256 | — | no |
| BF16 | 30 | 2 | 1 | — | no |
| TQ1_0 | 34 | 54 | 256 | — | no |
| TQ2_0 | 35 | 66 | 256 | — | no |

### Codebook / IQ — need the codebook tensor from the same file

Each 2-bit (or 3-bit) index selects from a learned codebook shipped *in the
GGUF as its own tensor*. These cannot be written in isolation; each needs the
codebook plus a `ggml_vec_dot` variant.

| Format | dtype | bytes | block |
|---|---|---|---|
| IQ2_XXS | 16 | 66 | 256 |
| IQ2_XS | 17 | 74 | 256 |
| IQ3_XXS | 18 | 98 | 256 |
| IQ1_S | 19 | 50 | 256 |
| IQ4_NL | 20 | 18 | **32** |
| IQ3_S | 21 | 110 | 256 |
| IQ2_S | 22 | 82 | 256 |
| IQ4_XS | 23 | 136 | 256 |
| IQ1_M | 29 | 56 | 256 |

### FP4 and the newest types

| Format | dtype | bytes | block | notes |
|---|---|---|---|---|
| MXFP4 | 39 | 17 | 32 | E8M0 scale |
| NVFP4 | 40 | 36 | 64 | 4× UE4M3 scales per block |
| Q1_0 | 41 | 18 | 128 | ternary, 1-bit |
| Q2_0 | 42 | 18 | 64 | 2-bit |

### Plain integer
`I8`(24) `I16`(25) `I32`(26) `I64`(27) `F64`(28) — 1/2/4/8/8 bytes.

Removed and never to be implemented: `Q4_2`(4), `Q4_3`(5),
`Q4_0_4_4/4_8/8_8`(31-33), `IQ4_NL_4_4/4_8/8_8`(36-38).

### Byte-size bug found and fixed (2026-10-05)

`gguf_tensor_nbytes()` had wrong values for **six IQ types and BF16**:

```
IQ4_NL  18 vs 110   (used a 256-block for a 32-block type)
IQ3_S  110 vs  82
IQ2_S   82 vs 136   (swapped with IQ4_XS)
IQ4_XS 136 vs 186
IQ1_M   56 vs  54
BF16     2 vs  56   (treated 2 bytes/elem as a 256-element block)
```

Summing the wrong table overran the file:

```
                        old sum_nbytes      new sum_nbytes     filesize
GG4-26B4-IQ4        11,093,359,736      13,581,352,056   13,597,177,568   (was short 2.50 GB)
GW38-27B-IQ4        16,777,233,024      13,894,652,544   13,905,647,712   (was over  2.87 GB)
GG4-E4B              4,912,314,536       4,961,343,656    4,977,171,584   (was short   65 MB)
```

Every other model already landed within ~15 MB of metadata padding; the three
files above did not, which is how the bug was isolated. Fixed and pinned by
`tests/test_nbytes_table.quanta` (3,496 tensors across 6 real models, 0 wrong).

### Formats actually present in models on this box

```
LFM2.5-2.6Bv1            F32=99   F16=167
LFM2.5-2.6Bv1-Q4_K_M     F32=99   Q4_K=148  Q6_K=19
GG4-E4B-Q4_K_M           F32=423  Q4_K=253  Q5_K=1  Q6_K=42  BF16=1
GG4-26B4-IQ4             F32=392  Q8_0=207  IQ4_NL=29  IQ3_S=29  IQ4_XS=1
GW38-27B-Q4KM            F32=456  Q8_0=1  Q4_K=294  Q5_K=48  Q6_K=67
GW38-27B-IQ4             F32=408  Q8_0=5  Q4_K=5  Q5_K=21  Q6_K=59  IQ3_S=75  IQ4_XS=293
```

Q2_K and Q3_K appear in **no** model on this box. No `gguf`/`numpy` package is
installed, so an independent reference for those two would have to come from
llama.cpp itself.

---

## The real blocking constraint: weight memory

Full dequantization to f64 is **20.1 GB**; to f32, **10.05 GB**. The box has 62 GB
total but 8 GB of GPU and a standing policy of running generated binaries under
`MemoryMax=6G`. Full materialization cannot run under that cap at all.

Options, with the tradeoff stated honestly:

| Approach | Memory | Cost |
|---|---|---|
| A. Dequantize all to f32 | 10.05 GB | Over the 6G cap. Simple. |
| B. Keep GGUF quantized, matvec in place | ~1.6 GB | Correct, and the quantized kernels already exist and are verified. |
| C. Layer-streamed: load one layer's ffn at a time | peak ~600 MB | Needs all 30 layers read 30× or cached; slower. |

**B is chosen.** The model is already quantized on disk; the correct thing is to
matvec against the quantized bytes rather than expand them. `matmul_q4k.quanta`
already implements a verified 144-byte Q4_K dequantize+matvec, and `gguf.quanta`
has verified F16/F32/Q4_K/Q6_K dequantizers. `q4k_dot`/`q4k_matvec` emitter
builtins are **unsafe stubs** and stay unused.

This means: **no weight buffer is ever materialized at inference time.** The
tensor table stays a descriptor table (it already is). Activations are f64 scratch,
2048 doubles per layer per token — negligible.

---

## Stage plan

Each stage is gated on producing **correct numbers against an oracle**, not on
compiling. The oracle is `scripts/audit/read_formats_oracle.py` for tensor-level
values and, for forward-pass stages, a Python reference implementation of the
LFM2 forward pass over the same GGUF, added as
`scripts/audit/lfm2_forward_oracle.py`.

### Stage 0 — remove dead code
Delete `lib/std/native_inference.quanta`. Nothing imports it; it does not compile;
leaving it makes the docs lie. Update `NATIVE_INFERENCE.md` to match this spec.

### Stage 1 — weight table (descriptors only, no data)
Build a name→index map over all 266 descriptors using `gguf_tensor_name_str()`.
Not a load — a lookup. Output: `lib/std/lfm2_model.quanta` exposing

```
lfm2_tensor(name) -> idx          // exact-name lookup, fails loudly if absent
lfm2_layer_is_attn(L) -> 0|1
lfm2_ffn_gate(L), lfm2_ffn_up(L), lfm2_ffn_down(L), lfm2_ffn_norm(L), lfm2_attn_norm(L)
lfm2_attn_q(L), ..._k, ..._v, ..._q_norm, ..._k_norm, ..._output
lfm2_conv_conv(L), ..._in_proj, ..._out_proj
```

Each returns an index or `-1`; a caller that gets `-1` must fail explicitly rather
than read index 0. This is the piece the old `[TensorInfo;128]` stage was reaching
for, done against the loader that actually runs.

### Stage 2 — tokenizer (GPT-2 BPE, `pre='lfm2'`)
- byte-level: 256 byte tokens, `token_type` decides which are byte tokens.
- 293,320 merges, applied by rank; `pre='lfm2'` splits on a whitespace-like class.
- specials: BOS 124894, EOS 124900, PAD 124893.
- verified: `tokenizer.ggml.tokens` and `.merges` are in the file; the oracle
  re-implements BPE independently and both must agree on a fixed prompt set.
- Until this is right **no output means anything**.

### Stage 3 — embeddings + final norm
`token_embd.weight` row for the token id, then `token_embd_norm.weight` (RMS, eps
1e-5). Tied output head: logits = `token_embd.weight` @ final_normed.

### Stage 4 — short convolution + cache (22 layers)
`in_proj` → `[3,2048]×[2048,6144]` → depthwise conv over the last `l_cache=3`
positions → SiLU → `out_proj`. Conv state per layer, position-sensitive, so a
cache bug is immediately observable. Gated against the forward oracle.

### Stage 5 — attention + RoPE + KV cache (8 layers)
32 q heads, 8 kv heads (GQA 4:1), head_dim 64, `q_norm`/`k_norm` [64] are
per-head RMS. RoPE base 1e7. KV cache grows per position. Gated.

### Stage 6 — all 30 layers, layer-by-layer
Each layer's output compared against the oracle as it is built, not only at the
end. A wrong layer 0 must not be allowed to hide behind 29 more.

### Stage 7 — logits, sampling, generation
Logits via tied head, `top_k=50`, `temp=0.1` per the model's own metadata, EOS
stop. Text out.

---

## Test conventions

- Every stage adds a native `.quanta` test under `tests/`.
- Freshly built binaries run under
  `systemd-run --user --scope -p MemoryMax=6G -p MemorySwapMax=0`.
- No f64 materialization of weights — assert peak memory stays bounded, which is
  part of the correctness of choice B.
- Python is oracle only. Production loading and inference stay native `.quanta`.

## Open decisions for review

1. **Sampling** — model metadata says `top_k=50, temp=0.1`. Greedy may be more
   useful for a first "does it work" milestone. Greedy first, then honour
   metadata?
2. **Prompt handling** — `tokenizer.chat_template` is Jinja and present in the
   file. Not implementing Jinja; stage 2 will emit BOS + raw text and document
   that. Confirm?
3. **F16 model role** — the 5 GB F16 model has identical tensor names/shapes and
   is the forward-pass oracle source. Do we run the native forward on both and
   compare, or only on Q4?
4. **`attn_norm` on conv-only layers** (see fact 4 above) — is it a genuine
   residual norm the block applies, or a dead/unused weight? This needs the
   reference implementation to settle, not the GGUF.