# 0.0.241 — WIP · **LEVER: three correctness defects + the Q6_K reference check**

Four deliverables, each with a red-first or reference-first proof. This is the
first version in the 0.0.2xx line whose **compiler source changed** (features.quanta,
method.quanta, parse.quanta), so unlike a lib-only release the binary moves:

```
0.0.240 golden  md5 6f83fe08a7f8819a725fe50c81680ef1   (frozen baseline)
0.0.241 built   md5 02b155430d10661b17645680b4092987   gen1 == gen2 == gen3
```

`compiler/0.0.241/src` vs `compiler/0.0.240/src` is **three files**; everything else
is byte-identical. `compiler/0.0.241/lib/**` and `compiler/0.0.241/test_suites/**`
are the 0.0.240 snapshot copied verbatim (the same stale-snapshot situation 0.0.239
and 0.0.240 recorded); imports resolve to the REPO `lib/std`, which is what the
build and the gate use.

---

## 1. A top-level `const` with a FLOAT initialiser evaluated to 0 — FIXED

### Minimal repro (golden compiler, raw)

```quanta
const CF = 2.5
const CI = 42
fn main() {
    prints("CF bits "); print(f64bits(CF)); newline()
    prints("CI     "); print(CI); newline()
    let r = CF + 2.5
    prints("CF+2.5 bits "); print(f64bits(r)); newline()
    return 0
}
```

```
0.0.240:  CF bits 0                            <- want 4612811918334230528
          CI     42
          CF+2.5 bits 4612811918334230528      <- want 4617315517961601024 (5.0)
0.0.241:  CF bits 4612811918334230528
          CI     42
          CF+2.5 bits 4617315517961601024
```

`CF + 2.5` returned **2.5** on the golden, i.e. CF acted as 0.0.

### Root cause (found, not guessed)

The lexer emits a float literal as **TT_FNUM (7)** — value `(mantissa << 8) |
frac_digits`, signed decimal exponent in the token's **side word**.
`eval_const()`'s literal branch tests `peek()==TT_NUM` **(2)**, so a float literal
matched nothing, `ec_factor()` returned 0 **without consuming the token**, and that
0 was written into the const table.

TWO sites write the const table and both had copied the same bug:

* **`features.quanta` (kt==57) — the one that actually runs for a TOP-LEVEL const.**
  The feature/global scan evaluates `const NAME = EXPR` *before* the parser and
  registers it. This is why fixing `parse_const()` alone changed nothing (measured:
  the `0.0.241` binary md5 was identical before and after that edit — proof the
  parse path is not the one taken for a top-level const).
* **`parse.quanta:parse_const()`** — same structure, same `else { eval_const() }`.
  Fixed too, so a const inside a function body cannot reintroduce the defect.

### The fix

