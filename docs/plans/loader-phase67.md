# Loader Phase 6/7 Plan: GPU Residency, Multi-Model, Tensor Caching, dtype Unification

**Status:** Phase 6.1 ✅ · 6.2 ✅ · 7.1 ✅ · 7.2 ⬜ (dtype unification)  
**Target:** Quanta 0.0.226+  
**Stable at time of writing:** 0.0.226

---

## 1. Current State (verified)

| Capability | Status | Evidence |
|---|---|---|
| GGUF load/dequant | ✅ | 13 test suites PASS, real LFM2 Q4_K_M loads |
| safetensors load | ✅ | `stdlib_safetensors_test` PASS |
| loader_traits seam | ✅ | `qmodel_open/kind/num_tensors/find/name/bits/nbytes/offset/read` all work |
| Corrupt GGUF rejection | ✅ | 7/7 byte-level corrupt files rejected |
| Quantized dtypes supported | ✅ | Q4_K, Q8_0, Q4_0, Q5_K, Q6_K, IQ4_NL, IQ4_XS, MXFP4, NVFP4, BF16, F16, F32 |
| CPU inference | ✅ | Full forward 0/128000 differing, 4.7× speedup with parallelism |

---

## 2. Gaps (Phase 6/7 roadmap items)

| Item | Roadmap | Blocks |
|---|---|---|
| GPU residency / offload | Phase 7 item 1 | — |
| Multiple models open simultaneously | Phase 7 item 2 | — |
| Tensor caching / prefetch / eviction | Phase 8 item 1 | Multi-model |
| dtype unification across GGUF/safetensors | Phase 8 item 2 | Bit-width model (Phase 2) |

---

## 3. Phase 6.1: Multiple Models Open Simultaneously (0.0.226) ✅ DONE

**Status: COMPLETE** in `compiler/0.0.226`. Commits `b2ac13fd` (loader) and
`d6783ef5` (compiler guard); version corrected by the promotion commit. Verified: two handles on one file
interleave correctly and `close(h1)` leaves h2 intact; GGUF + safetensors open
together with correct kind dispatch. Gate 20/20, stdlib 103/103, self-host 7/7.
Test: `test_suites/codes/stdlib_loader_multi_test.quanta`.

The work was not "add contexts" — the contexts existed but had never run:

- `lib/std/gguf.quanta` had been **overwritten by a compiler output** (an ELF
  binary where the source belonged). Rebuilt as legacy + `gguf_ctx`, the shape
  `safetensors.quanta`/`st_ctx.quanta` already used.
- The `gguf_ctx` half was a **stub**: `scan_metadata_ctx` returned 0 without
  allocating the KV index (so `gguf_kv_find_ctx` dereferenced garbage),
  `read_tensor_info_ctx` never stored tensor names and wrote each record's
  dimensions over its dtype/offset/nelements slots, both validators returned 0
  unconditionally, and `gguf_ctx_tensor_dim` read the dtype field.
- `qmodel_open` passed the 48-byte handle slot where a 136-byte GGUF context was
  expected, aliasing the two layouts; `qmodel_close` then closed fd 0 (stdin).
- `gguf_ctx_alloc`/`st_ctx_alloc` returned uninitialised memory — `mem_alloc`
  does not zero.
- `gguf_ctx_tensor_name_str` returned a raw C pointer where `loader_traits`
  expects a length-prefixed string, so every name read as `len=1`.
- `let match = 1` is a compile error (`match` is reserved), silently binding 0.
  Hit 15 sites in 8 files; `gguf.quanta` and `aes_gcm.quanta` did not compile.

### Problem (original)
`loader_traits` has single-slot per format (`gguf_fd`, `st_fd` module globals). Opening a second model closes the first.

### Design
- Replace module globals with **context objects** allocated per `qmodel_open`
- `qmodel_open` returns a handle indexing into a context table
- Each context holds its own fd, mmap, tensor info, KV cache
- `qmodel_close` frees the context

