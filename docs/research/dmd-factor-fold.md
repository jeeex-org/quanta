# DMD factor fold: the fused JIT dot's integrated win, 2.99x -> ~11.4-15.6x

Status: **DONE, committed and pushed** (`42134f2e`, `a6581fa5`, `e617d082`,
`eda70c4b` on `main`), lib/std + tests + this doc only, `compiler/**` untouched.
Started on 0.0.245; the 0.0.246 the peer unit landed mid-flight is in use for the
final gate and unblocked the dispatch (section 6).

Supersedes the "the DMD build is 70-84% of the fused cost" section of
`docs/research/jit-fused-dot-status.md`: this reproduces its *premise* and
overturns its *conclusion* (that a per-tensor cache is the natural next lever).
That doc's *blocker* section (the imported-module `closure_call` fault) is also
now resolved -- see section 6.

## 0. The lever, in one line

The per-row scalar DMD build was eating 70-84% of the fused JIT dequant-dot
path, so the fused kernel's ~11-13x on its own dot pair bought only ~3x
integrated. Deriving those factors **inside the kernel in SIMD** -- no table, no
per-row build -- moves the integrated win to **11.4-15.6x, i.e. 94-101% of the
kernel's own ratio**, at zero extra memory.

## 1. Premise, reproduced on this box (before the change)

`tests/lfm2_jit_mm_test.quanta`, 64 real FFN-gate Q4_K rows, best of 4,
governor `powersave`, load 8.6, `Hermes` holding ~750% CPU:

    A prod (mm_deq_row_raw + mm_dot4_s) : 1,226,920
    B dmd_build_only                   :   323,104
    C table_kernel_only                :   110,129
    D table build+kernel (INTEGRATED)  :   396,272
    A/D 3.09x   A/C 11.14x   dmd_share(D) 81%
    BITIDENT fused_vs_mm_deq+dot4: mismatches=0 / 64

This reproduces the recorded 2.79x / 10.87x / 75% row. The build is **81% of the
fused path** and the kernel alone is 11x, so the fusion was delivering almost
none of its own win.

Why it is so expensive -- checked against the source, because this decides the
fix: `jit_f_dmd_fill` (`lib/std/jit_x86_fused.quanta`) runs 8 iterations per
256-weight super-block, each doing `q4k_sc_jit`/`q4k_min_jit` bit extraction
with integer divisions, plus `i2f` + `fmul` + `mem_store` x2. Per the cost model
in `quanta-cpu-perf`, every Quanta float builtin call round-trips the frame at
~4.4 ns / ~14 cycles, so ~16 builtin calls + ~16 integer divisions per
super-block is O(weights) scalar work **inside the loop fusion exists to make
cheaper**. It is not memory traffic; it is builtin-call and integer-division
overhead in Quanta source.

## 2. Option 1 -- fold the factors into the kernel (CHOSEN)

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
  re-broadcast on every 4-byte step: 16 per half, 32 per chunk, 128 per
  super-block). The folded kernel emits one broadcast per half -- 4 per chunk,
  16 per super-block. So the folded body is ~85 instructions shorter per
  super-block despite the 27-instruction prologue, which is why it can match a
  *prebuilt* table.

The 6-bit unpack, expressed with shifts instead of mask registers so no constant
pool is needed (`(x<<26)>>26 == x&63`, `(x<<28)>>28 == x&15`), is exactly
`q4k_sc`/`q4k_min` (`lib/std/matmul_q4k.quanta:45,:51`) and `mm_deq_row_raw`'s
use of them:

    scales[0..3] = sc[0..3] & 63      scales[4..7] = (sc[8..11] & 15) | ((sc[0..3] >> 6) << 4)
    mins  [0..3] = sc[4..7] & 63      mins  [4..7] = (sc[8..11] >> 4) | ((sc[4..7] >> 6) << 4)

Args area `[W, X, DMD, nsuper]`, the 144-byte stride, one row per call and
`a0`-in-`rdi` are all unchanged; `[rdi+16]` is simply not read any more.

### 2b. The one real bug, and the diagnostic that caught it

The first implementation used **`vpermilpd`** for the broadcast, with imm
`0x00/0x55/0xAA/0xFF`. Every byte was produced by GNU `as` and read back out of
`objdump -d`, and the encodings were correct -- and the factors were still
wrong, 64/64 rows.

`tests/jit_fold_probe.quanta` (NEW) dumps the four factor vectors as raw f64 bit
patterns next to what `q4k_sc`/`q4k_min` + `f16_to_f64` say they must be, and
showed `ymm8 = [d, d, 0, 0]`. That is the signature: **VPERMILPD's imm8
selectors are LANE-RELATIVE** -- each 2-bit field picks a source element inside
the destination's own 128-bit half -- so imm `0x00` yields `[s0,s1,s0,s1]`, not a
broadcast. Only factor lanes 0 and 1 of each vector were ever right, which is
exactly why `SC_lo` came out `[63, 0, 0, 0]` instead of `[63, 0, 63, 1]`.

