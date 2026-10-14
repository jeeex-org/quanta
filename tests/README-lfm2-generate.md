# tests/lfm2_generate — the tracked native generation driver

`tests/lfm2_generate.quanta` + `tests/run_lfm2_generate.sh`: prefill -> KV-cached
decode -> sample -> print, using `lib/std/lfm2_chat.chat_build` and
`lib/std/sampling.sample_full`, on `QUANTA-LFM2.5-2.6Bv1-Q4_K_M.gguf`.

It lives in `tests/` and not in `test_suites/EXPECTED.tsv` because one token costs
seconds and the model is 1.67 GB: the gate's 15 s / 1536 MB guards cannot hold it (the
same reason `tests/threaded_forward_twice.quanta` is here).

    bash tests/run_lfm2_generate.sh          # compiles then runs, 8 GB cap
    # conf:   tests/lfm2_gen.conf    "<workers> <max_new> <temp_milli> <top_k> [seed]"
    # prompt: tests/lfm2_prompt.txt  (the user turn; read from a FILE, not stdin)

The 5th conf field is optional: it seeds the sampler (`sampling.sample_seed`), so a
run is reproducible from a chosen seed instead of the module's fixed 12345.

## WIRING, the two traps this wires (both real, both cost time to find)

1. **`fc_kv_init(NCTX)` before the first forward.** It is declared in
   `lib/std/lfm2_forward.quanta` and *nothing in lib/std calls it*; with the KV base at
   0 the first forward SIGSEGVs. Wire it, do not assume it.
2. **`mm_pool_begin()` / `mm_pool_end()` around the WHOLE loop**, not the per-forward
   bracket inside `fc_forward_token_ex`: `thread_create()` never unmaps its 1 MB child
   stack, so a 300-token run would leak 300 x nworkers stacks and die mid-run with exit
   status 0 (defect A9).

Two more traps the driver hit and documents in-line, because both are silent:

* `file_open` must receive the top-level `const` **directly**. A helper
  `fn slurp(path)` that forwards an untyped `path` parameter to `file_open` gets a bad
  pointer (defect A7) and returns -1 for a file that plainly exists — measured: the conf
  read failed and the run reported `workers=0` and `FAIL read prompt`.
* `chat_build` needs a real Quanta **string** (`[i64 length][bytes]`); handing it a raw
  `mem_alloc` + `read_raw` buffer makes `len()` read garbage — measured: SIGSEGV (rc=139).
  The driver wraps the file bytes with `as_str()` and keeps the raw bytes for
  `bpe_encode`, which wants an explicit length.

Failure paths `return 1`; the runner reports the program's own rc.

## MEASURED, 0.0.240 (20 cores, load ~9.5 — other units running)

| quantity | value |
|---|---|
| load | 3.5 s |
| prompt | 42 bytes -> `chat_build` 102 bytes -> **34 ids** |
| prefill (20 workers) | `prefill_ms=197852`, **5.82 s/prompt-token** |
| decode, argmax (temp_milli=0) | first token is `<|im_end|>` (EOS) -> `new_tokens=0` |
| decode, sampled (temp 0.7, top_k 40) | first token EOS -> `new_tokens=0` |
| `sample_full` at n_vocab=128000, k=40 | **62 ms** (top-k is 60 ms of it) |
| RSS | 130-180 MB (under the 8 GB cap) |

## The sampler was the first blocker and 0.0.240 fixes it — but it was not the only one

**Fixed and verified in 0.0.240** (`lib/std/sampling.quanta`; reference harness
`tests/sampling_ref.quanta` + `tests/verify_sampling_ref.py`, run with
`bash tests/run_sampling_ref.sh`). Before: `sample_softmax` used `1 + (v - max)` as its
"exp" (measured: it collapsed to a one-hot), `sample_top_k` was an O(n^2) sort that
measured **110,080 ms** at n=128000/k=40, and `sample_draw` compared `cumsum*1000`
against the raw rng value in [0, 2^31), which is never true — so **every draw returned
index 0, and token 0 is `'Ċ'x10`, ten newlines.** That is the whitespace this driver
used to print. After: 13 reference checks pass against numpy + a bit-exact replica of
the LCG and the draw; top-k is 60 ms at n=128000/k=40 (1834x faster).

**Still blocking text, and NOT a sampling defect.** With sampling enabled this driver's
first token is EOS, because the prompt it builds is not the prompt the model's own chat
template specifies:

* `chat_build` writes a **literal backslash-n** where the template renders a real
  newline. `llama.cpp`'s `/apply-template` (its Jinja renderer, same GGUF) returns
  `...<|im_start|>assistant\n thinking` with a REAL newline; `chat_build` returns
  `assistant` + `\` + `n` + ` thinking`. Verified by comparing both byte strings.
* the driver calls `bpe_encode`, which does **no special-token matching**; the
  special-aware entry point `bpe_encode_special` exists in `lib/std/lfm2_bpe.quanta` and
  is called by nobody, so `<|im_start|>`/`<|im_end|>` are encoded as text pieces
  (34 ids) where llama.cpp's `/tokenize` produces single ids (22-23 ids).

Measured consequence, same engine, same 23 prompt ids:

| prompt ids | argmax | first sampled token |
|---|---|---|
| literal backslash-n tail | 124900 = `<|im_end|>` (EOS) | EOS -> `new_tokens=0` |
| llama.cpp-rendered tail (newline + ` thinking`) | **597 = `The`** | real text |

With the correctly rendered prompt and sampling ON (temp 0.25, top_k 40, seed 12345) the
native engine produced **`The answer is: 2`** in 6 tokens at **7.85 s/token**, RSS
142 MB — real words, from `sample_full`, no whitespace. llama.cpp's own argmax for the
same prompt is also 597 = `The`.

**Residual divergence, not investigated here:** the native logits are still flatter than
llama.cpp's on the same ids (`p(The)` 0.251 native vs 0.847 llama.cpp; EOS sits at #2 in
the native top-10). The argmax agrees; the tail does not. That is a logits/forward-pass
question — the tied output projection is **Q6_K**, whose dequant has never been checked
against a reference (0.0.239 verified Q4_K only) — and it is outside the sampling lever.

## Cost

300 tokens is ~40 min at 20 workers from the measured 7.85-8.2 s/token. Prefill is
5.8-7.4 s **per prompt token** because prefill is one unbatched forward per token, so a
2.6k-token retrieved context is hours before the first output token. Both are recorded
as queued levers in `compiler/0.0.240/WIP.md`.
