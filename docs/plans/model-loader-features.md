# Model Loader — feature survey and implementation plan

Scope decided with the maintainer: **full architecture** — loader + tokenizer + multi-model support — with the GPU load/unload path as a first-class requirement.

**Status: plan for review. Nothing here is implemented yet.**

---

## 0. What exists today (measured, not assumed)

| Property | Value | How measured |
|---|---|---|
| GGUF parse | 266 tensors, 37 KV pairs, data offset 8239136 | `gguf_load` on the real file |
| Dtypes read | 14 (F32/F16/BF16, Q4_0/Q4_1/Q5_0/Q5_1/Q8_0, Q2_K…Q8_K) | `gguf_dtype_supported` |
| This model's dtypes | F32=99, Q4_K=148, Q6_K=19, **unsupported=0** | tally over all 266 |
| Architectures | **1** (LFM2), via `layer_of`/`role_of` name patterns | `lib/std/lfm2_model.quanta` |
| Tokenizers | BPE (LFM2), SentencePiece | `lfm2_bpe`, `sp_tokenizer` |
| Host I/O | `lseek` + `read_raw`. **No mmap in the GGUF path** | `lib/std/gguf.quanta` |
| Language has mmap? | **Yes** — 57 uses of `mmap`, 5 `munmap` | `lib/std/*.quanta` |

The last row matters: mmap is missing from the *loader*, not from the language.

### Known gaps, each verified by reading upstream source

| Gap | Evidence |
|---|---|
| Alignment hardcoded to 32 | `gguf.quanta:236`; upstream reads `general.alignment` and rejects non-power-of-2 |
| **No offset-chain validation** | verified: the only mention of `offset` is a comment at `gguf.quanta:40`. Upstream `gguf.cpp:770` rejects any tensor whose offset ≠ running total |
| **No byte-size overflow guard** | upstream `gguf.cpp:723` checks representability before accumulating. Quanta *does* have per-dtype block-size math (`gguf.quanta:373,376`) — the gap is the overflow check around accumulation, not the sizes |
| No header-size cap / truncation check | ComfyUI caps safetensors header at 100 MB and checks `data_base_offset > file_size` |
| Sub-byte dtype model | `gguf_type_size` returns a byte count (`gguf.quanta:304`). GGUF quant types are largely fine via `(n/block)*size` block math — the real gap is GPTQ/AWQ/NF4/MLX 2-8 bit packing |
| ~~7 loader tests, 0 in the gate~~ **FIXED** | all 8 now registered; gating exposed `gguf_general_test`, which could never pass (asserted a relative offset against an absolute accessor) |
| ~~No offset-chain validation~~ **FIXED** | `gguf_validate_chain()`, wired into `gguf_load`, mutation-tested |
| ~~Unbounded reads~~ **FIXED** | both read entry points bound against tensor size and EOF |
| ~~No checked_mul~~ **FIXED** | `gguf_checked_mul` + dim/nelements agreement |
| ~~No header cap / truncation~~ **FIXED** | metadata caps + `n_kv`/`n_tensors` bounded; truncation segfaults without them |
| ~~Alignment hardcoded to 32~~ **FIXED** | `gguf_read_alignment()` reads `general.alignment`, rejects non-power-of-2 |

---

## 1. The central design decision

llama.cpp supports **139 architectures** by not writing 139 loaders. It defines a shared vocabulary:

- **241 canonical tensor roles** (`LLM_TENSOR_ATTN_NORM`, `LLM_TENSOR_FFN_GATE`, `ALTUP_ROUTER`, …)
- **207 hyperparameter keys** in one enum
- each arch is a thin declarative file binding its *filenames* onto those roles
- **5 tokenizer families** (SPM, BPE, WPM, UGM, RWKV), each with a pluggable pre-tokenizer

Quanta today has an LFM2-specific name-pattern matcher. **The plan must introduce the role vocabulary, with LFM2 as the first entry — not more LFM2 special-cases.**

Proof this is necessary, from a model already on this box:

```
model.language_model.layers.0.linear_attn.A_log     [F32, shape (16,)]
model.language_model.layers.0.linear_attn.norm.weight
model.visual.merger.linear_fc1.weight
```

`qwen3.5-2b` is a hybrid linear-attention vision-language model. No LFM2-shaped pattern survives it.

### Local test corpus — 5 architectures, already downloaded

| Model | Arch | Shards | dtypes |
|---|---|---|---|
| qwen2.5-1.5b / 3b | Qwen2 | 1 / 2 | — |
| qwen3.5-0b8 / 2b / 4b | Qwen3.5 (hybrid VLM) | 1 / 1 / 2 | BF16×596, F32×36 |
| gemma-4b-e2b / e4b | Gemma-3 | 1 | — |
| gemma-4-E4B-it | Gemma-4 | 2 | — |
| Spark-X2.5-1.7B / 4B | Spark | 2 / 5 | — |

**All unquantized** — so they double as numeric oracles. A Qwen2 loader and a Gemma loader matching BF16 originals is the real proof of generality. LFM2 alone proves nothing of the kind.

Measured safetensors header (qwen3.5-2b): 632 tensors, **76,648-byte JSON header**, data at offset 76,656. qwen3.5-4b: 738 tensors across 2 shards, `total_size` 9,319,737,856.

---

## 2. Best-of-best feature list

### From llama.cpp (read from on-box source)
- canonical role vocabulary + per-arch declarative binding
- offset-chain validation; power-of-2 alignment check; byte-size representability guard
- `nbytes_remain` bounding every read against remaining file size
- alignment honored from `general.alignment`, not hardcoded
- per-tensor buffer-type selection (`select_weight_buft`) so a tensor can live on CPU or GPU

### From safetensors / ONNX Runtime / PyTorch
- **`Metadata::validate()`** — lift nearly verbatim: contiguity check (`s != start`) makes holes/overlaps/polyglots structurally impossible; every dimension product `checked_mul`; `e - s == nelements × bitsize/8`
- 100 MB header cap; external-data path containment
- **mapping lifetime == tensor lifetime** (ORT moves the unmap deleter into the tensor destructor)
- unaligned-offset mmap: map from `offset - (offset % page_size)`, return `base + remainder`
- `MAP_PRIVATE` (COW) — weights immutable without `mprotect`
- **CUDA host staging bounded at 128 MiB via two alternating 64 MiB pinned buffers**
- ⚠️ **safetensors is NOT zero-copy on the Python path** (`get_tensor` copies via `PyByteArray::new`). Zero-copy is real only at the Rust core.
- ⚠️ **`Dtype::size()` is deprecated and wrong for sub-byte types** — `bitsize()/8` truncates; F4 and MXF6 report wrong sizes; sub-byte ⇒ `MisalignedSlice`

