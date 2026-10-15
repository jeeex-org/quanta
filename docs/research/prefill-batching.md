# Batched prefill: where a native LFM2 prompt token actually goes, and what batching buys

Status: measured on `0.0.241` (compiler md5 `02b155430d10661b17645680b4092987`,
unmodified), HEAD `0dfddcf0`. One lever: **batching the prefill**. No compiler
change, so no version bump — the tracked `lib/std/lfm2_*.quanta` files and new
`tests/` drivers are the whole change.

## 0. The environment has to be stated, because it moved

Everything below is a throughput number, so the load was recorded. It was **not
quiet**: a runaway Hermes desktop (Electron) process held **878 % CPU** (measured
instantaneously from `/proc/<pid>/stat`, 8.8 of 20 cores), `chrome` another
121 %, firefox ~60 %, and the `intel_pstate` governor is `powersave` with cores
at **2.2–2.8 GHz of a 5.4 GHz ceiling**. A 20-way busy-loop probe still got
**19.7 effective CPUs**, so parallel capacity was there but each core ran slow.

The consequence, and how it was handled: absolute times measured early in this
session (load 1.5) are **1.69x** smaller than the same work now. That factor was
measured twice, independently:

| calibration | quiet-ish | under the load above | ratio |
|---|---:|---:|---:|
| `tests/lfm2_batch_unit.quanta` T1 serial batched | 327 ms | 554 ms | 1.69x |
| `FULL_TOKEN_NO_LOGITS_POS0` (serial token) | 22.93 s | 38.73 s | 1.69x |

So **every before/after pair below was taken back to back under the same load**,
and the reported ratios are the honest quantity. One earlier number is
reproduced here as evidence that the quoted baseline was load-inflated: the
generator's `prefill_ms_per_tok=5577` (23 tokens, 0.0.241 close-out) vs the
same code at load 1.54 giving **3,955 ms/token** over 64 tokens.

## 1. The per-token budget, measured, and it closes

`tests/lfm2_op_profile.quanta` times every op the forward uses, on the real
tensors, with `mm_workers = 0` (one thread). `calls_per_token` is the call count
of a 30-layer prefill.

| op | ns/call | calls/token | ms/token |
|---|---:|---:|---:|
| `FFN_GATE_MV` [10752x2048] Q4_K | 148,256,658 | 30 | 4,447.7 |
| `FFN_UP_MV` [10752x2048] Q4_K | 148,397,005 | 30 | 4,451.9 |
| `FFN_DOWN_MV` [2048x10752] Q6_K | 591,533,391 | 30 | 17,746.0 |
| `ATTN_Q_MV` [2048x2048] Q4_K | 28,436,910 | 8 | 227.5 |
| `ATTN_K_MV` [512x2048] Q4_K | 7,079,532 | 8 | 56.6 |
| `ATTN_V_MV` [512x2048] Q4_K | 28,023,938 | 8 | 224.2 |
| `ATTN_O_MV` [2048x2048] Q4_K | 28,278,510 | 8 | 226.2 |
| `CONV_IN_MV` [6144x2048] Q4_K | 82,716,336 | 22 | 1,819.8 |
| `CONV_OUT_MV` [2048x2048] Q4_K | 28,196,193 | 22 | 620.3 |
| `SILU_DFF` (d_ff, sigmoid) | 2,245,463 | 30 | 67.4 |
| `RMS_NORM_DM` | 40,422 | 60 | 2.4 |
| `RESIDUAL_DM` | 33,747 | 60 | 2.0 |
| `EMBED_LOOKUP` | 73,646 | 1 | 0.07 |
| **matvec total** | | | **29,820** |
| `FULL_TOKEN_NO_LOGITS_POS0` (measured, same run) | | 1 | **22,929** |

The matvec sum OVERSTATES the token, so the per-op numbers cannot simply be
added: `FFN_DOWN_MV` in isolation re-reads a 12.4 MB tensor that fits in L3 after
the first of its two reps. Splitting each matvec into its two halves -- which is
what batching can and cannot amortise -- is the number that closes:

