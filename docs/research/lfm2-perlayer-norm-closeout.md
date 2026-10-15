# Close-out: the LFM2 per-layer-norm divergence fix

Status: 2026-10-15, v0.0.241, compiler md5 unchanged (`02b155430d10661b17645680b4092987`).
Scope: verification only — no feature, no compiler change. Companion to
`docs/research/lfm2-perlayer-norm-defect.md` (the fixing unit's write-up), whose
section 8 listed "the full gate was not re-run" as unverified. That is now
verified, and this file records it plus an independent source re-read.

## 1. The guard was registered

Row `stdlib_lfm2_attn_perlayer_norm_test.quanta` added to
`test_suites/EXPECTED_STDLIB.tsv` next to the other LFM2 attention rows, source
copied verbatim from `tests/lfm2_attn_perlayer_norm_test.quanta` to
`test_suites/codes/` in the same commit. Convention there is 3 tab-separated
columns (`name<TAB>rc<TAB>prerequisite`); this row uses all three, prerequisite
`/opt/ai/models/quanta/QUANTA-LFM2.5-2.6Bv1-Q4_K_M.gguf` (the norms are real
per-layer weights, so the model is required).

Measured: compile+run rc 0 in **0.57 s** standalone (`qc --no-overflow-trap`, then
`scripts/quanta_run.sh` under the 1024 MB default cap), 1.09 s including build in
the fixing unit's measurement. Its numbers reproduce exactly: L2-vs-L5 k_norm
delta 3.828125; layer-5 K row `|stored - own k_norm| = 0.000000`,
`|stored - layer-2 k_norm| = 7.173737`; live `fc_at_kn`/`fc_at_qn` both 0.000000.

Why it was needed at all: of the rows importing `lib/std/lfm2_forward.quanta`,
**none** called `fc_attention` with a layer other than 2 — the one layer whose
weights the buggy one-time read loaded — so the defect was invisible to every
prior gate run.

## 2. First full gate with the fix + row

`bash test_suites/scripts/run_tests.sh`, exit **0**:

```
=== Results: 228/228 pass, 0 fail (incl. 0 compile-fail) [rows: EXPECTED.tsv] ===
  STDLIB: 111/111 GREEN
functional/native/stdlib/... : GREEN      GATE_EXIT=0
```

Two consecutive runs, both on the same tree (HEAD with the fix):
228/228 native both times; stdlib 111/111 on the second. The FIRST run showed
`FAIL stdlib_rag_search_gate_test.quanta (expected rc=0, got rc=124)` — see 4
below; it is a timing artifact, not the fix.

## 3. Independent source read of `lib/std/lfm2_forward.quanta`

Confirmed from the source, not from the report:

* `fc_attention` reloads when the layer changes — `if fc_at_qn_L != L { read_tensor_f64(qn, fc_at_qn); read_tensor_f64(kn, fc_at_kn); fc_at_qn_L = L }` (lines 608-612).
* `fc_attention_par` carries the identical reload (lines 854-858), so the
  divergence fix is present in **both** functions.
* The only weight DATA read inside the one-time `fc_at_q == 0` block (lines
  561-578 / 839-850) are `qn` / `kn`. Every other buffer allocated there
  (`fc_at_q/k/v/h/sc/out`) is scratch, not a weight.
* No other per-layer weight is loaded once. The projections `q/k/v/o`
  (`lfm2_attn_*(L)` -> `mm_matvec`, per call), the short-conv `in/conv/out`
  (per call), and the layer norms `attn_norm` / `ffn_norm` (read into the shared
  `fc_fw_normbuf` on **every** `fc_layer` call, lines 1100, 1126) are all
  per-layer by construction.

The one per-layer **scalar** read once is `nkv = fc_nkv_of(L)`, used to size the
once-allocated `fc_at_k` / `fc_at_v` / `fc_at_sc`. That is the same class of
assumption ("the first attention layer's value applies to all"), so it was
checked: the GGUF's `lfm2.attention.head_count_kv` is
`[0,0,8,0,0,8,0,0,0,8,0,0,0,8,0,0,0,8,0,0,0,8,0,0,8,0,0,8,0,0]` — **8 at every
attention layer** (2,5,9,13,17,21,24,27) and 0 elsewhere, i.e. `nkv` is constant,
so the once-sized buffers are correct here. It would overflow only for a model
whose attention layers disagree on `head_count_kv`; worth a guard if such a model
is ever targeted.

Not changed by any of this: `fc_attention_par` still has **no runtime exercise** —
nothing sets `fc_attn_workers > 1` (default 0), so its body is dead in every run
here, exactly as the fixing unit's section 8 states. The fix there is confirmed by
reading only.

## 4. The one red row in the first run was a flake, not the fix

`stdlib_rag_search_gate_test.quanta` hit the 15 s wall-clock cap (rc 124) in the
first full-gate run. It is unrelated to the divergence fix and to the new row:
it imports `std/rag` + `std/str` and fork+execs `scripts/rag_search_file.py`
(sqlite-vec KNN over the 21 GB `/opt/tali/ti/ai/rag/vectors.db`), sharing no code
with `lib/std/lfm2_forward.quanta`.

A/B: the same binary run standalone is rc 0 — **9.24 s cold, 3.66-3.79 s warm**
(page cache) — and it PASSED in the second full-gate run on the identical tree.
So the rc=124 was cold-cache/load sensitivity against the 15 s cap, present
before this close-out and not caused by it.

## 5. The generator, post-fix, measured first-hand

`bash tests/run_lfm2_generate.sh`, conf `20 24 700 40 12345 1 0`, 0.0.241:

```
prefill_ms=128290 prefill_ms_per_tok=5577
---generated---
The user asks: "What is 2+2? Answer with the number only." The user wants a specific format
---end---
new_tokens=24
gen_ms=176453  gen_ms_per_token=7352  decode_tok_per_s_x1000=136
DONE            (rc=0)
```

24 tokens, **no EOS** — where the pre-fix run of the same conf stopped at 8
(`The answer is: 2 (init<|im_end|>`). Matches the fixing unit's section 6 AFTER
line. Recorded in `tests/README-lfm2-generate.md`.
