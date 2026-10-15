# The SI prompt budget, cut to the low hundreds -- measured, not estimated

Status: measured on `0.0.243` (md5 `26430066a4e04f61a687ccf6291b61d7`). Ordered
item 3 of the prefill-batching work. Every token count comes from
`tests/lfm2_compact_budget.quanta`, which encodes with the **same in-tree BPE the
forward pass uses** (`bpe_init_from_gguf` / `bpe_encode`) -- a token count is only a
fact about a prompt if it comes from the encoder the model sees.

Environment, since the wall-clock figures are derived from a measured rate:
governor `powersave`, 20 cores, ambient load 13.68 -> 16.65, top CPU consumer
`Hermes` (Electron) at 742 % CPU. The *token counts* below are load-independent; the
*time* figures are not, and are labelled.

## 1. What was measured, and the cross-check that it is the same prompt

`tests/lfm2_compact_budget.quanta` reads the shipped prompt
(`tests/lfm2_prefill_prompt.txt`) and splits it on the harness's own marker TEXT
(`===== RETR`, `===== TASK`), not on a run of `=`: two weaker scans produced wrong
boundaries in the previous unit's work, which is exactly how a budget goes quietly
wrong.

```
current markers=3495 9138 10173 whole_bytes=10890
current SYSTEM+labels       tokens=1115 bytes=3495
current LANGUAGE_CARD       tokens=1973 bytes=5643
current neighbour           tokens=344  bytes=1035
current spec                tokens=206  bytes=717
current WHOLE PROMPT        tokens=3638 bytes=10890
```

Markers and every section match `docs/research/prefill-batching.md` §5 to the token
(3495 / 9138 / 10173, 1115 / 1973 / 344 / 206, whole 3638). That is the cross-check
that this tool is measuring the same prompt the previous unit did.

## 2. The proposed prompt

One file, `tests/lfm2_compact_card.txt`, replaces **both** static components:

| | current | proposed |
|---|---:|---:|
| SYSTEM card + section labels | 1,115 | 372 (the compact card) |
| LANGUAGE_CARD (a 5.6 KB `docs/SYNTAX.md` dump, retrieved "verbatim") | 1,973 | **0 -- not retrieved at all** |
| duplicate `RETRIEVED CONTEXT 1/3` header | included above | **0** |
| static total | **3,088** | **372** |

The card keeps what the encoder needs and drops what it cannot use: the value model
("every runtime value is a 64-bit integer; an f64 is its bit pattern held in an
i64"), control flow, the operators, arrays, the memory builtins and the **float
accessor** (`f64of(mem_load(p))` / `mem_store(p, v)`, `i2f`/`f2i` -- the idiom that
the doc dump spends ~700 tokens on), output builtins, the negations that trip SI up
(structs, generics, traits, imports, function-valued helpers), the 30-line limit, and
the STRICT fence format. Measured at **372 tokens / 1166 bytes**.

The card is **static**: it is the prefix, and it is the thing that must be cached.
The per-attempt part is the spec and, optionally, retrieval.

## 3. The budget, measured

```
compact card (proposed)     tokens=372 bytes=1166
--- proposed ---
per-attempt = compact+spec  tokens=578 bytes=1883
per-attempt, card PREFIX-CACHED (spec only) tokens=206 bytes=717
with one neighbour retained tokens=922 bytes=2918
shrink vs current whole x100=629
shrink vs current static x100=830
```

| scenario | tokens | vs 3,638 |
|---|---:|---:|
| current assembled prompt | 3,638 | 1.00x |
| compact card + spec | **578** | **6.29x smaller** |
| card PREFIX-CACHED, per attempt (spec only) | **206** | **17.7x smaller** |
| card + spec + one retrieved neighbour | 922 | 3.95x smaller |

**So the budget does reach the low hundreds**: 206 tokens per attempt once the
372-token card is a cached prefix, against 3,638 today. That is the concrete answer
to "cut it to the low hundreds", and it is achieved mostly by *deleting a retrieved
document* rather than by rewriting prose -- the 1,973-token LANGUAGE_CARD is not a
rules card at all, it is a syntax-manual dump that a 2.6B model does not read.

## 4. What it costs at the post-fix prefill rate

The one **measured** rate here is the post-fix serial prefill token, from
`tests/lfm2_op_profile.quanta` (`FULL_TOKEN_NO_LOGITS_POS0`), taken back to back with
its pre-fix twin in `docs/research/q6k-simd-dequant.md`:

| rate | value | measured or derived |
|---|---:|---|
| pre-fix, serial, 1 thread (load 13.68) | 34.63 s/token | **measured** |
| post-fix, serial, 1 thread (load 16.65) | **24.16 s/token** | **measured** |
| post-fix, B=8 batched, serial | 9.40 s/token | derived: 24.16 / 2.57 (the 2.57x B=8 ratio is measured in prefill-batching.md) |
| post-fix, B=8 batched, 20 workers | ~1.07 s/token | **derived from a derived number** -- prefill-batching.md derived 1.539 s/token from a quiet-box 3,955 ms/token, scaled by this A/B's 0.698. Treat as an estimate. |

| scenario | wall clock | basis |
|---|---:|---|
| 3,638 tokens, post-fix, **serial** | **24.4 h** | 3,638 x 24.16 s (measured rate) |
| proposed 578 tokens, post-fix, serial | 3.9 h | derived |
| proposed 206 tokens, post-fix, serial | **83 min** | derived from the measured serial rate |
| 206 tokens, B=8, 20 workers | ~3.7 min | derived again; least trustworthy row |

## 5. The honest bottom line

**Cutting the prompt is necessary and is not sufficient.** At the measured post-fix
serial rate, even 206 tokens is 83 minutes, so a correct prompt budget does not make
the native path usable on one core -- and B=8 batching (2.57x) does not close a 17x
gap either. Two separate things are true and should not be conflated:

1. **The prompt can be 17.7x smaller than it is** (206 vs 3,638) with no loss of the
   information the encoder needs, chiefly by not retrieving a syntax manual. That is
   under this project's control and costs nothing but the decision.
2. **Prefill needs another order of magnitude, and it is not in the prompt.** The
   Q6_K dequant lever took the serial prefill token 34.6 -> 24.2 s; what is left in
   that token is now dominated by the **dot**, which is a scalar left-to-right
   accumulate at ~9-15 ns/element in the tied output projection and `mm_dot4`'s
   2.73 ns/element elsewhere. A fused/wider dot, and the worker pool, is where the
   remaining 10x lives.

## 6. Not verified

- **No prompt was actually RUN against the model.** The counts are exact; whether a
  372-token card is *sufficient* for SI to emit a compiling file is a quality
  question this work does not answer, and it needs a generation experiment.
- The 20-worker / batched wall-clock rows are derived twice over and should be
  re-measured on a quiet box before being used for a decision.
- The neighbour was left in the table as an option (922 tokens with it) but no
  attempt was made to trim it; the previous unit's note that retrieval is already the
  cheap part still holds.
- `tests/lfm2_compact_card.txt` is a proposal. Nothing in the SI loop reads it yet.

## 7. Reproduce

    <qc> tests/lfm2_compact_budget.quanta /tmp/cb.bin
    ( ulimit -c 0 -v 8000000; /tmp/cb.bin </dev/null )     # from the repo root
