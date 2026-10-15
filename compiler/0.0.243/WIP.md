# 0.0.243 — WIP · **LEVER: Q6_K SIMD dequant (23x, bit-identical) + two defect fixes + the prompt budget**

Three deliverables, each with a red-first or reference-first proof. This version
changes the **compiler source** (four files: `features.quanta`, `emitter.quanta`,
`globals.quanta`, `method.quanta`) because the Q6_K lever and one of the defect fixes
both need compiler changes, so the binary moves.

```
0.0.241 golden  md5 02b155430d10661b17645680b4092987   (frozen baseline, untouched)
0.0.243 built   md5 26430066a4e04f61a687ccf6291b61d7
```

Landed as commit **`1c392ed7`** — 28079 files, staged and committed by
pathspec-limited `git commit -- <paths>` (never `git add -A`), so the concurrent
peer's `docs/plans/bugs.md`, `test_suites/EXPECTED*.tsv` and `compiler/0.0.242/**`
were not swept in. `git diff-tree --no-commit-id --name-only -r HEAD` is exactly the
11 non-`compiler/0.0.243` paths listed in the dirty-path audit plus
`compiler/0.0.243/**`.

`compiler/0.0.243/src` vs `compiler/0.0.241/src` is **four files**; everything else is
byte-identical. `compiler/0.0.243/lib/**` and `compiler/0.0.243/test_suites/**` are the
0.0.241 snapshot copied verbatim (the same stale-snapshot situation 0.0.239, 0.0.240
and 0.0.241 recorded); imports resolve to the REPO `lib/std`, which is what the build
and the gate use.

**`compiler/0.0.242/**` was NOT touched** — it is a committed WIP for the dead-auto-free
defect owned by another unit; its `WIP.md` was read and its tree left alone.

---

## 1. ORDERED ITEM 2 — THE LEVER: Q6_K dequantisation, 45.8 -> 2.0 ns/element

### The defect class it fixes

`dequant_q6k` was the last scalar dequant kernel. It is not an ordinary scalar loop:
per element it does **six integer divisions** to unpack the bit fields
(`qhb - (qhb/4)*4`, `ql0 - (ql0/16)*16`, ...), and `idiv` is 20-40 cycles with no
overlap. Measured on a real Q6_K row (`FFN_DOWN_DEQ`, 10752 elements):

| | before | after | ratio |
|---|---:|---:|---:|
| ns / call | 492,105 | 21,376 | |
| **ns / element** | **45.8** | **1.99** | **23.0x** |

The previous unit estimated 6.1x from the Q4_K instruction-rate comparison and 5.0 s
per decode token. **Measured: 23.0x on the dequant, 10.3 s on a decode token.** The
estimate was low because it compared instruction COUNTS; the scalar loop's cost is
dominated by `idiv`, which the SIMD form removes entirely.

### The builtin

`dq6(dst, ql, qh, dbits, scptr)` — one call per **128-element half** of a Q6_K
super-block, entirely in ymm registers, replacing the scalar loop with ~418
instructions of AVX2 emitted inline. Added in `emitter.quanta` (the sequence) and
`features.quanta` (`is_bltn`).

**One name, not `dq6lo`/`dq6hi`.** `dq32lo`/`dq32hi` split Q4_K because its `ql` is
ONE nibble plane read twice. Q6_K is a 4-bit plane plus a 2-bit plane (`qh`) whose
2-bit groups do **not** line up with 32-element `ql` chunks, so the work is four
`(nibble plane, qh shift, ql half, scale pair)` combinations x 2 halves x 4 vector
groups = 32 groups. Splitting that across two names would only divide the sections;
the caller needs all four, so it gets one call per 128 elements instead of eight per
32 — which also pays the fixed per-call cost once instead of eight times.

**Bit-identity is a multiply-ORDER claim, and that is the whole risk.** The scalar
computes `fmul(d, fmul(i2f(sc), i2f(q)))`, i.e. `d * (sc*q)` with the inner product
first. `sc` is an i8 and `q` is in [-32,31], so `sc*q` is a small integer and is
**exact** in binary64. The builtin therefore multiplies by `sc` BEFORE `d`
(`cvtdq2pd` exact, `vmulpd` by `(double)sc` exact, one `vmulpd` by `d` rounds in the
same place). Pre-folding `d*sc` at the caller would round twice and is NOT
equivalent — the one thing that must not be "optimised" here. No FMA, no
reassociation, and only dequantised VALUES are produced, never a sum.

