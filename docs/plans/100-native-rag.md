# 100% Native Quanta: Loader to RAG

**Status:** plan for review. No code written against it yet.
**Scope:** replace the entire Python/llama-server/sqlite3 RAG path with Quanta code,
from model loading through embedding, vector search, and generation.
**Non-goal:** speed. This is about removing every external dependency, in an order
where each layer is provable before the one above it exists.

---

## 1. What "100% native" means here

The RAG path today is three `exec()` calls in `lib/std/rag.quanta`:

| Step | Today | Native target |
|---|---|---|
| Embed a query | `python3` + sentence-transformers | Quanta: MiniLM forward pass |
| Vector search | `sqlite3` + the `vec0` C extension | Quanta: mmap + native scan/index |
| Generate an answer | `curl` → llama-server | Quanta: transformer forward pass |

Zero subprocesses, zero network, zero shared libraries. `strace` on a native
`rag_query` shows only `open`/`read`/`mmap` on the model and the database.

Python stays in the repo as an **oracle** — the thing we diff native output
against — and is deleted once each layer matches it. It is not on the runtime path.

---

## 2. Measured baseline

Everything below was measured, not assumed. This is the honest starting point.

### What exists

| Module | Lines | Fns | State |
|---|---|---|---|
| `lib/std/gguf.quanta` | 363 | 18 | metadata reader + Q4_K/Q6_K dequant + `matvec`, `rms_norm`, `softmax_arr`, `swiglu` |
| `lib/std/native_inference.quanta` | 566 | 20 | `tokenizer_load/encode/decode`, `transformer_load_weights`, `matmul_vec`, `rope`, `attention`, `quanta_infer`, `main` |
| `lib/std/linalg.quanta` | 372 | 25 | `mat_mul_f`, `mat_inv_f`, `vdot`, `vnorm`, `mat_transpose` — all f64 |
| `lib/std/ai.quanta` | 131 | 9 | `ai_test_matmul`, `ai_test_rmsnorm`, `ai_test_kv_cache`, `ai_test_quantize` |
| `src/x86/gguf_reader.quanta` | 224 | 9 | metadata only, no dequant, no compute |

### What actually compiles today

```
lib/std/gguf.quanta            -> error: no 'main' function found   (library, not a program)
lib/std/linalg.quanta          -> error: no 'main' function found   (library, not a program)
lib/std/ai.quanta              -> SIGILL, the COMPILER CRASHES (rc=132)
lib/std/native_inference.quanta-> SILENTLY PRODUCES NO BINARY
```

`native_inference.quanta` fails because it imports `std/mem`, which **does not
exist**. Nothing else has been reported, because nothing else compiles.

So the honest state: **there is no working native inference.** There is
substantial written work — a tokenizer, `rope`, `attention`, a full
`quanta_infer` entry point — and none of it has ever been executed. It is
plausible that most of it is wrong. Treat every line as unverified.

### Gaps, measured

| Gap | Evidence |
|---|---|
| **Three overlapping GGUF readers** | `lib/std/gguf.quanta`, `lib/std/native_inference.quanta`, `src/x86/gguf_reader.quanta` — three partial implementations of one format |
| **Dequant covers 2 of 16 dtypes** | implemented: Q4_K, Q6_K. declared: 16. Models on disk use Q4_0, Q5_K, Q8_0, F16, BF16 — **none implemented** |
| **No KV cache** | `kv_cache`, `k_cache`, `v_cache` all absent from `native_inference.quanta` |
| **No sampler** | `argmax`, `temperature`, `top_k`, `top_p` all absent. There is no way to pick a token |
| **No GPU** | the compiler emits no GPU code at all. Inference is CPU-only |
| **vec0 is a C extension** | cannot be called from Quanta. `sqlite3` is not on `PATH` |
| **`std/mem` missing** | `native_inference.quanta` cannot compile |
| **`ai.quanta` crashes the compiler** | SIGILL — an unknown construct in the language, not a bug in that file |
| **f64 only** | every numeric kernel in `linalg.quanta` is f64. Models are f32/bf16 |
| **2.8M stored vectors, 384 dims** | `vectors.db`, 21 GB, 2,862,440 rows, `vec0` + `vec_chunks` virtual tables |

### The models, and why the 2.6B

8 GB VRAM, 64 GB system RAM. From `/opt/tali/ti/ai/models/`:

