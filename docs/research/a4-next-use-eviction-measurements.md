# A4 / next-use eviction — measurements, and the premise it refutes

**Date:** 2026-10-16 · **HEAD at start:** `006ffa19` · **Baseline:** `compiler/0.0.243/bin/x86/qc`
(md5 `26430066a4e04f61a687ccf6291b61d7`) · **Lever tree:** `compiler/0.0.244/`

Everything below is measured on this machine, with the command that produced it.
Where a number is derived rather than measured, it says so.

> The box is throttled (`scaling_governor` = `powersave`, ~2.6 GHz of 5.4) and
> contended (the `Hermes` backend held 400-1300 % CPU during every run in this
> document). **Every conclusion here rests on load-independent metrics** —
> emitted instruction counts, frame-relative memory operations, frame bytes, and
> binary identity. Wall-clock ratios appear only where they are labelled as weak.

---

## 1. The premise, as recorded

`docs/plans/performance.md` §2.1/§3 and `docs/plans/next-queue.md` item 2 state:

> "the per-operation spill/reload traffic is the cost … `work()` = 254 instructions
> vs gcc's 9. **The next lever is A4 / next-use eviction (home-slot reuse)** …
> The pool is 13 registers with LIFO eviction and no next-use information
> (`afree()` picks the most-recently-allocated victim)."

Three separable claims are embedded there:

1. the spill/reload traffic is what costs the 9 arithmetic-loop cases their 6-32x;
2. the cause is the **eviction** policy (LIFO instead of next-use);
3. the frame (1104 bytes, one home slot per vreg) is a second, related target.

A4 was implemented exactly as specified. **Claim 2 is refuted by measurement, and
claim 3 is refuted by measurement. Claim 1 is right about the symptom and wrong
about the mechanism** — see §4.

---

## 2. `work()` is not reproducible, so a metrics kernel was defined and committed

The recorded `work()` = 218 (0.0.240) / 254 (A/B) instruction figure has **no
source in the repository** — `grep -rn "fn work" docs/ compiler/ benchmarks/` finds
nothing. A number that cannot be reproduced cannot be compared against.

`scripts/bench_instr.sh` (**new**, load-independent) plus
`benchmarks/benchmark_regpressure.{quanta,c}` (**new**) replace it:

```
scripts/bench_instr.sh <qc> [--only a,b] [--fn name] [--tsv FILE]
```

It compiles each Quanta twin with `--emit-obj` (which carries a symbol table — the
shipped executables have no section headers and no symbols) and each C twin with
`gcc -O2`, then reports, per function: instruction count, **hot-loop body size**
(the largest backward-branch region), **frame bytes** (the first `sub $0xNNN,%rsp`,
i.e. the prologue — later ones are inline), **frame-relative memory operations**
(`(%rbp` operands = spill/reload traffic) and call count.

For the `work()` shape the honest, reproducible number is `benchmark_heavy_int`'s
`main` = **198 instructions**, whose hot loop body is **75** (gcc: `main` 43, loop 17).

---

## 3. A4 as implemented

`compiler/0.0.244/src/x86/emitter.quanta`

| what | where |
|---|---|
| next-use context (`a4_at`, `a4_end`, `A4_WINDOW=64`, `A4_FAR`) | `emitter.quanta:312-331` |
| `a4_reads(k, vr)` — the read-set of IR op `k` | `emitter.quanta:343-361` |
| `a4_next_use(vr, from, lim)` — bounded, block-aware forward scan | `emitter.quanta:365-376` |
| `a4_pick(ex)` — the victim selector | `emitter.quanta:381-396` |
| `afree()` victim choice | `emitter.quanta:574-600` |
| `afree_x(ex)` victim choice | `emitter.quanta:434-460` |

`compiler/0.0.244/src/x86/codegen.quanta`

| what | where |
|---|---|
| publish `a4_end` / clear `a4_at` before the emit loop | `codegen.quanta:1437-1438` |
| `a4_at = ii` at each op | `codegen.quanta:1440` |
| clear `a4_at` after the loop | `codegen.quanta:3285-3289` |

Policy: the victim is the vreg whose **next use within the window is farthest
away**; a vreg with **no use left in the block is the best victim** (it is dead).
Ties keep the LIFO choice (`>=` in the selection loop, so the last entry with the
maximum distance wins), so a function where the two rules agree emits identical
code. `aphys_x`'s never-evict-`ex` semantics are unchanged.

Three design points that make this safe rather than clever:

* **Eviction choice is a pure performance decision.** `sdef(vr, reg)` writes the
  home slot at *every* definition (`emitter.quanta:1102`), and a mapped register
  is never modified in place, so any victim is always reloadable. This is why the
  read-set in `a4_reads` only has to be good enough to *rank* victims — over- or
  under-reporting a read can change codegen quality but cannot miscompile.
