# benchmarks/ — Quanta vs gcc -O2

**Run:** `bash scripts/bench.sh` — `--md` for a markdown table, `--runs N` for more repetitions.
Both sides are compiled fresh each run and executed through `scripts/qcrun.sh` (hard memory cap, nice,
timeout), alternating, best-of-N. Current VERSION: **0.0.247** (the tables below are
0.0.237/0.0.238 history; the current baseline is table 4 and table 5).

**Load-independent metrics:** `bash scripts/bench_instr.sh <qc> [--only a,b] [--fn name] [--tsv FILE]`
compiles every Quanta twin with `--emit-obj` (which carries a symbol table) and every C twin with
`gcc -O2`, then reports per function: instruction count, **hot-loop body size**, **frame bytes** and
**frame-relative memory operations**. On a throttled, contended box this is the only instrument that
resolves a 5 % codegen change — see table 5 and §"The metric that can actually see a codegen change".

**A/B between two compilers:** `bash scripts/bench_ab.sh <qcA> <qcB> [--runs N]` compiles every case
with BOTH compilers and runs the two *Quanta* binaries interleaved. It removes the gcc denominator and
the cross-run load drift, and it reports whether the two compilers emitted **byte-identical machine
code**. That last column is the cheapest explanation to test and the one most often skipped: if the
binaries are identical, the delta is noise *by definition*.

## Guards

1. **Twin fold check** — if the C source has a loop but the compiled twin has no jump inside `main`, gcc
   deleted the loop; the row is reported `TWIN_FOLDED`. A "0.005 s" C baseline for a 1M-iteration arith
   loop was exactly this artifact and produced a bogus "560x" claim.
2. **Output equality** — both sides must print the same thing (whitespace-insensitive) or the row is
   flagged `MISMATCH`. A fast wrong answer is not a result.
3. **Devirtualisation is invisible to guard 1.** gcc also deletes *calls*: it inlines constant function
   pointers, and `-foptimize-sibling-calls` turns mutual **tail** recursion into a loop. Call-shaped
   twins need `noinline` + `volatile` pointers / an opaque base case.
4. **Resolution floor.** Below **30 ms** the row's ratio is decided by scheduler jitter, not by code:
   the SAME C binary (byte-identical, unchanged source) reported 10 ms in one baseline run and 6 ms in
   the next — a 40 % swing on a program that did not change. Rows under 30 ms therefore keep running up
   to **15** interleaved repetitions and report the best-of, tagged `best-of-15 (<30ms row)`. Above 30 ms
   the spread is a few percent. Until this floor was added, *every* row under ~15 ms was
   noise-dominated, including the ones that looked like wins.
5. **Quarantine marker.** `// mismatch-reason: <text>` attaches a reason to a row that is known to
   diverge; unlike `twin-output: not-comparable` it does NOT silence the equality check, so a quarantined
   row can never be mistaken for parity.

`// known-fail: <reason>` in a case marks a documented defect: the row stays visible and a marker that
still passes is itself a failure, so it cannot outlive its bug.

## Table 1 — baseline, compiler 0.0.237 (the reference for every claim below)

### 0.0.237 — 37 cases, best-of-3 (best-of-15 under 30 ms) (load 10.14, 9.78, 9.79)

| case | Quanta ms | gcc -O2 ms | ratio | note |
|---|---|---|---|---|
| arith | 202 | 14 | 14.43× | best-of-15 (<30ms row) |
| big_array | 9 | 7 | 1.29× | best-of-15 (<30ms row) |
| closure_call | 15 | 8 | 1.88× | best-of-15 (<30ms row) |
| closure_capture | 16 | 9 | 1.78× | best-of-15 (<30ms row) |
| div_const | 120 | 9 | 13.33× | best-of-15 (<30ms row) |
| enum | 7 | 7 | 1.00× | best-of-15 (<30ms row) |
| fib | 6 | 6 | 1.00× | best-of-15 (<30ms row) |
| fib_recursive | 23 | 8 | 2.88× | best-of-15 (<30ms row) |
| file_io | 6 | 6 | 1.00× | best-of-15 (<30ms row) |
| fileio | 90 | 23 | 3.91× | best-of-15 (<30ms row) |
| float | 103 | 18 | 5.72× | best-of-15 (<30ms row) |
| float_ops | 6 | 6 | 1.00× | best-of-15 (<30ms row) |
| fnptr_indirect | 23 | 8 | 2.88× | best-of-15 (<30ms row) |
| generic_call | 19 | 8 | 2.38× | best-of-15 (<30ms row) |
| heavy_div | 75 | 8 | 9.38× | best-of-15 (<30ms row) |
| heavy_div2 | 789 | 24 | 32.88× | best-of-15 (<30ms row) |
| heavy_float | 89 | 14 | 6.36× | best-of-15 (<30ms row) |
| heavy_float2 | 493 | 42 | 11.74× |  |
| heavy_int | 417 | 19 | 21.95× | best-of-15 (<30ms row) |
| heavy_int2 | 1881 | 53 | 35.49× |  |
| heavy_mem | 23 | 8 | 2.88× | best-of-15 (<30ms row) |
| heavy_recursion | 10 | 7 | 1.43× | best-of-15 (<30ms row) |
| higher_order | 17 | 6 | 2.83× | best-of-15 (<30ms row) |
| int_ops | 6 | 6 | 1.00× | best-of-15 (<30ms row) |
| loop_sum | 10 | 6 | 1.67× | best-of-15 (<30ms row) |
| match | 6 | 6 | 1.00× | best-of-15 (<30ms row) |
| mem | 18 | 7 | 2.57× | best-of-15 (<30ms row) |
| mem_ops | 6 | 6 | 1.00× | best-of-15 (<30ms row) |
| mutual_recursion | 659 | 60 | 10.98× |  |
| nested_calls | 6 | 6 | 1.00× | best-of-15 (<30ms row) |
| params8 | 27 | 7 | 3.86× | best-of-15 (<30ms row) |
| q4k | 8 | 6 | 1.33× | best-of-15 (<30ms row) |
| q4k_heavy | 18 | 6 | 3.00× | best-of-15 (<30ms row) |
| q4k_matmul | 6 | 6 | 1.00× | best-of-15 (<30ms row) |
| recursion | 6 | 6 | 1.00× | best-of-15 (<30ms row) |
| string | 6 | 6 | 1.00× | best-of-15 (<30ms row) |
| struct | 6 | 6 | 1.00× | best-of-15 (<30ms row) |

