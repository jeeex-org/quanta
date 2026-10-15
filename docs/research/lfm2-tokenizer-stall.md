# The LFM2 tokenizer stalled on a 10 KB prompt — an O(id) vocab walk per pre-token boundary

**Status:** FIXED (lib/std, no compiler change) · **A-number:** A20 ·
**Owner file:** `lib/std/lfm2_bpe.quanta` (the defect is entirely in
`bpe_special_match`).

## 0. The complaint, and what it blocks

`tests/lfm2_prefill_bench.quanta` tokenizes the real SI-loop prompt
(`tests/lfm2_prefill_prompt.txt`, 10,890 bytes — a copy of
`stage1/ctx/PROMPT_sorting.txt`) and **never returned**; it printed
`prompt_bytes=10890` and then sat in the tokenizer. A peer reproduced it on both
the HEAD-lib and current binaries, so it is pre-existing. It was already recorded
as an unowned adjacent finding — `docs/research/loader-resource-politeness.md` §6:
"*the realistic-prompt prefill driver … has not returned in 240 s … a real item
for whoever owns the BPE path*". This is that item.

It matters because the SI loop's assembled prompts are thousands of tokens (the
full prompt is **3,638 ids**), the whole point of the compact-prompt work was to
get them down, and a tokenizer that needs ~6 minutes for one 10 KB prompt is a
wall in front of every attempt.

## 1. Reproduced, and located

The tokenizer is isolated in `tests/lfm2_tok_bench.quanta` (new, tokenizer-only —
no forward pass), driven by `tests/lfm2_tok_bench.conf` (whitespace-separated
byte LENGTHS; each is a prefix of `tests/lfm2_tok_bench_input.txt`).

```
cd /opt/tali/quanta
ulimit -c 0 -v 8000000
compiler/0.0.243/bin/x86/qc tests/lfm2_tok_bench.quanta /tmp/lfm2_tok_bench.bin
# or:  bash tests/run_lfm2_tok_bench.sh
```

It times two entry points separately, because they are not the same code path
and only one of them was slow:

* `plain` = `bpe_encode()` — pre-tokenize + BPE, no special-token split.
* `special` = `bpe_encode_special()` — special-token split FIRST, then BPE.
  **This is the path the prefill bench and the generator use** (`chat_build`
  emits `<|im_start|>` / `<|im_end|>`).

`special` is the stall. Where exactly: `bpe_special_match()`, the function that
looks for a CONTROL/USER_DEFINED token at the current position, called **once per
pre-token boundary** by `bpe_encode_special`. It called
`bpe_rec_at(bpe_vocab, id)` to fetch each special's bytes — and `bpe_rec_at`
**walks the packed vocab from index 0**, so it is `O(id)`. The model has **124
specials whose ids sum to 15,494,358**, so *every* boundary paid ~15.5 M
record-steps (each step a `mem_load`, a compare and `at = at + 8 + n`).

```
$ python3 -  # tokenizer.ggml.token_type histogram for QUANTA-LFM2.5-2.6Bv1-Q4_K_M
type histogram Counter({1: 124893, 5: 2983, 3: 122, 4: 2})
special count (CONTROL+USER_DEFINED) 124
sum of ids 15494358
```

## 2. Which of the three it is: (b), a genuinely slow scan — not (a), not (c)

The brief asked whether it is (a) quadratic in a path that should be linear,
(b) a genuinely slow scan, or (c) pathological in one specific input.

**It is (b).** The evidence is that the cost is **linear in input size with an
enormous constant** (~32 ms per input byte), not quadratic: doubling the input
doubles the time (×2.13 and ×1.79 between doublings, not ×4).

Measured BEFORE the fix, single shot, load ~11–12 (governor `powersave`; ambient
`Hermes` 748 % CPU and a second `Hermes` 5.5 % — recorded beside every number):

| bytes | plain (ms) | special (ms) | special µs/byte |
|---|---|---|---|
| 1 024 | 1.481 | **32 619.3** | 31 854.8 |
| 2 048 | 2.824 | **69 468.6** | 33 920.2 |
| 4 096 | 7.367 | **124 134.5** | 30 306.3 |
| 10 890 | 18.942 | **355 305.5** | 32 626.8 |
| 40 960 | 51.575 | **1 332 519.2** | 32 532.2 |

