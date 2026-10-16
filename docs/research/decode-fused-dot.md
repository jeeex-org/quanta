# Decode campaign: fused dequant-dot, mmap, worker scaling -- measured plan

Status: in progress, 0.0.245, lib/std + tests ownership only (compiler/** untouched).
Goal handed down: decode at >= 15 tok/s (<= 66 ms/token) on
QUANTA-LFM2.5-2.6Bv1-Q4_K_M.gguf, validated by large-scale end-to-end runs.

## 0. The verified premise -- CORRECTED (the 36 GB/s envelope was invalid)

Parsed straight from the GGUF header (266 tensors, GGUF v3):

- total 2.6972G elements, 1.6662 GB
- **matvec elements per decode token (every blk.* tensor + tied output):
  2.4351G elements = 1.4512 GB of weight bytes read per token**
- dtype split of that per-token work: Q4_K 1.766G elems (72.5%),
  Q6_K 669M elems (27.5%), F32 norm/conv tails ~10M

**RETRACTION (owner-confirmed):** the original premise anchored "15 tok/s is
inside the demonstrated ~36 GB/s envelope" on llama.cpp serving GG4-E4B -- a
7.5B MoE whose per-token streaming touches only its active experts (~4B of
7.5B), so total-file-size x tok/s does NOT measure its streaming rate. The
sound reference is llama.cpp on THIS exact model, measured here:

> **llama.cpp, QUANTA-LFM2.5-2.6Bv1-Q4_K_M.gguf, this box, CPU-only, 20
> threads, greedy, 300 generated tokens: 17.32 tok/s sustained decode**
> (prompt eval 59.6 tok/s; load 1.57 -> 4.55, governor powersave;
> /opt/ai/llama.cpp/build/bin/llama-server, /completion, ignore_eos).

The 15 tok/s target therefore sits just BELOW the same-model llama.cpp rate
(87% of it). The native loader measured 0.286 tok/s (20 workers) -> the honest
gap to close is **60x**, and the campaign deliverable is the measured absolute
rate plus per-lever relative gains, with 17.3 tok/s as the reference point.

**Strategy confirmed by the author: CPU-first, then GPU** ("with CPU more
devices can run it") -- GPU is QUEUED NEXT, not dropped: a separate unit does
the GPU/CUDA path once the CPU path is production. For that unit, the pieces
of this campaign that port directly are recorded in section 5.

## 1. The measured wall (why lib/std alone cannot reach 15)

Authoritative serial per-op costs, all measured on this box
(tests/lfm2_op_profile.quanta; tests/lfm2_dot_bench.quanta this campaign;
docs/research/prefill-batching.md and q6k-simd-dequant.md):

| component | rate (quiet-box est.) | per decode token |
|---|---:|---:|
| Q4_K dequant (dq32lo/hi, bit-exact) | ~4.0 ns/elem | 1.766G -> ~7.1 core-s |
| Q6_K dequant (dq6, bit-exact) | ~2.0 ns/elem | 0.931G -> ~1.9 core-s |
| dot (mm_dot4_s, 4 vector lanes) | ~2.7 ns/elem | 2.173G rows -> ~5.9 core-s |
| embed dot (scalar, left-to-right) | ~11 ns/elem | 262M -> ~2.9 core-s |
| row pread (page cache) | ~0.5 ns/elem | 2.435G -> ~1.2 core-s |
| non-matvec (norms, silu, attention, residuals) | measured 0.3% serial | ~0.05 core-s |

Serial-equivalent decode token: **~18 core-seconds**. Even at a perfect 20-worker
split that is ~0.9 s/token ~= 1.1 tok/s. The target needs the per-element cost
to fall ~7x to <= 0.6 cycles/element -- which is impossible for any code the
Quanta SOURCE can express, because every source-level op round-trips memory
(measured and recorded in gguf.quanta's dequant_q4k comment: the through-memory
AVX2 form ran 3.5x SLOWER than the scalar form; "6 memory ops per element ...
the scalar form already does 3 per element and is close to the floor").

The only mechanism that reaches <= 1 cycle/element is a compiler builtin that
keeps the accumulator in ymm across a whole row and never materialises f64
(exactly what llama.cpp's Q4_K/Q6_K dot kernels are). `q4k_matvec`,
`q4k_matvec_avx2` and `q4k_dot` are still `return y` placeholders in 0.0.245
(emitter.quanta ~1716-1826). compiler/** is outside this unit's ownership, so
the fused builtin is SPEC'd below as the hand-off.

### 1b. The multi-cell dot: built, measured, refuted (do NOT rebuild it)

An 8-cell interleaved dot (mm_dot8_s) was built to widen mm_dot4_s's chains.
Two lessons, both now pinned in tests/lfm2_avx2_call_chain_bench.quanta:

1. **fmulf_avx2/faddf_avx2 store 32 bytes (4 f64 lanes) per call.** Accumulator
   cells spaced 8 bytes apart SELF-ALIAS: each store clobbers the next three
   cells. The failure signature (unit-vector probes "dropping" elements 23,
   26-27, 29-31 of every 32; per-group diagnostics showing one call "reading"
   another call's address) looks exactly like a codegen defect and IS NOT ONE
   -- the emitted bytes are identical for every call, and with cells 32 bytes
   apart every sum is exact. The first version of the dot and its first "fix"
   both used 8-byte cells, which is why the failure survived two rewrites.
2. **Corrected, the 8-cell form still loses**: equal-work timing (128 elements
   x 200k reps) gave 8-cell 192.6 ms vs mm_dot4_s 106.0 ms -- 1.8x SLOWER.
   mm_dot4_s's own 4 vector lanes already interleave the dependency chains,
   and the Quanta-level group loop costs more per 4 elements than the extra
   chains save. mm_dot4_s stands; mm_dot8_s was deleted.

## 2. What this unit lands in lib/std (each lever measured before and after)

Ordered by expected yield; the end-to-end metric is tok/s over long
generations, per the measurement contract.

1. **Full-file weight mmap** -- `mm_attach_mmap_fd(fd)` maps the GGUF at offset 0
   (page-aligned by definition) PROT_READ|MAP_PRIVATE with MADV_POPULATE_READ,
   killing ~300k preads + copies per token (~1.2 core-s). Takes an FD, not a
   path: an untyped path parameter loses its string type in transit (defect A7,
   measured in tests/lfm2_generate.quanta).
2. **Mmap row-parallel matvec** (pool kind 4) and **embed path** (kind 5) --
   workers dequantise straight from the mapping with the SAME dq32lo/dq32hi /
   dq6 calls and the SAME summation order: bit-identical output. MEASURED
   bit-identity: 0 mismatches over 131072 Q4_K + 344064 Q6_K elements.
3. **Worker scaling** -- decode today runs the polite ceiling (8). The bench
   driver uses `mm_set_workers_uncapped(n)`; the pool is persistent (A21), so
   VmPeak must not grow. Target 1,600-1,900% CPU during decode.
4. **Norm/conv-kernel caching** (opt-in, `fc_cache_norms()`) -- 82 norm/conv
   tensors re-read per token today; ~2.5 MB one-time cache removes them.
5. **VmPeak contract** (from the SI-loop peer, commit e0d766f6) -- decode
   historically leaked ~11 MB/token of VIRTUAL space (13.1 GB VmPeak by token
   ~1000) while RSS grew only 0.35 MB/token; an 8 GB `ulimit -v` run dies
   mid-generation with zero output (the emitter's MAP_FAILED guard exits(1)
   silently). Consequences folded in: the bench samples VmPeak/VmSize from
   /proc/self/status every run (stability = flat VmPeak over 100+ tokens),
   the run script caps at 32 GB by default, and mm_pool_ensure prints its
   allocation sizes on failure. The bench itself holds the pool across the
   whole run (mm_pool_begin before the run loop), which is the A9 fix.
6. **Embed-dot order change: deliberately NOT taken.** The tied output
   projection's left-to-right scalar dot costs ~2.9 core-s/token; mm_dot4_s
   would cut it ~3x but CHANGES LOGIT BITS, which the bit-identical probes
   (tests/lfm2_prefill_batched_probe.quanta et al.) exist to catch. It is a
   hand-off lever requiring coordinated probe updates, not a silent change.

## 3. The fused builtin spec (hand-off to the compiler owner)

`q4k_row_dot(acc_bits, raw, x, nblocks) -> f64` (and a Q6_K twin
`q6k_row_dot`): one call per ROW. Emitted shape per 32-byte Q4_K plane
(two 32-element sub-blocks, scales sc[2c]/sc[2c+1] unpacked from the 12-byte
table exactly as q4k_sc/q4k_min):

    vpmovzxbd+vpslld+vpsrld (low nibbles)  vpmovzxbd+vpsrld (high nibbles)
    vcvtdq2pd x2      (nibble -> f64, exact)
    vmulpd by x-lane, then by d*sc (pre-broadcast)   -> 4-element group
    vsubpd of (dmin*m)*x  -- or fold x into per-sub-block sums xsub[] so the
    -mm term leaves the inner loop entirely (xsub[k] = sum of 32 x values,
    computed once per matvec, shared by all rows)
    vaddpd into an accumulator ymm that is NOT stored until the row ends

Budget: ~8 uops per 4 elements, all register-resident, no f64 materialisation,
no stores until the horizontal reduction. At 2 fp ports that is 1.0-1.5
cycles per 4 elements => ~0.3 cycles/element => the 36.9 G elem/s target is
inside a single 20-worker run's reach (projected 15-25 tok/s including KV and
attention). Verification requirements are the ones q6k-simd-dequant.md
established: objdump cross-check of every byte, bit-identity against the
scalar row for the DEQUANTISED VALUES, and the argmax oracle end-to-end.

## 3b. The measured end-to-end results and the pool-scaling ceiling

All numbers from tests/lfm2_decode_bench.quanta / tests/lfm2_dispatch_bench.quanta,
argmax temp=0, 20 workers except where stated, load 8-12, governor powersave,
the `Hermes` desktop holding ~580-750% CPU throughout (baseline condition):

| configuration | s/token | tok/s | first argmax | VmPeak/token |
|---|---:|---:|---:|---:|
| old pread path, 1 worker (serial truth) | 17.9 | 0.056 | 597 | -- |
| old pread path, 20 workers | 3.83 | 0.261 | 597 | +12.8 MB |
| mmap + norm cache, 20 workers (this campaign) | **3.49** | **0.286** | **597** (identical) | +1.47 MB |
| ... long generations (ignore_eos, same build): 128 tok | 3.69 | 0.271 | 597 | +4.34 MB |
| ... 512 tok | 3.69 | 0.271 | 597 | +4.37 MB |
| ... 1024 tok | launched; ~63 min wall, not harvested in this unit's window | | | |
| llama.cpp same model/box, 20 threads | 0.058 | **17.32** | -- | -- |

- Rate is context-independent across 128-512 generated tokens (0.271 tok/s
  both) -- the decode cost is weights-dominated at these context lengths, as
  expected while attention stays short.
- Memory, measured over the long runs: anon +0.59-0.65 MB/token and VmPeak
  +4.34-4.37 MB/token on the mmap path (vs 12.8 MB/token VmPeak on the old
  path). NOT flat: a ~4.4 MB/token virtual + ~0.6 MB/token anonymous growth
  remains open, allocator-side (the pool is held across the whole run, so it
  is not the A9 thread-stack class).

- Argmax and generated text are IDENTICAL between old and mmap paths
  (`The answer is 4 ... 4<|im_end|>` on the current reference prompt; the
  first-token argmax on this prompt is 597 on both paths -- the 5922 figure in
  older docs predates the current prompt file).
- The old pread path SIGBUSes (rc=136) on the third reset/prefill cycle in one
  process; the mmap path survived all cycles. VmPeak leaks 12.8 MB/token on
  the old path (reproduces peer commit e0d766f6) vs 1.47 MB/token with mmap --
  better but still growing; open item, allocator-side.

**The pool-scaling ceiling** (tests/lfm2_dispatch_bench, attn_k [512x2048]
per call): serial 8.54 ms -> nw=2 4.75 -> nw=4 3.18 -> nw=8 1.93 -> nw=12
1.82 -> nw=16 1.61 -> nw=20 1.6-2.1 ms. Parallel scaling SATURATES at ~5.3x;
going from 8 to 20 workers gains ~nothing. Per shape at nw=20: gate
[10752x2048] 25.4 ms, down [2048x10752] 18.7 ms -- in-situ slices run ~2.3x
slower than the isolated microbench rates (20-way concurrent weight
streaming), plus ~1.2-1.7 ms fixed dispatch cost per matvec. The complete
model (sum of measured per-dispatch times: 30 layers x (25.4+25.4+18.7+~12+
~5.2 ms) + 8 attention branches + embed ~175 ms) predicts 3.0-3.2 s/token
against 3.49 measured. 18 core-seconds of serial work at a 5.3x scaling cap
= 3.4 s/token: **the pool scaling cap, not the op rates alone, is the second
wall** (the first is the per-element dequant+dot cost, section 1). Reaching
15 tok/s needs BOTH the fused register-resident builtin AND a dispatch
rework (fewer, larger work units -- e.g. fusing the independent gate+up
matvecs into one job, or a per-layer mega-job), which is compiler/lib design
work beyond this unit's ownership.

## 4. Measurement contract (this campaign)

- Metric: end-to-end tok/s over long generations (tests/lfm2_decode_bench.quanta,
  run lengths 128/512/1024, argmax temp=0), plus ms/token min/median/max, and
  memory sampled per run: total Rss (/proc/self/statm), Anon and VmPeak/VmSize
  (/proc/self/smaps_rollup, /proc/self/status) at run start/end plus every 128
  tokens. Stability = anon-RSS flat AND VmPeak flat over 100+ tokens (VmPeak is
  the sizing instrument: see section 2 item 5).
- Oracle: first-token argmax 5922 on the reference prompt (tests/lfm2_prompt.txt)
  and the known-good generation `The answer is: 2<|im_end|>`; token-id prefix of
  every run printed for mechanical diffing.
- Environment line with every number: governor (powersave), load average, top
  CPU consumer. No timed run while a peer model-heavy process is alive
  (`pgrep -af 'lfm2_gen_driver|lfm2_generate.bin|wire.py'` gate -- the run
  script refuses). Load-inflated numbers are labelled. Reference baseline from
  the SI-loop peer (commit e0d766f6, nice -n 19, load 10-18): 7,385-8,570
  ms/token decode; batched prefill 2,428-2,555 ms/prompt-token at B=64.
- The gate (229 native + 112 stdlib) green before any lib/std push. Gate
  result this campaign: 229/229 native + stdlib GREEN (GATE_RC=0), pushed at
  387b868f.

## 5. What a GPU/CUDA follow-up unit can reuse (recorded per the author's sequencing: CPU first, then GPU)

- **The fused dequant-dot kernel shape** (section 3) maps 1:1 onto CUDA: one
  warp per 32-element Q4_K sub-block, scales unpacked exactly as q4k_sc/q4k_min
  (the bit-packing table is in matmul_q4k.quanta and verified against the real
  tensor), x-sub-block sums precomputed per matvec to keep the -min term out of
  the inner loop. The xsub[] trick and the exact scale association are the
  portable content; the AVX2 byte encodings are not.
- **Layout decisions that carry over**: full-file weight mapping (the GPU path
  should cudaMalloc-load each tensor once and address raw quantized bytes, the
  same no-pread principle as mm_attach_mmap_fd); per-worker (per-SM) scratch
  cells of 512 B; row-major matvec with static row partitioning (no atomics --
  Quanta has none and the static-slice rule is also the warp-assignment rule).
- **The benchmark harness** (tests/lfm2_decode_bench.quanta + run script +
  conf) is device-agnostic in shape: three run lengths, ignore_eos for real
  generations, argmax + token-id prefix oracle, Rss/Anon/VmPeak sampling. A GPU
  unit adds VRAM sampling and reuses the same oracle rows.
- **The correctness bar carries over**: bit-identity at the dequantised-value
  level (0-mismatch row diffs vs the scalar path) plus the argmax oracle; the
  llama.cpp same-model CPU (17.32 tok/s) and GPU (~65-95 tok/s) numbers are the
  two reference points the GPU unit should cite rather than re-derive.
- **Do NOT port**: the multi-cell accumulator dot (section 1b -- it loses to
  mm_dot4_s on CPU because of source-level loop overhead; on CUDA the fused
  kernel makes the whole question moot), and the pread row path.
