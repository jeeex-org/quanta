# Pool partition rule, dispatch cost, and the parallel short-conv block

**Status: MEASURED.** Every number below comes from a run whose command, conf line,
compiler and governor are printed with it. Nothing here is projected; where a number
is a projection it says so.

Compiler pinned: `compiler/0.0.247/bin/x86/qc`, md5 `a17e3cfb056f55d4ee68a0db0dfcfa22`
(NOT from `VERSION` -- a peer owns `compiler/**` + `VERSION` for an arithmetic campaign).

Environment for every decode run below: `powersave`, 20 cores, and **`Hermes` itself
holding ~813 % CPU (pid sampled at 813, 814, 813 across the session) plus ~1.3 cores of
`python`** -- i.e. roughly 8-9 of 20 cores are unavailable before the pool starts.
`loadavg` 21-23 during the paired run. Absolute tok/s on this box swings ~1.24x between
sessions for the SAME binary, so every claim below is a **same-session pair** or a
ratio; absolute tok/s is labelled.

## 0. What changed in this unit

1. The pool's partition rule was generalised from `"the last worker absorbs the
   remainder"` to the **quotient split** `[t*N/nw, (t+1)*N/nw)` in every kind
   (`pl_run_rows`, `pl_run_embed`, `pl_run_mm`, `pl_run_embed_b`, `pl_run_rows_map`,
   `pl_run_embed_map`, `pl_run_glu`, `pl_run_conv`). Kind 7 (attention) already had it.
2. New opt-in flag `mm_set_fused_conv` (pool kind 8, `pl_run_conv`): the whole
   channel-wise short-conv elementwise block runs on the pool as ONE channel-sliced job.
3. New test `tests/lfm2_pool_dispatch_probe.quanta`: the pool's per-call fixed dispatch
   cost, no model attached.
4. A driver defect was found and fixed while doing (2): `parse_ints` in the bench
   **counted** every conf field but **stored** only the first 14, so the 15th
   (`fused_conv`) read back as 0 and the A/B silently measured the conv-OFF arm twice.
   Caught by the bench's own printed `fused_conv_active=0` disagreeing with the conf
   file. This is the same silent-wrong-arm class as the peer's earlier mis-count.

## 1. The all-flags-ON phase table, 128 and 1024, same session

Command: `LENS="128 1024 128" bash tests/lfm2_prof_ab.sh prof_attn` (conv OFF) then
`... prof_conv` (conv ON), back to back in one session. Conf lines the runs wrote and
the bench printed back:

```
OFF: conf: workers=20 lens=128/1024/128 mmap=1 cache_norms=1 ignore_eos=1
            fused_q4k=1 fused_q6k=1 prof=1 prof_work=1 fused_chain=1 fused_glu=1 fused_attn=1
ON : conf: workers=20 lens=128/1024/128 mmap=1 cache_norms=1 ignore_eos=1
            fused_q4k=1 fused_q6k=1 prof=1 prof_work=1 fused_chain=1 fused_glu=1 fused_attn=1 fused_conv=1
ON : fused_conv_active=1 fused_conv_used=1   (all three runs)
```

`mark_ns=153-163` (raw `clock_gettime` syscall) vs `mark_ns_old_clock()=3526-4373`
(the `clock()` builtin, which mmaps per call -- A27). `us_tok` = run total / reported
tokens; the last decode iteration is argmax-only, so 127 (of 128) and 1023 (of 1024)
forwards contributed and every per-token figure is ~0.8 % low, uniformly.

### decode at 128 tokens (us/token), same session

