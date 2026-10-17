# Wiring the folded fused Q4_K dequant-dot into the decode route

Status: **WIRED, opt-in and DEFAULT OFF, bit-exact at the logits level, committed
and pushed.** VERSION 0.0.246, `lib/std` + `tests` + this doc only,
`compiler/**` untouched.

Supersedes the closing note of `docs/research/dmd-factor-fold.md` section 6 ("the
fused dot CAN now be wired into gguf_mm ... that wiring is a separate lever and
is the immediate next unit"). That lever is this document.

**Also supersedes two stale claims elsewhere, left in place as historical
records rather than rewritten:** `docs/research/jit-fused-dot-status.md` still
says the integration "is blocked on a compiler fix" and that `jit_f_setup` /
`jit_f_ready` / `jit_f_apply` are "marked BLOCKED in place". Both were true when
written and are FALSE now: the 0.0.246 fix was a front-end predicate (a parameter
named with a reserved keyword token was dropped by funcscan -- NOT a
`closure_call` emitter bug), the three functions carry an UNBLOCKED status
comment in `lib/std/jit_x86_fused.quanta`, and the wiring they were waiting for
is done here.

## 0. The lever, in one line

The folded kernel (bit-identical to `mm_deq_row_raw + mm_dot4_s`, ~12-17x that
pair on the dot) is now routed into the exact function the decode path already
executes for a Q4_K row -- `pl_run_rows_map`, the mmap row-worker -- behind
`mm_set_fused_q4k(1)`, which no caller sets unless it asks. End to end it is a
measured **2.71x / 2.42x / 2.18x** on decode at 128 / 512 / 1024 tokens (OFF
0.273 / 0.257 / 0.237 tok/s -> ON 0.742 / 0.622 / 0.516) with **identical logits**,
at ~184% LESS CPU and with RSS, anon-RSS and the VmPeak leak **unchanged**.

## 1. Which route decode actually takes -- decided FROM THE SOURCE

Not assumed. The chain, read off the files:

```
fc_forward_token_ex -> fc_forward_token_body -> fc_layer
  -> mm_matvec(...)                              (gguf_mm:466; 10 call sites)
       if mm_workers > 1 && rows/mm_workers >= 1
  -> mm_matvec_par(...)                          (gguf_mm:228)
       if mm_map_base != 0 && dtype in {12,14} -> pl_kind = 4
  -> pool worker pl_run   (pl_kind 4)
  -> pl_run_rows_map(t, cell)                    (gguf_mm:1370)
       mm_deq_row_raw(dtype, raw, cols, f64b)    then  mm_dot4_s(...)
```

So the live Q4_K hot path is **`pl_run_rows_map` (pool kind 4)**: rows read
straight from the mapping, dequantised into the worker's own f64 row, dotted.
It is NOT the serial `mm_load_row + mm_dot4` loop (that is the `mm_workers <= 1`
fallback) and NOT the pread block path (`mm_matvec_blk`, kept because it was
measured slower).

The two facts that select this route are both decisions the benchmark makes:
`mm_set_workers_uncapped(20)` (so `mm_workers = 20 > 1`) and
`mm_attach_mmap_fd(...)` (so `mm_map_base != 0` and the tensor is Q4_K/Q6_K).

**Evidence, not inference.** `tests/lfm2_fused_route_probe.quanta` calls
`mm_matvec` with exactly those two settings and witnesses the fused branch with
`mm_get_fused_used() == 1` (a sticky flag set inside the fused branch). With the
flag off the same call reports `used == 0` while producing the same numbers.

## 2. Per-worker argument area -- one per WORKER, allocated once

The kernel takes ONE row per call and reads a 4-qword argument area
`[W, X, DMD, nsuper]` from `rdi` (`jit_x86_fused.quanta`, folded variant).

**Decision: one block per worker, allocated once at pool spawn, reused for every
row.** It lives at `cell + 24` of the existing per-worker scratch cell
(`mm_scratch_new`, which now allocates a 4th word and a 32-byte area).

Why not one per work item: the worker is single-threaded and processes its rows
in sequence, so an area per item buys nothing and costs an allocation per row --
on ~1M rows per decode token, and `mem_alloc` inside a row loop is the documented
anti-pattern in this very file. Why not one SHARED area: `W` changes per row and
`X` is read by every worker, and a shared mutable area across workers is exactly
the cross-worker scratch race that `mm_load_row_s` / `mm_dot4_s` exist to avoid
(and that Quanta cannot fix with atomics -- there are none). Per-worker ownership
is contention-free by construction.

Only `W` actually changes per row, so the per-row cost is 1 store
(`[fargs+0]`); `X`, `nsuper` and the unused `DMD` slot are written once when the
worker picks the fused branch. `DMD = 0` is passed and verified harmless: the
folded kernel derives its factors in-kernel and never reads `[rdi+16]`.

## 3. Call sites: what is wired, and what is deliberately not

**Wired (one branch, `pl_run_rows_map`, dtype 12 rows only):** every Q4_K matvec
in the forward -- FFN gate/up/down, attention q/k/v/out, shortconv in/out. They
all funnel through the same function, so one branch covers all of them.

**Not wired, each for a stated reason:**

| site | dtype | why not |
|---|---|---|
| Q6_K rows inside the same worker (`pl_run_rows_map`) | 14 | no folded twin exists; `mm_deq_row_raw + mm_dot4_s` stays, row by row |
| embedding lookup (`mm_lookup_row`) | Q6_K | `token_embd.weight` is Q6_K |
| tied output projection (`mm_embed_logits`, pool kind 5) | Q6_K | same tensor; the single largest matvec in the token |
| serial fallback (`mm_matvec` when workers <= 1) | any | not the decode route |
| pread block path (`mm_matvec_blk`, kind 0) | any | not the decode route (measured slower) |
| pread embed (`kind 1`), prefill batched (`mm_matmul`, kind 2) | any | separate routes; prefill batching is its own lever |

**Fraction of per-token work covered.** From the model's OWN GGUF header (parsed
directly, 266 tensors):