The three constants (`-32`, `15`, `3`) come from `vpcmpeqd` + one shift, so the
builtin clobbers **no general-purpose register**. Scales are
`vpbroadcastb`+`vpmovsxbd`+`vcvtdq2pd`, i.e. **sign-extended from the i8 byte** as
`i8_at()` does. Byte encodings verified against GNU as, not derived.

### Bit-identity evidence (three independent checks)

1. **`test_suites/codes/q6k_dequant_ref_test.quanta` — the llama.cpp oracle, a
   pre-existing gate row**, unchanged and passing:
   `q6k_dequant_ref: PASS (bit-exact vs dequantize_row_q6_K)`. It compares against
   committed bit patterns dumped from upstream's `dequantize_row_q6_K`, the
   hand-computed `-62.0` case, and the f64 **sum** and **sumsq** over 1024 elements.
   An external oracle, so two paths sharing a bug cannot pass by agreeing.
2. **`tests/q6k_dequant_simd_test.quanta` — scalar vs `dq6`, bit for bit**: `0/65536`
   synthetic (every field swept, `d` alternating 1.0/-0.5) and `0/2097152` on the
   model's own Q6_K tensor, plus a repeat comparison AFTER the timed runs.
3. **The correlation table is untouched by construction** — same bits downstream.

### End-to-end (serial, 1 thread, back to back, same load)

| measurement | before | after | ratio |
|---|---:|---:|---:|
| `FULL_TOKEN_NO_LOGITS_POS0` (prefill token) | 34.63 s | **24.16 s** | **1.43x** |
| `FULL_TOKEN_WITH_LOGITS_POS0` (decode token) | 49.52 s | **28.72 s** | **1.72x** |
| tied output projection | 14.89 s | 4.56 s | 3.27x |

Environment for those: governor `powersave`, load 13.68 -> 16.65, top consumer
`Hermes` (Electron) at 742 % CPU, `nice 0`. The absolutes are ~1.5x the quiet-box
figures in `prefill-batching.md`; the ratio is the claim. Full record:
`docs/research/q6k-simd-dequant.md`.

