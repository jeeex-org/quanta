# benchmarks/ — Quanta vs gcc -O2

**Run:** `bash scripts/bench.sh` — `--md` for a markdown table, `--runs N` for more repetitions.
Both sides are compiled fresh each run and executed through `scripts/qcrun.sh` (hard memory cap, nice,
timeout), alternating, best-of-N. Current VERSION: **0.0.234**.

**What this suite is:** 37 core-language **performance shapes** — it exists to catch codegen regressions.
It is **not** a feature-coverage matrix; correctness lives in the gate (`test_suites/EXPECTED.tsv`, 819 rows,
plus 20 gate stages) and in `tests/`.

## Guards (all three learned the hard way)

1. **Twin fold check** — if the C source has a loop but the compiled twin has no jump inside `main`, gcc
   deleted the loop; the row is reported `TWIN_FOLDED` instead of a ratio. A "0.005 s" C baseline for a
   1M-iteration arith loop was exactly this artifact and produced a bogus "560x" claim.
2. **Output equality** — both sides must print the same thing (whitespace-insensitive) or the row is flagged
   `MISMATCH`. A fast wrong answer is not a result.
3. **Devirtualisation is invisible to guard 1.** gcc also deletes *calls*: it inlines constant function
   pointers, and `-foptimize-sibling-calls` (on by default) turns mutual **tail** recursion into a loop.
   Call-shaped twins therefore need `noinline` + `volatile` pointers / an opaque base case, and the
   disassembly has to be checked by hand — it changed two numbers below by up to 4x.

The script exits non-zero if a row fails to compile or a twin got folded (currently `exit 0`).
`// known-fail: <reason>` in a case marks a documented defect: the row stays visible, the suite stays green,
and a marker that still passes is itself a failure — so it cannot outlive its bug.

## Baseline — 37 cases, best of 3 (2026-10-13)

| benchmark_arith | 267 ms | 17 ms | 15.71x |  |
| benchmark_big_array | 9 ms | 7 ms | 1.29x |  |
| benchmark_closure_call | 15 ms | 10 ms | 1.50x |  |
| benchmark_closure_capture | - ms | - ms | -x | KNOWN-BROKEN (marker): compiler SEGFAULT — a capturing closure invoked inside a loop crashes qc |
| benchmark_div_const | 151 ms | 10 ms | 15.10x |  |
| benchmark_enum | 9 ms | 7 ms | 1.29x |  |
| benchmark_fib | 8 ms | 8 ms | 1.00x |  |
| benchmark_fib_recursive | 24 ms | 10 ms | 2.40x |  |
| benchmark_file_io | 8 ms | 7 ms | 1.14x |  |
| benchmark_fileio | 88 ms | 30 ms | 2.93x |  |
| benchmark_float | 116 ms | 20 ms | 5.80x |  |
| benchmark_float_ops | 7 ms | 7 ms | 1.00x |  |
| benchmark_fnptr_indirect | 26 ms | 10 ms | 2.60x |  |
| benchmark_generic_call | 21 ms | 11 ms | 1.91x |  |
| benchmark_heavy_div | 88 ms | 11 ms | 8.00x |  |
| benchmark_heavy_div2 | 818 ms | 28 ms | 29.21x |  |
| benchmark_heavy_float | 94 ms | 14 ms | 6.71x |  |
| benchmark_heavy_float2 | 479 ms | 41 ms | 11.68x |  |
| benchmark_heavy_int | 445 ms | 18 ms | 24.72x |  |
| benchmark_heavy_int2 | 1865 ms | 52 ms | 35.87x |  |
| benchmark_heavy_mem | 23 ms | 11 ms | 2.09x |  |
| benchmark_heavy_recursion | 10 ms | 6 ms | 1.67x |  |
| benchmark_higher_order | 21 ms | 9 ms | 2.33x |  |
| benchmark_int_ops | 6 ms | 6 ms | 1.00x |  |
| benchmark_loop_sum | 13 ms | 9 ms | 1.44x |  |
| benchmark_match | 8 ms | 8 ms | 1.00x |  |
| benchmark_mem | 23 ms | 10 ms | 2.30x |  |
| benchmark_mem_ops | 10 ms | 10 ms | 1.00x |  |
| benchmark_mutual_recursion | 754 ms | 63 ms | 11.97x |  |
| benchmark_nested_calls | 6 ms | 7 ms | 0.86x |  |
| benchmark_params8 | 29 ms | 7 ms | 4.14x |  |
| benchmark_q4k | 10 ms | 8 ms | 1.25x | MISMATCH: quanta='-1280' gcc='0' |
| benchmark_q4k_heavy | 22 ms | 9 ms | 2.44x | MISMATCH: quanta='result[0]=-1280' gcc='result[0]=0' |
| benchmark_q4k_matmul | 8 ms | 8 ms | 1.00x |  |
| benchmark_recursion | 8 ms | 5 ms | 1.60x |  |
| benchmark_string | 6 ms | 6 ms | 1.00x |  |
| benchmark_struct | 7 ms | 6 ms | 1.17x |  |


