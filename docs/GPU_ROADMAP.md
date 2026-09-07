# GPU Roadmap — Quanta GPU Backend

Consolidated from domain files (`programming_language_gpu_*.quanta`, `programming_language_hpc_cuda.quanta`). Roadmap: parallel to x86 core chain (0.0.163→1.0), versions GPU_0.0.001+ for GPU-only milestones. Final target: CPU Quanta (0.0.169) with GPU backend that runs the brain substrate.

---

## Existing domain source (from lib/std/)

| File | Status | Notes |
|---|---|---|
| `electronics_logic_gpu.quanta` | 🔲 planned | GPU logic circuits |
| `programming_language_gpu_cuda.quanta` | 🔲 planned | CUDA programming surface |
| `programming_language_gpu_open_cl.quanta` | 🔲 planned | OpenCL surface |
| `programming_language_gpu_vulkan.quanta` | 🔲 planned | Vulkan compute/shader |
| `programming_language_gpu_metal.quanta` | 🔲 planned | Apple Metal |
| `programming_language_gpu_direct_x.quanta` | 🔲 planned | DirectX compute |
| `programming_language_drivers_gpu.quanta` | 🔲 planned | GPU driver bindings |
| `programming_language_hpc_cuda.quanta` | 🔲 planned | CUDA HPC kernels |

---

## GPU Backend Milestones (GPU_0.0.001 → GPU_0.0.020) — in parallel with x86 core chain

### Phase A — Target Selection + Thin FFI (GPU_0.0.001 – GPU_0.0.003)

| Milestone | What | Source target | Status |
|---|---|---|---|
| GPU_0.0.001 | Select target: CUDA/PTX (RTX 4070 dev card) first; ROCm/Vulkan deferred | `programming_language_hpc_cuda.quanta` | 🔲 |
| GPU_0.0.002 | Thin FFI layer: `extern_c_ffi` extended to CUDA runtime (cuLaunchKernel, cuMemcpyHtoD, cuMemAlloc) using same `extern_var` / `extern_c_ffi` mechanism already in compiler/0.0.166/src/x86/globals.quanta | x86 `extern_c` path | 🔲 |
| GPU_0.0.003 | Minimal CUDA host program: allocate host buffer → `cuMemcpyHtoD` → allocate device buffer → `cuLaunchKernel` → `cuMemcpyDtoH` → free — no real compute yet, just the lifecycle | `programming_language_gpu_cuda.quanta` | 🔲 |

### Phase B — Emitter + Instruction Encoding (GPU_0.0.004 – GPU_0.0.007)

| Milestone | What | Source reference | Status |
|---|---|---|---|
| GPU_0.0.004 | Design target-independent IR: current `globals.quanta` defines `IR_*` codes (MOV, CONST, CALL, STR, etc.). Need `IR_GPU_*` for device-side ops OR extend existing codes with a backend flag. Decision: extend `globals.quanta` with a `GPU_BACKEND` bit in the vreg tag (same mechanism as `vfloat + ...` at line 259) rather than new codes, to avoid duplicating 147+ core logic. | `globals.quanta` | 🔲 |
| GPU_0.0.005 | Add GPU emitter: `emitter.quanta` (line 1230–1330 concurrency path shows how new builtins are added). Add `emit_gpu_*` functions that emit PTX SASS via CUDA driver API (thin FFI to nvcc at build time, same pattern as `quanta_link.sh` + `ld` used in 0.0.122). | `emitter.quanta` | 🔲 |
| GPU_0.0.006 | Build script: `scripts/` stays as the only place for scripts. Add `scripts/gpu_build.sh` that calls `qc --emit-ptx` then links via CUDA runtime (not `ld`), same structure as `quanta_link.sh`. | project rules (root clean) | 🔲 |
| GPU_0.0.007 | First real GPU binary: `qc --gpu-cuda src/main.quanta out` produces an `.o` with embedded PTX; host stub loads and launches it. Test on RTX 4070. Verified by comparing host-side result to x86 `qc` output (bit-exact differential gate from `fuzz_differential.sh`). | differential fuzz gate | 🔲 |

### Phase C — Memory Model + VRAM Safety (GPU_0.0.008 – GPU_0.0.011)

| Milestone | What | Source reference | Status |
|---|---|---|---|
| GPU_0.0.008 | VRAM memory model: `mem_alloc` on GPU means `cuMemAlloc`. Add GPU-specific `mem_alloc` / `mem_realloc` / `mem_store` / `mem_load` routes in `lib/std/` that call CUDA APIs via thin FFI. Safety: Valgrind-like GPU memory scan using CUDA `cuMemGetInfo` + `cuMemRangeIsValid` checks. | `SAFETY_MANUAL.md` (Valgrind section) | 🔲 |
| GPU_0.0.009 | Fail-closed VRAM: out-of-memory must return `exit(1)` (same as `big_udiv` div-by-zero guard at line 665 of `lib/std/big.quanta`). No silent fallback to host. | `big.quanta` guard pattern | 🔲 |
| GPU_0.0.010 | GPU memory safety argument: `MEMORY_SAFETY_ARGUMENT.md` extended with GPU section — `cuMemRangeIsValid` clean, `cuMemGetInfo` shows zero leaks after `mem_free`, differential vs x86 host run produces identical results for same inputs. | `MEMORY_SAFETY_ARGUMENT.md` | 🔲 |
| GPU_0.0.011 | VRAM differential fuzz: extend `test_suites/scripts/fuzz_differential.sh` with GPU mode: compile same source with `qc --gpu-cuda`, run on device, compare stdout/exit to x86. Must pass 120 runs clean (`N=120`, same parameter). | `fuzz_differential.sh` | 🔲 |

