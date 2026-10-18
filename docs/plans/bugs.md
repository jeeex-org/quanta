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

### A1 · FIXED (0.0.234) · a capturing closure invoked in a loop crashes the compiler

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

### A1b · FIXED (0.0.237) · block bindings are never popped, so an inner `let` clobbers an outer name

**Full record: `compiler/0.0.237/WIP.md`.** Fix: a watermark on the binding stack, saved at every
block entry and given back at its single exit (`a1b_enter`/`a1b_leave`), so a block's bindings die
with the block; per-vreg tag tables are provably safe to leave alone (vreg indices are never reused
inside a function and `nv()` writes every tag at allocation). Fail closed: a use after its block is
the existing located `undeclared variable` error.

Measured, warn-first, before the flip (the whole tree: compiler's own source, `lib/std`, all 619
`test_suites/codes`, `benchmarks`, `tools`, `scripts`, `tests`, `temp` = 1052 compile units):
**26 distinct sites in 6 files** — `lib/std/gguf.quanta` 12, `x86/method.quanta` 6,
`x86/entry.quanta` 3, `x86/lexer.quanta` 2 (one of them silent), `x86/funcscan.quanta` 1,
`x86/parse.quanta` 1, plus one frozen fuzz seed. All migrated here. Gate: 222/222 (214 core + 8
new rows), STDLIB 108/108, all stages GREEN, EXIT=0; 3-generation fixpoint `dca6b4ab…74e401`.

It was not hygiene. On 0.0.236 the leak **SIGSEGVs the compiler** (rc=139, 3/3 runs) on a
tuple-payload enum constructor, a bare `Ok(7)` payload reads back as **5**, `let x = 1.5` inside a
block makes a later `print(x)` on the outer INTEGER a hard compile error, and
`lib/std/gguf.quanta`'s Q4_1/Q5_0/Q5_1/Q2_K/Q3_K/Q8_K dequant arms passed an **uninitialised
pointer** to the dequant routine and then to `mem_free` (preserved-not-authored in `cc7ff74b`).

Two corrections to the 0.0.236 entry that used to be here: those "819/824, 38 compile failures,
STDLIB 74/108" figures describe a HOISTING transformation (`let x = f()` pulled out of a loop, so it
initialises once instead of per iteration) plus an 821-row suite — `EXPECTED.tsv` was pruned to 214
core rows since (`git show c55a6d11:test_suites/EXPECTED.tsv | grep -c .` = 821), so they are not
comparable to the 222 above and are not the cost of this fix.

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

### A2b · FIXED (0.0.235) · passing an `f64` to `exit()` silently exits 0 — and the release checklist's own smoke test

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

### A3 · STALE — already fixed in the tree (verified 0.0.235) · `gguf_type_size` succeeds for types with no decoder

**Re-verified 0.0.235 — half the original claim was stale.** The decoder entry points that exist are:
`dequant_f32`, `dequant_q4_0`, `dequant_q4_1`, `dequant_q5_0`, `dequant_q5_1`, `dequant_q5k`, `dequant_q6k`,
`dequant_q8_0`, `dequant_q8k`, `dequant_bf16` — so **Q5_K and Q8_0 DO have decoders** and the plan's claim
about them was wrong (the accuracy notes saying Q8_0 is "present and exact" were right).

What is genuinely missing, and still claimed by the size path:

| dtype | claimed by `gguf_type_size` / the block table | decoder |
|---|---|---|
| 1 = F16 | yes (`return 1`) | **none** — there is `dequant_bf16` but no `dequant_f16` |
| 14–16+ = the IQ family | yes (block table returns 256) | **none** |

A caller therefore sizes a buffer correctly and reads garbage — the same trap that hid the earlier F32 gap.
**Further re-verification settles it: this is STALE, and my own re-scope was also incomplete.** Two things the
first pass missed:

1. `dequant_f16` **does** exist (called from the dispatch at `read_block_f64`). My entry-point grep pattern
   was too narrow — the same "measured incompletely, concluded too fast" error the entry above warns about.
   `dequant_iq4_nl` (20), `dequant_iq4_xs` (23), `dequant_mxfp4` (39) and `dequant_nvfp4` (40) exist too.
2. The dispatch **already fails closed**: `read_block_f64` starts with
   `if gguf_dtype_supported(dtype) == 0 { return 0 }`, and that predicate enumerates exactly the set with a
   decoder — F32, F16, Q4_0/Q4_1/Q5_0/Q5_1/Q8_0, Q2_K…Q8_K, IQ4_NL, IQ4_XS, BF16, MXFP4, NVFP4.

A dtype with no decoder (IQ2/IQ3, F64) therefore cannot be decoded into garbage: the dispatch refuses
before touching a byte. The residual nit — `gguf_type_size` answering a number for those dtypes instead
of -1 — is a *consistency* wart, not a corruption path, since the size only allocates a buffer the
dispatch then declines to fill. Recorded rather than given a version.

- Fix approach: **fail closed** — return -1/error from both the size and the dispatch for a type with no
  decoder, and add a negative-control test per unsupported type. This is a one-session change and closes the
  whole class.

### A4 · MEASURED · recursion depth ceiling ~8 000 frames (no separate fix — it is the frame size)

**Measured 0.0.235** with a probe whose recursion cannot be tail-call optimised (`return 1 + down(n-1)`; a
bare `return down(n-1)` compiles to a jump — my first probe "survived 2 000 000" that way and was
measuring iterations, not frames):

| | depth survived | frame |
|---|---|---|
| Quanta | **~8 000** frames | `sub $0x450,%rsp` = **1104 bytes** |
| C twin, `-O0 -fno-optimize-sibling-calls` | **~262 000** frames | ~32 bytes |

Both die at their own stack limit (8 000 x 1104 B ≈ 8.8 MB ≈ the 8 MB stack; 262 000 x 32 B likewise), and
the 33x ratio IS the frame ratio — so the depth is fully explained by the frame size, nothing else.

- **No separate fix, and re-scoped out of the defect pass.** The crash is inherent to a fixed stack (the C
  twin segfaults the same way at its own depth); the lever is the frame — the eviction / shared-home-slot
  work in `docs/plans/performance.md`, which now has a measured motivation: every halving of the frame
  doubles the usable recursion depth.
- **Gate guard added:** `test_suites/codes/recursion_depth_test.quanta` (EXPECTED 184) recurses to 3 000,
  a depth both sides survive. It PASSES on 0.0.235, so it is a regression guard, not a red-first row —
  labelled that way deliberately, because rule #16 applies to rows asserting new behaviour.

### A5 · DEFECT CONFIRMED (executed 0.0.240): the P2 RAII auto-free for `mem_alloc` is DEAD CODE · the loop-clobber shape cannot fire today

Recorded in `WIP.md` "Still open" and in this project's known-gotchas list. Allocate up front is the
workaround, but a language whose allocator returns memory that a later iteration can reuse is a
memory-safety defect, not a style note.

