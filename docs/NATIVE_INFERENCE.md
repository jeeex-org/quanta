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
- Tensors: the model has **266**. `TensorInfo` is `[TensorInfo; 128]` — this is
  a hard truncation and is one of the blocking defects below.
- Tensor data offsets are absolute. An earlier double-offset bug is fixed.
- Partial tensor reads work; token `5000` was verified against the F16 model.

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

Nothing in this section exists. `lib/std/native_inference.quanta` lines 537–551
are comments where execution belongs.

| Component | State |
|---|---|
| GPT-2/LFM2 BPE tokenizer | `tokenizer_encode` returns placeholder IDs 1, 2, 3 |
| Token embeddings | not wired |
| All 30 layers | not wired |
| Short convolution + cache | not wired |
| Attention, RoPE, KV cache | not wired |
| Logits, sampling, generation | not wired |
| TensorInfo capacity 128 < 266 tensors | **blocking defect** |

### Order of work

Each stage is gated on the one before it producing correct numbers against the
F16 reference, not on compiling.

1. **`TensorInfo` capacity.** 266 tensors do not fit in a 128-entry array. This
   blocks everything downstream and is the cheapest fix.
2. **Tokenizer.** GPT-2 byte-level BPE, verified against the F16 model's own
   vocabulary. Until this is right, no output means anything.
3. **Embeddings.** Token 5000 is already verified as a decode, so the primitive
   exists; wiring it into the graph is the work.
4. **Short convolution + cache.** LFM2's conv layers are position-sensitive, so
   cache correctness is observable immediately.
5. **Attention, RoPE, KV cache.** RoPE frequencies must match the reference or
   attention silently degrades — a wrong-but-plausible failure mode.
6. **All 30 layers**, checked layer by layer against F16 rather than only at
   the end.
7. **Logits, sampler, generation loop.**

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