`benchmark_fib` is the **iterative** fib(40); `benchmark_fib_recursive` is recursive fib(30).

**Reading it:** 12 cases sit at 0.86-1.60× (several *faster* than gcc); the arithmetic/division cluster sits at
2.4-32.4×. The gap is **workload-dependent and bimodal** — never quote a single number for "Quanta vs C".

## Flagged rows — findings, not suite bugs

| row | flag | status |
|---|---|---|
| `benchmark_closure_capture` | `KNOWN-BROKEN`: **compiler SEGFAULT** | real defect — 6-line repro in the case header |
| `benchmark_q4k`, `benchmark_q4k_heavy` | `MISMATCH` `-1280` vs `0` | by design: integer division semantics, see below |

### Defect 1 — a capturing closure invoked in a loop crashes the compiler

```
fn main() { let y = 7
 let f = |x| { x + y }
 let i = 0
 while i < 3 { i = i + f(1) }
 print(i) }
```

`qc` segfaults (rc=139). Neither ingredient alone crashes: a closure in a loop without capture runs, and a
capturing closure called *once* runs — which is why the gate's `closure_capture.quanta` passes. Needs a gate
row alongside the fix, per rule #16.

### Defect 2 — no sibling-call (tail-call) elimination

Tail-form mutual recursion: gcc converts it to a loop and ran 40M calls in **15 ms** (~1 cycle/call) while
Quanta kept every frame at **637 ms**. The non-tail form (both sides make real calls) is the honest
comparison: **735 ms vs 75 ms = 9.80x**. Candidate for the optimizer phase.

### Defect 3 — recursion depth ceiling from frame size

Quanta emits a **1104-byte frame** per function (`sub $0x450,%rsp`, one home slot per vreg), so recursion
deeper than roughly **7k** overflows an 8 MB stack (SIGSEGV) where C reaches 200k+. The same
spill-everything defect, seen from the stack side.

### Quanta's integer division is FLOOR, not C truncation

```
-7 / 2      quanta: -4   gcc: -3
-7 % 2      quanta: +1   gcc: -1
```

Any twin that divides negative intermediates disagrees with C *by design* (this is the q4k row). It also
settles the strength-reduction question in `docs/plans/performance.md`: a power-of-two divisor is one `sar`,
modulo by a power of two is an `and`.

## Coverage notes

- **Function shapes were the suite's biggest blind spot** and are now covered: `closure_call`,
  `closure_capture` (known-broken), `fnptr_indirect`, `higher_order`, `generic_call`, `params8`,
  `mutual_recursion`, `heavy_recursion` (misnomer: it calls an *iterative* fib), `nested_calls`, `recursion`,
  `fib_recursive`.