**Probed 0.0.235, not reproduced** (allocate in iteration 0, read after the loop → old block intact).
That much is real — but the *reason* was measured incompletely, twice. The first framing ("not
reproduced") missed the defect behind it; the 2026-10-15 reclassification ("latent use-after-free,
masked by deferred reuse") was also wrong, and this entry retracts it: it claimed "a loop body's
allocation IS freed every iteration", and the emitted machine code says no free is ever emitted.

**VERIFIED BY EXECUTION + DISASSEMBLY (0.0.240): the auto-free never fires at all.**

Four probes compiled with `qc --emit-obj` and disassembled — `mem_alloc` at (1) function scope,
(2) inside an `if` block, (3) inside a `while` body, (4) the full original shape (alloc in loop,
pointer escaping the body). Every one contains the `mmap` syscall for `mem_alloc` and **zero**
free-list pushes: no instruction in `main` touches `HEAP_CTRL` (`0x42200408`); the byte pattern
`89 1c 25` (the `mov %rbx,HEAP_CTRL` free-list-head store) has **0 occurrences** in all four
objects. `vreg_owned` has exactly one writer that sets it to 1 (`parse.quanta:1437`) and that
writer never fires, so `owned_scope_pop_one`'s `if r64(vreg_owned+ov*8)==1` is never true and
`IR_FREE` is never emitted. The 0.0.235 probe read 111 back because the block was **never freed** —
not because it was freed and not reused.

**Root cause — a field-indexing bug in the ownership detector (`parse.quanta:1430-1443`):**

The detector peeks the last IR record for `IR_CALL` with callee name `mem_alloc`:

    let cnm = ira1(last); let cnl = ira2(last)
    if cnl==9 && r8(src+cnm)=='m' && ... {

But the `IR_CALL` record layout (written at `method.quanta:387`, `iremit(IR_CALL, vr2, nm, nargs, avs)`;
accessors `helpers.quanta:396-398`) is:

| field | accessor | contents for `mem_alloc(8)` |
|---|---|---|
| a0 (+16) | `ira0` | **callee name offset** (`nm`) |
| a1 (+24) | `ira1` | **argument count** (1) |
| a2 (+32) | `ira2` | **arg-start IR index** (`avs`) |

The detector reads the argument count as the "name" and the arg-start index as the "length".
`cnl==9` therefore asks whether the arg-start IR index happens to equal 9 — a data-dependent
coincidence, never the name length — and `src+cnm` reads a byte at `src+<arg count>`. Codegen's own
`IR_CALL` handler proves the authoritative layout: `let nm=a0`, and it **re-scans the name length
from the source bytes** (`codegen.quanta:2667-2674`) because the IR record does not even carry a
length field.

**Consequences:**

1. `let p = mem_alloc(...)` never marks `p` owned; `owned_add` never runs; `IR_FREE` is never
   emitted; the free-list push (`codegen.quanta:2843`) is unreachable on this path. The mechanism
   exists (`globals.quanta:29`, `features.quanta:24`, `emitter.quanta:1980`) but is dead code.
2. Every `mem_alloc` block leaks to process exit — consistent with, and now explaining,
   `docs/AUDIT_ROADMAP.md`'s "leaks every freed block" note on this path.
3. The original A5 loop-clobber shape is real but **two fixes away**: it goes live only when BOTH
   (a) the field-indexing bug is fixed so `IR_FREE` actually fires per loop iteration, AND
   (b) free-list reuse lands (recorded as deferred at `emitter.quanta:1980`). Whoever lands either
   change must re-run the probes below; whoever lands both must carry the alias-detection
   invariant — a pointer escaping a loop body that owns it is then silent, data-dependent
   aliasing corruption (`codegen.quanta:2741` already warns of "double-free → aliased-block").

**Regenerate the evidence at any time:**

```bash
cd /tmp && QC=/opt/tali/quanta/compiler/0.0.240/bin/x86/qc
$QC --emit-obj a5_probe.quanta a5_probe.o
objdump -d a5_probe.o | grep -c 42200408     # 0 = free never fires
objdump -d a5_probe.o | grep -c "89 1c 25"   # 0 = no free-list store bytes
```

#### A5 · FIXED in the 0.0.242 WIP tree — **NOT PROMOTED** (gate RED). Detector + handler + return ordering.

Full trail: `compiler/0.0.242/WIP.md`. The detector was worse than the field
bug above: it had **two** record-read defects. Measured with an instrumented
compiler on `let p = mem_alloc(8)` — `irop(irc-1)` is `IR_MOV` (the binding MOV
that `parse_let` emits at `parse.quanta:1315`); the `IR_CALL` is at `irc-2`;
`ira0(irc-2)=22` with `src+22=="mem_alloc(8)"`, `ira1=1` (nargs), `ira2=1`
(arg-start). So the old code read a MOV (never entering the `IR_CALL` branch)
*and* the wrong fields. Fixed: step over the binding MOV, read `a0`, scan the
name length from the source bytes.

Two more defects on the same path had to be fixed before the free was correct:

- **The IR_FREE handler was mis-encoded.** It emitted `48 89 5b 08`
  (`mov %rbx,0x8(%rbx)`) and `48 89 1b` (`mov %rbx,(%rbx)`) — clobbering the
  block's length header `[p]` and **never writing `HEAP_CTRL`**. Correct ModRM
  `48 89 43 08` / `48 89 1C 25` (the idiom at `codegen.quanta:2551`). A
  detector-only build corrupts memory; proof: `tests/raii_autofree_test.quanta`
  exits 1 with `139773645234176 139773645234176 …`.
- **`parse_ret` freed before evaluating the return expression**
  (`parse.quanta:490-491`): `return file_open(cp + 8, …)` in `lib/std/fs`'s
  `open()` freed `cp` before the call read `cp+8` → `open` returned "open
  failed". Fixed by emitting the frees after `parse_expr()`.

Proven firing: `0x42200408` refs 0→2 and `48 89 1c 25` 0→1 per free site; the
free-list chain test is `tests/raii_autofree_test.quanta` (0.0.241 golden rc=3
→ 0.0.242 rc=0, 5/5 deterministic).

**Why it is NOT promoted:** enabling the auto-free changes 341 of 821 corpus
units' codegen and breaks **26 `EXPECTED.tsv` rows** (`219/229`; see
`compiler/0.0.242/WIP.md` §5). The ownership rule ("any block-scoped
`mem_alloc` is owned") is unsound without escape detection — `lib/std/fmt`
returns a `mem_alloc` buffer and double-frees it. The recorded memory win is
also nil (peak RSS 79 840 → 82 064 kB over 20 000 allocs: reuse is deferred, so
the free only pushes onto a list nobody consumes).

### A6 · SUPERSEDED (see the FIXED and PROMOTED entry below) · root cause confirmed; three fix mechanisms measured and rejected

Documented at length in `docs/research/call-order-f64-defect.md` and `WIP.md`: `reduce(0.5)` is correct only
if `qmult` was called earlier in the program; the builtin path was fixed by `as_f64_rdi()` (0d7950b6) but
nothing equivalent exists for the *user-function* path. It holds back a complete fdlibm `sin` reduction
(kept at `/tmp/negctl/math.sin-attempt`).

- **ROOT CAUSE: a parameter written without `: f64`.** `fn qmult(x) -> f64` with
  `let y = x * (2.0 / 3.14159265358979323846)`. Annotating `x: f64` alone makes the failing program correct, and
  drops its untagged-conversion count from 2 to 1. The tagging case at `codegen.quanta:1123-1137` covers only
  DECLARED `: f64` parameters, so `x` reached the SSE multiply untagged and `fopld_rr` emitted `cvtsi2sd` over an
  f64 bit pattern. "Call-order sensitivity" was a red herring: an unreachable call elsewhere tagged that vreg
  index by another route.
- **ROOT CAUSE (certain):** an untyped parameter used as a float. `fn qmult(x) -> f64` with `let y = x * (2.0 / 3.14159265358979323846)`: annotating `x: f64` alone makes it correct and drops the untagged-conversion count 2 -> 1. So the tagging at `codegen.quanta:1123-1137` (declared `: f64` only) is the gap, and `fopld_rr` emits `cvtsi2sd` over an f64 bit pattern. "Call-order sensitivity" was a red herring.
- **THREE MECHANISMS TRIED, ALL REJECTED BY MEASUREMENT** — do not retry any: (1) a one-sided float rule in the `changed=1` tag pass -> **byte-identical binary**, inert; (2) tagging both operands at the two SSE emit sites -> repro fixed but §5 gate **rc=1** with 4 new stdlib failures (`embedding_test`, a clean A/B) — *which branch is taken is itself decided by `vfloat`*, so a wrong tag gets cemented; (3) call-argument tag -> callee parameter via `fn_parflt` -> the rule **fires** (32 events incl. `callee=0, 1 arg` for `qmult`) but the repro stays garbage, inert.
- **WHY MECHANISM 3 WAS INERT — CORRECTED. The \"wrong key\" explanation recorded here earlier was itself wrong.** `fn_parflt` is keyed by (function, parameter **ordinal**), not by a vreg, so the write mechanism 3 made was already the right slot. Settled from the CREATION site and the two readers, not from a name: `entry.quanta:856` is `let vr=nv(); iremit(IR_PARAM, vr, pc, 0, 0)`; `helpers.quanta:374` lays an IR record out as `res` at +8 and `a0` at +16; and both `fn_parflt` readers index it with `ira0(...)` — the pass case at `codegen.quanta:1136-1137` (`let ppi = ira0(mp)`) and the second at `1245` (`ta0`). So for `IR_PARAM` the RESULT (`irres`) is the target vreg and `a0` is `pc`, the ordinal. The `codegen.quanta:455` line cited as proof (`w8(live_bits+o0,1)   // PARAM target vreg is live`) is a different context — live-range marking over `live_bits`, a different table — and does not bear on `fn_parflt` at all. The real reason a call-argument rule was inert is the **layer**, not the key: parse and emit are fused per function, so a callee is fully emitted before any call site that could say what type is coming has been read, and the caller's and callee's vreg spaces are not joined by any `IR_MOV` chain. The inference has to be complete *before* the callee is emitted, which only a whole-file token scan can do.
- **THE FIX (landed 0.0.236): a whole-program token scan, not an emit-time rule.** `scan_call_types()` (`funcscan.quanta`, called from `entry.quanta` right after `scan_retstr()`) extends `scan_call_float`'s literal rule to an argument that NAMES an already-typed parameter of the enclosing function or is a call to a `-> f64`/`-> str` function, monotone to a fixpoint. It writes the same `fn_parflt`/`fn_parstr` slot at the same (function, ordinal) key `scan_call_float` already uses — no ordinal->vreg mapping is involved, so the earlier \"map the ordinal to the vreg first\" plan below was solving a problem that did not exist. The evidence (the argument's type) stays independent of the tag that picks the SSE branch, which is the constraint mechanism 2 broke.
- **FIX ATTEMPT (0.0.236) — REJECTED BY THE GATE.** At both SSE emit sites, tag both operands before loading
  them. It makes the repro correct (`cvtsi2sd` 2 -> 1, fixpoint holds), but the §5 gate on that tree returns
  **rc=1: 821/822 functional and 4 new stdlib failures** — `embedding_test` is a clean A/B (pass on 0.0.235, fail
  on 0.0.236) and the other three are the same float-heavy family. The reasoning was unsound: *which branch is
  taken is itself decided by the `vfloat` tag*, so a wrong tag is cemented and a genuinely-integer operand then
  gets marked float. `compiler/0.0.236/WIP.md` carries a DO-NOT-PROMOTE banner and the constraint for the next
  attempt: tag from evidence **independent** of the tag that chose the branch. The other rejected attempt (a rule
  in the `changed=1` tag pass) stays rejected — byte-identical binary, no float evidence in that pass. Verified: repro correct,
  `cvtsi2sd` 2 -> 1, fixpoint `08acae941891e1d387b550ca1d4a5554` (3 generations identical), new gate row
  `f64_call_order_test.quanta` RED on 0.0.235 (rc=1) and GREEN on 0.0.236 (rc=0). A rejected first attempt (a
  rule in the `changed=1` tag pass) produced a byte-identical binary and was reverted — the pass has no float
  evidence to propagate from.
- **Original report, kept for the record:** Built from the real bodies in
  `/tmp/negctl/math.sin-attempt` and saved as `tests/f64_call_order_defect.quanta` (182 lines):

  | program | output |
  |---|---|
  | `println(f64bits(reduce(0.5)))` alone | **-4336984033343832063** — garbage, and the exact value the
    original report recorded |
  | with a preceding `println(f64bits(qmult(0.5)))` | **4602678819172646912** — correct |

  Both stable across runs and recompiles, so it is deterministic codegen keyed on call order, not
  uninitialised memory. The trigger is `qmult`: the only callee whose body has the 2^52 magic AND the pair
  of guarded early returns (the `pio2_*` helpers are single-expression `return f64of(...)` bodies).
  My earlier "simple repro does not reproduce it" note stands — the reduction shape is required.
- **MECHANISM CONFIRMED (0.0.235), at the instruction level.** An **unreachable** `qmult` call fixes the
  result, so the trigger is compile-time bookkeeping, not execution; the two binaries are the same size and
  differ only in re-encodings. The site:

  | program | emitted code |
  |---|---|
  | no `qmult` call anywhere | `f2 48 0f 2a c0  cvtsi2sd %rax,%xmm0` — **converts** it |
  | with a dead `qmult` call | `66 48 0f 6e c0  movq %rax,%xmm0` — **moves** the bits |

  The value is an f64 bit pattern already in a GPR (what `f64of(<bits>)` produces); `movq` is correct and
  `cvtsi2sd` mangles it. Which one is emitted comes from a GLOBAL "has a `-> f64` call been compiled"
  flag rather than from the value's `vfloat` tag — that is "first call wins", and it is why a dead call in an
  unrelated function changes another function's arithmetic.
- **Fix direction:** drive that encoding from `vfloat[vreg]` (the tag the value actually carries), the same way
  the builtin path is driven by `as_f64_rdi()` (0d7950b6). When fixed, promote the saved repro into a gate row —
  it is red-first by construction.

### A6+A7 ARE ONE FIX · parameter typing inferred from the call argument (decision made)

**Decision: INFER, do not refuse.** Measured untyped-parameter signatures in this repo (param list containing an
identifier with no `:`):

| area | untyped-param signatures |
|---|---|
| `compiler/0.0.235/src/x86` (the compiler's own source) | **316** |
| `lib/std` | **1082** |
| `tests` + `test_suites/codes` | **493** |

Refusing an untyped parameter would therefore break over 1,800 signatures, including the 316 that must keep
self-hosting — so refusal is not an option and the question is closed. The fix is to make the parameter take the
type of the argument the caller passes.

**This is one change for two defects.** A6 (untyped param used as f64 -> bit pattern instead of a value) and A7
(untyped param used as str -> pointer instead of text) are the same mechanism: the parameter slot carries no
type, so the callee takes the integer path. One propagation fixes both.

**Mechanism 3 had the right idea and the right key; what it lacked was the layer.** It wrote `fn_parflt` at the
same (callee, parameter-ordinal) key the table is keyed by (see the corrected bullet under A6), so the write
itself was correct — an earlier note here claimed the opposite and was wrong. It was inert because a rule placed
in the per-function emit path cannot see a function's signature and its call sites at the same time: parse and
emit are fused per function, so the callee is already emitted before the call site that would inform it is read.
The fix therefore had to run at the whole-program token level, before codegen, and be monotone to a fixpoint —
which is what `scan_call_types()` does. The constraint from the SSE-site attempt still holds: the evidence (the
argument's type) must stay independent of the tag that picks the branch.

**Severity is higher than the ticket implied:** untyped parameters are the norm in this codebase, not an edge
case, so A6/A7 are the visible tip of a very common pattern.

### A6+A7 · FIXED and PROMOTED (0.0.236) · the stdlib row it first uncovered is fixed too; gate fully green

**The fix: `scan_call_types()` — `funcscan.quanta`, called from `entry.quanta` after `scan_retstr()`.**
It extends `scan_call_float`'s rule past float literals: for every call `name(args)` inside function `g`,
argument `k` carries a type when (1) it holds a float/string literal, (2) it NAMES a parameter of `g` whose
`fn_parflt`/`fn_parstr` slot is already set, or (3) it is a call to a function flagged `fn_retflt`/`fn_retstr`;
parameter `k` of every top-level `name` is then marked float/string, monotone to a fixpoint. Not one literal.

- **A6, the whole of it:** `reduce(0.5)` marks reduce's parameter from the literal; `qmult(x)` marks qmult's
  from reduce's already-marked parameter. The "a dead `qmult(0.5)` fixes it" puzzle falls out — the old rule
  needed a LITERAL at a call site, this pass reads the token stream, so reachability never enters into it.
- **A7 needed a scan that did not exist.** Verified by grep: `fn_parstr` had only two writers, both
  declaration/import metadata (`funcscan.quanta:319`, `objfmt.quanta:1252`) — there was no call-site inference
  for strings at all. The same rule now writes `fn_parstr`, which `entry.quanta:893` turns into `vreg_is_str`
  on the parameter vreg. Measured: `file_open(p, 0)` with an UNTYPED `p` returned `-2` on 0.0.235 and `3` on
  0.0.236, exactly matching `fn p: str` (3 on both).
- **Why the enclosing function is resolved from BRACES, not a name:** a name-only rule would tag any call that
  happens to pass an identifier spelled like some other function's float parameter, and a wrongly-float
  parameter is the same miscompile class this fix removes. Method calls are skipped (a preceding `.`).
- **The record above is wrong about mechanism 3**, and the source says so: `iremit(op,res,a0,a1,a2)` plus
  `entry.quanta:851` (`iremit(IR_PARAM,vr,pc,0,0)`) make `IR_PARAM.a0` the parameter ORDINAL and `irres` the
  target vreg. Both readers (`codegen.quanta:1136`, `1245`) key `fn_parflt` by that ordinal, and
  `scan_call_float` writes it by ordinal too — so mechanism 3's write went to the right slot already. The
  inertness was the LAYER, not the key: a call-argument rule placed in the per-function emit path cannot see a
  function's signature and its call sites at the same time (parse and emit are fused per function, so the callee
  is emitted before its call site is read) — which is why the fix had to move to a whole-program token scan. The
  `codegen.quanta:455` comment ("PARAM target vreg is live" reading `o0`) is the misreading that produced the
  earlier, wrong "wrong key" explanation.
- **Verified (0.0.236):** A6 repro `4602678819172646912` (was `-4336984033343832063`); A7 repro prints
  `untyped tag: GLOBAL` / `untyped lit: TEXT` (was two 20-digit numbers); `codes/f64_call_order_test.quanta`
  run rc 1 -> 0; `tests/f64_call_order_defect.quanta` still `0` then `4602678819172646912`;
  `codes/embedding_test.quanta` still rc=0; fixpoint `203e0d772ca38e903ad27c921645d10a` (3/3 generations);
  **STDLIB 108/108 GREEN** — the layer the rejected SSE-site mechanism broke.
- **Gate — RESOLVED, PROMOTED as 0.0.236.** The row this fix first uncovered is
  `lib/std/code_synthesizer.quanta`, and it had two defects of its own, independent of A6/A7: `read(2)` was asked
  for 16 MB into a 2 MB `mmap`, and `sanitize_ident()` returned a headerless buffer that every caller read with
  `len()`/`+8` (so the copy loops ran off the mapping). Both are fixed in that module, along with the required
  3-argument `file_open` and staging its output under a CWD-relative `synth_out/` so a gate run cannot rewrite
  the tracked `lib/std` tree. Full evidence: `compiler/0.0.236/WIP.md`.
- **Gate (promoted tree, official command, this environment):** `=== Results: 212/212 pass, 0 fail (incl. 0
  compile-fail) ===  rc=0`; every layer GREEN; `STDLIB: 108/108 GREEN`. `scripts/verify-release.sh 0.0.236
  0.0.235` -> 14 passed, 0 failed. The row itself: `std_code_synthesizer_const_test.quanta rc=0` in 9/9
  consecutive runs.
- **The row still exercises the module** — its `main` is the module's `main`, which runs `synthesize_all()`,
  reads all 2,290,042 bytes of `gap_specs.json` and emits 9,026 modules into `test_suites/run/synth_out` — so
  the pass is not a test that stopped testing anything.
- **Red-first for the buffer defect, on the PRISTINE compiler.** The original module with only its parameter
  typed `: str` and its buffer enlarged (so A6/A7 is out of the picture), compiled by the untouched 0.0.235
  golden, gives over nine runs **rc=0 x3, rc=124 x4, rc=135/SIGBUS x2** — flaky and not the expected 0, i.e.
  the module was broken before this change. (Earlier recorded as rc=0 x3 / rc=124 x2 / rc=135 x4; the
  re-measurement is the authority.)

### A7 · FIXED (0.0.236, with A6) for the untyped case · `NOT REPRODUCED` for typed paths

**Measured on 0.0.236. The typed paths are fine; an untyped parameter is not.**

Every typed string path was probed and is CORRECT — global, local, struct field, array element, a returned
value, and a returned value held in a local all print their text. So the original wording ("other string paths
can still emit a pointer") does **not** reproduce.

The live case is an **untyped parameter** carrying a string, and it is the same root-cause family as A6 — the
parameter slot has no type, so the callee's `print` takes the integer path:

    fn show(tag, x) { print(tag); print(x) }      -> 11093940081109393752  (pointer/bits)
    fn show(tag: str, x: str) { ... }             -> global     : GLOBAL   (correct)

Both forms compile **without complaint**, so the failure is silent — the A2 class: an integer-looking value
where text was expected. Repro saved as `tests/a7_untyped_str_param_defect.quanta`.

Note the A6 fix does not reach this: A6 tagged `vfloat` at the SSE operand site, while this needs the string tag
(`vreg_is_str`) supplied where the argument's string-ness is known. Same principle, different table — and the
same question applies to whether an untyped parameter should be refused rather than silently mis-typed.

### A8 · CLOSED (stale report) · `SYNTH_CAP` was a dead constant; it is now an enforced ceiling

**Reported as a dead constant at `lib/std/code_synthesizer.quanta:17` (one declaration, no
uses). Re-measured: the report predates HEAD `36760cd0` ("chore(std/code_synthesizer): make
SYNTH_CAP a real ceiling"), the commit that closed it, so the premise is stale.** The task
that raised it was to file the finding and leave the code to the file's owner — the owner
landed the fix first.

grep evidence in `lib/std/code_synthesizer.quanta` (`grep -n 'SYNTH_CAP' ...`):

```
18:// (exit 1, with a printed message) if a run would stage more than SYNTH_CAP
22:const SYNTH_CAP = 10000;
292:            // SYNTH_CAP is enforced, not decorative: fail loudly rather than
294:            if generated > SYNTH_CAP {
295:                prints("code_synthesizer: SYNTH_CAP ("); printi(SYNTH_CAP);
```

One declaration, and it is **read** at lines 294-295 inside `synthesize_all()`. (The
declaration is at line **22**, not 17 — the file grew above it; the cited line was right for
the pre-HEAD revision.) The two options on the table were delete it, or enforce it; the
**second** was taken — a loud failure (`exit 1` plus a printed message), never a silent stop,
which is the `std/vec` defect class (`vec_push` silently dropped pushes past capacity; see
`SELF_IMPROVEMENT.md` item 4). It is a no-op today: `gap_specs.json` holds 9,000 specs
(11 were removed in the SI contamination pass, this session) against a cap of 10,000.

- No code change is recorded here: `lib/std/**` belongs to another work unit and the ceiling
  is already in place. The entry exists so the next reader does not re-raise a closed report
  — the same reason A3 carries a status line instead of a fix. (A5 is different: it records a
  CONFIRMED open defect — the dead ownership detector — awaiting its fix version.)

### A9 · FIXED here (lib/std) · the native engine dies after ONE threaded forward, with rc=0

```quanta
// stage1/par_test.quanta, ulimit -c 0 -v 4194304
//   marker 111 written BEFORE fc_forward_token(35808, 0), marker 222 AFTER
//   -> rc=0, before=ok, after=ABSENT, no stdout
```

`mm_set_workers(20)` then one forward; the process disappears inside the forward and
is reported as **exited 0**. This is why every parallel benchmark in `stage1/bin/`
(`native_bench2/3/5`) exited rc=0 in 8-12 s having printed nothing: each ran one
forward and died.

**ROOT CAUSE (measured, not inferred).** `mm_matvec_par` / `mm_embed_logits_par`
spawned `nworkers` threads **per matvec call** with `thread_create`, which mmaps a
fresh **1 MiB** child stack (+ a page-rounded 24-byte join slot) per call, and
`thread_join` never unmaps either. `strace -f -e trace=mmap,clone,exit` over **one**
30-layer forward at 20 workers:

* `grep -c ' clone(' -> ` **2329 `clone()` calls** = **~2.33 GB of address space
  leaked per forward** (plus a `mm_scratch_new` cell per worker per matvec).
* The dying run ends:

  ```
  2219451 mmap(NULL, 1048576, PROT_READ|PROT_WRITE, MAP_PRIVATE|MAP_ANONYMOUS, -1, 0) = -1 ENOMEM
  2219451 exit(1)     = ?
  2219451 +++ exited with 0 +++
  ```

The `exit(1)` is `thread_create`'s child-stack MAP_FAILED guard
(`emitter.quanta`, `mov edi,1; mov eax,60; syscall`) running **on the main thread**.
It is `exit(60)`, not `exit_group(231)`, so the group's worker threads survive it,
exit 0, and the process status comes out **0** — the silent death. The after-marker is
never written because the main thread is gone.

The cap decides when: at `-v 4194304` (1.67 GB model + heap) one forward exhausts the
space; at `-v 8000000` forward 1 completes and forward **2** dies. Reproduced with
`tests/threaded_forward_twice.quanta` (pre-fix: 4 GB -> both markers missing; 8 GB ->
marker 1 present, marker 2 missing, rc=0; fixed -> rc=7, both markers, 4 GB and 8 GB).

**REJECTED:** a swallowed trap (strace shows no signal, only the explicit `exit(1)`);
a missing `fc_kv_init` in the threaded path (`par_test` calls it, and the serial path
works with the same sequence — the threaded path's broken premise is **memory**, not
initialisation); worker corruption (pooled output is element-wise identical to the
serial block path, 0 mismatches at 2/4/8/20 workers); too many workers for the cores
(20 workers on 20 cores is fine once memory suffices).

**FIX (`lib/std/lfm2_mm.quanta` + `lib/std/lfm2_forward.quanta`):** a persistent worker
pool. Workers are spawned **once** and fed jobs by a generation counter
(`fence()` -> `atomic_store(pl_gen) -> futex_wake`; each worker stamps `done[t] = gen`;
`done[t]` is written by exactly one worker, so nothing races). Scratch is allocated
once per worker. `mm_pool_begin`/`mm_pool_end` nest by depth and
`fc_forward_token_ex` brackets one forward, so no live worker is ever left at process
exit (the runtime's end-of-main is `exit(60)`: a live worker **hangs** the process —
measured, `stage1/hang_probe.quanta` rc=124). Clones per forward: **2329 -> 20**.

**VERIFIED.** `par_test` under the recorded cap now gives `rc=0, before=ok, after=ok,
r=0`; RSS 369 MB -> 116-154 MB. Real decode, same prompt, `-v 8000000`, load ~11/20:

| workers | 1 | 2 | 4 | 8 | 20 |
|---|---|---|---|---|---|
| s/token | 70.5 | 41.8 | 24.5 | **16.7** | 12.8 |
| tok/s | 0.014 | 0.024 | 0.041 | 0.060 | 0.078 |
| x serial | 1.00 | 1.69 | 2.88 | 4.23 | 5.50 |

`argmax=5922` at every worker count (equals the serial reference). Serial 70.5 s/token
matches the plan's 69.4; **the plan's 25.8 s/token @8 workers is BEATEN (16.7 measured)**.
8 -> 20 workers buys only 1.3x on 2.5x the threads — bandwidth-bound, as the plan
predicts; the remaining lever is SIMD/blocked dot products, not worker count.

**GATE.** New row `test_suites/codes/lfm2_threaded_pool_test.quanta` (EXPECTED.tsv ->
**7**, model in SKIP_IF_MISSING): 150 jobs at 20 workers under one held pool plus 4 jobs
each at 8/4/2, element-wise vs the serial block reference. **RED on the pre-fix tree**
(`call to undeclared function: mm_pool_begin` / `mm_pool_end`, compiler rc=7, no binary),
**GREEN post-fix (rc=7 in 3.78 s)**. It is a real leak guard: regressed to per-call
threads the loop leaks 3 GB and the row TIMEOUTS (rc=124). Completion is rc=7 and not 0
on purpose — this defect's failure mode also reports 0, so a rc=0 row would pass while
dying (rule #16). The literal "two threaded forwards" repro is
`tests/threaded_forward_twice.quanta` + `tests/run_threaded_forward_twice.sh` (tests/,
not EXPECTED.tsv: it needs the model, takes ~26 s > the 15 s gate cap, and rc alone
cannot detect the death so it asserts marker files).

**NOT FIXED (follow-up):** `thread_create` still never unmaps its 1 MiB stack, so each
pool leaks `nworkers` stacks — ~20 MB per forward as bracketed (was ~2.33 GB), or
20 MB per process if a caller holds the pool across its loop. The complete fix is in the
emitter (`thread_join` munmapping the child stack and slot, which needs the stack base
recorded in the join slot) and belongs to the compiler work unit, whose `0.0.237` tree
was in flight. Also unfixed: `fc_attn_workers`' parallel attention body still spawns
per-call threads (never enabled, so unexercised; **superseded — `fc_attn_workers`
and its `fc_attention_par` body were REMOVED in `21a7be4b`, see A21/A22**); bare `mm_matvec_par` callers outside a
bracket get a pool per call. A timed `futex_wait` was tried in the driver and reverted —
it made argmax diverge (5922 -> 35808/8696, varying) while the untimed wait is stable.
Full trail: `docs/research/threaded-forward-defect.md`.

### A10 · FIXED (0.0.241) · a top-level `const` with a FLOAT initialiser evaluated to 0

Root-caused: the lexer emits a float literal as **`TT_FNUM` (7)**, value
`(mantissa << 8) | frac_digits` with the decimal exponent in the token's side
word, but `eval_const()`'s literal branch tests **`TT_NUM` (2)** — so a float
literal matched nothing, `ec_factor()` returned 0 *without consuming the token*,
and 0 was written to the const table. Two sites (`features.quanta` kt==57, which
is the one that runs for a top-level const, and `parse_const()`) had copied the
bug. `CF + 2.5` returned 2.5 on 0.0.240, 5.0 on 0.0.241. Row:
`test_suites/codes/const_float_test.quanta` (EXPECTED.tsv, rc 0; RED on 0.0.240).
**Still unsupported:** a negative float literal `-2.5` (unary minus in front of a
float literal) — recorded here so it is not mistaken for fixed. Full trail:
`compiler/0.0.241/WIP.md` §1.

### A11 · gate-covered (0.0.241) · the sampling EOS-exclusion policy had no gate row

The EOS-exclusion policy in the sampler (an EOS id must be excluded from the
candidate set except where the policy allows it) was ungated. Row added:
`test_suites/codes/sampling_eos_test.quanta` (EXPECTED.tsv, rc 0; commit
5ed79597). `docs/README-lfm2-generate.md` said the row did not exist and was
corrected in a1c8eef6.

### A12 · FIXED (0.0.241) · `lib/std/tokenizer_trait.quanta` called `bpe_encode`, not `bpe_encode_special`

The delegation used `bpe_encode`, which does no special-token matching, so the
thinking/BOS ids were tokenised as ordinary text. Fix: call
`bpe_encode_special`. Row: `test_suites/codes/std_tokenizer_trait_special_test.quanta`
(EXPECTED_STDLIB.tsv; RED — 4 check(s) rc=1 — before the fix, PASS rc=0 after).
Full trail: `compiler/0.0.241/WIP.md` §2.

### A13 · gate coverage ADDED (0.0.241) · `lib/std/rag.quanta` was exercised by nothing

`lib/std/rag.quanta` was absent from `EXPECTED_STDLIB.tsv`, so the RAG unit's
edits to it were tested by no gate row (the live probe needs a hand-placed
`/tmp/rag_emb_hex.txt` that nothing creates — the real encoder needs torch, which
cannot map its shared objects under the runner's address-space cap). Row added:
`test_suites/codes/stdlib_rag_search_gate_test.quanta` (EXPECTED_STDLIB.tsv, rc 0
— it builds a deterministic index in-language, hex-encodes it itself and drives
the whole spill → fork/exec → sqlite-vec KNN path). Full trail:
`compiler/0.0.241/WIP.md` §4.

### A14 · root-caused (0.0.241) · native logits diverge from the reference with prefill position

Premise: native `p("The") = 0.251` vs llama.cpp `0.847`, top-10 overlap 1/10,
argmax agrees. Measured: the Q6_K dequant is **bit-exact** (0 ULP, real kernel
via a shim — prime suspect refuted), the tied output projection is exact
(max 2.7e-14), and forward positions 0-2 agree to corr 0.988-0.9997 against
llama.cpp on identical ids. The first clear break is **between prefill positions
3 and 4** (corr 0.9538 → 0.6881) and grows with position → the defect is in
**state carried across positions** (per-layer short-conv state and/or the KV
cache), not in the Q6_K decoder or the projection. Reference row (no model
needed): `test_suites/codes/q6k_dequant_ref_test.quanta` (EXPECTED.tsv, rc 0).
**The follow-on per-layer-norm fix and its evidence live in the peer unit's
write-up — `docs/research/lfm2-perlayer-norm-defect.md` (referenced, not edited
here).** 0.0.241 trail: `compiler/0.0.241/WIP.md` §3.

### A15 · FIXED in the 0.0.242 WIP tree — `mem_free` / `drop` never wrote the free list

Same mis-encoding as the A5 IR_FREE handler (below §A5): `emitter.quanta:1995-1996`
(mem_free) and `2056-2057` (drop) emitted `48 89 5b 08` (`mov %rbx,0x8(%rbx)`) and
`48 89 1b` (`mov %rbx,(%rbx)`) instead of `48 89 43 08` (`[ptr+8] = old head`) and
`48 89 1C 25` (`[HEAP_CTRL] = ptr`), so a manual free has **never** pushed onto
the free list — it corrupted `[p]` and `[p+8]`. `lib/std` calls `mem_free` in 13
files. `test_suites/codes/mem_free_test.quanta` passes rc=0 on both compilers
because it never inspects the free list. Fixed in the 0.0.242 WIP (not promoted,
same gate-RED reason as A5). Discovery trail: `compiler/0.0.242/WIP.md` §3.

### A16 · FIXED (0.0.243 tooling) · `stdlib_rag_search_gate_test.quanta` flaked RED under load — a row whose colour was decided by the page cache

The row imports `std/rag` + `std/str` and fork+execs `scripts/rag_search_file.py`,
a sqlite-vec vec0 KNN over the 21 GB `/opt/tali/ti/ai/rag/vectors.db`, TWICE
(search + the determinism re-check). `quanta_run.sh` capped it at the global
`QUANTA_TIME_S=15`, which is sized for a small in-process test: this row's runtime
*is* the disk read, so it is green or red by host page cache and machine load, not
by the code under test. It flaked `expected rc=0, got rc=124` in two separate gate
runs — `/tmp/gate_full.log:638` (2026-10-15 14:29) and
`/tmp/verify_release_gate.log:638` (2026-10-16 01:38).

Measured 2026-10-16 on this box — governor `powersave` (~2.2-2.8 of 5.4 GHz), load
10-14 with an ambient `Hermes` process at ~747-752 % CPU, recorded because the
numbers below mean nothing without it; cold paths forced with
`sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches'`:

| what | measured |
|---|---|
| full row at the 15 s cap, cold | **rc=124**, WALL 15.03 s |
| `rag_search_file.py` alone (one KNN) | cold **16.86 s** / warm **2.11 s** |
| full row, DB cold (n=2) | **18.54 s**, **18.80 s** |
| full row, everything cold (n=1) | **66.54 s** |
| full row, warm | 2.1-3.8 s |

Fix: `test_suites/scripts/run_tests.sh` gained a per-row wall-clock budget
(`stdlib_time_budget()`); this row is declared at **120 s**, ~1.8x the worst
measured cold path and still bounding a genuine hang. Every other row keeps the
15 s default and an explicit `QUANTA_TIME_S` still raises all of them. Demonstrated
green under load: see `/tmp/vr_healthy_gate.log` (A17's run).

### A17 · FIXED (0.0.243 tooling) · `scripts/verify-release.sh` read a healthy tree as RED — the version arithmetic assumed consecutive versions

Check 2 required `<NEXT> == <VER> + 1 patch`. With `compiler/0.0.242/` committed as
an unpromoted WIP (its own `WIP.md` says DO NOT PROMOTE; root `VERSION` stayed
0.0.241), the next promotion 0.0.243 is **two** patches above the frozen baseline
0.0.241 — so the check named the unpromoted WIP as the predecessor and failed. The
reported run was **12 passed / 2 failed** (`compiler/0.0.243/WIP.md`, "FAIL 1"),
and every real check passed: 0.0.241 rebuilds bit-for-bit (md5 `02b15543…`) and the
committed 0.0.243 binary **is** the seed-chain fixed point built from 0.0.241
(`26430066…`).

Fix: check 2 now asserts ORDER — same major.minor, `<NEXT>` a strictly later patch
than `<VER>` — and prints every committed tree in between as an unpromoted WIP.
`<VER>` was already the explicit predecessor (`arg 2`, default `cat VERSION`); it is
no longer assumed to be `<NEXT>-1`. Proving `<VER>` is the *right* seed remains
check 6 (the seed chain must close on the committed binary) and still fails loudly.
Demonstrated: healthy `0.0.243 0.0.241` → **11 passed / 0 failed, exit 0** (gate
skipped); a deliberately mismatched binary (8 bytes flipped) in a sandbox copy of
the two trees → **9 passed / 2 failed, exit 1** (check 6 and check 7, both naming
the mismatch). Nothing under `compiler/**` was touched.

### A18 · FIXED (0.0.243 tooling) · `test_suites/scripts/gguf_corrupt_gate.sh` ignored `QC=` and tested a compiler nobody handed it

The script resolved `compiler/$(cat VERSION)/bin/x86/qc` itself, and
`run_tests.sh` did not even pass `QC=` to it — unlike security / perf / generics /
multi-tu / qobj_gate, which all do. A WIP gate (QC=0.0.243, VERSION=0.0.241)
therefore compiled its probe with the OLD qc and reported
`FAIL gguf-corrupt: real probe did not compile: line 2511: error: call to
undeclared function: dq6`, `gguf-corrupt : RED`
(`/tmp/gate243.log:646` and `:715`, 2026-10-16 00:46) — RED until VERSION was
bumped, i.e. it measured the wrong compiler.

Fix: `QC="${QC:-$REPO/compiler/$(cat "$REPO/VERSION")/bin/x86/qc}"`, and the harness
now passes `QC="$QC"`. Demonstrated 2026-10-16 02:20 (load 14.57): handed the
0.0.241 qc the stage now fails with the same `undeclared function: dq6` — proof it
uses the compiler it is handed, where before it used VERSION's. The same pattern in
the qobj chain the gate drives is fixed in the same commit: `scripts/g4_verify.sh`
and `scripts/g4_transitive.sh` now read `qobj_write.quanta` from the handed
compiler's own tree (fallback VERSION), and `scripts/promote.sh` honours `${QC:-}`
for its seed. **Recorded, not fixed** (a separate defect, out of this fix's scope):
`GGUF_RC` and `FPR_RC` are computed and printed in the gate summary but are absent
from the exit condition (`run_tests.sh:888`), so a RED there cannot fail the gate —
gate243.log shows `gguf-corrupt : RED` in a summary whose exit could not be
non-zero. **Also recorded:** `scripts/g6_selfcache.sh:13` pins its source fixture
with a literal `V=0.0.217` (rule #1), overriding the `V=$(cat VERSION)` on the line
above it.

### A19 · FIXED here (lib/std + gate script) · the loader could ask for every core; and the gate ignored two of its own REDs

Two independent defects, both about "a resource/check that is not bounded".

**A19a — resource politeness (lib/std).** The loader's worker count was whatever
the caller passed: `mm_set_workers(20)` on a 20-core box spawned 20 workers, and
the SI loop runs this unattended. Measured first, not assumed
(`tests/park_cpu_probe.quanta`, `/proc/<pid>/task/*/wchan`): a **parked** pool
does **not** spin — with 8 workers spawned and no job submitted, every worker is
state `S` / wchan `futex_do_wait`, `num_threads=9`, and the process costs
**0.00 % CPU over an 8 s park** (0 ticks, external and in-process). So the CPU a
run costs is the CPU its workers *spend*; the fix is a **ceiling**, not a wait
loop. `mm_set_workers`/`mm_set_embed_workers` now clamp to
`min(affinity_cores/2, 8)` (floor 1), with explicit escapes
`mm_set_workers_uncapped(n)`, `QUANTA_MM_WORKERS=n`, `QUANTA_MM_ALL_CORES=1`
(the env is read from `/proc/self/environ` by hand — `getenv()` is a stub,
`emitter.quanta:3879`). `mm_pool_ensure` also refuses `n > 512` and fails closed
on a NULL protocol word. The per-call `mm_matvec_par(...,nw)` is deliberately not
clamped (the A9 gate row's 20-way leak guard depends on it).

Measured before/after (`tests/lfm2_polite_bench.quanta`, 4 `fc_forward_token`,
`/usr/bin/time -v`, `nice 0`, governor `powersave`, ambient `Hermes` 747 %):
BEFORE (HEAD lib, 20 workers) **831 % / 21.0 s**; AFTER default (asked 20 →
**8** workers) **563 % / 26.95 s**; AFTER `QUANTA_MM_ALL_CORES=1` (20 workers)
**827 % / 21.2 s**. RSS 112–115 MB. Good citizenship (`/tmp/citizen.sh`, a
concurrent 2.3 s single-threaded task, n=6): idle median 2.334 s → **8 w 3.055 s
(1.31×)** → **20 w 3.731 s (1.60×)** — the neighbour always made progress, and
the polite default is ~18 % kinder to it. The loader is **bandwidth-bound**
(20 workers use ~8.3 cores, not 20), so `% CPU` plateaus; the cap bounds it on
smaller boxes. Full data: `docs/research/loader-resource-politeness.md`.

**A19b — the gate ignored two of its own REDs (gate script).** `run_tests.sh`
printed `gguf-corrupt` and `float-print` in the GATE SUMMARY, but `GGUF_RC` and
`FPR_RC` were absent from the exit condition (the old line 888). Every other
stage folds into `FUNCTIONAL_RC` at its definition or is named in the exit test;
these two did neither, so a RED there could not fail the gate — the same
"cannot fail" class A18 *recorded but did not fix*. Fix: name both in the exit
condition. Red-first shown (a `QC=` shim that fails only the gguf real-probe
turns the whole gate exit non-zero; green run exits 0).

**Gate.** `tests/lfm2_polite_pool_test.quanta` +
`tests/run_lfm2_polite_pool_test.sh` (model-free, three env cases, all PASS);
`tests/lfm2_mm_workers_zero_test.quanta` still `WORKERS0 PASS`; full gate
**228/228 native, 0 compile-fail, STDLIB 111/111** with the new default. No
compiler file changed → VERSION stays 0.0.243 (prefill precedent).

### A20 · FIXED here (lib/std) · the tokenizer stalled on a 10 KB prompt — an `O(id)` vocab walk at every pre-token boundary

`tests/lfm2_prefill_bench.quanta` tokenizes the real SI-loop prompt (10,890 B)
and never returned; reproduced on HEAD-lib and current binaries, so it is
pre-existing. It was already on the record unowned — `loader-resource-politeness.md`
§6, "*a real item for whoever owns the BPE path*".

**Located exactly:** `bpe_special_match()` in `lib/std/lfm2_bpe.quanta`, called
once per pre-token boundary by `bpe_encode_special()` (the path the bench and the
generator use). It called `bpe_rec_at(bpe_vocab, id)` for each special's bytes,
and `bpe_rec_at` **walks the packed vocab from index 0** (`O(id)`). The model has
**124 CONTROL/USER_DEFINED specials whose ids sum to 15,494,358**, so every
boundary paid ~15.5 M record-steps. The length sort in `bpe_build_specials()` did
the same walk `O(cnt²)` times *at init*.

**Which of the three it is: (b), a genuinely slow scan — not (a), not (c).** It is
linear in size with a ~32 ms/byte constant (doubling the input doubled the time,
×2.13 and ×1.79, not ×4), because the cost is `(#boundaries) × sum(special ids)`
and `#boundaries ∝ bytes` whatever the content. Nothing was quadratic in size, and
it is not one bad input (a same-length content-uniform buffer behaves the same).

Measured, single shot, load ~11–12 (`powersave`; ambient `Hermes` 748 %), via the
new tokenizer-only driver `tests/lfm2_tok_bench.quanta`
(`tests/run_lfm2_tok_bench.sh`):

| bytes | plain ms | **special ms** | special µs/byte |
|---|---|---|---|
| 1 024 | 1.481 | **32 619.3** | 31 854.8 |
| 2 048 | 2.824 | **69 468.6** | 33 920.2 |
| 4 096 | 7.367 | **124 134.5** | 30 306.3 |
| 10 890 | 18.942 | **355 305.5** | 32 626.8 |
| 40 960 | 51.575 | **1 332 519.2** | 32 532.2 |

**Fix:** `bpe_build_specials()` now dereferences each special's bytes **once** into
`bpe_special_len` / `bpe_special_ptr` (the same walk it already had to do to sort
by length), and the sort moves all three arrays together; `bpe_special_match()` is
a byte compare against those arrays with no vocab walk. Same list, same
descending-length order, same first-match-wins ⇒ same longest match.

**After** (min of 7 runs, load 9.8–11.4), prompt vs a same-length content-uniform
input so ns/byte measures size and not content:

| bytes | ids | plain ms | special ms | plain ns/B | special ns/B | speedup |
|---|---|---|---|---|---|---|
| 1 024 | 341 | 1.378 | 2.209 | 1 345 | 2 157 | **14 767×** |
| 4 096 | 1 309 | 4.706 | 7.814 | 1 149 | 1 908 | **15 886×** |
| 10 890 | 3 638 | 12.991 | 25.963 | 1 193 | 2 384 | **13 685×** |
| 40 960 | 13 754 | 55.088 | 88.775 | 1 345 | 2 167 | **15 010×** |

Sum over the five sizes **1,914.0 s → 0.129 s (14 815×)**. **Linear now**: special
ns/byte flat in a 1.25× band across a 40× range (uniform: 1.28× band).

**Byte-for-byte id equality with llama.cpp** (the standard): every prefix handed
unchanged to upstream's own `/opt/ai/llama.cpp/build/bin/test-tokenizer-0` —
MATCH `1024`, `2048`, `4096`, `10890` (3 638 ids), `40960` (13 754 ids) — plus the
pre-existing 26-prompt fixture row `blocks=26 ids=183 fails=0 OK bpe rc=0`.

**Row proposed, not added** (the peer owns the manifests): a
`stdlib_lfm2_bpe_special_scale_test.quanta` row in `EXPECTED_STDLIB.tsv` (rc 0,
model as the `SKIP_IF_MISSING` prerequisite) that tokenizes a ≥10 KB prompt with
`bpe_encode_special` and compares the ids to a llama.cpp fixture, inside the
per-row wall budget. PRE-fix it cannot pass (355 s at 10,890 B); POST-fix it costs
26 ms. Its source belongs in `test_suites/codes/`, which is not this unit's.

### A21 · DECIDED here (lib/std) · `fc_attn_workers`: the parallel attention body is REMOVED, and why

`fc_attn_workers` was read by `fc_layer`'s attention dispatch (`> 1` →
`fc_attention_par`) but **no code in `lib/std` ever set it**, so the path had never
run; its only in-tree fix (per-layer norm) was verified by reading alone. Decided:
**remove it** — not because it is useless, but because as written it cannot be
enabled.

**It is measurably faster.** Enabled through the only route that exists (an
importing module *can* assign the global — a scratch probe compiled and printed
`4`), a forward at `pos=1600` with 8 workers was **~1.35×** faster, three repeats
each, same `argmax_last=35808`:

| run | `fc_attn_workers=0` | `=8` | VmSize growth (3 fwd) |
|---|---|---|---|
| 1 | 8 832 ms/tok | 6 791 ms/tok | 43 184 vs 241 424 kB |
| 2 | 8 886 | 6 803 | 43 184 vs 241 424 |
| 3 | 9 226 | 6 397 | 43 184 vs 241 424 |

**But it leaks 64 MB per forward token.** 241 424 − 43 184 = 198 240 kB over 3
forwards = 66 080 kB/forward ≈ `8 attention layers × 8 threads × 1 MB` — the
per-call `thread_create` stack leak A9 already retired from `mm_matvec`. At 8
workers that is ~128 tokens before an 8 GB `ulimit -v` is gone; the SI prompt alone
is 3 638 tokens. A setter that turns it on is a leak bomb, not a speedup. The fix
is to route the body through the **persistent pool** (`pl_*` in `lfm2_mm.quanta` —
a different file on the loader's critical path, and one lever per version), so it
is queued, with the ~1.35× recorded so the work is not re-derived.

**Removed:** `fc_attention_par`, `patt_worker`, the `patt_*` globals (268 lines),
`let fc_attn_workers = 0`, and the dispatch's `> 1` branch (now an unconditional
`fc_attention` call, with the reason in the comment). Behaviour-preserving by
construction: the branch required a value nothing ever set.

Full trail + the reproduction (the driver needs the pre-removal tree to set the
global; `tests/lfm2_attn_pos_bench.quanta` is the same harness without it):
`docs/research/fc-attn-workers-removal.md`. **Stale docs that still say
"left as-is / dead code"** (NOT this unit's files): `loader-resource-politeness.md`
§5, `threaded-forward-defect.md` §8.3, `lfm2-perlayer-norm-closeout.md` §3,
`prefill-batching.md`, `plans/lfm2-native-inference-perf.md`.

**Gate.** Full gate after both fixes:
**229/229 native, 0 compile-fail, STDLIB 111/111, all 24 stages GREEN** (the row
count is 229, not 228 — a peer added a row to `EXPECTED.tsv` this round, in
`08f2f9c1`/`6896004a`; a rising count is not a regression). No compiler file
changed, so VERSION is left at the peer's **0.0.244** and self-hosting is
unaffected — the compiler does not import `std/lfm2_*` (`grep` of
`compiler/0.0.244/src/`).

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

---

### Post-report findings (measured, not yet numbered above)

Full trails: `compiler/0.0.239/WIP.md` and `compiler/0.0.240/WIP.md`.

- **`lib/std/lfm2_chat.quanta`** - `chat_build` wrote a literal backslash-n where the template renders a
  real newline, and mis-transcribed the thinking tag (7 bytes, token id 124901); the driver called
  `bpe_encode` (no special-token matching) and prepended no BOS. Fixed, it reproduces llama.cpp's
  `/tokenize` byte-for-byte (23 ids).
- **`lib/std/rag.quanta`** - did not compile at all (`undeclared variable: config` + SIGILL), and assumed
  `exec()` returns - it is `execve` and replaces the process image, so the capture design was impossible.
- **Open:** a top-level `const` with a float initialiser evaluates to 0; `tokenizer_trait.quanta` still
  calls `bpe_encode`; native logits are flatter than the reference (p('The') 0.251 vs 0.847, 1/10 top ids
  shared, argmax agrees), with the unchecked **Q6_K** output projection as prime suspect.

---

### A22 · MEASURED here (audit, no code change) · the P2 auto-free blocker is now enumerated: 115 of 406 let-bound `lib/std` `mem_alloc` sites escape, 199 of 329 free sites double-push — ship needs the bounded interprocedural escape analysis, not a simple rule

Full trail: `docs/research/a22-mem-alloc-escape-audit.md` + the analyser
`docs/research/a22-escape-audit.py` (static, text-level, re-runs in ~2.6 s, no compilation — every
number regenerable). Answered the question A5 left open ("escape/alias detection does not exist"):
**how many `mem_alloc` sites let the pointer escape its scope?**

- The rule audited is the one the **0.0.242 WIP detector** fires on: `let x = mem_alloc(...)` direct
  initialisers, any block depth, freed at every block exit (loop bodies per iteration) and on every
  `return`. The **0.0.245 shipping line still has the old dead detector**
  (`parse.quanta:1460-1471`, the A5 field bug) — nothing auto-frees today; enabling means porting
  the 0.0.242 fix forward.
- `lib/std`: 564 sites / 49 files. Let-bound (P2's reach): **406 — 185 L (46 %), 221 (54 %) escape
  or double-free**: R 44 (returned as the function's value — `big`, `sha3`, `json`, `gguf`, `str`
  value modules), S 51 (41 written into caller-owned out-params via `w64`/`mem_store` — the
  SPIFFE/TLS/HSM out-param idiom; 12 into global-backed holders), Pr 15 (6 retainer fns:
  `config_expand` + 5 `gguf_ctx_set_*` that store the param into the long-lived ctx), G 6 (verified
  store lines: `keystore_master_key = master_key` x2, `keystore_entries = new_entries`,
  `mt_key/mt_val`, `mtls_ctx = ctx`), F 106 (explicit frees). 13 non-L sites sit inside loop bodies
  (per-iteration UAF). Corpus-wide let-bound: 1780 sites, 285 escape-or-double-free.
- **A simple escape rule ("in a return / assigned to a global") is unsound**: it covers 50 of 115
  and misses the 41 out-param stores and 15 retainer passes — the classes that broke the 26 gate
  rows in 0.0.242 §5b.
- `mem_free`/`drop`/`free` audit (329 sites, 13+7 files, encoding correct since 0.0.243): **0
  same-path double-frees, 0 use-after-frees today** (the raw MULTI-FREE/UAF hits dissolved under
  path analysis — exclusive error paths and re-bindings). But **199 sites free a let-bound alloc**
  (each = double free-list push under auto-free), **23 free a PARAM** (callee-frees contract —
  needs caller ownership cancellation too), and **11 `free()` sites are munmap**
  (`emitter.quanta:1235-1241`; `fmt.quanta:13` under auto-free would push an unmapped pointer onto
  the free list — SIGSEGV or silent corruption). Note `w64(p,v)` ≡ `mem_store(p,v)`
  (`helpers.quanta:8`) — every `w64(holder, ptr)` is a pointer escape the eye skips.
- **Recommendation:** implement the bounded interprocedural escape analysis before shipping —
  (a) direct-return analysis (arg-passes to readers are fine; the 0.0.242 return-ordering fix),
  (b) store-into-longer-lived-holder detection (`mem_store`/`w64` into param/global holders),
  (c) position-sensitive retention summaries to a fixpoint (6 retainer fns cover all std Pr sites),
  (d) explicit free cancels ownership, locally and via callee-frees, (e) loop-body sites checked
  per iteration (13). Anything not provably owned keeps today's leak behaviour (safe). The 26 gate
  rows of 0.0.242 §5b are exactly these classes; `tests/raii_autofree_test.quanta` stays out of
  EXPECTED.tsv until this lands. Not "keep parked": the blocker A5 named is now specified to the
  site, and the analysis is small enough to be a compiler pass (the Python prototype is the spec).
- Verified by reading: all 6 G stores, all 15 Pr sites + their retainer bodies, the 3 munmap sites,
  the R+F pair in `log_leaf_hash`, the L shape of `fs.open` (the case 0.0.242 §4 proved sound), and
  both SEQ-DOUBLE-FREE candidates (false positives — re-assignment between frees). Unverified and
  labelled so in the report: the 1495 L sites are spot-checked shapes, not one-by-one reads; the 1
  top-level site (`big.quanta:763`) is excluded (detector reach at top level unknown).

### A23 · FIXED in 0.0.246 (compiler) · a parameter whose name lexes as a reserved keyword was SILENTLY DROPPED — and it was misdiagnosed as a `closure_call` codegen fault

Found while chasing why the loader's JIT kernel could not be dispatched from an imported module.

The handed-down diagnosis was wrong. `closure_call` codegen is correct: the emitted byte
sequence is byte-identical at both sites (inline `main` @`0x40ab75`, `jit_f_apply` @`0x40c973`) —
`48 8b 10 / 4c 8b 50 08 / 4c 8b da / mov -0x60(%rbp),%rdi / mov -0x68(%rbp),%rsi / 41 ff d3`.
The module boundary was a red herring. gdb at the fault: `rax=0x7ffff7fe6000`, **`rdi=(nil)`**,
`RIP` = the JIT entry, whose first instruction is `mov (%rdi),%r9` — the kernel was entered with a
**null argument pointer**.

Root cause: `jit_f_apply(as)` — `as` lexes to `TT_AS`, not `TT_ID`. `funcscan.quanta:265` recorded a
parameter only `if tk == TT_ID`, so the parameter was dropped: the function was registered with
**zero** parameters, no prologue store for the incoming `rdi` was emitted, and the body's `as`
(no `parse_primary` atom branch) compiled to the constant **0**.

Reduced to ONE import-free file, which is how it should have been filed:
- `fn f(as) -> i64 { return as }` with `f(41)` -> **0**
- `fn f(as,b) { return b*100+as }` with `f(41,42)` -> **41** (every later parameter shifts by one)
- `fn f(type) { return type }` -> **compiler SIGILL, rc=132**

The reported "SIGILL on larger TUs" was the SAME root cause, not a second defect.

Fix (0.0.246, 3 files): `is_param_name_tok(tk)` = `TT_ID|TT_AS|TT_TYPE|TT_IMPL|TT_IN`
(`helpers.quanta`); `funcscan.quanta` scans with it; `method.quanta parse_primary` rewrites a keyword
token that `vfind()` says names a bound param/local to `TT_ID` and falls through to the identifier
path — the `vfind` guard is what leaves every existing keyword path untouched (verified identical on
both versions: `(x as u8)` rc=44, `type MyInt = i64` rc=42, `for x in a[0:3]` rc=13).

Red-first rows, verified independently on both versions:
| row | 0.0.245 | 0.0.246 |
|---|---|---|
| `param_kwid_name_test.quanta` | run rc=**1** (wrong values) | rc=0 |
| `param_kwid_type_test.quanta` | **compile rc=132 (qc SIGILL)** | rc=0 |
| `stdlib_jit_dispatch_test.quanta` | run rc=**139** (SIGSEGV) | rc=0 |

Gate 231/231 native + 113/113 stdlib, 24/24 stages GREEN; self-host 4 generations identical
(md5 `094020ff498e993d4888c41965584fe4`); `verify-release` 14/0. `jit_f_setup/ready/apply` now work
from an imported module, which unblocks the loader's JIT dispatch route.

### A24 · OPEN (compiler) · a string-keyed brace literal traps the compiler (rc=132)

Minimal: `fn f() { return { "a": 1 } }` -> **compiler SIGILL, rc=132**, on BOTH 0.0.245 and 0.0.246.

Consequence: `lib/std/ast.quanta` does not build. That file also has `type` parameters, which is how
it was reached while testing A23 — fixing A23 does not make it compile. Runtime consequence: none
observed (the compiler dies before emitting), so this is a compiler-crash defect, not a miscompile.

Note the escape hatch: the compiler dies with SIGILL and no diagnostic, so the fault is currently
indistinguishable from an out-of-resources kill by exit status alone. A located error would be
strictly better even before the crash is fixed.

### A25 · OPEN (compiler, diagnostic quality) · an UNBOUND keyword token in expression position traps instead of erroring

`return type` with no binding named `type` in scope traps the compiler the same way. A23's fix
deliberately handles only keyword tokens that `vfind()` resolves to a bound name; the unbound case
falls through to a path with no atom branch and no error. Out of scope for A23, recorded so the
diagnostic gap is not lost. Expected behaviour: a located "undeclared name" error.

### A26 · FIXED (0.0.248) · f16/f32 parameter and return annotations were SILENTLY IGNORED — every function boundary re-widened to f64

Same failure class as A23: a declared type is dropped without an error, and the divergence is
invisible at the call site.

Evidence: `compiler/0.0.247/src/x86/globals.quanta:500-501` allocate `fn_parft` and `fn_retft` as
2 MB tables that **nothing reads or writes** — grep finds only the declarations and their comment.

Probe against 0.0.247, with the language's own f32 storage as the oracle (no hand-computed
constants, so a bug in the probe's arithmetic cannot fake a pass):

    fn id32(x: f32) -> f64 { return x }
    fn ret32() -> f32 { return 1.0000001 }
    let w: f32[2] = mem_alloc(2)
    w[0] = 1.0000001                              // the f32-ROUNDED value
    f64bits(id32(1.0000001)) != f64bits(w[0])     // fires -> the param is NOT narrowed
    f64bits(ret32())         != f64bits(w[0])     // fires -> the return is NOT narrowed

- control `fn id64(x: f64) -> f64 { return x }` does not change the value, so the harness is sound.
- Measured: param drop `exit=4`, return drop `exit=5`. `ret16()` was not reached in either
  ordering — untested rather than assumed.
- Both probes compiled with **rc=0**: this is a silent semantic divergence, not a compile error.

Impact: "binary32 precision" holds for buffers and inline code and is lost the moment a value
crosses a function boundary — the callee computes in f64. The loader's f32 kernels would diverge
from ggml's f32 path with no visible cause. Blocks adopting f16/f32 across any call boundary, which
is every real use (e.g. a KV writer taking an `f16` value).

**FIXED in 0.0.248.** The declared type is now recorded and applied at both ends of the boundary:

- `scanfns` writes `fn_parft` (1 = f32, 2 = f16) from the parameter annotation; the new
  `scan_floattypes()` writes `fn_retft` from `fn_rettype_name` (the token after `->`, the same
  (offset,len) pair `scan_retstructs`/`scan_retbig` read, so the index cannot drift).
- codegen's `IR_PARAM` narrows the incoming value in the CALLEE (single RNE rounding) and tags the
  parameter vreg; `IR_RET` narrows a declared return in the callee; `parse_call_impl` and the
  post-aclr re-derivation tag a call result with the callee's declared float type so chained
  arithmetic stays in binary32.

THE CALLING CONVENTION (the design point this bug forced, now documented and pinned): an f16/f32
argument crosses the boundary as its **widened f64 carrier** in the ordinary ABI register — rdi,
rsi, rdx, rcx, r8, r9, then the stack from arg 6 — and the callee narrows it once. Narrowing in the
callee is not a stylistic choice: parse and emit are fused per function and a callee can be emitted
before any call site exists, so the declared signature is the only sound source of truth. A return
is narrowed in the callee and comes back the same way in rax. Nothing sub-word is ever in flight, so
caller and callee have no width to disagree about. `test_suites/codes/f32_f16_calling_convention_test.quanta`
pins it on RAW 64-bit patterns (read with `f64bits`, no arithmetic) in every register slot and on
the stack, with the mixed f64/f32 calls asserting the neighbours are untouched, and with the width
discriminators named explicitly (a 4-byte convention would deliver 0; a raw-bits convention would
deliver 1065353217 where the carrier 4607182419336888320 belongs).

Red first, on the same rows:

    0.0.247   a26_f32_f16_paramret_test          exit 4     (param not narrowed)
              f32_f16_calling_convention_test    exit 10
              f16_single_round_test              exit 11
    0.0.248   all three                         exit 0

Completion is tracked as `docs/plans/language-capabilities.md` #11; landed in 0.0.248.

### A27 · OPEN (compiler 0.0.247) · `clock()` costs 5,148 ns per call — it mmaps, syscalls and munmaps every time

`clock()` is a compiler builtin (`emitter.quanta:3142`: "clock() -> i64 nanoseconds, CLOCK_MONOTONIC …
Zero-arg. Internal mmap(16) timespec, clock_gettime(1, b…"). It allocates a 16-byte timespec with
**`mmap` per call and `munmap`s it again** — so the language's only timer costs about five
microseconds to read, wrapping a syscall that costs 135 ns.

Measured (profiling unit, same box): `clock()` **5,148 ns/call**; one raw `clock_gettime`
(`syscall(228, …)`) into a caller-supplied timespec **135 ns**. **38× overhead**, and it is paid per
mark, so an instrumented hot path measures the instrument.

Impact: fine-grained profiling is impossible — the instrument costs more than most operations being
instrumented. `lib/std/gguf_mm.quanta:1129-1147` documents this and then **works around it**: the
loader's profile marks use `mm_prof_now_b()`, a raw `clock_gettime` syscall, explicitly "Not clock()".
That is a workaround forced by a builtin, which is exactly the class of thing that should be fixed in
the language instead (`docs/plans/language-capabilities.md` #15).

Expected: `clock()` should read the clock without allocating — a direct syscall, or the vDSO clock
where available. The nanoseconds contract and CLOCK_MONOTONIC semantics stay identical.

### A28 · OPEN (compiler 0.0.247) · adding a STATEMENT can change a function's inferred return type, breaking unrelated callers

Found when a timer was added to the forward path: binding `mm_matvec(...)` to an untyped `let`
propagated an **f64 format tag into `fc_short_conv`'s return type**, so the gate's
`stdlib_lfm2_conv_test` **stopped compiling** — a change to an unrelated function's type signature,
caused by adding a local.

Impact: a function's apparent type depends on its statement list in a way that is not local. Adding
instrumentation (or any binding) can silently change what callers see, so the failure surfaces far
from the edit — here the gate caught it, which is the system working, but only because the row
happened to compile against that function.

Same family as A26: a type tag travelling where the source does not say it does. Expected: a
function's return type is determined by its declaration or its returned expression, not by an
unrelated local's inferred format.

### A29 · OPEN (compiler, all versions up to 0.0.248) · a HEX literal with more than 8 digits is SILENTLY WRONG

Found while writing the f16 rounding constant `2^41 - 1` as `0x1FFFFFFFFF`. The compiler emitted
`movabs $0x1fffffff000000ff` instead, so the rounding mask was wrong — a silently wrong constant in
exactly the kind of code that must be bit-exact.

Measured on 0.0.247 (0.0.248 is the same code path; this is not a regression introduced by 0.0.248):

    println(0xFFFFFFF)       -> 268435455              correct (7 digits)
    println(0xFFFFFFFF)      -> 4294967295             correct (8 digits)
    println(0x100000000)     -> 1152921504606846976    want 4294967296       (0x1000000000000000)
    println(0x1FFFFFFFFF)    -> 2305843004918726911    want 2199023255551    (0x1fffffff000000ff)
    println(0x123456789A)    -> 1311768464867721370    want 78187493530      (0x123456780000009a)
    println(2199023255551)   -> 2199023255551          correct (the DECIMAL path is fine)

The pattern is exact and mechanical: the first 8 hex digits are placed in the HIGH 32 bits and the
remaining digits in the LOW bits (`1FFFFFFFFF` -> `1FFFFFFF` << 32 | `FF`), i.e. the accumulator is
not multiplied by 16 per digit past the eighth. No diagnostic, and `0x100000000` — the smallest
9-digit case, the one a user is most likely to write — is wrong too.

Impact: any >32-bit hex constant in user code is silently wrong. Same class as the f16 casts and
the dropped declarations this version is about: the value is plausible, the compile is clean, and
nothing points at the literal. The workaround in-tree is to build large constants from shifts
(`ri(0,1); rshl_imm(0,41); rdec(0)` in the 0.0.248 f16 routine), which is exactly the kind of
workaround the language should not require.

Expected: match the decimal path — an exact accumulation, with the >INT64_MAX case failing closed
as TT_BIGNUM (the lexer already has that path). Fixing it needs its own red-first row and its own
version; it was NOT fixed in 0.0.248 because it is a separate lexer lever and this version's subject
is the f16/f32 boundary.

### A30 · OPEN (compiler, all versions up to 0.0.248) · one 17-digit decimal literal does not round to the nearest f64 (1 ULP low)

Found while hunting a witness for the f16 double-rounding defect: the f64 value had to be pinned by
its bit pattern first, and the pattern did not match the correctly rounded one.

Measured on 0.0.247 (same path on 0.0.248; not a regression):

    f64bits(4997.9998123605865)  -> 4662217373610405594   (0x40B385FFF3B3EEDA)
    correctly rounded f64        -> 4662217373610405595   (0x40B385FFF3B3EEDB)   1 ULP HIGH
    f64bits(0.30000000000000004) -> 4599075939470750516   correct
    f64bits(1.0000000000000002)  -> 4607182418800017409   correct
    f64bits(1234567890123456.0)  -> 4832797072101665536   correct
    f64bits(0.1)                 -> 4591870180066957722   correct

So this is not a blanket "17 significant digits are truncated" limit (three other 17-digit literals
round correctly); it is a specific input where the decimal -> binary conversion loses the last bit.
The correct expectation is the nearest f64, round-half-even, which is what every C/Rust/Python
`strtod` produces and what the compiler's own `fl_dexp2f64` produces for the other cases above.

Impact: a literal can differ from the value the source says by 1 ULP, silently — the hardest kind of
numeric bug to attribute, and it invalidates any test that uses a long decimal literal as an exact
oracle. The 0.0.248 f16 tests therefore build their witnesses from bit patterns
(`f16bits_to_f64`) and exact powers of two rather than from long decimals, and assert every literal
they do use against `f64bits` first.

Expected: exact nearest-even conversion for every literal length the lexer accepts, with the
17-digit case included in a fixture-driven row (compare against the host compiler's own strtod over
a generated set). Not fixed in 0.0.248 — it is a front-end conversion lever of its own, and fixing
it inside the f16/f32 work would mix two subjects in one version.

### A31 · OPEN (compiler, 0.0.248) · `adistinct` writes back the home slot of every operand it evicts — ~50% of a hot loop is marshalling

`adistinct(res, a1, a2)` (`emitter.quanta:473-488` in 0.0.247, `:499` in 0.0.248) evicts every
allocation entry bound to `a1` or `a2`, and for each one does
`if r8(vr_init+ev_vr)!=0 { wbp(spill_home(ev_vr), pr) }` — it **stores the operand's live value to its
home slot**. 36 call sites in `codegen.quanta`.

The operands are still live, nothing clobbers their registers, and nothing reads those slots before
the next write — so the stores are dead, and the operands' next use simply reloads them.

Emitted-byte evidence (`arith`, `i*7`): stores to both operand homes at `0x14b`/`0x153`, `imul` at
`0x15e`, later reload of `i`. Not read from source — read from the object.

Measured: **loop-restricted home-op share 33-59%, median 50.7%, against 0.0% in every C twin**, and
**30-67% of those stores are provably dead** (cyclic dead-store walk: arith 15/26, div_const 18/29,
heavy_div 10/17, heavy_float 8/21, float 13/43, regpressure 68/101).

This also corrects a recorded belief: the register pool never fills *because this empties the map on
every binary op*, so residency never accumulates. The lever is "stop evicting live operands", not
"choose better victims".

Decisive control experiment: `s+i*7`, `s+i*8`, `s+i*3` and `s+i/8` all emit **exactly 45
instructions** — the three multiplies are byte-identical apart from the immediate (normalised md5
`1a89553d7e`) and the divide differs only by `sar` vs `imul`. **One add costs what one mul costs what
one sar costs.** The arithmetic is not slow; the marshalling is.

Fix prerequisite already audited: all 20 direct `spill_home` readers in `codegen.quanta` are guarded
(16 inside a `flush_all` scope, 2 self-protected by an explicit write-then-read) — 0 hazards.

### A32 · OPEN (compiler, 0.0.248) · the float register allocator is dead code — and enabling it as written would corrupt the caller's frame

`fphys()` is defined at `emitter.quanta:786` with **zero call sites** (grep returns only the
definition). So FP values live in general-purpose registers and round-trip through `xmm` on every
operation — 17 such round trips in `float`'s hot loop alone.

Worse, it cannot simply be switched on: **`fspill_home` writes ~8 KB below `%rbp` while the frame
reserves 1120 bytes**, so enabling the float allocator as written writes outside the frame. The
frame/offset mismatch is the prerequisite.

This is why `float` (**127 vs 8 = 15.9x**) and `heavy_float` (**65 vs 6 = 10.8x**) are the worst
*honest* rows in the suite: both sides are scalar with no vectorisation, so the entire gap is
allocation and marshalling.

### A33 · OPEN (compiler, 0.0.248) · `loop_depth` is never incremented, so the integer-overflow trap fires in every loop

`codegen.quanta:1446` declares `let loop_depth = 0` and **nothing ever increments it** (grep finds
only reads, at `:1520` and `:1894`). The guard's intent was to skip the overflow trap inside loops;
with `loop_depth` stuck at 0 it never suppresses, so `jno; ud2` is emitted on every integer
add/sub/mul/neg — measured at 21% of `regpressure`'s loop body.

**This is a SEMANTICS decision, not a plain fix.** The trap exists to catch real overflow; deleting it
would trade correctness for speed, which is the opposite of this project's standing. The right shape
is a language-level *unchecked* region so the author can state "this cannot overflow here" — tracked
as `docs/plans/language-capabilities.md` #18, and it follows from the standing policy that the
LANGUAGE capability ships first rather than the trap being quietly removed.

**CORRECTION (phase 2, measured on 0.0.249) — the capability already exists, and the dead guard is the
defect.** `unsafe{}` already suppresses this trap AND the shift-count and index traps, per
*operation*: `ovf_trap_emit` / `shl_trap_emit` / `idx_trap_emit` are all gated on
`r8(ir_unsafe+ii)==0` (`emitter.quanta:250/256/322`), and `helpers.quanta:420` records
`unsafe_depth` for every IR op emitted inside a `unsafe{}` block. It is load-bearing today: the
compiler's own `compute_magic()` is wrapped in `unsafe{}` because its magic-number recovery does
deliberate 64-bit wraparound.

MEASURED, same probe with one line wrapped: loop body **39 -> 35 instructions (-10.3 %)** and
`ud2` in `main` **3 -> 1** (the survivor is `i = i + 1`, outside the block — the scope is exact).
The audit's 21 % of `regpressure`'s loop is the prize when the whole body is wrapped, and it is
available now.

So A33 is **not** "the language cannot express this". A33 is (a) the `loop_depth` guard is
constant-true dead code that misrepresents the compiler, and (b) **nothing tests the escape
hatch**, so it can regress silently. Design, measurement and the proposed order of work:
**`docs/research/phase2-a33-unchecked-design.md`**. Still OPEN — not landed in 0.0.249.

**RESOLUTION (measured 2026-10-18, 0.0.249): the language capability already exists — do NOT build a new one.**
`unsafe{}` already suppresses **three** traps per operation, gated on `r8(ir_unsafe+ii)==0`:
`ovf_trap_emit` (`emitter.quanta:250`), `shl_trap_emit` (`:256`) and `idx_trap_emit` (`:322`). The
construct is load-bearing — `compute_magic` depends on it. Measured: wrapping one statement in
`unsafe{}` takes a loop **39 -> 35 instructions (-10.3%)** and `main`'s `ud2` count **3 -> 1** (the
survivor lies outside the block).

So the work is not a new region type, it is:
1. red-first rows proving the trap IS suppressed under `unsafe{}` **and** that it still SIGILLs
   without it;
2. **delete the constant-true `loop_depth` guard** (byte-identity must stay 239/239 identical);
3. only then consider `unchecked{}` as a second spelling.

**Never wire `loop_depth` up** — that would silently re-enable the suppression the author never
asked for, and the flag is dead for a reason.