### From TensorRT-LLM
- **`ConsumableWeightsDict`**: `mark_consumed(prefix)` frees tensors after copy, so peak host RAM never holds checkpoint + model
  - **the non-obvious part**: a renamed/filtered mapping holds a *second* reference, so consuming the alias frees nothing — `take_ownership` empties the source
- sorted key index + binary search for prefix lookup; stale index is a safe superset
- meta-init on device before reading any weight bytes; bidirectional `memo` so tied params share one allocation
- three-phase contract: **translate → load-and-shard → postprocess**, with one-to-many (`qkv` → q/k/v) and many-to-one (`qweight`+`qzeros`+`scales` → `weight`) mappings
- repack-on-load with sentinel padding: pad scale slots with **`0x08`** (smallest normal E4M3), never 0
- transforms must run **inside** any sharing boundary, or zero-copy peers get stale bytes

### From SGLang
- `should_skip_weight` drops **non-local experts before the page-cache read** — ~85-90% of a MoE checkpoint
- rank-cooperative prefetch `sorted_files[local_rank::local_world_size]`; node-local rank deliberately (page cache isn't shared across nodes)
- `posix_fadvise(DONTNEED)` after load
- **online quantization at load** — support a quantized format you never pre-converted
- `restore_weights_before_loading` — inverse of in-place packing, or reload is impossible

### From vLLM
- shard index is authoritative: raise for files it names but that are missing; ignore files it doesn't name
- filenames **natural-sorted numerically**, not lexicographically
- `WeightsMapper`: ordered rule kinds; `None` = early-return drop; per-arch is one class attribute
- ⚠️ **the default loader is rank-blind** — every TP worker reads every shard, narrowing its own slice. Not parallel I/O.
- missing-weight strictness on by default **only for non-quantized**, with an enumerated exception list
- unknown checkpoint keys are a hard error listing available params

### From ollama (read from source, clone `d3c846f`)
- content-addressed blobs, path construction `manifest/paths.go:397` `BlobsPath(digest)`:
  `filepath.Join(envconfig.Models(), "blobs", digest)` with `":"` → `"-"` (line 405)
- the empty digest names the **blobs directory itself** (lines 398–410) — one resolver serves both
- `digestPattern` (line 30) accepts **both** `sha256:<hex>` and `sha256-<hex>`; `ValidateDigest`
  enforces exactly 64 hex digits, so no prefix truncation and no traversal through a digest
- dedup is a side effect of **`NewLayer` hashing into a temp file** (`manifest/layer.go:40–70`):
  stream → `sha256.New()` while writing to `os.CreateTemp(blobs, "sha256-")`; publish is
  `os.Rename` to the canonical name only if `os.Stat(blob)` fails. Dedup falls out of "content
  already exists at its own address" — there is no lookup step.
- verified, correcting the earlier research note: ollama **GCs by manifest reachability**, and
  `manifest/manifest.go` walks layer digests rather than scanning blobs for liveness
- split GGUF (`llm/model_split.go`): independent self-describing blobs reconciled at load
- ⚠️ its split mechanism is a **filesystem workaround, not a loader feature**: hard links under
  `.ollama-split-<digest12>-<random>/` exist only because llama-server auto-discovers shards by
  canonical filename and has "no CLI option for passing shard paths explicitly" (comment lines
  20–23). `maxSplitModelFiles = 99999` mirrors llama.cpp's five-digit count field.
  → Adopt the *validation*, not the hardlink dance. A split reprinted under canonical names is
  a symlink unmanageable in the general case; the useful part is reconciling shards (count,
  unique `split.no`, matching arch/filetype, summed tensor count, no duplicate tensor names).

### From MLX
- `mx.load` returns **lazy graph nodes**, not data — files stay on disk until eval
- ⚠️ **MLX does not mmap at all** — `pread` into fresh buffers, 32 MiB batches on a *shared* pool (a per-file pool "multiplies the reads in flight by the number of open files")
- quant mode inferred from tensor geometry; modules replaced **before** weights assigned
- `ModelArgs.from_dict` silently drops unknown config keys — forward-compatible by construction
- ⚠️ **GGUF is write-only in mlx-lm**

### From ComfyUI (read from on-box source)
- eviction sorted by **offloaded memory descending**, not LRU — evict what returns the most VRAM per swap
- `partially_load` / `partially_unload`: a model never fully occupies VRAM unless it must
- zero-copy safetensors: mmap + `memoryview((ctypes.c_uint8 * n).from_address(...))`, tensors are *slices*
- **dual-stream async offload** (`--async-offload`, default 2 streams on NVIDIA/AMD): per-stream cast buffers, round-robin, `wait_stream` handshake in both directions
  - **subtle**: if one weight is the largest, the *other* stream deliberately returns `None` — both streams must not allocate for a giant weight
- pinned-memory budget tracked as a scarce resource (`ensure_pin_budget`)
- **ComfyUI-GGUF is a third independent dequant oracle on disk**, covering 13 types including IQ4_NL and IQ4_XS. NOTE: Quanta already supports both — an earlier draft of this doc wrongly said otherwise, caught by re-reading the source before commit. Quanta's comment records that IQ4_NL/IQ2_S/IQ4_XS previously carried wrong block numbers and overran real IQ4 GGUF files by 2.50 GB and 2.87 GB, silently reading unrelated bytes as weights

### From Colibrì (pure C, single file, 744B on a 25 GB laptop)
- **placement only ever decides speed — never semantics.** The router's decisions and weight precision are identical whether an expert came from VRAM or disk. Quanta's LFM2 work already lives by this rule.
- **batch-union**: a batched position reads each unique expert once
- **one-layer-ahead router lookahead** — routing measured **71.6% predictable** one layer ahead
- **adjacent matrix layout**: each expert's three matrices stored adjacent, read in one `pread`
- `O_DIRECT` **+34% decode** measured — but drive-dependent, neutral-to-negative on QLC
- ⚠️ **int4 MTP head collapses speculative acceptance to 0-4%**; int8 required
- ⚠️ **per-row int4 vs gs64 measured ~9pp worse on quality**

### From MLX / diffusers group quantization
- MLX affine = **3 arrays** (packed uint32 + scales + biases), group ∈ {32,64,128}, bits ∈ {2,3,4,5,6,8}; 3/5/6-bit need boundary-straddling shuffles
- MLC: **`parameter_schema_id`** = hash of (name, shape, dtype) per param, verified at load
- MLC `linear_weight_layout ∈ {KN, NK}` — TP sharding legality enforced against layout

### Quantization byte layouts (verified against clones, 717-line reference)
- **GPTQ**: `qweight` packs 32/bits consecutive *input* columns per int32, LSB-first per output row; `qzeros` is transposed and **stores zero−1**, `+1` restored at read; `g_idx` maps permuted column → scale row
- **AWQ**: 4-bit only; three sequential reshape/transpose permutations then 4-nibble int16 packing, `interleave=4`, `kstride=64`; **zero-points are not stored** — dequant *adds* `scaled_zeros = -(scale*zero)`
- **NF4**: 16-entry codebook (values in the reference); block 64, no zero-point, no permutation; **even element in the high nibble**; double-quant blocks of 256 with a dynamic 8-bit code plus a mean offset
- **MXFP4/MXFP8**: block 32 + E8M0 shared exponent. **NVFP4**: block 16, scale byte is E4M3, global fp32 scale, `S_enc = 2688/global_scale`
- **EXL2**: per-group bit count in `q_groups` as interleaved int16 — `[2g]`=bit count, `[2g+1]`=packed row offset (back-filled during packing)
- ⚠️ **GPTQ act-order stores no `perm`** — original column order is *not recoverable from the file*; loaders apply `g_idx` for scale lookup only
- ⚠️ **EXL2-era trellis does not exist.** exllamav2 0.3.2 has no trellis; `pack_columns` dispatches only fixed rates 2-8. EXL3's layout was documented instead.

---

## 3. GPU load/unload — measured on this machine

Benchmarks run on the actual RTX 4070 Laptop (7.70 GiB, **PCIe Gen4 ×8**, CUDA 13.3/13.4). Reproducible sources in the preserved report.

| 4 GiB model, 8 GB card | Time |
|---|---|
| Load RAM→VRAM (pinned async, 64 MiB chunks) | **0.358 s @ 12.00 GB/s** |
| Unload (`cudaFree`) | **0.0058 s** |
| Full cycle | 0.364 s — **copy is 98.4%** |

**Load is purely PCIe-bound.** 1/2/3/4 streams all gave exactly 12.01 GB/s. **Load time = bytes ÷ link width.** Only partial loading or a faster link changes it — this kills the entire "parallelize the load" family before it starts.

### Findings that contradict standard advice

| Claim | Reality on this box |
|---|---|
| "mmap + `cudaHostRegister` for zero-copy" | **fails** — `cudaErrorInvalidValue`. Pin anonymous staging instead |
| "double buffering speeds load" | **+0.2%** — `cudaMemcpyAsync` already overlaps the host `memcpy` |
| "pinned is 2× faster" | **1.08-1.16×**, and **exactly 1.0× below 16 MiB**. Chunk size matters more |
| "mmap is the fast path" | **worst**: 2.446 s per 4 GiB vs 0.467 s for `pread` |

### Mechanisms worth building on

- **`MADV_POPULATE_READ`** prefaults 4 GiB in **0.057 s** (75.7 GB/s) — no cold-mmap penalty
- **on-load repacking is free**: fused Q4→FP16 load **0.179 s** vs load-then-unpack **0.358 s** (50% saved). Device bandwidth 247 GB/s is 20× the link, so any single-touch transform hides behind the wire
- **`cudaMemPoolAttrReleaseThreshold` ≥ model size → reload is a 0.0000 s pointer bump at the identical VA**. `cudaMemPoolTrimTo` costs 0.079 s
- VMM (`cuMemCreate`/`cuMemMap`/`cuMemSetAccess`) ≈ 0.1 ms for 512 MiB → reserve-once/map-many, VA aliasing
- `cudaMemGetInfo` counts other tenants — **wrong number on a shared card**; use `cudaMemPoolGetAttribute`

### ⚠️ Hardware caveat

**This card negotiates Gen4 ×8, not ×16, and `nvidia-smi` reports it without error.** Any design sized against x16 numbers is **2× optimistic** on this machine.

### Diffusion-specific

- Wan2.1's `feat_cache`/`CACHE_T=2` decodes the VAE **one latent frame at a time** — a stronger analogue of tiling, specific to video
- Wan2.2: per-timestep high/low-noise model swap with device guards
- HunyuanVideo: diffusers sequential CPU offload; VAE tiling on by default
- LTX: hard `< 30 GB` gate. Mochi **explicitly declines**: "~60GB VRAM… prioritizes flexibility over memory efficiency"
- ⚠️ **Wan has zero `block_swap`/`stream_load`/`preemption`** — 0 hits. Do not design around those names.
- **diffusers `apply_group_offloading`** (`BLOCK_LEVEL`/`LEAF_LEVEL`, `use_stream`) is genuine async CUDA-stream block swap, **uncalled by any of the five video repos** — and ComfyUI's equivalent (`--async-offload`) is on-box. This is the layer an 8 GB runtime needs for a 14B video DiT.

### Corrections to earlier assumptions in this session

- **A1111 has no `VRAMState`, no low/med switching thresholds, no OOM detector.** `VRAMState` is InvokeAI. A1111 has manual `--medvram`/`--lowvram` flags and one global slot; `MemUsageMonitor` is display telemetry.
- accelerate's class is **`AlignDevicesHook`**, not `AlignmentEnum`.

---

## 4. Implementation plan

Ordered by dependency, not by excitement. Each phase has a verification that can fail.

### Phase 0 — Gate the loader ✅ DONE

Seven tests exercised the loader with **none in the gate**. All seven are now registered in `EXPECTED_STDLIB.tsv`, plus a new eighth for the validator. STDLIB 66 → **75/75**.

Gating immediately found a real failure that had been sitting in the tree: `gguf_general_test` asserted `gguf_tensor_offset(0) == 0` while the accessor returns an **absolute** offset (8239136). It could never pass and had been sitting there looking fine. Fixed to assert absolute values.

That fix was then found to be *too weak* by mutation: it compared `offset - data_start`, which cancels out a change to how the offset is composed, so it passed even with the accessor returning a relative value. Now asserts the absolute constants directly and fails under that mutation.

Mutation-verified:
- Q6_K f16 scale read broken → `embedding_test` rc=1
- `gguf_tensor_offset` absolute→relative → `embedding_test` rc=1, `gguf_general_test` rc=1

Lesson recorded in the plan: **a test that has never run is not a test.**

### Phase 1 — Validation and safety (correctness before features) ✅ COMPLETE

Ported `Metadata::validate()` semantics; every item below has an upstream precedent.

**Done:**
- `gguf_validate_chain()` — offset-chain validation with a representability/bounds guard, wired into `gguf_load` (rc -6 on failure)
- `gguf_read_alignment()` — reads `general.alignment`, rejects non-power-of-2, defaults to 32
- `gguf_filesize` captured at load and used to bound every tensor against EOF
- `stdlib_gguf_validate_test` — 4 corruptions (gap, overlap, absurd nelements, tail shift) all detected, 0 missed, restoration exact

**The anchoring subtlety, measured not assumed:** the chain's running total must start at `gguf_data_start`, **not 0**. `gguf_tensor_offset()` already adds `gguf_data_offset()` internally (gguf.quanta:373) and returns an absolute offset. Measured on the real model: tensor 0 sits at absolute 8239136 with relative 0, and every later tensor chains exactly. A validator anchored at 0 reported a spurious 8239136-byte gap at tensor 0 and **rejected the real, valid model** — which is what the first version did.

**Also done:**
- `gguf_read_tensor_bytes_at()` and `gguf_read_tensor_bytes()` now bound every read against the tensor's own size and against EOF (the `nbytes_remain` guard). **Return contract preserved** — a byte count on success — because `lfm2_mm.quanta:87` depends on it.
- `gguf_checked_mul()` + `gguf_validate_dims()` + `gguf_validate_all_dims()`, wired into `gguf_load` (rc -7). Covers both an overflowing dim product and dims that disagree with the stored nelements.
- Metadata caps: `GGUF_MAX_META` (256 MB), `GGUF_MAX_STRING` (64 MB), short-read detection on the key length, and `n_kv`/`n_tensors` bounded against the file size (rc -8).

**What the guards actually prevent — measured:** removing the three metadata guards makes a truncated file **segfault (rc=139)** rather than being rejected. The guards turn a crash into a clean rejection.

**Mutation results (6 mutations):**
| mutation | result |
|---|---|
| M1 delete `t > GGUF_MAX_ELEMENTS` | caught |
| M2 remove read bounds in `read_tensor_bytes_at` | caught |
| M3 remove metadata string cap | caught |
| M4 remove dim/nelements agreement | caught |
| M5 remove all metadata guards | caught (segfault) |
| M6 remove `n_kv` bound | **not caught** — defence in depth, covered by the other guards |

Two mutations initially survived and both were fixed by *changing the test*, not the code:
- **M1**: the obvious case `4e18 * 4e18` wraps *negative*, so the `t <= 0` guard catches it too and the test passed with the limit check deleted. The value that isolates the limit guard is `1e9 * 1e9 = 1e18` (positive, > limit). Added.
- **M3**: the `read_raw(...) != 8` short-read guard fired first and masked the `klen` bounds, so deleting those still looked detected. Split into a separate file-based test (`stdlib_gguf_truncated_test`) that cuts the real model mid-record and exactly on a record boundary; deleting the bounds then segfaults.

**Byte-level corrupt-file generator — DONE.**
`scripts/audit/gen_corrupt_gguf.py` produces real corrupt files by patching one 8-byte field at a known offset, and `test_suites/scripts/gguf_corrupt_gate.sh` runs them through the real loader as a permanent gate (summarised in run_tests.sh as `gguf-corrupt`).

Seven corruptions, all rejected at rc=-6, with the real model still loading:
`gap`, `overlap`, `tail`, `dim_overflow`, `dim_mismatch`, `huge_dtype`, `neg_offset`.

**The design point:** the generator never parses the KV block. It takes the tensor-table offset from Quanta's own verified parser — a new `gguf_tinfo_start` recorded by `read_tensor_info()` — and walks only the fixed tensor-record layout. This exists because two hand-rolled Python GGUF readers failed earlier (both desynced on `general.base_model.0.name`), and a third attempt to fix one failed the same way. Asking the verified parser removed the failure mode instead of debugging it again.

Every derived offset is checked against Quanta's own parsed tensor offsets (t0=0, t5=245506048, t6=245514240, t7=257900544, dtype 14, dim0 2048) **before a byte is written**, and the generator refuses on mismatch — verified to correctly reject a deliberately wrong `tinfo_start`. A bug in the walk cannot silently corrupt an unrelated region of a 1.6 GB file.

Discrimination: with `gguf_validate_chain()` and `gguf_validate_all_dims()` stubbed to `0`, the gate reports **0/7 rejected, FAILED (7)** and rc=1. With them on, 7/7 and rc=0.

**Phase 1 complete.**

### Phase 2 — Bit-width dtype model ✅ COMPLETE

Prerequisite for the HF quantization formats (GPTQ/AWQ/NF4/MLX), which pack 2-8 bits per element. GGUF quant types are *mostly* already correct via block math — this phase targets the formats needing genuine sub-byte addressing, it is not a fix to GGUF.

- dtype = `{bits, block_size}`; `type_size()` → bit offset, not byte count
- keep `gguf_type_size` working — the 14 GGUF dtypes are believed bit-correct, but verify rather than assume
- add 3/5/6-bit paths (MLX `extract_bits` boundary-straddling shuffle)
- gate: existing 14 dtypes bit-identical after the change

### Phase 3 — safetensors reader + shard index ✅ COMPLETE

Because **that is where models actually ship**, and GGUF is the legacy path.

- header parse (u64 length + JSON), `data_offsets` relative to data section
- validate: contiguity, `checked_mul`, `e - s == nelements × bitsize/8`, 100 MB cap
- shard index: authoritative missing-file check, ignore unnamed files, **natural numeric sort**
- 13 local models as fixtures

### Phase 4 — Role vocabulary + arch registry ✅ COMPLETE

The generalization. Without this, every new model is a new special case.

- canonical role enum (start from llama.cpp's 241, adopt what applies)
- hparam enum (from the 207 keys)
- `arch_registry`: arch id → name patterns → roles + hparam reader + graph builder
- **port LFM2 onto it** and prove all existing LFM2 tests still pass unchanged
- then **Qwen2** as the second arch, validated against the local BF16 model
- then Gemma-3

The LFM2 port is the proof the abstraction works. If LFM2 needs special cases, the design is wrong — stop and fix it there.

### Phase 5 — Tensor-role → compute mapping ✅ COMPLETE

Not `role → function pointer` directly. Each role names a **tensor kind**: `[rows, cols]` matrix, `[n]` vector, per-layer state, or router indices.

- `mm_matvec` / `mm_matvec_t` (transposed) / elementwise / state update
- transposition must be explicit and cheap; roles declare which form they store
- llama.cpp's `get_tp_alignment` equivalent: declare alignment (group_size) per tensor kind

### Phase 6 — Loader traits

So callers write `if loader.has(load_weight_only)` and never branch on format name.

- `load_header`, `list_tensors`, `find_tensor`, `tensor_nbytes`, `read_tensor_bytes`, `dequantize_tensor`, `is_quantized`, `has`

### Phase 7 — GPU residency, load/unload at speed

Driven by the measurements, not by folklore.

1. mmap the model file; `MADV_POPULATE_READ` in windows (0.057 s per 4 GiB)
2. pinned anonymous staging in 64 MiB chunks (file-backed pinning **fails** on this driver)
3. **`cudaMemcpyAsync` on a dedicated stream, round-robin pool with a `wait_stream` handshake** — ComfyUI's design, including the "one stream owns the giant weight" rule
4. per-stream cast buffers, reused and resized
5. **fused dequant-on-load** in the copy kernel (50% saving, measured)
6. `cudaMemPoolAttrReleaseThreshold` for constant-VA reload
7. **do not** implement double buffering (+0.2%), **do not** attempt file-backed `cudaHostRegister` (fails)

#### Phase 7a — Threading the CPU matvec (prerequisite, measured)

The forward pass currently runs at **~90 s/token** (2.6B Q4_K_M, 20-core box). Profiled, not
guessed — per-phase in-program timestamps:

| phase | time |
|---|---|
| embedding lookup | 0.00 s |
| one conv layer (22 of 30 layers) | 3.47 s |
| one attn layer (8 of 30) | 3.21 s |
| output projection (128000x2048) | 12.80 s |

Within a 2048x2048 Q4_K matvec: **dequant 93 ms, dot 69 ms** — dequantization dominates.

**Micro-optimisation of this loop is exhausted.** Measured, all four variants:

| variant | dequant |
|---|---|
| direct `fmul`/`fsub` with `idiv` | 129 ms |
| shift/mask instead of `idiv` | **93 ms (1.39x, kept)** |
| merged nibble passes | 98 ms (noise) |
| precomputed 16-entry table | 101 ms (slower, reverted) |

The reason nothing else helps: **`-O` is a verified no-op** (byte-identical binaries with and
without it — md5 `5fab7144…` both ways). There is no register allocation, so every variable read
is a frame load no matter how the expression is arranged.

⚠️ **The remaining lever is parallelism: 20 cores, currently 1.** That is ~10x, not 1.4x.

**Constraints on doing it safely** (this is why it is a phase, not an edit):
- The matvec path uses **module-global scratch** (`mm_rowbuf`, `mm_rowraw`, `fc_sc_*`, `fc_at_*`,
  `fc_fw_*`). Those are a data race by construction. Each worker needs its own buffers, or the
  work must be partitioned so no two threads share one.
- A race here **silently corrupts numbers that currently verify exactly against llama.cpp**. A
  wrong answer is worse than a slow one.
- Required invariant, same as Phase 8: **thread count must not change the result.** Enforced by
  running 1/2/4/20 threads and comparing logits bit-for-bit — the existing
  `fc_forward_token` vs llama.cpp oracle already provides the reference.
- Quanta has the primitives: `fnptr(FNAME)` (code pointer), `syscall()` (so `clone`), `clock()`
  (CLOCK_MONOTONIC ns for timing). Verify each with a small probe before building on it.

Order: partition first (per-thread scratch), then measure scaling, then keep only what scales.

### Phase 8 — Partial load / block swap

- `load_partial(model, budget)` returning a handle that can grow
- eviction by **offloaded-memory descending**, not LRU
- batch-union: a batched position reads each unique tensor once
- one-layer-ahead prefetch where a router makes that predictable (Colibrì measured 71.6%)
- adjacent-matrix layout so one `pread` serves a whole group

**Invariant: partial load and full load must produce identical numbers.** Enforced by a test that runs both and compares bit-for-bit. This is the Colibrì "placement only decides speed" rule, and it is the same discipline already applied to the KV cache and RoPE.

### Phase 8b — MoE expert offload (the mechanism for "larger models" on 8 GB)

This is the concrete answer to "support larger models" on a single 8 GB card. A dense model larger
than VRAM is hopeless here; an **MoE** is not, because only a few experts are active per token.
Keep attention and the router dense on GPU, stream experts from host RAM (62 GB on this box).

Source: `exllamav3_ext/cpu/moe_handoff.h` (clone `151539c`). Its design, stated in the header:

- A **persistent worker child process** consumes a job ring. It is not spawned per forward pass.
- **Pinned shared memory** allocated and `cudaHostRegister`ed by the parent, plain-mapped by the
  child. All offsets are byte offsets from a region base.
- Control block: `quit`, `pass_wake` (parent bumps at the start of every forward pass; child spins
  hard), `abort` (set by the GPU wait kernel on timeout, checked by the parent per pass), `ready`
  (child → parent: loop entered, layers loaded), `jobs_tail`/`jobs_head` (producer/consumer).
- Per-slot sequence numbers, **three of them**: `data_ready[]` (GPU publishes job seq), `done[]`
  (child finished writing), `consumed[]` (the collecting device's stream published after reading
  the slot back). ⚠️ **Slot reuse waits on `consumed`, not `done`.** The header spells out why:
  with offloaded layers spread over several GPUs the next tenant's issue runs on a different
  stream than the previous tenant's readback, so `done` alone lets the child overwrite the output
  while the readback is still queued on the other device.
- Per-slot payload: `[x fp16 cap_rows*Hi][sel i32 cap_rows*topk][w fp16 cap_rows*topk]`.

**What this means for Quanta, honestly:** the mechanism is CUDA+shared-memory+process-handoff, so
none of it ports directly to a single-GPU CPU implementation. What *does* carry over is the
**design**: pinned staging, a bounded job ring, and a three-state slot protocol. Quanta's own
version would be single-process (worker threads via `clone`, or a pread pool), with the same
invariant as Phase 8 — **placement decides speed, never semantics** — enforced by the same
bit-for-bit test.

⚠️ Do not attempt this before Phase 7/8 exist and the forward pass is fast enough to measure. An
offloaded MoE at the current ~90 s/token is unusable regardless of how well it fits.

### Phase 9 — Formats beyond GGUF/safetensors

Prioritized by what actually ships:

1. **MLX affine** (3 arrays, 2-8 bit) — simple, well-documented
2. **NF4 + double-quant** — very widely deployed
3. **GPTQ** — note `qzeros` stores zero−1, and act-order `perm` is unrecoverable
4. **AWQ** — note zero-points are *not stored*; dequant adds
5. **MXFP4 / NVFP4** — block 32 E8M0 / block 16 E4M3 + global scale
6. **IQ4_NL / IQ4_XS** — ComfyUI-GGUF already has working reference code on-box
7. **EXL3 (trellis)** — see below. Corrects an earlier note in this plan that said "EXL2: no
   trellis exists". **EXL3 *is* the trellis format**, and it is what actually ships for large
   models. EXL2 is the older per-group-bit-count scheme.

Each new format: implement, then validate against the on-box independent implementations (ComfyUI-GGUF, the preserved Python references) before claiming support.

**EXL3 trellis — format notes** (read from `exllamav3` clone `151539c`; note that Kyojin is a
*fork* of exllamav3 for AMD Strix Halo/gfx1151 and its additions are `USE_ROCM`-guarded, so the
fork itself is not portable to this box — the upstream engine is the part worth reading):

- **Different in kind from GGUF.** GGUF K-quants are per-256-block affine (`d * q - m`); EXL3
  applies a **Hadamard rotation** to each 256-wide group and then a **trellis codebook** over the
  whole group, so error is spread across the group rather than independent per element. That is
  why it reaches usable quality at 1.5–2.0 bpw where GGUF cannot.
- Three codebooks: `mul1` (default), `mcg`, `3inst`. `mul1` is required by the int8 GEMV and
  CPU-expert-offload paths.
- Bitrate is **fractional**: integer part plus a `half` flag (a 0.5 bpw step). Packed size is
  `16*K + (HALF ? 8 : 0)` uint16 per tile — see `exllamav3_ext/quant/exl3_kernel_map.cuh`.
- Weights are stored as `uint16_t` tiles; `reconstruct.cu` is the reference decode and
  `exl3_gemv.cu` / `exl3_gemm.cu` are the GEMV/GEMM paths.
- The embedding table can itself be quantized (`-eb`, 1–8 bpw, or 16 = unquantized) and **streamed
  from disk or held in system RAM**, decoded on GPU at inference (`--embed_disk`).
- ⚠️ **There is no CPU reference implementation in-tree.** `exllamav3_ext/cpu/` contains only MoE
  handoff/mul helpers; every EXL3 decode kernel is CUDA (`*.cu`) with RDNA variants under
  `rocm/`. Porting to Quanta means transcribing the trellis decode from the CUDA kernels, which is
  a project, not a copy.
- ⚠️ **Not bit-reproducible by design in one respect:** greedy output under speculative decoding is
  *not* token-identical to plain decode, because near-tied logits can flip under batched verify
  (stated in the Kyojin README). Do not write a bit-equality test across those two paths.

**Layout references mined from unsloth source** (clone `660bcba`; it is a *trainer*, not a loader —
`FastLanguageModel.from_pretrained` delegates to HF, and llama.cpp is used only for GGUF export, so
there is no loader code to port here — but two kernels document byte layouts precisely):

- `unsloth/kernels/nf4_gemv.py` — batch-1 NF4 GEMV fusing nested absmax decode + NF4 lookup + dot
  into one launch. Two facts worth keeping: each weight row must start a new quantization block
  (`K % blocksize == 0`), and block sums are accumulated *before* scaling, so the result matches
  bitsandbytes to fp32 accumulation noise — **not bitwise**. Do not write a bit-equality test against
  bitsandbytes for NF4.
- `unsloth/kernels/int4_packed.py` — `compressed-tensors` `pack-quantized` layout, stated exactly:
  `weight_packed` is int32 `[N, ceil(K/pf)]` with `pf = 32 // bits` values per word, element `j` in
  bits `[j*bits, (j+1)*bits)`, stored as `q + 2**(bits-1)`. `weight_scale` is `[N, G]`; an asymmetric
  `weight_zero_point` is packed the same way along the **output** dim `[ceil(N/pf), G]`; act-order
  checkpoints carry `weight_g_idx` `[K]` (column → group). Decode `(q - zp) * scale` is exact in fp32,
  then rounded like compressed-tensors (scale dtype, then output).

### Phase 10 — Tokenizers as a family

Currently BPE + SPM, both arch-specific. Target the 5 llama.cpp families behind one trait:

- shared: `tokenize`, `detokenize`, `vocab_size`, `token_to_id`, `id_to_token`
- per-family: pre-tokenizer + merge/vocab table construction
- `trust_remote_code` equivalent — default **off**

---

## 4b. Beyond the loader — finetune, agent (measured state)

The loader is a means, not the end. The target is that Quanta can load, run, **finetune**, and host
an **agent** on a model. That is a larger scope, and this section records what is actually true
today so the build order is decided by evidence rather than by what the tree claims.

**Audit, `lib/std/` on 0.0.225:**

| Measure | Count |
|---|---|
| Files in `lib/std/` | 9,388 |
| Auto-generated stubs (`// Auto-generated stub`) | **8,817** |
| Real implementations (>60 lines, no stub marker) | ~24 |

The ~24 real files are the crypto/TLS/GGUF/LFM2/JSON ones (`gguf.quanta` 2,456 lines,
`lfm2_forward.quanta` 694, `json.quanta` 411, …). Everything else is a generated shell:

```
// Auto-generated by SI_0.0.002 Pattern Library
// Status: ✅ done
// Stdlib: `ai.quanta`
// Notes: SGD/Adam
module programming_language_dl_optimizer;
fn init() -> i64 { return 0; }        // Auto-generated stub
fn validate() -> i64 { return 0; }
```

⚠️ **Those files claim `Status: ✅ done` and contain no implementation.** By the project's own rule
(`X` means not fixed) they are not done. This is a documentation defect that will mislead any roadmap
built on it — a generator wrote a completion marker instead of code. The AI-domain files are the
worst case because they are the ones this section depends on.

**What genuinely exists, and what does not:**

| Capability | State |
|---|---|
| GGUF read + validate | ✅ real (`gguf.quanta`, hardened, mutation-tested) |
| safetensors read + validate | ✅ real (`safetensors.quanta`) |
| Role vocabulary + arch registry | ✅ real (Phase 4) |
| Role → compute dispatch | ✅ real (Phase 5) |
| LFM2 layers (attn, conv, rope, mm, BPE, pretok) | ✅ real, each with a passing test |
| **LFM2 token generation entry point** | ❌ **absent** — no `generate` / `sample` / `argmax` anywhere |
| Autograd / backward | ❌ absent from `lib/` and `compiler/` |
| Optimizer (SGD/Adam) | ❌ stub only |
| HTTP / socket stack | ❌ stub only (websocket files are generated) |
| Agent / tool-calling layer | ❌ absent |

**Build order (each step depends on the one above it):**

1. **One real token out of LFM2.** `generate` → `sample`/`argmax` over the existing pieces. Nothing
   downstream is testable until this produces a token, so it is first.
2. **Phases 6–10 of this loader** (traits, GPU residency, partial load, formats, tokenizer family).
3. **Autograd + optimizer as a real `ai.quanta`** — replacing the stubs that currently claim done.
   A finetuner needs backward through the arch graph; the arch registry from Phase 4 is what makes
   that expressible once instead of per-model.
4. **Agent layer** — HTTP/tool-calling. unsloth's `unsloth start hermes` is the reference for how an
   agent consumes a locally-served model.
5. **False-done stub sweep** — purge or re-mark the 8,817 generated files so the tree stops asserting
   completion it does not have. Do this before trusting any roadmap count.

**Not loader material, recorded so it is not re-investigated:** OmniRoute is a cloud-API gateway proxy
(no model files); hermes-agent is this agent; `Github-Ranking-AI` is a star list; LocalAI is a Go
server wrapping the same llama.cpp/whisper.cpp backends, not its own parser. unsloth is a trainer whose
loader path delegates to HuggingFace — its only durable contribution here is the two byte-layout
references in Phase 9.

---

## 4c. Phase 11 — Model-size intelligence: fit the harness to the model

**Why this belongs in the loader plan at all.** Every mechanism above assumes one execution
shape. That is the mistake HashCortX is built to avoid, and the measurements on this box make it
concrete: LFM2.5-2.6B takes **~68 s/token** here. A 2.6B model *is* the small case, and at that
speed the correct response is not a faster kernel — it is to stop asking the model to do work a
2.6B model cannot do. HashCortX (`src/platform/tauri/hashcoder.js:1067`) sizes its whole agent
harness to the model for exactly this reason. Read from source, not from the README.

### The size decision — from metadata, with a name fallback

`HC.code.sizeOf(billions)` → `'small' | 'mid' | 'full'`, with `null`/unknown → `'full'` so a missing
figure never *degrades* a model:

| Tier | Boundary | What the model gets |
|---|---|---|
| `small` | < 5B | light mode: writes whole files, **the harness does the tool work** and runs the tests |
| `mid` | 5B–15B | focused tools, steps written out, a plan for longer requests |
| `full` | ≥ 15B, cloud, or unknown | code map, per-project lessons, a reviewer for larger changes |

`billions` is **read from the model's own metadata** (`local-context.js:90` — Ollama
`details.parameter_size` via `/api/show`), parsed as `"3.1B"`/`"770M"` → billions
(`local-context.js:64`), cached per `host|model`, falling back to parsing the *name*
(`light.js:67` `billionsInName`). Unknown ⇒ `full`, so an older Ollama or a model with no
`details` loses nothing.

**Quanta can do better than a name regex, because the loader already has the truth.** Phases 2–4
built a dtype model and a role registry over the tensor table; the parameter count is derivable
from the same table exactly, and GGUF carries `<arch>.block_count`, embedding width and
`general.parameter_count` in metadata. So: **read the real count from the loaded tensor graph,
use the name parse only as the pre-load fallback.** That is a genuine improvement over the
reference, not a port.

### Four mechanisms worth adopting (all pure functions, all testable without a model)

1. **Context budget by size** (`agent-context.js:39-78`). Tool-output budget scales with tier:
   `small` 12k chars / 4 results / 3k shell output → `full` 60k / 10 / 20k. The non-obvious part is
   *how* it gives way: hiding happens in **steps** (cut to `hideTo` × budget, several results at
   once) rather than one per turn, because a per-turn change forces a full re-read of the prompt
   on every turn and destroys prefix-cache reuse. **Pure functions of the message list, no state
   between turns** — the same conversation always yields the same prompt.
2. **Temperature ceiling by size** (`hashcoder.js:1077`). `{small: 0.1, mid: 0.2, full: 0.35}`,
   and the user's slider is a *ceiling*, never a wish for more. Rationale: an agent copies text
   exactly and writes paths/arguments in fixed shapes; a small model samples those wrongly.
   Default 0.15 when unset.
3. **Light mode — the harness does the work** (`light.js`). Under 5B the model is offered
   whole-file writes and no fine-grained tools; the host performs the tool operations and runs the
   tests. This is the mechanism that makes a 2.6B model *capable* rather than merely fast.
4. **Proof, not the model's word** (`verify.js`). The best mechanism here, and the one with the
   clearest lesson for Quanta. An agent that changed code and said "done" was believed on its
   word. Instead:
   - the project's own checks are discovered once (test/lint/type/build per package.json,
     pyproject, Cargo, Makefile) — **the app never runs them itself**;
   - every command the agent runs is sorted (test/lint/type/build/format) and recorded with
     pass/fail, scope (whole project or part) and whether it ran **after the last file change**;
   - the agent is **sent back** when it tries to finish unproven, each check bounded to at most
     2 send-backs (3 in light mode);
   - **for a local model < 15B, a reply of words alone is also sent back** — that class of model
     ends a run by *explaining* the fix or asking a question instead of making the change;
   - **for < 15B that changed files, one more send-back quotes the original request and checks
     each item against the files.** Stated failure mode: *"Such a model's usual failure is not a
     wrong change but a finished half: one of three edits, a page without the stylesheet."*
   - the end-of-run summary is computed **from the proof record**, never from the agent's own
     words.
   
   The ordering is fixed and each rule is tried in turn (`sendBack`, `verify.js`): unmade change →
   unchecked test → open plan steps → no proof → per-ask check → small-model self-review.

