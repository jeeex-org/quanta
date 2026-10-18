# Phase 2, commit 1 — the twin-width fix, and the new fair baseline

Phase 2 of the arithmetic-codegen campaign. This is the **baseline commit**: no
compiler change. It fixes the comparison itself before any codegen lever is
measured against it.

- Repo `/opt/tali/quanta`, `VERSION` **0.0.248**, HEAD `51da429a`.
- Instrument of record: `scripts/bench_instr.sh` (load-independent). Wall clock
  from `scripts/bench.sh` is labelled **WEAK** below — the provenance run was at
  load 19.7-27.0, and this box swings +-17 % on rows that emit byte-identical
  code.
- Raw artefacts for this commit: `phase2-baseline-before.tsv` /
  `phase2-baseline-after.tsv` (the `bench_instr.sh` TSVs either side of the
  change) and `phase2-bench-after.txt` (the `bench.sh` timing run).

Every number below is **MEASURED** in this session with the command given.

---

## 1. What was wrong (audit §3c, re-verified before acting)

21 of the 30 looped C twins declared their loop counters `int` while every
Quanta twin's `let i = 0` is **i64**. A 32-bit counter is exactly what licenses
gcc's 8-wide `vpaddd`/`vpmuldq` at `-O2`, and the 64-bit equivalent (`vpmullq`)
is AVX-512-only, so a `long` twin cannot vectorise the multiply at all on this
CPU. Those rows were therefore comparing *scalar i64 codegen* against
*8-lane i32 SIMD*, and the ratio flattered gcc.

MEASURED, before the fix: `arith`'s C twin `main` loop is 27 instructions of
`vpaddd`/`vpmuldq`/`vpblendd` on `%ymm` — 8 `int` lanes per pass where Quanta
does one 64-bit iteration.

## 2. The fix (mechanical, one token per loop header, 43 lines in 21 files)

All loop counters in the C twins are now `long`, matching Quanta's i64:

```
for (int i|j|qi|bi|outer = ...)   ->   for (long i|j|qi|bi|outer = ...)
```

43 replacements across the 21 files named in the audit
(`arith big_array div_const fib fileio float heavy_div heavy_div2 heavy_float
heavy_float2 heavy_int heavy_int2 heavy_mem heavy_recursion match mem mem_ops
q4k q4k_heavy q4k_matmul recursion`), plus the inner counters (`j`, `qi`, `bi`)
in the same files, because Quanta's inner counters are i64 too.

```bash
for f in benchmarks/*.c; do sed -i -E 's/for \(int (i|j|qi|bi|outer)( =| )/for (long \1\2/g' "$f"; done
grep -n "for (int" benchmarks/*.c    # -> no matches
```

## 3. Verification — the comparison changed, the programs did not

1. **Q-side codegen is untouched, proven by column diff.** Every `q_*` column of
   `bench_instr.sh`'s TSV is **byte-identical on all 38 rows** before vs after
   (`q_instr, q_loop, q_frame, q_mem, q_calls, q_text, q_brs, q_hst, q_hld,
   q_lst, q_lld`). The change is confined to the C side:
   **12 of 38 C twins changed codegen**, 26 unchanged.
2. **Every output still matches.** `bash scripts/bench.sh` (0.0.248 qc) prints
   the structural guard:

   ```
   # OK: every row compiled and every C twin kept its loop.
   ```

   with **0** `MISMATCH`, 0 `TWIN_FOLDED`, 0 compile failures. No C twin's
   output moved when its counter widened — the bounds in these loops cannot
   overflow i32, so the width change is value-preserving by construction and by
   measurement.

## 4. What de-vectorised, measured C-side

`c_instr` / `c_loop` (whole `main` / hot-loop body), `int` -> `long`:

| case | c_instr | c_loop |
|---|---|---|
| arith | 56 -> **34** | 27 -> **20** |
| big_array | 64 -> **50** | 11 -> **7** |
| div_const | 49 -> **30** | 23 -> **15** |
| fileio | 143 -> 163 | 50 -> 45 |
| float | 21 -> 24 | 8 -> 8 |
| heavy_div | 37 -> **19** | 13 -> **7** |
| heavy_div2 | 37 -> **19** | 13 -> **7** |
| heavy_int | 43 -> **19** | 17 -> **7** |
| heavy_int2 | 43 -> **19** | 17 -> **7** |
| heavy_mem | 45 -> **40** | 10 -> **6** |
| mem | 123 -> 146 | 33 -> 45 |
| mem_ops | 47 -> **41** | 11 -> **7** |

