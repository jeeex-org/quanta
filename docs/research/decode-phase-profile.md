# Where a decode token's time actually goes (0.0.246, after the fused matvecs)

**Status: MEASURED.** Every number below comes from a run whose command, conf line
and flags are printed with it. Nothing here is projected or carried over from an
earlier profile.

## 0. Why this exists

The Q4_K and Q6_K matvec kernels landed fused, bit-exact and 18x / 9.9x faster than
the dequant+dot pair they replaced. That invalidated the previous profile: the Q4_K
dot had been ~60% of a decode token and is now roughly a tenth of one, so ~1.15 s
per token was spending itself somewhere nobody had measured. The project had
already wasted a day on an invented bandwidth envelope, so the rule here was
instrument first and let the instrument name the target.

## 1. The instrument

`lib/std/lfm2_forward.quanta` — `fc_prof_*`

* 28 **inclusive** phase slots. `fc_prof_begin(s)` / `fc_prof_stop(s)` bracket a
  region and `s` accumulates the elapsed ns, so a parent slot CONTAINS its
  children. The driver prints the nesting in the labels (`  attn_qkv(8x)` is
  indented under `attn_all(8x)`), and the table **closes**: in the 8-token
  calibration sample below, the four top-level children sum to 978,305 us against a
  `token_body` of 978,311 us — a 6 us residual on a 978 ms token. Nothing in the
  table is a remainder or an inferred term; every row is a timed region.
* Labels and slot indices come from `fc_prof_label()` / `fc_prof_nslot()`, never
  from a copy in the driver. A hand-copied index table one edit out of date prints
  the right name over the wrong phase, which is the same failure class as the
  positional bench conf that already silently measured the wrong arm once here.
* Default OFF. `fc_prof_on == 0` costs one compare per mark site.

`lib/std/gguf_mm.quanta` — `mm_prof_*`

* Dispatcher-side publish+wait ns, `y`-zero ns, `pool_ensure` ns, parallel-call and
  element counts, and a **per-worker busy accumulator** (worker `t` writes only slot
  `t`; disjoint writers, so no atomics are needed — and the language has none).
  `worker_busy_sum / submit_sum` is the achieved pool concurrency, which the phase
  table alone cannot answer.

### The mark primitive, and the compiler defect it exposes

`clock()` in this emitter is **`mmap(16)` + `clock_gettime` + `munmap(16)` per
call** (`compiler/0.0.246/src/x86/emitter.quanta:3142-3168`). Measured with a
standalone probe whose loop does increment its counter: **5148 ns per call**
standalone, **3396 ns** in-process — against **153 ns** for one raw
`clock_gettime(CLOCK_MONOTONIC)` syscall into a preallocated timespec. Both figures
are printed side by side in every profile dump (`mark_ns=` and
`mark_ns_old_clock()=`), so the ratio is a measurement, not a claim.

Every mark therefore uses `syscall(228, 1, ts, 0,0,0)`, with a **per-worker**
timespec (`cell+32`) so the 20 workers never share the buffer the kernel writes.

**This is a compiler-level defect, not a lib/std workaround.** `clock()` is the
language's only monotonic time builtin and it is unusable at any sampling rate: at
~2000 marks per decode token it is 10 ms/token of pure mark cost on a token that
costs ~1200 ms, before the VMA churn's effect on other cores. The fix belongs in
the emitter (a vDSO read, or a caller-owned reusable timespec); `compiler/**` is
not this unit's to change, so it is reported rather than patched.

### A retracted claim, kept so it is not re-derived

An earlier version of this work asserted that each mark cost ~5 ms of *token* time,
inferred from two prof runs that took ~12 s/token with the process pinned near 88%
of one core. **Those runs were not measuring anything**: the calibration loop was
written `while j < 2000 { clock() }` with no incrementer, so it never terminated and
the process was spinning in `clock()`. The 5148 ns/call figure stands (direct
measurement); the "5 ms per mark" figure is **withdrawn**.

## 2. The flag set, printed with every run

`tests/lfm2_decode_bench.conf`, positional:

```
<workers> <len1> <len2> <len3> <use_mmap> <cache_norms> <ignore_eos>
<fused_q4k> <fused_q6k> [prof] [prof_work] [fused_chain]
```

Fields 10-12 are new and optional: a 9-field conf still works, everything defaults
0, so the peer driver `tests/run_q6k_fused_ab.sh` is unaffected. The driver and the
bench both print the conf line actually written, immediately before running.

Driver: `bash tests/lfm2_prof_ab.sh exact|baseline|prof|prof_nw|conc|ab`.
Compiler **pinned**: `compiler/0.0.246/bin/x86/qc`,
md5 `094020ff498e993d4888c41965584fe4` — not derived from `VERSION`, because a
second unit is bumping `VERSION` for a new compiler tree and a mid-flight swap
would silently change what was measured.

## 3. The phase table

Command: `bash tests/lfm2_prof_ab.sh prof`, `LENS="128 1024 128"`.
Conf line actually written and printed by the run (field 12 = fused_chain):

```
conf: workers=20 lens=128/1024/128 mmap=1 cache_norms=1 ignore_eos=1
      fused_q4k=1 fused_q6k=1 prof=1 prof_work=1 fused_chain=0 (argmax temp=0)
```

Compiler `compiler/0.0.246/bin/x86/qc` md5 `094020ff498e993d4888c41965584fe4`,
governor `powersave`, load 19-20 during the run, `Hermes` holding ~840% CPU.

### Decode at 128 tokens — average over the run's decode tokens

`us_tok` is the run total divided by the 128 reported tokens. The bench's last
decode iteration computes the argmax of the next token and no forward, so 127
forwards contributed: **every per-token figure below is 0.78% low**, and the pool
counters reconcile exactly at 127 (see §5).

| phase | us/token | % of token |
|---|---|---|
| `token_body` (the whole forward) | **1,167,488** | 100% |
| &nbsp;&nbsp;`embed_lookup` | 52 | 0.004% |
| &nbsp;&nbsp;`layer_stack` (all 30 layers) | 668,675 | 57.3% |
| &nbsp;&nbsp;`ln_final` | 53 | 0.004% |
| &nbsp;&nbsp;**`tied_logits`** (tied output projection) | **498,694** | **42.7%** |
| Σ of the four = 1,167,474, i.e. a **14 us** residual | | |

Inside `layer_stack` (each row is that phase summed over all 30 layers):

| phase | us/token | % of token |
|---|---|---|
| `attn_all` (8 attention layers) | 146,818 | 12.6% |
| `conv_all` (22 short-conv layers) | 103,351 | 8.8% |
| `ffn_gate` | 104,560 | 9.0% |
| `ffn_up` | 104,639 | 9.0% |
| `silu_glu` | 101,959 | 8.7% |
| `ffn_down` | 102,184 | 8.7% |
| `ln_attn` | 1,605 | 0.14% |
| `ln_ffn` | 1,526 | 0.13% |
| `residual1` | 939 | 0.08% |
| `residual2` | 927 | 0.08% |
| Σ = 668,506 against `layer_stack` 668,675 — a **169 us** residual | | |

Inside `attn_all`:

| phase | us/token | % of token |
|---|---|---|
| `attn_accum` (weighted sum of v) | 61,487 | 5.3% |
| `attn_scores` (q·k loop + running max) | 52,150 | 4.5% |
| `attn_qkv` (the 3 projections) | 14,618 | 1.3% |
| `attn_outproj` | 9,266 | 0.8% |
| `attn_softmax` | 7,064 | 0.6% |
| `attn_qknorm` | 738 | 0.06% |
| `attn_kvappend` | 359 | 0.03% |
| `attn_rope` | 350 | 0.03% |
| Σ = 146,032 against 146,818 — a **786 us** residual | | |

Inside `conv_all`:

| phase | us/token | % of token |
|---|---|---|
| `conv_inproj` | 46,338 | 4.0% |
| `conv_kernel` (dequant + correlation) | 30,595 | 2.6% |
| `conv_outproj` | 21,860 | 1.9% |
| `conv_state` | 3,022 | 0.26% |
| `conv_gate` | 1,444 | 0.12% |
| Σ = 103,259 against 103,351 — a **92 us** residual | | |