| term | ns per ELEMENT | elements/token | s/token | share |
|---|---:|---:|---:|---:|
| Q4_K dequant (`mm_load_row` -> `dq32lo`/`dq32hi` path) | 4.09 | 2,122 M | 8.68 | 38% |
| **Q6_K dequant (SCALAR path)** | **25.0** | 313 M | 7.81 | 34% |
| dot (`mm_dot4`) | 2.73 | 2,434 M | 6.64 | 29% |
| everything else (norms, silu, residuals, conv, embed) | — | — | 0.10 | 0.4% |
| **total** | | | **23.23** | **vs 22.93 measured — 1.3%** |

Per-element rates are `FFN_GATE_DEQ` 8,376 ns / 2048 = 4.09, `FFN_DOWN_DEQ`
268,731 / 10752 = 25.0, `FFN_GATE_DOT` 5,588 / 2048 = 2.73.

### Syscalls: one `pread64` per matvec row, and 0.4% of the time

The count is consequence of the row-wise design and it cross-checks exactly. Per
token the forward issues `30 x (10752+10752+2048) + 8 x (2048+512+512+2048) +
22 x (6144+2048)` = **927,744** matvec rows, plus 128,000 output-projection rows
and 1 embedding row = **1,055,745** -- which is the 0.0.239 `strace -f -c`
`pread64` count for one serial forward, to the call. A prefill token skips the
output projection, so it is **927,745** reads. Batching does not change the
per-ROW count; it divides it by B, so at B=8 prefill costs ~116,000 reads per
token instead of 927,745.

The cost is negligible and was measured, not argued: `/usr/bin/time -v` on a
serial run gives **System 0.79 s** against User 198.38 s, i.e. **0.4%**. This is
not a syscall-bound loop and there is nothing to win here.
The 313 M Q6_K elements are the 14 `ffn_down` tensors that ship as Q6_K plus 4
`attn_v`; verified from the GGUF header: 19 Q6_K tensors totalling 574,619,648
elements, of which `token_embd` is 262.1 M (output projection only).

### What this says about the ordered list

- **The score/softmax/accumulate body is NOT a factor.** `ATTN_BODY_POS63` minus
  `ATTN_BODY_POS31` is the whole position-dependence of a prefill token: the two
  calls are 99.8 ms and 95.6 ms, of which 91.8 ms is the q/k/v/o matvecs, so the
  body costs ~0.13 ms per position per attention layer -- ~1 ms per position for
  8 layers. At a 2,600-token context that is ~2.7 s/token against 23 s for the
  matvecs: **12%, not the bottleneck**. Batching it is not the lever.
- **The non-matvec remainder is 0.4%.** There is nothing to win there.
- So the token is 72% dequantisation and 29% dot, and **the dequant is paid once
  per ROW, which is exactly what is redundant across the tokens of a prompt.**

## 2. The lever: one dequant per row, B dots

`mm_matmul(idx, x, rows, cols, B, y)` in `lib/std/lfm2_mm.quanta`: for each weight
row, dequantise ONCE and then do B dot products (`y[b*rows + r]`). The prefill
forward (`fc_prefill_batch_lg`, `fc_layer_batch`, `fc_attn_batch`,
`fc_conv_batch` in `lib/std/lfm2_forward.quanta`) then processes positions
`pos0 .. pos0+B-1` in one pass.

Per-token elementwise cost becomes `dequant/B + dot`:

| B | dequant (s) | dot (s) | s/token-equiv | vs B=1 |
|---:|---:|---:|---:|---:|
| 1 | 16.49 | 6.64 | 23.13 | 1.00x |
| 4 | 4.12 | 6.64 | 10.76 | 2.15x |
| 8 | 2.06 | 6.64 | 8.70 | 2.66x |
| 16 | 1.03 | 6.64 | 7.67 | 3.02x |
| 64 | 0.26 | 6.64 | 6.90 | 3.35x |

The dot is the floor: batching cannot help it, and beyond B~32 the curve is flat.

### Measured, before and after

All serial (`mm_workers = 1`), 4- and 8-token prefixes of the real SI prompt
(`tests/lfm2_prefill_prompt.txt`, 3,648 tokens), back to back:

| conf (workers tokens batch) | ms/prompt-token | ratio | `argmax_last` | maxRSS | load before |
|---|---:|---:|---:|---:|---:|
| `1 4 0`  (one forward per token) | **38,730** | 1.00x | 14066 | 189 MB | 11.6 |
| `1 4 4`  (batched, B=4) | **20,166** | **1.92x** | 14066 | 160 MB | 15.3 |
| `1 8 8`  (batched, B=8) | **15,097** | **2.57x** | 3701 | 162 MB | 14.9 |

`argmax_last` is identical to the unbatched run at the same length, and the
1.92x / 2.57x sit inside the 2.15x / 2.66x the budget predicts (the shortfall is
the per-token work batching does not touch: the embeddings, the norms, the conv
channel loops, and the final position's logits).

On a quiet box the same code measured **3,955 ms/prompt-token** unbatched (20
workers, 64 tokens, load 1.54), so the 20-worker batched figure is expected at
**~1.5-2.0 s/prompt-token**; that pair could not be taken under the load above
and is stated as a prediction, not a measurement.

### Correctness: bit-identical, and proven three ways

The claim is not "close", it is **identical bits**, because the change is only
*when* a row is dequantised: same `read_block_f64` on the same bytes, same
`mm_dot4` (or the same left-to-right scalar loop in the logits path), same
summation order.

1. `tests/lfm2_batch_unit.quanta` -- `mm_matmul` vs the B single-token
   `mm_matvec` calls it replaces, on a Q4_K `ffn_gate`, the Q6_K `ffn_down` and a
   Q4_K square projection, serial AND 4-worker: **0 differing f64 bit patterns**
   over 43,008 + 8,192 + 8,192 values, and 1.63x-4.17x faster per call. Plus
   `mm_embed_logits_batch` vs `mm_embed_logits`: 0/32.
2. `tests/lfm2_batch_layer_unit.quanta` -- ONE whole layer (norm + conv window +
   state + ffn; and norm + q/k/v/o + per-head norms + RoPE + KV append + causal
   softmax + ffn) batched vs the same layer called once per position: **0
   differing bits / 8,192** for L=0 (conv), L=2 and L=5 (attention), serial and
   4-worker, at 2.45x-2.94x.
3. `tests/lfm2_prefill_batched_probe.quanta` + `tests/diff_lfm2_probe.py` -- the
   whole 23-token prompt in ONE batch of 23, dumped in the same byte layout as
   `tests/lfm2_prefill_probe.quanta`, compared region by region:

       TOTAL differing f64 bit patterns: 0        worst |delta| = 0.000e+00
       A consumed 4484126 of 4484126 f64 | B consumed 4484126 of 4484126 f64
       DIFF PASS (bit-identical)

   That covers **logits at all 23 positions** (128,000 values each), the input to
   all 30 layers at the first 8 positions, the final hidden state pre- and
   post-norm, all 22 conv states, and every K/V row of all 8 attention layers at
   every position. The prefill itself was 366,905 ms for 23 tokens (serial,
   `B=23`, load 16.7), i.e. 15,954 ms/prompt-token.

   Because the batched logits are the SAME f64 values, the correlation-to-llama.cpp
   table must be unchanged by construction, and it was checked rather than argued:
   `tests/verify_lfm2_state_ref.py` was run on BOTH dumps against the same cached
   llama.cpp reference and the 23-row tables `diff` clean. The batched table:

       pos | native_argmax llama_argmax | corr        | top10
         0 |         5922         5922 | 0.9997 |  9/10
         1 |          207          207 | 0.9983 |  9/10
         2 |         5922         5922 | 0.9993 |  9/10
         3 |        14066        14066 | 0.9985 | 10/10
         4 |          355          355 | 0.9991 |  9/10
         5 |          278          278 | 0.9992 |  9/10
         6 |           26           26 | 0.9991 | 10/10
         7 |         1510         1510 | 0.9993 |  9/10
       8..22 (all 23 agree)          | 0.9976-0.9996 |  9-10/10

   and the reference-free checks that need no model comparison pass exactly:
   conv-state shift invariant 0.000e+00 at every t; V cache rows vs reference
   5.6e-16; worst conv state vs reference 4.6e-14; K rows 5.3e-15 against a
   reference built with THEIR OWN k_norm while the same rows against LAYER 2's
   k_norm are 1.3e+01 to 2.0e+01 -- i.e. the per-layer-norm fix is present and
   the probe would have caught its absence; final
   `PASS: every carried state matches its independent reference to f64 round-off`.

   STATED PLAINLY: positions 1 and 3 read 0.9983 / 0.9985, a hair below the
   0.9991-0.9997 band quoted in `docs/research/lfm2-perlayer-norm-closeout.md` for
   positions 0-7. This is NOT a regression from batching -- the two dumps are
   bit-identical, so the table is the tree's, not the change's. Either the quoted
   band was approximate or that run's reference differed; re-measuring the
   unbatched path against a freshly built llama.cpp reference is the way to settle
   it, and it is not done here.

The oracle is separate on purpose: `tests/verify_lfm2_state_ref.py` correlates a
dump against **llama.cpp**, so two paths that share a bug cannot pass by agreeing
with each other.

## 3. A compiler defect this work ran into (not fixed here)

`fc_conv_batch` originally expressed the conv gate as

    mem_store(p, f64of(mem_load(a + t*8)) * f64of(mem_load(b + (k+t)*8)))

and every such site **SIGSEGV'd at address 0** (`mov (%rcx),%rax` with
`rcx = 0x0`, gdb). The two `f64of(mem_load(...))` operands are evaluated into one
frame slot and the second operand's address comes out 0. Writing it as the
original `fc_short_conv` does -- one `mem_load` per `let` -- is correct and is
bit-identical, so this is a codegen defect in *expression shape*, not in the
address arithmetic: `fc_pf_skw` and `fc_pf_sbx` were both non-zero when printed
immediately before the faulting statement. Four sites in the new code hit it
(conv gate, conv kernel, conv output, and both residuals).