Both sites now detect `peek()==TT_FNUM`, read the exponent with `toke(tokp)`
**before** `adv()` (afterwards `tokp` points at the next token — the trap
`method.quanta`'s TT_FNUM branch documents), store the **exact IEEE-754 bit
pattern** via `fl_dexp2f64()` (the same helper the ordinary float-literal path
uses), and record **kind = 2**. The three const-use sites in `method.quanta`
(TT_ID primary, TT_KEY primary, marked-const path) emit **IR_FCONST** for kind==2 —
the float-constant opcode `codegen.quanta`'s re-mark pass keys on — instead of
IR_CONST, which is what makes the operand a float vreg rather than an integer
holding a float's bits.

The TT_ID site must test kind==2 **before** the `cv0 >= bvmark()` enum test and
before the `cv0 >= 0` guard: an f64 bit pattern is an unremarkably large positive
integer (2.5 → 4612811918334230528 > bvmark() = 2^60), so it would otherwise be
read as an enum-variant mark, and a negative float's pattern is < 0 so the guard
would skip it and the name would fail as "undeclared".

**Fail-closed for what cannot be evaluated:** a float *expression* initialiser
(`const X = 2.5 * 4.0`) needs a float const evaluator that does not exist.
Half-parsing it silently recorded just `2.5` (measured, before the guard). Now:

```
$ compiler/0.0.241/bin/x86/qc --no-overflow-trap cn_expr.quanta /tmp/o
error: a float const initialiser must be a bare literal (no expression): CN
rc=7
```

### Red-first gate row

`test_suites/codes/const_float_test.quanta` (EXPECTED.tsv, expected rc 0) — 10
float consts covering a fraction, an exponent, a long mantissa, plus an integer
regression guard, checked by **exact f64 bits**; plus arithmetic use and use as a
function argument. Every expectation derived numerically, not from memory:

```
/usr/bin/python3 -c "import struct; print(struct.unpack('<q',struct.pack('<d',5.5))[0])"
```

```
0.0.240 (golden):   const_float: FAIL 13 case(s)   run rc=1
                    FAIL CF: got 0 want 4612811918334230528
                    ... (all 10 consts, plus CF+CF, CF*CH, addf(CF,3.0))
0.0.241 (fixed):    const_float: PASS              run rc=0
```

`CI_INT == 42` passes on BOTH, so the row is not a blanket change.

**Known limitation, stated rather than hidden:** a *negative* float literal
(`const X = -2.5`) is still 0. The lexer emits it as `TT_OP '-'` then `TT_FNUM`, so
it never reaches the bare-literal branch and `eval_const` cannot read it either. It
was 0 before this version too (no regression), and no file in `lib/`, `compiler/`,
or `test_suites/` uses one — only `stage1/sp_const_probe.quanta`, a scratch probe.

### Nothing in the tree depended on the old (0.0) behaviour

```
grep -rn 'const ... = [-0-9][0-9]*\.[0-9]' --include=*.quanta lib/ compiler/ test_suites/
```
returns **only** `stage1/sp_const_probe.quanta` (scratch). So the fix cannot change
the meaning of any shipped program; it only stops a silent 0.

---

## 2. `lib/std/tokenizer_trait.quanta` called `bpe_encode`, not `bpe_encode_special` — FIXED

`vt_encode()` called `bpe_encode()` at both call sites. `bpe_encode` does **no
special-token matching**, so a chat template's control tokens (`<|im_start|>`,
`<|im_end|>`) were byte-encoded and BPE-merged as ordinary text. The prompt is still
valid ids, so nothing downstream errors — the model simply sees a different prompt.

Fix: both call sites now call `bpe_encode_special()`, which falls back to
`bpe_encode()` itself when the vocab carries no `token_type` array
(`bpe_special_n == 0`) — so a model without specials gets identical ids, which is
what keeps the existing `std_tokenizer_trait_test` delegation checks green
(verified: that STDLIB row still PASSes, 67 checks).

**Interface note:** one `vt_encode` is the right seam. Special tokens are the
model's own vocabulary, not a caller's choice — there is no caller for whom
tokenising `<|im_start|>` as ten ordinary bytes is correct — so the trait exposes
the special-aware path only rather than a pair the caller could pick wrongly.

### Red-first evidence (raw)

`test_suites/codes/std_tokenizer_trait_special_test.quanta` (EXPECTED_STDLIB.tsv,
rc 0, GGUF in SKIP_IF_MISSING). Expectations are llama.cpp's own tokenizer
(`llama_cpp` python bindings, `m.tokenize(text, add_bos=False, special=True)`):

```
"<|im_start|>user"     -> [124899, 5922]
"<|im_end|>"           -> [124900]
"hello<|im_end|>world" -> [52071, 124900, 27735]
"a<|im_start|>b"       -> [73, 124899, 74]
"hello world"          -> [52071, 1530]
"The quick brown fox"  -> [597, 4104, 10299, 35886]
```

```
with the fix REVERTED (vt_encode -> bpe_encode):
  FAIL: <|im_start|>user = 6 ids, want 2
  FAIL: <|im_end|> = 5 ids, want 1
  FAIL: hello<|im_end|>world = 7 ids, want 3
  FAIL: a<|im_start|>b = 7 ids, want 3
  std_tokenizer_trait_special: FAIL 4 check(s)      rc=1
with the fix:
  std_tokenizer_trait_special: PASS                 rc=0
```

The row also asserts that no-special text is byte-identical to plain BPE (the
ordinary path is untouched) and that `bpe_encode` does NOT emit the special id (so
the two paths stay distinguishable).

---

## 3. The Q6_K output projection — a REFERENCE CHECK, and the divergence is NOT there

Premise handed in: native `p("The") = 0.251` vs llama.cpp `0.847`, only 1 of the
top-10 ids shared, argmax agrees; prime suspect the Q6_K tied output projection.

**Confirmed first, so the premise is not being argued with:** for a fixed 23-id
prompt, native `p(597)=0.250726`, llama.cpp `p(597)=0.910269`, top-10 overlap
**1/10**. logit range native −17.03..11.49 vs llama −17.63..22.68; **mean −4.013 vs
−3.955 and sd 2.742 vs 2.724 are nearly identical** — the bulk distribution is right
and the extreme tail is wrong.