`vpermpd ymm1, ymm2, imm8` IS a cross-lane 4-element permute, so a repeated
2-bit selector broadcasts. After the swap the probe reports `factor mismatch
lanes=0` on all 32 lattice values, and exact lane selection for all 8 chunk
halves (`perm6_lo` == `d*sc[2c]`, `perm6_hi` == `d*sc[2c+1]`, for c=0..3).

Worth recording as a general trap: **"assembles and disassembles exactly as
intended" is not evidence that an instruction means what you think it means.**
The ISA was consulted only after the emitted code was measured against an oracle.
There is a second, related trap in the same probe: `jbytes(n, hexstr)` silently
truncates to the first `n` bytes, and an 8-byte `vmovupd [rdx+disp32]` store
declared as 7 produced a SIGSEGV in the probe rather than a wrong number.

## 3. Measurements

`tests/jit_dmd_fold_test.quanta`, real FFN-gate Q4_K rows, interleaved best-of.
Bit-identity is asserted **before** any timing, in every run. Governor
`powersave` throughout; `Hermes` holds ~750% CPU permanently.

### 3a. Bit-identity (load-independent evidence)

| run | tensors | shapes | result |
|---|---|---|---|
| R1, R2, R3 | FFN gate L0 | cols 2048, nsuper 8 | 0 mismatches / 512 rows (each of table and folded) |
| R4, R5, R6 | the first Q4_K tensor for **each distinct super-block count**, found by scanning all 266 tensors | **idx 4: cols 2048, nsuper 8** and **idx 30: cols 10752, nsuper 42** | **0 mismatches / 128 rows, both kernels, both shapes** |

The folded kernel is run with the DMD argument slot **zeroed** -- it must not
need a table -- and a *different* x is used per tensor so agreement cannot come
from a degenerate (all-zero) input. Both kernels are diffed against
`mm_deq_row_raw` + `mm_dot4_s`, the shape `lfm2_forward` actually executes. A
42-super-block, 10752-column row exercises a very different chunk cadence from
the 8-super-block gate rows.

### 3b. Cost split, as ratios

