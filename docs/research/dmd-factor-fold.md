# DMD factor fold: the fused JIT dot's integrated win, 2.99x -> 12.69x

Status: **DONE and committed** (`42134f2e`), lib/std + tests + this doc only,
`compiler/**` untouched. 0.0.245. Gate GREEN (0 FAIL, GATE_RC=0).

Supersedes the "the DMD build is 70-84% of the fused cost" section of
`docs/research/jit-fused-dot-status.md`, whose *premise* this reproduces and
whose *conclusion* (a per-tensor cache is the natural next lever) this
measurement overturns.

## 0. The lever, in one line

The per-row scalar DMD build was eating 77-80% of the fused JIT dequant-dot
path, so the fused kernel's 13x on its own dot pair bought only ~3x integrated.
Deriving those factors **inside the kernel in SIMD** — no table, no per-row
build — moves the integrated win to **12.7x, which is 94-96% of the kernel's own
ratio**, at zero extra memory.

## 1. Premise, reproduced on this box (before the change)

`tests/lfm2_jit_mm_test.quanta`, 64 real FFN-gate Q4_K rows, best of 4,
governor `powersave`, load 8.6, `Hermes` holding ~750% CPU:

    A prod (mm_deq_row_raw + mm_dot4_s) : 1,226,920
    B dmd_build_only                   :   323,104
    C table_kernel_only                :   110,129
    D table build+kernel (INTEGRATED)  :   396,272
    A/D 3.09x   A/C 11.14x   dmd_share(D) 81%
    BITIDENT fused_vs_mm_deq+dot4: mismatches=0 / 64

This reproduces the recorded 2.79x / 10.87x / 75% row. The build is **81% of
the fused path** and the kernel alone is 11x: the fusion was delivering almost
none of its own win.

Why it is so expensive — check this against the source, because it decides the
fix: `jit_f_dmd_fill` (`lib/std/jit_x86_fused.quanta`) runs 8 iterations per
256-weight super-block, each doing `q4k_sc_jit`/`q4k_min_jit` bit extraction
with integer divisions, plus `i2f` + `fmul` + `mem_store` ×2. Per the cost model
in `quanta-cpu-perf` every Quanta float builtin call round-trips the frame at
~4.4 ns / ~14 cycles, so ~16 builtin calls + 16 integer divisions per
super-block is O(weights) scalar work **inside the loop fusion exists to make
cheaper**. It is not memory traffic; it is builtin-call and integer-division
overhead in Quanta source.

## 2. Option 1 — fold the factors into the kernel (CHOSEN)