### 3a. The Q6_K dequant IS bit-exact (prime suspect refuted)

`token_embd.weight` is **Q6_K [2048, 128000]** (confirmed from the GGUF: 19 Q6_K
tensors, 148 Q4_K, 99 F32). The house rule is to link the real kernel rather than
transcribe it, so a shim calls the genuine `dequantize_row_q6_K`:

```
extern void dequantize_row_q6_K(const void *x, float *y, int64_t k);
gcc -O2 -w -o q6k_oracle q6k_oracle.c \
    -I/opt/ai/llama.cpp/ggml/include \
    -L/home/tali/.local/lib/python3.12/site-packages/lib64 \
    -lggml-base -Wl,-rpath,.../lib64 -lm      # prints %.17g per element
```

Fixture (840 bytes = 4 blocks × 210, built in-language by the gate row):
block 0 `byte[j]=(j*37+11)%256`, d=1.0 · block 1 `byte[j]=(j*101+200)%256`, d=−0.5 ·
block 2 hand case (`ql[0]=0x21`, `sc[0]=2`, rest 0, d=1.0) · block 3 all 0xFF.
Blocks 0/1 sweep the full byte range so every packed field is exercised across its
whole width.

Result — **BIT-EXACT, 0 ULP**:

| check | value |
|---|---|
| hand case elem 512 | −62.0 exactly (1.0·2·(−31)) |
| 15 sampled elements across all block boundaries | exact |
| sum over 1024 | −9878.0, bits −4556715934596726784 |
| sumsq over 1024 | 630193196.0, bits 4738569652051902464 |

Permanent row: **`test_suites/codes/q6k_dequant_ref_test.quanta`** (EXPECTED.tsv,
rc 0, no model needed — the fixture is built in memory). It passes under BOTH
0.0.240 and 0.0.241 (lib-independent). The pre-existing
`gguf_q6k_dequant_test.quanta` never calls the dequant at all (a 3-byte mask test)
and `blocks_oracle.c` covers no K-quant.

### 3b. The output projection is arithmetically exact

Reference for the projection alone: dump the native final normed hidden state
`fc_fw_n` after the same 23-id prefill, then check
`logits[i] == dot(dequant(row_i of token_embd), fc_fw_n)` with `row_i` dequantised
by the real kernel and the dot in numpy f64:

```
max |native_logit - reference_projection| over 23 sampled vocab rows = 2.665e-14
rows differing by more than 1e-3: 0
```

So the tied output projection, fed the native hidden state, reproduces the native
logits to f64 rounding. **The divergence enters BEFORE the projection.**

### 3c. Where it enters: a position bisection (the accumulation signature)

Same 23-id prompt, native logits dumped at prefill positions, each compared with
llama.cpp evaluated on the **identical ids** (llama_cpp `scores[pos]`):

| pos | native argmax | llama argmax | corr(native,llama) | max logit nat/llama | top-10 overlap |
|---|---|---|---|---|---|
| 0 | 5922 | 5922 | **0.9997** | 9.563 / 9.630 | 9/10 |
| 1 | 207 | 207 | 0.9886 | 19.719 / 19.863 | 9/10 |
| 2 | 5922 | 5922 | 0.9980 | 12.299 / 12.435 | 9/10 |
| 3 | 14066 | 14066 | 0.9538 | 10.189 / 8.845 | 7/10 |
| 4 | 355 | 355 | **0.6881** | 20.150 / 23.610 | 6/10 |
| 5 | 278 | 278 | 0.7865 | 25.680 / 24.104 | 5/10 |
| 6 | 27 | 26 | 0.7361 | 16.945 / 18.148 | 5/10 |
| 7 | 71 | **1510** | 0.6521 | 14.755 / 19.354 | 0/10 |
| 8 | 26 | 27 | 0.7107 | 19.016 / 22.428 | 7/10 |
| 9 | 342 | **19** | 0.5522 | 15.110 / 20.438 | 5/10 |
| 10 | 124900 | 124900 | 0.6330 | 20.776 / 16.009 | 6/10 |
| 22 | 597 | 597 | 0.6691 | 11.490 / 22.676 | 1/10 |

**The per-op arithmetic is right; the error accumulates with sequence position.**
Positions 0–2 agree to corr ≥ 0.988 (position 0 to 0.9997 — the layer stack, the
norms, RoPE, the softmax and the Q6_K projection are all essentially exact on a
near-stateless step). The first clear break is **between position 3 and 4**
(0.954 → 0.688); from position 7 the argmax itself is wrong. A per-layer arithmetic
error would show the same relative error at position 0; this grows, so the defect is
in **carried state** — the per-layer short-conv state (22 conv layers) and/or the KV
cache (8 attention layers).

