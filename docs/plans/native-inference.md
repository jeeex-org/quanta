# Quanta Native Inference Engine — Design

## Goal
Add native GGUF loading + inference to the Quanta compiler — no llama.cpp dependency.

## Module Layout

```
include "inference/gguf_reader.quanta"   // GGUF file parser (mmap, metadata, tensors)
include "inference/tensor_ops.quanta"    // Matmul, softmax, layernorm, silu, rope
include "inference/model.quanta"         // Transformer block + full model
include "inference/tokenizer.quanta"     // BPE + SentencePiece tokenization
include "inference/engine.quanta"        // Autoregressive generation loop
include "inference/sampler.quanta"       // Greedy/temp/top-k/top-p
```

## Phase 1: GGUF Reader

Read the binary format:
- Magic `GGUF`, version, metadata K/V pairs
- Tensor definitions (name, shape, offset, type)
- Memory-map the file for zero-copy access

### Key structs:
```quanta
struct GGUFMeta {
    arch: String,        // "gemma4", "llama", etc.
    quant: String,       // "Q4_K_M", "F16", etc.
    n_layers: int,
    n_heads: int,
    n_kv_heads: int,
    head_dim: int,
    hidden_size: int,
    intermediate_size: int,
    vocab_size: int,
    // tokenizer info
    tok_model: String,   // "bpe", "spm"
    tok_merges: String,  // serialized merges
    tok_vocab: String,   // serialized vocab
}

struct GGUFFile {
    fd: int,
    size: usize,
    data: *u8,           // mmap'd file
    meta: GGUFMeta,
    tensors: Vec<TensorInfo>,
}

struct TensorInfo {
    name: String,
    shape: Vec<u32>,
    dtype: int,          // GGUF type enum
    offset: usize,
    size: usize,
}
```

## Phase 2: Tensor Operations

```quanta
fn matmul_f32(A: *f32, B: *f32, C: *f32, M: int, K: int, N: int)
fn dequant_q4_to_f32(src: *u8, dst: *f32, ne: int, bs: int)
fn layernorm(x: *f32, w: *f32, b: *f32, n: int, eps: f32)
fn softmax(x: *f32, n: int)
fn silu(x: *f32, n: int)
fn rope(q: *f32, k: *f32, n: int, dim: int, pos: int, base: f32)
```

## Phase 3: Model Forward Pass

Single transformer block:
```
input → layernorm → attention → residual → layernorm → FFN → residual → output
```

Multi-block stack with shared embedding table.

KV cache: ring buffer for autoregressive generation.

## Phase 4: Tokenizer

BPE decoder:
- Load merges + vocab from GGUF metadata
- Tokenize: text → Vec<int>
- Detokenize: Vec<int> → text

## Phase 5: Engine

```
prompt → tokenize → embedding → N×transformer blocks → final_layernorm → unembed → sample → append to input_ids → repeat
```

## Target Model

**QUANTA-LFM2.5-2.6Bv1-Q4_K_M.gguf**
- 2.6B params, Q4_K_M quantized
- Gemma4 architecture
- 10 layers, 5 KV heads, 64 head_dim
- ~5.5 GB VRAM

## Implementation Notes

- Use `mmap()` for zero-copy weight access
- Lazy dequantization (Q4 → F32 on demand during matmul)
- Simple greedy/temperature sampling first
- No SIMD initially — get correctness, then optimize

---

*Start implementation?*
