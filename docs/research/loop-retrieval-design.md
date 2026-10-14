# The SI loop's retrieval (the "R"): what it is, what it costs, what to do

Status: investigation + small-scale proof, 2026-10-14. Read-only over the 21 GB
store. Companion artifacts: `stage1/retrieval/{compare_retrieval.py,REPORT.md,
results.json}`.

This answers four questions the self-improvement loop needs settled before the
"R" in RAG can be called real:

1. Does the 21 GB vector store already contain embeddings?
2. Can retrieval be made semantic, and what is missing?
3. Is semantic retrieval actually *better* here? (measured, with losses shown)
4. What should the loop retrieve, and what does the assembled prompt cost?

Short version: **the store already holds embeddings and the KNN index already
answers queries — the only missing piece was the query encoder, which exists at
`/usr/bin/python3`. Semantic retrieval is a WIRING job, not a 2.8M-chunk
re-embedding project.** But on *this* corpus semantic retrieval does **not**
beat keyword retrieval for finding the right module, because the corpus is 92%
clone noise and the real modules are machine-named stubs. The right design is
hybrid, and the argument for that is below.

---

## 1. The store already contains embeddings (read-only audit)

`config/rag.conf` `[rag] db = /opt/tali/ti/ai/rag/vectors.db`, 21,010,685,952
bytes. Schema (`sqlite3_master`, via python sqlite3):

```
chunks      (id TEXT PRIMARY KEY, source TEXT NOT NULL, type TEXT NOT NULL,
             chunk_index INTEGER, content TEXT, embedding BLOB)
vec0        CREATE VIRTUAL TABLE vec0 USING vec0(embedding float[384])
vec_chunks  CREATE VIRTUAL TABLE vec_chunks USING vec0(id TEXT PRIMARY KEY,
             embedding FLOAT[384])
```

Row counts and vector content:

| query | result |
|---|---|
| `SELECT count(*) FROM chunks` | 2,862,440 |
| `... WHERE embedding IS NOT NULL` | 2,862,440 |
| `... WHERE embedding IS NULL` | 0 |
| `min/max/avg(length(embedding))` | 1536 / 1536 / 1536.0 |
| `SELECT count(*) FROM vec0_rowids` | 2,862,440 |
| `SELECT count(*) FROM vec_chunks_rowids` | 2,862,440 |
| `SELECT type, count(*) ... GROUP BY type` | md 2,643,064 / quanta 219,376 |
| `vec0_info` | CREATE_VERSION = v0.1.9 |

1536 bytes = 384 float32 = the dim `config/rag.conf` records, and a decoded blob
has L2 norm 1.0 (all-MiniLM output is normalised).

**Proof the index is live, not a dead schema** — three independent checks:

- KNN with a chunk's OWN stored vector as the query returns that chunk at
  distance `0.0`.
- `cos(all-MiniLM(content), stored_embedding) = 1.0` for the same chunk, i.e.
  the stored vectors ARE all-MiniLM-L6-v2 output; a query encoded with that
  model is in the same space.
- Re-encoding that chunk's text and running KNN self-retrieves it at rank 0.

So the store answers KNN. **What was missing was only the query-time encoder**:
`config/rag.conf` had `[embed] python =` (empty), so `rag_embed()` in
`lib/std/rag.quanta` returned `[error: embed.python / embed.script not set]`.
Nothing needed re-embedding.

### The encoder — exact reproducibility facts