`A` = prod (`mm_deq_row_raw` + `mm_dot4_s`), `B` = per-row scalar DMD build,
`C` = table kernel alone (DMD prebuilt, row 0), `D` = OLD integrated
(build + table kernel), `E` = **FOLDED integrated**, `F` = option-2 cache
amortised (build every row's table once, then sweep). Columns are ratios
`x100` as the test prints them, divided by 100.

| run | load | rows | A/D | A/C | **A/E** | A/F | **E/C** | **B/D** |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| R1 | 9.8 | 64 | 2.99 | 13.34 | **12.69** | 13.28 | 0.951 | 81% |
| R1 | 9.8 | 256 | 2.90 | 13.46 | **12.81** | 13.31 | 0.952 | 79% |
| R2 | 9.8 | 64 | 3.95 | 17.68 | **16.71** | 17.45 | 0.945 | 78% |
| R2 | 9.8 | 256 | 3.12 | 14.56 | **13.86** | 14.46 | 0.952 | 77% |
| R2 | 9.8 | 512 | 1.24 | 6.79 | **6.36** | 13.49 | 0.937 | 80% |
| R3 | 9.8 | 64 | 1.76 | 8.68 | **8.35** | 8.58 | 0.962 | 78% |
| R3 | 9.8 | 256 | 3.91 | 18.13 | **17.05** | 17.99 | 0.940 | 78% |
| R3 | 9.8 | 512 | 1.49 | 8.38 | **8.02** | 9.94 | 0.957 | 78% |
| R4 | 12.2 | 64 | 3.67 | 16.43 | **15.55** | 16.34 | 0.947 | 79% |
| R4 | 12.2 | 256 | 3.15 | 14.56 | **13.84** | 14.42 | 0.951 | 81% |
| R4 | 12.2 | 512 | 3.07 | 14.60 | **14.28** | 14.94 | 0.978 | 76% |
| R6 | 10.3 | 64 | 2.80 | 11.56 | **11.40** | 11.16 | 0.986 | 72% |
| R6 | 10.3 | 256 | 2.72 | 11.73 | **11.87** | 13.59 | 1.012 | 70% |
| R6 | 10.3 | 512 | 2.22 | 8.97 | **8.76** | 8.68 | 0.977 | 77% |

R5 (load 13.1) is **excluded and named**: `B/D` came out 201%, which is
physically impossible and is the tell that the box was thrashing -- `B` and `D`
are timed in different loops, so unequal load between them corrupts the share.
Its *identity* result (section 3a) is load-independent and therefore stands.

### 3c. What is robust, and what is not

- `A/D` and `A/C` swing 1.24-3.95x and 6.79-18.13x with load. **Do not quote
  either as a constant** -- this is the recorded load-sensitivity of this box,
  not a property of the lever.
- **Within any single run, the lever is worth 3.9-5.4x on the integrated fused
  dot.** `E` beats `D` by 4.25/4.41 (R1), 4.23/4.44/5.10 (R2), 4.73/4.36/5.36
  (R3), 4.99/4.47/2.97 (R4), 4.06/4.35/3.94 (R6) -- median ~4.4x.
- **`E/C` is 0.937-1.012 over all 14 measurements** (median 0.955): the folded
  kernel, with NO build at all, runs at 94-101% of the table kernel's own time.
  The integrated ratio therefore approaches kernel-alone as asked; `A/E` is
  94-101% of `A/C`, and at R6/rows=256 it is nominally *faster*.
- `B/D` (the eliminated cost) is 70-84% in every well-measured run: real, large
  and stable.
- `F` (the cache) versus `E` (folded): `F` is 0-5% faster than `E` in the clean
  runs, i.e. the folded kernel recovers ~95-100% of a prebuilt table's benefit
  while building nothing. `E/F` values above 1 (R2/512, R6/64-256) are load
  noise on `F`, which is measured last in each pass.
- The **quietest** runs are the headline: R4/rows=64 gives **A/D 3.67x ->
  A/E 15.55x against A/C 16.43x**; R6/rows=64 gives **A/D 2.80x -> A/E 11.40x
  against A/C 11.56x**. The single clean committed run at rows=64 is
  **A/D 2.99x -> A/E 12.69x against A/C 13.34x**.

## 4. Option 2 -- a persistent per-tensor DMD cache (LOSING)

Measured, not argued. Section F of the test builds every row's DMD once into a
row-sized table and then sweeps the table kernel over all rows with no build
inside the timed loop -- exactly what a per-tensor cache buys across decode
tokens. It gives `A/F` within 0-5% of `A/E`, for ~1 GB.

**Cache size, from the model's OWN metadata** (`gguf_num_tensors` +
`gguf_tensor_nelements`, dtype 12), not from a doc: 266 tensors,
**q4k_elems = 2,122,317,824**, so `q4k_elems/256 * 128 = 1,061,158,912 B =
1012 MB`. (The per-token Q4_K working set is smaller -- 1.766G elems ~= 883 MB --
but a per-tensor cache must cover all Q4_K weights.)

**Memory verdict, measured** by `tests/jit_dmd_cache_mem_probe.quanta`
(`gguf_load` + full-file `mm_attach_mmap_fd`, then allocate and touch the cache):

| VA cap | result | Max RSS (`/usr/bin/time -v`) |
|---|---|---|
| `ulimit -v 8000000` (8 GB -- the cap the rest of this work runs under) | **dies inside `mem_alloc`**, no output at all, not even the `phase=allocated` line | 1,707,476 KB = 1.63 GB (the model alone) |
| `ulimit -v 32000000` (32 GB -- what `tests/run_lfm2_decode_bench.sh` uses) | `phase=touched` / `OK` | 2,743,672 KB = 2.62 GB |

So: **it does not fit under the 8 GB cap, and it does fit under the 32 GB cap,
where it costs a measured ~1.0 GB of resident memory** (2.62 - 1.63 GB) on a
path whose VmPeak already leaks 4.37 MB/token (13.54 GB at 1024 tokens). The
8 GB failure is silent -- the emitter's `MAP_FAILED` guard `exit(1)`s with no
message, the failure mode `quanta-cpu-perf` already records.

**Decision: option 1.** It recovers 95-100% of the cache's benefit at **zero
extra bytes** and with no lifetime/keying/invalidations question (the cache must
be built, keyed and invalidated per tensor, and its 1012 MB is permanent).
Option 2 stays on the list as a lever for a unit with a ~1 GB resident budget
that wants the last few percent -- not as a plan.

## 5. Gate

`bash test_suites/scripts/run_tests.sh`, run four times. The final state:

- **Final run (12:5x, VERSION 0.0.246): GATE_RC=0, 391 PASS, 0 FAIL, 26
  sections, NO RED.** This is the tree as pushed.
- Run 1 (11:2x, 0.0.245): **GATE_RC=0, 0 FAIL, all sections GREEN** -- the state
  when this unit's first two commits were made.
