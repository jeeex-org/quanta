# Native inference — consolidated status

Consolidated 2026-10-05 from `docs/plans/quanta-native-gguf.md`,
`docs/plans/native-inference.md`, `docs/plans/100-native-rag.md` and
`docs/research/native-inference-gaps.md`. Those four are removed; this file
replaces them and is the single place to read about native inference.

Target model: `/opt/ai/models/quanta/QUANTA-LFM2.5-2.6Bv1-Q4_K_M.gguf`
Reference (F16): `QUANTA-LFM2.5-2.6Bv1.gguf`

## Where this actually stands

**Loader: verified. Inference engine: does not exist.**

These two are separate and the distinction matters. Everything below is
measured, not planned.

## Loader — verified

### GGUF container

- Metadata parsing works.
- KV entries: the model has 37.
### Tensors

The model has **266** tensor descriptors and the loader holds all of them:
`lib/std/gguf.quanta:96` allocates `mem_alloc(gguf_n_tensors * TINFO_SIZE)`, so
the table is sized from the header count rather than a fixed cap. Names are
materialised as real strings by `gguf_tensor_name_str()`.

An earlier version of this doc claimed `TensorInfo` was `[TensorInfo; 128]` and
that 266 tensors did not fit, as a blocking defect. **That was wrong** — it
described `lib/std/native_inference.quanta`, which nothing imported, did not
compile, and which has since been deleted. The real loader was never capped. The
actual weight-memory constraint is documented in
`docs/plans/lfm2-native-inference-spec.md`.

### Dequantizers

`scripts/audit/dequant_diff.py` compares against **compiled `ggml-quants.c`**
and reports **0 mismatches of 32**:

| Format | Coverage |
|---|---|
| Q6_K | 256-element block |
| Q5_K | 256-element block |
| Q8_0 | 32-element block |
| F16 | 10 patterns |

`dequant_q4k` is verified **separately**, against a pure-Python oracle. It is
**not** covered by `dequant_diff.py`.

Q6_K scales use signed `i8_at`. Getting this wrong yields plausible-looking
garbage rather than an error.

### Not present

- Q2_K, Q3_K, IQ variants — **unused by this model**, so not blocking.
- F32 — not covered by the audit harness.
- The metadata smoke test validates *shape*, not tensor *correctness*. It
  passing says nothing about whether a tensor decodes correctly.

### Q4 matvec

The emitter builtins `q4k_dot` and `q4k_matvec` are **unsafe stubs**
(`q4k_matvec` is a no-op that returns `y` unchanged). They were deliberately
rejected. The real path is `lib/std/matmul_q4k.quanta`, a pure-Quanta
144-byte Q4_K dequantize + matvec, independently oracle-verified.

## Inference engine — absent

Nothing in this section exists. The `lib/std/native_inference.quanta` that this
table originally described has been deleted: nothing imported it, it did not
compile (`cannot resolve imported module 'std/mem'`), and its `tokenizer_encode`
returned placeholder IDs 1, 2, 3.

| Component | State |
|---|---|
| GPT-2/LFM2 BPE tokenizer | absent |
| Token embeddings | not wired |
| All 30 layers | not wired |
| Short convolution + cache | not wired |
| Attention, RoPE, KV cache | not wired |
| Logits, sampling, generation | not wired |

### Order of work

Superseded by `docs/plans/lfm2-native-inference-spec.md`, which replaces the
"raise TensorInfo capacity" step (there is no such defect) with the real weight
memory constraint and corrects the architecture facts: no separate output head
(`token_embd.weight` is tied to the output projection), attention and conv layers
are mutually exclusive, `attn_k`/`attn_v` are 512 wide (GQA 4:1), and the
attention layers are `[2, 5, 9, 13, 17, 21, 24, 27]`.

Each stage is gated on the one before it producing correct numbers against the
F16 reference, not on compiling.

## Design constraints

- **Native is the default.** `extern C` and other external support stay
  available as an *optional* switch — for CUDA or similar — but the default path
  must be fully native. Quanta must be able to build anything natively.
- **Oracle or it did not happen.** Every stage is compared against
  `ggml-quants.c` (dequant) or the F16 model (forward pass). A stage that
  compiles and runs but has no oracle is not verified.
- Generated and freshly built binaries run under
  `systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0`. `ulimit -v`
  and `prlimit` both return rc=1 on this host **without taking effect**.

## RAG

`plans/100-native-rag.md` described embedding storage and retrieval. It is
dependent on the inference engine being operational — embeddings come from the
model. It is therefore not scheduled and is not represented here as a stage.