**Not done, on purpose:** the `mm_embed_logits` scalar dot (left-to-right, ~9-15
ns/element vs `mm_dot4`'s 2.73). It changes the logits BITS, so it cannot be one
lever with a bit-identity bar.

---

## 2. ORDERED ITEM 1 — the two batched-prefill defects

### A11 (FIXED, red-first): an integer `const` >= 2^60 crashed the COMPILER

```quanta
const V = 2305843009213693952          // 2^61
fn main() { print(V); return 0 }
-> 0.0.241 golden:  Segmentation fault (core dumped), rc=139
   0.0.243:          CONST_BIG PASS, rc=0
```

**Root cause.** A bare enum-variant name is registered as a MARKED const,
`bvmark() + ei*1048576 + vidx` with `bvmark() == 2^60`, and the const-use site decided
"this is a marker" by **VALUE RANGE**: `if cv0 >= bvmark()`. For `V = 2^61` that gave
`bei = 2^40` and `evariant_tag()` indexed `enums + 2^40*96` — tens of gigabytes past
the table. Both writers and the one reader are now keyed on the const's **kind** (3)
instead. `2^60` and `2^60+1` survived only because `bei == 0` happened to land inside
the table; the crash threshold is measured and tabulated (unused consts and `let`
bindings are unaffected; `2^60+1` ok, `~1.18e18` crash, `2^61` crash, `2^62` crash).

**This is worse than one const.** The tree writes f64 BIT PATTERNS as integer
constants constantly — `f64bits(1.5)` is `4609434218613702656`, `f64bits(2.0)` is
`4611686018427387904`, and the 0.0.241 WIP quotes `2.5 -> 4612811918334230528`. Every
one is >= 2^60. It was found by accident: `tests/f64of_mem_load_shape_test.quanta`
used one such const and qc segfaulted.

### A12 (FIXED in c77d06db, PINNED here): `mm_workers = 0` was a division by zero

`mm_workers` defaults to 0 and `mm_set_workers(0)` is the documented serial setting,
but the new `mm_matmul` / `mm_embed_logits_batch` computed `rows / mm_workers` BEFORE
testing `<= 1`. Reverting the guard makes the new test die exactly as documented:

```
=== mm_workers = 0 (documented serial) ===
Floating point exception (core dumped)              RED_RC=136
```

with the guard: `TOTAL_MISMATCH=0`, `WORKERS0 PASS`, and the workers=0 output is
bit-identical to workers=1 across a Q4_K gate, a Q6_K down-projection, a square
projection, a negative worker count (clamps to 0) and the 4-worker pool path.

### The `f64of(mem_load(...))` report: NOT REPRODUCED

`prefill-batching.md` §3 records two `f64of(mem_load(...))` operands in one expression
SIGSEGV'ing at address 0. **It does not reproduce, and it did not when the sites were
put back**: 1920 generated programs (8 index forms x 8 x 5 contexts x 3 pointer kinds
x 2 operators) gave 0 crashes and 0 wrong values; all FIVE reported sites re-inlined
into the real `fc_conv_batch`/`fc_layer_batch` gave `TOTAL_MISMATCH=0`, rc=0.

Mechanically it is safe here: every `IR_CALL` starts with `flush_all()`, which spills
all register-resident vregs and clears the map, and `spill_home(v) =
-(SPILL_BASE + (v+1)*8)` is unique per vreg, so two live operands cannot share a home
slot. `tests/f64of_mem_load_shape_test.quanta` now **pins** the idiom (12 shapes) so a
future change cannot break it silently. That file is a regression pin, not a
red-first test, and its header says so. Full record, including the shape of the
search: `docs/research/lfm2-defects-0.0.243.md` §"NOT REPRODUCED".

### NEW FINDING, not fixed: a parameter named `ref`, used, makes the compiler SIGILL

`fn mismatch(dst, ref, n) { ... mem_load(ref + i*8) ... }` -> `Illegal instruction
(core dumped)`, rc=132, after an error message that names **nothing** (the name and
the line are both garbage because `compile_error(8, ...)` is handed a keyword id where
a source offset belongs). An UNUSED `ref` parameter compiles; the same parameter
crashes when read. Minimal repro, the measured variant table and the located root
cause are in `docs/research/lfm2-defects-0.0.243.md`. Not fixed deliberately: whether
`ref` is a legitimate ownership marker is a language-semantics question, and
validating parameter names changes what the language ACCEPTS rather than fixing a
crash.

---

## 3. ORDERED ITEM 3 — the prompt budget, measured

`tests/lfm2_compact_budget.quanta`, with the in-tree BPE. It reproduces the previous
unit's section split **to the token** (markers 3495/9138/10173; 1115 / 1973 / 344 /
206; whole 3638), which is the cross-check that it is the same prompt.

| | tokens | bytes |
|---|---:|---:|
| current SYSTEM card + labels | 1,115 | 3,495 |
| current LANGUAGE_CARD (a 5.6 KB syntax-manual dump) | 1,973 | 5,643 |
| current neighbour | 344 | 1,035 |
| current spec | 206 | 717 |
| **current whole prompt** | **3,638** | 10,890 |
| **proposed compact card** (replaces head AND card) | **372** | 1,166 |
| **proposed per-attempt = card + spec** | **578** | 1,883 |
| **proposed per-attempt with the card PREFIX-CACHED** | **206** | 717 |

**The low-hundreds target is reached: 206 tokens per attempt**, 17.7x below today,
mostly by *not retrieving a syntax manual* rather than by rewriting prose. The card is
in `tests/lfm2_compact_card.txt`.

At the measured post-fix serial rate (24.16 s/token) 206 tokens is still **83 min**, so
the prompt budget is necessary and not sufficient — prefill needs another order of
magnitude and it is not in the prompt. Both halves are stated in
`docs/research/prompt-budget-compact.md`.

---

## 4. Gate, self-hosting, release

Standalone gate, `bash test_suites/scripts/run_tests.sh` with `VERSION=0.0.243` (so
every stage, including the ones that resolve the compiler from `VERSION`, tests the
tree under test):