`special` µs/byte is flat across a 40× size range (30 306 → 33 920), so the path
is linear; the constant is the problem. The `plain` path was already fine
(1.4–1.5 µs/byte).

Not (c): the mechanism is content-independent — the cost is `(#boundaries) ×
sum(special ids)`, and `#boundaries` is proportional to the byte length whatever
the text is. The `uniform` arm below (a tiled ASCII sentence, same length,
different content) shows the same shape.

Not (a): there is no quadratic-in-size term to remove here. One *could* call the
per-boundary cost "the same scan repeated", but it repeats **once per boundary**,
so the total is first-order in the input. Nothing about the pre-tokenizer or the
merge loop was quadratic either (the merge loop is written as the naive
lowest-rank-first scan, which is `O(L²)` **per pre-token**, not per prompt, and
pre-tokens are word-sized).

## 3. The fix

`bpe_build_specials()` already had to know each special's length (it sorts by
descending length so longest-match wins). It now **dereferences each special's
token bytes once**, into two arrays built at init:

```quanta
k = 0
while k < bpe_special_n {
    let rec = bpe_rec_at(bpe_vocab, mem_load(bpe_special_ids + k * 8))
    mem_store(bpe_special_len + k * 8, mem_load(rec))
    mem_store(bpe_special_ptr + k * 8, rec + 8)
    k = k + 1
}
```

and `bpe_special_match()` compares against those arrays instead of walking the
vocab. The bytes are stable (`bpe_vocab` is slurped once and never freed), so the
pointer is valid for the process lifetime. The insertion sort now moves the
length and pointer arrays in lockstep with the ids, so it no longer walks the
vocab either (it was `O(cnt² × id)` ≈ 1.7 e9 steps at init — seconds of the load
time). Cost at init: 124 walks once. Cost per boundary afterwards: ≤124 byte
compares, usually 1 byte each.

**Semantics are unchanged by construction:** same special list, same
descending-length order, same first-match-wins → same longest match.

## 4. Growth curve AFTER the fix (min of 7 runs)

`tests/lfm2_tok_bench.conf` = `1024 2048 4096 10890 40960`. Seven repeated runs,
min per case (the box was loaded, load 9.8–11.4; single shots varied up to 2×).
`src=prompt` is the SI-loop prompt text; `src=uniform` is a same-length tiled
ASCII sentence, so the ns/byte column measures **size**, not content.

`src=prompt`:

| bytes | ids | plain ms | special ms | plain ns/B | special ns/B | speedup (special) |
|---|---|---|---|---|---|---|
| 1 024 | 341 | 1.378 | 2.209 | 1 345 | 2 157 | **14 767×** |
| 2 048 | 718 | 2.640 | 4.432 | 1 289 | 2 164 | **15 674×** |
| 4 096 | 1 309 | 4.706 | 7.814 | 1 149 | 1 908 | **15 886×** |
| 10 890 | 3 638 | 12.991 | 25.963 | 1 193 | 2 384 | **13 685×** |
| 40 960 | 13 754 | 55.088 | 88.775 | 1 345 | 2 167 | **15 010×** |

`src=uniform`:

| bytes | ids | plain ms | special ms | plain ns/B | special ns/B |
|---|---|---|---|---|---|
| 1 024 | 227 | 0.732 | 1.342 | 715 | 1 311 |
| 2 048 | 455 | 1.389 | 2.630 | 678 | 1 284 |
| 4 096 | 911 | 2.765 | 5.267 | 675 | 1 286 |
| 10 890 | 2 421 | 8.142 | 16.714 | 748 | 1 535 |
| 40 960 | 9 103 | 29.223 | 61.884 | 713 | 1 511 |

**It is linear now, and I will say so plainly:** special ns/byte is flat within a
1.25× band (1 908–2 384) across a **40×** size range on the real prompt, and flat
within a 1.2× band (1 284–1 535) on the uniform input. `plain` is flat too
(1 149–1 345 ns/B). The full 10,890-byte prompt that used to take 355 s now takes
**26.0 ms**, and 40,960 bytes takes 88.8 ms.