| Model | Size | Verdict |
|---|---|---|
| `lfm2.5-2b6-Q4_K_M.gguf` | 1.6 GB | **the RAG generator.** Fits VRAM with room for KV |
| `lfm2.5-2b6.gguf` | 5.0 GB | f16, fits system RAM, too slow for interactive |
| `LFM2-24B-A2B-*.gguf` | 45–173 GB | **out of reach.** MoE, 24B params, streams from disk. Later |
| `all-MiniLM-L6-v2` | 90 MB | the embedder. Already in the HF cache |

Q4_K is the only K-quant that matters. It is also the only K-quant implemented —
so the target dtype and the implemented dtype coincide, by luck. That is the
reason to start here and not widen the dtype table first.

---

## 3. Architecture

Five layers. Each is provable alone, and each is useless alone.

```
  L5  RAG          query -> embed -> search -> prompt -> generate -> answer
  L4  Generation   tokenizer -> transformer -> logits -> sampler -> tokens
  L3  Model        GGUF parse -> dequant -> tensor arena -> matmul/rope/attention
  L2  Numeric      f32 primitives, matmul, rmsnorm, softmax, gelu/swiglu
  L1  Memory       mmap, arena allocator, tensor view, no-copy access
```

**L1 and L2 are prerequisites for everything.** The single largest risk in this
plan is that L2 has to be written in the language that `ai.quanta` cannot yet
compile. So L2 comes with a compiler capability audit, and that audit is Phase 0.

### Decisions

**One GGUF reader, not three.** Consolidate on `lib/std/gguf.quanta` — it has the
most complete dequant and the most compute primitives. The other two are deleted
once their unique capability is ported. Three partial readers means three
definitions of "tensor offset", and the loader is where an off-by-one becomes a
silent wrong answer instead of a crash.

**Tensor arena, not a copy per tensor.** A 2.6B Q4_K model is 1.6 GB. Reading
each tensor into its own allocation means 1.6 GB of copies plus 1.6 GB resident.
`mmap` the file, compute each tensor's absolute offset, and pass a
`(base, offset, n_elements, dtype)` view. Dequantisation writes into a
pre-allocated scratch buffer reused across layers.

**f32, not f64.** `linalg.quanta` is entirely f64. That is 2× the memory bandwidth
and no AVX F32 path. Every kernel added for inference is f32, and the f64
kernels stay for the compiler's own numeric use. This is a hard split, not a
preference.

**Vector search reads the database directly.** `vec0` is a SQLite C extension;
`sqlite3` is not even on `PATH` here. The path is: parse the SQLite file format
in Quanta (b-tree pages, the `chunks` table, the `embedding` BLOB column), then
scan or index natively. 2.8M × 384 × f32 = 4.1 GB of vectors. A linear scan is
4.1 GB of reads per query — correct, and too slow to be useful. So a native
index is required, not optional.

**The embedding model is the same problem as the LLM, smaller.** MiniLM-L6-v2 is
6 layers, 384 hidden, 22M params. It needs the identical L2 primitives. Build
once, use twice.

**CPU first, GPU when the CPU path is provably correct.** The CPU path is
verifiable against Python to the last bit. A GPU path verified only against
itself is a different bug hunt. GPU is Phase 7 and is additive, not a rewrite.

---

## 4. Build order

Phases are ordered by dependency and by verifiability. Each ends with something
that runs and is checked.

### Phase 0 — Unblock the language (prerequisite for everything)

`ai.quanta` crashes the compiler with SIGILL. Until that is understood, Phase 2
cannot be written, because we cannot tell a kernel bug from a codegen bug.

1. Reduce `ai.quanta` to the smallest input that still SIGILLs the compiler.
2. Fix it. If the construct is unsupported, either add it to the language or
   rewrite the kernel without it.
3. Create `std/mem` — `native_inference.quanta` already imports it.
4. **Gate:** every file in `lib/std` that imports only existing modules compiles.
   A 15th gate stage: "all lib/std modules compile".

### Phase 1 — Numeric core (f32)

`matmul_f32`, `rmsnorm_f32`, `softmax_f32`, `gelu_f32`, `silu_f32`, `add/mul/scale`
in f32, row-major with an explicit leading dimension.

**Gate:** each kernel matches a NumPy reference to 1e-6 relative on random input,
across batch sizes 1/2/8 and the shapes a real forward pass uses. A 16th gate
stage with the references checked in.

### Phase 2 — GGUF loader, consolidated

Merge the three readers. Add the dtypes the chosen model uses: Q4_K, Q6_K (have
them), then Q8_0, F16, BF16. Q4_0/Q5_0/Q6_0 only when a model needs them.

