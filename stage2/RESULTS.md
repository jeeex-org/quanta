# stage2: the SI loop wired end to end for one spec — raw trail

Status: measured 2026-10-16, HEAD `968d3646`, VERSION `0.0.245`, golden compiler
`compiler/0.0.244/bin/x86/qc` (md5 `886e36f8318aaae414e188e947d11c49`). One spec,
one run id (`run_20261016_112523`), every stage of
`spec -> retrieval -> prompt -> generate -> compile -> feedback -> retry` executed
with its timing and its artifacts on disk.

Environment (recorded with every timing; timings are NOT quiet-box numbers):
governor `powersave`, 20 cores, ambient load 10.4→18 during the runs, top CPU
consumer `Hermes` (Electron). The box was busy the whole session; per the house
rule, treat the absolute wall-clock numbers as load-inflated and the ratios
within one run as the honest quantity.

---

## 1. What was wired (the deliverable)

`stage2/wire.py` — the loop, one command per stage group:

```
python3 stage2/wire.py <spec.quanta>              # retrieval + prompt + launch
python3 stage2/wire.py --poll --resume-id ID      # poll the background run
python3 stage2/wire.py --resume-id ID             # compile/run/feedback/retry
```

Generators and helpers, all new files, all in `stage2/`:

| file | what it is |
|---|---|
| `wire.py` | orchestrator: retrieval, prompt assembly + budget enforcement, background launch, compile, run, error-feedback retry, provenance JSON |
| `lfm2_gen_driver.quanta` | the tracked `tests/lfm2_generate.quanta` with exactly 3 deltas (see its header): stage2 conf/prompt paths, max_new clamp 256→1024, prefill through `fc_prefill_batch_lg` |
| `tok_count.quanta` | counts the assembled prompt with the in-tree BPE (`bpe_encode_special`), no forward pass — the pre-flight ground truth |

Artifacts of the run live in `stage2/run_20261016_112523/`:
`spec.json`, `run.json` (per-stage timings + commands + env), `retrieval.json`
inputs (`stage2/rag_query.txt`, `.hex`, `rag_knn_raw.txt`), `prompt.txt`,
`prompt_attempt2.txt`, `prompt_attempt3.txt`, `tokcount.txt`,
`gen_stdout.crash1.txt` (attempt that died), `gen_stdout.txt` (latest),
`attempt{1,2}.quanta` + `.compile.txt` + `.raw.txt`, and the binaries.

## 2. The spec

`planned/lib_std/mathematics_algebra_boolean_algebra.quanta` — the same spec
stage1 proved passable with an external llama-server (2 attempts, one compile-
error feedback). Header: `Domain: mathematics | Category: Algebra | Module:
Boolean Algebra`, notes "Boolean rings, lattices, SAT kernels → `math_full`
0.187+". It is a stub (`init`/`validate` returning constants).

## 3. Stage: retrieval (hybrid, live over the repaired store)

Command: `python3 stage2/wire.py --dry` / the real launch (both measured; the
numbers below are from the real launch, `run.json` → `stages.retrieval`).

| arm | cost (measured) | result |
|---|---:|---|
| name match (spec triple == planned filename) | <1 ms | HIT — the file exists |
| keyword over the store (SQL LIKE over curated quanta chunks, remapped `lib/std→planned/lib_std`) | 7,283 ms | 40 rows; top hits: the module's own const-test chunks, `lib/std/linalg.quanta`, `sidechannel`, `x509_asn1` |
| semantic (embed via `scripts/rag_embed_file.py` + vec0 KNN k=4096 via `scripts/rag_search_file.py`) | embed 16,824 ms + KNN 9,894 ms | 25 curated rows; top hits `docs/OS_ROADMAP.md`, `docs/status.md`, `si_impl_engine.quanta` at L2 distance 1.06–1.08 |

Neighbour picked: **`lib/std/linalg.quanta` (keyword arm)** — a real 10 KB
implementation; the semantic arm returned near-orthogonal distances (~1.06,
where 1.41 = orthogonal for normalised 384-d vectors) on self-improvement
prose. This reproduces the design doc's measured conclusion **live in the
loop**: keyword/name selects the module, semantic adds nothing for module
selection on this corpus (92% clone noise, machine-named stubs).