Outside the forward: sampling (argmax over 128,000 logits + detok)
**1,868 us/token (0.16%)**.

**Timer cost, stated plainly.** The timer build IS the binary that produced these
tables, with `prof=1 prof_work=1`. Measured against the SAME build with the timer
off, same lens, same session, same conf apart from field 10/11:

| | tok/s | median token |
|---|---|---|
| timer OFF (arm A, 128 tokens) | 0.858 | 1166 ms |
| timer ON (this run, 128 tokens) | 0.855 | 1174 ms |
| timer ON (this run's 128-token repeat) | 0.862 | 1179 ms |

i.e. **inside the run-to-run spread of this box** (the two timer-ON runs differ by
0.8% from each other). The timer does not move the measurement at this mark
density. Calibrated mark cost printed with every table: **135 ns** for a raw
`clock_gettime` syscall against **3,076 ns** for the `clock()` builtin.
### Decode at 1024 tokens

Same run, same conf, second run of the set. `us_tok` normalized on the 1024
reported tokens (1023 forwards), so again 0.1% low. `tok_per_s_x1000=570`,
median token 1757 ms, prefill 620 ms/prompt-token.

| phase | us/token | % of token |
|---|---|---|
| `token_body` | **1,750,254** | 100% |
| &nbsp;&nbsp;`embed_lookup` | 46 | 0.003% |
| &nbsp;&nbsp;`layer_stack` | 1,252,969 | 71.6% |
| &nbsp;&nbsp;`ln_final` | 52 | 0.003% |
| &nbsp;&nbsp;`tied_logits` | 497,181 | **28.4%** |
| Σ = 1,750,248 — a **6 us** residual | | |

Inside `layer_stack`:

| phase | us/token | % of token |
|---|---|---|
| **`attn_all`** (8 layers) | **736,763** | **42.1%** |
| `ffn_up` | 104,143 | 5.9% |
| `ffn_gate` | 103,900 | 5.9% |
| `ffn_down` | 101,622 | 5.8% |
| `conv_all` | 101,654 | 5.8% |
| `silu_glu` | 99,806 | 5.7% |
| `ln_attn` / `ln_ffn` / `residual1` / `residual2` | 1,570 / 1,508 / 919 / 916 | 0.28% total |
| Σ = 1,252,801 against 1,252,969 — a **168 us** residual | | |

Inside `attn_all` — this is where the context dependence lives:

| phase | us/token | % of token |
|---|---|---|
| `attn_accum` | 361,807 | 20.7% |
| `attn_scores` | 307,040 | 17.5% |
| `attn_softmax` | 41,019 | 2.3% |
| `attn_qkv` | 13,865 | 0.8% |
| `attn_outproj` | 10,831 | 0.6% |
| Σ = 735,952 against 736,763 — an **811 us** residual | | |

Pool at 1024: 170,841 calls / 1023 forwards = **167.0 per forward**, the same 166
matvecs + 1 tied projection, and the element counters again reproduce the model's
geometry exactly. `ns_submit` 890.9 ms/token (50.9%), worker busy 9.94 s/token,
**achieved concurrency 11.15 of 20**, `ns_yzero` 7.01 ms (0.40%).

**The context term, measured:** `attn_all` goes from 146,818 us at 128 tokens to
736,763 us at 1024 — **0.659 ms per added context position**, which is the same
slope the earlier work fitted (0.6227 ms/pos), measured here on a differently
loaded box and including the softmax that also grows with position.

### The two tables side by side

| | 128 tokens | 1024 tokens |
|---|---|---|
| token | 1,167,488 us | 1,750,254 us |
| `tied_logits` | 498,694 (42.7%) | 497,181 (**28.4%**) |
| `attn_all` | 146,818 (12.6%) | 736,763 (**42.1%**) |
| FFN 4 phases together | 413,342 (35.4%) | 409,471 (23.4%) |
| `conv_all` | 103,351 (8.8%) | 101,654 (5.8%) |
| `silu_glu` | 101,959 (8.7%) | 99,806 (5.7%) |
| pool concurrency | 11.2 / 20 | 11.15 / 20 |

Every context-independent term is the SAME within ~1% across the two runs (the
tied projection, all four FFN phases, the conv branch, silu) — which is the
strongest available evidence that these are fixed per-token costs and that the
only term that moves is attention. The ranking at 1024 is attention first, the tied
projection second; at 128 it is the tied projection first and attention fourth.
There is no single "the" bottleneck: **there are two, and which one is on top is
the context length.**

## 4. What the table says

Ranked by MEASURED us/token at 128 tokens (the 1024 table below shows the same
ranking with the context-dependent attention term grown):

| # | item | us/token | % of token | what it is |
|---|---|---|---|---|
| 1 | **`tied_logits`** | **498,694** | **42.7%** | the tied output projection, `token_embd.weight` `[2048,128000]` = 262,144,000 elements, pool kind 5, scalar-chain dot |
| 2 | `ffn_up` | 104,639 | 9.0% | 30 fused matvecs, 660M elements |
| 3 | `ffn_gate` | 104,560 | 9.0% | 30 fused matvecs, 660M elements |
| 4 | `conv_all` | 103,351 | 8.8% | 22 short-conv layers, whole branch, 3 matvecs each |
| 5 | `ffn_down` | 102,184 | 8.7% | 30 fused matvecs, 660M elements |
| 6 | **`silu_glu`** | **101,959** | **8.7%** | elementwise `g*sigmoid(g)*uv` — 322,560 elements, MAIN THREAD |
| 7 | `attn_all` | 146,818 | 12.6% | the 8 attention layers, whole branch |

Three things the table settles that the old profile could not:

1. **The tied output projection was the largest single item, at 42.7%** — nearly
   double the whole FFN's largest single matvec and, on its own, larger than
   everything outside the layer stack combined. It is the one matvec the two
   existing fused kernels deliberately did NOT cover, because its reference dot is
   a strict scalar chain. §6 is the attack on it.
2. **The four FFN phases together are 413,342 us (35.4%)** and they are nearly
   equal, so there is no "one FFN site" to single out.
3. **`silu_glu` is 8.7% of a token for 322,560 elements — the same cost as
   `ffn_down`, which moves 660,602,880 elements.** That is 316 ns per element
   against `ffn_down`'s 0.155 ns. It is main-thread scalar Quanta (20 workers idle
   while it runs), and its per-element cost is dominated by an `expf` and a float
   DIVISION — compare `conv_gate`, the same shape of elementwise loop without
   those two ops, at 32 ns/element. **Not attacked in this round** (see §8): it is
   a second, independent 100 ms-class item and it needs its own measurement of what
   `expf` and `fdiv` actually cost before anything is changed.

