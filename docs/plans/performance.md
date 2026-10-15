# Compiler codegen performance — fix-forward series from 0.0.234

**Goal:** close the measured runtime gap between Quanta-generated code and `gcc -O2` on the project's own
benchmark suite, without regressing the parity cases and with the full gate GREEN (819/819 rows, 24 stages),
`SELFHOST 7/7`, and the per-version fixpoint md5 recorded. Never by adjusting a golden to match the code
(`docs/RELEASE_CHECKLIST.md` rule #17).

**Base:** `VERSION` = `0.0.233` (HEAD `a449d1a8`, tree clean).

> **Sequencing — do not start this series yet.** Every verified defect is fixed first, from 0.0.234, in
> `docs/plans/bugs.md` (standing instruction: bugs, then speed). Two of those defects are *compiler crashes on
> valid input* and one is `print` on `f64`, which is how this suite's own twins got written wrongly — measuring
> codegen through a broken `print` produces numbers that have to be redone. When the bug pass lands, the series
> below starts at whatever `VERSION` is then; the ordering and the levers are unchanged.
**Version numbers are allocated at release time** (`cat VERSION` + 1, per `RELEASE_CHECKLIST.md` §9) — the
numbers below are the intended order, not pre-promised artifacts. One release = one lever, each landed and
verified on its own.

**Supersedes:** the 2026-10-12 draft that lived here (`100x slower than C`, `no register allocation`). Its
claims are corrected in §2.3 from measurement; the draft is recorded as removed in `docs/INDEX.md`.

> **STATUS 2026-10-14 (0.0.238) — the first codegen lever landed, and it REFUTES this document's premise.**
> The 0.0.235 item (constant division/modulo by strength reduction) shipped as **0.0.238**. Removing
> essentially every hot-loop `idiv` — plus the dead `sar`-then-`idiv` double work the old power-of-two path
> emitted, which meant constant division *never* actually got the shift — bought only **0-12 %** on the 12
> benchmark rows whose machine code changed (`heavy_int` −12.2 %, `div_const` −10.2 %, `heavy_int2` −7.3 %,
> best-of-15 interleaved A/B via `scripts/bench_ab.sh`, load ~9.8). The predicted "move toward ≤3×" did NOT
> happen: `heavy_int2` went 35.5× → 27.7×, `arith` 14.4× → 14.7×, `heavy_int` 22.0× → 22.0×.
>
> **So `idiv` was not the dominant cost**, and §1.1's causal claim is wrong. The per-operation spill/reload
> traffic is the cost — §2.1 already measures it: `work()` = 254 instructions vs gcc's 9. **The next lever
> is A4 / next-use eviction (home-slot reuse), not more division work.** Caveat that applies to every ratio
> in this document: 25 of 37 suite rows emit byte-identical code across that change and still swing ±17 %,
> and every row under 30 ms is noise-dominated — see `benchmarks/BENCHMARK.md` tables 3-4. The version's
> full evidence is `compiler/0.0.238/WIP.md`.

---

## 1. Measured baseline — the existing suite on 0.0.233

Source: `benchmarks/` (**30** `.quanta` cases — 29 with C twins — plus `BECHMARK.md`, written Sep 2026 at
0.0.212) — adopted as the benchmark home, **but the directory is currently gitignored: only `BECHMARK.md` is
tracked, so all 30 cases are invisible to git and absent from a clean clone** (see §4.1). Survey run 2026-10-13, one run per case, both sides through
`scripts/qcrun.sh`, load 11.6 → 12.1 on 20 cores (so treat single-run ratios as ±20%; the runner in §4.2 does
min-of-3 interleaved).

| case | Quanta | gcc -O2 | ratio | | case | Quanta | gcc -O2 | ratio |
|---|---|---|---|---|---|---|---|---|
| heavy_int2 | 1893 ms | 76 ms | **24.9×** | | heavy_mem | 27 ms | 12 ms | 2.2× |
| div_const | 179 ms | 9 ms | **19.9×** | | mem | 29 ms | 17 ms | 1.7× |
| heavy_int | 539 ms | 31 ms | **17.4×** | | q4k | 11 ms | 7 ms | 1.6× |
| arith | 242 ms | 16 ms | **15.1×** | | big_array | 12 ms | 10 ms | 1.2× |
| heavy_div | 81 ms | 8 ms | **10.1×** | | q4k_matmul | 10 ms | 9 ms | 1.1× |
| heavy_float2 | 466 ms | 64 ms | 7.3× | | fib | 10 ms | 9 ms | 1.1× |
| heavy_recursion | 73 ms | 10 ms | 7.3× ⚠️ **rc=132** | | string | 9 ms | 8 ms | 1.1× |
| float | 119 ms | 17 ms | 7.0× | | match | 8 ms | 8 ms | 1.0× |
| heavy_float | 137 ms | 20 ms | 6.8× | | mem_ops | 9 ms | 9 ms | 1.0× |
| loop_sum | 20 ms | 6 ms | 3.3× | | file_io | 9 ms | 9 ms | 1.0× |
| fileio | 92 ms | 32 ms | 2.9× | | float_ops | 7 ms | 8 ms | 0.9× |
| q4k_heavy | 23 ms | 10 ms | 2.3× | | recursion | 8 ms | 10 ms | 0.8× |
|  |  |  |  | | nested_calls | 7 ms | 10 ms | **0.7×** |

**Compile failures (3):** `benchmark_enum` (`call to undeclared function: Color`), `benchmark_int_ops`
(`reserved type keyword used as a variable name`), `benchmark_struct` (`call to undeclared function: width`).
Language drift since 0.0.212, not present-day regressions — **repaired already, with `scripts/bench.sh` as the
runner (30/30 compile, exit 0)**; see `benchmarks/BENCHMARK.md` for the authoritative best-of-3 table, which is
what to quote, not this one-shot survey.

**The suite now also covers function shapes** (7 new cases: closure call, closure capture, fn-pointer
indirect, higher-order, generic call, 8-param call, mutual recursion), which immediately produced three
findings — see §0 below. Two rows stay flagged: `closure_capture` (a **compiler SEGFAULT**, marked
`known-fail`) and `q4k`/`q4k_heavy` (`-1280` vs `0`, explained by Quanta's **floor** division semantics).

- **Two independent kernels** (added during verification, core-language only, results consumed so nothing is
  dead-code eliminated): 3M-iteration float+int loop **58 ms vs 14 ms = 4.1×**; 3M-element array fill+sum
  **68 ms vs 13 ms = 5.2×**. Both land inside the cluster below, consistent with the suite.
- **Recursive fib(30)** (a case the suite does *not* cover — its `benchmark_fib` is the **iterative** fib(40),
  measured 1.1×): **25 ms vs 8 ms = 3.12×** interleaved min-of-3, outputs identical (832040). Add a recursive
  fib case in 0.0.234; recursion cost is visible where the iterative version hides it.
- **1M-iteration arithmetic + struct loop** (struct field read + `p.x*i/3` per iteration):
  **22 ms vs 10 ms = 2.20×**, outputs identical. Included because a claim of *560×* for this shape circulated;
  it is refuted here by ~250× (see §4.2).

### 1.1 The gap is bimodal — say it precisely or the plan chases ghosts

- **Parity group (12 cases, 0.7-2.3×, several already *faster* than gcc)**: `nested_calls`, `recursion`,
  `float_ops`, `match`, `mem_ops`, `file_io`, `fib`, `q4k_matmul`, `string`, `big_array`, `q4k`, `mem`.
  Nothing here needs fixing. **They are the regression guard**: any codegen change that slows these is a loss.
- **Arithmetic-loop group (7-32×)**: `heavy_int2`, `div_const`, `heavy_int`, `arith`, `heavy_div`,
  `heavy_float2`, `heavy_recursion`, `float`, `heavy_float`.

All of the group's worst cases share one thing — **integer division or modulo by a compile-time constant
inside a hot loop**:

```quanta
benchmark_div_const     sum = sum + i / 128 * 3 + i / 64 - i / 32      // 3 constant divides, all powers of two
benchmark_heavy_int2    sum = sum + i * 7 / 3                          // constant divide by 3
benchmark_arith         sum = sum + i * 7 - i / 3 + i % 5              // constant divide + modulo
```

gcc turns these into shifts or a multiply-high sequence; Quanta emits **`idiv`** (40-80 cycles, serialised
on the divisor unit) once per operation per iteration — and `-O` cannot recover it because `-O` does nothing
(§2.1). This is the cheapest, highest-yield codegen fix in the tree, and it is exactly the lesson already
recorded for the `q4k` kernels in `lib/std` (*"divisors are constant powers of two and -O is a verified no-op,
so `/64` was a real `idiv` ... 17% faster"*) — the fix belongs in the **code generator**, where it pays on
every Quanta program instead of one kernel.

The float cases (`heavy_float2` 7.3×, `float` 7.0×, `heavy_float` 6.8×) are a *different* defect: a scalar
dependency chain where each float operation costs a builtin **call** (~14 cycles: call + spill + reload +
`ret`) where gcc emits ~4 SSE instructions with `vfmadd`. Separate lever, later version, needs a numerics
decision.

---

## 2. Diagnosis, and the corrections that changed this plan

### 2.1 Verified facts about the current code generator

| fact | evidence |
|---|---|
| `-O` is **inert**: byte-identical binaries with and without it | md5 `5ddc11461291e187dc92bbbc5f3f3aaa` both ways, 0.0.233 |
| Register pool = **13** physical regs (RAX,RCX,RDX,RBX,RSI,RDI,R8-R10,R12-R15); `afree()` scans for a free one then **pops the LAST entry — LIFO, evicting the most recently allocated value**; `aphys_x(vr,ex)` refuses to evict a named vreg | `emitter.quanta` read directly |
| Loop flush hoisting **already landed (0.0.211)**: `flush_all()` before every IR op (38 sites) → loop entry/exit only — **25× on integer loops** | `benchmarks/BECHMARK.md` |
| Loop register pinning **already landed (0.0.212)** — marginal gain (~0.011 s → ~0.010 s) | same |
| Generated loop body still shows per-operation spill/reload; `work()` = **254 instructions** vs gcc's 9 | `qc --emit-obj` + `objdump -d` |
| Compiler binary is section-less/symbol-less → **unprofilable** until a symbol-ful build exists | `nm`: no symbols; `readelf -S`: 0 symtab |

### 2.2 What that means for the plan

1. The "flush per statement" phase I had planned is **already done** — do not re-do it, and do not assume the
   remaining 45 `flush_all()` sites are per-statement (they sit at control-flow boundaries).
2. "Write a register allocator" is the **wrong shape** — a pool exists; the *policy* is wrong. But it is now
   **behind** the division fix, which is cheaper and measurably bigger.
3. Pin/hoist experiments are already spent; the next scheduling lever must be a real next-use/interval policy.

### 2.3 Corrected claims from the superseded draft

| draft claim | measured verdict |
|---|---|
| "**100×** slower than C" | Not reproducible. The suite splits into **0.7-2.3× (12 cases)** and **6.8-32.3× (9 cases)**. A `gcc -O2 < 1 ms` baseline for a 100k-iteration loop is dead-code elimination, not speed — **every C twin must be proven loop-present in its disassembly**. |
| "Root cause: **no register allocation**" | Imprecise: a 13-register pool exists with a LIFO victim policy and no next-use information. |
| "10m31s for the full suite" | Consistent with measurement: 425-478 ms for a 172-line file ≈ 2.5 ms/line, and a ~10-13 min gate. The compiler is compiled by the same code generator, so every codegen win also shortens every future gate run. |
| "all 21 gates GREEN" | Stale: 24 stages / 819 rows + `SELFHOST 7/7`. |

---

## 3. The series (one lever per version, in this order)

Each version: implement → prove the new test fails against the pre-fix binary → gate GREEN → §3 fixpoint
(`gen2 == gen3`) → §2b `selfhost_consistency.sh` → §6 `verify-release.sh` → record the measured ratio → §9
promote + commit. Full protocol in §5.

### 0.0.234 — defects the new benchmark cases found (fix before any codegen work)

These are correctness/capability defects, not tuning: they block or invalidate the measurements the rest of
the series depends on.

1. **Compiler SEGFAULT — a capturing closure invoked inside a loop.** 6-line repro:
   ```
   fn main() { let y = 7
    let f = |x| { x + y }
    let i = 0
    while i < 3 { i = i + f(1) }
    print(i) }
   ```
   Neither ingredient alone crashes (closure-in-loop without capture runs; capturing closure called once
   runs — which is why the gate's `closure_capture.quanta` passes). Add the repro as a gate row **with** the
   fix, per rule #16, so the loop shape can never regress silently.
2. **No sibling-call (tail-call) elimination.** Tail-form mutual recursion: gcc turns it into a loop and runs
   40M calls in 15 ms; Quanta keeps every frame at 637 ms. The non-tail form (fair, real calls both sides) is
   9.80×. Candidate for the optimizer phase; it is the largest call-path gap measured.
3. **Recursion depth ceiling ≈ 7k frames.** Frames are **1104 bytes** (`sub $0x450,%rsp`, one home slot per
   vreg), so recursion deeper than ~7k overflows an 8 MB stack (SIGSEGV) where C reaches 200k+. Same
   spill-everything defect seen from the stack side — frame-size reduction belongs with the eviction work.

### 0.0.234 — measurement infrastructure (no codegen change)

1. **Adopt `benchmarks/` as the suite home** and wire it: a runner (`benchmarks/run.sh`) that compiles each
   Quanta twin with the current `qc`, compiles the C twin with `gcc -O2`, runs both through `scripts/qcrun.sh`,
   and prints the ratio table — **min-of-3, A/B interleaved, `uptime` recorded**, C twin verified
   loop-present.
2. **Repair the 3 drifted cases** (`enum`, `int_ops`, `struct`) so the suite covers core language again.
3. **Triage `heavy_recursion` rc=132 (SIGILL)** — a real defect, not a benchmark artefact; bisect before
   changing any codegen (the known suspects are the `ud2` integer-overflow trap and unchecked array indexing).
4. **A symbol-ful compiler build** so `perf`/callgrind can name functions (the `--emit-obj` path proves a
   symbol table is reachable). Keep it a separate build target: the shipped golden stays byte-stable and the
   bootstrap fixpoint untouched.
5. **Instruction-count harness**: `qc --emit-obj` + `objdump -d` with symbols, asserting non-empty output.
   Track `work()` (**254** now → target **< 60**) and spill/reload pairs per loop body (target 0-2).
6. Re-baseline the whole suite on the promoted 0.0.234 and publish the table in `benchmarks/BECHMARK.md`
   (regenerate; the file name's typo goes with it).

**Exit:** suite runnable in one command, drifted cases repaired, SIGILL triaged with a written finding,
symbol-ful build, corrected baseline committed.

### 0.0.235 — constant division and modulo by strength reduction

**Files:** `compiler/<NEXT>/src/x86/codegen.quanta` (IR for `/` and `%`), possibly `emitter.quanta` (`idiv`
emission), `opt`/`fconst` for the constant table.

1. Power-of-two constant divisor → `shr`/`sar` (+ correction for signed operands where the language's
   semantics require floor/truncation — **decide and document which**, this is a semantics question, not an
   implementation detail).
2. Non-power-of-two constant divisor → the standard multiply-high/shift sequence.
3. `%` by a constant → remainder from the same sequence (gcc shares one computation for `q` and `r`).
4. **Correctness first:** new gate tests asserting exact quotients/remainders for positive, negative, zero and
   boundary operands against hand-computed values (not against the old binary's output — the old output is the
   bug). Element-wise over the domain, per the project's rule about whole-domain verification.
5. Targets: `div_const` (19.9×), `heavy_div` (10.1×), `arith` (15.1×), `heavy_int2` (24.9×), `heavy_int`
   (17.4×) all move toward ≤3×; the parity group must not move.

**Exit:** measured ratios in the table above drop with the gate GREEN and hand-derived goldens; or a written
no-go. This is the expected biggest single win in the series.

### 0.0.236 — next-use eviction (the remaining loop churn)

`afree()`'s LIFO victim → choose by **next use** (scan the rest of the block; evict the vreg used farthest
away; dead values are the best victims; tie-break LIFO). Keep `aphys_x`'s never-evict-`ex` semantics (it
exists because a binary op's second operand once evicted the first and computed `x+x`). Metric: `work()`
instruction count and spill/reload pairs (§1 of the harness).

### 0.0.237 — float operations without a call per operation, and fused SSE

Attack the float cluster (6.8-7.3×): each float op currently costs a builtin call (~14 cycles) against gcc's
~4 SSE instructions. Options in order: keep values in registers across the chain, then fuse
(`vfmadd`/`vfnmadd`). **Fusing changes intermediate rounding** — requires an explicit, documented tolerance and
evidence the gate's expected outputs are unaffected. Do not claim "matches upstream" for a fused path.

### 0.0.238+ — make `-O` real, one transformation per version

The optimizer stage exists and is inert. Order: constant folding → dead code elimination (the redundant `mov`
chains visible in the listings) → loop-invariant code motion → small-function inlining (measure the threshold).
The differential stage (`-O` vs no-`-O` **identical stdout**) and the fixpoint stay green throughout. The
contract is exactly: **stdout identical, binary different and faster** — byte-identity is the bug.

---

## 4. Benchmark suite: one home, one runner

### 4.1 Home — and it must become *committable* first

Measured inventory of `benchmarks/`: **30** `.quanta` cases, **29** `.c` twins, **29** extension-less compiled
twins (stale build products), 1 results doc. **Tracked by git: `BECHMARK.md` only** — `.gitignore:19:/*` is a
root whitelist (`!/test_suites/`, `!/tools/`, `!/tests/`, `!/compiler/`, `!/docs/`, `!/lib/`, `!/config/` …)
and `benchmarks/` is **not** in it. Consequences: the suite cannot be committed, cannot be run by CI, is lost on
a clean clone — which is exactly why it drifted to three compile failures and why nothing referenced it.

**0.0.234 task:** make it committable, consistent with how the other root dirs are handled —
`!/benchmarks/` + `!/benchmarks/**` in `.gitignore` (mirroring `!/tools/**`), plus `benchmarks/*_c` to keep the
compiled twins out, and **delete the 29 stale binaries already on disk**. Alternative if you prefer no new root
entries: move the suite under `test_suites/benchmarks/` (already whitelisted). Either way the case files must be
tracked or this plan's numbers can never be reproduced by anyone else.

It is *not* a core gate stage: rule #12 defers stdlib, and these are core-language programs — a performance
suite, not gate rows. Its role is the regression guard for every codegen change.

**Not duplicates — do not delete:**
- `test_suites/codes/bench_fib.quanta` is **recursive fib(30)** (3.12×); `benchmarks/benchmark_fib.quanta` is
  **iterative fib(40)** (1.1×). Different algorithm, different N, different measured ratios — the suite lacks a
  recursive case, so **absorb** it (with its C twin) rather than remove it.
- `tests/` is **not** an orphan: 164 files, **all tracked**, referenced by `docs/GPU_ROADMAP.md`,
  `docs/research/struct-return-defects.md`, `docs/plans/lfm2-native-inference-spec.md` ("every stage adds a
  native `.quanta` test under `tests/`"), and by `lib/std/{gguf,lfm2_bpe}.quanta` comments
  (`tests/fixtures/tokenizer_ref.txt`). It is the **inference/feature test home**, a different thing from the
  perf suite. Deleting it would break documented fixtures and the spec's stated convention.

**Genuine strays:** `benchmarks/test_avx2.quanta` — a builtin/feature test (AVX2 float builtins), no C twin, not
a measurement; move it next to the feature tests or drop it. The ad-hoc kernels written during verification
(`bench_arith`, `bench_mem`) fold into `benchmarks/`.

### 4.2 Runner rules (non-negotiable, each learned on this box)

- **A/B interleaved in ONE process**, min-of-3: run-to-run spread is ±20% at load ~10-12 on 20 cores, wider
  than most effects being chased. Two sequential runs cannot resolve a 17% change.
- Record `uptime` with every run.
- **Every C twin must consume its result and be verified loop-present in `objdump -d`** (§2.3). This is not
  theoretical: a naive twin for the struct case (`P p = {3,5}; … s += p.x*i/3 + p.y;`) compiles to a binary with
  **zero `imul`/`idiv`** — gcc propagates the fields, folds `3*i/3` to `i`, computes the closed form and deletes
  the loop, which is how a "0.005 s" baseline (and a bogus 560×) is born. The fix is to make the values opaque
  to the optimizer (a `noinline` constructor reading `getpid()`), after which gcc emits a real loop
  (`imul` + `sar` + backward `jne`) and the honest ratio is 2.20×.
- **Repairing the drifted cases (0.0.234):** `benchmark_struct` compiles once the struct-typed parameter is
  annotated (`fn area(r: Rectangle)` — an unannotated param cannot resolve `r.width`); verified working.
- Both sides through `scripts/qcrun.sh` (hard caps, symmetric `nice`).
- Report the ratio *table*, never a single headline number: the bimodal split is the finding.

### 4.3 Suite hygiene tasks (0.0.234)

Repair `enum`, `int_ops`, `struct`; add a twin-consistency check (every `benchmark_X.quanta` has a
`benchmark_X.c`); delete checked-in `_c` binaries (they are stale build products — `benchmark_*_c`,
`*_c`) and `.gitignore` them.

---

## 5. Release protocol per version (from `docs/RELEASE_CHECKLIST.md` — do not paraphrase)

1. §0 ground truth: `cat VERSION`, `git log --oneline -3`, `git status --porcelain`.
2. §1-§2 seed: `cp -r compiler/<VER> compiler/<NEXT>`; drift check `cmp` → `IDENTICAL`.
3. §2b **before touching any test**: `bash scripts/selfhost_consistency.sh` → `SELFHOST 7/7`. A self-rebuild is
   the only thing that sees source drift (that is how a broken `parse_while()` once shipped with the gate GREEN).
4. §3 fixpoint: 3-step chain, one distinct md5; record it in `WIP.md`.
5. §4 smoke → expect `exit 20`.
6. §5 gate: `ulimit -c 0 -v 8000000; QC=./compiler/<NEXT>/bin/x86/qc bash test_suites/scripts/run_tests.sh`.
7. §6 `bash scripts/verify-release.sh <NEXT> <VER>`; §7 CI pin; §8 doc sync (roadmap/quanta.md, status.json,
   SPEC.md, `WIP.md`); §9 promote (`echo "<NEXT>" > VERSION`), commit `src/`, `WIP.md`, docs, tests,
   `EXPECTED.tsv`, `VERSION`, and the tracked golden `bin/x86/qc` — never `debug/` or scratch. Push.

**Never:** hardcode the version (rule #1); write `bin/x86/qc` in place (truncates the running file to 0
bytes); run a compiled `.bin` raw; `gdb` a compiled binary; run gate/self-host jobs concurrently with compiler
edits or with each other.

---

## 6. Exit criteria and stop rules

- **Series goal:** the arithmetic-loop group ≤3× with the parity group unchanged, gate GREEN, `SELFHOST 7/7`.
- **Per version:** measured improvement on the suite *plus* an unchanged or improved parity group. A version
  that improves one row and regresses another is not landed until the regression is explained.
- **Stop rule:** two consecutive versions with no measured win means Quanta-source levers are exhausted and the
  remaining gap needs emitter builtins that consume whole blocks (the builtin-call cost model, §0.0.237's
  harder half) — a different project, planned separately.
- A change that cannot be verified is **reverted and recorded with its measurement**; a reverted change is
  information.

## 7. Open questions (genuine calls)

1. ~~Signed division semantics~~ — **RESOLVED by measurement** (no decision needed): Quanta's integer division
   is **floor**, not C's truncation. Verified: `-7 / 2` → Quanta **-4** (remainder **+1**), gcc **-3**
   (**-1**). Since changing that would be a silent language break, 0.0.235 must **preserve floor semantics** —
   which makes it *easier*: a power-of-two divisor is a single `sar` (no sign-correction sequence) and modulo
   by a power of two is an `and`. Non-power-of-two constants need the floor-correct multiply-high sequence.
   Add a gate test that pins floor semantics so the strength reduction cannot silently switch to truncation.
   Evidence + the twin consequence: `benchmarks/BENCHMARK.md` §"Verified: Quanta's integer division is FLOOR".
2. **Signed modulo** likewise (`%` with negative operands) — same answer: keep floor.
3. **Where the runner lives** — `benchmarks/run.sh` (beside the suite) vs `scripts/` (the checklist says all
   shell scripts live in `scripts/`; my default is `scripts/bench.sh` calling the suite in `benchmarks/`).

## 8. Files likely to change

- `compiler/0.0.234/` … `compiler/0.0.23x/` — one per release (`cp -r` + `VERSION` bump)
- `compiler/<NEXT>/src/x86/codegen.quanta` — division/modulo IR, float chains, `-O` passes
- `compiler/<NEXT>/src/x86/emitter.quanta` — `afree`/`aphys*` policy, `idiv`/shift emission, fused emission
- `compiler/<NEXT>/src/x86/{opt,fconst,objfmt,elf}.quanta` — optimizer passes, symbol table for profiling
- `benchmarks/` — repaired twins, `BECHMARK.md` → regenerated results, runner
- `test_suites/codes/*`, `test_suites/EXPECTED.tsv` — new gate tests for every fix
- `compiler/<VER>/WIP.md`, `docs/status.json`, `docs/roadmap/quanta.md`, `docs/SPEC.md`, `VERSION`,
  `.github/workflows/ci.yml`, `docs/INDEX.md`

---

## Correction (appended by the campaign lead, after 0.0.244): A4 is IMPLEMENTED and its premise is REFUTED

`0.0.244` ships next-use eviction (nearest-use-farthest victim, dead-in-block values first, `>=` keeps LIFO ties,
bounded 64-op block-aware scan; `emitter.quanta:312-331/343-361/365-376/381-396/574-600`, `codegen.quanta:1437-1440,3285-3289`).
It is correct and semantics-preserving. It also has almost nothing to act on, measured:

- **Evictions across the whole 37-case suite: 5** (`file_io` 2, `params8` 3). The compiler's own 427-fn self-build:
  462 evictions out of 144,484 allocations. `arith`'s `main` peaks at **3 of 13 registers mapped — 0 evictions**.
  The pool never fills, so victim selection cannot be the 6-32x cost.
- **The real cost is home-slot STORE traffic:** home stores per hot-loop body are **39 / 43 / 28 / 55 / 71**
  (`arith` / `div_const` / `heavy_int` / `fileio` / `float`) against **gcc's 0**. `sdef()` stores the home slot on
  every definition, and `flush_all()` re-stores every live value at each block boundary **and at every `IR_CALL`**.
  **That is the next lever** (obstacle to name up front: direct `spill_home()` readers in the SHL/SHR and IR_CALL paths).
- **The frame is NOT gated by per-vreg slots.** `min_spill=1024` clamps `spill_size = 48 + vreg_n*8`, so `arith`'s
  1120 B is floor+alignment and the ~8,000-vs-262,000 recursion depth is set by that constant. Shrinking `min_spill`
  is the recursion-depth lever; home-slot reuse would not have moved it.
- **`work()` = 254 instructions has no source in the tree** and was not reproducible (earlier notes quoted it).
  The reproducible kernel is `heavy_int` `main` = **198** instructions, loop 75.

**Method, because this box cannot be trusted for wall time:** `scripts/bench_instr.sh` reports instruction, frame and
spill counts. 37 of 38 cases emit **byte-identical code** under 0.0.243 vs 0.0.244 and all 12 parity cases hold;
`regpressure` (one of the three that changed) went 401 -> 381 instructions (-5.0 %) and 259 -> 239 home mem-ops.
Meanwhile 36 byte-identical rows swung **-12.5 % to +20.0 %** in wall time, and the same binary gave `heavy_div2`
32.85x at load 17-20 and 21.68x at load 12 — so instruction/frame/spill counts are the evidence and ratios are not.

---

## Next lever (appended after 0.0.245): cross-block liveness

Home-store elimination (0.0.245, write-back on demand) cut suite-wide home stores 3,395 -> 1,963 (-42.2 %)
and loop instructions 11.7-18.6 % with frames and loads unchanged. What remains in the hot loops is the
boundary flush: `flush_all()` re-stores every live value at each block boundary and every `IR_CALL`, and
some of those values are **dead** in the successor block. Cross-block liveness (is this vreg read again
after this boundary?) is the next lever; the divmod floor-semantics row that caught the miscompile during
0.0.245's development is the existing red-first guard for the whole home-store invariant.
Also note: the gate command documented in this file ran with `ulimit -v 6000000`, which is below the
compiler's ~6.2 GB floor and once produced 229 spurious compile-fails; it is 8000000 now. Use 8 GB.
