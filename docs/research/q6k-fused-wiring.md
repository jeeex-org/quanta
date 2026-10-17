# The folded fused Q6_K dequant-dot: kernel, wiring, and the end-to-end table

Status: **kernel built and proven bit-exact; wired into the decode route, opt-in
and DEFAULT OFF; committed and pushed.** VERSION 0.0.246, `lib/std` + `tests` +
this doc only, `compiler/**` untouched.

This is the twin of `docs/research/q4k-fused-wiring.md`, which closed with
"the next lever is unambiguous ... Q6_K ... a folded Q6_K twin of the same shape
would extend this exact branch to those rows at zero risk to the Q4_K path. That
is where the next unit should start". That is this document.

Supersedes the Q6_K rows of the "Not wired" table in that doc (section 3 there).

## 0. The lever, in one line

`jit_f_build_folded_q6k()` is the Q6_K twin of the folded Q4_K kernel, and it is
routed into the same `pl_run_rows_map` branch behind its own flag
`mm_set_fused_q6k(1)`. The kernel alone is a measured **9.09-9.87x**
`mm_deq_row_raw + mm_dot4_s` on real Q6_K rows. End to end, on top of the
already-landed Q4_K fusion (fused_q4k=1 in BOTH arms), it is a measured
**1.183x / 1.166x / 1.125x** on decode at 128 / 512 / 1024 tokens
(0.737 / 0.618 / 0.519 -> 0.872 / 0.720 / 0.584 tok/s) and **1.36x / 1.34x /
1.31x** on prefill, with **identical logits**, identical generated ids, and
**byte-identical VmPeak deltas**.

## 1. What Q6_K is, and why it was the next lever

From the model's own GGUF header (266 tensors, parsed directly), per-token matvec
elements:

| dtype | elements | share | tensors |
|---|---:|---:|---:|
| Q4_K | 2,122,317,824 | 78.69% | 148 |
| Q6_K | 574,619,648 | 21.30% | 19 |
| F32 tails | 261,120 | 0.01% | 99 |

The 19 Q6_K tensors are NOT one kind of thing, and that decides the wiring:

| tensor | shape [cols=k, rows] | elements | route |
|---|---|---:|---|
| `token_embd.weight` | [2048, 128000] | 262,144,000 | pool kind 5 (`pl_run_embed_map`) |
| 14 x `blk.N.ffn_down.weight` | [10752, 2048] | 22,020,096 each | pool kind 4 (`pl_run_rows_map`) |
| 4 x `blk.N.attn_v.weight` | [2048, 512] | 1,048,576 each | pool kind 4 (`pl_run_rows_map`) |

The eighteen matvec tensors go through the SAME worker the Q4_K fusion already
hooks, so ONE branch fuses all of them. `token_embd` does not -- see section 3.

## 2. The block format, and the three properties that make it bit-exact

Q6_K super-block: 210 bytes -> 256 weights.

```
+0    u8  ql[128]   low 4 bits of every quant
+128  u8  qh[64]    high 2 bits of every quant
+192  i8  sc[16]    one signed scale per 16 weights
+208  f16 d         super-block scale
```

For a 128-element half (`n` = 0,1; ql at `+n*64`, qh at `+128+n*32`, sc at
`+192+n*8`) and a section `s` = 0..3:

```
s=0  y[ 0.. 31]  ql[ 0..31] &15, qh>>0, sc[0] sc[1]
s=1  y[32.. 63]  ql[32..63] &15, qh>>2, sc[2] sc[3]
s=2  y[64.. 95]  ql[ 0..31] >>4, qh>>4, sc[4] sc[5]
s=3  y[96..127]  ql[32..63] >>4, qh>>6, sc[6] sc[7]
```

each section = two 16-element halves (ONE scale each) = four 4-element groups.
Per element: `q = (ql & 15 | ((qh >> 2s & 3) << 4)) - 32` in [-32,31], and
`value = d * (sc * q)` with `sc*q` EXACT.

The reference the route must match (the un-fused branch of `pl_run_rows_map`) is
`mm_deq_row_raw(14) + mm_dot4_s`. Identity rests on three properties, all argued
in the kernel header in `lib/std/jit_x86_fused.quanta`:

1. **Per-element rounding.** `sc` (i8) times `q` (int in [-32,31]) is an integer
   in [-4064,4064], exactly representable in binary64. The vector form
   `q -> vcvtdq2pd -> *sc -> *d` therefore rounds EXACTLY where the scalar
   `fmul(d, fmul(sc, q))` rounds -- once, at `*d` -- and then `*x` rounds once,
   the same as `mm_dot4_s`'s element product. `d` is decoded f16->f32->f64 (both
   exact, since f16's 11-bit significand fits f32's 24), matching `f16_to_f64`.
   Pre-folding `d*sc` would round twice; it is deliberately not done.
2. **Lane assignment.** Groups are 4 CONSECUTIVE elements and element `k` of a
   group lands in ymm0 lane `k`, so lane `k` accumulates elements `k, k+4, k+8,
   ...` -- exactly `mm_dot4_s`'s lane `k`.
3. **Accumulation order.** `mm_dot4_s` walks `c = 0,4,8,...` in increasing
   element index. This kernel walks `n(0,1) -> s(0,1,2,3) -> h(0,1) -> g(0,1,2,3)`,
   whose destination index `32s+16h+4g+k` is itself increasing with the loop
   nesting, so every lane sees its elements in the same order on both sides. The
   final reduce `((l0+l1)+(l2+l3))` is byte-for-byte `mm_dot4_s`'s `s0+s1`.

Float addition is not associative, so all three must hold -- (2) and (3) are the
easy ones to get subtly wrong. (This is the same class of trap that cost the Q4_K
kernel a day: `vpermilpd`'s lane-relative selectors, and the group-cadence vs
allocated-stride mismatch.)

### Emitting it

Same discipline as every other JIT kernel here: **every byte was produced by GNU
`as` and read back out of `objdump -d`**; none was derived by hand. The kernel
is one leaf function using no callee-saved register (no prologue/epilogue), with
a register map of `r9`=W block cursor (advance 210/block), `r10`=X cursor
(advance 32/group), `rcx`=nsuper, ymm0=accumulator, ymm1=d broadcast, ymm2=sc
broadcast (reloaded per 16-half), xmm3/4/5 = -32/15/3 built from `vpcmpeqd`, and
ymm6/ymm7 = q/qh scratch. The `-32`, `15`, `3` masks come from `vpcmpeqd` plus one
shift, so no GPR and no constant pool is touched.

Two encoding details worth keeping:

- **The `d` load is `movzx eax, word ptr [r9+208]`, not `vmovd xmm1,[r9+208]`.**
  The format promises 2 bytes at +208; a 4-byte load would read 2 bytes past the
  end of the last block of the tensor. The 2-byte form removes that class
  entirely (and costs one instruction per super-block, amortised over 64 groups).
- **qh displacements are disp32.** The qh plane starts at +128, past the disp8
  window, so `vpmovzxbd xmm7,[r9+disp32]` (modrm `0xB9`) is used while the ql
  plane stays disp8 (`modrm 0x71`, max offset 124).

## 3. Wiring: what is fused, what is not, and why

| site | dtype | wired? |
|---|---|---|
| Q4_K rows, `pl_run_rows_map` (kind 4) | 12 | yes (`mm_fused_q4k`, previous unit) |
| **Q6_K rows, `pl_run_rows_map` (kind 4)** | 14 | **yes (`mm_fused_q6k`, this unit)** |
| tied output projection, `mm_embed_logits` -> `pl_run_embed_map` (kind 5) | Q6_K | **NO -- see below** |
| embedding lookup (`mm_lookup_row`) | Q6_K | NO (a gather, not a matvec) |
| serial fallback (`mm_workers <= 1`), pread block path (kind 0) | any | NO (not the decode route) |

**Yes, it is a separate flag.** `mm_fused_q6k` (`mm_set_fused_q6k`, witness
`mm_get_fused_q6k_used`), default 0, rather than extended into `mm_fused_q4k`,
for three reasons: (a) the measurement that matters is *Q4_K-only* vs
*Q4_K+Q6_K* and one flag cannot express it (the bench grows conf field 9 for the
same reason); (b) fail-closed is per kernel -- each flag is cleared only if ITS
own RWX region is refused, so a box that can run one is never recorded as
running the other; (c) a dtype-confined defect can be disabled without losing
the other.