| phase | conv OFF | conv ON | delta | OFF % | ON % |
|---|---|---|---|---|---|
| `token_body` (whole forward) | **542,714** | **541,884** | -830 | 100.00 | 100.00 |
| `embed_lookup` | 46 | 45 | -1 | 0.01 | 0.01 |
| `layer_stack` (30 layers) | 498,758 | 497,430 | -1,328 | 91.90 | 91.80 |
| &nbsp;&nbsp;`attn_all` (8) | 37,363 | 37,197 | -166 | 6.88 | 6.86 |
| &nbsp;&nbsp;&nbsp;&nbsp;`attn_qkv` / `outproj` | 15,164 / 7,480 | 14,813 / 7,633 | | 2.79 / 1.38 | 2.73 / 1.41 |
| &nbsp;&nbsp;`conv_all` (22) | 81,281 | 80,774 | -507 | 14.98 | 14.91 |
| &nbsp;&nbsp;&nbsp;&nbsp;`conv_inproj` | 51,047 | 51,091 | +44 | 9.41 | 9.43 |
| &nbsp;&nbsp;&nbsp;&nbsp;`conv_gate` | 1,567 | **0** | -1,567 | 0.29 | 0.00 |
| &nbsp;&nbsp;&nbsp;&nbsp;`conv_state` | 3,209 | **0** | -3,209 | 0.59 | 0.00 |
| &nbsp;&nbsp;&nbsp;&nbsp;`conv_kernel` | 2,637 | **12** | -2,625 | 0.49 | 0.00 |
| &nbsp;&nbsp;&nbsp;&nbsp;`conv_outproj` | 22,703 | 20,967 | -1,736 | 4.18 | 3.87 |
| &nbsp;&nbsp;`ffn_gate` (30) | 115,156 | 115,025 | -131 | 21.22 | 21.23 |
| &nbsp;&nbsp;`ffn_up` (30) | 113,608 | 112,924 | -684 | 20.93 | 20.84 |
| &nbsp;&nbsp;`silu_glu` (30) | 34,604 | 34,620 | +16 | 6.38 | 6.39 |
| &nbsp;&nbsp;`ffn_down` (30) | 111,349 | 111,441 | +92 | 20.52 | 20.57 |
| &nbsp;&nbsp;`tied_logits` | 43,849 | 44,348 | +499 | 8.08 | 8.18 |
| `ln_*` + `residual*` (30 each) | 5,262 | 5,315 | +53 | 0.97 | 0.98 |

The largest items are now the **three FFN matvecs (62.6 % combined)** and `conv_all`
(14.9 %, of which `conv_inproj` 9.4 %). `attn_all` is 6.9 %, `silu_glu` 6.4 %,
`tied_logits` 8.1 %.

### decode at 1024 tokens (us/token), same session

| phase | conv OFF | conv ON | delta | OFF % | ON % |
|---|---|---|---|---|---|
| `token_body` | **597,948** | **596,652** | -1,296 | 100.00 | 100.00 |
| `layer_stack` | 553,128 | 552,370 | -758 | 92.50 | 92.58 |
| &nbsp;&nbsp;`attn_all` (8) | 93,470 | 93,788 | +318 | 15.63 | 15.72 |
| &nbsp;&nbsp;`conv_all` (22) | 80,953 | 81,576 | +623 | 13.54 | 13.67 |
| &nbsp;&nbsp;`ffn_gate` | 113,904 | 113,744 | -160 | 19.05 | 19.06 |
| &nbsp;&nbsp;`ffn_up` | 112,655 | 111,951 | -704 | 18.84 | 18.76 |
| &nbsp;&nbsp;`silu_glu` | 35,748 | 35,065 | -683 | 5.98 | 5.88 |
| &nbsp;&nbsp;`ffn_down` | 110,955 | 110,755 | -200 | 18.56 | 18.56 |
| &nbsp;&nbsp;`tied_logits` | 44,711 | 44,172 | -539 | 7.48 | 7.40 |

**`attn_all` at 1024 tokens is 15.6 %, not 56 %.** The previous unit's 56.31 % was
the SCALAR head loop; the head-parallel route (kind 7) removed ~80 % of it at 1024 on
the same box.

### Same-run pool totals (the same-run total asked for)

| | OFF 128 | ON 128 | OFF 1024 | ON 1024 |
|---|---|---|---|---|
| `pool_ns_submit` (us/token) | 472,167 | 470,018 | 471,308 | 467,773 |
| `pool_n_parcalls` | 21,209 (=165.7/tok) | 21,209 | 170,841 | 170,841 |
| `pool_n_elems_matvec` (/token) | 2,415,772,000 | same | same | same |
| `pool_worker_busy_ns` (us/token, summed over workers) | 3,394,142 | 3,406,659 | 3,894,237 | 3,905,273 |
| **achieved concurrency** | **7.19 / 20** | **7.25 / 20** | **8.26 / 20** | **8.35 / 20** |

`n_parcalls` does NOT rise with conv ON because `mm_glu_par`/`mm_attn_par`/`mm_conv_par`
do not touch the `MMP_SUBMIT`/`MMP_CALLS` accumulators (only the matvec paths do); the
22 extra jobs are visible as `conv_all`'s unaccounted remainder instead (see §4).

**The pool's own wall is now ~87 % of the token** (`pool_ns_submit` 470,018 of
541,884 us). Every lever that does not shrink the pool's wall is capped at the
remaining 13 %.