| dtype | per-token matvec elements | share |
|---|---:|---:|
| Q4_K | 2,122,317,824 | **78.69%** |
| Q6_K | 574,619,648 | 21.30% |
| F32 tails | 259,072 | 0.01% |
| **total** | 2,697,196,544 | |

So this wiring can touch **at most 78.69% of per-token matvec ELEMENTS** (1.4512
GB of the 1.6662 GB file is read per token). The Q6_K remainder -- 19 tensors,
including `token_embd.weight` (262,144,000 elems, the tied projection), 14 Q6_K
`blk.*.ffn_down.weight` and 4 Q6_K `blk.*.attn_v.weight` -- has no folded twin.

Element share is not time share: Q6_K's dequant is cheaper per element and the
embed dot is scalar, so the covered share of TIME is different -- and it is
*measured*, not derived, in section 6.

## 4. The flag

| | |
|---|---|
| name | `mm_fused_q4k`, set through `mm_set_fused_q4k(n)` (`lib/std/gguf_mm.quanta`) |
| default | **0 (OFF)** -- nothing in the tree sets it except the decode bench's conf field 8 |
| scope | the mmap row-workers' dtype-12 rows only (section 3) |
| fail-closed | `mm_matvec_par` emits the kernel once (`jit_f_setup_folded`) before any worker runs and clears the flag if the RWX mapping is refused, so a box without executable anonymous memory keeps the existing path instead of trapping in a worker |

Conf: `tests/lfm2_decode_bench.conf` field 8 is the flag
(`<workers> <len1> <len2> <len3> <use_mmap> <cache_norms> [ignore_eos] [fused_q4k]`),
so ONE binary measures OFF and ON in the same session. The committed conf leaves
it at 0.

## 5. Bit-exactness

Two independent gates, both asserting 0 mismatches BEFORE any timing.

**(a) Through the real route, element-wise, per tensor.**
`tests/lfm2_fused_route_probe.quanta` drives `mm_matvec` (workers 20 + mmap) with
flag OFF and flag ON and diffs every output element:

| Q4_K tensors (fused) | cols | nsuper | rows |
|---|---|---:|---:|
| ffn_gate.0, ffn_up.0 | 2048 | 8 | 10752 each |
| ffn_down.3 | 10752 | 42 | 2048 |
| attn_q.2, attn_output.2 | 2048 | 8 | 2048 each |
| conv_in_proj.0 | 2048 | 8 | 6144 |
| conv_out_proj.0 | 2048 | 8 | 2048 |

plus Q6_K `attn_v.2` (512x2048), `ffn_down.0` (2048x10752) and `token_embd`
(128000x2048), which must be *untouched*.

**Result: 166,400 rows, 0 mismatches, `used_on=1` on every Q4_K tensor and
`used_off=0`.** Both super-block cadences the kernel can see are exercised
(nsuper 8 and nsuper 42).

**(b) At the logits level, all 128,000 values.** `tests/lfm2_fused_logits_test.quanta`
runs the same prompt+decode sequence three times in one process:

```
pass0 fused_q4k=0 (existing)   pass1 fused_q4k=0 (CONTROL)   pass2 fused_q4k=1
CONTROL pass1-vs-pass0 : logit_mism=0 argmax_mism=0
FUSED   pass2-vs-pass0 : logit_mism=0 argmax_mism=0 max_abs_diff_bits=0
fused_used=1   argmax seq (all three): 597 597 4695 20589 34
```