`mm_matvec_par` emits the Q6_K kernel once, before any worker runs, and clears
the flag if the RWX mapping is refused. The branch sits AFTER the Q4_K branch and
reuses the same per-worker argument area (`cell + 24`, allocated once at pool
spawn by `mm_scratch_new`); `[AS+16]` is written 0 and unread, because the folded
kernel derives its factors in-kernel. The Q4_K branch is untouched byte-for-byte.

### Why the tied output projection is NOT fused

`token_embd.weight` [2048, 128000] is the single largest matvec in the model
(262,144,000 elements, 45.6% of all Q6_K) and it does NOT go through kind 4. It
is `mm_embed_logits` -> `pl_run_embed_map` (kind 5), whose dot is a **strict
left-to-right scalar chain**:

```
acc = 0;  for c in 0..ncols: acc = acc + row[c] * x[c]
```

That is a DIFFERENT summation order from `mm_dot4_s`'s four lanes and a single
`((l0+l1)+(l2+l3))` reduce. Fusing it bit-exactly therefore cannot reuse the
four-lane kernel: it would have to reproduce the chain. Two honest options, both
deferred rather than smuggled in:

- a **chain-order kernel**: keep the SIMD dequant (the expensive part) and
  accumulate with four serial `vaddsd` per 4-element group (3 `vpsrldq` + 4
  `vaddsd`), which reproduces `acc = ((acc+p0)+p1)+p2)+p3` exactly. It gives up
  the 4-lane ILP on the ADD (~4 cycles/element) but not on the dequant, so it
  should still be several times the scalar Quanta loop -- but it is unmeasured
  and unbuilt here, so it is a proposal, not a result;
- **changing the embed reference** to `mm_dot4_s` so the four-lane kernel can be
  reused. Rejected for this unit: it changes the model's logits in the low bits
  and would silently invalidate every recorded logits/text expectation, which is
  a much bigger blast radius than the win.

**Coverage of per-token matvec elements:** with both flags on the pair covers
2,122,317,824 + 312,475,648 = **2,434,793,472 of 2,696,937,472 (90.28%)**. The
un-fused remainder is `token_embd` (9.72%) plus the embedding lookup.

## 4. Correctness

Two independent gates, both asserting 0 mismatches BEFORE any timing.

**(a) Element-level, per tensor.** `tests/jit_q6k_fold_test.quanta` walks EVERY
Q6_K tensor in the model (all 19), takes real rows straight from the mmap, and
diffs `jit_f_apply_folded_q6k` against `mm_deq_row_raw(14) + mm_dot4_s` BIT FOR
BIT. Two x vectors per row so a bug that cancels on one input cannot pass: the
model's REAL activation `fc_fw_f` after one forward, and a mixed-magnitude,
both-signs synthetic.

```
q6k_tensors=19
REAL-X  total mismatches over 152 rows: 0
SYNTH-X total mismatches over 152 rows: 0
nonzero_results=304 of 304
PASS: folded Q6_K kernel bit-identical on every Q6_K tensor (both x vectors)
```

`nonzero_results=304 of 304` is the anti-vacuity guard: a kernel that returned
0.0 for everything would otherwise "match" only if `mm_dot4_s` also returned 0.0,
so the row requires every result to be non-zero.

**(b) At the logits level, all 128,000 values.**
`tests/lfm2_fused_logits_test.quanta` was extended from three passes to five and
runs one process:

```
pass0 fused_q4k=0 fused_q6k=0   (REFERENCE)
pass1 fused_q4k=0 fused_q6k=0   (CONTROL: is fc_fw_reset() clean?)
pass2 fused_q4k=1 fused_q6k=0   (Q4_K only -- the previous stage)
pass3 fused_q4k=0 fused_q6k=1   (Q6_K only -- the new twin)
pass4 fused_q4k=1 fused_q6k=1   (BOTH -- the shipped configuration)
```