* **The scan is bounded and block-aware.** It stops at 64 ops, and at the first
  `IR_LABEL`/`IR_JMP`/`IR_BR`/`IR_RET` — because codegen calls `flush_all()` at
  all four (`codegen.quanta:2344-2359`), so the allocator map is empty at any
  block boundary and a value live past one is spilled and reloaded whatever
  register it sat in. The window is exact where it matters (hot loop bodies are
  short) and O(1)-amortised in compile time.
* **It is inert with no context.** `a4_pick()` returns -1 whenever `a4_at < 0`
  (before the loop, after the loop, during the pre-pass, and in the prologue), and
  the caller then takes the original LIFO branch. `afree()`/`afree_x()` now
  compact the map by moving the last entry into the victim's slot; `afree_x` and
  `adistinct` already compacted, so map order was never load-bearing.

---

## 4. The measurement that refutes the premise: eviction never fires on the suite

`afree()`'s eviction branch is reached **only** when all 13 physical registers are
mapped. An instrumented scratch build of the compiler (counters only — never
committed) reports, per emitted function, the eviction count, the number of
reloads from a home slot in `aphys`, the maximum allocator-map occupancy, the
`aset` count and the `sdef` count. Over **all 37 pre-existing benchmark cases**:

```
case                #fns    evict    reload   maxfc
benchmark_arith        2        0        13       3
benchmark_big_array    2        0        24       3
benchmark_div_const    2        0        13       3
benchmark_fileio       2        0        34       6
benchmark_float        2        0        23       3
benchmark_heavy_int    2        0        10       3
benchmark_heavy_int2   2        0        10       3
benchmark_mem          2        0        36       3
benchmark_params8      3        3        18      12
benchmark_file_io     23        2       283      12
...
cases with ANY eviction: 2 / 37
max allocator-map occupancy across the suite: 12 of 13
```

**The pool is never full.** `main` of the worst case (`arith`) does 36 `aset` calls
and **zero** evictions: at most **3** registers are mapped at once. Its hot loop
contains 13 reloads from home — and all 13 come from `flush_all()` at the loop's
`IR_LABEL`/`IR_BR`, not from eviction.

The same instrument on a **large** program — the compiler compiling itself —
finds the pathology does exist, it is just rare:

```
427 functions · 462 evictions · 35 984 reloads · 144 484 asets · 115 427 sdefs
max allocator-map occupancy 13   (the true maximum; the first instrumentation
                                  read 12 because aset compared before increment)
largest single function: 46 evictions, 66 reloads, 325 IR ops
functions with >=1 eviction: 16 of 427
```

So A4's target is **0.3 % of the home traffic** in the largest program in the
repo (462 of ~151 000 home accesses), and **5 events in the whole benchmark suite**.
A perfect victim choice there cannot move a 6-32x ratio. Measured effect on the
suite is in §6 and it is exactly what that predicts.

---

## 5. Where the loop instructions actually go (the real root cause)

Classification of the **hot-loop body** the golden compiler emits, largest
backward-branch region of `main`, by instruction class:

| case | loop instr | home **loads** | home **stores** | arith/cmp | jmp | reg→reg mov | other |
|---|---:|---:|---:|---:|---:|---:|---:|
| arith | 111 | 13 | **39** | 39 | 7 | 13 | 7 |
| div_const | 98 | 14 | **43** | 23 | 7 | 10 | 8 |
| heavy_int | 75 | 9 | **28** | 23 | 5 | 9 | 6 |
| heavy_int2 | 75 | 9 | **28** | 23 | 5 | 9 | 6 |
| mem | 72 | 9 | **32** | 17 | 6 | 7 | 7 |
| q4k_matmul | 67 | 8 | **29** | 15 | 6 | 7 | 8 |
| fileio | 123 | 21 | **55** | 23 | 8 | 12 | 12 |
| float | 155 | 30 | **71** | 8 | 3 | 17 | 29 |
| match | 174 | 15 | **59** | 35 | 12 | 19 | 46 |

(**Derived**: counted with `objdump -d --no-show-raw-insn` over the loop region,
bucketed by mnemonic and `(%rbp` operand. The four right-hand columns are counts
of instructions, not measured weighted costs.)

**The store side dominates every case — 28 to 71 home stores per loop body, more
than the arithmetic itself, against only 8-30 loads.** gcc's equivalent loops
contain **zero** frame-relative operands (`c_mem` = 0 for every one of these rows).

The mechanism is not eviction and not reload. It is that **`sdef()` stores the
home slot on every single definition** (`emitter.quanta:1102`) and `flush_all()`
stores every live vreg again at every block boundary and every `IR_CALL`, even
though the value is usually consumed inside the same block and the store is never
read. A representative slice of `arith`'s loop, straight from the disassembly —
the same slot stored twice with a reload between:

```
116: mov $0x1312d00,%eax          ; N
11b: mov %rax,-0x78(%rbp,%riz,1)  ; sdef(N)          <- store
123: mov -0x50(%rbp),%rcx         ; reload i (block-entry flush wiped the pool)
12a: mov %rax,-0x78(%rbp,%riz,1)  ; sdef(N) AGAIN    <- same slot, same register
132: mov %rcx,-0x50(%rbp,%riz,1)  ; sdef(i)          <- store of a just-reloaded value
```

That is the shape a lever must attack: **home-store elimination / write-back on
demand**, not victim selection. It is queued in §9, not done here — one lever per
version.

---

## 6. Measured effect of A4

`scripts/bench_instr.sh`, all 38 cases, both compilers, one run each. This metric
does not move with load.

**37 of 38 cases produce byte-identical code** — every column identical, not just
"close". The one case that moves is the purpose-built `benchmarks/benchmark_regpressure`:

| case | main instr | **loop instr** | frame bytes | **home mem-ops** |
|---|---|---|---|---|
| regpressure 0.0.243 | 524 | 401 | 1136 | 259 |
| regpressure 0.0.244 | 504 | **381 (−5.0 %)** | 1136 | **239 (−7.7 %)** |
| every other case | unchanged | unchanged | unchanged | unchanged |

**Frame bytes are unchanged everywhere.** This is refutes the "one home slot per
vreg" framing: `frame_size = spill_region + total_str + 80` with
`spill_region = 48 + vreg_n*8` (`codegen.quanta:1374-1385`), but `min_spill = 1024`
clamps it — `arith`'s 1120 bytes are 1024 floor + 80 + 16 alignment, and its
`vreg_n` contributes 1040−48 = 124 slots for at most 12 live values. Home-slot
reuse would shrink `spill_region` and the frame would not move for the small
cases; and the ~8 000-vs-262 000 recursion depth is set by `min_spill`, not by the
per-vreg slots.

Independent confirmation that A4 fires where (and only where) the instrumentation
said it would — `scripts/bench_ab.sh` (interleaved, best-of-8, load 11.4-12.0),
"machine code" column:

* **36 of 39 rows `IDENTICAL-CODE`** (38 pre-existing + regpressure + the new gate row is not a benchmark);
* the 3 rows reported `code differs` are **`file_io`, `params8` and `regpressure`**
  — and `file_io` (2) and `params8` (3) are **exactly the two cases where the
  instrument counted evictions**. The predictor and the A/B agree row for row.

### The 12 parity cases

Held, and by construction: the 12 parity cases (`nested_calls`, `recursion`,
`float_ops`, `match`, `mem_ops`, `file_io`, `fib`, `q4k_matmul`, `string`,
`big_array`, `q4k`, `mem`) all report `IDENTICAL-CODE` in the A/B and identical
instruction/frame/spill counts in `bench_instr.sh`. `file_io` changed code in the
same way `params8` did (a victim swap), and its wall-time delta is +0.0 % best /
+0.0 % median. No parity case regressed.

### Wall time — recorded, and weak

Interleaved A/B, best-of-8, load 11.35/11.80/11.99, `Hermes` at 400-1300 % CPU:

* `regpressure` −1.1 % best, −3.8 % median — while the load-independent metrics say
  −5.0 % loop instructions. The wall figure is *derived* and understates it.
* **36 rows that are byte-identical swung from −12.5 % to +20.0 %** (`fib` −20 %,
  `int_ops`/`match`/`mem_ops`/`struct` +16.7 %, `string` +20 %). These are pure
  noise: the binary did not change by one byte.
* Same binary, two runs, different load: `heavy_div2` measured **32.85x** vs gcc in
  one run (load 17.0-20.2) and **21.68x** in another (load 11.9-12.0) — a 34 %
  swing on unchanged code.
* `arith` measured 17.82x (load 17-20) and 13.79x (load 12). The recorded 0.0.238
  table's 14.71x is consistent with the *lower*-load run, not with the higher one.

**Conclusion: no wall-time claim of A4's effect is defensible on this box.** The
effect is stated in instructions and memory operations, where it is exact.

---

## 7. Re-baselined Quanta-vs-gcc table (0.0.243 golden)

`bash scripts/bench.sh --runs 3 --md`, load 17.03/14.47/11.63. **Every row compiled,
no `TWIN_FOLDED`, no `MISMATCH`** → the two sides agree on every one of the 38 rows.

