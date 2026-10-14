# 0.0.240 — WIP · **LEVER: sampling correctness in `lib/std/sampling.quanta`**

One mechanism, one concern: make `sample_full` a real sampler — a stable softmax, a
non-quadratic top-k, and a draw whose rng value shares a domain with the cumsum.
**No compiler source changed**: `compiler/0.0.240/src` is byte-identical to 0.0.239's
(`diff -rq` clean) and so is the golden binary.

Golden: `compiler/0.0.240/bin/x86/qc`, md5 `6f83fe08a7f8819a725fe50c81680ef1` (the same
one 0.0.239 carries — a lib-only change cannot move the compiler's own codegen).

---

## 1. What sampling did before, exactly (read from HEAD, then measured)

Signatures as they were (unchanged by this version, except the documented additions):

```
rng_next()                                   -> i64 in [0, 2^31)
sample_temperature(logits, n, temperature)   -> void, scales in place
sample_top_k(logits, n, k)                   -> void, masks in place
sample_softmax(logits, n)                    -> void, normalises in place
sample_draw(probs, n)                        -> i64 index
sample_full(logits, n, temperature, k)       -> i64 index
```

Three defects, each measured with a synthetic logits vector (10 distinct logits, f64
bits printed — `stage1/sp_before_small`):

1. **`sample_softmax` used `1 + (v - max)` as its "exp"** (`fadd(1, fsub(v, max))`),
   clamped to 0 when the truncating `f2i` went negative. That is not a softmax.
   MEASURED worse than "crude": on the 10-logit vector it produced a **one-hot** — only
   the argmax survived, at 1.0, every other entry exactly 0.0.
2. **`sample_draw` compared `cumsum * 1000` against `rng_next()`.** cumsum is in [0,1],
   so the left side is in [0,1000]; `rng_next()` is in [0, 2^31). The test is never
   true, so the walk always fell through to `return 0`. MEASURED: 10/10 draws returned
   0, and `sample_full` returned 0 for all 10 calls. **Token id 0 is `'Ċ'x10` — ten
   newlines.** This, not the softmax, is the whitespace the driver printed.
3. **`sample_top_k` was an O(n^2) exchange sort that allocated n*8 bytes per call.**
   MEASURED over the real vocab size at k=40 (`stage1/sp_topk_before`): 111 / 448 /
   1850 / 6882 / 27880 / **110,080 ms** at n = 4000 / 8000 / 16000 / 32000 / 64000 /
   128000 — x4 per doubling, i.e. quadratic. 110 s per call is why the driver ran
   `top_k = 0`.

Greedy was unusable for a different reason: the driver called `fc_argmax` and the
model's argmax at its prompt is EOS, so `temperature = 0` generated 0 tokens.

## 2. What changed

`lib/std/sampling.quanta`, rewritten for correctness:

* **softmax**: subtract the max, `expf(v - max)` from `std/math` (itself verified
  against Python's `math.exp` on raw IEEE-754 bits, worst 7.0e-14 relative), normalise.
  The max subtraction is load-bearing and is proved by a 1000-magnitude logits case
  that a naive softmax would overflow.
* **top-k**: k repeated max-scans (each pass finds the largest value strictly below the
  previous pass's value) plus one O(n) threshold pass. O(n*k), no allocation.
* **draw**: `u = fdiv(i2f(rng_next()), i2f(2^31))` in [0,1), compared against the
  running cumsum; returns n-1 if the walk falls through.
* **`sample_full(logits, n, temperature: f64, k)`**: `temperature <= 0` is now GREEDY —
  it returns the argmax instead of dividing by zero into inf logits. The parameter list
  and all call sites are unchanged; the temperature parameter is declared `: f64`
  because an UNTYPED float parameter is silently wrong on this compiler (measured:
  `let t: f64 = x; t * 0.5` with an untyped 3.0 returned 2.3e18, while the same body
  with `x: f64` returned 1.5).
* added `sample_seed(s)` so a run can be pinned to a seed — without it nothing about
  reproducibility is testable.
* every float local is a typed `f64` built with `f64of()`: `mem_load` yields an
  untagged integer, and a float builtin handed an untagged operand takes the integer
  path over the bit pattern.
* **the top-k sentinel is an inline literal, not a `const`**: a top-level `const` with
  a float initialiser evaluates to **0** on this compiler (measured: `const CF = 2.5`
  -> `f64bits(CF) == 0`), which silently made the sentinel 0.0 and left the masked
  tail in the distribution.

### top-k before/after over the real vocab size (k=40, same machine)

| n | before ms | after ms |
|---|---|---|
| 4000 | 111 | 2 |
| 8000 | 448 | 4 |
| 16000 | 1850 | 8 |
| 32000 | 6882 | 17 |
| 64000 | 27880 | 30 |
| **128000** | **110,080** | **60** |

**1834x at n=128000**, and the shape is now linear (2/4/8/17/30/60). The whole
`sample_full` at n=128000, k=40, temp 0.8 measures **62 ms**, so top-k is 60 of those
62 ms and the rest is the temperature pass, the softmax and the draw.

## 3. Reference verification — numpy AND a bit-exact replica

`tests/sampling_ref.quanta` emits f64 **bit patterns** (integers), so the reference
decodes exactly the values the engine saw — no assumption about how a literal rounded.
`tests/verify_sampling_ref.py` checks them with numpy. Run:
`bash tests/run_sampling_ref.sh`. Stated tolerances: **1e-11** on probabilities (abs and
rel), **1e-12** on the sum.

```
PASS  softmax vs numpy  max_abs=8.674e-19 max_rel=1.010e-15 tol=1e-11
PASS  softmax matches naive (numpy)  max_abs(ref,naive)=3.253e-19
PASS  probabilities sum to 1  sum=1.0000000000000007
PASS  argmax  quanta=554 numpy=554
PASS  sample_full(temp=0) == argmax  quanta=554
PASS  top-k kept set == numpy top-k  k=8 kept=[187,554,1108,1662,2216,2770,3324,3878]
PASS  draw sequence == replica  n=200, got == pred for all 200
PASS  same seed -> same samples  A=[434,236,161,1580,2978,4046] B=[same]
PASS  different seed -> different samples  C=[2440,1213,1348,2826,4072,413]
PASS  sample_full(k=16) draws only from top-16
PASS  large-logit softmax vs numpy (max subtracted)  max_abs=1.110e-16 sum=1
PASS  large-logit sum == 1
PASS  all-equal -1000 logits -> uniform 0.25  probs=[0.25,0.25,0.25,0.25]
=== ALL CHECKS PASSED ===
```

The draw check is stronger than a probability comparison: the reference **replicates the
LCG and the cumsum walk** in Python and reproduces the engine's 200 drawn ids exactly,
so the RNG arithmetic, the [0,1) scaling and the walk are all pinned.

**Real model logits too, not only the synthetic vector.** A probe prefilled the chat
prompt and dumped the true 128000-wide logits (`stage1/sp_logits_dump`). Recomputing
softmax -> top-k -> draw in numpy + the replica predicted the id `sample_full` returned
(124900) exactly, and with the seed restored `SAMPLE == SAMPLE2`. On that vector
`p(EOS) = 0.744`, the top-40 kept set carries `0.99999999999999978` of the mass, and the
engine's argmax equals numpy's.

## 4. Reproducibility

`sample_seed(s)` added. Seed 12345 then 12345 again gives the same id sequence
(synthetic: `[434,236,161,1580,2978,4046]` twice; real logits: `SAMPLE 124900 ==
SAMPLE2 124900`), while seed 7 differs. The generator now reads an optional 5th conf
field as the seed, so an end-to-end run is pinned as well.

## 5. End to end — the TRACKED driver now emits real text

The prompt construction was a second, INDEPENDENT blocker. It is fixed in this version
too (the sampler remains the version's declared lever; the prompt port was added on the
reviewer's instruction and is committed separately). Three measured defects:

1. **`chat_build` wrote a literal backslash + `n`** (bytes 92,110) where the template
   renders a real newline. llama.cpp's own Jinja renderer (`/apply-template`, same GGUF)
   returns a real newline (0x0a) in every one of those positions.
2. **`chat_build` wrote the thinking tag as `space + "thinking"`** — one byte wrong
   (0x20 where 0x3c belongs). The tag is the 7 bytes `3c 74 68 69 6e 6b 3e`, i.e. vocab
   token **124901**. It is now written as explicit bytes, so a renderer that strips
   `<...>` (which is how the space got there in the first place) cannot put it back.
3. **the driver called `bpe_encode`, which does NO special-token matching.** The
   special-aware `bpe_encode_special` existed and was called by nobody. The template
   begins with `bos_token`, so the prompt is BOS + the template text.

**The prompt is now verified RIGHT, not merely different.** `chat_build()` +
`bpe_encode_special()` + BOS reproduces llama.cpp's `/tokenize` (`add_special=true`) for
the same prompt **exactly — 23 ids, byte-for-byte**:

```
124894 124899 5922 207 2992 355 229 26 19 26 39 41774 415 278 1579 1049 318 124900 207 124899 63514 207 124901
```

RAW OUTPUT of the tracked driver — `tests/lfm2_generate.quanta`, built with
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

Same binary, conf `20 24 700 40 12345` (sampling ON, the earlier config): first sampled
token is the word `str`, then EOS -> `new_tokens=1`, `gen_ms_per_token=7919`, RSS 165 MB.
So temp 0.7 gives one real word and temp 0.25 a whole sentence; both are REAL TEXT, and
neither is whitespace.

**Cross-binary reproducibility**: the scratch probe `stage1/bin/sp_ids_lowt` (same ids,
same temp, same seed) produced the SAME text — `The answer is: 2`, 6 tokens — so the port
changed no numbers. (Probe and driver are different binaries; both were run.)

**What is STILL true about the logits** (measured, unchanged, outside this lever): the
native distribution is flatter than llama.cpp's on the same ids — `p("The")` 0.251 native
vs 0.847 llama.cpp, only 1 of 10 top ids shared, EOS at #2 in the native top-10 (0.098) —
though the argmax agrees (597 = `The` in both, and that is what the driver generated
from). Prime suspect: the Q6_K tied output projection, whose dequant has never been
checked against a reference.


## 6. Gate, self-hosting, release — all recorded runs are RAW output

Standalone gate, `bash test_suites/scripts/run_tests.sh`, with the tree's own golden
(`QC=compiler/0.0.240/bin/x86/qc`, i.e. `VERSION = 0.0.240`; byte-identical to the 0.0.239
golden at md5 `6f83fe08a7f8819a725fe50c81680ef1`, so the golden choice cannot change this):

```
=== Results: 225/225 pass, 0 fail (incl. 0 compile-fail) [rows: EXPECTED.tsv] ===
  STDLIB: 108/108 GREEN
  ... 24 stages, every one GREEN ...
  stdlib        : GREEN  (lib/std/* via import, EXPECTED_STDLIB.tsv)
exit 0
```

The 24-stage `GATE SUMMARY` lines are all GREEN, including `functional`, `float-oper`,
`stdlib`, `differential` (`-O == no-O`), `qobj`, `fuzz` (0 crashes), `valgrind`
(0 errors), `gguf-corrupt`, `bare-metal`. Exit 0.

GATE HISTORY, kept because it is why the STDLIB row is trustworthy here: putting the real
chat-template bytes into `stdlib_lfm2_chat_test.quanta` first made it RED (STDLIB 107/108,
gate exit 1) — the rewrite had transcribed its long-user-turn length check as
`n1 - (1 + tag_len()) + 2000` (= 2051) where the correct build is `n1 - 2 + 2000` (= 2057),
i.e. the formula was wrong and the code was right. With that corrected the row passes and
the gate is exit 0.

`bash scripts/verify-release.sh 0.0.240 0.0.239` (POST-promotion re-check: root VERSION is
already 0.0.240 = `<NEXT>`, and 0.0.239 is the frozen baseline being re-verified):

```
PASS  <VER> src rebuilds BIT-FOR-BIT (md5 6f83fe08a7f8819a725fe50c81680ef1) -- qualifies as frozen baseline
PASS  <NEXT> src/bin lockstep: committed binary (6f83fe08a7f8819a725fe50c81680ef1) IS the seed-chain fixed point built from 0.0.239 + the committed source
PASS  self-host fixed point: gen0==gen1==gen2==released binary (md5 6f83fe08a7f8819a725fe50c81680ef1)
PASS  official gate ran (log: /tmp/verify_release_gate.log)
PASS  Results: 225/225 pass, 0 fail
PASS  functional stage GREEN
=== 14 passed, 0 failed ===
```

**Self-hosting: 3 generations byte-identical, distinct = 1** — the fixed point
`6f83fe08a7f8819a725fe50c81680ef1` is reached immediately (a lib-only change cannot
move the compiler's own codegen), and `compiler/0.0.240/src` is `diff -rq`-identical to
0.0.239's.

**Version promoted:** yes — `VERSION` moved 0.0.239 -> 0.0.240 with the gate green.


## 7. Not verified / open / queued follow-ups

1. **PREFILL IS THE TOP QUEUED LEVER, and it is a hard blocker for the SI loop
   independent of everything above.** Prefill is one UNBATCHED forward per prompt token:
   measured **5,820 ms/prompt-token** on the 23-token prompt of §5 (133,880 ms total)
   and 5,865 ms on the 34-token prompt. A 2.6k-token retrieved context is therefore
   ~4 hours before the first output token. Until this is amortised (batched prefill,
   and/or prefix KV reuse) the native path cannot serve the SI loop no matter how fast
   decode becomes. Nothing else about the engine matters for the loop until then.
2. **Q6_K dequant has no reference check — the second queued lever.** The tied output
   projection (128000 rows, 128000x2048) is Q6_K, ~30% of a token, and the native logits'
   tail diverges from llama.cpp's while the argmax agrees (§5). Prime suspect for that
   divergence. Explicitly NOT touched here.
3. **Decode is 7.8 s/token at 20 workers** (0.127 tok/s; ~40 min for 300 tokens).
   Measured on the tracked driver: `gen_ms_per_token=7824`, `decode_tok_per_s_x1000=127`.
4. **`lib/std/rag.quanta` has NO gate coverage** — it is not a row in
   `test_suites/EXPECTED_STDLIB.tsv`, so the RAG unit's edits to it are exercised by
   nothing in the gate. Recorded, not fixed (not this lever).
5. **`bpe_encode_special` is still called by nobody else.** `lib/std/tokenizer_trait.quanta`
   still calls `bpe_encode`, so any chat-templated prompt routed through that trait gets
   the same special-token defect the driver had. Recorded, not changed (not this lever).
6. **A top-level `const` with a float initialiser evaluates to 0** (measured:
   `const CF = 2.5` -> `f64bits(CF) == 0`). Found while writing this file, worked
   around, not diagnosed. Any float constant in the tree is silently zero — worth its
   own unit.
7. Measurements were taken at load ~9.5 on 20 cores (other units running); `uptime`
   ~9.5/10.0/10.5. Not re-measured on an idle box.
8. `compiler/0.0.240/lib/**` and `test_suites/**` are the 0.0.239 snapshot copied
   verbatim (the same stale-snapshot situation 0.0.239 recorded); imports resolve to the
   REPO `lib/std`, which is what the build and the gate use.
9. **The residual logits divergence (§5) is NOT explained**, only localised: n_vocab-wide
   logits were compared against llama.cpp's server on identical ids, and only the argmax
   agrees. Not investigated further here.
10. **The tracked driver stops after one token at temperature 0.7 because EOS is INSIDE the
   sampled top-k candidate set.** `sample_full` masks to the top-k and draws from it without
   ever excluding the EOS token (`<|im_end|>`), so at temp 0.7 (top_k 40) the model drew EOS
   on the second step and generation ended (`new_tokens=1`, first token `str`, §5). The temp
   0.25 row is unaffected only because EOS happened to fall outside its sampled set that step
   — it is luck, not policy. Desired: drop EOS from the candidate set unless it IS the argmax
   (or is otherwise forced), and/or impose a minimum generation length. Recorded, not
   implemented (not this lever).