**Rule: one `f64of(mem_load(...))` per arithmetic expression.** Every pre-existing
matvec/norm/silu line in `lib/std/lfm2_forward.quanta` already obeys it; the new
code did not. Reported here rather than in `docs/plans/bugs.md` (owned by another
unit).

A second, unrelated one found the same way, in the new code: `mm_matmul` and
`mm_embed_logits_batch` computed `rows / mm_workers` **before** testing
`mm_workers <= 1`, so the documented serial setting `mm_workers = 0` was an
integer division by zero -- **SIGFPE at `idiv %rcx` with `rcx = 0`**. `mm_matvec`
and `mm_embed_logits` guard first (`if mm_workers > 1 { ... rows / mm_workers ... }`)
and are correct; the new functions did not copy that. Both now guard before
dividing. Nothing in the benchmark path saw it because the bench's serial runs use
`workers=1`, not `0`.

## 4. What remains after the dequant SIMD work (ordered item 2)

The 0.0.239 SIMD work cut Q4_K dequant to 4.09 ns/element. What it did not touch:

- **Q6_K dequant is still scalar at 25.0 ns/element** -- 6.1x the Q4_K rate, over
  21.3% of the model's weight elements. In a PREFILL token that is 7.81 s of
  23.1 s (34%); batching divides it by B, which is why batching helps so much.
- **The tied output projection has a scalar dot as well.** Measured:
  `FULL_TOKEN_WITH_LOGITS_POS0` 31.85 s - `FULL_TOKEN_NO_LOGITS_POS0` 22.93 s =
  **8.92 s for 262.1 M Q6_K embedding elements**, i.e. 34.0 ns/element, of which
  the dequant is 25.0 ns and the remaining 9.0 ns is the `mm_embed_logits`
  LEFT-TO-RIGHT scalar accumulate against `mm_dot4`'s **2.73 ns**. The output
  projection is 28.0% of a serial decode token, reproducing the 29.8% figure, and
  **73% of it is the Q6_K dequant.**

Two independent, measurable levers, neither attempted here (one lever per
version, and both need a compiler builtin):