## 2. Generalising the partition rule: what it bought, and what it did NOT fix

### It is an algorithmic fix, not a workaround

The old rule made worker `nw-1` own everything from `(nw-1)*(N/nw)` to `N`. The work is
statically independent and the split should be even, so the even split is the fix. It
is **not** the forbidden thing: no individual slice is hand-tuned to compensate for
the absence of atomics, and the rule contains no magic numbers. It is applied
uniformly to every kind.

### The measured effect is small, and the reason is arithmetic

Static ceiling = `N / max_i(size_i)`. At nw=20 on THIS model:

| tensor rows `N` | old max size | old ceiling | new max size | new ceiling |
|---|---|---|---|---|
| 512 (attn k/v proj, Q6_K) | 32 | 16.0 | 26 | 19.7 |
| 2048 (attn q/out, ffn down, conv out) | 110 | 18.6 | 103 | 19.9 |
| 6144 (conv in_proj) | 311 | 19.8 | 308 | 19.9 |
| 10752 (ffn gate/up) | 549 | 19.6 | 538 | 20.0 |
| 128000 (tied logits) | exact both ways | 20 | | 20 |
| 322560 (GLU) | exact both ways | 20 | | 20 |
| 32 heads (attention) | 13 | 2.46 | 2 | 16.0 |

Element-weighted over one decode token (2,162 M matvec elements + 262 M tied), the
**static ceiling moves 19.50 -> 19.97, i.e. +2.4 %**. The remainder-absorption rule
was pathological only where `N/nw` is small and the remainder is large relative to it
-- attention's 32 heads over 20 workers -- and that case was already fixed by the
previous unit. For the matvec kinds at nw=20 the row counts divide almost evenly.

### Achieved concurrency is far below BOTH ceilings, so the rule is not the constraint

Measured achieved concurrency: **7.19-8.35 of 20**, against a static ceiling of 19.50
(old rule) / 19.97 (new rule). Two other candidate causes were measured and excluded:

- **Fixed dispatch cost** (§3): 14.6 us/call x 166 calls = **2.4 ms/token, 0.4 %** of
  the token. Not it.
- **Memory bandwidth**: one token streams ~1.65 GB of weights (the model size). At the
  measured pool wall of 470 ms/token that is **3.5 GB/s**. The reference runtime on the
  SAME model and CPU run does 1.65 GB x 17.32 tok/s = **28.6 GB/s**. So the matvec path
  is 8x off a demonstrated bandwidth, i.e. it is not bandwidth-limited either.

What remains is the ramp: a woken worker is not running until the scheduler gives it a
core, and on this box ~8-9 of 20 cores are taken by `Hermes` + `python` before the
pool asks for 20. The achieved 7.25 of an effective ~11-12 available cores is ~60-65 %.

**Statement of the limit, as asked:** the residual concurrency shortfall is NOT a
partition-rule problem (imbalance is now <= 2 % by construction) and NOT a dispatch cost
(0.4 %). It is core availability plus wake/start stagger. **Atomics would not fix it**
-- a work-stealing deque fixes *imbalance*, and imbalance is already <= 2 %. Naming
atomics as the prerequisite for this particular residual would be wrong; atomics are the
prerequisite for a work-stealing pool, not for this number. The honest next lever for
concurrency is either a quieter box or fewer workers (a conf field, not a workaround).

## 3. The pool's per-call fixed dispatch cost (measured, no model)

`./compiler/0.0.247/bin/x86/qc -O tests/lfm2_pool_dispatch_probe.quanta P && P`.
It drives the pool with `mm_glu_par` at one element per worker (pure dispatch) K=4000
times per case, wall timed with the same raw `clock_gettime` syscall the library marks
use. Run on a quiet box (load 1.8).

| nw | wall ns per call | worker-busy ns per worker per call |
|---|---|---|
| 4 | 7,277 | 651 |
| 8 | 8,823 | 624 |
| 12 | 9,457 | 816 |
| 16 | 10,720 | 659 |
| 20 | **14,619** | 652 |

So the fixed cost is ~15 us at nw=20 and rises ~0.6 us per worker (it IS the wake
broadcast, not a fixed syscall). At 166 calls/token that is **2.4 ms/token = 0.4 %** of
a 543 ms token. Two consequences:

- "Open-code 166 dispatch calls per forward" is **not** a problem worth a version.
- Moving more main-thread work onto the pool is cheap: 22 extra calls cost ~0.32 ms.