```
logits_n=128000
CONTROL pass1-vs-pass0 : logit_mism=0 argmax_mism=0
Q4K     pass2-vs-pass0 : logit_mism=0 argmax_mism=0 max_abs_diff_bits=0
Q6K     pass3-vs-pass0 : logit_mism=0 argmax_mism=0 max_abs_diff_bits=0
BOTH    pass4-vs-pass0 : logit_mism=0 argmax_mism=0 max_abs_diff_bits=0
pass0_argmax0=597
pass4 first 24 ids: 597 4695 20589 34 496 2992 355 229 26 19 26 39 41774 415 278 1579 1049 2426 440 4695 10966 267 2936 1579
PASS: fused Q4_K, fused Q6_K and both are IDENTICAL to the existing path (all 128000 logits)
```

`max_abs_diff_bits = 0` is exactly +0.0 -- not "close", identical. The CONTROL
comes first so the reset is proven clean before any other comparison means
anything.

**Witnesses, asserted.** Each pass records `mm_get_fused_used()` and
`mm_get_fused_q6k_used()`, and the test FAILS if they are not what that pass
asked for (pass2 q4k=1/q6k=0, pass3 q4k=0/q6k=1, pass4 both=1). A pass that
"matched" without ever dispatching its kernel is not evidence.

## 5. End-to-end measurement

`tests/lfm2_decode_bench.quanta` (new conf field 9 = `fused_q6k`), one binary,
two sequential sessions on the same box, worker count 20 uncapped, mmap on,
`cache_norms` on, `ignore_eos` on, temp 0.

Both arms have `fused_q4k=1`:
- **A** = Q4_K fused only (`20 128 512 1024 1 1 1 1 0`)
- **B** = Q4_K + Q6_K fused (`20 128 512 1024 1 1 1 1 1`)

Environment, stated with every number, both sessions back to back on the same
box: governor **powersave**; load average **11.3-25.4** (the bench is itself a
20-thread run on a 20-core box shared with other work, so it raises the load);
**no peer model process** (the driver refuses to start if one is alive).
`clock()`'s absolute unit is UNVERIFIED repo-wide -- read the within-session
A-vs-B ratio, not the absolute clock.

### Decode

| tokens | arm | ms/token | min/med/max ms | tok/s | **B/A** |
|---:|---|---:|---|---:|---:|
| 128 | A Q4_K only | 1355.38 | 2 / 1357 / 1575 | 0.737 | |
| 128 | **B both** | **1145.70** | 2 / 1159 / 1339 | **0.872** | **1.183x** |
| 512 | A Q4_K only | 1617.55 | 1 / 1630 / 2084 | 0.618 | |
| 512 | **B both** | **1387.63** | 1 / 1394 / 1859 | **0.720** | **1.166x** |
| 1024 | A Q4_K only | 1923.11 | 2 / 1920 / 2757 | 0.519 | |
| 1024 | **B both** | **1709.73** | 2 / 1705 / 2501 | **0.584** | **1.125x** |

Prefill (same branch, unbatched), ms per prompt token: A 801 / 802 / 813 vs
B **591 / 600 / 619** -- **1.36x / 1.34x / 1.31x**. (`min` is 1-2 ms in every run
because the bench's final iteration has no forward, by its own convention; the
median is the representative figure and both arms share the convention.)

