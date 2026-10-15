# Quanta Defect & Performance Report

**Date:** 2026-10-15
**Version:** 0.0.240
**Compiler:** `compiler/0.0.240/bin/x86/qc`

---

## 1. Defect Status Summary

| Defect | Description | Status | Fixed in |
|---|---|---|---|
| **A1** | Capturing closure in loop crashes compiler | ✅ FIXED | 0.0.234 |
| **A1b** | Block bindings never popped (inner `let` clobbers outer) | ✅ FIXED | 0.0.237 |
| **A2** | `print` on f64 emitted bit pattern | ✅ FIXED | 0.0.235 |
| **A2b** | `exit(f64)` silently exits 0 | ✅ FIXED | 0.0.235 |
| **A3** | `gguf_type_size` succeeds for types with no decoder | ✅ STALE | — |
| **A4** | Recursion ceiling ~8,000 frames (1104-byte frame) | 📊 MEASURED | — |
| **A5** | `mem_alloc` clobber in loop | ⚠ LATENT (masked by deferred reuse) | — |
| **A6** | Untyped param used as float → bit pattern | ✅ FIXED | 0.0.236 |
| **A7** | Untyped param used as string → pointer | ✅ FIXED | 0.0.236 |
| **A8** | `SYNTH_CAP` believed dead | ✅ CLOSED (stale report; now enforced) | — |
| **A9** | Native engine dies after ONE threaded forward with rc=0 | ✅ FIXED | 0.0.239 |

**Status:** A1, A1b, A2, A2b, A6, A7 and A9 fixed (7). A3 stale. A8 closed as a stale report. A4 measured, no fix (the frame size is the performance lever). **A5 is latent, not absent.** Defects found after this table was written are in section 6.

---

## 2. Defect Details

### A1 — Capturing closure in loop crashes compiler ✅ FIXED (0.0.234)

**Symptom:** `qc` segfaults (rc=139) on a capturing closure called in a loop.

```quanta
fn main() { let y = 7
let f = |x| { x + y }
let i = 0
while i < 3 { i = i + f(1) }
print(i) }
```

**Root cause:** A shadowed `fi` parameter in `ci_func` produced a store through a wild address. The `fnptr()` cases did `let fi=a0`, which shadowed the `fi` parameter for the rest of the function (block bindings are not popped).

**Fix:** Renamed the two shadowing locals `let fi=a0` → `let ftgt=a0` in the `fnptr()` paths.

**Verified:** Repro compiles and prints 8. 7 of 8 probes that crashed on 0.0.233 now compile and return correct values.

---

### A1b — Block bindings never popped ✅ FIXED (0.0.237)

**Symptom:** An inner `let` in a block rebinds the enclosing name's storage and stays visible after the block.

```quanta
fn f(p) { let a = 1
if a == 1 { let p = 99 }
print(p) }          // prints 99, not the parameter
```

**Root cause:** `parse_block()` pushes/pops only the ownership scope. Local bindings live in the `vars` table with `varc` as the count, appended once per `let`. `vfind()` resolves by scanning newest-first. Nothing truncates `varc` when a block ends.

**Fix:** One-line patch in `parse_block()`: save `varc` at block entry, restore at block exit. 26 sites in 6 files required hoisting.

**Verified:** Gate 222/222. Shadow probe prints 11 where it printed 9977.

---

### A2 — `print` on f64 emitted bit pattern ✅ FIXED (0.0.235)