- Still uncovered: traits/dispatch, arrays and slices beyond simple indexing, string building/comparison,
  match-heavy dispatch, allocation-heavy patterns, struct-heavy mutation in a loop, FFI call cost.
- Two historical rows were **invalid** and are fixed: `heavy_recursion` computed `fib(1000)` (~4.3e208 →
  int64 overflow; Quanta's overflow trap fired correctly, gcc wrapped with UB), and `loop_sum`'s twin had its
  loop folded away.

## History

- **0.0.211 — loop flush hoisting.** `flush_all()` ran before every IR operation (38 locations); moved to loop
  entry/exit only → **25×** on integer loops (0.33 s → 0.013 s).
- **0.0.212 — loop register pinning.** Loop-carried vregs pinned to callee-saved registers; marginal further
  gain (~0.011 s → ~0.010 s).
- **0.0.212 table (superseded, kept for reference).** Heavy Int 14.8-16.7×, Heavy Float 10.1-10.7×, Arith
  7.9-13.2×, Div Const 15.8-17.2×, Int Ops / Float Ops / Fib near parity. Its "Next Steps for Parity" list
  (LICM, basic-block scheduling, 4× unrolling, SSA + linear-scan RA, strength reduction) is still sound input
  to ordering. Correctness noted then: `f2i(3.0)`→3, `i2f/fadd/fsub/fmul/fdiv` correct,
  `gguf_tensor_info_test` PASS, self-host 0.0.202→0.0.212 chain verified.
- **Two claims in that table are now known wrong and must not be inherited:**
  1. *"The register allocator runs `aphys()` for every operand … 60M allocator calls vs C's zero."* `aphys()`
     is **compile-time** machinery — it picks registers while emitting. It does not run inside the generated
     loop. The runtime cost is the **spill/reload traffic it emits**: measured `work()` = 254 instructions vs
     gcc's 9, with a store/reload pair per operation.
  2. *"div with magic constants (done for pow2)."* Not done in the code generator: `benchmark_div_const`
     (`i/128*3 + i/64 - i/32`, three power-of-two divides) still measures **14.1×**, explicable only as real
     `idiv`s. The shift-for-divide fix exists **only inside the `q4k` kernels in `lib/std`**.
- **Suite repair (0.0.234 prep).** 30/30 compile again: `benchmark_enum` (variant syntax is now `Color.Green`
  + `match`), `benchmark_int_ops` (`mod` is reserved → variable is `rem`), `benchmark_struct` (struct-typed
  parameter must be annotated: `fn area(r: Rectangle)`). Four float twins cast doubles to `long` (UB →
  INT64_MIN); they now print the f64 **bit pattern**, matching what Quanta's `print` emits, so those rows
  became bitwise checks. `benchmark_loop_sum`'s twin had its loop folded away (fixed with an argc-dependent
  bound). `test_avx2.quanta` — an AVX2 builtin feature test with no twin — moved to
  `tests/test_avx2_builtins.quanta`. `benchmark_fib_recursive` added. The directory is now visible to git
  (`!/benchmarks/` in `.gitignore`); the 29 stale compiled twins were deleted.

## Function coverage vs the gate (context)

The 30 original cases contained only three call-shaped rows (`nested_calls`, `recursion`, `fib_recursive`),
all measuring call/recursion *overhead*. Function **correctness** was never thin — `EXPECTED.tsv` carries ~20
function rows: `closure_basic`/`closure_capture`/`closure_capture_byvalue`/`closure_capture_multi`/
`closure_higher_order`/`closure_multi_param`/`closure_named_fn`/`closure_selfrec_test`/`array_push_closure_mix`,
`fnptr_test`, `func_call_args`, `param8`/`param9`/`param12`, `generics_test`/`generics_typecheck`/
`generics_const_test`, `op_overload_recur`, `external_call`, plus the raw-pointer rows. The gap was
*performance* coverage — and closing it immediately exposed Defect 1 and Defect 2 above.