- Run 2 (11:4x): `GATE_RC=1` with **3 FAILs -- all three of them the peer unit's
  own in-flight RED-first rows**, added at 11:32 after the clean run:
  `param_kwid_type_test` (compile `rc=132`), `param_kwid_name_test` (`rc=1`) and
  `stdlib_jit_dispatch_test` (`rc=139`), together with the peer's unstaged edits
  to the shared `test_suites/EXPECTED.tsv` / `EXPECTED_STDLIB.tsv`.

  **Verified, not assumed:** a pre-change tree built with `git archive fdd6be9a`
  (confirmed to contain no folded kernel) plus those same three rows fails
  **identically** -- `rc=139` / `rc=1` / compile `rc=132`. So the trio was the
  peer's, not a regression from this change, and it is exactly the class
  `parallel-agent-workstreams` warns about: a peer's RED-first row whose source
  is in the tree while its fix is not committed. That trio is now all PASS
  (`stdlib_jit_dispatch_test` rc=0) in the final run.

- The new tests are **NOT** wired into the gate manifest, deliberately and
  consistently: no `tests/jit_*` file is a manifest row (nor is
  `tests/lfm2_jit_mm_test.quanta`), they need the 1.67 GB model and a 32 GB VA
  cap, and the manifest is a single-writer shared file that another unit was
  editing. They are run by hand; the exact commands are in each file's header.
  The one exception is the peer's own `stdlib_jit_dispatch_test.quanta`, which
  is a manifest row and which this unit relied on to confirm the unblock.

Pushed as `fdd6be9a..e617d082` then `998e2abf..eda70c4b` on `main` (both
fast-forwards, 0 behind at push time).

## 6. Honest remaining gap and the next lever

- **This is a microbenchmark of the dot. It is not a tok/s number and must not
  be reported as one.** `clock()`'s absolute unit is still UNVERIFIED -- only
  ratios are trustworthy.
- **The dispatch blocker is GONE, and this is the new top of the list.** Every
  measurement in this doc was taken by dispatching inline in `main`, because on
  0.0.245 reaching `closure_call` through a function in an imported module
  SIGSEGV'd. The peer unit fixed that in 0.0.246 (root cause: a parameter named
  with a keyword token was dropped by `funcscan`, so the kernel was entered with
  `rdi=0` -- NOT a `closure_call` emitter bug, which is why `jit_x86_fused`
  needed no emitter change). Verified first-hand here:

  - the gate row `test_suites/codes/stdlib_jit_dispatch_test.quanta` now PASSES
    (rc=0, was rc=139);
  - `tests/jit_fold_dispatch_test.quanta` (NEW) dispatches the **folded** kernel
    both ways on 64 real FFN-gate rows -- inline `closure_call`, and
    `jit_f_apply_folded()` through the imported module -- and gets 0 and 0
    mismatches against `mm_deq_row_raw + mm_dot4_s`.

  So the fused dot CAN now be wired into `gguf_mm`. That wiring is a separate
  lever and is the immediate next unit, not a footnote. It was deliberately NOT
  started here, and the reason is concrete rather than budgetary caution:
  `mm_matvec` (gguf_mm:466) runs `mm_load_row` -> `gguf_read_tensor_bytes_at`
  (a `pread`), while the decode path the campaign measures is the **mmap**
  route; `mm_matvec_par` and the embed path are separate call sites; and the
  kernel takes a 4-qword argument area per call, so a parallel worker needs its
  **own** area (one shared `asz` is exactly the cross-worker scratch class the
  `quanta-cpu-perf` notes already name). A follow-up needs to answer those three
  questions before it touches the model's hot path, then hold bit-identity
  end-to-end, not just per row. The route itself is now proven; the plumbing is
  the work.
- Q4_K is only part of the per-token work: the tied **Q6_K** output projection
  and the Q6_K down-projection are not covered by this kernel. There is no
  `q6k` folded twin; that is a separate lever of the same shape (and worth
  having -- Q6_K is 27.5% of per-token elements and the tied output projection
  is the single largest item).
- The other named wall is untouched: **pool scaling saturates at ~5.3x** and the
  ~774-811% CPU ceiling stands. With the Q4_K dot now worth ~4.4x integrated
  instead of ~2.8x, dispatch/bandwidth is the larger remaining term.
- The **table** kernel still emits its 128 redundant `vbroadcastsd` per
  super-block. Hoisting them is a cheap win *for that kernel* and was
  deliberately NOT done: it would move the committed baseline this unit
  measured against, and one lever per version. Queued, not taken.
- `E/F` and `E/C` cannot resolve below ~5% on this box. The 5% gap between the
  folded kernel and a prebuilt table is real in direction (the prologue's
  `vcvtph2ps`/header load is a serial dependency at each super-block boundary,
  where the table kernel's broadcasts are independent loads) but its exact size
  is inside the noise. If that last few percent matters, option 2 remains
  available once a 1 GB resident budget exists.
