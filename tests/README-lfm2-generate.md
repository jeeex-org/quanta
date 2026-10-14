# tests/lfm2_generate — the tracked native generation driver

`tests/lfm2_generate.quanta` + `tests/run_lfm2_generate.sh`: prefill -> KV-cached
decode -> sample -> print, using `lib/std/lfm2_chat.chat_build`,
`lib/std/lfm2_bpe.bpe_encode_special` and `lib/std/sampling.sample_full`, on
`QUANTA-LFM2.5-2.6Bv1-Q4_K_M.gguf`.

It lives in `tests/` and not in `test_suites/EXPECTED.tsv` because one token costs
seconds and the model is 1.67 GB: the gate's 15 s / 1536 MB guards cannot hold it (the
same reason `tests/threaded_forward_twice.quanta` is here).

    bash tests/run_lfm2_generate.sh          # compiles then runs, 8 GB cap
    # conf:   tests/lfm2_gen.conf    "<workers> <max_new> <temp_milli> <top_k> [seed]"
    # prompt: tests/lfm2_prompt.txt  (the user turn; read from a FILE, not stdin)

The 5th conf field is optional: it seeds the sampler (`sampling.sample_seed`), so a run
is reproducible from a chosen seed instead of the module's fixed 12345.

## WIRING — four traps, all measured, all cost time

1. **`fc_kv_init(NCTX)` before the first forward.** It is declared in
   `lib/std/lfm2_forward.quanta` and *nothing in lib/std calls it*; with the KV base at
   0 the first forward SIGSEGVs. Wire it, do not assume it.
2. **`mm_pool_begin()` / `mm_pool_end()` around the WHOLE loop**, not the per-forward
   bracket inside `fc_forward_token_ex`: `thread_create()` never unmaps its 1 MB child
   stack, so a 300-token run would leak 300 x nworkers stacks and die mid-run with exit
   status 0 (defect A9).
3. **The prompt is BOS + a chat-templated string whose pieces are SPECIAL tokens.**
   `bpe_encode()` does no special-token matching, so `<|im_start|>`, `<|im_end|>` and the
   thinking tag were encoded as ordinary text pieces (34 ids) and the model was fed a
   prompt it was never trained on — first-token argmax EOS, nothing generated. The driver
   now prepends `bpe_bos` and calls `bpe_encode_special` (23 ids). Verified: this equals
   llama.cpp's `/tokenize` for the same prompt byte-for-byte.
4. Two silent ones in the driver's own helpers: `file_open` must receive the top-level
   `const` **directly** (a helper forwarding an untyped `path` parameter gets a bad
   pointer — defect A7 — and returns -1 for a file that plainly exists), and `chat_build`
   needs a real Quanta **string** (`[i64 length][bytes]`; a raw `mem_alloc` + `read_raw`
   buffer makes `len()` read garbage -> SIGSEGV rc=139). Hence `as_str()`.

Failure paths `return 1`; the runner reports the program's own rc.

## MEASURED, 0.0.240 (20 cores, load ~9.5 — other units running)

The driver GENERATES REAL TEXT. Raw output, `tests/lfm2_generate.quanta` built with
`compiler/0.0.240/bin/x86/qc`, conf `20 24 250 40 12345`:

```
workers=20 max_new=24 temp_milli=250 top_k=40 seed=12345
prompt_bytes=99
prompt_ids=23 (bos=124894)
prefill_ms=133880 prefill_ms_per_tok=5820
---generated---
The answer is: 2<|im_end|>
[EOS]
new_tokens=6
gen_ms=46945  gen_ms_per_token=7824  decode_tok_per_s_x1000=127
DONE            (rc=0, RSS 181612 kB = 177 MB)
```

| quantity | value |
|---|---|
| load | ~4.0 s |
| prompt | 42 bytes -> `chat_build` **99 bytes** -> **23 ids** (= llama.cpp's id list) |
| prefill (20 workers) | `prefill_ms=133880`, **5,820 ms/prompt-token** |
| decode, sampled temp_milli=250, top_k=40 | `The answer is: 2` in **6 tokens**, **7,824 ms/token** |
| decode, sampled temp_milli=700, top_k=40 | first token `str`, then EOS -> `new_tokens=1`, 7,919 ms/token |
| decode, argmax (temp_milli=0) | first token `<|im_end|>` — but see below, that was the mis-prompted build |
| `sample_full` at n_vocab=128000, k=40 | **62-79 ms** (top-k is 60 ms of it) |
| RSS | 165-181 MB (under the 8 GB cap) |

Both sampled rows are REAL TEXT. The temp 0.7 row stops after one word because the
native distribution is flatter than llama.cpp's (see the end of this file).

**Which binary produced the text: the tracked driver**, `tests/lfm2_generate.quanta`.
The same text was reproduced by the scratch probe `stage1/bin/sp_ids_lowt` with the same
ids/temp/seed, so the port changed no numbers.

## What 0.0.240 fixed, and how it is verified

**1. The sampler** (`lib/std/sampling.quanta`; reference harness
`tests/sampling_ref.quanta` + `tests/verify_sampling_ref.py`, run with
`bash tests/run_sampling_ref.sh`). Before: `sample_softmax` used `1 + (v - max)` as its
"exp" (measured: it collapsed to a one-hot), `sample_top_k` was an O(n^2) sort measuring
**110,080 ms** at n=128000/k=40, and `sample_draw` compared `cumsum*1000` against the raw
rng value in [0, 2^31), which is never true — so **every draw returned index 0, and token
0 is `'Ċ'x10`, ten newlines.** That is the whitespace this driver used to print. After:
13 reference checks pass against numpy (tol 1e-11) plus a bit-exact Python replica of the
LCG and the draw (200/200 ids); top-k is 60 ms at n=128000/k=40 (1834x).

**2. The prompt construction** (`lib/std/lfm2_chat.quanta` + this driver), three measured
defects: `chat_build` wrote a literal backslash-n where the template renders a real
newline; it wrote the thinking tag as `space + "thinking"` when the tag is the 7 bytes
`3c 74 68 69 6e 6b 3e` (vocab id 124901); and the driver called `bpe_encode`, which does
no special-token matching, on a prompt whose template starts with `bos_token`. Verified
against llama.cpp's own renderer and tokenizer (`/apply-template`, `/tokenize`, same
GGUF): `chat_build()` + `bpe_encode_special()` + BOS now reproduces llama.cpp's id list
**exactly, 23 ids byte-for-byte**, and llama.cpp's argmax for that prompt (`The`) matches
the engine's argmax.

**3. Still true about the logits** (measured, left alone): the native distribution is
flatter than llama.cpp's on identical ids — only 1 of 10 top ids shared, `p("The")` 0.251
native vs 0.847 llama.cpp, EOS at #2 in the native top-10 — the argmax agrees, the tail
does not. The tied output projection is Q6_K and no Q6_K dequant has ever been checked
against a reference.

## Cost — and the blocker that outranks all of the above

Prefill is one UNBATCHED forward per prompt token: **5,820 ms/prompt-token** measured
here (23 tokens = 134 s) and 5,865 ms on a 34-token prompt. A 2.6k-token retrieved
context is therefore ~4 hours before the first output token. Decode is 7.8 s/token at 20
workers. Recorded as the top queued lever in `compiler/0.0.240/WIP.md` §7, alongside the
Q6_K output projection.