```
=== Results: 228/228 pass, 0 fail (incl. 0 compile-fail) [rows: EXPECTED.tsv] ===
  STDLIB: 111/111 GREEN
  gguf-corrupt: 7/7 rejected, real model rc=0
  gguf-corrupt: GREEN
  26 stages GREEN, 0 RED
```

Note on the ORDER of promotion, which cost one extra gate run and is worth recording:
`test_suites/scripts/gguf_corrupt_gate.sh` resolves its compiler as
`compiler/$(cat VERSION)/bin/x86/qc` and **ignores `QC=`**. The first gate run (with
`VERSION` still 0.0.241) therefore compiled the real-model probe with the GOLDEN
compiler against the new `lib/std/gguf.quanta`, and went RED with
`call to undeclared function: dq6` — every other stage GREEN. Bumping `VERSION`
first fixes it. A stage that silently uses a different compiler from the rest of the
gate is a trap.

Self-hosting — 3 generations byte-identical, **distinct = 1**, gen1 built by the
0.0.241 golden:

```
26430066a4e04f61a687ccf6291b61d7  gen1  (built by the 0.0.241 golden, md5 02b15543…)
26430066a4e04f61a687ccf6291b61d7  gen2
26430066a4e04f61a687ccf6291b61d7  gen3
26430066a4e04f61a687ccf6291b61d7  compiler/0.0.243/bin/x86/qc   (the released binary)
```

The fixed point is reached on the FIRST generation, as expected: `dq6` is a new
builtin the compiler's own source does not call, and the A11 fix changes a value
written into the const table, not the code emitted for the compiler's own source.

`bash scripts/verify-release.sh 0.0.243 0.0.241` — **12 passed, 2 failed**. Both
failures are recorded here in full because neither is a gate result about the code:

```
  PASS  no compiler/VERSION (root VERSION is the only pointer)
  FAIL  <NEXT>=0.0.243 is not <VER>=0.0.241 plus one patch
  PASS  compiler/0.0.243/ exists
  PASS  compiler/0.0.243/src/x86/ exists
  PASS  compiler/0.0.243/bin/x86/qc exists and is non-empty (3337976 bytes)
  PASS  compiler/0.0.241/bin/x86/qc exists and is non-empty (3325688 bytes)
  PASS  <VER> src rebuilds BIT-FOR-BIT (md5 02b155430d10661b17645680b4092987) -- qualifies as frozen baseline
  PASS  <NEXT> src/bin lockstep: committed binary (26430066a4e04f61a687ccf6291b61d7) IS the seed-chain fixed point built from 0.0.241 + the committed source
  PASS  self-host fixed point: gen0==gen1==gen2==released binary (md5 26430066a4e04f61a687ccf6291b61d7)
  PASS  compiler/0.0.243/WIP.md exists
  FAIL  official gate returned non-zero (log: /tmp/verify_release_gate.log)
  PASS  Results: 228/228 pass, 0 fail
  PASS  functional stage GREEN
=== 12 passed, 2 failed ===
```

**FAIL 1 — version arithmetic, not a code result.** `0.0.243` is `0.0.241` plus
**two** patches, because `compiler/0.0.242/` exists as another unit's
committed-but-**unpromoted** WIP (its own `WIP.md` says DO NOT PROMOTE and root
`VERSION` stayed 0.0.241). The script's "`<NEXT>` == `<VER>` + one patch" convention
cannot express "the next promotion skips an unpromoted WIP tree". The frozen baseline
is genuinely 0.0.241 and it verified: `0.0.241`'s source rebuilds **bit-for-bit**
(`02b15543…`), and the committed 0.0.243 binary **is** the seed-chain fixed point built
from 0.0.241 + the committed source.

**FAIL 2 — one timing-sensitive stdlib row hit the gate's own 15 s cap.**

```
  FAIL stdlib_rag_search_gate_test.quanta (expected rc=0, got rc=124)
  STDLIB: 110/111 GREEN
  stdlib        : RED
```

`rc=124` is a **TIMEOUT**, and it is the 21 GB sqlite-vec store plus a `fork`+`exec` of
`scripts/rag_search_file.py`, against the gate's 15 s / 1536 MB ceiling, with the
ambient `Hermes` Electron at ~723 % CPU and the gate's own 20 threads on the box.
Re-run on the same binary and the same tree:

```
( ulimit -c 0 -v 8000000; timeout 15 ./scripts/quanta_run.sh /tmp/rag.bin </dev/null )   -> rc=124
( ulimit -c 0 -v 8000000; timeout 60 ./scripts/quanta_run.sh /tmp/rag.bin </dev/null )   -> rc=0  PASS
      rag_search_gate: returned 5 ranked rows -- PASS
```

It is not a regression from this version: the row imports `std/rag` and `std/str`,
**not `std/gguf`**, so the changed library is not in its compile path at all; and in
this unit's own full gate run (below) it passed, `STDLIB: 111/111 GREEN`. The honest
statement is that the row is load-sensitive at its 15 s cap, which is a property of the
row and the box, not of 0.0.243.

---

## 5. Dirty-path audit

Owned and touched by this unit:

| path | state |
|---|---|
| `compiler/0.0.243/**` | NEW — 0.0.241 copied, then `features.quanta`, `emitter.quanta`, `globals.quanta`, `method.quanta` edited; `bin/x86/qc` = the released binary |
| `lib/std/gguf.quanta` | modified — `dequant_q6k` is now the SIMD path; the scalar loop is kept as `dequant_q6k_scalar` |
| `VERSION` | 0.0.241 -> 0.0.243 |
| `tests/const_large_int_test.quanta` | NEW (A11 red-first) |
| `tests/lfm2_mm_workers_zero_test.quanta` | NEW (A12 red-first) |
| `tests/q6k_dequant_simd_test.quanta` | NEW (bit-identity + ns/elem) |
| `tests/f64of_mem_load_shape_test.quanta` | NEW (negative-result pin) |
| `tests/lfm2_compact_budget.quanta`, `tests/lfm2_compact_card.txt` | NEW (item 3) |
| `docs/research/q6k-simd-dequant.md` | NEW |
| `docs/research/lfm2-defects-0.0.243.md` | NEW |
| `docs/research/prompt-budget-compact.md` | NEW |

NOT touched: `test_suites/EXPECTED*.tsv` (owned by another unit),
`docs/plans/bugs.md` (owned by another unit), `compiler/0.0.242/**`,
`tests/lfm2_prefill_bench.conf` (edited for a bench run and restored with
`git checkout --`), and `lib/std/lfm2_forward.quanta` / `lib/std/lfm2_mm.quanta`
(temporarily edited for the two A/B experiments and restored; `git status` shows them
clean).

`tests/const_large_int_test.quanta` is **proposed** as an `EXPECTED.tsv` row
(`const_large_int_test.quanta<TAB>0` — no model, no skip dependency). It is a
red-first row: it does not compile on 0.0.241 at all. The manifest is another unit's,
so it is proposed and not added.

## 6. New A-numbers to assign (a peer owns `docs/plans/bugs.md`)

| A# | defect | state |
|---|---|---|
| **A11** | an integer `const` >= 2^60 was decoded as an enum-variant mark -> **compiler SIGSEGV** | FIXED, red-first (`tests/const_large_int_test.quanta`) |
| **A12** | `mm_workers = 0` (the documented serial setting) divided before the `<= 1` guard -> **SIGFPE** in `mm_matmul` and `mm_embed_logits_batch` | FIXED in `c77d06db`, pinned (`tests/lfm2_mm_workers_zero_test.quanta`) |
| **A13** | a parameter named `ref`, when READ, reports "reserved type keyword" with an **empty name and a garbage line**, and in some shapes makes the compiler exit with **SIGILL (rc=132)` instead of a diagnostic | **OPEN** — minimal repro + variant table + located root cause recorded, not fixed |
| **A14** | the two other const-use sites (`method.quanta` ~1899, ~2068) still emit `IR_CONST` with the raw `bvmark()` value for a non-kind-1/2 const, so a bare enum variant reaching them yields a huge integer instead of the unit variant | **OPEN** — pre-existing, unchanged by A11's fix, noted for a follow-up |
| — | `f64of(mem_load(...))` x2 in one expression -> SIGSEGV at address 0 | **NOT REPRODUCED** (1920 shapes + all five sites re-inlined); `tests/f64of_mem_load_shape_test.quanta` pins the correct behaviour |