## Table 2 — with the 0.0.238 constant-division strength reduction

### 0.0.238 — 37 cases, best-of-3 (best-of-15 under 30 ms) (load 11.72, 10.36, 9.99)

| case | Quanta ms | gcc -O2 ms | ratio | note |
|---|---|---|---|---|
| arith | 206 | 14 | 14.71× | best-of-15 (<30ms row) |
| big_array | 8 | 7 | 1.14× | best-of-15 (<30ms row) |
| closure_call | 15 | 8 | 1.88× | best-of-15 (<30ms row) |
| closure_capture | 14 | 8 | 1.75× | best-of-15 (<30ms row) |
| div_const | 110 | 9 | 12.22× | best-of-15 (<30ms row) |
| enum | 5 | 5 | 1.00× | best-of-15 (<30ms row) |
| fib | 6 | 6 | 1.00× | best-of-15 (<30ms row) |
| fib_recursive | 23 | 8 | 2.88× | best-of-15 (<30ms row) |
| file_io | 6 | 6 | 1.00× | best-of-15 (<30ms row) |
| fileio | 82 | 19 | 4.32× | best-of-15 (<30ms row) |
| float | 104 | 17 | 6.12× | best-of-15 (<30ms row) |
| float_ops | 6 | 6 | 1.00× | best-of-15 (<30ms row) |
| fnptr_indirect | 20 | 7 | 2.86× | best-of-15 (<30ms row) |
| generic_call | 20 | 7 | 2.86× | best-of-15 (<30ms row) |
| heavy_div | 74 | 8 | 9.25× | best-of-15 (<30ms row) |
| heavy_div2 | 715 | 21 | 34.05× | best-of-15 (<30ms row) |
| heavy_float | 104 | 14 | 7.43× | best-of-15 (<30ms row) |
| heavy_float2 | 493 | 44 | 11.20× |  |
| heavy_int | 396 | 18 | 22.00× | best-of-15 (<30ms row) |
| heavy_int2 | 1664 | 60 | 27.73× |  |
| heavy_mem | 21 | 8 | 2.62× | best-of-15 (<30ms row) |
| heavy_recursion | 8 | 5 | 1.60× | best-of-15 (<30ms row) |
| higher_order | 20 | 7 | 2.86× | best-of-15 (<30ms row) |
| int_ops | 6 | 6 | 1.00× | best-of-15 (<30ms row) |
| loop_sum | 9 | 5 | 1.80× | best-of-15 (<30ms row) |
| match | 6 | 7 | 0.86× | best-of-15 (<30ms row) |
| mem | 20 | 7 | 2.86× | best-of-15 (<30ms row) |
| mem_ops | 5 | 6 | 0.83× | best-of-15 (<30ms row) |
| mutual_recursion | 605 | 63 | 9.60× |  |
| nested_calls | 6 | 6 | 1.00× | best-of-15 (<30ms row) |
| params8 | 25 | 6 | 4.17× | best-of-15 (<30ms row) |
| q4k | 8 | 8 | 1.00× | best-of-15 (<30ms row) |
| q4k_heavy | 22 | 8 | 2.75× | best-of-15 (<30ms row) |
| q4k_matmul | 7 | 7 | 1.00× | best-of-15 (<30ms row) |
| recursion | 5 | 5 | 1.00× | best-of-15 (<30ms row) |
| string | 5 | 6 | 0.83× | best-of-15 (<30ms row) |
| struct | 5 | 5 | 1.00× | best-of-15 (<30ms row) |

## Table 3 — the noise-free A/B (SAME source, both Quanta compilers, 15 runs interleaved)

