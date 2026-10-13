# Bug backlog — fix every defect first, then the speed series

**Order (per instruction):** all bugs, starting at **0.0.234**, and only then the codegen speed series in
`docs/plans/performance.md`. Rationale, stated once: a crash or a silently wrong value invalidates any
measurement taken on top of it — two of the items below are *compiler crashes on valid input*, and one makes
`print` unusable for floats, which is how the perf suite's own twins got written wrongly.

**Every item here was re-verified on 0.0.233 in this session** (repro + observed result). Statuses are
`LIVE`, `STALE` (the document claims broken, measurement says fixed) or `DOC` (documented, repro needs the
original shape). Version numbers are allocated at release time (`cat VERSION` + 1,
`docs/RELEASE_CHECKLIST.md` §9) — the numbering below is intent.

---

## Severity A — crashes and wrong values on valid programs (0.0.234)

### A1 · LIVE · a capturing closure invoked in a loop crashes the compiler

```quanta
fn main() { let y = 7
 let f = |x| { x + y }
 let i = 0
 while i < 3 { i = i + f(1) }
 print(i) }
```

`qc` **segfaults** (rc=139, core dumped). Neither ingredient alone crashes: a closure in a loop without
capture runs fine, and a capturing closure called *once* runs fine — which is exactly why the gate's
`closure_capture.quanta` passes: it calls `f` outside any loop. The loop shape was never covered.

- Repro lives in `benchmarks/benchmark_closure_capture.quanta` (marked `// known-fail:`), so the suite keeps
  the row visible without going red.
- **Triage done (0.0.234, 14 probes, compile-only).** The defect is far wider than "in a loop" and does **not**
  need the closure to be called at all:

  | shape | result |
  |---|---|
  | capture + `while` calling `f` (the original repro) | CRASH |
  | capture **never called** + `while { i = i + 1 }` | CRASH |
  | capture + `if i < 3 { i = i + f(1) }` (no loop) | CRASH |
  | capture + `print(f(1))` then a `while` (call *before* the branch) | CRASH |
  | capture declared **after** the branch | ok |
  | capture + branch with an **empty** body | ok |
  | capture + branch body storing a **constant** (`if z<1 { z = 5 }`) | ok |
  | capture + plain store, no branch | ok |
  | **capturing a `const`** + loop | ok |
  | capture a **param** + loop, closure never called | CRASH |
  | *non*-capturing closure + loop (what the gate tests) | ok |
  | no control flow (what the gate tests) | ok |

  Trigger, stated precisely: **a closure capturing a local or a param, combined with a branch whose body
  stores a computed value.** The gate's nine closure rows all avoid that combination, which is why the defect
  survived.

- **ROOT CAUSE (confirmed by instrumentation, 0.0.234) — not the escape walk.** `coredumpctl` gave the fault
  address, the flat binary disassembled to `mov %rsi,(%rdi)` (a store through a wild pointer) at file offset
  `0x3572f`. Byte-marker probes then walked the compiler's own path: `escape_record` was entered **once** with
  `ci = -1` (clean), the closure body was registered as synthetic function `fi=1`, its capture binding ran
  (`y`), and the crash came **after** `clo_scope_save(fi)` and **before** `ci_func` — inside `sfn()`'s IR-slice
  copy. Printing the index there showed the real defect: in the `IR_CAPREAD` handler,
  `w64(cap_bodyvreg + (fi*CAP_MAX + a0)*8, res)` used `fi` = **140,483,158,344,240** (a token offset), not the
  function index 1. `fn ci_func(fi, is_main)` takes `fi` as its **parameter** — but the `fnptr()` cases earlier
  in the same body do `let fi=a0`, and Quanta's block bindings are not popped at block exit
  (`vfind`, `helpers.quanta:493`, scans newest-first because a re-`let` *appends*), so that `let` shadowed the
  parameter for the **rest of the function**. `cap_bodyvreg + (1.4e14*32)*8` is a wild address → SIGSEGV.
  The `escape_record`/`vreg_clo` hypothesis in the earlier triage was **wrong and is retracted**.
- **Fix (landed 0.0.234, `codegen.quanta`):** rename the two shadowing locals `let fi=a0` → `let ftgt=a0` in the
  `fnptr()` paths. Nothing else changes; the `IR_CAPREAD`/`IR_CAPWRITE` handlers now read the parameter again.