For scale: the pool moves 2,696,937,472 matvec elements per forward in 901.5 ms of
dispatcher submit time — 2.99e9 elements/s aggregate, against a weight stream of
~1.6 GB/token, i.e. **~1.8 GB/s against llama.cpp's demonstrated ~33 GB/s on this
same model and box**. That is the honest distance to the reference: ~18x on the
matvec path itself, before the elementwise and per-token fixed costs.

## 5. The pool, measured

Same run, `prof_work=1`, so both sides are measured: the dispatcher times its own
publish+wait, and each worker times its own busy period into its own slot.

| figure | measured | per forward | note |
|---|---|---|---|
| parallel calls | 21,209 | **167.0** | 166 `mm_matvec` + 1 tied projection — matches the forward's geometry exactly |
| `mm_matvec` elements | 309,218,770,944 | 2,434,793,472 | **exactly** the model's Q4_K+Q6_K matvec total |
| embed elements | 33,292,288,000 | 262,144,000 | **exactly** `token_embd` `[2048,128000]` |
| `ns_submit` | | **894.4 ms** | 76.6% of the token — "submit" IS the matvec |
| worker busy (`Σ_t busy_t`) | | **10.0 s** | total worker CPU per token |
| achieved concurrency | `1120/100` | **11.2 of 20** | 56% occupancy |
| `ns_yzero` (the `y=0` poison loop) | | 7.15 ms | 0.61% |
| `ns_ensure` | | 62.8 us | 0.005% — the pool is built once and reused |