This is the table to read for "did the codegen change help?" — the gcc denominator is gone and the two
binaries are alternated inside one loop. `d_best`/`d_med` are B_best/A_best and B_med/A_med.

| case | A 0.0.237 best | B 0.0.238 best | A med | B med | d_best | d_med | machine code |
|---|---|---|---|---|---|---|---|
| arith | 199 | 192 | 254 | 229 | -3.5% | -9.8% | differs |
| big_array | 7 | 7 | 10 | 9 | +0.0% | -10.0% | differs |
| closure_call | 12 | 12 | 18 | 17 | +0.0% | -5.6% | IDENTICAL |
| closure_capture | 15 | 13 | 18 | 17 | -13.3% | -5.6% | IDENTICAL |
| div_const | 127 | 114 | 148 | 142 | -10.2% | -4.1% | differs |
| enum | 5 | 5 | 8 | 7 | +0.0% | -12.5% | IDENTICAL |
| fib | 7 | 7 | 8 | 8 | +0.0% | +0.0% | IDENTICAL |
| fib_recursive | 23 | 23 | 25 | 28 | +0.0% | +12.0% | IDENTICAL |
| file_io | 4 | 4 | 7 | 7 | +0.0% | +0.0% | differs |
| fileio | 90 | 87 | 102 | 99 | -3.3% | -2.9% | differs |
| float | 100 | 99 | 136 | 117 | -1.0% | -14.0% | IDENTICAL |
| float_ops | 6 | 6 | 8 | 8 | +0.0% | +0.0% | IDENTICAL |
| fnptr_indirect | 24 | 23 | 27 | 26 | -4.2% | -3.7% | IDENTICAL |
| generic_call | 20 | 20 | 24 | 23 | +0.0% | -4.2% | IDENTICAL |
| heavy_div | 73 | 70 | 88 | 76 | -4.1% | -13.6% | differs |
| heavy_div2 | 686 | 672 | 852 | 724 | -2.0% | -15.0% | differs |
| heavy_float | 91 | 99 | 111 | 118 | +8.8% | +6.3% | IDENTICAL |
| heavy_float2 | 471 | 469 | 518 | 522 | -0.4% | +0.8% | IDENTICAL |
| heavy_int | 433 | 380 | 481 | 420 | -12.2% | -12.7% | differs |
| heavy_int2 | 1622 | 1503 | 1919 | 1666 | -7.3% | -13.2% | differs |
| heavy_mem | 22 | 21 | 27 | 25 | -4.5% | -7.4% | IDENTICAL |
| heavy_recursion | 10 | 11 | 12 | 13 | +10.0% | +8.3% | IDENTICAL |
| higher_order | 19 | 19 | 24 | 24 | +0.0% | +0.0% | IDENTICAL |
| int_ops | 6 | 5 | 8 | 8 | -16.7% | +0.0% | IDENTICAL |
| loop_sum | 11 | 10 | 13 | 13 | -9.1% | +0.0% | IDENTICAL |
| match | 6 | 6 | 8 | 7 | +0.0% | -12.5% | IDENTICAL |
| mem | 21 | 20 | 27 | 26 | -4.8% | -3.7% | IDENTICAL |
| mem_ops | 6 | 7 | 8 | 8 | +16.7% | +0.0% | IDENTICAL |
| mutual_recursion | 619 | 601 | 717 | 711 | -2.9% | -0.8% | IDENTICAL |
| nested_calls | 6 | 6 | 8 | 7 | +0.0% | -12.5% | IDENTICAL |
| params8 | 26 | 24 | 31 | 30 | -7.7% | -3.2% | IDENTICAL |
| q4k | 9 | 8 | 11 | 10 | -11.1% | -9.1% | differs |
| q4k_heavy | 22 | 22 | 27 | 26 | +0.0% | -3.7% | differs |
| q4k_matmul | 6 | 6 | 7 | 7 | +0.0% | +0.0% | differs |
| recursion | 6 | 6 | 7 | 8 | +0.0% | +14.3% | IDENTICAL |
| string | 6 | 6 | 7 | 7 | +0.0% | +0.0% | IDENTICAL |
| struct | 6 | 6 | 9 | 8 | +0.0% | -11.1% | IDENTICAL |

### Reading table 3

**25 of 37 cases produce BYTE-IDENTICAL machine code on both compilers.** For those, any timing or ratio
difference in tables 1/2 is noise: the swings in table 3 reach ±17 % (`mem_ops` +16.7 %, `recursion`
+14.3 %, `fib_recursive` +12.0 %, `struct` −11.1 %) on code that did not change by a single byte.

**12 cases changed code, and every one of them is neutral-to-faster:**