New `jit_f_build_folded()` in `lib/std/jit_x86_fused.quanta`. The kernel's quant
cursor `r9` points at the 128 quant bytes, so the 144-byte super-block header is
at `r9-16..r9-1`: `f16 d`, `f16 dmin`, 12 packed scale/min bytes. Per
super-block the kernel now does (27 instructions, once per 256 weights):

    vmovd xmm3, [r9-16]        4 header bytes
    vcvtph2ps xmm3, xmm3       f16 -> f32  (exact: f16's 11-bit significand fits f32)
    vcvtps2pd ymm3, xmm3       f32 -> f64  (exact)
    vpermpd ymm8/ymm9          broadcast d / dmin
    vpmovzxbd xmm4/5/6         sc[0..3] / sc[4..7] / sc[8..11] as 4 dwords each
    shifts + vpor              the q4k_sc/q4k_min 6-bit unpack, per dword
    vcvtdq2pd + vmulpd         ymm12=[d*sc0..3] ymm13=[d*sc4..7]
                               ymm14=[dmin*mn0..3] ymm15=[dmin*mn4..7]

and then one `vpermpd` per half of each chunk to broadcast the pair that half
needs (`0x00/0x55/0xAA/0xFF` = lane 0/1/2/3). Two secondary wins fall out:

- the 128-byte-per-super-block DMD table and its memory traffic disappear, and
- the table kernel emits **8 redundant `vbroadcastsd` per half** (the same pair
  re-broadcast on every 4-byte step, 8× per half × 2 halves × 4 chunks = 32 per
  chunk). The folded kernel emits one broadcast per half — 4 per chunk.

The 6-bit unpack, expressed with shifts instead of mask registers so no constant
pool is needed (`(x<<26)>>26 == x&63`, `(x<<28)>>28 == x&15`), is exactly
`q4k_sc`/`q4k_min` (`lib/std/matmul_q4k.quanta:45,:51`) and `mm_deq_row_raw`'s
use of them:

    scales[0..3] = sc[0..3] & 63          scales[4..7] = (sc[8..11] & 15) | ((sc[0..3] >> 6) << 4)
    mins  [0..3] = sc[4..7] & 63          mins  [4..7] = (sc[8..11] >> 4) | ((sc[4..7] >> 6) << 4)

Args area `[W, X, DMD, nsuper]`, the 144-byte stride, one row per call and
`a0`-in-`rdi` are all unchanged; `[rdi+16]` is simply not read any more.

### The one real bug, and the diagnostic that caught it

The first implementation used **`vpermilpd`** for the broadcast, with imm
`0x00/0x55/0xAA/0xFF`. Every byte was produced by GNU `as` and read back out of
`objdump -d`, and the encodings were correct — and the factors were still
wrong, 64/64 rows.

`tests/jit_fold_probe.quanta` (NEW) dumps the four factor vectors as raw f64 bit
patterns next to what `q4k_sc`/`q4k_min` + `f16_to_f64` say they must be, and
showed `ymm8 = [d, d, 0, 0]`. That is the signature: **VPERMILPD's imm8
selectors are LANE-RELATIVE** — each 2-bit field picks a source element inside
the destination's own 128-bit half — so imm `0x00` yields `[s0,s1,s0,s1]`, not a
broadcast. Only factor lanes 0 and 1 of each vector were ever right, which is
why `SC_lo` came out `[63, 0, 0, 0]` instead of `[63, 0, 63, 1]`.

`vpermpd ymm1, ymm2, imm8` IS a cross-lane 4-element permute, so a repeated
2-bit selector broadcasts. After the swap the probe reports `factor mismatch
lanes=0` on all 32 lattice values and exact lane selection for all 8 chunk
halves.

Worth recording as a general trap: **"assembles and disassembles exactly as
intended" is not evidence that an instruction means what you think.** The ISA
was consulted only after the emitted code was measured against an oracle.

## 3. Measurements (after the change)

`tests/jit_dmd_fold_test.quanta`, real FFN-gate Q4_K rows, interleaved best-of.
Bit-identity is asserted **before** any timing, in every configuration.
Governor `powersave`; load 9.8; `Hermes` ~750% CPU permanently. Two runs, three
row counts.

**Correctness (both runs):**

    BITIDENT table_vs_mm   : mismatches=0 / 512
    BITIDENT folded_vs_mm  : mismatches=0 / 512
    (folded run with the DMD arg slot ZEROED -- it must not need a table)

| run | rows | A prod | B build | C table-kernel | D table+build | E FOLDED | F cache-amort | A/D | A/C | **A/E** | A/F | B/D |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 64 | 1,169,258 | 231,888 | 66,129 | 296,010 | 69,962 | 66,972 | 3.95x | 17.68x | **16.71x** | 17.45x | 78% |
| 1 | 256 | 3,461,651 | 859,462 | 237,650 | 1,109,438 | 249,720 | 239,299 | 3.12x | 14.56x | **13.86x** | 14.46x | 77% |
| 1 | 512 | 6,509,401 | 4,201,457 | 957,976 | 5,217,572 | 1,022,546 | 482,209 | 1.24x | 6.79x | **6.36x** | 13.49x | 80% |
| 2 | 64 | 1,191,175 | 530,777 | 137,142 | 673,802 | 142,526 | 138,724 | 1.76x | 8.68x | **8.35x** | 8.58x | 78% |
| 2 | 256 | 4,467,828 | 890,961 | 246,415 | 1,142,147 | 261,896 | 248,301 | 3.91x | 18.13x | **17.05x** | 17.99x | 78% |
| 2 | 512 | 8,370,465 | 4,392,356 | 998,561 | 5,596,602 | 1,043,690 | 841,923 | 1.49x | 8.38x | **8.02x** | 9.94x | 78% |

`E`/`F` sweep **distinct** rows; `C` re-reads row 0 — that is why `A/C` is the
largest column and is an upper bound on kernel-alone, not a like-for-like
partner for `E`.

**What is robust across all six measurements (and what is not):**

- `A/D` (`D` = the OLD integrated path) and `A/C` swing 1.24-3.95x and 6.79-18.13x
  with load — the recorded load-sensitivity of this box, not a property of the
  lever. Do not quote one of them as a constant.
- **Within any single run, the lever is worth 4.2-5.4x on the integrated fused
  dot:** E beats D by 4.23x / 4.44x / 5.10x / 4.74x / 4.36x / 5.36x in the six
  rows above.
- **`E/C` = 0.936-0.962 in every run:** the folded kernel, with NO build at all,
  is within 4-6% of the table kernel alone. The integrated ratio therefore
  approaches kernel-alone as asked — `A/E` is 94-96% of `A/C`.
- `B/D` (the DMD share) is 77-80% in every run: the eliminated cost is real and
  large.
- `E/F` = 0.957-0.973: the folded kernel recovers 95.7-97.3% of what a
  **prebuilt** table gives, with no table.

The first clean run (rows=64) is the headline: **A/D 2.99x -> A/E 12.69x, against
A/C 13.34x.** The corresponding `tests/lfm2_jit_mm_test.quanta` before/after on
this box is A/D 3.09x -> A/C 11.14x with the same kernel that now folds.

## 4. Option 2 — a persistent per-tensor DMD cache (LOSING)

Measured, not argued. `tests/jit_dmd_fold_test.quanta` section F builds every
row's DMD once into a row-sized table and then sweeps the table kernel over all
rows with no build inside the timed loop — exactly what a per-tensor cache buys
across decode tokens. It gives `A/F` = 8.58-17.99x, i.e. **95.7-97.3% of what
option 1 already gives** (see `E/F`), for 1 GB.

**Cache size, from the model's OWN metadata** (`gguf_num_tensors` +
`gguf_tensor_nelements`, dtype 12), not from a doc: 266 tensors,
**q4k_elems = 2,122,317,824**, so `q4k_elems/256 * 128 = 1,061,158,912 B =
1012 MB`. (The per-token Q4_K working set is smaller — 1.766G elems ≈ 883 MB —
but a per-tensor cache covers all Q4_K weights.)