**Symptom:** `print(fadd(i2f(3), i2f(2)))` printed `4617315517961601024` (5.0's IEEE-754 bits) instead of `5`.

**Fix:** Compile-time refusal. The six handlers that could write a float refuse it, naming both correct routes:
- `print`, `echo`, `println` → `print_f(x)` (decimal) or `f64bits(x)` (exact bits)
- `printi`, `printsp` → same
- `exit` → `exit(f2i(x))`

**Verified:** 28 files in the tree printed a float. All 28 compile with the refusal. 27 verified byte-identical in runtime output against the original code.

---

### A2b — `exit(f64)` silently exits 0 ✅ FIXED (0.0.235)

**Symptom:** `exit(fadd(i2f(2), i2f(3)))` exited 0 instead of 5. The release checklist's smoke test had been passing for the wrong reason.

**Fix:** Same as A2 — compile-time refusal naming `exit(f2i(x))`.

---

### A3 — `gguf_type_size` succeeds for types with no decoder ✅ STALE

**Status:** The dispatch already fails closed. `read_block_f64` starts with `if gguf_dtype_supported(dtype) == 0 { return 0 }`. A dtype with no decoder cannot be decoded into garbage. The residual nit — `gguf_type_size` answering a number for those dtypes instead of -1 — is a consistency wart, not a corruption path.

---

### A4 — Recursion ceiling ~8,000 frames 📊 MEASURED

**Symptom:** Recursion depth ceiling ~8,000 frames.

| Depth survived | Frame |
|---|---|
| Quanta | ~8,000 frames | 1104 bytes |
| C twin (-O0) | ~262,000 frames | ~32 bytes |

**Root cause:** The 33× ratio IS the frame ratio. The depth is fully explained by the frame size, nothing else.

**No separate fix.** The lever is the frame — the eviction / shared-home-slot work in `docs/plans/performance.md`. Every halving of the frame doubles the usable recursion depth.

**Gate guard:** `recursion_depth_test.quanta` recurses to 3,000 (a depth both sides survive). PASSES on 0.0.240 — regression guard, not red-first.

---

### A5 — `mem_alloc` clobber in loop ❌ NOT REPRODUCED

**Status:** One shape tested, not reproduced. `mem_alloc` never pops its freed list, so it bump-allocates and hands out fresh blocks rather than reusing a live one. Runaway growth is the consequence of that design; silent clobbering in this shape is not happening.

**Still needs the original repro before it can be called live or stale.**

---

### A6 — Untyped param used as float ✅ FIXED (0.0.236)

**Symptom:** `reduce(0.5)` returned the right bits only if `qmult` was called earlier in the program.

```quanta
fn qmult(x) -> f64 { let y = x * (2.0/3.14159...) ... }   // x UNTYPED
fn reduce(x) -> f64 { ... let nf = qmult(x) ... }
reduce(0.5)   // wrong unless qmult was called first
```

**Root cause:** A parameter written without `: f64`. The parameter's vreg was never tagged float, so `fopld_rr` took the integer path (`cvtsi2sd`) over an f64 bit pattern.

**Fix:** New pass `scan_call_types()` in `funcscan.quanta`. Infers an untyped parameter's float/string tag from the call argument. Handles non-literal arguments (forwarding a parameter).

**Verified:** A6 repro fixed. A7 repro fixed. Gate 212/212 on 0.0.236.

---

### A7 — Untyped param used as string ✅ FIXED (0.0.236)

**Symptom:** `fn show(s) { print(s) }` printed a pointer (1109393760) instead of text.

**Root cause:** Same as A6 — the parameter slot has no type, so `print` takes the integer path.

**Fix:** Same as A6 — `scan_call_types()` extended to strings.

---

## 3. Performance Gap (measured 0.0.240)

### Full benchmark list (37 twins, min-of-5) - SUPERSEDED, read the caveat

> **Caveat (added on review):** measured min-of-5 with **no load recorded**, GCC column quantised to
> 0.00-0.01 s, so a ratio off a 0.01 s denominator can be wrong by a factor of two. It disagrees with
> the A/B measurement on every large row, pessimistically: `heavy_int` 46x here vs **23x** measured,
> `heavy_int2` 39x vs **27.7x**, `heavy_div2` 40x vs **20.4x**, `arith` >25x vs **13.6x**, `div_const`
> >14x vs **12.2x**. Correct method: `scripts/bench_ab.sh` - two compilers on the same source,
> interleaved, best-of-15, plus a **generated-code identity check**, which showed 25 of 37 rows emit
> byte-identical machine code and still swing +/-17%: a single-run ratio on a sub-10 ms row measures
> the scheduler. Best-of-15 result (0.0.237 vs 0.0.238): 19 improved, 12 worse, 6 flat, **all 12
> changed-code rows neutral-or-faster, no row regressed**. 0.0.239 changed codegen, so this is not a
> 0.0.240 table either. Re-measure on a quiet box before quoting any ratio.

| Benchmark | Quanta | GCC -O2 | Ratio |
|---|---|---|---|
| benchmark_heavy_int | 0.46s | 0.01s | **46×** |
| benchmark_heavy_int2 | 1.17s | 0.03s | **39×** |
| benchmark_heavy_div2 | 0.79s | 0.02s | **40×** |
| benchmark_mutual_recursion | 0.53s | 0.04s | **13×** |
| benchmark_heavy_float2 | 0.57s | 0.04s | **14×** |
| benchmark_float | 0.12s | 0.01s | **12×** |
| benchmark_arith | 0.25s | 0.00s | >25× |
| benchmark_fileio | 0.09s | 0.02s | **4.5×** |
| benchmark_div_const | 0.14s | 0.00s | >14× |
| benchmark_heavy_div | 0.08s | 0.00s | >8× |
| benchmark_heavy_float | 0.10s | 0.00s | >10× |
| benchmark_closure_call | 0.01s | 0.00s | noise |
| benchmark_closure_capture | 0.01s | 0.00s | noise |
| benchmark_fnptr_indirect | 0.02s | 0.00s | noise |
| benchmark_generic_call | 0.01s | 0.00s | noise |
| benchmark_higher_order | 0.01s | 0.00s | noise |
| benchmark_params8 | 0.01s | 0.00s | noise |
| benchmark_fib_recursive | 0.01s | 0.00s | noise |
| benchmark_heavy_mem | 0.01s | 0.00s | noise |
| benchmark_big_array | 0.00s | 0.00s | noise |
| benchmark_enum | 0.00s | 0.00s | noise |
| benchmark_fib | 0.00s | 0.00s | noise |
| benchmark_file_io | 0.00s | 0.00s | noise |
| benchmark_float_ops | 0.00s | 0.00s | noise |
| benchmark_heavy_recursion | 0.00s | 0.00s | noise |
| benchmark_int_ops | 0.00s | 0.00s | noise |
| benchmark_loop_sum | 0.00s | 0.00s | noise |
| benchmark_match | 0.00s | 0.00s | noise |
| benchmark_mem | 0.00s | 0.00s | noise |
| benchmark_mem_ops | 0.00s | 0.00s | noise |
| benchmark_nested_calls | 0.00s | 0.00s | noise |
| benchmark_q4k | 0.00s | 0.00s | noise |
| benchmark_q4k_heavy | 0.00s | 0.00s | noise |
| benchmark_q4k_matmul | 0.00s | 0.00s | noise |
| benchmark_recursion | 0.00s | 0.00s | noise |
| benchmark_string | 0.00s | 0.00s | noise |
| benchmark_struct | 0.00s | 0.00s | noise |

**37 benchmarks total.** 8 measurable, 29 noise-dominated (<30ms). Every row under 30 ms is noise — the real measurement requires `scripts/bench_ab.sh` (best-of-15 interleaved A/B).

**The gap is 4.5–46× on the 8 measurable benchmarks.** The worst cases are integer-heavy loops with constant division.

### Root cause

Per-operation spill/reload traffic. `work()` = 218 instructions vs GCC's 9. The register pool (13 regs) uses LIFO eviction with no next-use information.

### What was tried

| Version | Lever | Result |
|---|---|---|
| 0.0.238 | Constant division strength reduction | 0–12% improvement. `idiv` was NOT the dominant cost. |

### What's next

Next-use eviction policy (phase 3 of `docs/plans/performance.md`). Not started.

---

## 4. Compiler Infrastructure

| Metric | Value |
|---|---|
| Register pool | 13 physical regs (RAX,RCX,RDX,RBX,RSI,RDI,R8-R10,R12-R15) |
| Eviction policy | LIFO (last-in-first-out), no next-use info |
| Frame size | 1104 bytes (`sub $0x450,%rsp`) |
| `-O` flag | Inert (byte-identical binaries) |
| Compile speed | ~2.5 ms/line |
| Gate | **225/225 native** + **108/108 stdlib**, 0 compile-fail, all 24 stages GREEN, exit 0 (verified at HEAD `e0cde330`) |

---

## 5. Files

| File | Purpose |
|---|---|
| `docs/plans/bugs.md` | Defect backlog (all 9 entries) |
| `docs/plans/performance.md` | Performance series plan |
| `docs/research/call-order-f64-defect.md` | A6 investigation (resolved) |
| `docs/research/let-scope-inventory.md` | A1b migration inventory |
| `benchmarks/` | 37 benchmark twins (Quanta + C) |
| `benchmarks/BENCHMARK.md` | Benchmark results tables |

---

## 6. Findings after this table (added on review)

**A5 is latent, not absent.** `IR_FREE = 37` frees an `mem_alloc`-owned binding at scope end
(`globals.quanta:29`, emitted per owned vreg at `features.quanta:24`), so a loop body's allocation IS
freed each iteration. What prevents the next iteration clobbering it is that `mem_alloc` never reuses
a freed block - and the emitter says so as a deliberate deferral: `emitter.quanta:1980`
"(Deferred reuse: mem_alloc left UNCHANGED to keep emitted bytes stable -> fixpoint-safe.)". So the
0.0.235 probe read 111 back because reuse does not exist yet, not because the hazard does not.
Holding an owned pointer past its scope exit is already a use-after-free that the bump allocator
masks; landing the deferred reuse turns it into silent aliasing. `codegen.quanta:2741` already warns
of "double-free -> aliased-block". Allocate-up-front is the correct pattern, not a workaround.

**Defects found after this report was written** (all measured, all in `docs/plans/bugs.md` or the
version WIPs):

- **A9** - per-matvec thread spawn leaked a 1 MiB child stack per call (2329 clones/forward = 2.33 GB);
  ENOMEM on the main thread, `exit(1)` not `exit_group`, so the process reported **rc=0**. Fixed 0.0.239.
- **`lib/std/sampling.quanta`** - the "softmax" was `1+(v-max)` (a one-hot), and `sample_draw`
  compared `cumsum*1000` against an rng in [0,2^31) - never true, always index 0, and token 0 is ten
  newlines. That is where the whitespace output came from. Top-k went from O(n^2) (110,080 ms at
  n=128000) to 60 ms. Fixed 0.0.240.
- **`lib/std/lfm2_chat.quanta`** - `chat_build` wrote a literal backslash-n and a mis-transcribed
  thinking tag; the driver used `bpe_encode` (no special-token matching) and no BOS. With those fixed
  it reproduces llama.cpp's `/tokenize` byte-for-byte (23 ids). Fixed 0.0.240.
- **`lib/std/rag.quanta`** - did not compile at all (`undeclared variable: config` + SIGILL), used a
  non-existent `sqlite3` CLI, and assumed `exec()` returns (it is `execve` and replaces the image).
- **Open:** a top-level `const` with a float initialiser evaluates to 0; `tokenizer_trait.quanta`
  still calls `bpe_encode`; native logits are flatter than the reference (p('The') 0.251 vs 0.847,
  1/10 top ids shared, argmax agrees) with the unchecked Q6_K output projection as prime suspect.

**Native inference measurements (the half this report was missing)**, all measured at 0.0.239/0.240:
decode **0.126 tok/s** at 20 workers (16.20 -> 10.10 s/token at 8 workers, 12.29 -> 7.70 at 20, a
~1.6x gain from routing `dequant_q4k` through SIMD `dq32lo`/`dq32hi`, with the full 128,000-element
logits vector **byte-identical** to before); prefill **5,968 ms per prompt token** (one unbatched
forward per token - the binding constraint for the SI loop); RSS 141-180 MB under a 4 GiB cap;
fixpoint `6f83fe08a7f8819a725fe50c81680ef1`; `verify-release.sh` 14 passed / 0 failed. For scale,
llama-server on a LARGER 7.5B model measured 8.24 tok/s on this CPU: the native path is ~65x off.