| case | mechanism | d_best | d_med |
|---|---|---|---|
| arith | ÷3 magic, %5 magic | -3.5% | -9.8% |
| big_array | ÷ const | +0.0% | -10.0% |
| div_const | ÷128,÷64,÷32 → sar (was sar+idiv) | -10.2% | -4.1% |
| file_io | ÷ const | +0.0% | +0.0% |
| fileio | ÷ const | -3.3% | -2.9% |
| heavy_div | ÷128 → sar | -4.1% | -13.6% |
| heavy_div2 | ÷128 → sar | -2.0% | -15.0% |
| heavy_int | ÷3 magic | -12.2% | -12.7% |
| heavy_int2 | ÷3 magic | -7.3% | -13.2% |
| q4k | ÷128,÷16,÷2 → sar/and | -11.1% | -9.1% |
| q4k_heavy | ÷ const | +0.0% | -3.7% |
| q4k_matmul | ÷ const | +0.0% | +0.0% |

No changed-code case is slower on either statistic. The largest wins are `heavy_int` (−12.2 %),
`div_const` (−10.2 %) and `heavy_int2` (−7.3 %) best-of-15.

### The payoff is small, and that REFUTES the recorded premise

`docs/plans/performance.md` recorded (on 0.0.233) that the 6.8-32.3× arithmetic-loop cluster was caused
by `idiv` for constant division, and predicted those rows would "move toward ≤3×" once strength
reduction landed. Measured on 0.0.238 the ratios barely move: `heavy_int2` 35.5→27.7, `div_const`
13.3→12.2, `arith` 14.4→14.7, `heavy_int` 22.0→22.0. Removing essentially every hot-loop `idiv` (and
the dead `sar`-then-`idiv` double work) buys 0-12 %, not multiples.

So `idiv` was **not** the dominant cost. What is left is the per-operation spill/reload traffic that the
same document measures as `work()` = 254 instructions vs gcc's 9 — the A4 / next-use-eviction lever
(1104-byte frames, one home slot per vreg). That is where the remaining gap lives.

## Table 4 — load-independent baseline at 0.0.247, and the root cause re-measured

Wall-clock table 5 is load-sensitive; **this is the instrument of record** for codegen work. Measured
2026-10-18, `scripts/bench_instr.sh ./compiler/0.0.247/bin/x86/qc`, governor `powersave`, load 17.4-18.9
(`Hermes` at 946 %). Full raw output: `docs/research/suite-instr-0.0.247.txt` / `.tsv`; per-case hot-loop
instruction census: `docs/research/hotloop-census-0.0.247.txt`; full defect write-up and fix designs:
`docs/research/arithmetic-codegen-defects-0.0.247.md`.

**All 38 cases compile. No COMPILE_FAIL, no MISMATCH, no TWIN_FOLDED.**

| case | q_loop | c_loop | ratio | q home ops in loop | C twin vectorised? |
|---|---:|---:|---:|---:|---|
| regpressure | 310 | 9 | 34.44 | 43.2 % | no — **algebraically collapsed** by gcc |
| float | 127 | 8 | **15.88** | 57.5 % | no |
| params8 | 81 | 6 | 13.50 | 53.1 % | no |
| q4k | 62 | 5 | 12.40 | 46.8 % | yes |
| match | 148 | 13 | 11.38 | 32.4 % | no |
| heavy_float / heavy_float2 | 65 | 6 | **10.83** | 52.3 % | no |
| fnptr_indirect | 76 | 11 | 6.91 | 52.6 % | no |
| higher_order | 48 | 7 | 6.86 | 54.2 % | no |
| closure_call | 47 | 7 | 6.71 | 48.9 % | no |
| closure_capture | 47 | 8 | 5.88 | 48.9 % | no |
| generic_call | 46 | 8 | 5.75 | 56.5 % | no |
| heavy_mem | 57 | 10 | 5.70 | 47.4 % | yes |
| big_array / mem_ops | 59 | 11 | 5.36 | 47.5 % | yes |
| loop_sum | 38 | 8 | 4.75 | 50.0 % | no |
| heavy_div / heavy_div2 | 52 | 13 | 4.00 | 48.1 % | yes |
| recursion | 43 | 11 | 3.91 | 48.8 % | no |
| heavy_int / heavy_int2 | 65 | 17 | 3.82 | 41.5 % | yes |
| div_const | 84 | 23 | 3.65 | 51.2 % | **yes** |
| arith | 98 | 27 | 3.63 | 39.8 % | **yes** |
| heavy_recursion | 43 | 15 | 2.87 | 48.8 % | yes |
| q4k_matmul | 55 | 20 | 2.75 | 45.5 % | yes |
| fileio | 101 | 50 | 2.02 | 53.5 % | yes |
| fib | 10 | 5 | 2.00 | 0 % | no |
| mem | 59 | 33 | 1.79 | 47.5 % | yes |
| file_io | 10 | 8 | 1.25 | 0 % | no |
| enum, string | — | — | no loop in `main` | — | — |
| fib_recursive, float_ops, int_ops, nested_calls, struct | 10 | 0 | **not a ratio** | 0 % | no loop on either side |

### Two reading rules, both measured