The 8-wide **int32** lane forms (`vpaddd`, `vpmuldq`, `vpblendd`) are gone from
every twin. `mem`/`fileio`/`float` grow slightly: with an i64 counter gcc loses
the i32-lane vector form and its replacement (scalar i64, or a 4-wide i64 form)
is larger in text. That is the honest i64 code, not a regression in the twin.

**Residual SIMD, and it is legitimate.** 9 twins still contain `%ymm`
instructions after the fix: `big_array, fileio, heavy_mem, heavy_recursion,
mem, mem_ops, q4k, q4k_heavy, q4k_matmul`. Disassembled, these are **4-wide
i64-lane** forms — `vpaddq`, `vpsllq`, `vpsubq`, `vpbroadcastq` — i.e. the
8 x i64 equivalent of what Quanta's scalar code does, which gcc is entitled to
on a width-fair twin. The unfair part (8 x i32 lanes for a 64-bit computation)
is what was removed. The 9 rows are tagged in the table below so no reader
mistakes the residual, legitimate SIMD for the old unfairness.

## 5. The new fair baseline

`q_loop` = Quanta hot-loop body; `che= c_loop` = C hot-loop body; "home-ops"
= loop-restricted `q_lst + q_lld` (frame-relative stores+loads inside the loop
body) and "share" = that over `q_loop`. Wall clock is **WEAK** (load 19.7-27.0),
quoted only to show the shape.

| case | q_loop | c_loop | home-ops | share | wall Q ms | wall C ms | ratio | note |
|---|---|---|---|---|---|---|---|---|
| arith | 98 | 20 | 40 | 40.8% | 217 | 48 | 4.52x | |
| big_array | 59 | 7 | 29 | 49.2% | 10 | 10 | 1.00x | residual i64-lane SIMD |
| closure_call | 47 | 7 | 24 | 51.1% | 17 | 10 | 1.70x | |
| closure_capture | 47 | 8 | 24 | 51.1% | 19 | 11 | 1.73x | |
| div_const | 84 | 15 | 44 | 52.4% | 103 | 24 | 4.29x | |
| enum | 0 | 0 | - | n/a | 8 | 8 | 1.00x | **NO_LOOP both sides** |
| fib | 10 | 5 | 0 | 0.0% | 9 | 9 | 1.00x | |
| fib_recursive | 10 | 0 | 0 | 0.0% | 25 | 9 | 2.78x | **EXCLUDE: c_loop=0, fold guard skipped** |
| file_io | 10 | 8 | 0 | 0.0% | 8 | 9 | 0.89x | |
| fileio | 101 | 45 | 55 | 54.5% | 91 | 31 | 2.94x | residual i64-lane SIMD |
| float | 127 | 8 | 74 | 58.3% | 119 | 23 | 5.17x | |
| float_ops | 10 | 0 | 0 | 0.0% | 8 | 9 | 0.89x | **EXCLUDE: gcc constant-folded; fold guard skipped** |
| fnptr_indirect | 76 | 11 | 41 | 53.9% | 27 | 12 | 2.25x | |
| generic_call | 46 | 8 | 27 | 58.7% | 23 | 10 | 2.30x | |
| heavy_div | 52 | 7 | 26 | 50.0% | 67 | 16 | 4.19x | |
| heavy_div2 | 52 | 7 | 26 | 50.0% | 622 | 87 | 7.15x | |
| heavy_float | 65 | 6 | 35 | 53.8% | 91 | 15 | 6.07x | |
| heavy_float2 | 65 | 6 | 35 | 53.8% | 435 | 54 | 8.06x | |
| heavy_int | 65 | 7 | 28 | 43.1% | 352 | 47 | 7.49x | |
| heavy_int2 | 65 | 7 | 28 | 43.1% | 1432 | 147 | 9.74x | |
| heavy_mem | 57 | 6 | 28 | 49.1% | 27 | 15 | 1.80x | residual i64-lane SIMD |
| heavy_recursion | 43 | 15 | 22 | 51.2% | 12 | 8 | 1.50x | residual i64-lane SIMD |
| higher_order | 48 | 7 | 27 | 56.2% | 22 | 9 | 2.44x | |
| int_ops | 10 | 0 | 0 | 0.0% | 8 | 7 | 1.14x | **EXCLUDE: c_loop=0, fold guard skipped** |
| loop_sum | 38 | 8 | 20 | 52.6% | 13 | 9 | 1.44x | |
| match | 148 | 13 | 49 | 33.1% | 8 | 10 | 0.80x | |
| mem | 59 | 45 | 29 | 49.2% | 22 | 11 | 2.00x | residual i64-lane SIMD |
| mem_ops | 59 | 7 | 29 | 49.2% | 9 | 9 | 1.00x | residual i64-lane SIMD |
| mutual_recursion | 73 | 10 | 37 | 50.7% | 519 | 76 | 6.83x | |
| nested_calls | 10 | 0 | 0 | 0.0% | 7 | 8 | 0.88x | **EXCLUDE: c_loop=0, fold guard skipped** |
| params8 | 81 | 6 | 44 | 54.3% | 29 | 9 | 3.22x | |
| q4k | 62 | 5 | 30 | 48.4% | 10 | 9 | 1.11x | residual i64-lane SIMD |
| q4k_heavy | 62 | 5 | 30 | 48.4% | 23 | 10 | 2.30x | residual i64-lane SIMD |
| q4k_matmul | 55 | 20 | 26 | 47.3% | 8 | 9 | 0.89x | residual i64-lane SIMD |
| recursion | 43 | 11 | 22 | 51.2% | 8 | 8 | 1.00x | |
| regpressure | 310 | 9 | 135 | 43.5% | 82 | 15 | 5.47x | **EXCLUDE: gcc algebraically collapsed all 16 temps** |
| string | 0 | 0 | - | n/a | 9 | 7 | 1.29x | **NO_LOOP both sides** |
| struct | 10 | 0 | 0 | 0.0% | 7 | 9 | 0.78x | **EXCLUDE: c_loop=0, fold guard skipped** |