Two measured corrections to prior claims:

- the keyword store query is **not** "0.2 s" as stage1's notes say — the
  curated predicate is a full scan; first cold measurement **34.96 s**, warm
  5.1–7.3 s (page cache);
- the semantic KNN at k=4096 is ~10 s warm, embed 16 s warm (torch import
  dominates; the per-query encode itself is ~16 ms as documented).

## 4. Stage: prompt (compact, measured, enforced)

Card: `tests/lfm2_compact_card.txt` (the 372-token measured compact card) +
`===== TASK =====` + spec fields + a 250-byte trimmed head of the neighbour.
`wire.py` shrinks the neighbour head (900→600→400→250→0 bytes) until the HF
tokenizer count fits the 600-token budget, then `stage2/tok_count.quanta`
measures the in-tree count of the FINAL prompt:

```
tok_count user_bytes=1917 prompt_bytes=1974 prompt_ids=583 (bos=124894)
```

- prompt bytes 1,917 → **583 in-tree tokens** (HF estimate 573 — 1.7% apart)
- vs the stage1 assembled prompt: 3,638 tokens → **6.24x smaller**, and the
  retrieved neighbour is 250 bytes, not 1,035
- budget enforcement is measured, not asserted: the 583 number is the count of
  the exact bytes the driver reads, from the encoder the model sees

## 5. Stage: generation (native, batched prefill, background)

Driver conf: `20 <max_new> 250 40 12345 1 0` (workers=20, temp 0.25, top_k 40,
seed 12345, EOS policy on). Run under `ulimit -c 0 -v <cap>; timeout 14400
nice -n 19`, launched as a background process, polled.

### attempt A1 (max_new 700) — died mid-decode, SILENTLY

```
load_ms=1394  prompt_ids=583
prefill_ms=1486041  prefill_ms_per_tok=2548  batch=64
---generated--- (≈480 think tokens) ... then nothing
```

Exit status read from the zombie: **256 = the program's own exit(1)**, no FAIL
line, no diagnostics. Root cause chain, measured:

- `lib/std/lfm2_mm.quanta` (~line 865): the allocator's MAP_FAILED guard is
  `mov edi,1; mov eax,60; syscall` — a **silent exit(1)**;
- RSS at death was only ~342 MB — but VmPeak tracking on the next run shows
  **virtual** memory climbing ~11 MB per decoded token (4.5 GB after prefill →
  13.1 GB by token ~1000, vs an RSS slope of ~0.35 MB/token);
- attempt A1 therefore died when VmPeak reached the 8 GB `ulimit -v` cap at
  ~480 tokens. **The old 8 GB cap cannot hold a multi-hundred-token native
  generation regardless of RSS.**

Consequence: wire.py now samples VmPeak/VmRSS on every poll, the run cap is
32 GB (RSS stays sub-GB; timeout + nice stay), and a generation that exits
without DONE is recorded as `generation_crashes[]` with its stdout preserved
(`gen_stdout.crash1.txt`) and retried.

### attempt A2 (max_new 700, brevity feedback added) — truncated at the cap

```
prompt_ids=642  prefill_ms=1558976  prefill_ms_per_tok=2428  batch=64
new_tokens=700  gen_ms=5170179  gen_ms_per_token=7385  decode_tok_per_s_x1000=135
```

Truncated mid-think — the model spent ~600 of 700 tokens inside the
chat-template's forced ` Meadow thinking block. Extracted file compiled with
`error: no 'main' function found` (rc=7) — the exact diagnostic fed back.

### attempt A3 (max_new 1024, compile diagnostics + brevity fed back)

```
prompt_ids=697  prefill ≈ 1.56e6 ms (2428 ms/tok)  batch=64
new_tokens=1024 gen_ms=8776466  gen_ms_per_token=8570  decode_tok_per_s_x1000=116
```

Think finally closed at ~token 512, the fence opened, ~500 tokens of code —
truncated again at the 1024 cap, mid-expression. Compile: rc=7,
`error: no 'main' function found` again; fed back for the final retry (A4,
pid recorded in `run.json`).

### attempt A4 = JSON attempt 3 (max_new 1024, diagnostics + brevity fed back)