### What this changes about the performance work already done

This reframes the ~68 s/token result rather than replacing it. The AVX2 dot win (2.95× on the dot,
~1.8× end-to-end) stands on its own, and threading remains blocked on the `clone` trampoline.
But at 2.6B and 68 s/token, **kernel work has a ceiling**: it improves a number nobody can use,
while light mode + proof-send-back converts the same model into one that completes tasks at all.
Sequencing: build the size tiering and light mode *alongside* further kernel work, not after it.

### Build order

| Step | Deliverable | Done when |
|---|---|---|
| 11.1 | `qmodel_size_class()` from the tensor graph + metadata | returns `small/mid/full` for LFM2 2.6B from a real GGUF, `full` on unknown |
| 11.2 | Context budgeting, pure, stepped | same conversation ⇒ same prompt, 1/2/4 worker-agnostic; sizes verified per tier |
| 11.3 | Temperature ceiling | slider can lower, never raise, the tier ceiling |
| 11.4 | Light mode: whole-file writes, host-side tool execution | a task a 2.6B model cannot do directly completes via light mode |
| 11.5 | Proof record + send-back loop | an agent that "finishes" with no test after its change is sent back, ≤2 times |

**Explicitly not adopted:** the app never runs the project's own test commands (the agent runs
them and the result is *recorded*); lessons/code-map stay ≥15B-only, as upstream.

