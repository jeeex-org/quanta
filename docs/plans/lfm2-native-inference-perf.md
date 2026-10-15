# Native LFM2 inference performance — CPU first, GPU when available

**Scope:** how to make the *existing* native LFM2 path fast, not what to implement. The **what** lives in
`docs/plans/lfm2-native-inference-spec.md` (stages 0-7) and `docs/plans/model-loader-features.md` (18/18 loader
phases); this doc is the speed plan for the engine those produced.

**Priority:** after the compiler codegen series in `docs/plans/performance.md`. Reason, stated once: the
inference hot loop is **Quanta code end to end**, so every codegen win lands in it too — and a codegen change
invalidates any model timing taken before it. Measure the model once, against final code quality.

**Version numbers** are allocated at release time (`cat VERSION` + 1, `docs/RELEASE_CHECKLIST.md` §9); the order
below is intent, not pre-promised artifacts. Compiler-touching items take a version bump like any other change;
`lib/std/*` items land in the stdlib track (`EXPECTED_STDLIB.tsv`, the `stdlib` gate) — per rule #12 stdlib is
not a core stage, which is how the loader work has landed all along (loader 6.1/6.2/7.1/7.2 → 0.0.226-0.0.228).

---

## 1. Verified state (2026-10-13)

| fact | value / evidence |
|---|---|
| Native forward pass | **correct** — tokenizer exact vs llama.cpp, shortconv fix made the pass match, generation emits text (`lib/std/lfm2_forward.quanta`, 1199 lines; `lfm2_bpe`, `sampling`, `lfm2_mm`) |
| Serial token | **69.4 s/token**; **25.8 s/token at 8 workers** (2.7×), 0 differing rows on real tensors |
| FFN gate matvec [10752×2048] | 514 ms serial → **77 ms at 20 workers (6.7×)**; 16→20 flat (bandwidth bound) |
| Largest single item | **logits matvec 2391 ms** (output head tied to `token_embd.weight` [2048×128000], 6× an FFN matvec) |
| Inside a matvec | dequant **93 ms** vs dot **69 ms** (dequant = 57%) |
| llama.cpp, same weights, CPU | **~110 tok/s** |
| **The parallel paths exist but are OFF** | `mm_workers` is **0** and **nothing in the tree calls `mm_set_workers`** → the shipped forward pass is serial. (`fc_attn_workers` — the other parallel path this row used to name — was **removed** in `21a7be4b`, A21: it leaked 64 MB of address space per forward token and so could not be enabled; the re-add is queued through the pool.) |
| Block kernels | `q4k_dot`, `q4k_matvec`, `q4k_matvec_avx2` are registered builtin names whose emitter bodies are **`return y`** |
| GPU | RTX 4070 Laptop (8188 MiB, cc 8.9, driver 615.71.09), ~7.4 GiB free; toolkit at `/usr/local/cuda-13.3` (nvcc not on PATH); `dequant_q4k`/`matvec_q4k`/`matvec_f32` kernels + `qg_*` wrappers exist; Quanta client `lib/std/cuda_daemon.quanta` |
| CUDA daemon stability | **already fixed** — `b8870462` (sync-before-destroy, `stage_stream` cleanup, stream validation) with a negative control that reproduced the crash with the defenses removed. A 6h25m unattended run on 2026-10-13 with no crash supports it |

**GPU arithmetic (projected; the IPC number is the one that decides, and it gets measured first):** Q4_K_M
2.6B ≈ 1.6 GB of weights per token at ~256 GB/s → **~6 ms/token ≈ 160 tok/s bandwidth bound**; compute ~0.3 ms;
per-matvec PCIe traffic negligible. So `IPC_latency × ops_per_token` decides: 200 µs/op × ~266 ops ≈ 53 ms/token
(**19 tok/s**); 1 ms/op ≈ 266 ms (**3.8 tok/s**, needs graph mode); 1 round trip/token → bandwidth bound
(**100-160 tok/s**).