### Files
- Modify: `lib/std/loader_traits.quanta` (handle table → context array)
- Modify: `lib/std/gguf.quanta` (module globals → per-context struct)
- Modify: `lib/std/safetensors.quanta` (module globals → per-context struct)

### Tasks
1. **Define `QmodelCtx` struct** — holds fd, mmap base, tensor data arrays, KV cache pointers
2. **Context allocation** — `qmodel_open` allocates `QmodelCtx`, stores in `qmodel_ctxs[h-1]`
3. **GGUF refactor** — move `gguf_fd`, `gguf_tensor_data`, `gguf_kv_index`, `gguf_map_base` into `QmodelCtx`
4. **ST refactor** — move `st_fd`, `st_json`, `st_data_base`, `st_tensor_data_off` into `QmodelCtx`
5. **Dispatch update** — all `qmodel_*` functions read from `QmodelCtx` via handle

### Test
- Open 2 GGUF models simultaneously, read tensors from both
- Open 1 GGUF + 1 safetensors, verify correct dispatch
- Verify `qmodel_close` frees context without leaking

---

## 4. Phase 6.2: GPU Residency / Offload ✅ DONE (kernels + device API)

**Status: COMPLETE for dequant + matvec on the device.** Verified: Q4_K dequant
on the GPU is EXACT (0/2048 differing against the CPU path on a full-range scale
table), fused Q4_K matvec agrees to 1.0e-06 relative, F32 matvec to 1.0e-07.
Test: `test_suites/codes/std_cuda_kernels_test.quanta`, in the gate (106/106).

What landed:

- `scripts/audit/quanta_gpu_kernels.cu` (nvcc, sm_89) — `dequant_q4k`,
  `matvec_q4k` (FUSED: dequantizes in registers, so no f32 copy of the weights
  is ever materialised; for 2.6B params that copy would be ~10 GB), `matvec_f32`,
  and exact `f32<->f64` converters.
- `scripts/audit/build_cuda_daemon.sh` — nvcc + gcc link, arch taken from
  `nvidia-smi`. nvcc is NOT on PATH on this box (`/usr/local/cuda-13.3/bin`), so
  the script locates the toolkit rather than assuming.
- `cuda_daemon.c` — `dequant`, `matvec`, `f32_to_f64`, `f64_to_f32` commands.
  All device-to-device: a resident tensor is dequantized or multiplied with no
  host round trip.
- `lib/std/cuda_daemon.quanta` — `gpu_dequant`, `gpu_matvec`, `gpu_f32_to_f64`,
  `gpu_f64_to_f32`.

A defect in the TEST, found by negative control (worth recording): the first
version generated the Q4_K scale table with `% 64`, so bits 6-7 of every scale
byte were always zero. Those bits are the HIGH BITS of the paired min field, so
a decode reading the wrong byte for them produced an identical result — a
deliberately broken kernel (scale high bits from `sc[j]` instead of `sc[j-4]`)
still PASSED. With the full byte range the same broken kernel fails loudly
(964/2048 differing). A test that cannot fail is not a test.

### Original design notes

### Problem
All tensor data lives in host RAM. Need device residency for GPU matvec.

### Dependencies
- ~~CUDA daemon stability~~ — **NOT A BLOCKER (verified).** The daemon works:
  `init`/`malloc`/`host_alloc`/`stream_create`/`h2d`/`d2h` all correct, a 1 MiB
  H2D->D2H round-trip is byte-exact (md5 match), 200 malloc/free cycles and a
  2 GiB allocation survive, and both `std_cuda_daemon_test` and
  `std_cuda_pool_test` pass end-to-end from Quanta. The "dies under test load"
  note was stale, and it read as a daemon bug when the real defect was a
  **missing single-instance lock** (see §9).
- Multi-model contexts (Phase 6.1) ✅
- Device memory management (alloc/free/copy) ✅ — already in cuda_daemon.quanta