---

## 5. Explicit non-goals

- **No tiered VRAM/RAM/NVMe hierarchy as a core primitive.** Colibrì needs it at 744B/372 GB; Quanta's LFM2 target is 2.6B/~5 GB and never tiers. Build a bounded streaming reader; keep placement a policy layer *above* it.
- **No speculative decoding** until a model actually runs. (Colibrì's int4-MTP finding is recorded so it is not rediscovered expensively.)
- **No CUDA/Metal/Vulkan backend abstraction** beyond what the residency work needs.
- **No multi-GPU / TP.** vLLM's own default loader is rank-blind; this is not a small feature.

---

## 6. Open questions for the maintainer

1. **Phase 4 scope** — llama.cpp has 139 archs. Porting all is not the goal; which second and third archs matter most?
2. **IQ4_NL/IQ4_XS** — ComfyUI-GGUF has reference code on-box. Adopt now or defer to Phase 9?
3. **Diffusion scope** — video loaders need a whole second graph layer (DiT, VAE tiling, text-encoder lifecycle). Separate plan or fold into this one?
4. **`mmap` in the GGUF path** — measured: cold mmap is the *worst* read path (2.446 s/4 GiB) while `pread` is 0.467 s. Adopt `pread` + `MADV_POPULATE_READ` rather than switching to mmap?

---

## 7. Sources

Read from source, on-box: llama.cpp (`gguf.cpp`, `llama-arch.h/.cpp`, `llama-vocab.cpp`, `llama-model-loader.cpp`, `llama-mmap.cpp`), ComfyUI (`model_management.py`, `model_patcher.py`, `utils.py`), ComfyUI-GGUF (`dequant.py`), plus the local safetensors model corpus.

HashCortX, cloned and read for Phase 11 (`git clone --depth 1`, v2.6.0-era `main`):
`src/platform/tauri/hashcoder.js` (`sizeOf`, `SMALL_MODEL_BILLIONS`, `MID_MODEL_BILLIONS`,
`TEMPERATURE_CEILING`, `SMALL_MODEL_TOOLS`), `src/js/local-context.js` (`billionsOf`, `infoOf`),
`src/js/agent-context.js` (`TIERS`, `optionsFor`, stepped hiding), `src/js/code/light.js`
(`billionsInName`, light-mode tool substitution), `src/js/code/verify.js` (`sendBack`, `proofLog`,
`stopCheck`, `proofLine`), `src/js/code/{plan,review,asks,lessons,codemap,digest}.js`.
Note: the README's "under 15B checks its own work" summary is much thinner than the code —
the mechanisms above are what actually ship.

Preserved research (2,923 lines, six inventories):
`~/.hermes/cache/scratch/research/` — hp-runtimes-loaders, mlx-loader-inventory, quant-formats-layouts, safetensors-onnx-pytorch, vllm-ollama-loaders, gpuload/REPORT.md + 6 CUDA benchmarks, a1111-video-accelerate.

**Correction to earlier claims in this session:** the MLX researcher found `web_extract` returning a *stale cached* `utils.py`, caught by cloning. Any web-fetched claim should be re-verified against a clone before entering a plan — llama.cpp and ComfyUI findings above were read from on-box source and are solid. The same applied to HashCortX: its README describes the tiering in prose, and reading the source was what found the real boundary constants, the metadata-first size lookup, the stepped hiding rule, and the six-rule `sendBack` order.