1. **15 of 38 C twins are auto-vectorised by gcc at `-O2`** (arith, big_array, div_const, fileio,
   heavy_div, heavy_div2, heavy_int, heavy_int2, heavy_mem, heavy_recursion, mem, mem_ops, q4k,
   q4k_heavy, q4k_matmul). `arith`'s C loop is 24 of its 27 instructions of `vpaddd`/`vpmuldq`/
   `vpblendd` on `%ymm` — gcc does **8 `int` lanes per loop pass** where Quanta does one. So `arith`
   3.63× is (scalar codegen) × (SIMD), not a scalar-codegen ratio. **`float` and `heavy_float` are the
   honest scalar arithmetic cases** — both sides scalar, and the two worst ones.
2. **`float_ops`, `int_ops`, `enum`, `struct`, `nested_calls`, `fib_recursive` are loop-free on both
   sides** (8 C twins contain no `for`/`while`: also `file_io`, `string`). `float_ops`'s C twin is
   constant-folded (`movabs $0x3fe5555555555555`), so it does no arithmetic while Quanta emits 402
   instructions of call sequences — yet the row prints a ratio, because guard 1 is skipped for a C
   source with no `for`/`while`. Not a deleted loop: there was never a loop.
3. **The twins are not the same width, and that is what licenses the vectorisation.** 21 of the 30
   looped C twins use `for (int i = …)` against a Quanta `let i = 0` that is **i64** — and `int i` is
   exactly what lets gcc vectorise 8-wide (`vpmullq`, the 64-bit multiply, is AVX-512-only, so a
   `long i` twin cannot vectorise the multiply on this CPU at all). All 15 vectorised rows are `int i`
   rows. Outputs still agree (no overflow at these bounds, e.g. `20000000*7 = 1.4e8 < INT32_MAX`), so
   no row is miscompiled — but the cost compared is not the same computation and the ratio is flattered
   toward gcc. **Not changed here**: rewriting 21 C twins moves every ratio in these tables and resets
   the phase-2 baseline, so it is sequenced as its own commit. Fix = `for (int i` → `for (long i` in
   21 files; verify with `scripts/bench.sh`. Recommend doing it **before** the phase-2 measurement
   campaign. Detail: `docs/research/arithmetic-codegen-defects-0.0.247.md` §3c.

### Root cause, re-measured: `adistinct()`, not `sdef()`