---

## 2. The series

### Next version — turn on the parallelism that already exists (cheapest lever in the project)

`lib/std/lfm2_forward.quanta` (+ `mm_set_workers`/`mm_scratch_new`/`mm_matvec_par` already in `lfm2_mm.quanta`).

1. One entry point (`fc_set_workers(n)`) setting `mm_set_workers(n)`; keep default
   0 so the byte-identical serial path stays default until measured. (The
   `fc_attn_workers = n` half of this step is void: that global was **removed** in
   `21a7be4b`, A21. The attention-body parallelism it gated is queued to be
   re-added through the persistent pool, not as a per-call thread body.)
2. Per-row element-wise identity serial vs 1/2/4/8/16 workers on **real** forward-path tensors (0 mismatches,
   5 repeats). Assert the setup call's return value — a parallel-matvec test once "passed" while comparing
   against zeros; use derived row counts, not round numbers.
3. Measure interleaved, then flip the default and commit the measured number.

**Expected:** 69.4 → **~12-20 s/token** (measured 25.8 s at 8 workers; stop at 16, 16→20 is flat).

### Next — re-profile and go after the new #1

The bottleneck moves after each win. With the FFN parallel, the **logits matvec (2391 ms)** is the largest
single item (128000 rows partition trivially — confirm the logits site actually takes the parallel path, and
that the prefill logits skip is on for every non-final position). Take the next target **from the profile
table**, not from assumption.

### Next — batched prefill (amortise the dequant)

Dequant is 57% of each matvec and per-position prefill re-pays it. Dequantise a weight row **once** into
per-worker scratch, then dot it against N activation vectors → dequant ÷ N. (The earlier "templated prefill"
attempt died on an 870 s cap because it templated the *forward pass*; batch inside the kernel.)
Requirement: per-`(row,pos)` accumulation order identical to the per-token path, so the result is
element-wise **equal**, not close — prove it at npos = 1, 2, 7, 64 on real tensors, then measure prefill tok/s
separately from decode. **Expected:** 64-token prefill ~64× → ~3-6× one decode step.

### Next — prefix KV reuse

Hash the prompt prefix, keep the KV cache across turns, rewind to the common prefix. Agent-style loops resend
a long system prompt every turn; this removes it from the critical path. (Not a refine-the-logits change:
candidate pruning of the output head stays a **non-goal** — it changes the logits.)

### Later — block-consuming SIMD kernels (only if the compiler series leaves a gap)

`q4k_dot` etc. are placeholders emitting `return y`: either implement a real fused Q4_K block kernel (one call
consuming a whole 256-element block, using the emitter helpers after `flush_all()` frees `r8`-`r15`) or
**delete the placeholders** so the tree stops asserting kernels exist. Realistic ceiling from prior attempts:
2-4× on the dequant, more only if the dot moves to int8 SIMD MACs inside the same call.
**Fusing changes the summation order** → not bit-exact against `libggml-base`: an explicit, documented
tolerance is required before it lands. Never claim "matches upstream" for a fused path.
**Re-evaluate this item after the compiler series**: cheaper codegen may make it unnecessary — that is the
whole reason the compiler work is sequenced first.

### GPU track (independent of codegen; can interleave)

1. **Measure the IPC round trip first** — single op through `/tmp/quanta_cuda/queue` → `result`, ≥200 samples,
   median + p99, plus the daemon's internal GPU time. Multiply by the real ops-per-token (instrument the
   `mm_matvec` call sites). Decision point: <250 µs/op → wire the per-op path; otherwise step 2 is mandatory.
   (Daemon stability is **not** a blocker — it was fixed in `b8870462`; verify with a stress run, do not
   re-plan it.)
2. **Cut the round trips:** shared-memory ring + spin/futex instead of append/poll/lock (target single-digit µs),
   and **graph mode** — describe a token's whole op sequence once (weights resident) so the daemon executes it:
   1-2 round trips per token instead of ~266, converting the GPU from latency-bound to its ~160 tok/s
   bandwidth bound. The op sequence is static, so this is cheap to build and the whole point of residency.