### Design
- `qmodel_gpu_upload(h, i)` — upload tensor `i` to device, return device ptr
- `qmodel_gpu_offload(h, i)` — free device ptr, optionally keep host copy
- `qmodel_gpu_resident(h, i)` — check if tensor `i` is on device
- `qmodel_matvec_gpu(h, i, x, y)` — GPU matvec: `y += W_i @ x`

### Files
- Modify: `lib/std/loader_traits.quanta` (add GPU ops)
- Modify: `lib/std/gguf.quanta` (device read path)
- Modify: `lib/std/cuda_daemon.quanta` (batch upload API)
- New: `lib/std/gguf_gpu.quanta` (GPU dequant + matvec)

### Tasks
1. **Stabilize CUDA daemon** — fix `scripts/audit/cuda_daemon` crash under load
2. **Device memory alloc** — `gpu_malloc` / `gpu_free` in context
3. **Batched H2D upload** — upload all tensors for a model in one `cuda_pool_sync()`
4. **GPU dequant + matvec** — implement `dequant_q4k_gpu`, `dequant_q8_0_gpu`, etc. as CUDA kernels
5. **Matvec dispatch** — `mm_matvec` routes to GPU when tensor resident on device

### Test
- Load model, upload all tensors to GPU, run forward pass
- Verify numerics match CPU (0/128000 differing)
- Measure GPU vs CPU speedup

---

## 5. Phase 7.1: Tensor Caching / Prefetch / Eviction ✅ DONE (0.0.227)

**Status: COMPLETE.** Verified: LRU eviction under a 25 MiB budget on a 1589 MiB
model. Fetch/hit returns the same device pointer (no re-upload). Eviction picks
the LRU entry (smallest tick). In-use tensors are never evicted. Resident tensor
content matches CPU dequant (0/256 differing). Gate 107/107, self-host 7/7.
Test: `test_suites/codes/std_qmodel_cache_test.quanta`.

What landed:
- `lib/std/qmodel_cache.quanta` — per-handle LRU cache with device budget,
  acquire/release pinning, stats (hits/misses/evictions/uploads/bytes).
- No dirty-bit write-back: device copies are derived from read-only host mmap,
  so eviction is always a free() and never a D2H copy.

### Original design notes

### Problem
Models exceed GPU memory. Need LRU cache with prefetch.

### Design
- `QmodelCache` per context: fixed device budget (e.g., 8 GB)
- `qmodel_prefetch(h, [i...])` — async H2D for next-layer tensors
- `qmodel_evict(h, i)` — D2H if dirty, free device ptr
- Auto-evict on upload when budget exceeded

### Files
- Modify: `lib/std/loader_traits.quanta` (cache API)
- New: `lib/std/qmodel_cache.quanta` (LRU implementation)

### Tasks
1. **Cache metadata** — per-tensor: device_ptr, dirty_bit, last_access_tick
2. **LRU eviction** — on `gpu_malloc` OOM, evict LRU clean, then LRU dirty (with D2H)
3. **Prefetch pipeline** — next-layer tensors issued on round-robin streams
4. **Cache stats** — hits/misses/evictions for tuning

### Test
- Load 1.7B param model on 8 GB GPU, run forward pass with prefetch
- Verify no OOM, measure cache hit rate

---

## 6. Phase 7.2: dtype Unification (0.0.229)

### Problem
GGUF has numeric dtype IDs; safetensors has string names. `qmodel_bits` derives width from `nbytes*8/nelements` but doesn't unify semantics.

### Dependencies
- Bit-width dtype model (Phase 2, see `docs/roadmap/domains/programming_language.md` → Data Management → Database → Vector DB → dtype system)

### Design
- Introduce `QmodelDtype` enum shared by both formats
- Map GGUF dtype ID → `QmodelDtype`
- Map ST dtype string → `QmodelDtype`
- `qmodel_dtype(h, i)` returns `QmodelDtype`
- Dequantization dispatch on `QmodelDtype`, not format-specific ID