### Phase D — Core AI Tensor + LLM Substrate (GPU_0.0.012 – GPU_0.0.016) — overlaps with x86 `ai_llm` core chain (0.163–0.172)

| Milestone | What | Status |
|---|---|---|
| GPU_0.0.012 | `ai` core: basic tensor ops (`tadd`, `tmul`, `tmatmul`) on device — pure Quanta source in `lib/std/`, not Python bindings. Implemented via thin FFI to CUDA `cublas` / `cudnn`. | 🔲 |
| GPU_0.0.013 | `ai_llm` — RoPE, RMSNorm, SwiGLU, GQA: GPU-native versions in Quanta. Each operation is a `fn` in `lib/std/` that calls CUDA kernels (same structure as `std/math/algebra/linear/vector_spaces`). | 🔲 |
| GPU_0.0.014 | KV cache: device-side `kv_cache_store` / `kv_cache_load` using `cuMemAlloc` / `cuMemcpyAsync`. Memory budget tracked via `cuMemGetInfo`. Fail-closed on overflow (same `exit(1)` pattern). | 🔲 |
| GPU_0.0.015 | FlashAttn / quantization: `NF4` dequant (Soup's use case — `NF4` above ~165 MiB per layer was the wrong-gradient defect source). Implemented in pure Quanta with GPU differential gate: NF4 dequant result must be bit-exact vs x86 reference. | 🔲 |
| GPU_0.0.016 | `ai_llm` complete gateway: from `std/io` input through `std/types` tokenizer (`programming_language.md` token module at line 354 🔲) to GPU-emitted tensor operations to `std/print` output. Full pipeline verifiable by `test/EXPECTED_STDLIB.tsv`. | 🔲 |

### Phase E — SI + Brain Substrate (GPU_0.0.017 – GPU_0.0.020)

| Milestone | What | Status |
|---|---|---|
| GPU_0.0.017 | SI Phase 1 on GPU: gap detector runs as a Quanta binary (`qc --gpu-cuda`) reading `docs/roadmap/domains/*.md` from disk (same `std/io` + `std/regex` prerequisites at 0.0.169). No Python. | 🔲 |
| GPU_0.0.018 | SI Phase 2 (code generation) on GPU: `spec-to-IR mapper` emits GPU-targeted IR; `code synthesizer` uses GPU `pattern library`; `Quanta emitter` produces `.quanta` source; `test generator` produces `EXPECTED_STDLIB.tsv` rows. All in pure Quanta. | 🔲 |
| GPU_0.0.019 | Merge automation on GPU: `std/git` + `std/ci` gates run as GPU binaries. `VERSION` bump from 0.0.166 to next (core chain continues 0.0.167+ independently). | 🔲 |
| GPU_0.0.020 | Full brain substrate: Quanta compiler (`qc`) running as GPU-resident binary (layer-streamed base weights in VRAM + Quanta runtime in device memory) executing `ai_llm` inference. Verified: same config and same weights as Soup's `stream_layers: true` mode produce bit-exact results, but without Python overhead. Final proof: `docs/SELF_IMPROVEMENT.md` updated: "Phase 1: Gap Detection ✅ Pure Quanta (GPU-resident); Phase 2: Code Generation ✅; Phase 3: Testing ✅; Phase 4: Merge ✅". | 🔲 |

---

## CPU Quanta — Final Target Integration

When the GPU backend is at GPU_0.0.020:

1. **CPU Quanta remains the authoritative compiler** (`compiler/0.0.166/` → `compiler/0.0.XXX/`). The GPU backend produces an additional artifact (`.ptx` or `.o` with embedded PTX) alongside the x86 binary, not a replacement.
2. **Self-hosting fixpoint verified on both targets**: `qc` (x86) compiles `qc` source → x86 binary; `qc --gpu-cuda` (thin FFI calling CUDA driver API at build time) produces `.o` with PTX; the PTX is loaded by the GPU-host stub and runs the brain substrate.
3. **Root rules preserved**: `bin/qc` never exists in root; binaries stay under `compiler/${VERSION}/bin`; `scripts/` holds `gpu_build.sh`; `docs/SELF_IMPROVEMENT.md` is the single source of truth for SI status.
4. **Version pointer**: `VERSION` continues the core chain (0.0.166 → 0.0.167... → 0.1.0 STABLE). GPU versions are tracked separately (`GPU_0.0.020` = 0.1.0 STABLE + GPU brain substrate complete) but don't replace VERSION.

---

## Verification Gates (same quality rules as x86 core chain)

- Gate: all `tests/` pass on GPU mode (same 11-layer gate as `docs/SECURITY_TOOLING.md`)
- Gate: `fuzz_differential.sh` passes on GPU mode (`N=120`, zero divergence)
- Gate: `EXPECTED_STDLIB.tsv` 7/7 stdlib modules pass (same standard as `docs/MEMORY_SAFETY_ARGUMENT.md`)
- Gate: Valgrind-equivalent GPU memory clean (`cuMemRangeIsValid`, zero leaks, `MEMORY_SAFETY_ARGUMENT.md` GPU section)
- Final binary: the GPU-host stub (`compiler/${VERSION}/bin/x86/gpu_host`) loads the `.o` with embedded PTX, runs `ai_llm` inference, and produces identical stdout to x86 `qc` output for the same `.quanta` source.