| change | saving, serial token | needs |
|---|---:|---|
| `mm_embed_logits` dot -> `mm_dot4` | 262.1 M x 6.3 ns = **1.6 s** (decode only) | nothing, but it CHANGES the logits bits (4-lane vs left-to-right), so the correlation table must be re-measured |
| `dq6lo`/`dq6hi` builtins for Q6_K, as `dq32lo`/`dq32hi` were for Q4_K | 262.1 M x 19 ns = **5.0 s** decode, **5.9 s** prefill | a new compiler builtin + self-host proof -> `0.0.243` |

Q6_K is a 4-bit plane (`ql`) plus a 2-bit plane (`qh`) and a per-16-element `i8`
sub-scale, so the high plane's 2-bit groups do **not** line up with 32-element
`ql` chunks: a `dq6` builtin has to gather `qh` differently from `dq32hi`. That
is the whole reason it is not a copy of the Q4_K one.

## 5. The prompt budget (ordered item 3)

Nothing in the model can make a 3,648-token prompt cheap: at the batched rate the
static preamble is still tens of seconds, and for a 2.6k-token context the
arithmetic is hours unbatched. `tests/lfm2_prompt_budget.quanta` reads the real prompt and counts each section
with the in-tree BPE (the encoder the forward runs), splitting on the harness's
own `===== ...` marker lines. The marker anchors are matched on their TEXT: two
weaker scans (a run of five `=` at a line start) were tried and both returned
wrong boundaries -- one also matched the closing run of the same line, the other
a `=====` ruler line inside LANGUAGE_CARD.txt -- which is how a token budget ends
up quietly wrong. Measured, offsets 3495 / 9138 / 10173, and the four sections sum
to the whole exactly (3,638 as raw text; 3,648 with BOS + special matching):

| component | tokens | share | regenerated per attempt? |
|---|---:|---:|---|
| LANGUAGE_CARD (static) | 1,973 | 54% | no |
| SYSTEM card + section labels (static) | 1,115 | 31% | no |
| retrieved neighbour | 344 | 9% | yes |
| spec | 206 | 6% | yes |
| **whole prompt** | **3,638** | | |

An earlier unit measured the same prompt at 1,947 / ~1,198 / 317 / 176 = 3,638
with the same tokenizer family; the split agrees to a few percent, which is the
cross-check.

**85% of the prompt (3,088 tokens) is static scaffolding that is prefilled
identically on every iteration and for every spec.** The measured cost of the
recommended per-attempt prompt -- system + neighbour + spec, the language card
moved to a cached prefix -- is **1,665 tokens**, a 2.2x shrink before any caching;
with the 3,088-token prefix cached, each attempt costs 550 tokens. The recommendation is therefore, in order:

1. **Prefix-cache the static 3.1k tokens** (or otherwise prefill them once and
   reuse the KV/conv state across attempts). This is the whole win and it is an
   architectural decision, not a model one: it removes 87% of the prompt cost
   whatever the model's speed.
2. **Cut the LANGUAGE_CARD.** 1,947 tokens is over half the prompt and it is
   prose rules; a compact card of the same rules is the second-largest win and
   it is the only component whose size is under this project's control.
3. **Keep retrieval at 2-3 modules (~600-1,000 tokens).** The retrieved block was
   only 9% and the one spec that passed used a neighbour of this size, so
   retrieval is already the cheap part: do not trade retrieval quality for
   tokens before (1) and (2) are done.

### What that costs in wall clock, and the honest bottom line

Measured marginal costs, and every wall-clock figure below is DERIVED from them
(the derivation is stated so it can be checked):

| quantity | value | measured or derived |
|---|---:|---|
| prompt tokens, real SI prompt (`sorting`) | 3,638 | measured |
| static prefix (system + card) | 3,088 | measured |
| recommended per-attempt prompt (system + neighbour + spec) | 1,665 | measured |
| per-attempt prompt with the prefix cached | 550 | measured |
| unbatched, 20 workers, quiet box | 3,955 ms/token | **measured** (load 1.54) |
| batched B=8 vs unbatched, serial | 2.57x | **measured** |
| batched B=8, 20 workers | ~1,539 ms/token | derived (3,955 / 2.57) |

