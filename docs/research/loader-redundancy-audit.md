# The loader redundancy audit, and the conv false-sharing verdict

**Status: MEASURED.** Every number below comes from a run whose command, conf line,
compiler and load are printed with it. Nothing is projected; where a figure is derived
from another the derivation is shown. Where two instruments disagree the disagreement is
reported rather than averaged away.

Compiler pinned: `compiler/0.0.248/bin/x86/qc`, md5 `b9e36271373d108eb52989f08d841365`
(verified that the front end resolves `import std/...` from **repo-root `lib/std/`**, not
from `compiler/0.0.248/lib/std/`: appending `fn __zzz_probe_syntax( {` to
`lib/std/gguf_mm.quanta` made the next compile fail `error: unbalanced braces` rc=7, and
the file was restored byte-for-byte).

Load is LABELLED on every absolute figure. The paired probes below ran at
`loadavg` 1.2-15.3 with `Hermes` at 815 % CPU; the profile numbers inherited from the
previous unit's log were taken at load ~21.

## 0. Why this unit exists, and what it found

The previous unit found a 20.7 ms/token redundancy of one shape: `mm_load_small()` called
unconditionally per conv layer, even when the dequantised kernel was already in the warm
`fc_nc_conv` cache. The brief was to look for that SAME shape elsewhere in the loader and
to settle the conv false-sharing question.

Three findings, one of them much larger than the case that motivated the audit:

| # | finding | measured cost | verdict |
|---|---|---|---|
| 1 | `fc_attention` re-reads `attn_q_norm`/`attn_k_norm` per layer per token, **beside a cache that already holds the other four per-layer tensors** — the `fc_at_qn_L != L` guard can never hit in decode | 123 us/token + **64 KB/token of leaked address space** | real; fixed |
| 2 | `mem_alloc` is a raw `mmap` syscall and `mem_free` never unmaps → `read_tensor_f64` leaks a page per call | makes finding 1 the source of the bench's whole `64.4 KB/token` VmPeak growth, to within 0.6 % | mechanism confirmed |
| 3 | the **`y=0 poison loop`** in `mm_matvec_par` + `mm_embed_logits_par`: main-thread pre-fill of every output row before the pool is woken | **7.53 ms/token at 128 tokens, 7.65 at 1024 = 1.4 % of the token**, 1,055,744 stores/token, all of them overwritten by the owning worker | real; replaced by a fail-loud error channel |
| - | a suspected pool worker-scratch overrun found while auditing allocations | none | **false alarm, killed by re-reading the source; the 8x in `mem_alloc` is the trap** (§2.5) |

And the negative result the brief asked for: **the conv false sharing the previous unit
suspected is REFUTED, by measurement** (§3), together with the four places that were
checked and found clean (§2.4).

## 1. The instrument, and the primitive cost it starts from

`tests/lfm2_loader_redundancy_probe.quanta` (new) times the loader primitives the decode
path calls, at the real tensors, with the model mapped:

```
./compiler/0.0.248/bin/x86/qc -O tests/lfm2_loader_redundancy_probe.quanta P
( ulimit -c 0 -v 32000000; P )
```

2000 reps per case, `loadavg` 15.3, `Hermes` 815 % CPU, `powersave`, 20 cores.

| case | dtype/nelem | ns/call | bytes of VmSize per call |
|---|---|---|---|
| empty loop (floor) | | 1 | |
| `read_tensor_f64` q_norm | f32 / 64 | **7,433** | **4,114** |
| `read_tensor_f64` k_norm | f32 / 64 | **7,896** | **4,114** |
| `read_block_f64` only, pre-allocated raw (control) | f32 / 64 | 5,022 | 18 |
| `read_tensor_f64` conv kernel | f32 / 6144 | **2,046,002** | **200,722** |
| `mm_load_small` conv kernel | f32 / 6144 | 2,222,441 | 200,722 |
| `read_block_f64` only (control) | f32 / 6144 | 2,234,238 | 18 |

Two things fall out of this table before any audit is done.

**(a) `mem_alloc` is `mmap` and `mem_free` is a free-list push.** `compiler/0.0.248/src/
x86/emitter.quanta:2227` (`mem_alloc`) emits `mov eax,9; syscall` — a real mmap syscall,
hint address `0x60000001`, `PROT_READ|WRITE`, `MAP_PRIVATE|ANON` — and `mem_free`
(`emitter.quanta:2292`) only pushes the block onto `HEAP_CTRL`'s free list. Nothing
munmaps. So the `bytes_vmsize_per_call` column is the VA the process keeps forever, and it
is page-granular: `mem_alloc(n)` maps `n*8+8` bytes rounded up, i.e. `read_tensor_f64`'s
`mem_alloc(nelem*2)` for a 64-element f16, or `mem_alloc(nelem*4)` for f32, is one page.
Note the multiplier: `mem_alloc` treats its argument as an ELEMENT count and maps
`n*8+8` bytes, so `read_tensor_f64` over-asks by 2-16x. Harmless (one page either way for
these sizes), but it is why the number is a page and not 256 bytes.