The paragraph above ("home stores dominate … `sdef()` stores the home slot on every definition
(`emitter.quanta:1102`) and `flush_all()` stores every live value again") was measured on the 0.0.233
compiler and its premise has since been **half-fixed**: 0.0.245 made `sdef()` write back only when the
vreg is unmapped. The store volume did fall 42 %, yet the hot loops still store 21-101 times each — so
the remaining writer is a different one, and it is named by disassembly rather than by reading source:

**`emitter.quanta:473-488`, `adistinct(res, a1, a2)` evicts — that is, stores — BOTH operand vregs on
every binary operation it is called for (30 call sites in `codegen.quanta`).** Because `a1`/`a2` are the
two operand registers just obtained by `aphys()`, the loop stores both live operands to their home slots
before the operation uses them; neither the operation nor the result register clobbers them, and nothing
reads those slots in between. The operands' next use then reloads them. Measured on `benchmark_arith`'s
`i * 7`: stores to both operand homes at `0x14b` and `0x153`, `imul` at `0x15e`, and the reload of `i`
at `0x5a1`/`0x144` — exactly one dead store + one redundant load per operand per operation.

Corroborating measurements (all in `docs/research/arithmetic-codegen-defects-0.0.247.md`):

- **30-67 % of hot-loop home stores are provably dead** (cyclic dead-store walk over the emitted
  listing): arith 15/26, div_const 18/29, heavy_div 10/17, heavy_float 8/21, float 13/43,
  regpressure 68/101.
- **Operation identity does not change the loop cost.** Isolated probes of `s + i*7`, `s + i*8`,
  `s + i*3` and `s + i/8` emit **byte-identical 45-instruction loop bodies** — only the immediate
  differs. One `add` costs what one `mul` costs what one `sar` costs. **The arithmetic is not slow; the
  operand marshalling is.**
- The frame is **per-function** (`codegen.quanta:1369`: `spill_region = 48 + vreg_n*8`, floor 1024) and
  is 75-83 % unused in every normal arithmetic case (deepest slot touched: 192-328 bytes of a 1120-1136
  byte frame). The frame is not a runtime cost and `min_spill` is not a performance lever.
- **`loop_depth` (`codegen.quanta:1433`) is never incremented**, so the `if loop_depth == 0` guard on
  `ovf_trap_emit()` is always true and every integer add/sub/mul/neg pays `jno +0x2; ud2` — 21 % of
  `regpressure`'s loop body, 5 instructions of `arith`'s.
- **The float register allocator is dead code**: `fphys()` (`emitter.quanta:760`) has **zero call
  sites** anywhere in the compiler, so FP values are allocated from the *integer* pool and round-trip
  GPR↔`xmm` on every use (`movq %rax,%xmm0` … `addsd` … `movq %xmm0,%rdx`) — 17 such moves in `float`'s
  loop. Its `fspill_home` writes ~8 KB below `%rbp` while the frame reserves 1120 bytes, so it cannot be
  enabled before the frame formula is fixed.


## Flagged rows — findings, not suite bugs

| row | flag | status |
|---|---|---|
| `closure_capture` | none (repaired) | Was `known-fail: compiler SEGFAULT`. Fixed in 0.0.237 by the A1b block-scoping work; the marker was removed and the C twin repaired — see Defect 3. |
| `q4k`, `q4k_heavy` | none (repaired) | Were `MISMATCH` `-1280` vs `0`. Both were twin derivation errors, not a compiler defect — see Defect 4. |


## Suite repair (0.0.238 prep) — four repaired cases, one found by the equality guard

| case | defect | disposition |
|---|---|---|
| `closure_capture` | carried `known-fail: compiler SEGFAULT`. That defect was fixed in 0.0.237 by the A1b block-scoping work; the marker outlived it, which `bench.sh` flags as a structural failure. | marker removed; verified 0.0.237 compiles + runs and prints `500006500000` = sum(i+7, i=0..999999), matching the twin. |
| `closure_capture` (C) | the C twin did not COMPILE: `struct env` was declared inside the function-pointer parameter list, so it was a prototype-scoped type and `add_y`'s pointer was incompatible. The row was measuring nothing — the stale marker short-circuited it before the C side was reached. | `struct env` declared once, before the typedef. |
| `closure_capture` (C) | with the compile error fixed, gcc devirtualised the struct-held function pointer and folded the loop to its closed form: **zero jumps inside `main`**. Guard 3's exact failure mode. | the closure object is `volatile`, so the pointer is reloaded and the indirect call is real (1 jump, 2 call sites). |
| `heavy_float2` | the Quanta side printed `printi(f64bits("sum="))` — `f64bits` is a float bit-pattern extractor and it was being handed a STRING literal, so the row printed a garbage 10-digit number where the C twin printed the text `sum=`. The arithmetic itself was correct: the f64 bit pattern matched gcc's exactly (`4945415844807707746`). | `print("sum=")`, so the twins agree byte-for-byte. |
| `q4k`, `q4k_heavy` | `MISMATCH` `-1280` vs `0` — Defect 4 below. | C twin corrected; both rows now agree. |

## Defect 4 — `q4k` / `q4k_heavy` MISMATCH: a TWIN divergence, not a compiler defect (RESOLVED)

The rows printed `-1280` (Quanta) against `0` (gcc), identically before and after 0.0.238's codegen
change. There were **two independent causes**, and each one alone flips the value:

1. **Algorithm.** The Quanta twin's `f16_to_q8` computes `base * (1 * (-shift)) * Q8_SCALE / 1024`, a
   plain multiply by the shift amount; the derived C twin said `base * (1 << (-shift)) * Q8_SCALE / 1024`,
   i.e. 2^shift. For the benchmark's own input (`W = 0x97`, `f16 = 38807`, `shift = -10`) that is
   `scale_q8 = 1943*128/1024/10 = 24` on the Quanta side and `1943*128/1024/1024 = 0` on the C side. The
   two sides were not running the same algorithm at all.
2. **Semantics.** Quanta's `/` is FLOOR and `%` takes the divisor's sign; C truncates toward zero. The
   dequant numerator is negative for half the nibbles, and `-3624 / 128` is **-29** in Quanta and **-28**
   in C.

Isolation, computed in Python from each source (not by trusting either program):

| model | y[0] | printed by |
|---|---|---|
| Quanta algorithm (/10) + floor | **-1280** | the Quanta twin |
| Quanta algorithm (/10) + truncation | 0 | — |
| C algorithm (/1024) + floor | 0 | — |
| C algorithm (/1024) + truncation | **0** | the C twin |

**Verdict: Quanta was not miscompiling.** Its `-1280` is exactly what its own source plus its documented
floor semantics produce, and the value was identical before and after the codegen change, so the change
did not cause it. The C twin — the DERIVED artifact — had two derivation errors, and both are now
corrected in `benchmark_q4k.c` / `benchmark_q4k_heavy.c`: it uses the same arithmetic as the program it
mirrors, and a `qdiv()` floor-division helper. The rows now agree exactly (`-1280`). Note this makes the C
side slightly slower (the floor helper), so the `q4k` ratios are not comparable with the pre-repair runs.

## Defect 5 — the `1 * shift` typo in the `q4k` Quanta twins (FILED, not fixed here)

`base * (1 * shift) * Q8_SCALE / 1024` looks like a typo for `1 << shift`: 2^shift is the standard FP16
exponent scale, and `<<` is used throughout `lib/std` (e.g. `lib/std/gguf.quanta`). It is a
**benchmark-data** question, not a compiler one, and it is deliberately left alone here because
correcting it changes the result: with `1 << (-shift)` the scale for the current input becomes 0, i.e. the
payload degenerates to zero and the benchmark stops exercising meaningful values. The correct fix is to
correct the expression AND retune the `W` byte in the same change (an exponent giving `shift >= 0`), which
is a separate piece of benchmark work. Recorded so it cannot be lost.

## Quanta's integer division is FLOOR, not C truncation

```
-7 / 2      quanta: -4   gcc: -3
-7 % 2      quanta: +1   gcc: -1
 7 / -2     quanta: -4   gcc: -3
 7 % -2     quanta: -1   gcc: -1
-7 / -3     quanta:  2   gcc:  2      (signs agree here)
INT64_MIN / 3, % 3      quanta: -3074457345618258603, 1
```

Any twin that divides negative intermediates disagrees with C by design (this was the `q4k` row). It is
also what makes constant-divisor strength reduction simple: a power-of-two divisor is one `sar` and
`% 2^k` is one `and`. Two gate rows pin it — `divmod_floor_semantics_test` (runtime divisors) and
`divmod_const_strength_test` (literal divisors, i.e. the strength-reduction path) — and both are
**red-first**: compiled with the floor corrections removed they return rc 101 / 105 instead of 42.

## Table 5 — 0.0.243 re-baseline (load-independent), and the A4 / next-use-eviction lever in 0.0.244

Tables 1-3 last moved at 0.0.238 and **five levers have landed since** (A1b block scoping, the
float-`const` fix, the per-layer attention-norm fix, the Q6_K SIMD dequant, tooling). Re-baselined on
the 0.0.243 golden, `scripts/bench_instr.sh`, all 38 cases (the 37 below plus `regpressure`).

| case | main instr | loop instr | frame B | home mem-ops | | case | main instr | loop instr | frame B | home mem-ops |
|---|---:|---:|---:|---:|---|---|---:|---:|---:|---:|
| arith | 219 | 111 | 1120 | 79 | | match | 378 | 174 | 1168 | 178 |
| div_const | 206 | 98 | 1120 | 84 | | mem | 495 | 72 | 1136 | 221 |
| heavy_int | 198 | 75 | 1136 | 71 | | mem_ops | 310 | 72 | 1136 | 132 |
| heavy_int2 | 198 | 75 | 1136 | 71 | | mem/others | — | — | 1104-1232 | — |
| heavy_div | 185 | 62 | 1136 | 69 | | q4k | 433 | 74 | 1120 | 197 |
| heavy_div2 | 185 | 62 | 1136 | 69 | | q4k_matmul | 577 | 67 | 1184 | 268 |
| float | 284 | 155 | 1120 | 144 | | string | 86 | 0 | 1152 | 32 |
| heavy_float | 224 | 80 | 1136 | 99 | | struct | 167 | 10 | 1136 | 53 |
| fileio | 482 | 123 | 1184 | 254 | | **regpressure** | **524** | **401** | 1136 | **259** |

gcc's twin, same function, same run: `arith` 56 instructions / 27 in the loop / **0** frame bytes;
`heavy_int` 43 / 17 / 0; `regpressure` 24 / 9 / 8. **gcc's hot loops contain zero frame-relative memory
operands.** Every number above is emitted-code, not executed-code, so it does not move with load.

### A4 / next-use eviction landed in 0.0.244 — and it does not close the gap

`afree()` and `afree_x()` evicted the LAST allocator-map entry (LIFO = the most recently allocated
value). In 0.0.244 the victim is the vreg whose **next use is farthest away**, with a dead vreg the best
victim of all. Measured, all 38 cases:

* **37 of 38 cases emit byte-identical code**; 36 of 39 `bench_ab.sh` rows report `IDENTICAL-CODE`.
* Changed: `file_io`, `params8` and `regpressure` — and `file_io`/`params8` are **exactly the two cases**
  an instrumented build counts evictions in (2 and 3 respectively, over the whole suite).
* `regpressure`: loop body **401 -> 381 instructions (-5.0 %)**, home mem-ops **259 -> 239 (-7.7 %)**.
* **No parity case regressed**; all 12 are `IDENTICAL-CODE` with identical counters.
* **Frame bytes unchanged on every case.**

The lever is correct and it is real. It is also nearly irrelevant to the 6-32x cases, because
**the register pool is never full**: `arith`'s `main` maps at most 3 of the 13 registers at once and
evicts **zero** times; the whole suite evicts 5 times. The compiler's own 427-function self-build evicts
462 times, so the pathology exists — it is just 0.3 % of that build's ~151 000 home accesses.

### The metric that can actually see a codegen change

A/B 0.0.243 vs 0.0.244, best-of-8 interleaved, load 11.35/11.80/11.99, `Hermes` at 400-1300 % CPU.
**36 rows are `IDENTICAL-CODE`, i.e. byte-identical binaries, and their wall-time deltas range from
-12.5 % to +20.0 %** (`fib` -20 %, `string` +20 %, `int_ops`/`match`/`mem_ops`/`struct` +16.7 %). Those
are noise by definition. `regpressure` timed -1.1 % best / -3.8 % median while its loop body lost 5.0 %
of its instructions.

The same binary measured against gcc twice, minutes apart, different load:
`heavy_div2` **32.85x** (load 17.0-20.2) and **21.68x** (load 11.9-12.0); `arith` **17.82x** and
**13.79x**. A 34 % swing on unchanged code. **No wall-clock claim about a codegen change on this box is
defensible** — quote instructions, frame bytes and memory operations, and label anything timed as
derived.

### The real root cause, measured (queued, not fixed here)

Classification of the golden compiler's hot-loop bodies by instruction class:

| case | loop instr | home **loads** | home **stores** | arith/cmp |
|---|---:|---:|---:|---:|
| arith | 111 | 13 | **39** | 39 |
| div_const | 98 | 14 | **43** | 23 |
| heavy_int | 75 | 9 | **28** | 23 |
| mem | 72 | 9 | **32** | 17 |
| fileio | 123 | 21 | **55** | 23 |
| float | 155 | 30 | **71** | 8 |
| match | 174 | 15 | **59** | 35 |

**Home stores dominate every case** — 28-71 per loop body, more than the arithmetic itself, against 8-30
loads and zero on the C side. `sdef()` stores the home slot on every definition
(`emitter.quanta:1102`) and `flush_all()` stores every live value again at every block boundary and every
`IR_CALL`, even when the value is consumed in the same block and the store is never read. **The next
lever is home-store elimination / write-back-on-demand**, with the obstacle (direct `spill_home()`
readers that rely on "home is always current") and a first measurable step named in
`docs/research/a4-next-use-eviction-measurements.md` §9.

## History

- **0.0.244 — A4 / next-use eviction** (`compiler/0.0.244/`). `afree()`/`afree_x()` victim selection:
  farthest-next-use instead of LIFO, dead values first. **37 of 38 cases emit byte-identical code**;
  the exceptions (`file_io`, `params8`) are the only two the whole suite evicts in. Effect is real but
  aimed at a target that is not there: the 13-register pool never fills on this suite (`arith` peaks at
  3 registers, 0 evictions), and the loop cost is **home stores**, not eviction. Loop body on the new
  `regpressure` row: 401 → 381 instructions, 259 → 239 frame memory ops. Frames unchanged.
  Evidence: `docs/research/a4-next-use-eviction-measurements.md`.
- **0.0.238-0.0.243 — five levers landed without a suite re-baseline.** A1b block scoping (0.0.237),
  the float-`const` fix, the per-layer attention-norm fix, the Q6_K SIMD dequant (0.0.243). Tables 1-3
  above are therefore 0.0.237/0.0.238 history; **table 5 is the current baseline.**
- **0.0.211 — loop flush hoisting.** `flush_all()` ran before every IR operation (38 locations); moved to
  loop entry/exit only → **25×** on integer loops (0.33 s → 0.013 s).
- **0.0.212 — loop register pinning.** Loop-carried vregs pinned to callee-saved registers; marginal.
- **0.0.237 — A1b block scoping** retired the `closure_capture` SEGFAULT that this suite had marked.
- **0.0.238 — constant division/modulo strength reduction.** `/` and `%` by a positive compile-time
  constant no longer emit `idiv`: `d = 2^k` → `sar` / `and`, `d = 1` → copy / zero, other `d ≤ 2^31-1` →
  magic multiply with the floor correction. It also removes a real defect: the previous power-of-two path
  emitted the `sar` and then **fell through** into the idiv sequence, so every constant division paid
  `sar` + `idiv` for the same value. Measured effect: tables 2 and 3 above — 0-12 % on the 12 rows whose
  code changed, no regression anywhere.
- **0.0.212 table (superseded, kept for reference).** Heavy Int 14.8-16.7×, Heavy Float 10.1-10.7×, Arith
  7.9-13.2×, Div Const 15.8-17.2×, Int Ops / Float Ops / Fib near parity.
- **Two claims in that table are known wrong and must not be inherited:** (1) "the register allocator runs
  `aphys()` per operand" — `aphys()` is compile-time machinery; the runtime cost is the spill/reload
  traffic it emits. (2) "div with magic constants (done for pow2)" — not done in the code generator; the
  shift-for-divide fix existed only inside the `q4k` kernels in `lib/std`.

## Coverage notes

- **Register pressure is now covered:** `benchmark_regpressure` (16 live temporaries against the
  13-register pool, definition order opposed to consumption order) is the only row that forces
  evictions, and it is the row that moves under a victim-selection change. Its gate twin is
  `test_suites/codes/regpressure_eviction_test.quanta`.
- **Function shapes** are covered: `closure_call`, `closure_capture`, `fnptr_indirect`, `higher_order`,
  `generic_call`, `params8`, `mutual_recursion`, `heavy_recursion`, `nested_calls`, `recursion`,
  `fib_recursive`.
- Still uncovered: traits/dispatch, arrays and slices beyond simple indexing, string building/comparison,
  match-heavy dispatch, allocation-heavy patterns, struct-heavy mutation in a loop, FFI call cost.
- **Every row under 30 ms is noise-dominated** even with best-of-15 (table 4's `best-of-15 (<30ms row)`
  tag). Quote those rows as "at the resolution floor", never as parity.