**The headline does not move: the loop-restricted home-op share of a Quanta hot
loop is 33.1-58.7 %, median 50.8 %, against 0.0 % in every C twin.** 38 rows:
not one C twin performs a single frame-relative load or store inside its hot
loop. The marshalling share the audit measured on 0.0.247 survives the fair
baseline intact, which is the point of doing this commit first.

### The rows that must never be quoted

- **Constant-folded C twin:** `float_ops` (gcc computes `2/3` at compile time —
  `movabs`, no arithmetic). Its 0.89x is fictional.
- **Algebraically collapsed C twin:** `regpressure` (gcc reduces 16 affine temps
  to 9 instructions of `lea` recurrence). Its 5.47x must never be quoted as a
  codegen gap; it is still useful as the strongest evidence of the *shape* of
  the defect (33 source adds -> 33 adds + 101 stores + 33 loads + 70 movs + 66
  overflow-check instructions before F1/F2).
- **No loop on either side, yet a ratio is printed:** `enum`, `string`
  (`q_loop == c_loop == 0`) and `fib_recursive`, `float_ops`, `int_ops`,
  `nested_calls`, `struct` (`c_loop == 0` while `q_loop == 10`). These 7 rows are
  the fold-guard hole documented in the audit: `scripts/bench.sh:85` only runs
  the `TWIN_FOLDED` check when the C source matches `\b(for|while)\b`, so a
  loop-free C twin is never tested for having had its loop deleted — and a
  loop-free Quanta `main` still prints a "loop ratio".

## 6. Recommendation filed for the owner of `scripts/` (not edited here)

`scripts/bench.sh` is outside this campaign's write scope, so the hole is
recorded rather than patched:

1. Run the fold/jump guard **unconditionally**, and report `NO_LOOP` (not a
   ratio) when the C `main` has no backward branch at all.
2. Add a `TWIN_VECTORISED` report when the C `main` contains `%ymm` — a
   vectorised baseline is as fictional as a folded one, and after this commit
   the honest label is narrower: only the 8-wide **i32** forms are unfair, so
   the check should look for `vpaddd|vpmuldq|vpblendd|vpbroadcastd`, not for
   `%ymm` in general.
3. Best-of-15 resolution floor is already handled; keep it.

## 7. State handed to the codegen levers

Nothing in the compiler changed in this commit. The levers (F1 `adistinct`
first, then F2 dead-store elimination, F3 comparison-result mapping, F4
xmm-resident FP after the A32 frame fix, F5 opt-in FMA, F6 constant-multiply
lowering, F7 LICM, F8 constant shift-range fold) are measured against **this**
table. Every ratio above is WEAK (wall clock) or a loop-body instruction count;
the load-independent `q_*` columns in `phase2-baseline-after.tsv` are the
instrument that decides whether a lever won.