- **Verified:** repro compiles `rc=0` and **prints 8** (correct: `i` = 0+f(1) = 8, loop exits). 7 of the 8
  probes that crashed on 0.0.233 now compile and return their arithmetically-correct values
  (c1→8, c2→3, c3→10, c4→17, c6→8, c7→7, c8→8); the non-crashing control is unchanged (c5→4). Self-host
  fixpoint byte-identical (`md5 4d08aaac7e3e27f199f6700fdc3fe7f0`). Gate row
  `test_suites/codes/closure_capture_branch_test.quanta` (`EXPECTED.tsv` → 23) is **red on 0.0.233**
  (rc=139) and green on 0.0.234, per rule #16.

### A1b · OPEN · block bindings are never popped, so an inner `let` clobbers an outer name

### A2 · FIXED (0.0.235) · `print` on an `f64` emitted the raw bit pattern, not the value

```quanta
print(fadd(i2f(3), i2f(2)))     // prints 4617315517961601024, expected 5
```

Verified: `4617315517961601024` = `0x4014000000000000` = 5.0's IEEE-754 bits. Documented as a 0.0.222 defect
in `docs/research/native-inference-gaps.md` §6 ("`print` is BROKEN for all f64") and still live.

**Second consequence, found 0.0.234 — and it makes a gate row lie.** `exit()` takes an int, so `exit(p)` with
`p: f64` **silently exits 0** instead of trapping or converting:

| statement | measured rc |
|---|---|
| `exit(fadd(i2f(2), i2f(3)))` | **0** (checklist claims "expect 20") |
| `exit(20)` | 20 |
| `exit(f2i(fadd(i2f(2), i2f(3))))` | 20 |

`docs/RELEASE_CHECKLIST.md` §4 smoke test is exactly the first row, so **the release smoke has been passing for
the wrong reason** — it asserted a value it never observed. Fixed in 0.0.234 by writing `exit(f2i(p))` in the
checklist, and §4 now carries a note saying why.

**Fix (0.0.235) — a compile error, not auto-formatting.** The generic printers already dispatch on the vreg
tags; a float simply had no branch and fell into the integer path. Two ways to close that and the choice
matters: auto-rendering the value (`print(5.0)` -> `5.000000`) hides the type, and a systems language that
silently picks a float format is how the original trap got written in the first place. So the tag is checked at
compile time and the six handlers that could write a float **refuse it**, naming both correct routes:

| handler | message names |
|---|---|
| `print`, `echo`, `println` (1-arg, non-string) | `print_f(x)` (decimal, `std/fs`) and `f64bits(x)` (exact bits) |
| `printi`, `printsp` (the explicit integer printers) | same |
| `exit` | `exit(f2i(x))` — it previously passed the bit pattern to the exit syscall, which takes the low byte, so `exit(5.0)` exited **0** |

Both routes were verified working before the guards were trusted: `print_f` prints `5.000000` and
`f64bits(x)` prints `4617315517961601024` for the same value, and `f64bits` is a builtin, so bit-exact IEEE
testing is unaffected.

**The sweep was done with the compiler as the oracle, not by eye.** 28 files in the tree printed a float
(`tests/`, `benchmarks/`, `test_suites/codes`). The refusal now names the offending line **and its source
text**, which is what made an exact sweep possible: the token arena has no line field (`tokln` is the token's
LENGTH — `funcscan` reads it as a module-name length), and a bare line number is ambiguous once `import` pulls
modules in (`std_context_budget_test` reported line 8161 for a ~150-line file). Text needs no mapping.

Result: **all 28 compile**, and **27 of them were verified byte-identical** in runtime output against the
original code compiled by 0.0.234 (`f64bits` reproduces the old bit pattern exactly); the 28th
(`tests/test_float_bench.quanta`) prints a timing measurement — its `result=` line matches and only
`ns_per_iter` differs. Two rewrite classes were caught and reverted by that diff rather than shipped: wrapping
a **string** argument (a label became a printed pointer — 7 files) and wrapping an **int** argument. Both are
now excluded in the rewriter, and the diff is the standing check.

**Gate coverage:** new stage `float-print` — two negative probes (a float to `print` and to `exit` must each be
rejected with the right message) plus a positive control asserting `print_f` and `f64bits` agree
(`5.000000 4617315517961601024`). Negative rows are the right shape here: on 0.0.234 the probes *compiled*, so
the stage is red before the fix and green after.

**Not done, deliberately:** `print(x)` auto-formatting a float as a decimal. It is an ergonomics upgrade with a
format to choose (six decimals? shortest round-trip?), not a defect fix — recorded here rather than smuggled in.

---

## Fixed in 0.0.234 as release hygiene (found while gating)