Tensor view (`base + offset + n + dtype`), no copies. Verify against a real
`Q4_K_M` file: parse the header, walk every tensor, and check that
`offset + size` for the last tensor equals the file size.

**Gate:** for `QUANTA-LFM2.5-2.6Bv1-Q4_K_M.gguf`, all tensor names, dtypes,
dims and offsets match a reference GGUF parser exactly.

### Phase 3 — Transformer forward pass, CPU

`quanta_infer` for real. Layer loop, attention with a **KV cache** (currently
absent), `rope`, the LFM2-specific architecture — note it is MoE at 24B and dense
at 2.6B, and the 2.6B path is the one we build.

**Gate:** logit-for-logit against the Python reference on a fixed prompt, to
1e-4. Same input, same weights, compare the full logit vector.

### Phase 4 — Sampler and text generation

`argmax`, `temperature`, `top_k`, `top_p`, seeded RNG. Greedy decode first, then
sampling. Bounded output length.

**Gate:** with greedy decode and a fixed seed, output is byte-identical to the
reference across 10 prompts.

### Phase 5 — Native embedding

MiniLM-L6-v2 through the same L1–L3 stack: tokenizer (already written in
`native_inference.quanta`, unverified), 6 encoder layers, mean pooling over the
attention mask, L2 normalise.

**Gate:** the 384-dim output matches the Python `SentenceTransformer` to 1e-5.
This gate is what makes the RAG database trustworthy — a different embedding
model means the 2.8M stored vectors are in a different space and every
distance is meaningless.

### Phase 6 — Native vector search

Read the SQLite file in Quanta: page structure, b-tree walk of the `chunks`
table, BLOB column extraction. Then a native index over 2.8M vectors.

**Gate:** a query returns the same top-k rows, in the same order, as
`vec_distance_euclidean` — on the existing database, not a rebuild.

### Phase 7 — GPU

The compiler emits no GPU code. This is a codegen feature, not a kernel change:
same L2 primitives, different backend. Start with matmul and elementwise, fall
back to CPU for anything unimplemented.

**Gate:** every CPU result is reproduced on GPU to 1e-4, and a full generation
is not slower than the CPU path.

### Phase 8 — Retire the interim path

`rag.quanta` loses its three `exec()` calls. `embed.python` leaves
`config/rag.conf`. The Python scripts stay as test oracles and stop being
reachable from the runtime.

**Gate:** `strace` on `rag_query` shows no `execve`. A new 17th gate stage
asserts it.

---

## 5. What has to be true at the end

- `rag_query("What is IR_CALL?")` in Quanta, no subprocess, no network.
- The answer matches what the Python pipeline produced for the same query.
- `grep -rn 'exec(' lib/std/rag.quanta` is empty.
- The 21 GB database is read natively, not shelled to.
- Every layer is checked against Python to a stated tolerance, and the check is
  in the gate so it cannot rot.

---

## 6. Risks, stated plainly

**The written work may be wrong.** `native_inference.quanta` has 566 lines of
tokenizer, `rope`, `attention` and `quanta_infer` that have never executed. The
plan above reuses it where it is right, but Phase 3 should assume a large
fraction needs rewriting. This is the main reason Phases 1–2 are gates rather
than milestones: the first real forward pass is where the true state becomes
visible.

**A compiler SIGILL could be deep.** Phase 0 is gated on a fix. If the construct
in `ai.quanta` turns out to need a language feature, that is a language change
with its own regression surface. It is first for that reason.

**f32 kernels on 8 GB.** The 2.6B Q4_K model at 1.6 GB plus a KV cache plus
activations is comfortable on the GPU and tight on CPU. The 24B is out of reach
regardless; it needs a MoE router and disk streaming, and is deliberately
excluded.

**SQLite from scratch.** Reading a b-tree correctly — including overflow pages
and the record format — is real work. It is tractable but it is not a
half-day task, and a subtly wrong b-tree walk returns wrong results rather than
failing.

**2.8M vectors must be regenerated if the embedder changes.** The stored
vectors were built by `all-MiniLM-L6-v2` at 384 dims (verified: a sampled blob is
1536 bytes). If native embedding matches that to 1e-5, the existing database
is reused as-is. If it does not, the 21 GB index has to be rebuilt — which is
why the Phase 5 tolerance is a gate and not a target.

---

## 7. Immediate next step

Phase 0. It is the only phase whose outcome is genuinely uncertain, and every
other phase depends on it. Specifically: reduce `ai.quanta`'s SIGILL to a minimal
reproducer, and add the `lib/std` compile gate so a module that cannot build is
caught before it is depended on.