The CONTROL is what makes this mean anything: two serial runs of a stateful pass
differ just as much when state is carried, so the reset is proven clean first.
`max_abs_diff_bits = 0` is exactly +0.0 -- not "close", identical. This upgrades
the claim from "same argmax" to **identical logits**.

**(c) End to end.** First-token argmax **597** and the generation begins
`The user asks: "What is 2+2? ... The answer is 4. ...` in BOTH runs; the first
24 generated ids are byte-identical (section 6). The older `5922` /
`The answer is: 2` oracle in older docs is STALE and was not used.

## 6. End-to-end measurement (ON vs OFF)

`tests/lfm2_decode_bench.quanta` via `tests/run_lfm2_decode_bench.sh`, one binary,
two sessions, same box, worker count 20 uncapped, mmap on, `cache_norms` on,
`ignore_eos` on, temp 0.

Environment, stated with every number: governor **powersave**; `Hermes` holds
**~820% CPU** permanently; load average 10.0-21.0 across both sessions (the bench
itself pushes it up); no peer model process. `clock()`'s absolute unit is
UNVERIFIED -- read the ratios and the within-session comparison, not the absolute
clock.

| tokens | flag | ms/token (whole run) | ms/tok min | med | max | tok/s | OFF/ON ratio |
|---|---:|---:|---:|---:|---:|---:|---:|
| 128 | OFF | 3656.95 | 3 | 3688 | 4165 | 0.273 | |
| 128 | **ON** | **1347.21** | 2 | 1357 | 1514 | **0.742** | **2.71x** |
| 512 | OFF | 3889.19 | 1 | 3884 | 4439 | 0.257 | |
| 512 | **ON** | **1607.18** | 1 | 1612 | 2100 | **0.622** | **2.42x** |
| 1024 | OFF | 4214.85 | 2 | 4198 | 5192 | 0.237 | |
| 1024 | **ON** | **1936.53** | 1 | 1940 | 2813 | **0.516** | **2.18x** |

Prefill (the same branch, unbatched), ms/prompt-token: OFF 3180 / 3165 / 3172 vs
ON 824 / 808 / 824 -- **3.9x**. (`ms/tok min` is 1-3 ms in every run because the
bench's final iteration has no forward, by its own convention; the median is the
representative figure, and OFF and ON share the convention.)

**Token-id identity, end to end**: the first 24 generated ids are byte-identical
between OFF and ON --

```
597 4695 20589 34 496 2992 355 229 26 19 26 39 41774 415 278 1579 1049 2426 440 4695 10966 267 2936 1579
```

-- and the generated text begins identically in both, containing
`The user asks: "What is 2+2? ... The answer is 4. ...`.

**The win is real but it is NOT monotone in length**, and the reason is visible:
the covered Q4_K matvec work is per-position-independent, while the attention
score loop is O(pos) and does not touch this route, so the ratio falls 2.71x ->
2.42x -> 2.18x as the context grows. Inverting the measured ratio against the
kernel's own 12.7-17x on the covered pair gives the covered fraction of a
decode token's TIME: **~69% at 128 tokens, ~64% at 512, ~58% at 1024**
(inferred, not measured; see section 9).

`tok/s` is the bench's own `k * 1e12 / (g1-g0)`; `ms/token` is `(g1-g0)/(k*1e4)`.
Both are whole-run figures over the run's generated tokens.

**CPU%.** The bench emits no CPU field, so the process's CPU utilisation was
measured separately with `/usr/bin/time -v` on a short (8-token) run of the SAME
binary, both flags:

| flag | Percent of CPU | elapsed | MaxRSS kB |
|---|---:|---:|---:|
| OFF | 779% | 4:56 | 1,842,964 |
| ON | **595%** | **1:24** | 1,842,872 |

The fused path uses ~184% LESS CPU while finishing ~3.5x sooner -- it does
strictly less work per token, not merely less wall time (the f64 row is never
written and never re-read). MaxRSS agrees to 100 kB, a fourth independent
confirmation that the route is memory-neutral.

## 7. Memory: the change is neutral, and the leak is untouched

Per-run `smaps_rollup` / `/proc/self/status` deltas, OFF vs ON, at identical token
counts:

| run | flag | RSS delta kB | anon delta kB | VmPeak delta kB | VmPeak delta / token |
|---|---|---:|---:|---:|---:|
| 128 | OFF | 75,200 | 75,200 | 555,864 | 4,342 |
| 128 | ON | 75,200 | 75,200 | 555,864 | 4,342 |
| 512 | OFF | 335,328 | 335,328 | 2,236,464 | 4,368 |
| 512 | ON | 335,328 | 335,328 | 2,236,464 | 4,368 |
| 1024 | OFF | 626,276 | 626,276 | 4,477,264 | 4,372 |
| 1024 | ON | 638,476 | 638,476 | 4,477,264 | 4,372 |