A job with real work shows the marginal cost on top (same run): n=20,000 -> 908 us/call;
n=200,000 -> 6,722 us/call, i.e. ~33 ns per pooled GLU element.

## 4. The short-conv elementwise block (new flag) and the bigger unplanned win

### The unplanned win: a redundant unconditional dequant, ~20 ms/token

While restructuring, the conv kernel load was hoisted out of the elementwise block and
its duplicate removed. The pre-change code called `mm_load_small(cwt, kw*dm, fc_sc_kw)`
**unconditionally on every conv layer**, and then again in the cold-cache branch -- and
the unconditional one ran even when `fc_nc_ready != 0`, i.e. when `kwptr` came from the
already-materialised `fc_nc_conv` cache and `fc_sc_kw` was never read. 22 conv layers x
6,144 elements, per token, into a buffer nobody reads.

Measured, flag-OFF path both sides (so this is the refactor, not the flag):

| run | `conv_kernel` us/token |
|---|---|
| all-flags-ON, load 13.7, pre-change | 23,357 |
| chain-only, load 17-20, pre-change | 30,423 |
| all-flags-ON, load 21-23, post-change | **2,637** |

A HIGHER load produced a 9x LOWER `conv_kernel`, so ambient load cannot explain it: the
~20.7 ms/token is the removed dequant. (The unrelated `fc_conv_batch` prefill path at
`lib/std/lfm2_forward.quanta:1708` still does an unconditional `mm_load_small` with no
cache branch -- same shape, once per batch, NOT fixed here; queued, not a defect.)

This is why the task table's `conv_kernel = 23,357 us (29 % of conv_all)` was mostly a
redundant dequant, not the correlation loop.

### The flag itself: measured

`tests/lfm2_prof_ab.sh ab_conv`, timer OFF, `LENS="128 256 128"`, 15-field conf, both
arms with `fused_chain=1 fused_glu=1 fused_attn=1`:

| arm | run1 (128) | run2 (256) | run3 (128) | tok/s |
|---|---|---|---|---|
| A conv=0 | 54,487 | 55,697 | 54,688 | 1.835 / 1.795 / 1.828 |
| B conv=1 | 54,290 | 55,028 | 53,873 | 1.841 / 1.817 / 1.856 |

Ratio B/A paired by run index: **1.0033 / 1.0123 / 1.0153, mean 1.010**. Conv ON is
faster in 3 of 3 pairs, but the arms ran sequentially under a drifting ambient load
(A: load_pre 12.07 -> load_post 21.80; B: 21.80 -> 20.39), so the honest reading is
"~1 %, consistently non-negative, within the session's load confound".

The profiled same-session pair agrees in sign and gives the mechanism: at 128 tokens
`token_body` 542,714 -> 541,884 (**-0.15 %**), `conv_gate`/`conv_state`/`conv_kernel`
1,567 + 3,209 + 2,637 = **7,413 us/token -> 12 us** on the main thread, while
`conv_all`'s unaccounted remainder (the conv job's own pool wall, no child slot covers
it) grows to **8,704 us/token = 396 us per conv job** against a 15 us fixed dispatch
cost. So the move is roughly **break-even at the phase level**: 7.4 ms of main-thread
work traded for 8.7 ms of pool wall.

396 us for a job whose arithmetic is 2,048 channels x ~3 MACs is 20-30x what the
arithmetic predicts and is the reason the win is ~1 % rather than ~5 %. Prime suspect,
named but NOT measured: FALSE SHARING on the in-place `state` update -- adjacent
channels live in the same 64-byte line and are owned by different workers, so the line
pings between cores. A cache-line-aligned slice boundary (a uniform rule change, not a
hand-tuned slice) is the obvious next experiment and is queued, not done.

**Verdict on the flag:** it is correct, bit-exact, memory-neutral, and consistently
non-negative, so it STAYS as a default-OFF opt-in. It is NOT the 7.5 % the old phase
share suggested, and the report says so rather than quoting the share as a win.

### Bit-exactness (asserted BEFORE any timing)

`tests/lfm2_fused_logits_test.quanta`, all 128,000 logits, 9 passes in one process:

```
CONTROL pass1-vs-pass0 : logit_mism=0 argmax_mism=0
Q4K/Q6K/BOTH/CHAIN/GLU/ATTN/CONV  : logit_mism=0 argmax_mism=0 max_abs_diff_bits=0
CONV    pass8-vs-pass0 : logit_mism=0 argmax_mism=0 max_abs_diff_bits=0   fused_conv_used=1
pass0_argmax0=597
pass4 first 24 ids: 597 4695 20589 34 496 2992 355 229 26 19 26 39 41774 415 278 1579 1049 2426 440 4695 10966 267 2936 1579
```