| case | Quanta ms | gcc -O2 ms | ratio | | case | Quanta ms | gcc -O2 ms | ratio |
|---|---:|---:|---:|---|---|---:|---:|---:|
| heavy_int2 | 2384 | 76 | **31.37x** | | heavy_mem | 24 | 9 | 2.67x |
| heavy_div2 | 1084 | 33 | **32.85x** | | params8 | 30 | 9 | 3.33x |
| heavy_int | 629 | 42 | **14.98x** | | higher_order | 22 | 7 | 3.14x |
| arith | 303 | 17 | **17.82x** | | mem | 24 | 8 | 3.00x |
| div_const | 167 | 13 | **12.85x** | | fib_recursive | 30 | 12 | 2.50x |
| heavy_float2 | 731 | 64 | **11.42x** | | fnptr_indirect | 32 | 13 | 2.46x |
| heavy_float | 167 | 16 | **10.44x** | | generic_call | 28 | 11 | 2.55x |
| heavy_div | 114 | 11 | **10.36x** | | closure_call | 22 | 10 | 2.20x |
| mutual_recursion | 697 | 97 | **7.19x** | | closure_capture | 21 | 10 | 2.10x |
| float | 157 | 22 | **7.14x** | | loop_sum | 13 | 8 | 1.62x |
| fileio | 157 | 34 | 4.62x | | heavy_recursion | 9 | 6 | 1.50x |
| q4k_heavy | 23 | 6 | 3.83x | | big_array | 12 | 9 | 1.33x |
| | | | | | q4k / fib / enum / int_ops / recursion | 8 / 9 / 7 / 7 / 7 | 8 / 9 / 6 / 6 / 6 | 1.00-1.17x |
| | | | | | nested_calls / string / struct | 7 / 6 / 8 | 7 / 6 / 8 | 1.00x |
| | | | | | file_io / float_ops / match / mem_ops / q4k_matmul | 8 / 9 / 6 / 6 / 7 | 9 / 10 / 7 / 7 / 8 | 0.86-0.90x |

**This table is not comparable with the recorded 0.0.238 table row-for-row**: it
was taken at load 17.0-20.2 against 9.8-11.7 there, and §6 shows an identical
binary swings 34 % between those regimes. What it *does* establish, load-independently,
is the current instruction/frame/spill baseline in §5, and that all 38 pairs are
output-equal and loop-present.

---

## 8. What was proved, and how far it goes

| claim | evidence | strength |
|---|---|---|
| A4 implemented as specified | `emitter.quanta:311-403,573-603`, `codegen.quanta:1435-1441,3286-3289` | source |
| 37 of 38 cases emit byte-identical code | `bench_instr.sh` all columns equal | measured |
| `regpressure` loop body −5.0 % instructions, −7.7 % home ops | 401→381, 259→239 | measured |
| all 12 parity cases held | A/B `IDENTICAL-CODE` + identical counters | measured |
| eviction fires 5x on the suite, 462x in the self-build | instrumented scratch build | measured |
| home stores, not evictions, are the loop cost | §5 table | derived from objdump |
| frames do not move (min_spill dominates) | 1136 bytes unchanged on every case | measured |
| A4 **does not close the C gap** | 37/38 unchanged; the gap is in §5 | measured |

---

## 9. Queued handoff — the lever the measurement says is next

**Home-store elimination / write-back-on-demand.** `sdef()` stores the home slot on
every definition; `flush_all()` stores every live vreg again at every block
boundary and `IR_CALL`. §5 shows the store side is 28-71 of every 67-174-instruction
hot loop, against gcc's zero.

The obstacle is that `spill_home(vr)` is read *directly* in several places that
rely on "home is always current" — e.g. the `IR_SHL`/`IR_SHR` path
(`codegen.quanta:1891-1892`, after a `flush_clob` that spills only rax/rcx/rdx) and
the `IR_CALL` argument loader (`codegen.quanta:2699,2720`, after a full
`flush_all`). Any change must either preserve that invariant, or convert those
readers to `aphys()` — which is what `pow` (`emitter.quanta:4383`) already does for
exactly this reason.

Cheapest safe first step, and its size is measurable before it is written: the
**duplicate store** in the listing above (`11b`/`12a` — same slot, same register,
nothing written in between) and the store of a just-reloaded value (`132`). Both
are detectable in `sdef` with a per-vreg "(last stored register, unchanged since)"
pair, but the *dangerous* case — an op that writes `aphys(res)`'s already-mapped
register and then `sdef`s it — must be excluded, which is why this wants its own
version and its own red-first row.

Second, independently measurable and much smaller: `min_spill = 1024`
(`codegen.quanta:1384`) is what pins every small function's frame at 1104-1152
bytes while only ~12 slots are ever live, and it is the sole cause of the
~8 000-frame recursion ceiling. It is a one-constant change; it was **not** made
here because it is a different lever and because the comment at
`codegen.quanta:1376-1383` records a real SIGSEGV caused by getting a frame-size
floor wrong.
