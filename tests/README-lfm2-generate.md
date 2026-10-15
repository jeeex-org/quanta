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
| decode, sampled temp_milli=700, top_k=40 | first token `str`, then EOS -> `new_tokens=1`, 7,919 ms/token (pre-EOS-policy; the A/B below reruns it) |
| decode, argmax (temp_milli=0) | first token `<|im_end|>` — but see below, that was the mis-prompted build |
| `sample_full` at n_vocab=128000, k=40 | **62-79 ms** (top-k is 60 ms of it) |
| RSS | 165-181 MB (under the 8 GB cap) |

Both sampled rows are REAL TEXT. The temp 0.7 row stops after one word because the
native distribution is flatter than llama.cpp's (see the end of this file) — that is the
OLD behaviour, EOS a live candidate. The A/B section below reruns the same config with the
EOS policy on and gets 8 tokens.

**Which binary produced the text: the tracked driver**, `tests/lfm2_generate.quanta`.
The same text was reproduced by the scratch probe `stage1/bin/sp_ids_lowt` with the same
ids/temp/seed, so the port changed no numbers.

## MEASURED — the EOS policy A/B at temp_milli=700 (same binary, one conf field)

`lib/std/sampling.quanta` now excludes the model's end-of-turn id from the sampled
candidate set UNLESS it is the argmax (`sample_set_eos(id)`, opt-in; conf field 6).
The driver hands it `bpe_eos` (124900, read from the GGUF's
`tokenizer.ggml.eos_token_id`). The pair below is the SAME binary, SAME prompt,
SAME seed, temp_milli=700, top_k=40 — the only difference is conf field 6. Raw
output, 20 cores, load ~9-19:

```
# BEFORE -- conf `20 24 700 40 12345 0 0`   (policy off = 0.0.240 behaviour)
workers=20 max_new=24 temp_milli=700 top_k=40 seed=12345 eos_policy=0 min_len=0
prefill_ms=148042 prefill_ms_per_tok=6436
---generated---
eos_id=124900 eos_excluded_unless_argmax=0 min_len=0
str<|im_end|>
[EOS]
new_tokens=1
sample_ms 96 96
tok_ms 8802 96
gen_ms=8898  gen_ms_per_token=8898   (rc=0, 2m46s wall)

# AFTER -- conf `20 24 700 40 12345 1 0`   (policy on)
workers=20 max_new=24 temp_milli=700 top_k=40 seed=12345 eos_policy=1 min_len=0
prefill_ms=196208 prefill_ms_per_tok=8530
---generated---
eos_id=124900 eos_excluded_unless_argmax=1 min_len=0
The answer is: 2 (init<|im_end|>
[EOS]
new_tokens=8
sample_ms 140 119 117 123 102 115 96 97 171
tok_ms 16119 17063 18843 15433 14623 14442 13999 15111 171
gen_ms=125809  gen_ms_per_token=15726   (rc=0, 5m31s wall)
```

Read the AFTER block carefully: the turn ENDS at token 9 with `[EOS]`, but this
time EOS was **the argmax** (the policy leaves it in place), not a draw that
happened to land on it — 8 tokens of real text where the old path stopped at 1.
`sample_ms`/`tok_ms` are per generated token; `tok_ms` for the FINAL token is the
short one because that iteration ends at the EOS test and runs no forward.
`prefill_ms_per_tok` differs between the two runs only because the box's load
differed (6.4 s vs 8.5 s per prompt token); nothing in this change touches prefill.

The answer text is still `The answer is: 2` (the native model's own arithmetic is
wrong under a flatter logit tail — unchanged by this fix, and the same text the
0.0.240 temp 0.25 row produced). What changed is that the model is no longer CUT
OFF by sampling noise; whether it ends a turn is now its argmax's decision.

**Method check:** with the policy off the very same draw chose EOS after one token
(so the defect is reproduced by measurement, not quoted from an earlier run), and
`tests/sampling_eos_selfcheck.quanta` pins it numpy-free: policy off -> EOS is in
the kept top-4 and IS drawn; policy on -> excluded, kept count still k, never
drawn in 300 samples.

## What 0.0.240 fixed, and how it is verified

**1. The sampler** (`lib/std/sampling.quanta`; reference harness
`tests/sampling_ref.quanta` + `tests/verify_sampling_ref.py`, run with
`bash tests/run_sampling_ref.sh`). Before: `sample_softmax` used `1 + (v - max)` as its
"exp" (measured: it collapsed to a one-hot), `sample_top_k` was an O(n^2) sort measuring
**110,080 ms** at n=128000/k=40, and `sample_draw` compared `cumsum*1000` against the raw
rng value in [0, 2^31), which is never true — so **every draw returned index 0, and token
0 is `'Ċ'x10`, ten newlines.** That is the whitespace this driver used to print. After:
33 reference checks pass against numpy (tol 1e-11) — 13 from 0.0.240 plus 20 for
the EOS policy — plus a bit-exact Python replica of the LCG and the draw (200/200
ids, and 200/200 again on the EOS-masked vector); top-k is 60 ms at n=128000/k=40 (1834x).

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

**4. The EOS policy — queued for the next promotion** (`lib/std/sampling.quanta` +
this driver + `tests/sampling_ref.quanta`/`verify_sampling_ref.py` +
`tests/sampling_eos_selfcheck.quanta`). The sampler put the end-of-turn id inside
the sampled candidate set, so a draw could truncate an answer: at
temp_milli=700/top_k=40 the tracked driver stopped after ONE token (the A/B
above). Policy now: exclude `sampling_eos` unless it is the argmax; optional
`sample_set_min_len(n)` floor. Both OFF by default, so no existing caller's
behaviour moved. Signatures unchanged (`sample_full` is still 4 args); a caller
opts in with `sample_set_eos(bpe_eos)`. Also see `tests/sampling_eos_selfcheck.quanta`
— the numpy-free, model-free property check written to be registrable as a gate
row, since `lib/std/sampling.quanta` was ungated until `5ed79597` added `sampling_eos_test.quanta` to `EXPECTED.tsv` (now 228 native rows); it was ungated when this was written.

## Cost — and the blocker that outranks all of the above

Prefill is one UNBATCHED forward per prompt token: **5,820 ms/prompt-token** measured
here (23 tokens = 134 s) and 5,865 ms on a 34-token prompt. A 2.6k-token retrieved
context is therefore ~4 hours before the first output token. Decode is 7.8 s/token at 20
workers. Recorded as the top queued lever in `compiler/0.0.240/WIP.md` §7, alongside the
Q6_K output projection.