| | |
|---|---|
| interpreter | `/usr/bin/python3` — Python 3.12.14 (NOT the 3.14 `python3` on PATH, which is what `config/rag.conf`'s stale comment had tested) |
| model | `all-MiniLM-L6-v2`, 384-dim, sentence-transformers name resolved through the HF cache |
| weights | `~/.cache/huggingface/hub/models--sentence-transformers--all-MiniLM-L6-v2/snapshots/1110a243fdf4706b3f48f1d95db1a4f5529b4d41/model.safetensors` — **90,868,376 B (~87 MiB)**, cache dir 88 MB |
| packages | sentence-transformers 5.6.0, torch 2.10.0+cu128, transformers 5.5.0, numpy 2.5.1, huggingface-hub 1.23.0, tokenizers 0.22.2, **sqlite-vec 0.1.9** (loads the `vec0` ext) — all in `~/.local/lib/python3.12/site-packages` |
| installed by this unit | **nothing.** Packages dated 2026-07-14; weights 2026-07-17. All pre-existed; only the config value was missing. |
| cold model load | ~7 s (103 tensors) |
| per-query encode | **~16 ms warm** (min 3 ms / mean 16 ms / max 62 ms); first encode 0.2 s; batch of 10 ~0.01–0.27 s |
| peak RSS | ~1.5 GB (torch import + model) |
| KNN search | **1.7–15 s per query** over 2.86M vectors — this, not encoding, is the cost |

Two operational consequences: (a) encoding a query on every loop iteration is
negligible (~16 ms), so the encoder is not a constraint — only the one-time ~7 s
load is, so keep the embedder process warm rather than spawning it per spec;
(b) the **search** dominates, which is why *candidate-set size* is the lever
that matters (below).

`config/rag.conf` is now set to `python = /usr/bin/python3`. Verified the whole
embed script runs: `scripts/rag_embed_file.py /tmp/rag_query.txt` emits 3072 hex
chars = 1536 bytes = one 384-float32 query vector.

**Still broken (not fixed here):** `rag_search()` in `lib/std/rag.quanta` shells
out to the `sqlite3` **CLI**, which is not installed on this host, and calls
`vec_distance_euclidean(embedding, X'...')`, which is not a sqlite-vec function
name. So the in-language *embed* half now works but the in-language *search*
half does not; drive KNN through `scripts/fast_rag.py` (Python, loads the
sqlite-vec extension properly) until `rag_search` is rewritten. This is a source
fact, not a guess — the CLI is absent from PATH and the vec0 extension must be
loaded by the client.

---

## 2. The corpus is the bottleneck (what retrieval is actually searching)

Source-tree composition of the 2,862,440 chunks (269,747 distinct sources):

| prefix | chunks | share |
|---|---:|---:|
| `learning/` (clone dump of GH repos) | 2,640,560 | **92.2%** |
| `compiler/` (mostly STATE.md/IR dumps) | 189,328 | 6.6% |
| `test_suites/` | 18,769 | 0.66% |
| `lib/` | 10,215 | 0.36% |
| `docs/` | 2,244 | 0.08% |
| `generated/` | 605 | 0.02% |
| `tools/` | 583 | 0.02% |

93.5% of chunks are `md` prose. The Quanta-relevant material (`lib/`, `docs/`,
`generated/`, `test_suites/`) is ~1% of the index. Any un-filtered KNN spends
almost all its distance budget comparing against clone noise — visible
directly: the top hits for "insertion sort algorithm over an integer buffer"
were chunks of `learning/LINKS_CLONE_GH/infinite-bookshelf/Example_2.md`.

Two further corpus facts that decide the design:

- **The index is stale.** The corpus indexes `lib/std/<domain>_<category>_<module>.quanta`
  (9,364 `lib/` sources), but at HEAD those paths **do not exist on disk** — the
  repo's `lib/std/` has 165 files and the same modules now live at
  `planned/lib_std/` (9,237 files). The db was written ~2026-09-17; HEAD is
  2026-10-14. Retrieval therefore returns paths that must be remapped (or the
  store rebuilt).
- **The targets are stubs.** Of 9,237 `planned/lib_std/*.quanta`,
  **8,817 (95.5%) have no non-trivial function body** — they are auto-generated
  metadata (`// Domain: … | Category: … | Module: …` + `// Notes: …`) plus
  `const MODULE_STATUS` and functions returning a constant. Only 420 (4.5%)
  contain real logic. There is very little *content* for a semantic model to
  discriminate on.

And the naming convention is the spec triple concatenated:
`computer_science_algorithms_sorting.quanta` == domain `computer_science`,
category `Algorithms`, module `Sorting`. **Matching a spec to its module is a
name-matching problem here, and a general sentence embedder has no advantage at
it.**

---

## 3. Is semantic retrieval better here? (measured; keyword often wins)

`stage1/retrieval/compare_retrieval.py` — 10 real manifest specs, one per
domain, each with an objective ground-truth implementation file named BEFORE
looking at any result. Methods: **K** keyword token-overlap (today's path),
**Kc** keyword restricted to the curated candidate set, **S** all-MiniLM KNN
over the whole store, **SC** same KNN filtered to drop `learning/`+`tools/`.
`rank` = 0-based position of the target in the top-10, `—` = not retrieved.

| # | spec (domain / module) | K | Kc | S | SC |
|---|---|---|---|---|---|
| 1 | accounting / Revenue Recognition | 2 | 2 | 3 | **1** |
| 2 | advertising / Copywriting | **2** | **2** | — | 9 |
| 3 | agriculture / Wheat | **2** | **2** | — | — |
| 4 | airlines / Route | **2** | **2** | — | 3 |
| 5 | biology / DNA | — | — | — | **2** |
| 6 | computer_science / Sorting | 2 | 2 | **0** | **0** |
| 7 | investment / Listing | **2** | **2** | — | — |
| 8 | logistics / Dry Van | **2** | **2** | — | — |
| 9 | mathematics / Vector Spaces | 2 | 2 | 3 | **1** |
| 10 | programming_language / HTML | — | 6 | **1** | **1** |

Aggregate (of 10):

| metric | K | Kc | S | SC |
|---|---:|---:|---:|---:|
| target retrieved (top-10) | **8** | **9** | 4 | 7 |
| avg code (`type=quanta`) chunks in top-10 | 4.0 | 7.4 | 0.7 | 3.2 |
| avg curated-source chunks in top-10 | 6.0 | 10.0 | 3.1 | 10.0 |

Head-to-head on target retrieval:
- S vs K: **wins 2, losses 7, ties 1**
- SC vs K: wins 5, losses 5, ties 0
- SC vs Kc: wins 5, losses 5, ties 0

Deeper KNN pool (K_KNN=4096 vs an earlier 200) moved SC from 6/10 to 7/10 and
`advertising` from `—` to 9; S and K were unchanged. So the pool depth matters
only for the curated branch, and modestly.

**Honest conclusion: semantic retrieval does NOT dominate keyword retrieval on
this corpus.** Concretely:

- `advertising/Copywriting` and `agriculture/Wheat`: keyword retrieves the
  target at rank **2**, both semantic variants return `—` (the KNN top-10 are
  `learning/…/ad-copywriting/SKILL.md`, `…/copywriting/SKILL.md` etc. — genuinely
  topically similar *prose* from the clone dump, but not the module).
- `investment/Listing`, `logistics/Dry Van`: same shape — K=2, S=—, SC=—.
- Semantic's wins are real but scattered: `Sorting` (both K and SC at 0),
  `HTML` (S/SC at 1 vs keyword `—`), `Revenue Recognition` and `Vector Spaces`
  (SC at 1 vs keyword 2).

The failures are explained by the two corpus facts above: the target is a ~2 KB
machine-named stub whose body says nothing, buried under 2.6M clone chunks;
lexical matching on the name wins. **That is an architectural finding, not a
disappointing one.**

Pre-existing evidence of the same asymmetry from the opposite direction: the
prior unit's `stage1/ctx/RAG_RETRIEVAL.txt` shows keyword failing badly on a
*paraphrased* query — `'insertion sort algorithm'` returned morphology and an
XSS skill — because keyword has no name to match. Keyword wins when the query
carries the module name; semantic is the only option when it does not.

---

## 4. Design: how the loop's retrieval should work end to end

### 4.1 What gets embedded

- **Queries**: the spec text (name triple + behaviour notes), encoded per
  iteration at ~16 ms. Cheap; keep the process warm (~7 s cold load once).
- **Corpus**: only chunks that pass the curation filter (below). Today the whole
  2.86M store is embedded and searchable; that is the problem, not the solution.
  Do **not** re-embed the 2.8M store — the vectors already exist and are valid.

### 4.2 The candidate set is the primary lever

Exclude `learning/` and `tools/` (92%+ of the index). Then take a view over the
~220k curated chunks, or — better — a **separate small KNN index** over the ~32k
chunks from `docs/`, `lib/`, `generated/`, `test_suites/` (excluding the 189k
`compiler/` dumps). Effect measured here: dropping `learning/` moved average
curated-source chunks in the top-10 from **3.1 (S) to 10.0 (SC)** and raised
the target-hit rate from 4/10 to 7/10. Search cost also scales with the index:
a ~32k-vector index is ~90× less work than 2.86M, turning the 1.7–15 s KNN into
well under a second. **Curation buys both quality and latency.**

### 4.3 Retrieval is a hybrid — name first, semantics second

- **Module selection ("which existing module corresponds to this spec") →
  normalised name/keyword match.** Evidence: Kc finds the target in 9/10 at rank
  2; S finds it 4/10. The filename *is* the spec triple; collapse case, `_`, and
  domain synonyms and match on that. The embedder adds little and can lose.
- **Content similarity ("which real implementation does something like this") →
  semantic**, but only once real implementations exist. With 95.5% of
  `planned/lib_std` being `return 0` stubs there is nothing for a sentence model
  to match on; running semantic over stubs is why it loses here. Revisit this
  half when the stub fraction drops.

So: **retrieve by name to pick the module; retrieve by meaning to pick the code
inside it.** They answer different questions and should not be one ranking.

### 4.4 What gets retrieved, and the context budget (measured)

Current `config/rag.conf`: `default_top_k = 5`, `context_chunks = 3`. The
harness (`stage1/harness.py build_prompt`) assembles SYSTEM card + LANGUAGE_CARD
+ ONE `neighbour_<spec>.txt` (the closest real implementation) + the spec.

Measured with the **LFM2 tokenizer** (`/opt/tali/ti/ai/models/lfm2.5-2b6`,
`local_files_only=True`), token counts for the real prompts on disk:

| prompt | bytes | tokens | bytes/tok |
|---|---:|---:|---:|
| PROMPT_sorting.txt | 10,848 | **3,638** | 2.98 |
| PROMPT_boolean_algebra.txt | 10,989 | **3,628** | 3.03 |
| PROMPT_sortino_ratio.txt | 10,589 | **3,544** | 2.99 |

Component breakdown of `PROMPT_sorting` (3,638 tok):

| component | tokens | share |
|---|---:|---:|
| LANGUAGE_CARD (static, identical every iteration) | 1,947 | **54%** |
| SYSTEM card + labels (static) | ~1,198 | 33% |
| retrieved neighbour | 317 | **9%** |
| spec | 176 | 5% |

Note: the earlier estimate "10,583 B ≈ 2.6k tokens" is ~40% low — the LFM2
tokenizer gives ~3.0 bytes/token, so these prompts are **~3.6k tokens**.

The tension the design must name: a prior unit measured this prompt size against
the then-measured prefill rate and got *minutes before the first generated
token* (that prefill rate is the throughput unit's to re-measure; this unit did
not). Two facts set the dial:

- **~87% of the prompt is static scaffolding**, prefilled identically on every
  iteration and for every spec. It should be prompt-cache / prefix-cached once,
  not paid per attempt. That, not shaving the retrieved context, is the bulk of
  the win.
- **The retrieved context is only ~9%** (317 tok), and it was *sufficient*: the
  one spec that passed in the prior 3-spec run used a neighbour of this size.
  So there is room to retrieve **2–3 modules** (~600–1,000 tok) without moving
  the total much — and no reason to retrieve the free-text 3 chunks × arbitrary
  size that `context_chunks = 3` implies over a prose-dominated index.

Recommended dial: **cap the assembled retrieved context at ~1,500 tokens total
(≈2–3 modules), prefer `type=quanta` neighbours, and cache the ~3.1k-token
static prefix.** If prefill is still the bottleneck, cut the LANGUAGE_CARD
(1,947 tok, over half the prompt) behind a cached prefix or a shorter card
before touching retrieval — the retrieved block is already the cheap part.

### 4.5 One-line summary of the recommendation

Build a **curated ~32k-vector index** (drop `learning/`, `tools/`, `compiler/`
dumps), select the module by **normalised name match**, use **semantic** only
for content similarity once real implementations exist, retrieve **2–3
`quanta` neighbours ≤ ~1.5k tokens**, and **prefix-cache the ~3.1k-token static
prompt**. Re-index when the stale `lib/std` → `planned/lib_std` paths are
settled. Semantic retrieval is feasible today (encoder wired, index live) but is
**not yet superior** here, and the reason is the corpus, not the embedder.

---

## 5. Reproduce

```
/usr/bin/python3 stage1/retrieval/compare_retrieval.py     # writes REPORT.md, results.json
```
Read-only against the store; writes only into `stage1/retrieval/`. Set
`K_KNN` to change the KNN pool (hard-capped at 4096 by sqlite-vec).

Prompt token counts: load the LFM2 tokenizer from
`/opt/tali/ti/ai/models/lfm2.5-2b6` (`local_files_only=True`) and encode the
`stage1/ctx/PROMPT_*.txt` files.

## 6. The generator output cap (this unit's change to `stage1/harness.py`)

Independent of the retrieval work: the generator was capped at 700 completion
tokens and it was truncating output, which the loop then read as model failure.

- **File / line**: `stage1/harness.py`, `GEN_TOKENS` — was line 31, now line 37
  (a comment block was added above it). It is the single source for the request's
  `max_tokens` (passed at line 137).
- **Value**: `700` → **`1400`**.
- **Why**: in the prior 3-spec run the one passing spec (`boolean_algebra`) needed
  575 tokens, while BOTH failing specs (`sorting`, `sortino_ratio`) hit **exactly
  700** on every attempt (`stage1/logs/run.log`) — i.e. truncated mid-expression,
  then "failed to compile" for a reason that was never the model's fault. 1400
  gives headroom for a full ≤30-line module plus its self-test `main()`.
- **Pending**: the experiment has **NOT** been re-run. The model runs are the
  native-throughput unit's resource; re-run `python3 stage1/harness.py` after that
  unit finishes, and do not read a 1400-token truncation as model incapacity
  either.

`stage1/` is gitignored by repo policy (`.gitignore`'s `/*` catch-all, with
`compiler/ docs/ lib/ config/rag.conf test_suites/ …` the only re-included
trees), so this edit lives in the working tree where the harness reads it, and is
recorded here so the next session does not have to rediscover it. The retrieval
study artifacts likewise live in the untracked `stage1/retrieval/`.

## 7. Not verified here

- Prefill rate (minutes-to-first-token) — cited from the prior unit, **not**
  re-measured by this unit; the other unit owns native throughput.
- Whether a curated **32k-vector** index really returns sub-second KNN — argued
  from index size and measured per-query scan cost, not built and timed. The
  curated branch here is a *filter over the 4096-deep global KNN*, which
  approximates but is not a curated-only index.
- The output-cap change was not exercised by a model run (see §6).
- Nothing was promoted; no VERSION bump; the gate was not run.