At 128 tokens the deltas are **byte-identical** between OFF and ON, and at 512 and
1024 the per-token VmPeak rate is the same ~4.34-4.37 MB/token on both sides. So:

- the fused route **does not make the leak better or worse** -- it is neutral, as
  expected: it replaces a dequant+dot with a dequant+dot and allocates nothing
  per row (the args area is per worker, once);
- the pre-existing leak is confirmed to be **not** in the matvec row path. It is
  per *token/forward*, not per row, and it is the named A9-class item reaching
  ~13.5 GB of the 32 GB cap at 1024 tokens (ON run3 peaked at 13,537,172 kB). The
  8 GB cap this work's protocol shell sets is BELOW the model + leak trajectory
  and will kill a 512-token run inside `mem_alloc` with no output.

## 8. Gate

`bash test_suites/scripts/run_tests.sh`, run once on the final tree (VERSION
0.0.246), box otherwise idle:

- **GATE_RC=0**: no section RED, all **29** summary sections GREEN.
- native: **231/231 pass, 0 fail** (0 compile-fail).
- stdlib: **113/113 GREEN**.

The two new tests (`tests/lfm2_fused_route_probe.quanta`,
`tests/lfm2_fused_logits_test.quanta`) are deliberately **NOT** manifest rows,
consistent with every other `tests/jit_*` and `tests/lfm2_jit_*` file: they need
the 1.67 GB model and a VA cap above it, and `test_suites/**` is outside this
unit's ownership. They are run by hand; the exact build and run commands are in
each file's header.

## 9. The honest gap, and the next lever

Measured ON decode rates: **0.742 / 0.622 / 0.516 tok/s** at 128 / 512 / 1024,
against OFF **0.273 / 0.257 / 0.237**. The reference is **llama.cpp, this exact
model, this box, CPU, 20 threads: 17.32 tok/s**. So the honest gap is
**23.3x at 128 tokens, 27.8x at 512 and 33.6x at 1024** -- and it WIDENS with
context, because the untouched O(pos) attention work grows while the fused work
does not.

What the wiring bought is real and bounded: the fused kernel is 12.7-17x the pair
it replaces, but that pair is only ~58-69% of a decode token's TIME (inferred:
`F(1 - 1/K) = 1 - 1/R` for the measured ratio R = 2.71/2.42/2.18 and the kernel's
K = 12.7-17 gives F = 0.57-0.69, falling with length). The remaining ~31-42% is
untouchable Q6_K and non-matvec work.

**The next lever is unambiguous and already measured in shape: Q6_K.** It is
21.30% of per-token elements, its `blk.*.ffn_down` and `attn_v` rows go through
the SAME `pl_run_rows_map` worker, and the tied output projection
(`token_embd`, 262,144,000 elements -- the single largest matvec) is Q6_K and
runs on a separate pool kind. A folded Q6_K twin of the same shape would extend
this exact branch to those rows at zero risk to the Q4_K path. That is where the
next unit should start, not in more Q4_K tuning.

The other named wall is untouched: pool scaling saturates well below linear and
the ~800% CPU ceiling stands, so bandwidth/dispatch is the larger remaining term
after Q6_K.

## 10. What could not be measured cleanly

- The OFF 512/1024 rows run for ~2 hours under a load average that the bench
  itself raises to ~17-23 (it is a 20-thread run on a 20-core box shared with a
  process holding ~820% CPU). Absolute ms/token is therefore load-sensitive and
  the ON/OFF ratio is the number to trust; the sessions ran back to back at
  comparable load (OFF start 10.0, end 22.8; ON start 10.4, end 21.2). The two
  OFF-128 figures taken in different sessions (0.278 earlier, 0.273 here) differ
  by ~2%, which is this box's run-to-run spread.
- CPU% was measured on a SHORT 8-token run rather than inside the long runs,
  because the bench has no CPU field. It is a whole-process figure (779% vs
  595%) and, like every number here, is load-sensitive.
- `clock()`'s absolute unit remains UNVERIFIED (a standing caveat in this repo):
  every ratio here is within-session or ON-vs-OFF on the same binary.
- The kernel's own per-row ratio was NOT re-measured here; this doc uses the
  committed `docs/research/dmd-factor-fold.md` figure (A/C 12.83-18.81, A/E
  16.34-18.00 in the quietest runs) as the covered-work speedup, and the
  2.71x/2.42x/2.18x end-to-end as the thing actually measured by this unit.