### 3d. Localisation summary (first point of divergence + delta)

* Q6_K dequant: **exact, 0 ULP** (prime suspect refuted).
* Tied output projection: **exact, max 2.7e-14**.
* Forward positions 0–2: **corr 0.988–0.9997** vs llama.cpp on identical ids.
* First divergence: **between prefill position 3 and 4** (corr 0.9538 → 0.6881;
  max logit 10.19→20.15 native against 8.85→23.61 llama). At position 22 the
  distribution is the reported flat one (p(597) 0.251 vs 0.910, overlap 1/10).
* Conclusion: the defect is in **state carried across positions**, not in the Q6_K
  decoder or the output projection. A **localised, unexplained divergence** — not an
  explained-away one.

### 3e. Next discriminating test (recorded, not run)

1. **Dump the short-conv state and the KV rows at positions 3 and 4** and recompute
   them independently: the conv state after position *t* must be `(g[t-1], g[t])`
   with `g[t] = b[t]*x[t]` from `in_proj @ x_t`; a KV row must be
   `rms_norm_head(rope(v_proj @ x_t))`. Compare elementwise.
2. **F16-twin discriminator** for quant-vs-architecture: the same 23 ids on
   `QUANTA-LFM2.5-2.6Bv1.gguf` (5.1 GB, the unquantised twin) in both the native
   engine and llama_cpp. Positive relative to F16 isolates quantization; identical
   relative to F16 on both engines isolates the architecture/state code.
3. **Layer-type toggle**: LFM2 alternates conv and attention layers
   (`lfm2.attention.head_count_kv` is 0 on conv layers). Run to position 4 with the
   conv state forcibly zeroed each step, and with the KV cache truncated — two runs
   separate the two carriers.

---

## 4. `lib/std/rag.quanta` had NO gate coverage — row added

`lib/std/rag.quanta` is not in EXPECTED_STDLIB.tsv, so the RAG unit's edits to it
were exercised by nothing. The live probe a prior unit left
(`rag_search_live_test.quanta`) does run — measured rc=0 in 7 s under
`quanta_run.sh` — but it depends on **`/tmp/rag_emb_hex.txt`**, a hand-placed
handoff that nothing in the repo creates, because the real encoder needs torch and
torch cannot map its shared objects under the runner's address-space cap:

```
rag_embed_file: libtorch_cuda.so: failed to map segment from shared object
```

As a gate row that dependency is fatal in one direction and invisible in the other:
RED on a fresh runner, GREEN here only because the file happens to exist.

So the row added is **self-contained**:
`test_suites/codes/stdlib_rag_search_gate_test.quanta` builds a deterministic
384-float32 vector in-language (three valid finite float32 patterns cycled by
index), hex-encodes it itself, and drives the **whole** `rag_search` path — spill →
`fork`+`exec` of `scripts/rag_search_file.py` → sqlite-vec vec0 KNN over the 21 GB
store → read the out_file back → `str_split`/field parse — then `rag_parse_results()`
over the same rows, then **determinism** (two identical calls must be byte-identical).

```
[embed] synthetic 1536-byte vector, 3072 hex chars (encoder needs torch; cannot map under the cap)
rag_search_gate: returned 5 ranked rows -- PASS        rc=0
```

One prerequisite — the 21 GB store — declared in SKIP_IF_MISSING
(`/opt/tali/ti/ai/rag/vectors.db`), so an absent store prints `SKIP` and is excluded
from the totals rather than silently passing. The row does **not** claim to verify
embedding quality: the encoder is out of scope under the cap and the row prints
which vector it used. What it establishes is that the repaired in-language search
path works end to end — the coverage that was missing.

---

## 5. Manifest totals

| manifest | before | after | rows added |
|---|---|---|---|
| `test_suites/EXPECTED.tsv` | 225 | **227** | `const_float_test.quanta`, `q6k_dequant_ref_test.quanta` |
| `test_suites/EXPECTED_STDLIB.tsv` | 108 | **110** | `std_tokenizer_trait_special_test.quanta`, `stdlib_rag_search_gate_test.quanta` |

Both new EXPECTED_STDLIB rows carry their GGUF / store path in SKIP_IF_MISSING, so
neither can pass on a runner that lacks its dependency.

---

## 6. Gate, self-hosting, release — all recorded runs are RAW output

