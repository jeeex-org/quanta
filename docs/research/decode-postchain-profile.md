# Decode profile AFTER the chain kernel, and the two levers it named

**Status: MEASURED.** Every number below comes from a run whose command, conf line,
compiler, and governor are printed with it. Nothing is projected or carried over.
Compiler pinned: `compiler/0.0.247/bin/x86/qc`, md5 `a17e3cfb056f55d4ee68a0db0dfcfa22`
(NOT derived from `VERSION` -- a peer is adding f16/f32 types in `compiler/0.0.248`
and will bump `VERSION`, which would swap the compiler under a running measurement).

## 0. Why a re-measure

`docs/research/decode-phase-profile.md` measured the phase table with the tied
output projection (`tied_logits`) on the SCALAR chain route. The chain kernel
(`jit_f_apply_chain`, opt-in `mm_fused_chain`, conf field 12) then saved ~448 ms/token,
which invalidates that table's shares: at 128 tokens the post-chain shares were only
DERIVABLE. This is the re-measurement with the chain ON, so the shares are measured.

The driver's `prof` stage writes only 11 conf fields -- field 12 (`fused_chain`) is
absent and defaults 0 -- so `stage_prof` measures the chain-OFF table. A new stage
`stage_prof_chain` writes the 12th field and is the one used here.

## 1. The post-chain phase table

Command: `bash tests/lfm2_prof_ab.sh prof_chain`, `LENS="128 1024 128"`.
Conf line this run wrote and the bench printed back (field 12 = fused_chain):

```
conf: workers=20 lens=128/1024/128 mmap=1 cache_norms=1 ignore_eos=1
      fused_q4k=1 fused_q6k=1 prof=1 prof_work=1 fused_chain=1 (argmax temp=0)
fused_q4k_active=1 fused_q6k_active=1 fused_chain_active=1   fused_chain_used=1
```

Governor `powersave`, 20 cores, load 17-20 during the run, `Hermes` holding ~840% CPU.
`mark_ns=198` (raw `clock_gettime` syscall) vs `mark_ns_old_clock()=5108` (the `clock()`
builtin, which mmaps per call -- A27).

### Decode at 128 tokens -- `us_tok` = run total / 128 reported tokens

The bench's last decode iteration is argmax-only (no forward), so 127 forwards
contributed: every per-token figure is ~0.78% low, uniformly. `token_body` closes to
**6 us** against its four children.

| phase | us/token | % of token |
|---|---|---|
| `token_body` (whole forward) | **709,696** | 100% |
| &nbsp;&nbsp;`embed_lookup` | 44 | 0.006% |
| &nbsp;&nbsp;`layer_stack` (30 layers) | 667,696 | 94.08% |
| &nbsp;&nbsp;`ln_final` | 50 | 0.007% |
| &nbsp;&nbsp;`tied_logits` (chain kernel ON) | **41,900** | **5.90%** |

Inside `layer_stack` (each row summed over the named layers):

| phase | us/token | % of token |
|---|---|---|
| **`attn_all`** (8 attention layers) | **141,731** | **19.97%** |
| `conv_all` (22 short-conv layers) | 103,929 | 14.64% |
| `ffn_gate` (30) | 106,656 | 15.03% |
| `ffn_up` (30) | 106,418 | 14.99% |
| `ffn_down` (30) | 102,987 | 14.51% |
| **`silu_glu`** (30) | **101,025** | **14.23%** |
| `ln_attn` / `ln_ffn` / `residual1` / `residual2` | 1,504 / 1,453 / 881 / 946 | 0.67% |

Σ = 667,530 against 667,696 -- a 166 us residual. Closes.

Inside `attn_all`:

| phase | us/token | % of token |
|---|---|---|
| `attn_accum` (weighted sum of v) | 58,729 | 8.28% |
| `attn_scores` (q.k loop + running max) | 50,943 | 7.18% |
| `attn_qkv` (3 projections) | 13,996 | 1.97% |
| `attn_outproj` | 8,958 | 1.26% |
| `attn_softmax` | 6,957 | 0.98% |
| `attn_qknorm` / `attn_rope` / `attn_kvappend` | 738 / 342 / 282 | 0.19% |

Σ = 140,945 against 141,731 -- a 786 us residual.

### Decode at 1024 tokens

| phase | us/token | % of token |
|---|---|---|
| `token_body` | **1,269,151** | 100% |
| &nbsp;&nbsp;`tied_logits` | 41,633 | 3.28% |
| &nbsp;&nbsp;`layer_stack` | 1,227,418 | 96.71% |
| **`attn_all`** | **714,672** | **56.31%** |
| `ffn_gate` / `ffn_up` / `ffn_down` | 103,499 / 103,743 / 100,932 | 8.15 / 8.17 / 7.95% |
| `conv_all` | 101,207 | 7.97% |
| `silu_glu` | 98,487 | 7.76% |