| defect | measurement | fix |
|---|---|---|
| Gate cap too tight: every compile layer failed **silently** (`rc=1`, empty stderr, no binary) | compiler fails at `-v 6200000`, succeeds at `-v 6300000`; **same for the 0.0.233 golden**, so it is not a change regression | `docs/RELEASE_CHECKLIST.md` §5 now uses `-v 8000000` and the warning paragraph carries the new measurement |
| A stale note in the checklist: "functional (matches `EXPECTED.tsv` row count — currently 143)" | actual `EXPECTED.tsv` = **820** rows; gate reports 820/820, 0 fail | checklist text corrected to 820 |
| `compiler/0.0.234/test_suites/` was a stale copy of 0.0.233's | new row absent from the tree's own copy | test + `EXPECTED.tsv` synced into the tree |
| **Prerequisite checks used `[ -f ]`, which is false for a device node** | `/dev/nvidia0` reported "missing" on a machine that has the GPU, so declaring it would have **silently skipped every CUDA row** and weakened the local gate | `run_tests.sh` now uses `[ -e ]` at both check sites (a prerequisite may be a file or a device); skip text no longer assumes "model absent" |
| **5 stdlib rows asserted coverage they could not have on a model/GPU-less runner** | CI RED: `std_tokenizer_trait_test` (rc=1, "cannot open the model"), `std_model_size_test`, plus the three `std_cuda_*` rows reported as FAIL from a CUDA SKIP | the model path / `/dev/nvidia0` added to the `SKIP_IF_MISSING` column those rows were missing (20 sibling rows already had one); found by auditing every stdlib row against its own source, not just the 4 CI exercised |
| Remote CI had been "green" since 2026-10-07 only because nothing had been pushed | the 0.0.234 push sent all local commits; CI met the model/CUDA rows for the first time | not a regression from the A1 fix — recorded so the next push is not misread the same way |

**Consequence beyond printing:** this is why four benchmark twins had to print float *bits* to be
comparable, and why the C twins that cast doubles to `long` "matched" nothing. Any user formatting a float
gets an integer-looking number with no diagnostic.

- Fix approach: route `print`/format through the float path when the value's vreg is float-tagged
  (`is_float_vr`/`vfloat` already exist and are used by the arithmetic builtins). Add gate rows for
  `print` of f64 expression, f64 parameter, f64 return, and f64 local.

### A2b · LIVE · passing an `f64` to `exit()` silently exits 0 — and the release checklist's own smoke test

```
exit(fadd(i2f(2), i2f(3)))   // exits 0, not 5
exit(20)                     // exits 20        (int path is fine)
exit(f2i(fadd(...)))         // exits 20        (conversion fixes it)
```

Verified **identically on 0.0.233 and 0.0.234** (byte-identical binaries). Same defect class as A2: a float value
loses its float-ness at a builtin's boundary. The consequence is bigger than a wrong exit code:

> `docs/RELEASE_CHECKLIST.md` §4 prescribes exactly `printf 'fn main(){ let s = fadd(i2f(2), i2f(3)); let p =
> fmul(s, i2f(4)); exit(p) }'` and says **"expect 20"**. On the released compiler it yields **rc=0**, so that
> check has been passing for the wrong reason (or being read past) for every release that used it — rule #16's
> exact failure mode: a gate step whose expected value does not match reality is a bug shield.