3. **Residency + VRAM floor:** upload all weights once as Q4_K in VRAM (~1.6 GB of 7.4 GiB free); keep the KV
   cache GPU-side. Refuse the GPU path below ~3 GiB free (this GPU also serves ComfyUI/torch on this box) and
   fall back to CPU — never silently take VRAM.
4. **Numerics:** GPU kernels accumulate in **fp32** (fp64 is 1/64 rate), so the GPU path cannot be bit-identical
   to the f64 CPU path. Verify element-wise per row against the CPU reference with a documented tolerance, then
   verify the **token stream on a fixed prompt**. Stream divergence is a blocker to analyse, not a threshold to
   relax.
5. **One switch:** backend global (`cpu|gpu`) behind the existing `mm_matvec` funnel, set by a capability probe
   (`/dev/nvidia0` readable + `libcuda` loadable + daemon alive + VRAM ≥ floor). CPU stays default until the
   measurements are green.

---

## 3. Measurement discipline (every rule learned on this box)

- **A/B interleaved in ONE process**, min-of-3, `uptime` recorded (±20% spread at load ~10 on 20 cores).
- **Element-wise oracles over the whole domain** for anything touching weights; a reduction agreement is weaker
  evidence than element equality.
- **A stateful forward pass cannot be compared against its own rerun** — the KV cache accumulates, so two serial
  calls differ too: always run the serial-vs-serial control before concluding a change diverged.
- Compare parallel vs serial identity at 1/2/4/8/16 workers; a mismatch that grows with worker count is a
  shared-buffer race (use `pread64`, never `lseek`+`read`).
- **Do not re-run settled experiments**: block-size sweep (~5% over 16×), block reads (slower), 16-entry factor
  table (slower), 4-wide AVX2 f64 dequant (3.5× slower), workers above 16.
- Compiled binaries only through `scripts/qcrun.sh`; never `gdb` a compiled binary.

## 4. Exit criteria and stop rules

- **CPU goal:** ≥1 tok/s decode with prompt reuse — the threshold where the SI loop can use the local model for
  small, host-verified steps.
- **GPU goal:** this card's bandwidth-bound ceiling (~100-160 tok/s) — the point where the local model stops
  being throughput-limited.
- **Stop rule (fixed now):** if, after the compiler series plus parallelism + batched prefill, CPU decode is
  still > 1 s/token, CPU-native stays what it is good at — verification, small edits, the bounded-memory loader
  — and generation runs on the GPU or through a local llama.cpp while Quanta owns the loop, the gate, and the
  proofs. State it in the docs; do not leave a half-wired backend claiming support.

## 5. Open question (genuine)

**Tolerance bar** — the fused CPU path and the fp32 GPU path both break bit-exactness by arithmetic necessity.
Proposal: element-wise tolerance documented per kernel **plus** token-stream equality on a fixed prompt, with
stream divergence treated as a blocker. Confirm that is the bar you want, or set a stricter one.

## 6. Files likely to change

- `lib/std/lfm2_forward.quanta` — worker entry point, batched prefill call sites, prefix KV reuse
- `lib/std/lfm2_mm.quanta` — `mm_matvec_batch`, activation quantiser, kernel call sites, backend funnel
- `lib/std/cuda_daemon.quanta` — client, ring/graph protocol, backend switch
- `compiler/<NEXT>/src/x86/emitter.quanta` — only if the block kernel is implemented (version bump)
- `scripts/audit/cuda_daemon.c`, `quanta_gpu_kernels.cu` — fp32 accumulation, batching, ring protocol
- `test_suites/codes/stdlib_lfm2_*_test.quanta`, `EXPECTED_STDLIB.tsv` — identity and tolerance tests
- `benchmarks/` — inference-shaped cases (the loader/q4k twins already exist there)
