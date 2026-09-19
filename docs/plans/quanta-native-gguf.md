# Quanta Native GGUF Loader — Design Document

## Goal
Load and run GGUF models in pure Quanta without llama.cpp or any third-party dependency.

## Architecture

### 1. GGUF Binary Parser (`std/gguf/reader.quanta`)
- **Magic/Version:** Read 4-byte magic (`GGUF`), uint32 version
- **Metadata K/V:** Read metadata header (key-value pairs for model name, architecture, quantization, tokenizer, etc.)
- **Tensor Info:** Read tensor definitions (name, shape, offset, type)
- **Tensor Data:** Memory-mapped access to raw tensor bytes
- **Quantization Types Supported:**
  - F32, F16, BF16 (float types)
  - Q4_K_M (4-bit block quantization with 16-bit scales)
  - Q8_0 (8-bit block quantization)
  - Q5_K_M, Q6_K, IQ4_NL (future)

### 2. Tensor Operations (`std/inference/tensor.quanta`)
- **GGUF Tensor Object:** name, type, shape, data pointer
- **Dequantize:** Convert Q4_K_M blocks → F32 on demand
- **Matrix Multiply:** `matmul(A, B)` — core operation
- **Softmax:** `softmax(x, dim)`
- **LayerNorm:** `layernorm(x, weight, bias, eps)`
- **SiLU Activation:** `silu(x)`
- **ROPE:** Rotary position embedding
- **KV Cache:** Ring buffer for K/V states

### 3. Transformer Forward Pass (`std/inference/transformer.quanta`)
- **Attention:** Multi-head attention with KV cache
- **FFN:** Gate + Up + Down projection with SiLU
- **Block:** Pre-norm → Attention → Residual → Pre-norm → FFN → Residual
- **Stack:** N transformer blocks with shared embedding

### 4. Tokenizer (`std/inference/tokenizer.quanta`)
- **BPE:** Byte-pair encoding decoder
- **SentencePiece:** Support for SP models (Gemma uses this)
- **Simple fallback:** Character-level or whitespace tokenization for prototyping

### 5. Sampler (`std/inference/sampler.quanta`)
- **Greedy:** argmax
- **Temperature:** Softmax with temperature scaling
- **Top-k:** Restrict to k highest probability tokens
- **Top-p (nucleus):** Cumulative probability threshold

### 6. Inference Engine (`std/inference/engine.quanta`)
- **Pipeline:** tokenize → forward pass → sample → detokenize → repeat
- **Autoregressive:** Generate one token at a time
- **Batch support:** Optional batching for throughput

## Data Structures

```quanta
// GGUF file handle
struct GGUFFile {
    fd: int,
    size: usize,
    data: *u8,           // mmap'd
    metadata: Map<String, Value>,
    tensors: Vec<TensorInfo>,
    tensor_data_offset: usize,
}

// Tensor info (metadata only, no data loaded)
struct TensorInfo {
    name: String,
    shape: Vec<u32>,
    dtype: GGufDType,
    offset: usize,
}

// Tensor with loaded data
struct Tensor {
    info: TensorInfo,
    data: *u8,           // Pointer into mmap
    dequantized: Option<Vec<f32>>,  // Lazy dequantization cache
}

// Inference state
struct InferenceState {
    pos: u32,                    // Current position
    kv_cache: Vec<KVTensor>,    // Per-layer K/V cache
    input_ids: Vec<u32>,        // Token sequence
    logits: Vec<f32>,           // Last layer logits
}

// KV cache entry
struct KVTensor {
    key: Vec<f32>,
    value: Vec<f32>,
}
```

## Quantization Format: Q4_K_M (Primary Target)

Q4_K_M is a block quantization:
- **Block size:** 32 elements
- **Per block:** 16-byte scale (F16) + 16 bytes of 4-bit values (32 values packed into 16 bytes)
- **Total:** 32 bytes per block = 1 bpw (bit per weight)

**Dequantize algorithm:**
```
for each block of 32 elements:
    scale = read_f16(scale_ptr)
    for i in 0..32:
        byte_idx = i // 2
        is_high_nibble = (i % 2) == 0
        nibble = (block_bytes[byte_idx] >> (4 if is_high_nibble else 0)) & 0xF
        // Signed 4-bit: values in [-8, 7]
        value = nibble - 128 if nibble >= 8 else nibble  // Actually [-8, 7] directly
        dequantized = scale * value as f32
```

Actually Q4_K_M stores nibbles as signed integers in [-8, 7]. The high nibble is first.

## Performance Considerations

1. **Memory mapping:** Use `mmap()` for zero-copy tensor access
2. **Lazy dequantization:** Only dequantize weights when needed for matmul
3. **Block-wise matmul:** For Q4, do block-level operations rather than per-element
4. **SIMD:** Use Quanta's SIMD intrinsics if available, or fall back to scalar
5. **GPU offload:** For larger models, compute matmuls on GPU

## Implementation Phases

### Phase 1: GGUF Reader
- [ ] Parse GGUF header and metadata
- [ ] Read tensor info and mmap data
- [ ] Verify with existing QUANTA-LFM2.5-2.6Bv1-Q4_K_M.gguf
- [ ] Test: print all tensor names, shapes, types

### Phase 2: Tensor Operations
- [ ] Implement Q4_K_M dequantization
- [ ] Implement F16 dequantization
- [ ] Basic matmul (scalar, correctness over speed)
- [ ] LayerNorm, Softmax, SiLU

### Phase 3: Transformer
- [ ] Single transformer block forward pass
- [ ] Multi-block stack with shared embedding
- [ ] KV cache management
- [ ] Autoregressive generation loop

### Phase 4: Tokenizer
- [ ] BPE tokenizer implementation
- [ ] SentencePiece fallback (or require BPE-only models initially)

### Phase 5: Sampler + Integration
- [ ] Greedy/temperature/top-k/top-p sampling
- [ ] Full inference pipeline
- [ ] Compare outputs with llama.cpp for correctness

### Phase 6: Optimization
- [ ] SIMD matmul
- [ ] Block-sparse computation
- [ ] GPU offload via Vulkan/CUDA

## First Target

**QUANTA-LFM2.5-2.6Bv1-Q4_K_M.gguf** — 2.6B params, Q4_K_M quantized.

With this design, Quanta can load its own fine-tuned model natively, run inference, and use it for code generation — no external dependencies.

## Verification Plan

1. Load GGUF, print metadata (model name = "QUANTA-LFM2.5-2.6Bv1")
2. Decode first transformer block weights, compare with PyTorch reference
3. Run single forward pass on "Hello", compare logits with llama.cpp
4. Generate 10 tokens, compare text output with llama.cpp
5. Full benchmark: tokens/sec comparison

---

*Design review requested before implementation.*