Sum over the five sizes: **1,914.0 s → 0.129 s (14,815×)**.

## 5. Byte-for-byte id equality with llama.cpp (the standard)

A faster tokenizer that emits different ids is worthless, so this is the
acceptance test. Every prefix is written to a file **unchanged** and handed to
upstream's own binary, `/opt/ai/llama.cpp/build/bin/test-tokenizer-0`, against
the real model; the native ids are the `IDS` blocks the bench dumps.

```
$ /opt/ai/llama.cpp/build/bin/test-tokenizer-0 \
      /opt/ai/models/quanta/QUANTA-LFM2.5-2.6Bv1-Q4_K_M.gguf /tmp/tokcmp/pfx_<L>.txt
```

```
MATCH  len=  1024  ids=   341  == llama.cpp (test-tokenizer-0) byte-for-byte
MATCH  len=  2048  ids=   718  == llama.cpp (test-tokenizer-0) byte-for-byte
MATCH  len=  4096  ids=  1309  == llama.cpp (test-tokenizer-0) byte-for-byte
MATCH  len= 10890  ids=  3638  == llama.cpp (test-tokenizer-0) byte-for-byte
MATCH  len= 40960  ids= 13754  == llama.cpp (test-tokenizer-0) byte-for-byte
ALL_MATCH
```

Plus the pre-existing standard, the 26-prompt fixture the gate already owns
(`tests/fixtures/tokenizer_ref.txt`, generated from the same upstream binary):

```
$ compiler/0.0.243/bin/x86/qc test_suites/codes/stdlib_lfm2_bpe_test.quanta /tmp/bpe_gate.bin
$ ( ulimit -c 0 -v 8000000; /tmp/bpe_gate.bin </dev/null )
blocks=26 ids=183 fails=0OK bpe        rc=0
```

So the ids are unchanged on both the 26-prompt fixture **and** the 10,890-byte SI
prompt (of which llama.cpp and the native path agree on all 3,638 ids).

## 6. Files

| path | change |
|---|---|
| `lib/std/lfm2_bpe.quanta` | `bpe_special_len` / `bpe_special_ptr` built once in `bpe_build_specials()`; `bpe_special_match()` no longer walks the vocab; the length sort moves the three arrays together |
| `tests/lfm2_tok_bench.quanta` | new tokenizer-only timing driver (plain vs special, prompt vs uniform, dumps ids) |
| `tests/run_lfm2_tok_bench.sh` | new run wrapper (the sanctioned guards: `ulimit -c 0 -v 8000000`, `timeout`, `nice -n 19`) |
| `tests/lfm2_tok_bench.conf`, `tests/lfm2_tok_bench_input.txt` | the sizes and the input (the prompt tiled to 4× so 40960 is a real prefix) |

## 7. Not verified / residual (stated, not hidden)

* **The prompt-tiling for the 40 KB point.** `tests/lfm2_tok_bench_input.txt` is
  the prompt repeated 4× (43,568 bytes), so the 40,960-byte prefix is 3.76 copies.
  That is fine for a growth curve and for id equality (the same bytes go to both
  tokenizers), but it is not a real 40 KB SI prompt.
* **Absolute times carry the box's load.** Load average 9.8–15.5 throughout,
  governor `powersave` (~half clock), ambient `Hermes` at ~748 % CPU. The
  before/after *ratio* is robust (orders of magnitude apart); the absolute ms are
  not a quiet-box number.
* **A gate row is proposed, not added** (the peer owns `EXPECTED.tsv` /
  `EXPECTED_STDLIB.tsv` this round). What it should be is in A20 in
  `docs/plans/bugs.md`: a row that tokenizes a ≥10 KB prompt with
  `bpe_encode_special` and compares the ids to a llama.cpp fixture, under the
  gate's wall-clock cap. PRE-fix that row cannot pass (it needs ~355 s); POST-fix
  it costs 26 ms.
* The `plain` path's ~1.3 µs/byte is untouched — it was never the problem and
  optimising it is a different lever.