Standalone gate, `bash test_suites/scripts/run_tests.sh` with `QC=compiler/0.0.241/bin/x86/qc`
(the PROMOTED tree's own compiler; repo `EXPECTED.tsv` / `EXPECTED_STDLIB.tsv`):

```
=== Results: 227/227 pass, 0 fail (incl. 0 compile-fail) [rows: EXPECTED.tsv] ===
  STDLIB: 110/110 GREEN
  stdlib        : GREEN  (lib/std/* via import, EXPECTED_STDLIB.tsv)
  PASS const_float_test.quanta (rc=0)
  PASS q6k_dequant_ref_test.quanta (rc=0)
  PASS std_tokenizer_trait_special_test.quanta (rc=0)
  PASS stdlib_rag_search_gate_test.quanta (rc=0)
GATE_RC=0
```

All 24 `GATE SUMMARY` stages GREEN: `functional`, `native`, `float-oper`,
`float-builtin`, `float-return`, `float-operpath`, `extern-c`, `extern-ld`,
`security`, `performance`, `valgrind` (0 errors), `fuzz` (0 crashes),
`differential` (-O == no-O), `generics`, `stdlib`, `multi-tu`, `gguf-corrupt`,
`verify-status`, `qobj`, `output-path`, `naked`, `asm-assembler`, `bare-metal`,
`float-print`. Exit 0.

Self-hosting — 3 generations byte-identical, **distinct = 1**:

```
02b155430d10661b17645680b4092987  gen1  (built by the 0.0.240 golden)
02b155430d10661b17645680b4092987  gen2
02b155430d10661b17645680b4092987  gen3
```

The fixed point is reached on the FIRST generation, as expected for a parser/scan
change that does not alter what the compiler emits for its own source.

`bash scripts/verify-release.sh 0.0.241 0.0.240` (PRE-promotion: root VERSION was
still 0.0.240, so 0.0.241 is proved to build from 0.0.240's committed seed and
0.0.240 is proved a valid frozen baseline):

```
PASS  root VERSION = 0.0.240 (<VER>) -- pre-promotion state
PASS  <VER> src rebuilds BIT-FOR-BIT (md5 6f83fe08a7f8819a725fe50c81680ef1) -- qualifies as frozen baseline
PASS  <NEXT> src/bin lockstep: committed binary (02b155430d10661b17645680b4092987) IS the seed-chain fixed point built from 0.0.240 + the committed source
PASS  self-host fixed point: gen0==gen1==gen2==released binary (md5 02b155430d10661b17645680b4092987)
PASS  compiler/0.0.241/WIP.md exists
PASS  official gate ran (log: /tmp/verify_release_gate.log)
PASS  Results: 227/227 pass, 0 fail
PASS  functional stage GREEN
=== 14 passed, 0 failed ===
VR_RC=0
```

**Version promoted:** yes — `VERSION` moved 0.0.240 -> 0.0.241 with the gate green.

**Commits:** manifest rows and their source files landed in ONE commit; staged by
targeted `git add` of named paths only (never `git add -A`), so the concurrent peer
unit's `docs/plans/bugs.md` was NOT swept in.

---

## 7. Not verified / open / queued follow-ups

1. **The residual logits divergence is LOCALISED, not fixed** (§3d/§3e).
2. **`const X = -2.5` is still 0**; a float *expression* initialiser is now a hard
   error (§1). Negative float literals need a sign flip on the bit pattern.
3. **Prefill remains the top queued lever** (unchanged): 5.8 s per prompt token.
4. **`stage1/`** (probes + logits artifacts, ~60 MB) is not part of the gate and
   was not pruned.
5. **A peer unit runs concurrently in the SAME working tree, and its commit swept
   this unit's files in.** This unit staged its paths with targeted `git add` of
   named paths only (never `git add -A`) — after which the peer committed with
   `git add -A` and pushed: commit `12380ab2` ("docs(bugs): …") carries all 28078
   files, including `VERSION`, `compiler/0.0.241/**` and the four new rows. The
   CONTENT is intact and pushed (`git status` clean, `main == origin/main`), but
   that commit message does not describe the 0.0.241 promotion, which is why a
   follow-up commit records it. All four manifest rows and their source files did
   land in ONE commit, so the "rows and sources together" rule held; the lesson is
   that a shared working tree makes `git add -A` a cross-unit write.
   `lib/std/sampling.quanta` was already committed by the peer (`59f58aaf`)
   *before* this unit's gate run, so the 227/227 result includes it.
   `docs/plans/bugs.md` was the peer's own change and is correctly attributed to
   the peer's commit.