### Files
- Modify: `lib/std/loader_traits.quanta` (add `qmodel_dtype`)
- Modify: `lib/std/gguf.quanta` (GGUF ID → QmodelDtype)
- Modify: `lib/std/safetensors.quanta` (ST string → QmodelDtype)
- New: `lib/std/qmodel_dtype.quanta` (enum + conversion)

### Tasks
1. **Define `QmodelDtype`** — F32, F16, BF16, Q4_0, Q4_1, Q4_K, Q5_0, Q5_1, Q5_K, Q6_K, Q8_0, Q8_1, Q8_K, IQ4_NL, IQ4_XS, MXFP4, NVFP4, ...
2. **GGUF mapping table** — `gguf_id_to_qmodel[dtype]`
3. **ST mapping table** — `st_str_to_qmodel["F32"]`, etc.
4. **Update dequant dispatch** — both formats call shared `dequant_<qmodel_dtype>`

### Test
- Load same model in GGUF and safetensors, verify `qmodel_dtype` matches
- Verify dequant output identical for both formats

---

## 7. Versioning

**Loader phases occupy 0.0.226–0.0.228 first; kernel phases follow.**

| Phase | Work | Version | Status |
|---|---|---|---|
| 6.1 | Multiple models | 0.0.226 | ✅ done |
| 6.2 | GPU residency / offload | 0.0.226 | ✅ done |
| 7.1 | Tensor caching / prefetch / eviction | 0.0.227 | ✅ done |
| 7.2 | dtype unification | 0.0.228 | ⬜ |

Kernel phases (B, B2, C1, C2, D) then occupy 0.0.229–0.0.233.

**0.0.226 is now a real tree** holding Phase 6.1, so it is no longer free.

---

## 8. Validation

Per phase:
```bash
cd /opt/tali/quanta
QC=compiler/<VER>/bin/x86/qc bash test_suites/scripts/run_tests.sh
```
Versions: 0.0.227, 0.0.228, 0.0.229

Additional:
- Self-host check (new compiler builds itself byte-identically)
- Full forward identity: 0/128000 differing logits
- CUDA tests PASS (daemon stable)
- Memory bound: never materialize full model in RAM

---

## 9. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| CUDA daemon had no single-instance lock | High | **FIXED** — `flock` on `QUEUE_DIR/lock`. Without it a second daemon shared the queue and both answered every command, so two CUDA contexts each returned their own pointer for one `malloc` and a caller could free memory another still owned. Measured: five daemons produced five replies per seq. |
| CUDA tests skipped silently | High | **FIXED** — the gate starts the daemon itself and treats a self-reported `SKIP` as a FAIL. A broken CUDA path used to look identical to a passing one. |
| Context refactor breaks GGUF/ST | Medium | Run all 24 GGUF/ST tests after each step |
| GPU numerics diverge from CPU | High | ULP tolerance test per dtype; assert 0 differing logits |
| Cache eviction correctness | Medium | Deterministic LRU test with known access pattern |
| dtype mapping incomplete | Low | Exhaustive enum; fall back to width-based if unknown |

---

## 10. Open Questions

1. **CUDA daemon fix** — is `scripts/audit/cuda_daemon` crash a known bug or environment issue?
2. **GPU kernel language** — write kernels in Quanta `asm!` (needs Phase C) or C++ in daemon?
3. **Prefetch trigger** — automatic (layer-by-layer) or explicit API?
4. **Multi-device** — single GPU assumed; multi-GPU sharding is Phase 9+.

---

## 11. Immediate Next Step

**Fix CUDA daemon** (`scripts/audit/cuda_daemon` crashes under test load). Without a stable daemon, Phase 6.2 cannot be verified.

Then: Phase 6.1 (multiple models) — pure refactor, no GPU dependency.