| scenario | wall clock | derived |
|---|---:|---|
| 3,638 tokens, batched B=8, 20 workers | **1.6 h** | 3,638 x 1.539 s |
| recommended 1,665-token prompt | **43 min** | 1,665 x 1.539 s |
| 550-token per-attempt prompt, prefix already cached | **14 min** | 550 x 1.539 s |
| ...plus the 3,088-token prefix, once | 79 min | 3,088 x 1.539 s |

**Batching is worth 2.6x and that is not enough.** A 2.6x on a multi-hour prefill
leaves an hour: SI cannot use the native path on this prompt even batched. Two
consequences, and they are the real answer to the ordered list:

1. **The prompt budget has to be in the LOW HUNDREDS of tokens**, not 1.6-3.6 k.
   At ~1.5 s/prompt-token, 250 tokens is a ~6-minute attempt and 550 tokens is
   ~14 minutes. Since 85% of the current prompt is static, the first move is a
   cached prefix; the second is cutting the 1,973-token LANGUAGE_CARD, which alone
   is 50 minutes of prefill per attempt at these rates.
2. **Prefill needs another order of magnitude, and it is not in the prompt.** By
   the budget in section 1 the remaining levers are the Q6_K dequant (7.81 s of
   23.1 s serial) and the dot (6.64 s); batching already removes the rest of the
   dequant. A `dq6` builtin plus a fused/wider dot is where 3-4x more lives, and
   no amount of prompt shaving substitutes for it.

## 6. Gate rows: none asked for, and why

`test_suites/EXPECTED*.tsv` was NOT touched, and no row is proposed. Every one of
the new checks needs the 1.67 GB GGUF: `mm_matmul` can only be exercised through a
`gguf_tensor_*` descriptor, and the smallest real tensor here is a 4 MB projection.
The gate's ceiling is 15 s / 1536 MB and the model mapping alone is larger than
that, which is exactly why `tests/lfm2_generate.quanta`,
`tests/lfm2_prefill_probe.quanta` and `tests/threaded_forward_twice.quanta` are not
gate rows either. A row would be an un-runnable row.

If the gate ever gains a model-bearing tier, the row to add is

    lfm2_batch_unit.quanta<TAB>0<TAB>/opt/ai/models/quanta/QUANTA-LFM2.5-2.6Bv1-Q4_K_M.gguf

(it prints `UNIT PASS` and exits 0 with 0 mismatches, or `UNIT FAIL` and exits 1).
The STDLIB rows that already import `std/lfm2_forward` and `std/lfm2_mm` do cover
the *compilation* of both changed files, and they pass -- see the gate result below.

## 7. Gate, self-hosting, verify-release

**Decode is untouched, and that is checkable rather than asserted.** The diff to
both library files is **insertions only** -- `git diff --numstat` gives
`546 0` for `lib/std/lfm2_forward.quanta` and `218 0` for `lib/std/lfm2_mm.quanta`,
i.e. no pre-existing line was deleted or modified, so `fc_forward_token_body`,
`fc_layer`, `fc_attention`, `fc_short_conv`, `mm_matvec` and `mm_embed_logits`
are the same code they were. The decode rate is therefore exactly the closed-out
7.35-7.9 s/token and was not re-timed here. The decode lever is section 4: the
tied output projection is 8.92 s of a serial token, 73% of it the scalar Q6_K
dequant -- and `mm_embed_logits`' `pl_run_embed`/`mm_embed_logits_par` paths use a
LEFT-TO-RIGHT scalar accumulate (9.0 ns/element) where the rest of the forward
uses `mm_dot4` (2.73).

**No compiler file was changed**, so there is nothing to re-prove about
self-hosting and no version tree was created: `VERSION` stays **0.0.241**,
`compiler/0.0.241/bin/x86/qc` keeps md5 `02b155430d10661b17645680b4092987`, and
`compiler/0.0.242/` (a committed WIP for a different defect) is untouched. The
change is confined to `lib/std/lfm2_*.quanta` and new `tests/`/`docs/` files,
which is how the per-layer-norm fix and the earlier lib fixes also landed.