```
prompt_ids=697  prefill_ms=1781233  prefill_ms_per_tok=2555  batch=64
new_tokens=1024 gen_ms=7890181  gen_ms_per_token=7705  decode_tok_per_s_x1000=129
```

Think again closed at ~token 512, fence opened, code emitted — truncated at
the 1024 cap mid-expression, `error: no 'main' function found` (rc=7) again.
`--max-attempts 3` exhausted → the loop concluded `outcome=compile-fail`.
VmPeak at token ~1000: 12.9-13.2 GB, inside the 32 GB cap (the OOM is
contained; the truncation is the surviving failure mode).

### measured throughput (the numbers the loop plans around)

| quantity | measured this session | prior docs |
|---|---|---|
| batched prefill (B=64, 20 workers, load 10-18) | **2,428–2,548 ms/prompt-token** | 1,838 ms (brief's number, quieter box) |
| decode (temp 250, top_k 40, 20 workers) | **7,385–8,570 ms/token** | 7,352–7,924 (README, load ~9.5) |
| RSS | 165→340 MB over ~1000 tokens (+0.35 MB/tok) | 165-181 MB for 24 tokens |
| VmPeak | 4.5 GB post-prefill, +~11 MB/token | not previously tracked |

A 583-token prompt = ~24 min prefill; a 700-token completion = ~86 min decode.
**One attempt ≈ 1.8-2.9 h wall. This is the honest unit cost of the native
loop on this box.**

## 6. Stage: compile + run + feedback (the oracle half)

- compile: `( ulimit -c 0 -v 8000000; compiler/0.0.244/bin/x86/qc <src> <out> )`
  — sub-second per attempt (recorded in `run.json`).
- both compile-failing attempts produced the exact diagnostics and they were
  fed back verbatim into `prompt_attempt{2,3}.txt`:
  `error: no 'main' function found` (truncation never reached a `main`).
- no attempt has compiled yet, so the RUN half (quanta_run.sh, output compare
  vs the spec) has not been exercised by this run — it is wired and unexercised
  (see `wire.py run_bin`), the same state stage1 left it in.
- the feedback→relaunch path itself is proven working end to end (twice), and
  one wiring bug was found and fixed during it: the retry condition read the
  `MAX_ATTEMPTS` constant instead of the `--max-attempts` argument, silently
  dropping the third attempt.

## 7. The honest verdict on unattended operation

**The loop now RUNS unattended through every stage — retrieval, measured
prompt, background native generation, compile, exact-diagnostic feedback,
relaunch — and recovers from both failure modes it hit (silent crash,
truncation). It did NOT produce a green module in this session: 3 compile
attempts, all truncated by the max_new cap before `main()` was reached
(`error: no 'main' function found`, rc=7, fed back each time), and the
blockers are model+budget, not wiring:**

1. the chat template forces a thinking block; the 2.6B model spends 500-600
   tokens thinking before the fence, so a ≤700-token budget cannot hold
   think + a complete file. max_new=1024 finally got a file started; it
   truncated mid-expression. The cap vs think-length race is the loop's
   dominant failure mode. (levers: an in-prompt "no thinking" contract,
   `sample_set_min_len`, or a finer-tuned generator.)
2. at 7.4-8.6 s/token decode, each attempt costs 1.5-2.9 h; a 3-attempt
   policy is a 5-9 h commit per spec. Unattended overnight runs are
   feasible; interactive use is not.
3. two library-level defects were measured and are queued for their owners:
   the silent MAP_FAILED exit(1) (lfm2_mm ~865) and the ~11 MB/token VSZ
   growth of decode (unbounded sessions will OOM at any fixed cap; ~1000
   tokens is today's practical ceiling at 32 GB).
4. when (1) is beaten, the run half needs its first green: compile →
   quanta_run.sh → compare vs the spec's expectation, which is wired but has
   never executed a passing binary.

## 8. Reproduce

```
cd /opt/tali/quanta
python3 stage2/wire.py planned/lib_std/mathematics_algebra_boolean_algebra.quanta
python3 stage2/wire.py --poll --resume-id <id>
python3 stage2/wire.py --resume-id <id> --max-attempts 3 --max-new 1024
```

Raw per-stage JSON: `stage2/run_20261016_112523/run.json`. Every external
command is recorded verbatim next to its timing and rc.