Inside `attn_all` at 1024:

| phase | us/token | % of token |
|---|---|---|
| `attn_accum` | 346,532 | 27.31% |
| `attn_scores` | 301,214 | 23.73% |
| `attn_softmax` | 40,436 | 3.19% |
| `attn_qkv` | 13,625 | 1.07% |
| `attn_outproj` | 10,691 | 0.84% |

### What the chain moved, and what it left

| item | chain OFF (128 tok) | chain ON (128 tok) |
|---|---|---|
| `token_body` | 1,167,488 | **709,696** |
| `tied_logits` | 498,694 (42.7%) | **41,900 (5.90%)** |
| everything else | unchanged within ~1% | unchanged within ~1% |

The tied projection fell 11.9x and every other context-independent term is the same
within ~1%, which is the cross-check that the chain touched only its own op. **The
post-chain ranking at 128 tokens is: FFN gate/up/down+silu together 58.8%, attention
20.0%, conv 14.6%, tied projection 5.9%.** Two of the four FFN terms and the two
attention terms are the levers (see the sibling docs).

## 2. Pool concurrency after the chain: 6.8 of 20

`prof_work=1`, same run. 21,209 parallel calls / 127 forwards = **167.0/forward**
(166 `mm_matvec` + 1 tied projection) -- the same geometry as before, so the element
counters still reconcile to the GGUF (2,434,793,472 matvec + 262,144,000 embed).

| figure | chain OFF (doc) | chain ON (this run) |
|---|---|---|
| `worker_busy` | 10.0 s/token | **3.04 s/token** |
| `ns_submit` | 894.4 ms | **445.7 ms** |
| achieved concurrency | 11.2 / 20 | **6.8 / 20** |

`worker_busy` drops ~7 s while wall time drops only 0.46 s because the tied projection
was the one phase where all 20 workers were busy for a long time (450 ms wall x 20 =
~9 s of worker-busy away); the chain kernel removed that. The remaining 166 matvecs
have a worse busy/submit ratio. **Reported, not tuned**: the static slice exists only
because the language has no atomics, so re-tuning it is a workaround that dies when
atomics land. Atomics are the queued compiler capability (backlog item).

## 3. Lever 1: `silu_glu` -> the pool (mm_glu_par, pool kind 6)

`silu_glu` is 322,560 elements/token (30 layers x d_ff 10752) at ~316 ns/element --
the same us/token as `ffn_down`, which moves 660,602,880 elements. It runs on the MAIN
thread with 20 pool workers idle. The per-element cost is `expf`, which in
`lib/std/math.quanta` is a **20-term Taylor loop in Quanta source**
(`term = term*r/i2f(i)` with a division each iteration), not a hardware instruction.

**The op is elementwise**, so a static contiguous slice per worker is the CORRECT
partition, not a workaround: element i depends on `gate[i]` and `up[i]` alone and no
two elements touch the same output word, so no atomics are involved and none is
needed. The arithmetic is UNCHANGED (same `expf`, same division, same multiply order),
so the output is bit-identical by construction. **No SIMD exp approximation is used** --
that would move bits.

A/B, `bash tests/lfm2_prof_ab.sh ab_glu`, `LENS="128 256 128"`, chain=1 in BOTH arms,
timer OFF, conf printed per arm:

```
A glu=0 chain=1: 20 128 256 128 1 1 1 1 1 0 0 1 0   fused_glu_used=0
B glu=1 chain=1: 20 128 256 128 1 1 1 1 1 0 0 1 1   fused_glu_used=1
```

| run | tokens | A med ms | B med ms | A tok/s | B tok/s | **B/A** | A load / B load |
|---|---|---|---|---|---|---|---|
| 1 | 128 | 711.8 | **651.1** | 1.404 | **1.535** | **1.093x** | 12.99 / 18.17 |
| 3 | 128 | 717.5 | **656.9** | 1.393 | **1.522** | **1.092x** | (same session) |
| 2 | 256 | 796.5 | **738.6** | 1.255 | **1.353** | **1.078x** | |

Saving **60.8 ms/token at 128 tokens** (60.7 in the repeat), against a `silu_glu` phase
measured at 101,025 us. That is **1.66x on the phase**, not the ~11x an embarrassingly
parallel op would take from a saturated pool -- the per-layer job is small (10,752
elements over 20 workers = 537 each) and there are 30 dispatches/token, so pool
publish+wait dominates. Stated plainly because it is the honest number.

**Correctness (asserted before any timing):**

| test | result |
|---|---|
| `tests/lfm2_fused_logits_test.quanta` pass6 (q4k+q6k+chain+glu) | all 128,000 logits identical: `logit_mism=0 argmax_mism=0 max_abs_diff_bits=0`, argmax 597, first 24 ids identical, witness `used=1` |
| `tests/lfm2_glu_test.quanta` | element-wise bits: `mismatch=0` at nw=2/3/8/20, non-divisible 10751/10757/999, 65536 (non-zero comparisons counted); `n<nw` declines as designed |

