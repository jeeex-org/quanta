# tests/lfm2_generate — the tracked native generation driver

`tests/lfm2_generate.quanta` + `tests/run_lfm2_generate.sh`: prefill -> KV-cached
decode -> sample -> print, using `lib/std/lfm2_chat.chat_build` and
`lib/std/sampling.sample_full`, on `QUANTA-LFM2.5-2.6Bv1-Q4_K_M.gguf`.

It lives in `tests/` and not in `test_suites/EXPECTED.tsv` because one token costs
seconds and the model is 1.67 GB: the gate's 15 s / 1536 MB guards cannot hold it (the
same reason `tests/threaded_forward_twice.quanta` is here).

    bash tests/run_lfm2_generate.sh          # compiles then runs, 8 GB cap
    # conf:   tests/lfm2_gen.conf    "<workers> <max_new> <temp_milli> <top_k>"
    # prompt: tests/lfm2_prompt.txt  (the user turn; read from a FILE, not stdin)

## WIRING, the two traps this wires (both real, both cost time to find)

1. **`fc_kv_init(NCTX)` before the first forward.** It is declared in
   `lib/std/lfm2_forward.quanta` and *nothing in lib/std calls it*; with the KV base at
   0 the first forward SIGSEGVs.
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

## MEASURED, this build (0.0.239, 20 cores, load ~10 — a second unit was running)

| quantity | value |
|---|---|
| load | 4.0 s |
| prompt | 42 bytes -> `chat_build` 102 bytes -> **34 ids** |
| prefill (20 workers) | `prefill_ms=195460`, **5.75 s/prompt-token** |
| prefill (8 workers) | `prefill_ms=253042`, **7.44 s/prompt-token** |
| decode, argmax (temp_milli=0) | first token is `<|im_end|>` (EOS) -> `new_tokens=0` |
| decode, sampled (temp_milli=500) | `new_tokens=6`, **6.55 s/token**, rc=0 |
| RSS | ~110-150 MB |

Command behind the decode-argmax row:

    printf '8 8 0 0\n'  > tests/lfm2_gen.conf
    printf 'What is 2+2? Answer with the number only.\n' > tests/lfm2_prompt.txt
    ./compiler/0.0.239/bin/x86/qc tests/lfm2_generate.quanta /tmp/lfm2_gen.bin
    ( ulimit -c 0 -v 8000000; timeout 560 nice -n 19 /tmp/lfm2_gen.bin </dev/null )

## VERDICT: the driver runs, the native path still cannot be used by the SI loop

Stated plainly, because it is the point:

* The driver completes end to end with **rc=0** (load -> template -> tokenize -> prefill ->
  sample -> detokenize -> print), so the plumbing is proven.
* **With argmax it emits EOS as the first token**, so no text is produced for this prompt.
  That is a model/prompt behaviour, recorded as a blocker, not worked around.
* **With sampling it emits 6 tokens of whitespace.** `std/sampling.quanta`'s
  `sample_softmax` uses `1 + (v - max)` as its "exp" — it is not a softmax — and
  `sample_top_k` is an O(n^2) sort that allocates n x 8 bytes per call, so top-k must be
  left at 0 at n_vocab = 128000. The sampler is the weak link once the engine is fast
  enough to reach it.
* **Cost:** 300 tokens is ~50 min at 8 workers and ~40 min at 20 (from measured per-token
  times; not run end to end). Prefill alone is 5.7-7.4 s **per prompt token** because
  prefill is one unbatched forward per token, so a 2.6k-token retrieved context is hours
  before the first output token.

So: the engine got ~1.6x faster (see `compiler/0.0.239/WIP.md` §4), and that is still
~65x short of llama-server's 8.24 tok/s on a larger model, with ~30% of each token now in
an untouched Q6_K output projection. The honest conclusion is the one
`docs/plans/lfm2-native-inference-perf.md` §4 already allows: the native CPU path stays
what it is good at (correctness, verification, a bounded-memory loader), and generation
should run through llama.cpp or the GPU while Quanta owns the loop, the gate and the
proofs.