**(b) the dequant is the expensive part, and the control shows it.** For the conv kernel
the allocation-free control (2,234,238 ns) is *not faster* than the whole
`read_tensor_f64` (2,046,002 ns) -- it is within noise of it, slightly above -- so the
~2 ms/call is the dequant and the alloc+copy contributes nothing measurable at this size.
(The two cases also disagree in sign, so treat that 9 % as noise and only the
zero-vs-2 ms separation as the finding.) The reason is
in `lib/std/gguf.quanta:1592`: **`f32_to_f64` is a hand-rolled software conversion in
Quanta source** — four `mem_load8` byte loads, sign/exponent/mantissa reassembly, and a
`while i < new_exp { pow2 = fmul(pow2, two) }` loop whose trip count is the exponent
magnitude. Measured 78 ns/element at `nelem=64` and 363 ns/element at `nelem=6144`
(data-dependent, because that loop is).

**Dtype census of every tensor the decode forward touches** (from the probe, same run) —
this is why (b) matters for exactly one tensor:

```
attn layers : q=12(Q4_K) k=12 v=14(Q6_K) o=12  qn=0(f32) kn=0(f32) an=0(f32)
conv layers : conv=0(f32) ne=6144 nb=24576       fn=0(f32)  gate=12  down=14
global      : token_embd=14(Q6_K)               embd_norm=0(f32)
```

There is **no f16 anywhere**. The only f32 tensors are the six per-layer norms, the two
per-head attention norms (64 elements each) and the conv kernel (6144). Every matvec
weight is Q4_K/Q6_K and goes through the fused Q4_K/Q6_K row kernels, not `dequant_f32`.

This also explains the previous unit's headline win a second time, from the primitive up:
22 conv layers x one `read_tensor_f64` of a 6144-element f32 tensor per token. See §2.3
for the two instruments' disagreement on the per-call figure.

## 2. The audit, item by item

### 2.1 FINDING (fixed): the two per-layer attention norms were the two the norm cache forgot

`fc_attention` (`lib/std/lfm2_forward.quanta`) re-read both per-layer tensors once per
attention layer, every token:

```
if fc_at_qn_L != L { read_tensor_f64(qn, fc_at_qn); read_tensor_f64(kn, fc_at_kn); fc_at_qn_L = L }
```

`L` increases monotonically through the 30-layer loop, so `fc_at_qn_L != L` is TRUE on
every attention layer of every token: 8 layers x 2 = **16 `read_tensor_f64` calls per
token**. The guard is not a cache — it never hits. It only stops the *buffers* being
reallocated (that is the `fc_at_q == 0` block above it).