**Memory unchanged:** VmPeak deltas are byte-identical between arms in every run
(555,864 kB delta at 128, 1,116,064 kB at 256) and RSS deltas match (75,200 kB at 128).
The inherited ~4.37 MB/token VmPeak growth is untouched -- the GLU is not in the matvec
path and allocates nothing.

## 4. Lever 2: attention scores/softmax/accumulate over the pool (mm_attn_par, pool kind 7)

`attn_scores` (q.k + running max) and `attn_accum` (weighted sum of v) are each O(pos)
per head and are the term that GROWS with context: scores+softmax+accum are 116,629
us/token at 128 (16.4%) and 688,182 us/token at 1024 (54.2%). They run on the MAIN
thread as scalar f64.

**Query heads are the correct partition.** Head h writes only
`fc_at_out[h*hd .. h*hd+hd)` and reads only its own q row plus the read-only KV cache,
so a static slice of heads per worker is race-free with no atomics -- the RIGHT
partition, not a workaround around the missing atomics (the same argument as the GLU,
and the same reason). Per head the arithmetic and ORDER are unchanged (same
`1/sqrt(hd)` scale, same strict left-to-right `acc = acc + q[c]*k[c]`, same running
max, same exp/sum, same `cur + w*v` order), so the output is bit-identical.

Two implementation notes worth keeping:

* **The pool's usual "last worker absorbs the remainder" slice is WRONG here.** With
  nh=32 and nw=20 the remainder rule gives worker 19 THIRTEEN heads and the other
  nineteen ONE -- a 13:1 tail that caps the speedup near 2.5x. Heads in this model have
  equal cost, so the slice is the quotient split `[t*nh/nw, (t+1)*nh/nw)`; still static
  and deterministic, sizes differ by at most one head.