The element counters are the instrumentation's own integrity check: dividing the
run totals by 127 forwards (not 128 — the bench's last iteration is argmax-only)
reproduces the GGUF geometry **to the element**, which is what makes the rest of
the table trustworthy.

**Achieved concurrency is 11.2 of 20, and that is reported, not tuned.** The pool
partitions rows with a static disjoint slice `[t*chunk, (t+1)*chunk)` for one
reason: the language has **no atomics**, and a work-stealing counter was measured
wrong (931/2048 rows) for exactly that reason. Hand-tuning the slice assignment
would be a workaround that has to be thrown away the moment atomics land, so it was
NOT done. The prerequisite for the next step here is a language capability —
atomic read-modify-write / a proper work queue — and it is named rather than
papered over.

## 6. The lever this picked, and the A/B

The table names one item at 46% of a decode token and nothing else above 10%. That
item is the **tied output projection** — `token_embd.weight`, Q6_K,
`[2048, 128000]` = 262,144,000 elements, the largest single matvec in the model —
reached as pool kind 5 / `pl_run_embed_map`, whose reference dot is a **strict
left-to-right scalar chain**, not `mm_dot4_s`'s four lanes. It was the one 9.72% of
per-token matvec elements still on a scalar dot.

**The reference order was not changed.** `jit_f_build_chain_q6k()`
(`lib/std/jit_x86_fused.quanta`) is the folded Q6_K twin with exactly one change:
the four products of each 4-element group are folded into a scalar accumulator with
**four serial `vaddsd` in element order**, instead of `vaddpd` into four lanes plus
a horizontal reduce. That is literally `acc = acc + row[c]*x[c]` for
`c = 0..ncols-1`. The dequant stays register-resident and factor-free; only the
per-element Quanta builtin call goes away, which is what the scalar path was paying
for. It is the change where "fuse the remaining matvec" and "keep the reference
order" are the same instruction, so it is legitimate algorithm work, not a
workaround around a missing language feature.

Wiring: opt-in, default OFF — `mm_fused_chain` / `mm_set_fused_chain`, checked in
`mm_embed_logits_par` (fail-closed: `jit_f_setup_chain()` runs on the main thread
before any worker sees the flag, and the flag is cleared if the RWX region is
refused), dispatched in `pl_run_embed_map` for dtype 14 with `cols % 256 == 0`, with
`mm_get_fused_chain_used()` as a dispatch witness. Conf field 12.

### A/B, one process per arm, timer OFF in both, same build, same session

`bash tests/lfm2_prof_ab.sh ab`, `LENS="128 256 128"`, conf printed with each arm:

| run | tokens | A `fused_chain=0` med ms | B `fused_chain=1` med ms | A tok/s | B tok/s | **B/A** |
|---|---|---|---|---|---|---|
| 1 | 128 | 1166 | **718** | 0.858 | 1.397 | **1.63x** |
| 2 | 256 | 1255 | **802** | 0.803 | 1.249 | **1.57x** |
| 3 | 128 | 1176 | **720** | 0.858 | 1.393 | **1.63x** |

The saving is **448 ms/token at 128 tokens**, against a profile that put
`tied_logits` at **450 ms/token**. Two independent instruments agreeing to 0.4% is
the cross-check that the attribution was right.

Prefill is unaffected (594 vs 605 ms/prompt-token): only the LAST prompt position
computes logits, so the chain touches 1 of 23 prefill tokens.

**Memory: unchanged.** VmPeak deltas are byte-identical between arms in every run
(555,864 kB for the 128-token runs, 1,116,064 kB for the 256-token run), and RSS
deltas are identical in run 3 (75,200 kB both arms) — the chain kernel materialises
nothing. The inherited ~4.37 MB/token growth is untouched by this change and is not
in the matvec path.

### Correctness, asserted BEFORE any timing

| test | what it proves | result |
|---|---|---|
| `tests/lfm2_fused_logits_test.quanta` (pass5 = q4k+q6k+chain) | all 128,000 logits identical to the shipped path | `logit_mism=0 argmax_mism=0 max_abs_diff_bits=0`, argmax 597, first 24 ids identical, witnesses `used=1/1/1`, rc=0 |
| `tests/lfm2_chain_route_test.quanta` | **all 128,000 rows** of real `token_embd` through `mm_embed_logits`, flag OFF vs ON, compared by raw f64 **bits** | `rows=128000 elems=262144000 mismatch=0 nonzero=128000`, witnesses `used_off=0 used_on=1` |
| same test, independent oracle | 96 rows recomputed by a hand-written left-to-right loop written out in the test | `oracle_mismatch=0` |
| `tests/lfm2_chain_kernel_test.quanta` | the kernel alone, direct call, no pool, 24 real rows | `mismatch=0 nonzero=24` |

## 7. Defects found on the way

1. **`clock()` is 5148 ns/call** because it does `mmap`+`clock_gettime`+`munmap`
   per call (emitter.quanta:3142-3168). Compiler-level; see §1.
2. **`jbytes(n,hex)` silently drops bytes.** `vmovq rax,xmm0` is `c4e1f97ec0` —
   FIVE bytes. Declared as `jbytes(4, ...)` it dropped the ModRM byte, the
   following `ret` (`c3`) was consumed as that instruction's ModRM
   (`vmovq %xmm0,%rbx`), and the kernel ran off the end of its emitted region into
   zero padding: SIGSEGV at `add %al,(%rax)` with `rax=0xbc`, inside the JIT
   region, with every arithmetic result up to that point correct. Found with gdb
   on the JIT region after the isolated kernel test faulted.
   `tests/lfm2_jbytes_len_check.py` now checks all of them mechanically — 159
   `jbytes()` calls in `lib/std/jit_x86*.quanta`, currently 0 mismatches.
3. **Adding a timer changed a TYPE.** Rewriting `return mm_matvec(...)` as
   `let rc = mm_matvec(...) ; return rc` propagates a **float tag** into an
   untyped function's return value, and the 0.0.235 A2 rule then makes
   `print(result)` a compile error. The gate caught it precisely:
   `stdlib_lfm2_conv_test.quanta` failed to COMPILE with
   *"print/println/echo on an f64 would write its raw bit pattern; use print_f(x)"*.
   The marks now compare the call in place (`if <call> != 0 { ...; return -1 }`)
   and bind nothing, so no tag moves. This is the sharpest available evidence for
   why an instrumented build needs the SAME correctness gate as a kernel change —
   instrumentation is not free of semantics in this language.
4. **Emitted bytes must be verified against an assembler, not by eye.** The fold
   block was checked with `as` byte-for-byte. Two hand-derivations were wrong:
   VEX.vvvv is stored **inverted**, and `objdump` renders `vextractf128` with the
   ModRM.reg / r-m roles swapped relative to the SDM text (`as` settled it).

## 8. What was NOT measured

* **1024 tokens with the chain route ON.** The A/B measured the chain at 128 and
  256 tokens; the 1024 table was taken with `fused_chain=0`. The chain's saving is
  a per-token CONSTANT (the same 262,144,000 elements, independent of context), so
  it should compose onto the 1024 baseline unchanged — but that is a projection, and
  no number for it is reported here.
* **512 tokens** in this round (the peer's earlier table has it).
* **`expf` / `fdiv` cost in isolation.** `silu_glu`'s 316 ns/element is a
  measurement; the split between `expf`, the division, and the loop itself is not.
* **Why concurrency is 11.2 and not ~19.** The number is measured; the cause
  (wake latency on small slices, tail imbalance, or the serial `y`-zero before each
  submit) is not. Distinguishing them needs atomics or per-worker slice timing at a
  finer grain than one mark per job.
* **Anything under ~0.01% of a token**: the mark cost at 135 ns puts a floor of
  ~1 us/token on a phase measured with 4 marks, so rows near zero
  (`ln_final`, `embed_lookup`) are indistinguishable from noise.
* **Prefill's own scaling** beyond the per-prompt-token figures printed with each
  run; prefill is not the subject of this table.