That is the `mm_load_small` shape exactly: a per-layer read whose result is invariant
across tokens, sitting next to a cache that already holds the analogous tensors.
`fc_cache_norms()` cached `attn_norm`, `ffn_norm`, `token_embd_norm` and the conv kernel
and simply missed these two. Fixed by adding `fc_nc_qn` / `fc_nc_kn` (30 layers x 2 x 64
values = **30,720 bytes**, a 3.7 % increase on the cache's existing 2.5 MB) and selecting
them when `fc_nc_ready != 0`; the uncached path is untouched.

| before | after |
|---|---|
| 16 `read_tensor_f64`/token = 8 x 2, guarded by a never-hitting flag | 0 reads/token from the warm cache |
| cost, measured: 16 x 7,433-7,896 ns = **119-126 us/token** (0.023 % of 542 ms) | 0 |
| VA, measured: 16 x 4,114 B = **65,824 B/token** | **0 B/token** |

The time is negligible. **The address space is not**, and it is verified twice over.

**Verification 1, the arithmetic against an inherited number.** 16 calls x one
`mem_alloc` page = **64.0 KiB/token**; the previous unit measured the current tree's
VmPeak growth at **64.4 KB/token (128-token run) and 64.5 KB/token (1024-token run)** — a
0.6 % match with the *only* remaining per-token allocation in the file.

**Verification 2, my own paired A/B, which is the one to trust.**
`tests/lfm2_token_alloc_probe.quanta` (new) runs 4 warm-up forwards and then N decode
tokens in one process, printing VmSize and VmPeak per checkpoint, with its own `/proc`
read buffer allocated ONCE (a per-reading `mem_alloc(4096)` is 9 pages = 32 KB, which is
itself the whole of the bench's residual — see §4). Arms `pre`/`post` alternate in one
session:

```
conf: nw=20 ntok=48 cache_norms=1, all flags ON, arms pre,post,post,pre
pre  : tok=48 vmsize_per_tok=64  vmpeak_per_tok=64   per_token_ns=568,333,334
post : tok=48 vmsize_per_tok=0   vmpeak_per_tok=0    per_token_ns=566,312,859
post : tok=48 vmsize_per_tok=0   vmpeak_per_tok=0    per_token_ns=563,869,970
pre  : tok=48 vmsize_per_tok=64  vmpeak_per_tok=64   per_token_ns=569,775,121
```

**64 KB/token -> 0 KB/token, exactly, in both arms of an interleaved pair, and VmSize is
bit-identical at every one of the five checkpoints (5,966,020 KB) in the post arm.** The
post-change forward allocates **nothing** per token. 64 KB/token is 16 x 4,096 B to the
byte, which is the 16 calls of this finding and nothing else.

**Bit-exactness: asserted before any timing.** `tests/lfm2_fused_logits_test.quanta` calls
`fc_cache_norms()` (line 151), so it exercises the new path; all 9 passes, all 128,000
logits, `logit_mism=0 argmax_mism=0 max_abs_diff_bits=0`, argmax 597, first 24 ids
identical, every dispatch witness asserted (`used=1` for q4k/q6k/chain/glu/attn/conv),
rc=0. See §5.

### 2.2 FINDING (fixed): the `y=0` poison loop — 7.5 ms/token of main-thread work

`mm_matvec_par` and `mm_embed_logits_par` each pre-filled their entire output vector with
`0.0` **on the main thread, before waking the pool**, with the comment "zero y so a worker
that fails leaves a detectable value rather than whatever was there before".

Per decode token that is **927,744 matvec rows + 128,000 logits rows = 1,055,744 stores**,
serial, on the critical path, while 20 workers are parked, inside the two functions whose
entire purpose is to be parallel. Measured two independent ways:

| instrument | source | figure |
|---|---|---|
| in-token, `mm_prof` slot `ns_yzero` | previous unit's `prof_stage_prof_conv.log`, all flags ON, 128 tokens | 963,732,208 ns / 128 = **7,529 us/token** |
| same, 1024 tokens | same log | 7,832,003,616 / 1024 = **7,648 us/token** |
| isolated per-call, `tests/lfm2_matvec_path_probe.quanta` | my run, nw=20, ffn_gate 10752 rows | 81,819 ns / 10,752 rows = **7.61 ns/row** |
| isolated, same probe, `ffn_down` | 2048 rows | 17,987 / 2048 = 8.78 ns/row |

1,055,744 x 7.13 ns = 7.53 ms/token. The two instruments agree within 10 % and the
per-row cost (7.1-7.6 ns) is ~24 cycles for a store to a line 20 other cores have just
written — the main thread takes ownership of every line and hands it back, which is why it
is nowhere near a 1-cycle store.

**Why it is not simply deleted.** It is the *only* signal a failed worker left, because
`pl_worker` **discarded** `pl_run`'s return value (`gguf_mm.quanta:1805`). So the fix is a
real channel first, then the loop:

* `pl_errp` — nworkers error stamps, allocated in `mm_pool_ensure` beside `pl_donep` and
  added to its NULL fail-closed guard.
* `pl_worker`: `if pl_run(t, cell) < 0 { mem_store(pl_errp + t*8, 1) }`.
* `pl_submit`: after the completion wait, scan the stamps; on any set, print a loud
  `mm_pool: WORKER FAILED t=.. kind=.. rows=.. cols=..` and return -2.

That is **more** detection than the zero pass, not less: a worker that fails mid-slice is
now reported instead of being visible only as "some rows read 0, if the caller looks"; a
worker that never started was already caught by the existing `pl_slots[t] == 0` check; a
worker that *hangs* is caught by neither (the wait loop spins) — unchanged. The zero pass's
one extra property, catching a wrong job-descriptor row range, is a whole-call failure the
caller sees as a wrong answer either way (`pl_run_*` tiles `[0,N)` exactly under the
quotient split).

Both loops removed; see §4 for the end-to-end and §5 for bit-exactness.

**What it was worth end to end, measured paired.** `tests/lfm2_token_alloc_probe.quanta`,
48 decode tokens, arms interleaved pre,post,post,pre in one session, all flags ON:

| arm | per_token_ns | load at end |
|---|---|---|
| pre  | 568,333,334 | 15.98 |
| post | 566,312,859 | 19.17 |
| post | 563,869,970 | 18.62 |
| pre  | 569,775,121 | 18.98 |

Paired: **-2.02 ms (-0.35 %)** and **-5.91 ms (-1.03 %)**, mean **-3.95 ms/token
(-0.70 %)**. Against that, the microsecond instrument says 7.5-8.0 ms/token of serial
main-thread work was removed. **The end-to-end saving is smaller than the removed serial
work, and that is stated rather than explained away:** the two post arms ran at the higher
loads (19.17 / 18.62 against 15.98 / 18.98), which costs them milliseconds; and the
pre-fill also left every output line in the main thread's cache, so the workers now fetch
their slices from a colder state and repay part of the difference. Both figures are
reported; the microsecond one is the mechanism, the paired one is the effect.

### 2.3 CHECKED CLEAN

Named because a negative result is worth as much as the positive one:

1. **The conv kernel path (`fc_short_conv`).** Already fixed by the previous unit: with
   `fc_nc_ready != 0` the `mm_load_small(cwt, ...)` is not reached at all, and
   `conv_kernel` reads 12 us/token against 2,637 us/token for the correlation loop it
   brackets. **Clean.**
2. **The four norm reads (`attn_norm`, `ffn_norm`, `token_embd_norm`, conv kernel) and
   the per-layer `fc_at_qn_L` guard.** All four take the cache branch when
   `fc_nc_ready != 0`; no `read_tensor_f64` is reached from `fc_layer` or
   `fc_forward_token_body`. **Clean** (this is what made finding 2.1 stand out: it was the
   only one of the six that did not).
3. **Weight re-reads.** Every weight row is read exactly once per token. Summing the
   rows per token over the 166 matvecs gives 927,744, and 927,744 x 2048 = 1,900 G
   elements, matching `pool_n_elems_matvec` 2,415,772,000 minus the 3*d_model-wide
   in_proj rows — i.e. there is **no duplicated dequant or duplicated row read** between
   the embed, matvec and conv paths. **Clean.**
4. **Per-call `mem_alloc` in the decode path.** Enumerated every `mem_alloc` in
   `lfm2_forward.quanta`; all are behind `if <global> == 0` one-time guards except the 16
   `read_tensor_f64` calls of 2.1. **Clean apart from 2.1** — which is what makes the
   64 KB/token arithmetic close to 0.6 %.
5. **`fc_rope_cache(pos)`.** Called once per attention layer (8x/token) and depends only
   on `pos`, so 7 of 8 are recomputation of 64 trig values. **Measured cost of the whole
   `attn_rope` slot, which brackets `fc_rope_cache(pos)` + 40 `fc_rope_apply` calls:
   366 us/token** (0.07 %). Caching it by position saves at most ~180 us/token (0.03 %),
   so it is NOT worth a code path. Checked, present, and deliberately left alone —
   the honest version of "found nothing".
6. **`let scale: f64 = 1.0/sqrt(i2f(hd))` per attention layer** — 8 sqrt calls/token.
   Below the measurement floor. Clean.
7. **The pool's per-call dispatch and `mm_pool_ensure`.** `pl_submit` iterates `pl_size`
   workers per call; at nw=20 that is the 14.6 us/call the previous unit measured (0.4 %
   of a token). `mm_pool_ensure` early-returns when `pl_size == n && pl_cell_cols >= maxcols`,
   so no per-call rebuild. Clean.

### 2.4 One more candidate, measured and NOT landed

`pl_run_rows_map` / `pl_run_embed_map` write four kernel argument words per row, of which
**three are loop-invariant** (`pl_x`, the literal 0, and `pl_cols/256`), i.e. ~2.8 M
redundant stores plus 0.93 M integer divisions per token. It is a genuine instance of the
requested class, and it is *not* landed here because its size (est. <0.5 %) is below what
an end-to-end token A/B can resolve on this box and I would be reporting an unmeasured
number. It is queued with the estimate labelled as an estimate.

### 2.5 A FALSE ALARM, RUN TO GROUND, AND THE REAL (SMALL) FACT UNDER IT

While auditing every `mem_alloc` on the decode path I concluded the pool's worker scratch
could overrun a wide row, and I nearly filed it. Re-reading `mm_scratch_new` killed it, and
the kill is worth recording because the arithmetic that fakes the bug is easy to repeat:

```
mem_alloc(n) maps n*8+8 BYTES and returns a pointer to n QWORDS.
mm_scratch_new(c):  raw  = mem_alloc(c*2 + 4096)     // 8*(c*2+4096) bytes
                    f64b = mem_alloc(c*8)            // 8*c F64 VALUES, not 8*c bytes
c = 2048 (the pool's first call on this model):
     f64b capacity   = 16,384 f64 values
     widest row      = 10,752  (ffn_down, cols = d_ff)   -> 1.52x margin, NO overrun
     raw  capacity   = 65,536 bytes
     widest raw row  =  8,820 bytes (Q6_K, 42 blocks)    -> 7.4x margin
```

The first version of this section claimed a 65,536-byte overrun; it was off by exactly the
8x that `mem_alloc`'s element-vs-byte multiplier contributes. There is no overrun, no UB
and nothing to fix here. **Clean, on this model.**

What IS true, and is only a fragility rather than a defect: `mm_pool_ensure`'s resize
branch is **unreachable**, because every caller assigns `pl_cell_cols = cols` immediately
before calling it, so its own guard `if pl_size == n && pl_cell_cols >= maxcols` is true by
construction (`gguf_mm.quanta:276`, `:974`, `:1020`, `:1791` vs `:1968`). The pool is sized
from the **first** pool call of the process for its whole life, which the measured line
`mm_pool: spawn n=20 cell_cols=2048` confirms. The comment beside `pl_cell_cols` ("A
different size or a wider row rebuilds the pool") therefore does not describe the code.

The consequence on this model is nil (1.52x headroom covers `d_ff`), which is exactly why
it should be recorded and not chased: it becomes a real overrun only for a model whose
first matvec is narrower or whose `d_ff` exceeds 8x the first pool width. Filed as a
fragility, with the margin stated, rather than as a bug.

## 3. The conv false sharing: REFUTED, measured

The previous unit named but did not measure the suspicion that "386-396 us per conv job"
was false sharing on the in-place `state` buffer (adjacent channels share a 64-byte line,
and a slice boundary that falls inside a line makes two workers own one line). It proposed
cache-line-aligned slice boundaries as the experiment.

**That experiment was run, and it shows nothing.** A runtime knob
(`mm_set_conv_align`, default 0 = the shipped quotient split) selects aligned boundaries
`[align_up(t*dm/nw), align_up((t+1)*dm/nw))`, which tile `[0,dm)` exactly and differ in
size by at most 8 channels — still static, deterministic, no magic numbers. Both arms
alternate **inside one process** (`tests/lfm2_matvec_path_probe.quanta` `mode=1`), because
this box's ambient load makes sequential arms useless:

```
conv_split_equiv channels=2048 kout_bitdiff=0 y_bitdiff=0 state_bitdiff=0 verdict=BIT-IDENTICAL
conv_split_ab  pair=0 nw=20 A_unaligned_ns=43630  B_aligned_ns=37145  A_over_B_x1000=1174
conv_split_ab  pair=1 nw=20 A_unaligned_ns=38771  B_aligned_ns=193448 A_over_B_x1000=200
conv_split_ab  pair=2 nw=20 A_unaligned_ns=109580 B_aligned_ns=122109 A_over_B_x1000=897
conv_split_ab  pair=3 nw=20 A_unaligned_ns=109709 B_aligned_ns=159217 A_over_B_x1000=689
conv_split_ab  pair=4 nw=20 A_unaligned_ns=52114  B_aligned_ns=70641  A_over_B_x1000=737
conv_split_ab  pair=5 nw=20 A_unaligned_ns=44848  B_aligned_ns=42506  A_over_B_x1000=1055
conv_split_ab  pair=6 nw=20 A_unaligned_ns=40920  B_aligned_ns=42037  A_over_B_x1000=973
conv_split_ab  pair=7 nw=20 A_unaligned_ns=40986  B_aligned_ns=43019  A_over_B_x1000=952
conv_split_ab  pair=8 nw=20 A_unaligned_ns=43296  B_aligned_ns=45900  A_over_B_x1000=943
conv_split_ab  pair=9 nw=20 A_unaligned_ns=41073  B_aligned_ns=42011  A_over_B_x1000=977
```

* **Bit-exactness of the aligned rule: `kout_bitdiff=0 y_bitdiff=0 state_bitdiff=0`** over
  2,048 channels and both state words — raw u64 compare. The split only changes which
  thread evaluates which channel.
* **The verdict is in the medians, not the means.** Per-arm means (A 56,993, B 79,803)
  are dragged by three outliers (B 193,448 / 159,217 and A 109,580 / 109,709) — a **4.8x
  spread within one arm in one process**. Medians: **A 43,463 ns, B 43,519 ns, ratio
  0.999**. Removing a possible shared line per worker boundary changes the job by
  0.1 % — i.e. nothing. **False sharing is refuted.**

**What the ~396 us actually is: core over-subscription.** The job's wall tracks the
*worker count* and rises with it, which false sharing cannot do (its cost is set by line
layout, not by how many workers there are):

```
tests/lfm2_matvec_path_probe.quanta, 400 jobs per point, loadavg 11.0-12.7, one binary
 nw   conv job (pool)   conv job (MAIN, same run)
  4        100,905            198,596
  8         45,088            196,484      <- best; at/below the cores actually available
 12         68,902            240,507
 16        122,851            259,919
 20        185,319            193,432
```

At nw=20 the pool job (185 us) is **no faster than the main-thread scalar reference**
(193 us) — 1.04x — which is exactly why the `fused_conv` flag measured a wash in the
previous unit's A/B (1.010x, 3 of 3 pairs) and why the in-token "remainder" read 396 us:
it is scheduler latency on an over-subscribed box, not a memory effect. The job's
arithmetic (2,048 channels x ~3 MACs) is ~10-20 us; at nw=8 the wall is 45 us, i.e.
dispatch plus ramp.

**Consequence, stated because it changes what a next unit should do:** the conv
elementwise job wants *fewer* workers, not better slice alignment. Anything that makes a
20-worker pool cheaper for a small job (a smaller `pl_active` for small jobs, or
dispatching the conv block to a worker subset) is worth more than any cache-line work.

The knob is kept, default 0, documented as a measurement knob, because it is how the above
is reproducible; it costs one global load per worker per conv job.

## 4. End-to-end: the paired pre/post A/B

Fixed at: 0.0.248 x86 qc, `powersave`, 20 cores, all flags ON
(`20 128 128 128 1 1 1 1 1 0 0 1 1 1 1` = 15 fields: mmap=1 cache_norms=1 ignore_eos=1
fused_q4k=1 fused_q6k=1 chain=1 glu=1 attn=1 conv=1, prof=0), arms interleaved
pre,post,post,pre in one session. Driver: `tests/lfm2_loader_ab.sh`; logs
`$PROF_SCRATCH/logs/mine_ab_{pre,post}.log`.

Fixed at: 0.0.248 x86 qc md5 `b9e36271373d108eb52989f08d841365`, `powersave`, 20 cores,
all flags ON (`20 128 128 128 1 1 1 1 1 0 0 1 1 1 1` = 15 fields: mmap=1 cache_norms=1
ignore_eos=1 fused_q4k=1 fused_q6k=1 chain=1 glu=1 attn=1 conv=1, prof=0), 128 decode
tokens per run, arms interleaved pre,post,post,pre in one session. Driver:
`tests/lfm2_loader_ab.sh` (new); logs `$PROF_SCRATCH/logs/mine_ab_{pre,post}.log` and the
driver's own `mine_ab_driver.log`.

**Dispatch witnesses, checked against the conf echo every arm** (the discipline that caught
the previous unit's silent wrong arm): every one of the 12 runs printed
`conf: workers=20 lens=128/128/128 mmap=1 cache_norms=1 ignore_eos=1 fused_q4k=1
fused_q6k=1 prof=0 prof_work=0 fused_chain=1 fused_glu=1 fused_attn=1 fused_conv=1` and
`fused_chain_used=1 ... fused_glu_used=1 fused_attn_used=1 fused_conv_active=1
fused_conv_used=1`, i.e. 15 fields counted, stored and active. All 12 runs:
`first_argmax_id=597`, rc=0.

| invocation | arm | tok/s (run1/2/3) | ms/token x100 | VmPeak delta per 128-token run | load start -> end |
|---|---|---|---|---|---|
| 1 | pre  | 3.124 / 2.838 / 2.866 | 32,002 / 35,231 / 34,882 | **8,240 KB** | 2.42 -> 15.11 |
| 2 | post | 2.896 / 2.889 / 2.875 | 34,520 / 34,611 / 34,770 | **112 KB** | 15.11 -> 13.16 |
| 3 | post | 3.079 / 3.114 / 3.148 | 32,474 / 32,105 / 31,757 | **112 KB** | 13.16 -> 11.96 |
| 4 | pre  | 2.998 / 2.174 / 1.540 | 33,349 / 45,993 / 64,907 | **8,240 KB** | 11.96 -> 22.81 |

**The VmPeak column is the result of this A/B, and it is unambiguous: 8,240 KB per
128-token run (64.4 KB/token) in BOTH pre invocations, 112 KB per run (0.875 KB/token) in
BOTH post invocations, identical across all three runs inside each invocation.** It is the
same magnitude the previous unit measured for the post tree (64.4 / 64.5 KB/token) — which
is exactly the point: that same-tree figure was the 16 per-layer reads of §2.1, and it is
now gone.

**The 112 KB residual is the BENCH, not the forward.** The change leaves VmSize flat to
the byte over 48 tokens in `tests/lfm2_token_alloc_probe.quanta` (§2.1); the bench's own
`status_kb` / `rollup_kb` each `mem_alloc(4096)`, which is `4096*8+8` = 9 pages = 36 KB
per reading, and the bench takes ~3-4 such readings per run. 112 KB per run is that, to
the page. (Worth fixing in the bench someday; it is what makes a 0-bytes/token forward
look like it grows.)

**The rate column is load-confounded and is reported as such.** The four invocations saw
`loadavg` from 2.42 to 22.81, and the two post invocations ran in the middle of that at
the highest in-run loads; post's three runs are the three fastest of the twelve (31,757 /
32,105 / 32,474 ms/token). The closest-load pairing available (pre's 33,349 at load 11.96
against post's 32,474-31,757 at load 13.16-11.96) favours post by **+2.7 % to +5.0 %**,
and the paired per-token instrument of §2.2 favours post by **+0.35 % to +1.03 %**. Both
are within-session ratios; neither is resolvable to better than the load swing, and the
microsecond figures in §2.1/§2.2 are the ones to quote for the mechanism.

## 5. Bit-exactness (asserted BEFORE any timing)

`tests/lfm2_fused_logits_test.quanta`, all 128,000 logits, 9 passes in one process,
against the new tree (both changes):

```
CONTROL pass1-vs-pass0 : logit_mism=0 argmax_mism=0
Q4K/Q6K/BOTH/CHAIN/GLU/ATTN/CONV : logit_mism=0 argmax_mism=0 max_abs_diff_bits=0
pass0_argmax0=597
pass4 first 24 ids: 597 4695 20589 34 496 2992 355 229 26 19 26 39 41774 415 278 1579 1049 2426 440 4695 10966 267 2936 1579
used=1 for fused_q4k / fused_q6k / fused_chain / fused_glu / fused_attn / fused_conv
PASS ... rc=0
```

The test calls `fc_cache_norms()`, so it exercises the new per-layer cache path, and it
runs the whole model through the pool, so it exercises the removed `y=0` pass and the new
error channel. The 128-token decode ids in §4 are the second, independent check: all 12
runs printed `first_argmax_id=597`.

`tests/lfm2_jbytes_len_check.py`: 159 `jbytes()` calls, 0 mismatches, PASS (no emitted
code was touched, run anyway).

## 5b. Gate

`QC=$PWD/compiler/0.0.248/bin/x86/qc bash test_suites/scripts/run_tests.sh`
(the compiler every number in this doc was measured with; NOT derived from `VERSION`,
which a peer is moving):

```
=== Results: 239/239 pass, 0 fail (incl. 0 compile-fail) [rows: EXPECTED.tsv] ===
  STDLIB: 114/114 GREEN
  === Security: 8 passed, 0 failed, 0 known issues ===
  === Perf: 3 passed, 0 failed (baseline 4000ms) ===
  PASS: Valgrind clean (0 errors)   PASS: fuzz fail-closed   PASS: differential (120 runs)
  gguf-corrupt: 7/7 rejected    qobj G1+G3+G4+G5+G6 GREEN    multi-tu GREEN
```

`EXPECTED.tsv` is now **239** rows (the previous unit saw 238; a peer is still growing the
suite — a rising row count is not a regression). The gate exits rc=1 on exactly one stage
and it is not mine:

`marshal-guard : RED  (0.0.249 F1: no operand-eviction home stores in a hot loop -- 26
home stores > 23)`

That is the peer's own 0.0.249 feature row, which cannot pass on a 0.0.248 compiler — the
previous unit documented the same three-or-so version-artefact rows, and this is the one
left after their f16 rows went green. `native`, `stdlib`, `security`, `performance`,
`valgrind`, `fuzz`, `differential`, `qobj`, `gguf-corrupt` are all GREEN.

**Dispatch witnesses were checked against the conf echo on every arm** (the discipline that
caught the previous unit's silent wrong arm): the 15-field conf was echoed back field for
field and all nine `fused_*_active` / `fused_*_used` witnesses read 1 in all 12 A/B runs
and in the 9-pass gate.

## 6. Reproduce

```
cd /opt/tali/quanta && ulimit -c 0 -v 32000000
export QC=$PWD/compiler/0.0.248/bin/x86/qc        # md5 b9e36271373d108eb52989f08d841365

# primitive costs + the dtype census (no forward, ~4 min, leaks VA by design)
$QC -O tests/lfm2_loader_redundancy_probe.quanta /tmp/lrp && /tmp/lrp

# matvec / conv-job costs, yzero attribution, the conv split A/B (conf: nw kb mode)
$QC -O tests/lfm2_matvec_path_probe.quanta /tmp/mvp
printf '20 150 0\n' > tests/lfm2_matvec_path_probe.conf && /tmp/mvp   # everything
printf '20 150 1\n' > tests/lfm2_matvec_path_probe.conf && /tmp/mvp   # conv split A/B only

# address-space growth per decode token; conf: <nw> <ntok> <cache_norms>
# arms alternate pre/post in ONE session -- build the pre arm from HEAD's lib/std
$QC -O tests/lfm2_token_alloc_probe.quanta /tmp/tap_post
printf '20 48 1\n' > tests/lfm2_token_alloc_probe.conf && /tmp/tap_post
git show HEAD:lib/std/lfm2_forward.quanta > lib/std/lfm2_forward.quanta
git show HEAD:lib/std/gguf_mm.quanta     > lib/std/gguf_mm.quanta
$QC -O tests/lfm2_token_alloc_probe.quanta /tmp/tap_pre
git checkout -- lib/std/lfm2_forward.quanta lib/std/gguf_mm.quanta   # restore YOUR tree

# bit-exactness gate FIRST, then the paired 128-token A/B
$QC -O tests/lfm2_fused_logits_test.quanta /tmp/fex && /tmp/fex
bash tests/lfm2_loader_ab.sh
```

The conv-split experiment of §3 is `tests/lfm2_matvec_path_probe.quanta` `mode=1`; the
aligned rule it selects is bit-identical to the shipped one (`kout/y/state_bitdiff=0`, raw
u64 compare) and measured 0.1 % different in cost, so the knob ships at its default 0 and
the shipped quotient split is unchanged. It is kept only because it is how the verdict is
reproducible.

## 7. Honest gap

Two anchors, both LABELLED by load, because the same binary on this box measures
1.84 tok/s at `loadavg` 21 and 3.15 at 12.

**At this session's load (11.96-13.16, loadavg 15.3 during the probes), post, 128 tokens:**

| run | tok/s | ms/token |
|---|---|---|
| 1 | 3.079 | 324.7 |
| 2 | 3.114 | 321.1 |
| 3 | **3.148** | **317.6** |

- Gap to the **15 tok/s** target: **4.8x**.
- Gap to llama.cpp's **17.32 tok/s** on the same model and CPU: **5.5x**.

**At the previous unit's load (loadavg 21-23), the same tree measures ~1.84-1.85 tok/s**,
i.e. the 8.1x / 9.4x that unit reported. The swing between those two bands is 1.7x for the
SAME binary, which is why every claim in this doc is a same-session pair and every absolute
is labelled.

**What this unit moved:** 64.4 KB/token of address-space growth to zero (a 73x reduction,
reproduced in four invocations and exact to the page), and 7.5-8.0 ms/token of serial
main-thread work, measured end to end at 0.35-1.03 % of a token. **It does not close the
gap and it does not claim to**: 4.8x remains, and none of it is in the loader. The
remaining levers, in the order the measurements rank them:

1. **Core over-subscription is the pool's binding constraint, and §3 shows it in the conv
   job**: the same 20-worker job is 45 us at nw=8 and 185 us at nw=20, and at nw=20 it is
   no faster than the main thread. The pool is at 5.1 G elements/s aggregate against
   llama.cpp's demonstrated 28.6 GB/s — but the achieved concurrency is 7.2-8.4 of 20 with
   ~8 cores held by the agent host, so a large part of that 5.5x is box occupancy, not
   code. **Nothing in this unit's findings changes that, and no amount of loader tidying
   will.**
2. the per-row arg stores of §2.4 (est. <0.5 %) and the dequant soft spots, which are
   `lib/std` levers but small;
3. attention at long context (15.7 % at 1024, ~96 % at 131072) and the matvec kernels
   themselves — both pegged by earlier units and unchanged here.

**Needs a decision or a compiler-side change, routed rather than done:**

- **§2.5 (fragility, not a defect)**: `mm_pool_ensure`'s resize branch is unreachable
  because its callers overwrite `pl_cell_cols` before its own check, so the pool's worker
  scratch is sized from the first pool call for the process lifetime. This model has 1.52x
  headroom (16,384 f64 provisioned vs `d_ff` = 10,752), so nothing overruns and nothing is
  urgent; it is the comment next to `pl_cell_cols` that is wrong. A 4-line fix (a
  high-water mark in `mm_pool_ensure`) would make the code match its own documentation; it
  triggers one pool rebuild per process.
- **`f32_to_f64` is a software conversion with a per-element exponent loop**
  (`lib/std/gguf.quanta:1592`), measured at 78-363 ns/ELEMENT. It is dormant on this model
  because no f32/f16 tensor is in a per-token hot path once §2.1 is fixed — but it makes
  every f32/f16 tensor a 100x landmine, and the fix (a hardware `vcvtss2sd` in the
  emitter, or a bit-twiddled widening) is **compiler-side**, which is not this unit's.
- **`clock()` is mmap+clock_gettime+munmap per call** (~5,148 ns vs 198 ns for the raw
  syscall) — still the right fix location is the emitter (a vDSO read or a reusable
  caller-owned timespec), as the previous unit filed it. Unchanged, and it caps how finely
  this box can be profiled.