Full gate on this tree, compiler `0.0.241`:

    load 15.26 at start, 14.67 at end (the gate's own 20 threads included)
    === Results: 228/228 pass, 0 fail (incl. 0 compile-fail) [rows: EXPECTED.tsv] ===
      STDLIB: 111/111 GREEN
      all 26 stages GREEN, GATE EXIT=0

This matches the stated baseline (228/228 native, 0 compile-fail, STDLIB 111/111,
exit 0) even with the box loaded, so the timing-sensitive rows did not need any
allowance. `scripts/verify-release.sh` is a *version-to-version* check and was not
run: there is no new version for it to compare.

## 8. Reproduce

    bash tests/run_lfm2_prefill_bench.sh                  # conf-driven prefill rate
    printf '1 8 8\n' > tests/lfm2_prefill_bench.conf      # serial, 8 tokens, B=8
    <qc> tests/lfm2_op_profile.quanta       /tmp/op.bin && /tmp/op.bin </dev/null
    <qc> tests/lfm2_batch_unit.quanta       /tmp/bu.bin && /tmp/bu.bin </dev/null
    <qc> tests/lfm2_batch_layer_unit.quanta /tmp/bl.bin && /tmp/bl.bin </dev/null
    <qc> tests/lfm2_prompt_budget.quanta    /tmp/pb.bin && /tmp/pb.bin </dev/null
    bash tests/run_lfm2_prefill_probe.sh          # the reference dump (one per token)
    bash tests/run_lfm2_prefill_batched_probe.sh  # diff vs it + the llama.cpp oracle

## 9. Not verified / stated plainly

- **The 20-worker batched rate (~1,539 ms/prompt-token) is DERIVED**, not measured.
  The box could not deliver it: with the ambient 878%-CPU process present, a
  serial 4-token run took 525 s wall against a `User time` of 520 s and a 20-worker
  run of the SAME 15-second workload hit a 300 s timeout with 198 s of user time
  (1.0 cores of progress). Every measured number here is serial for that reason.
- **The B=23 (one-chunk) point is not on the throughput curve**: the 23-token run
  was the probe, which also computes the output projection at EVERY position. Use
  the B=4 / B=8 bench rows for the scaling claim.
- **Positions 1 and 3 correlate 0.9983 / 0.9985**, a hair below the 0.9991-0.9997
  band quoted for positions 0-7 in the per-layer-norm close-out. Bit-identity
  between the two paths proves this is not from batching, but whether the quoted
  band or that run's reference is the thing that differs was NOT established; it
  needs the unbatched path re-measured against a freshly built llama.cpp reference.
- **`B` beyond 8 is unmeasured.** The budget says the dot floors it at ~3.35x by
  B=64, but only B=4 and B=8 were timed.
- **`fc_attn_workers` / `fc_attention_par` remain dead code**, as before this work
  (the batched path uses `mm_matmul` through the worker pool instead).
- The `tests/lfm2_prefill_prompt.txt` fixture is a copy of
  `stage1/ctx/PROMPT_sorting.txt` (sha256
  `fbf2be64cf0c793ec5083f9c5bb7cb23b99ee17e714d55c29fcadebd48c8f62a`); `stage1/` is
  gitignored, which is why it was copied rather than referenced.

## 10. Reproduce

Record `/proc/loadavg` with every number. Two environment traps found the hard
way, both of which silently produced a 20x-wrong number rather than an error:

1. **`nice -n 19` is NOT usable for a throughput measurement on this box** while
   an ambient nice-0 load exists: the measurement gets starved to ~1 core
   (measured: `User time 198.38 s` in `Elapsed 3:20` for a 20-worker run, i.e.
   1.0 cores of progress, and two runs that normally take 15 s hit a 300 s
   timeout). At nice 0 the same box gives 19.7 effective CPUs.
2. **`ps -o pcpu` is a LIFETIME average**, not the current rate. Establish
   whether the box is busy from two `/proc/<pid>/stat` samples, not from `ps`.