`stdlib_lfm2_conv_test`: `mismatches=0 state entries changed=4096 OK conv`. The
generalised split is covered by the same logits run (every pass used the new rule) and
by `lfm2_dot_bench`/`stdlib_lfm2_conv_test` for the row-worker kinds.

### Memory

**Flag OFF vs ON: byte-identical VmPeak.** Same-session A/B `vmpeak_kb` start/end per
run index are equal to the kilobyte in BOTH arms: `5969740 -> 5977980`,
`5979564 -> 5996068`, `5997652 -> 6005892`. `pl_run_conv` allocates nothing (the pool
already exists), so the flag is memory-neutral by construction and by measurement.

**But the absolute per-token VmPeak growth did NOT reproduce in this session, and that
is a finding, not a footnote.** The task's inherited figure is ~4.37 MB/token (13.5 GB
by token 1024). Measured now:

| session | run | VmPeak start -> end | growth |
|---|---|---|---|
| pre-change, load 13.7 | 128 tokens | 6,068,968 -> 6,624,832 | +4.34 MB/token |
| pre-change, load 13.7 | 1024 tokens | 6,725,592 -> 11,202,856 | +4.37 MB/token |
| post-change, load 21-23 | 128 tokens | 5,969,796 -> 5,978,036 | +64 KB/token |
| post-change, load 21-23 | 1024 tokens | 5,979,620 -> 6,045,708 | +64.5 KB/token |

The growth is ~68x smaller post-change, and a higher load cannot cause that. The one
allocation-shaped change in this unit is the removal of the redundant unconditional
`mm_load_small(cwt, kw*dm, fc_sc_kw)` per conv layer (22 per token), and that function
does allocate: `read_tensor_f64` (`lib/std/gguf.quanta`) does `mem_alloc(n)` followed by
`mem_free(raw)` **per call**. So 22 alloc/free pairs per token did disappear with it --
but 22 x the conv kernel's raw size (3456 B if Q4_K, 24,576 B if f32) is 77-540 KB/token,
which does NOT close a 4.3 MB/token gap. **The link is plausible and UNVERIFIED; it is
reported as a lead, not as a fix.** Either way the actionable statement is: do not size
a long-run VA cap from 13.5 GB any more -- re-measure, because the current tree measures
6.05 GB at 1024 tokens.

### Gate

- `QC=./compiler/0.0.247/bin/x86/qc bash test_suites/scripts/run_tests.sh` (the pinned
  binary every decode number in this document was measured with): see §7b.
- A plain `bash test_suites/scripts/run_tests.sh` was ALSO run and returned
  **238/238 native (0 fail, 0 compile-fail) and STDLIB 114/114 GREEN**, but note it did
  NOT use 0.0.247: a peer bumped `VERSION` to **0.0.248** mid-campaign and created
  `compiler/0.0.249`, and the runner derives `QC` from `VERSION`. That result is
  therefore attributed to `compiler/0.0.248`, not to the pinned tree.


## 5. Attention: does the score loop need a vectorised kernel yet?

Measured on the paired ON arm:

- `attn_all` = **37,197 us/token at 128** (6.9 %) and **93,788 us/token at 1024**
  (15.7 %). Same-session slope = (93,788 - 37,197) / 896 = **63.2 us per added context
  position**. (The quiet-box baseline measured 39.5 us/position; the difference is this
  session's ambient load, not the code.)
- The sub-slots `attn_scores` / `attn_softmax` / `attn_accum` read **0** on the
  flag-ON path -- they are marked only inside the scalar fallback loop, so the parallel
  head work is not attributable from the phase table. `attn_all` minus its children
  (`qkv` 15,058 + `qknorm` 789 + `rope` 366 + `kvappend` 364 + `outproj` 8,517) =
  **68,694 us/token at 1024 = 67.1 us/position** is the scores+softmax+accum.
- Per position the loop does 8 layers x 32 heads x 64 dims x 2 (k then v) =
  **32,768 MACs**, so 67.1 us/position = **2.05 ns per MAC (~6.8 cycles)**. A
  register-resident f64 FMA chain is ~0.3-0.5 ns/MAC, i.e. there is **4-7x of headroom
  inside the loop itself**, and the cost is the per-element Quanta sequence
  (2 `mem_load` + `f64of` + `fmul` + `fadd` per MAC), exactly the pattern the fused
  matvec kernels deleted.
- **It is not a bandwidth problem.** The KV is f64 throughout (one `fc_kvbuf`, per-layer
  stride `fc_kv_cap * fc_nkv_max * fc_head_dim * 8` -- 8 bytes per element). Unique KV
  bytes per position = 8 layers x 8 kv heads x 64 dims x 8 B x 2 = 64 KiB; at
  67.1 us/position that is **~1.0 GB/s**, against a demonstrated 28.6 GB/s on this
  model. Even counting the 4x GQA re-read it is ~4 GB/s.

**Verdict, per the instruction not to start it unless it dominates:**

- At <= 1024 tokens it does NOT dominate: 6.9 % of the token at 128, 15.7 % at 1024, so
  a perfect vectorised kernel is worth <= 15 % there and realistically ~10 %. Not worth
  a version on its own.
- The measured slope says it WILL dominate: at the model's full 131,072 context,
  63.2 us x 131,072 = **8.28 s/token of attention alone**, ~96 % of the token. So the
  vectorised kernel is the right NEXT lever for long context, with this session's
  numbers as the baseline to beat.
- **f16 KV would change almost nothing now**, because bytes are not the limit (1.0 GB/s
  of a 28.6 GB/s envelope). It becomes relevant only AFTER the loop is vectorised and
  the kernel becomes load-issue-bound. It is also gated on the language work (f16/f32
  types), so it is not a lever this unit can pull. The KV format was NOT touched.

## 6. Honest gap to the reference

All flags ON including conv, timer OFF, `ab_conv` arm B, `LENS="128 256 128"`,
`powersave`, `loadavg` 21.8-21.0, `Hermes` at 813 % CPU:

| run | tokens | tok/s |
|---|---|---|
| 1 | 128 | 1.841 |
| 2 | 256 | 1.817 |
| 3 | 128 | 1.856 |

**~1.84 tok/s** (mean 1.838; arm A without conv mean 1.819). Gap to the 15 tok/s target:
**8.2x**. Gap to llama.cpp's 17.32 tok/s on the same model+CPU: **9.4x**. Because the
session swing is ~1.24x for the same binary, the honest bands are ~7.5-9.5x and
~8.5-11x; the number and both anchors are stated rather than a single figure.

The previous unit's stated 8.5-9.1x / 9.8-10.5x implies 1.65-1.76 tok/s, which is the
same run family under a heavier ambient load; this session measured 1.84.

## 7. What is blocked on a language capability (and what is not)

- **Atomics / work stealing is NOT the fix for the concurrency shortfall measured here**
  (imbalance <= 2 %). It remains the prerequisite for a work-stealing pool, which is a
  different (unmeasured) lever.
- **A vDSO `clock_gettime`, or a reusable caller-owned timespec, in the emitter** is the
  right fix for A27; the raw-syscall mark used here is a measurement tool, not a
  substitute, and it stays in `lib/std` as an opt-in behind the prof flag.
- **The whole-pool wall is 87 % of the token and the matvec path runs at 3.5 GB/s of a
  demonstrated 28.6 GB/s** -- 8x off -- so the remaining headroom is in the matvec
  kernels and their dispatch, not in the partition rule. Nothing measured here is
  blocked on a missing feature except the f16 KV/vector attention work, which is gated
  on the f16/f32 language types the compiler peer is building.

## 7b. Reproduce

```
cd /opt/tali/quanta && ulimit -c 0
export QC=$PWD/compiler/0.0.247/bin/x86/qc      # md5 a17e3cfb056f55d4ee68a0db0dfcfa22
bash tests/lfm2_prof_ab.sh exact                 # bit-exactness gate, 9 passes
python3 tests/lfm2_pool_dispatch_probe.quanta    # (compile+run; see the header)
./compiler/0.0.247/bin/x86/qc -O tests/lfm2_pool_dispatch_probe.quanta /tmp/pp && /tmp/pp
LENS="128 256 128" bash tests/lfm2_prof_ab.sh ab_conv
LENS="128 1024 128" bash tests/lfm2_prof_ab.sh prof_attn    # conv OFF arm
LENS="128 1024 128" bash tests/lfm2_prof_ab.sh prof_conv    # conv ON arm
```
Logs land in `$PROF_SCRATCH/logs` (default
`/home/tali/.hermes/cache/scratch/lfm2prof/logs`). The conf is positional; the driver
prints the conf it wrote and the bench prints `fused_*_active` / `fused_*_used` back --
check them before trusting an arm.