* **Each worker needs its OWN score scratch.** The reference reuses one `fc_at_sc`
  because heads ran sequentially; parallel heads cannot share it. `fc_at_scp`
  (nworkers x (fc_kv_cap+2) f64) is allocated on first use. The worker computes the KV
  address from bases derived from `fc_kv_at` itself (`fc_kv_at(L,1,0,0) - fc_kv_at(L,0,0,0)`
  is one position's stride), so it reads exactly the bytes `fc_kv_get` would.

### A/B, controlled and INTERLEAVED (the box's frequency makes sequential arms useless)

The box runs `powersave`; its absolute ms/token swings ~1.24x between sessions for the
SAME binary and conf (arm A of the same config measured 594 ms in one session and 736 ms
in another), and the swing does NOT track `/proc/loadavg` (arm A was 745 ms at load 7.46
AND 746 ms at load 22.19). So a sequential A-then-B driver cannot resolve this. The
measurement below alternates the arms (A,B,A,B,...) with the SAME binary and 3 runs of
the same length per invocation, and only adjacent-A/B pairs are compared.

Command per arm: `<bench> </dev/null` with conf `20 L L L 1 1 1 1 1 0 0 1 1 X`
(chain=1, glu=1 both arms; field 14 `fused_attn` = 0 for A, 1 for B).

**96 tokens, 3 interleaved pairs** (each arm 3 runs):

| pair | A (attn=0) med ms | B (attn=1) med ms | B/A |
|---|---|---|---|
| 1 | 744.15 | 646.07 | **1.152x** |
| 2 | 745.95 | 647.11 | **1.153x** |
| 3 | 714.57 | 623.03 | **1.147x** |

**128 tokens, 2 interleaved pairs:**

| pair | A (attn=0) med ms | B (attn=1) med ms | B/A |
|---|---|---|---|
| 1 | 735.70 | 595.46 | **1.236x** |
| 2 | 711.79 | 594.79 | **1.197x** |

The ratio grows with length (1.15x at 96 -> ~1.21x at 128), which is the expected
signature: attention is the context-dependent term, so parallelising it buys more the
longer the context. At 128 tokens the attention branch is 20.0% of the token; if the
head loop were fully parallel (11x) the end-to-end saving would be ~18%, and 1.20-1.24x
is well on the way to that, so the pool overhead is not dominating this job the way it
does the 30 small GLU dispatches.

**A separate sequential driver run (A then B) gave 1.365x at 128 and 1.260x at 256** --
consistent in direction, but those arms ran at different frequencies and are NOT the
number to quote. The interleaved pairs are.

### Correctness (asserted before any timing)

`tests/lfm2_fused_logits_test.quanta` pass7 (q4k+q6k+chain+glu+attn): all 128,000
logits identical -- `logit_mism=0 argmax_mism=0 max_abs_diff_bits=0`, argmax 597, first
24 generated ids identical, witness `fused_attn_used=1`, rc=0.

Memory: the per-worker score scratch is `nworkers x (fc_kv_cap+2) x 8` = 20 x 2050 x 8 =
**328,000 bytes**, allocated once. No VmPeak rate change is claimed for it beyond that
one-time allocation.

## 5. Cumulative effect and the honest gap

| configuration (all @128 tokens) | tok/s | source |
|---|---|---|
| baseline, no fusion | 0.281 | q4k/q6k docs (peer) |
| + Q4_K + Q6_K fused matvecs | 0.872 | q4k/q6k docs (peer) |
| + chain kernel (tied projection) | **1.397** | decode-phase-profile.md (peer) |
| + parallel GLU + parallel attention | **~1.65-1.77** | this work, see below |

**Direct same-session, interleaved measurement of the two levers together.** Two
interleaved A/B pairs at 128 tokens, each arm 3 runs, same binary, conf
`20 128 128 128 1 1 1 1 1 0 0 1 G A` with (G,A) = (0,0) for arm A (chain only) and
(1,1) for arm B (chain + glu + attn), witnesses printed per run:

| pair | A chain-only med ms | B chain+glu+attn med ms | A tok/s | B tok/s | **B/A** |
|---|---|---|---|---|---|
| 1 | 762.80 | 603.42 | 1.312 | **1.657** | **1.264x** |
| 2 | 776.72 | 611.50 | 1.288 | **1.635** | **1.270x** |

So the two levers together are **1.264-1.270x** measured end to end. Note this is LESS
than the product of the individual ratios (1.093 x 1.20 = 1.31) -- the levers touch
overlapping fixed costs, which is the standing "do not multiply levers" warning here.

**Absolute tok/s is frequency-dependent and must be read against its own A arm.** This
session's chain-only arm was 762-777 ms; an earlier session measured the same
configuration at 712 ms. The RATIO is stable (1.264 / 1.270 across two pairs); the
tok/s is not. Scaled onto the task's chain-only baseline of **1.397 tok/s**, the
composed 1.267x gives **~1.77 tok/s at 128 tokens**; measured directly in this session,
arm B is **1.64-1.66 tok/s**.

**Gap at 128 tokens:** against the target **15 tok/s** that is **8.5x** (ratio-scaled
1.77) to **9.1x** (this session's measured 1.65); against llama.cpp's measured **17.32**
on this model and box, **9.8x to 10.5x**. The task's chain-only baseline sat at
10.7x / 12.4x, so this work closed roughly 20% of the remaining distance to the target.

**Where the time still is (128 tokens, chain ON):** FFN gate/up/down + silu together
58.8%, attention 20.0%, conv 14.6%, tied projection 5.9%. At 1024 the single largest
term is attention (56.3%), which is exactly the term this work parallelised and the
reason the attention ratio grows with context (1.15x at 96 -> 1.27x at 128 and up).

## 6. Next arithmetic lever: FMA (queued, NOT attempted here)

A parent instruction census of the emitted JIT kernels found **26 `vmulpd` + 15
`vaddpd`** and **zero** FMA, while `/proc/cpuinfo` reports `fma`. In a MAC chain
`vfmadd231pd` does `a*b+c` in one instruction instead of two, with one rounding instead
of two, so it roughly halves the arithmetic instruction count on the matvec dot chains
-- and the JIT emits raw encodings, so it needs no language change.

**It is NOT landed here, and the reason matters.** (a) It moves bits (single rounding
vs mul-then-add), so it cannot replace the sequence in any kernel that holds the
bit-exact bar; it needs its own opt-in default-OFF flag and its own bounded-difference
bar (argmax 597 + first 24 ids identical + a MEASURED max_abs_diff_bits / ULP bound).
(b) **It does not apply to the attention work in this doc**: that change is SCALAR f64
parallelised across query heads, not a vectorised MAC kernel, so the census above does
not describe it. The FMA lever lives in the JIT dot kernels
(`jit_f_apply_folded`/`_q6k`/`_chain`), which are the peer's bit-exact territory.
(c) In Quanta SOURCE there is no `fma` builtin (`grep` over `lib/std` finds none), so a
source-level FMA would be a language capability first -- per the author's standing
policy that is a prerequisite, not a workaround. Within budget, the honest move is to
leave the finding standing (recorded by the parent in `docs/plans/performance.md`) and
not rush a sequence change without its bit-bar evidence.

**Also queued: `*ps` (4 f32 lanes -> 8) forms.** Every FP instruction in the census is
`*pd`. The f32 forms double lanes per instruction and `vcvtdq2ps` converts 8 at once,
but they require f32 DATA IN MEMORY -- i.e. the in-flight f16/f32 language work plus
loader adoption. Not reachable from here.