**Memory verdict, measured** by `tests/jit_dmd_cache_mem_probe.quanta`
(`gguf_load` + full-file `mm_attach_mmap_fd`, then allocate + touch the cache):

| VA cap | result | Max RSS (`/usr/bin/time -v`) |
|---|---|---|
| `ulimit -v 8000000` (8 GB — the cap the rest of this work runs under) | **dies inside `mem_alloc`**, no output at all, not even the `phase=allocated` line | 1,707,476 KB = 1.63 GB (the model alone) |
| `ulimit -v 32000000` (32 GB — what `tests/run_lfm2_decode_bench.sh` uses) | `phase=touched` / `OK` | 2,743,672 KB = 2.62 GB |

So: **it does not fit under the 8 GB cap and it does fit under the 32 GB cap,
where it costs a measured ~1.0 GB of resident memory** (2.62 - 1.63 GB) on a
path whose VmPeak already leaks 4.37 MB/token (13.54 GB at 1024 tokens). The
8 GB failure is silent — the emitter's `MAP_FAILED` guard `exit(1)`s with no
message, the failure mode `quanta-cpu-perf` already records.

**Decision: option 1.** It captures 95.7-97.3% of the cache's benefit at **zero
extra bytes** and with no lifetime/eviction question (the cache has to be built,
keyed and invalidated per tensor, and its 1012 MB is permanent). The cache
remains the right answer only if a future unit has a ~1 GB resident budget to
spend and wants the last ~3% — record it as a lever, not a plan.

## 5. Gate

`bash test_suites/scripts/run_tests.sh` with the peer's `run_tests.sh` clear:
**GATE_RC=0, 0 FAIL, all sections GREEN** (functional, native, float-*, extern-*,
security, performance, valgrind, fuzz, differential, generics, stdlib, multi-tu,
gguf-corrupt, verify-status, qobj, output-path, naked, asm-assembler, bare-metal,
float-print).

The new tests are **NOT** wired into the gate manifest, deliberately and
consistently: neither `tests/lfm2_jit_mm_test.quanta` nor any other `tests/jit_*`
is a manifest row, they need the 1.67 GB model and a 32 GB VA cap, and the
manifest is a single-writer shared file. They are run by hand; the commands are
in each file's header.

## 6. Honest remaining gap and the next lever

- **This is a microbenchmark of the dot. It is not a tok/s number and must not
  be reported as one.** `clock()`'s absolute unit is still UNVERIFIED — only
  ratios are trustworthy.
- The fused kernel **still cannot be dispatched from an imported module**: the
  peer unit's `closure_call` fix is the gate on that, and `jit_f_setup` /
  `jit_f_ready` / `jit_f_apply` in `jit_x86_fused.quanta` are still marked
  BLOCKED and untouched. Every number here was taken by dispatching inline in
  `main`, which is the only shape the defect permits.
- Q4_K is only part of the per-token work: the tied **Q6_K** output projection
  and the Q6_K down-projection are not covered by this kernel at all. There is
  no `q6k` folded twin; that is a separate lever of the same shape.
- The other wall this campaign named is untouched: **pool scaling saturates at
  ~5.3x** and the ~774-811% CPU ceiling. With the Q4_K dot now worth 4.2-5.4x
  integrated instead of ~2.8x, the dispatch/bandwidth cap is the larger
  remaining term.
- The **table** kernel still emits its 8 redundant `vbroadcastsd` per half.
  Hoisting them is a cheap ~12%-of-body win *for that kernel* and was
  deliberately not done: it would move the committed baseline this unit
  measured against, and one lever per version. Queued, not taken.
- `tests/jit_dmd_fold_test.quanta` reports `best of 4` / `best of 3` at three
  row counts, but the box cannot resolve sub-15% effects sequentially; the
  within-run pairs (`E` vs `D`, `E` vs `C`, `E` vs `F`) are the evidence, and
  the absolute ratios are quoted with the load beside them.