Fix both ends: make `exit`/`print` convert a float-tagged argument (A2's fix), **and** change the checklist §4
line to `exit(f2i(p))` so it can fail for the reason it exists.

### A3 · DOC · `gguf_type_size` succeeds for types that have no decoder

`std/gguf.quanta` covers F32, Q4_K, Q6_K (266/266 for the reference model) but returns a byte size for
types 0..13 plus 30 while decoders for **F16, Q5_K, Q8_0 and the IQ family** do not exist. A caller therefore
sizes a buffer correctly and reads garbage — the exact trap that hid the earlier F32 gap (`WIP.md`
"OPEN DEFECTS").

- Fix approach: **fail closed** — return -1/error from both the size and the dispatch for a type with no
  decoder, and add a negative-control test per unsupported type. This is a one-session change and closes the
  whole class.

### A4 · LIVE · recursion depth ceiling ≈ 7 000 frames

Quanta emits a **1104-byte frame** per function (`sub $0x450,%rsp`, one home slot per vreg). Verified:
mutual recursion deeper than ~7k dies with SIGSEGV where the C twin reaches depth 200 000+ comfortably.
Bounded by the same spill-everything defect the speed series targets, but the *bug* is the crash.

- Fix approach: shrink the frame (share home slots for non-overlapping live ranges) — this is the same work
  as the eviction/frame-size item in `performance.md`, so it lands once and satisfies both.
- Gate: a recursion-depth test at a depth both sides survive today, plus one that documents the ceiling.

### A5 · DOC · `mem_alloc` inside a loop body can be clobbered by the next iteration

Recorded in `WIP.md` "Still open" and in this project's known-gotchas list. Allocate up front is the
workaround, but a language whose allocator returns memory that a later iteration can reuse is a
memory-safety defect, not a style note.

- Fix approach: decide the semantics (arena per loop iteration vs leak-until-function-exit) and either make it
  safe or make it a compile error. A silent clobber is the one outcome that must not remain.

### A6 · DOC · a `-> f64` user function's result can depend on what the program called earlier

Documented at length in `docs/research/call-order-f64-defect.md` and `WIP.md`: `reduce(0.5)` is correct only
if `qmult` was called earlier in the program; the builtin path was fixed by `as_f64_rdi()` (0d7950b6) but
nothing equivalent exists for the *user-function* path. It holds back a complete fdlibm `sin` reduction
(kept at `/tmp/negctl/math.sin-attempt`).

- **My simple repro does not reproduce it** (`fn qmult(x: f64) -> f64` / `reduce` return 8 and 4/8 correctly
  in both call orders), so the trigger is narrower: the fdlibm shape (2^52 magic constant + guarded early
  returns). Verify against that file first, then bisect.

### A7 · DOC · raw-pointer vs Quanta-string separation is unresolved

`print` on a string *parameter* emits text, but other string paths can still emit a pointer
(`WIP.md` "Still open"). Same user-visible class as A2: an integer-looking value where text was expected.

---

## Severity B — accuracy (0.0.235)

| item | measured | source |
|---|---|---|
| Long decimal literals | 160/222 exact, 58 at 1 ULP, 4 at 2 ULP | `WIP.md` "Still open" |
| `sin` near roots (x87 `FSIN`) | 73/88 bit-exact, worst case 57 ULP; `sin(pi+1e-9)` 19558 ULP out | same |
| Q8_0 present and exact, but the full model has not been run end to end (KV cache, sampling, vector store, RAG ingestion) | — | same |

---

## Severity C — stale documents and dead references (0.0.236, cheap)

Verified **fixed** on 0.0.233, so the documents that claim otherwise must be corrected rather than inherited:

| claim | verified reality |
|---|---|
| `docs/research/struct-return-defects.md` §A: "a struct-typed field read off a call result core-dumps the compiler" | **works**: `o.inn.a` → 7 |
| same §B: "a scalar field read off a call result gives 0 in a non-first argument" | **works**: `mk().b` → 9, `two(99, mk().b)` → 108 |
| same §C: "a bad `import` fails silently" | **errors**: `qc: cannot resolve imported module 'std/does_not_exist_at_all'` + searched paths |
| `compiler/0.0.233/WIP.md`: "The LFM2 forward path remains unimplemented: tokenizer … attention … generation" | **stale** — implemented and gate-tested (`stdlib_lfm2_*_test`), commits `a3c3dc5a`/`8535edd`/`07d913eb`/`e5ca7908` |
| `test_suites/codes/bench_fib.quanta` comment: "keep in lockstep with `tests/bench_fib.c`" | that twin **does not exist** |

---

## Not bugs, but on the record (capability, not correctness)

D4 ring-3 privilege transition · relocatable `GDATA`/BSS (drops the ≥1.06 GiB guest requirement) · ARM64
convergence (deferred post-0.1.0) · missing quant decoders (IQ\*, MXFP4, NVFP4, Q1_0, Q2_0) · **no
sibling-call (tail-call) elimination** (measured: gcc turns mutual tail recursion into a loop, 40M calls in
15 ms; Quanta 637 ms) — the last is a speed item, listed in `performance.md`.

---

## Working rules for this backlog

- One bug per release; each follows `docs/RELEASE_CHECKLIST.md` §0-§9 (drift check, `SELFHOST 7/7`, fixpoint
  md5, smoke, full gate, release matrix, CI pin, doc sync, promote).
- **Prove every fix red first:** reproduce against `compiler/0.0.233/bin/x86/qc`, add the regression test,
  then fix. A test that cannot fail is worse than no test (rule #16).
- A fix that changes codegen must keep the gate (819 rows / 24 stages) and `SELFHOST 7/7` green.
- Close the stale list as fixes land — a document that still claims a fixed defect is broken is a bug of its
  own, and it costs the next session the same verification pass this one just paid for.
