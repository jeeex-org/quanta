# The native LFM2 forward's per-layer attn_q_norm / attn_k_norm were never reloaded

Status: 2026-10-15, v0.0.241, compiler md5 unchanged (no compiler change was needed).
Defect owner: lib/std/lfm2_forward.quanta. Fixed and verified; 0.0.241 gate
baseline is unaffected except for the new row recommended at the end.

## 1. Symptom (reproduced, then fixed)

The native forward pass's logits agreed with llama.cpp at prefill position 0 and
drifted further with every later position. Same 23-id prompt, identical ids
(`[124894, 124899, 5922, 207, 2992, 355, 229, 26, 19, 26, 39, 41774, 415, 278,
1579, 1049, 318, 124900, 207, 124899, 63514, 207, 124901]`, verified equal to
llama.cpp's `/tokenize`):

| pos | corr BEFORE | corr AFTER | top-10 overlap BEFORE | AFTER |
|----:|---|---|---|---|
| 0 | 0.9997 | 0.9997 | 9/10 | 9/10 |
| 1 | 0.9886 | 0.9983 | 9/10 | 9/10 |
| 2 | 0.9980 | 0.9993 | 9/10 | 9/10 |
| 3 | 0.9538 | 0.9985 | 7/10 | 10/10 |
| 4 | **0.6881** | **0.9991** | 6/10 | 9/10 |
| 5 | 0.7865 | 0.9992 | 5/10 | 9/10 |
| 6 | 0.7361 | 0.9991 | 5/10 | 10/10 |
| 7 | 0.6521 | 0.9993 | 0/10 | 9/10 |
| 8 | 0.7107 | 0.9992 | 7/10 | 10/10 |
| 9 | 0.5522 | 0.9991 | 5/10 | 10/10 |
| 10 | 0.6330 | 0.9991 | 6/10 | 10/10 |
| 22 | 0.6691 | 0.9986 | **1/10** | 9/10 |

The exact instance quoted in `compiler/0.0.241/WIP.md` §3, at position 22:

| quantity | BEFORE | AFTER | llama.cpp |
|---|---|---|---|
| p(597 = "The") | **0.250726** | **0.946577** | 0.910269 |
| top-10 overlap | **1/10** | 9/10 | — |
| logit mean / sd | -4.013 / 2.742 | -4.077 / 2.759 | -3.955 / 2.724 |

Mean and sd were already right, so the defect was a tail/redistribution effect and
not a scale error — which is what made "the bulk distribution is fine" true and
misleading at the same time.

## 2. Root cause

`fc_attention()` and `fc_attention_par()` allocated the q_norm/k_norm buffers AND
read the tensors inside the one-time initialisation block:

```quanta
if fc_at_q == 0 {                 // true only on the FIRST attention layer reached
    fc_at_qn = mem_alloc(hd * 8)
    fc_at_kn = mem_alloc(hd * 8)
    read_tensor_f64(qn, fc_at_qn)  // layer 2's weights
    read_tensor_f64(kn, fc_at_kn)
    ...
}
```

The buffers are per-module, so this is the right place to allocate them — but
`attn_q_norm` and `attn_k_norm` are **per layer** (`blk.L.attn_q_norm.weight`,
64 values each) and every attention layer's pair is different. The first
attention layer reached is layer 2, so layers 5, 9, 13, 17, 21, 24 and 27 all
normalised their q and k with **layer 2's** weights.

The fix (both functions) reloads whenever the layer changes:

```quanta
if fc_at_qn_L != L {
    read_tensor_f64(qn, fc_at_qn)
    read_tensor_f64(kn, fc_at_kn)
    fc_at_qn_L = L
}
```

## 3. The first carried state that diverges, element-wise

The claimed cause was "carried state: the short-conv state and/or the KV cache".
That was half right, and the half it named first is innocent.

Method: `tests/lfm2_prefill_probe.quanta` walks the layer stack once (a faithful
copy of `fc_forward_token_body`'s loop, so it can capture each layer's INPUT) and
dumps, at every prefill position, the logits, every layer's input, the final
hidden state, every conv layer's state, and every K/V cache row.
`tests/verify_lfm2_state_ref.py` then reconstructs each carried state from the
dumped layer input using the **real** ggml row kernels linked from
`libggml-base.so` (`dequantize_row_q4_K`), i.e. an independent reference, and
reports the worst element-wise delta.

BEFORE the fix:

| carried state | vs reference built with ITS OWN norm | vs reference built with LAYER 2's norm |
|---|---|---|
| K cache row, layer 2 | 9.77e-15 | 9.77e-15 |
| K cache row, layer 5 | **1.60e+01** | **4.44e-15** |
| K cache row, layer 9 | **1.62e+01** | 5.77e-15 |
| K cache row, layer 13 | **1.85e+01** | 4.44e-15 |
| K cache row, layer 17 | **1.44e+01** | 4.44e-15 |
| K cache row, layer 21 | **1.96e+01** | 5.11e-15 |
| K cache row, layer 24 | **1.58e+01** | 5.33e-15 |
| K cache row, layer 27 | **1.31e+01** | 4.44e-15 |

**The stored keys were bit-for-bit what layer 2's k_norm produces.** That is the
proof: the divergence is not "large and mysterious", it is exactly the wrong
norm tensor.

First diverging carried state, first in (layer, position) order:

```
K cache row, layer 5, pos 0, element 150:
    native -8.014531878   reference +8.014531878   delta -16.029063756
```

Everything else in the state set was already correct, and stayed correct:

| carried state | BEFORE | AFTER |
|---|---|---|
| short-conv state, worst over all 22 conv layers | 4.62e-14 | 4.62e-14 |
| conv shift invariant `state[t+1][0:dm] == state[t][dm:2dm]`, every t | **0.000e+00** | 0.000e+00 |
| V cache rows, all 8 attention layers | 5.55e-16 | 5.55e-16 |
| K cache rows vs their OWN norm (all 8 layers) | 12.45..19.63 | **<= 1.33e-14** |
| self-check: native logits vs projection of the dumped hidden | 5.33e-14 | 5.33e-14 |

So: **the short-conv state is not the defect** (it is self-consistent to exactly
zero and reconstructs to f64 round-off), **the V cache is not the defect**, and
the K cache was corrupt *as a consequence of* the wrong norm tensor rather than
independently. The first corrupt carried state is a stored K row, but the root
cause is upstream of the cache, in which weights were used to build it.

### Why position 0 looked fine, and why the error grows

At position 0 the softmax is over a single cached position, so its weight is 1
whatever q and k are and the attention output is exactly `v` — **the stored K row
is wrong but unused**. From position 1 on, the wrongly-normed keys are what the
scores are computed against, and every later position adds one more corrupt key to
the cache. Hence "agrees at pos 0, drifts monotonically after" without any
position-dependent code being wrong.

## 4. Why the existing gate row did not catch it

`test_suites/codes/stdlib_lfm2_attn_test.quanta` (row
`stdlib_lfm2_attn_test.quanta`, GREEN in the 228/228 baseline) calls
`fc_attention(2, ...)` **only** — the first attention layer, which is precisely
the layer whose weights the buggy code loaded. Worse, its hand reference reads
`read_tensor_f64(lfm2_attn_q_norm(L), ...)` for that same `L`, so the reference
and the implementation agree whether the reload exists or not. A guard for this
has to call **two** attention layers and check the second against **its own**
norm tensor.

## 5. The guard, and its mutation

`tests/lfm2_attn_perlayer_norm_test.quanta` (fast: build+run **1.09 s**, runs
under a 1536 MB `ulimit -v` and a 15 s timeout, so it fits the gate budget)
does exactly that and adds three checks:

1. the two layers' k_norms differ (otherwise the guard cannot bite) — 3.828125;
2. the K row stored by layer 5 is the one layer 5's own k_norm makes — with the
   fix: `0.000000` against own, `7.173737` against layer 2's;
3. the live module buffers `fc_at_kn` / `fc_at_qn` hold layer 5's weights after
   `fc_attention(5, ...)` — `0.000000` for both (this is the only check that can
   see the q_norm half, since no K-row comparison involves q).

Mutation (fix reverted, guard rebuilt and re-run):

```
K row L5 pos0: |stored - reference(own k_norm)| = 8.484214   |stored - reference L2 k_norm)| = 6.920399
FAIL: the stored K row is not the one layer 5's OWN k_norm produces
live fc_at_kn vs L5 k_norm: max|delta| = 3.828125
FAIL: fc_at_kn still holds another layer's k_norm after fc_attention(L5)
live fc_at_qn vs L5 q_norm: max|delta| = 3.648437
FAIL: fc_at_qn still holds another layer's q_norm after fc_attention(L5)
FAILURES: 3        rc=1
```

With the fix in place it prints `PASS` and exits 0.

## 6. The visible symptom: the tracked generator's answer

`tests/lfm2_generate.quanta`, conf `tests/lfm2_gen.conf`
(`20 24 700 40 12345 1 0`), via `bash tests/run_lfm2_generate.sh`:

```
BEFORE   The answer is: 2 (init<|im_end|>        new_tokens=8  (ended at EOS)
AFTER    The user asks: "What is 2+2? Answer with the number only." The user wants a specific format
                                                 new_tokens=24 (hit max_new, no EOS)
```

Both are real text and both are drawn at temp_milli=700 from the same seed, so
this is a symptom, not a proof: the distribution the sampler draws from is no
longer flattened, so the trajectory changed. The deterministic evidence is §1
(p(597) 0.2507 -> 0.9466 against llama.cpp's 0.9103) and §3 (the state deltas).
The BEFORE run also reproduces the `The answer is: 2` text recorded in
`compiler/0.0.241/WIP.md`, so the defect is reproduced by measurement rather than
quoted.

## 7. Reproducing all of it

```bash
cd /opt/tali/quanta && ulimit -c 0 -v 8000000

# correlation table + element-wise carried-state verification (~4 min with the
# python reference reconstruction; the probe alone is ~3 min)
bash tests/run_lfm2_prefill_probe.sh

# the fast guard (1.1 s) and its mutation
compiler/$(cat VERSION)/bin/x86/qc tests/lfm2_attn_perlayer_norm_test.quanta /tmp/g.bin
./scripts/quanta_run.sh /tmp/g.bin </dev/null ; echo $?      # 0

# the generator
bash tests/run_lfm2_generate.sh
```

## 8. What is NOT verified

* **`fc_attention_par` carries the same fix but was never exercised.** No test,
  and not the tracked driver, ever set `fc_attn_workers > 1` (default 0), so the
  parallel attention body was dead code in every run made here; the fix there was
  a verbatim copy of the `fc_attention` one, type-checked only. `fc_attention_par`
  and `fc_attn_workers` were **REMOVED** in `21a7be4b` (A21): as written the body
  leaked 64 MB of address space per forward token (8 layers x 8 threads x 1 MB,
  the retired per-call `thread_create` pattern), so it could not be enabled
  despite being ~1.35x faster at `pos=1600`. The re-add is queued through the
  persistent pool. See `docs/research/fc-attn-workers-removal.md`.
* Positions 0..7 have carried-state dumps (`NSTATEPOS = 8` in the probe); the
  correlation table covers 0..22. The state claim is therefore about 0..7.
* The reference K row is reconstructed from the **dumped layer input**, so it
  validates the state given the input. The input itself is validated indirectly:
  the logits derived from the dumped final hidden state match the engine's logs
  to 5.3e-14, and the logits match llama.cpp at every position.
* The full gate was **not** re-run (the compiler was not touched). The five gate
  rows that touch `lib/std/lfm2_forward.quanta` were run individually with the fix
  in place and all pass: `stdlib_lfm2_attn_test` (rc 0, cos 0.999999..1.0),
  `gguf_forward_pass_test` (rc 0), `stdlib_lfm2_conv_test` (rc 0),
  `stdlib_lfm2_rope_test` (rc 0), `stdlib_lfm2_mm_test` (rc 0), each well inside
  the 15 s cap.
* The logits' remaining 0.999x-not-1.0 gap is expected f32(compute)+f16(KV) in
  llama.cpp against f64 in the engine, not a further defect. It was not
  investigated further.

## 9. Recommended gate row

`test_suites/EXPECTED_STDLIB.tsv` (the other LFM2 attention rows live there):

```
stdlib_lfm2_attn_perlayer_norm_test.quanta	0	/opt/ai/models/quanta/QUANTA-LFM2.5-2.6Bv1-Q4_K_M.gguf
```

The source is `tests/lfm2_attn_perlayer_norm_test.quanta`; it should be copied to
`test_suites/codes/` when the row is added. Measured cost: rc 0, 1.09 s including
the build, peak address space inside a 1536 MB cap.