**Composed against the fully-unfused baseline**, this is where the stack stands
(the OFF column is the previous unit's measurement, same binary less the flags):
0.273 -> 0.872 = **3.19x** at 128; 0.257 -> 0.720 = **2.80x** at 512;
0.237 -> 0.584 = **2.46x** at 1024.

**Token-id identity, end to end.** The first 24 generated ids are byte-identical
in A and B (and identical to the logits test's `pass4`):

```
597 4695 20589 34 496 2992 355 229 26 19 26 39 41774 415 278 1579 1049 2426 440 4695 10966 267 2936 1579
```

Both begin `The user asks: "What is 2+2? ... The answer is 4.` and first-step
argmax is **597** in every run. `tok/s` is the bench's `k*1e12/(g1-g0)`,
`ms/token` is `(g1-g0)/(k*1e4)`.

### Memory: neutral, and byte-identical where it counts

Per-run `smaps_rollup` / `/proc/self/status` deltas:

| tokens | arm | RSS delta kB | anon delta kB | **VmPeak delta kB** |
|---:|---|---:|---:|---:|
| 128 | A | 75,200 | 75,200 | **555,864** |
| 128 | B | 75,200 | 75,200 | **555,864** |
| 512 | A | 309,728 | 309,728 | **2,236,464** |
| 512 | B | 335,328 | 335,328 | **2,236,464** |
| 1024 | A | 641,676 | 641,676 | **4,477,264** |
| 1024 | B | 638,476 | 638,476 | **4,477,264** |

At 128 tokens the three deltas are byte-identical. At 512 and 1024 the **VmPeak
delta -- the sizing instrument, the one that actually kills a capped run -- is
byte-identical** (2,236,464 and 4,477,264 kB on both arms); RSS/anon differ by
0.5-3%, which is the pre-existing A9-class per-token leak's own run-to-run
variation, not the flag (it is per forward, not per row, and both arms allocate
nothing per row: the args area is per worker, once). Conclusion: the Q6_K route
is **memory-neutral**.

### Kernel-level attribution

`tests/jit_q6k_perf_test.quanta`, interleaved A/B in ONE process, best of 5
cycles, 256 real rows per sweep, single-threaded:

| tensor | cols | fused best | pair best | **ratio** | fused ns/elem | pair ns/elem |
|---|---:|---:|---:|---:|---:|---:|
| `ffn_down.3` | 10752 | 1,325,833 | 13,094,494 | **9.87x** | 0.48 | 4.76 |
| `attn_v.2` | 2048 | 238,178 | 2,179,641 | **9.15x** | 0.45 | 4.16 |
| `token_embd` | 2048 | 231,395 | 2,105,584 | **9.09x** | 0.44 | 4.02 |

The pair's per-element cost (4.0-4.8 ns) independently reproduces the recorded
figures for `dq6` (~2.0 ns/elem) + `mm_dot4_s` (~2.7 ns/elem), which is the
sanity check that this row measures the right pair.

**Attribution arithmetic (inferred, not measured).** For an end-to-end ratio `R`
and a kernel ratio `K`, the Q6_K covered rows were `F = (1 - 1/R)/(1 - 1/K)` of
a decode token's wall time: with R = 1.183/1.166/1.125 and K ~ 9.5-9.9, **F ~
17% / 16% / 12%** at 128 / 512 / 1024 tokens. F falls with context because the
untouched O(pos) attention work grows while this work does not.

Measured B (both fused) decode rates: **0.872 / 0.720 / 0.584 tok/s** at
128 / 512 / 1024. The reference is **llama.cpp, this exact model, this box, CPU,
20 threads: 17.32 tok/s**. The honest gap is therefore **19.9x / 24.1x / 29.7x**,
and it still WIDENS with context.

What this unit bought is real and bounded: the Q6_K kernel is 9.1-9.9x the pair
it replaces, but that pair is only ~12-17% of a decode token's time (inferred,
section 5), so the end-to-end gain is 1.125-1.183x. At 128 tokens the composed
stack (both fused, vs fully unfused) is 3.19x.

**The next lever is the tied output projection** (`token_embd.weight` -> pool
kind 5, `pl_run_embed_map`). It is the single largest matvec in the model
(262,144,000 elements, 45.6% of all Q6_K, 9.72% of per-token matvec elements),
and it is on a **scalar** dot, so its per-element cost is far above the
4.0-4.8 ns the kind-4 pair already achieves. Its fix is not a flag flip: see
section 3 -- it needs a chain-order kernel (SIMD dequant, four serial `vaddsd`
per group) to stay bit-exact against the scalar reference, or a deliberate
change of that reference. That is the shape, unmeasured, and it is where the
next unit should start.

**After that, the wall is not more matvec.** Even fusing the entire output
projection cannot close a 20-30x gap, because at 1024 tokens the untouched O(pos)
attention work alone accounts for most of the token (the ratio falling
1.183 -> 1.125 as context doubles is this term growing). The two named levers
past the output projection remain: the attention score loop (O(pos), no fused
path), and pool scaling (~800% CPU ceiling on a 20-core box, saturating well
below linear).

**Gap to the author's 15 tok/s target:** 15 / 0.872 = **17.2x at 128 tokens**,
15 / 0.584 = **25.7x at 1024**. Two dtypes of fused kernel have now taken the
route from 0.273 to 0.872 tok/s (3.19x); the remaining distance is dominated by
work these two levers do not touch.

## 7. What could not be measured cleanly

- **The A/B ratio is the number to trust, not the absolute ms/token.** Both
  sessions ran at high and rising load (the bench is a 20-thread run on a 20-core
  box shared with other work; load 11.3 -> 25.4 over session A, 18-23 over B).
  The two arms ran back to back on the same box with the same binary, so the
  ratio is within-session; the absolute rates would move under a quiet box.
- **A's reproduction of the previous Q4_K-only baseline is the cross-check that
  the A arm is right**: this session 0.737 / 0.618 / 0.519 tok/s at 128/512/1024
  against the committed Q4_K-wiring doc's 0.742 / 0.622 / 0.516 -- a ~1% spread,
  which is this box's run-to-run noise and confirms the new conf field 9 defaults
  to "off" without disturbing field 8.
- **`F` (the Q6_K share of a decode token) is INFERRED**, from the measured
  end-to-end ratio and the measured kernel ratio, not timed directly. The
  INFERENCE is what the section-5 arithmetic says; the kernel ratio and the
  end-to-end ratio are measured.
- **CPU%** was not re-measured here (the previous unit's method used a separate
  `/usr/bin/time -v` short run); the fused route is expected to use strictly less
  CPU per token -- as it does for Q4_K -- but that is not a number this unit
  produced. Treat it as unmeasured.
- **`clock()`'s absolute unit remains UNVERIFIED** repo-wide, as in every other
  perf doc here; the ~0.44-0.48 ns/elem "fused" column in section 5 is a
  within-process comparison and is labelled as such in the test's own output.
- The **tied output projection is NOT fused** (section 3), so its measured cost
  inside these runs is the un-fused scalar-dot path; no number here describes a
  fused version of it.
- The Q6_K **kernel was not put through `perf`/callgrind** (the compiler cannot
  be profiled -- symbol-less flat blob), so the 9.1-9.9x is a wall-clock ratio
  and instruction counts were not taken.

## 8. Files

- `lib/std/jit_x86_fused.quanta` -- `jit_f_build_folded_q6k()` + its emit helper
  set + `jit_f_setup_folded_q6k()` / `jit_f_ready_folded_q6k()` /
  `jit_f_apply_folded_q6k()`.
- `lib/std/gguf_mm.quanta` -- `mm_fused_q6k` flag + witness + setters, the
  fail-closed setup in `mm_matvec_par`, and the dtype-14 branch in
  `pl_run_rows_map`.
- `tests/jit_q6k_fold_test.quanta` (new) -- element-level identity, all 19 Q6_K
  tensors.
- `tests/jit_q6k_perf_test.quanta` (new) -- interleaved kernel-vs-pair ratio.
- `tests/lfm2_fused_logits_test.quanta` (extended) -- five-pass 128,000-logit
  identity with witnesses.
- `tests/lfm2_decode_bench.quanta` (extended) -- conf field 9.
- `tests/run_q6k_fused_ab.sh` (new) -- the sequential A/B measurement driver.

Neither new test is a manifest row, consistent with every other `tests/jit_*` and
`tests/lfm2_*` file: they need the 1.67 GB model and a VA cap above it, and
`test_suites/**` is outside this unit's ownership. The gate is run separately;
its result is recorded here.

## 9. Gate

`bash test_suites/scripts/run_tests.sh` on the final tree (VERSION 0.0.246, no
bump):

- **GATE_RC=0**: no section RED, all **29** summary sections GREEN.
- native: **231/231 pass, 0 fail** (0 compile-fail) [rows: EXPECTED.tsv].
- stdlib: **113/113 GREEN** (`STDLIB: 113/113 GREEN`).

Every row that exercises the touched libraries passes, including
`gguf_forward_pass_test`, `gguf_fp_inference_test`, `stdlib_gguf_mm_test`,
`stdlib_jit_dispatch_test`, `q4k_matvec_test`, `q6k_dequant_ref_test`,
`embedding_test` and `std_gguf_mmap_test`. The changes are additive -- a new flag
defaulting OFF and a branch reachable only when it is set -- so those untouched
rows assert that the DEFAULT path is unchanged.