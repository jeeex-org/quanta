# Decode campaign: fused dequant-dot, mmap, worker scaling -- measured plan

Status: in progress, 0.0.245, lib/std + tests ownership only (compiler/** untouched).
Goal handed down: decode at >= 15 tok/s (<= 66 ms/token) on
QUANTA-LFM2.5-2.6Bv1-Q4_K_M.gguf, validated by large-scale end-to-end runs.

## 0. The verified premise (bytes/element arithmetic, from the file itself)

Parsed straight from the GGUF header (266 tensors, GGUF v3):

- total 2.6972G elements, 1.6662 GB
- **matvec elements per decode token (every blk.* tensor + tied output):
  2.4351G elements = 1.4512 GB of weight bytes read per token**
- dtype split of that per-token work: Q4_K 1.766G elems (72.5%),
  Q6_K 669M elems (27.5%), F32 norm/conv tails ~10M
- token_embd (Q6_K, 262.1M) is looked up once per token (1 row), not matvec'd

Arithmetic of the target:

- 15 tok/s => 66 ms/token => weight streaming 1.4512 GB / 0.066 s = **22.0 GB/s**
  (plus KV reads), against the llama.cpp-proven envelope of ~36 GB/s on this box
  (7.5B model at 8.24 tok/s). The bandwidth premise HOLDS.
- compute side: 2.4351G element-ops / 0.066 s = **36.9 G elem/s**. Across 20 cores
  that is 1.84 G elem/s/core = **0.66-0.84 cycles/element** at the powersave clock
  (2.2-2.8 GHz). That is llama.cpp-class hand-written-AVX2 territory.

## 1. The measured wall (why lib/std alone cannot reach 15)

Authoritative serial per-op costs, all measured on this box
(tests/lfm2_op_profile.quanta; docs/research/prefill-batching.md and
q6k-simd-dequant.md):

| component | rate | per decode token |
|---|---:|---:|
| Q4_K dequant (dq32lo/hi, bit-exact) | ~3.5-4.1 ns/elem | 1.766G -> 6.2-7.2 core-s |
| Q6_K dequant (dq6, bit-exact) | ~2.0 ns/elem | 0.931G -> 1.9 core-s |
| dot (mm_dot4, single 4-lane chain) | 2.73 ns/elem | 2.435G -> 6.6 core-s |
| row pread (page cache) | ~0.5 ns/elem | 2.435G -> 1.2 core-s |
| non-matvec (norms, silu, attention, residuals) | measured 0.3% serial | ~0.05 core-s |

Serial-equivalent decode token: **~16 core-seconds**. Even at a perfect 20-worker
split that is 800 ms/token = 1.25 tok/s. The target needs the per-element cost
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

## 2. What this unit lands in lib/std (each lever measured before and after)

Ordered by expected yield; the end-to-end metric is tok/s over long
generations, per the measurement contract.

1. **Full-file weight mmap** -- `mm_attach_mmap(path)` maps the GGUF at offset 0
   (page-aligned by definition) PROT_READ|MAP_PRIVATE with MADV_POPULATE_READ,
   killing ~300k preads + copies per token. Workers get raw row pointers
   instead of fd + offset. Bit-exact: same bytes, same dequant calls.
2. **Mmap row-parallel matvec** (pool kind 4) -- worker dequantises its row
   straight from the mapping with the SAME dq32lo/dq32hi / dq6 calls and dots
   with the SAME mm_dot4_s order: bit-identical output, no fd, no shared rowbuf.
3. **8-lane dot** (`mm_dot8_s`) -- the mm_dot4 dependency chain is one
   store-to-load-forward serial chain (~6 cycles/iteration); 8 interleaved
   accumulator cells hide it. Projection: 2.73 -> ~0.4-0.8 ns/elem. NOT
   bit-identical (different summation order): gated behind `mm_dot_multi`
   (default 0) and validated by the argmax oracle before being enabled in a
   measured run.
4. **Worker scaling** -- decode today runs the polite ceiling (8). The bench
   driver uses `mm_set_workers_uncapped(n)`; the pool is persistent (A21), so
   RSS must not grow. Target 1,600-1,900% CPU during decode.
5. **Norm/conv-kernel caching** (opt-in, `fc_cache_norms()`) -- 60 norm tensors
   + 22 conv kernels are re-read per token today (~82 preads + conversions);
   ~2.1 MB one-time cache removes them.
6. **Embedding-logits mmap path** (pool kind 5) -- the tied output projection is
   262.1M elems/token; keep the left-to-right scalar order (bit-identical), drop
   the preads. A dot-order change here is part of lever 3's validation.

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

## 4. Measurement contract (this campaign)

- Metric: end-to-end tok/s over long generations (tests/lfm2_decode_bench.quanta,
  run lengths 128/512/1024, argmax temp=0), plus ms/token median, RSS
  (Rss + Anon from /proc/self/statm and smaps_rollup) at run start/end -- anon
  RSS must be flat across 100+ tokens.
- Oracle: first-token argmax 5922 on the reference prompt (tests/lfm2_prompt.txt)
  and the known-good generation `The answer is: 2<|im_end|>`; token-id prefix of
  every run printed for mechanical diffing.
- Environment line with every number: governor (powersave), load average, top
  CPU consumer. No timed run while a peer model-heavy process is alive
  (`pgrep -af 'lfm2|wire.py'` gate). Load-inflated numbers are labelled.
- The gate (229 native + 112 stdlib) green before any lib/std push.
