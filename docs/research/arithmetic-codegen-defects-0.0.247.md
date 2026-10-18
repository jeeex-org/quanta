# Arithmetic codegen defects — measured on 0.0.247

Phase 1 of the arithmetic-codegen campaign. No compiler change was made: this
document is measurement and design only.

- Repo `/opt/tali/quanta`, HEAD `9c1e96ef`, `VERSION` **0.0.247**.
- Instrument of record: `scripts/bench_instr.sh` (load-independent instruction
  counts). Box: governor `powersave`, load 9.4–18.9, `Hermes` backend holding
  9–11 cores. Wall clock is quoted only where labelled weak.
- `compiler/0.0.248/` exists as an **untracked** directory (a peer unit is
  creating it); `VERSION` was still 0.0.247 at the end of this phase, so phase 2
  was not started.

Raw artefacts beside this file: `suite-instr-0.0.247.txt` / `.tsv` (whole-suite
metrics), `bench-0.0.247.md` (timing run), `hotloop-census-0.0.247.txt`
(per-case hot-loop classification).

Every number below is labelled **MEASURED** (produced in this session, command
given), **DERIVED** (arithmetic on a measurement), or **PROJECTED** (an estimate
for a change that has not been made). Nothing is inherited unlabelled.

---

## 1. Suite-rot audit: all four reported items are already fixed, and one was never true

| reported | verdict | evidence |
|---|---|---|
| `benchmark_enum`, `benchmark_int_ops`, `benchmark_struct` "fail to COMPILE" | **REFUTED** | MEASURED: all three compile `rc=0` with `-O` and produce a non-empty `--emit-obj` artifact. Whole-suite `bench_instr.sh` run reports **0 COMPILE_FAIL across 38 cases**, and `scripts/bench.sh` prints `# OK: every row compiled and every C twin kept its loop.` |
| 29 stale `benchmark_*_c` binaries checked in | **REFUTED** | MEASURED: `ls benchmarks/*_c \| wc -l` = **0**; `git ls-files benchmarks/ \| grep -c '_c$'` = **0**; `git ls-files benchmarks/ \| wc -l` = **77** = 38 `.c` + 38 `.quanta` + `BENCHMARK.md`. `.gitignore:107` already contains `benchmarks/*_c`. |
| `bench_fib.quanta` duplicated in `benchmarks/` and `test_suites/codes/` | **REFUTED** | MEASURED: md5 `ef73f38e…` vs `e1a89c14…` — different files. `benchmarks/benchmark_fib.quanta` is **iterative** fib(40); `test_suites/codes/bench_fib.quanta` is **recursive** fib(30). This is the documented near-duplicate trap: similar names, different algorithms, different measured ratios. |
| `tests/` holds ~100 orphan files | **REFUTED** | MEASURED: `git status --short -- tests/` empty; `git ls-files --others --exclude-standard tests/ \| wc -l` = **0**; 254 files tracked. |

Provenance of the two real fixes: commit **`1c3cc7bf` "bench: repair four
drifted/folded twins, raise the small-row resolution floor, add a compiler A/B
harness"** repaired the drift and added the `.gitignore` line (its comment names
the `/*` root-whitelist trap explicitly). Nothing is left to do on this list.

**These premises were stale, not hypothetical.** The brief also inherited "3
drifted cases fail to compile" as a fact about the current tree. It is a fact
about a tree older than `1c3cc7bf`. Re-measured before work: no rot.

### 1b. What the audit *did* find (real, and not in the brief)

1. **`benchmarks/BENCHMARK.md` is stale**: line 5 says "Current VERSION:
   **0.0.244**" against a tree at 0.0.247, and its only tables are 0.0.237/0.0.238.
   Fixed in this commit (recorded as table 4, not by rewriting history).
2. **The fold guard is blind to two whole classes of unusable C twin** — see §3.2.
   Not fixed here (`scripts/bench.sh` is outside this phase's write scope); filed
   as a recommendation.
3. **21 of the 30 looped C twins use a 32-bit `int i` counter against Quanta's
   i64**, which is what licenses gcc's 8-wide vectorisation — see §3c. Not
   changed here; it moves every ratio in `BENCHMARK.md`, so it is sequenced as
   its own baseline commit.

### 1c. What is genuinely *clean* (so phase 2 does not re-chase it)

- **All 38 rows compile and run, every output matches its C twin**, zero
  `MISMATCH`, zero `TWIN_FOLDED`, zero stale `known-fail` markers. The oracle's
  structural guards are green today.
- **Constant-division strength reduction is present and correct** — verified per
  case, not assumed (§6). `div_const`'s hot loop has no `idiv`; the single `idiv`
  in that object is the inlined itoa printer's `/10`.

---

## 2. Confirmation of the lead: the gap is marshalling, not arithmetic

The handoff hypothesis was "the arithmetic is not slow, the spilling is". **The
disassembly confirms it, and names the exact mechanism.** Two corrections to the
framing are also measured below.

### 2.1 The frame (question (a): per-function or per-vreg?)

`codegen.quanta:1374-1385`:

```quanta
let spill_region = 48 + vreg_n * 8          // vreg_n = the FUNCTION's total vreg count
let frame_size = spill_region + total_str + 80
let min_spill = 1024
if spill_region < min_spill { spill_region = min_spill; frame_size = spill_region + total_str + 80 }
```

MEASURED: the frame is **per-function**, sized from the function's total vreg
count and floored at **1024 bytes**. It is not sized from live ranges. Prologue
(`sub $0x460,%rsp`) matches `q_frame` exactly for every case.

MEASURED frame utilisation (deepest `(%rbp)` slot touched in the hot loop, from
a cyclic slot walk over the emitted listing):

| case | frame (q_frame) | deepest slot used | live slots in loop | utilisation |
|---|---|---|---|---|
| arith | 1120 | -0xf0 (240 B) | 15 | 21 % |
| float | 1120 | -0x148 (328 B) | 27 | 29 % |
| div_const | 1120 | -0x100 (256 B) | 17 | 23 % |
| heavy_div | 1136 | -0xc0 (192 B) | 11 | 17 % |
| heavy_float | 1136 | -0xe8 (232 B) | 15 | 20 % |
| regpressure | 1136 | -0x390 (912 B) | 70 | 80 % |

So for a normal arithmetic loop **75-83 % of the frame is never touched**; the
1024-byte floor dominates. `regpressure` (written to exceed the register pool)
is the only case that nearly fills its frame.

Note the floor is also the recursion-depth clamp (an 8 MB stack / 1120 B ≈ 7.1 k
frames) — it is not free to reduce, and **the frame is not the performance
problem**. It is one store-address base, and a smaller frame buys nothing at
runtime.

### 2.2 The stores (question (b): how many are home writes, and how many are provably dead?)

There is no second spill mechanism: **home slots *are* the spill mechanism**, so
every in-loop store to `(%rbp…)` is a "spill" in the ordinary sense. What matters
is whether it is needed.

MEASURED, cyclic dead-store analysis over each hot-loop body (a write with no
read before the next write of the same slot, treating the body as a cycle, since
a store at the end *is* read at the top of the next iteration):

| case | loop body | home writes | **provably DEAD** | home reads | read immediately after a write of the same slot |
|---|---|---|---|---|---|
| arith | 98 | 26 | **15 (58 %)** | 13 | 3 |
| div_const | 84 | 29 | **18 (62 %)** | 14 | 4 |
| heavy_div | 52 | 17 | **10 (59 %)** | 8 | 5 |
| heavy_float | 65 | 21 | **8 (38 %)** | 13 | 4 |
| float | 127 | 43 | **13 (30 %)** | 30 | 11 |
| regpressure | 310 | 101 | **68 (67 %)** | 33 | 8 |

**30-67 % of hot-loop home stores are provably dead.** Deleting them changes no
value: nothing reads the slot before it is overwritten. This is the safest lever
on the board.

### 2.3 Residency (question (c): why doesn't a 13-register pool hold a 3-5 variable working set?)

**Because the mapping is destroyed on almost every operation, not because the
pool is too small. `emitter.quanta:473-488`:**

```quanta
fn adistinct(res, a1, a2) {
    let f=afind(res); if f>=0 { if f!=a1&&f!=a2 { return f } }
    // evict everything mapped to a1 or a2 so the result cannot reuse them
    let i=0
    while i<allocfc {
        let pr=r64(alloc+i*16+8)
        if pr==a1||pr==a2 {
            let ev_vr=r64(alloc+i*16)
            if r8(vr_init+ev_vr)!=0 { wbp(spill_home(ev_vr), pr) }   // <-- STORES A LIVE OPERAND
            w8(vr_spill+ev_vr, 1)
            ...unlink the entry...
        } else { i=i+1 }
    }
```

`adistinct` is called at **30 sites** in `codegen.quanta` — every arithmetic,
compare, bitwise and shift op. Because `a1`/`a2` are the two register operands
just obtained by `aphys(a0)`/`aphys_x(a1,a0)`, this loop evicts **both operands of
the operation it is about to emit**. The operands are still live (`rr(rd,r1)`,
`ra(rd,r2)` run *after*), the operation does not clobber their registers, and
nothing reads their home slots in between. So the store is pure waste, and the
operand's next use then reloads it — this is the store/load pair the instrument
sees.

**The mechanism is confirmed from emitted bytes, not from the source.**
`benchmark_arithmetic`'s `i * 7` (0.0.247, `main`):

```
 13f: mov    $0x7,%eax              <- IR_CONST for the literal 7, mapped to rax
 144: mov    -0x50(%rbp),%rcx       <- aphys(i): i was UNMAPPED, so reload from home
 14b: mov    %rax,-0x98(%rbp,%riz,1)<- adistinct evicts operand #1 (vreg of const 7)  ← WASTE
 153: mov    %rcx,-0x50(%rbp,%riz,1)<- adistinct evicts operand #2 (vreg of i)          ← WASTE
 15b: mov    %rcx,%rdx              <- rr(rd,r1)
 15e: imul   %rax,%rdx              <- rm(rd,r2)
 162: jno    166 <main+0xbc>
 164: ud2
 166: mov    -0x40(%rbp),%rax       <- reload s  (its own adistinct eviction, same op)
 16d: mov    %rdx,-0x90(%rbp,%riz,1)<- adistinct evicts the just-computed product
 175: mov    %rax,-0x40(%rbp,%riz,1)<- adistinct evicts s
 17d: mov    %rax,%rcx
 180: add    %rdx,%rcx
```

Both store addresses are exactly `spill_home` for the two operand vregs, and both
stores sit between the operand load and the instruction that consumes the
operand. Same shape at `lo_mul8` (probe): `mov $0x8,%eax; mov -0x50(%rbp),%rcx;
mov %rax,-0x98(%rbp,%riz,1); mov %rcx,-0x50(%rbp,%riz,1); mov %rcx,%rdx; imul
%rax,%rdx`.

**Correction to a recorded belief.** `quanta-cpu-perf` and
`docs/research/a4-next-use-eviction-measurements.md` conclude "the pool never
fills, so victim selection cannot be the gap". That measurement is correct and
its conclusion is *still* right for a different reason than it states: the pool
is not full, but the **map is emptied on every operation by `adistinct`'s
eviction loop**, so residency never accumulates in the first place. The lever is
not "pick better victims" (5 evictions across the suite) — it is "**stop evicting
live operands**". `adistinct`'s eviction loop is the single most-executed waste
site in the suite.

---

## 3. The oracle: 38-case instruction table and the worst arithmetic cases

### 3.1 Whole suite (MEASURED, `scripts/bench_instr.sh ./compiler/0.0.247/bin/x86/qc`)

`q_instr`/`c_instr` = instructions in `main`; `q_loop`/`c_loop` = hot-loop body
size (innermost largest-span backward branch); `q_st`/`q_ld` = home stores/loads;
`q_l_*` = those inside the loop body. Full raw output:
`suite-instr-0.0.247.txt` / `.tsv`. `q_frame` was 1104-1232 for all 38 and
`c_frame` 0-8 (gcc's arithmetic loops use no stack at all).

| case | q_loop | c_loop | ratio | q home ops in loop | **C twin vectorised?** |
|---|---|---|---|---|---|
| regpressure | 310 | 9 | 34.44 | 43.2 % | no — **algebraically collapsed** (see 3.2) |
| float | 127 | 8 | **15.88** | 57.5 % | no |
| params8 | 81 | 6 | 13.50 | 53.1 % | no |
| q4k | 62 | 5 | 12.40 | 46.8 % | yes (2) |
| match | 148 | 13 | 11.38 | 32.4 % | no |
| heavy_float | 65 | 6 | **10.83** | 52.3 % | no |
| heavy_float2 | 65 | 6 | 10.83 | 52.3 % | no |
| fnptr_indirect | 76 | 11 | 6.91 | 52.6 % | no |
| higher_order | 48 | 7 | 6.86 | 54.2 % | no |
| closure_call | 47 | 7 | 6.71 | 48.9 % | no |
| closure_capture | 47 | 8 | 5.88 | 48.9 % | no |
| generic_call | 46 | 8 | 5.75 | 56.5 % | no |
| heavy_mem | 57 | 10 | 5.70 | 47.4 % | yes (7) |
| big_array | 59 | 11 | 5.36 | 47.5 % | yes (8) |
| mem_ops | 59 | 11 | 5.36 | 47.5 % | yes (8) |
| loop_sum | 38 | 8 | 4.75 | 50.0 % | no |
| **arith** | 98 | 27 | **3.63** | 39.8 % | **yes (24)** |
| **div_const** | 84 | 23 | **3.65** | 51.2 % | **yes (20)** |
| heavy_int | 65 | 17 | 3.82 | 41.5 % | yes (14) |
| **heavy_div** | 52 | 13 | **4.00** | 48.1 % | **yes (10)** |
| heavy_div2 | 52 | 13 | 4.00 | 48.1 % | yes (10) |
| recursion | 43 | 11 | 3.91 | 48.8 % | no |
| heavy_recursion | 43 | 15 | 2.87 | 48.8 % | yes (6) |
| q4k_matmul | 55 | 20 | 2.75 | 45.5 % | yes (17) |
| fileio | 101 | 50 | 2.02 | 53.5 % | yes (35) |
| fib | 10 | 5 | 2.00 | 0 % | no |
| mem | 59 | 33 | 1.79 | 47.5 % | yes (30) |
| file_io | 10 | 8 | 1.25 | 0 % | no |
| enum, string | — | — | no loop in `main` | — | — |
| fib_recursive, float_ops, int_ops, nested_calls, struct | 10 | 0 | **not a ratio** | 0 % | no loop on either side |

**The one number that holds across the whole suite: the loop-restricted home-op
share of a Quanta hot loop is 33.1-58.7 %, median 50.7 % (29 cases with a real
loop body; loop-restricted `q_lst+q_lld` over `q_loop` from
`suite-instr-0.0.247.tsv`), and 0.0 % in every one of the C twins** — not one C
twin performs a single frame-relative load or store inside its hot loop. The
independent classifier in §2.2 agrees to within one instruction per case
(e.g. `arith` 39/98 vs the script's 40/98).

### 3.2 Consequences for reading these ratios (do not quote them raw)

1. **15 of 38 C twins are auto-vectorised by gcc at `-O2`** (arith, big_array,
   div_const, fileio, heavy_div, heavy_div2, heavy_int, heavy_int2, heavy_mem,
   heavy_recursion, mem, mem_ops, q4k, q4k_heavy, q4k_matmul). `arith`'s C loop
   is 24 of its 27 instructions of `vpaddd`/`vpmuldq`/`vpblendd` on `%ymm` and
   `vpaddq` for the accumulator — gcc handles **8 `int` lanes per loop pass**
   where Quanta handles one 64-bit iteration. So `arith` 3.63× is (scalar
   codegen) × (SIMD), *and* (see 3c) an unfair twin. **Use `float` and
   `heavy_float` as the honest scalar arithmetic cases** — both sides scalar, and
   they are the two worst non-vectorised ratios (15.88×, 10.83×).
2. **`float_ops`, `int_ops`, `enum`, `struct`, `nested_calls`, `fib_recursive`
   are loop-free programs on both sides** (verified: 8 C twins contain no
   `for`/`while` — the other two are `file_io` and `string`). `float_ops`'s C
   twin is constant-folded (`movabs $0x3fe5555555555555` — gcc computed `2/3` at
   compile time and does no arithmetic at all). `bench.sh`'s fold guard is
   skipped for a C source with no `for`/`while`, so this row prints **0.86×**
   even though gcc did no arithmetic and Quanta emitted 402 instructions of call
   sequences. It is not the "deleted loop" the brief warned about either — there
   was never a loop.

### 3c. The twins are not the same width, and that is what licenses the vectorisation

MEASURED, whole-population audit of the 30 looped C twins: **21 of 30 declare the
loop counter `for (int i = …)`** (34 such loops in total — `for (int i` ×34,
`for (long i` ×9, plus `for (int j` ×4, `for (int qi` ×3, `for (int bi` ×2)),
while every Quanta twin's `let i = 0` is **i64**. The 21 files are
`arith, big_array, div_const, fib, fileio, float, heavy_div, heavy_div2,
heavy_float, heavy_float2, heavy_int, heavy_int2, heavy_mem, heavy_recursion,
match, mem, mem_ops, q4k, q4k_heavy, q4k_matmul, recursion`. So they compute
32-bit arithmetic on the C side and 64-bit arithmetic on the Quanta side, and the
mismatch is *exactly* the licence gcc uses to vectorise 8-wide (`vpaddd`/
`vpmuldq` on 32-bit lanes; the 64-bit equivalent `vpmullq` is AVX-512-only, so a
`long i` twin cannot vectorise the multiply at all on this CPU). **All 15
vectorised rows are `int i` rows.**

Worked example — `benchmarks/benchmark_arith.c:5` vs `benchmark_arith.quanta:7`:

```c
for (int i = 0; i < 20000000; i++) sum += i * 7 - i / 3 + i % 5;   // int32 lanes
```
```quanta
while i < N { sum = sum + i * 7 - i / 3 + i % 5; i = i + 1 }       // i64
```

No overflow occurs at these bounds (`20000000*7 = 1.4e8 < INT32_MAX`), so
**the outputs are identical and the row is not miscompiled** — but the *cost
being compared is not the same computation*, and the ratio is flattered toward
gcc. `arith`'s 3.63× understates Quanta's arithmetic codegen relative to a
same-width twin.

**Deliberately not changed in this phase.** Rewriting 21 C twins is a baseline
change that moves every ratio in `BENCHMARK.md` tables 1-5 and resets the row
phase 2 will measure against, so it is a sequencing decision, not a phase-1 edit.
The mechanical fix is one token per file — `for (int i` → `for (long i` in the
loop init of each of the 21 — and the verification is `scripts/bench.sh`, which
already checks compile + output equality on every row. Recommend applying it as
its own commit **before** the phase-2 measurement campaign so the baseline is
fair; re-run `bench_instr.sh` and `bench.sh` afterwards and rewrite table 4.
The two clean cases (`float`, `heavy_float`) are unaffected in substance: their
`int i` is a loop counter whose increment costs the same either way, but they
should still be normalised for consistency.

4. **`regpressure` is not a scalar-codegen measure.** gcc recognised that t0..t15
   are all affine in `i` and reduced the whole loop to 9 instructions of `lea`
   recurrence. The row is still valuable: it is the strongest evidence of the
   *shape* of the defect (see §4.1), because for **33 source-level adds** Quanta
   emits **33 adds + 101 stores + 33 loads + 70 register moves + 66 overflow-check
   instructions**. But the 34.44× must not be quoted as a codegen gap.

Recommendation (outside this phase's write scope, filed for phase 2 or the owner
of `scripts/`): extend the fold guard to detect `%ymm` in the C `main` and report
the row as `TWIN_VECTORISED`, and report loop-free rows as `NO_LOOP` instead of a
loop ratio. A vectorised baseline is as fictional as a folded one.

---

## 4. Instructions per source-level operation (MEASURED, isolated probes)

Each probe puts exactly **one** source-level op inline in the loop body
(`while i < N { <op>; i = i + 1 }`), compiled with 0.0.247 and disassembled.
gcc's equivalent for the same shapes is 4-6 instructions.

| probe (inline op) | Quanta loop body | what the body shows |
|---|---|---|
| `s = s + i` | *instrument picked the inlined itoa loop; not measured* | — |
| `s = s + i * 7` | **45** | `imul`, no `lea` |
| `s = s + i * 8` | **45** | **`imul $0x8`, not `shl $3`/`lea`** |
| `s = s + i * 3` | **45** | `imul` |
| `s = s + i / 8` | **45** | `sar $0x3` ✓ (strength reduction works) |
| `s = s + i / 3` | **56** | magic `0x5555555555555556` + floor fix ✓ |
| `s = s + i - (i/3)*3` | **72** | magic + `imul $0x3` |
| `if i < s { s = i }` | **45** | branchy, value parked in a home slot |
| `if i > s { s = i }` | **45** | branchy |
| `s = s + abs(0 - (i % 977))` | **76** | `neg` + overflow trap |
| `s = s + (i << 3)` | **45** | `cmp $0x40,%rcx; jb; ud2` **shift-range check in the loop** |
| `s = s + (i & 255)` | **43** | `and` |
| `let j = i; s = s + j` | **38** | copy through a home slot |
| `if i < 500000 { s = s + 1 }` | **52** | two full compare sequences |
| `s = s + k * 1000` (k invariant) | **45** | **`k*1000` recomputed every iteration** |
| `f = fadd(f, i2f(i))` | **52** | 17 stores, 11 loads, xmm↔GPR round-trip |
| `f = fmul(f, i2f(i))` | **52** | same |
| `f = f + g` (FP **operator**) | **38** | `movq %rax,%xmm0; movq %rcx,%xmm1; addsd; movq %xmm0,%rdx` |

### 4.1 The decisive measurement: op *identity* does not change the cost

`i*7`, `i*8`, `i*3` and `i/8` all emit **exactly 45-instruction loop bodies**. The
three multiplies are **byte-identical apart from the immediate** (235 bytes each;
normalised instruction sequences hash equal, md5 `1a89553d7e`), and the divide
differs only in the one arithmetic instruction (`sar $0x3` where the multiplies
have `imul`) — same count, 246 bytes. So four different source-level arithmetic
operations cost the same 45 instructions.

Verdict: in the current codegen the loop cost is a function of the number of **IR
operations** (each doing its own operand marshalling), not of the arithmetic
performed. That is the direct experimental confirmation of the handoff's headline:
**the arithmetic is not slow; the marshalling is.** One `add` costs the same as one
`mul` costs the same as one `sar`.


---

## 5. Codegen defects, ranked, with `file:line`

All line references are `compiler/0.0.247/src/x86/`.

### D1 — `adistinct()` stores both live operands of every binary op. Highest impact.
```
emitter.quanta:473-488   fn adistinct(res, a1, a2)   <- the eviction loop, lines 476-488
emitter.quanta:481       if r8(vr_init+ev_vr)!=0 { wbp(spill_home(ev_vr), pr) }
```
30 call sites in `codegen.quanta` (1473, 1478, 1485, 1490, 1501, 1506, 1556,
1560, 1583, 1616, 1648, 1680, 1712, 1731, 1876, 1884-1890, 2957, 2974, 2994,
3038, 3152, 3160, 3167, 3201). Evidence: §2.3 disassembly. Measured: 30-67 % of
the resulting stores are provably dead (§2.2); the reload immediately follows.

### D2 — the float register allocator exists but is dead, so FP values live in GPRs and re-round-trip through xmm on every op.
```
emitter.quanta:747-839   FREGS / falloc / fvr_init / fphys / fdef / fspill_home
```
MEASURED: `grep -c 'fphys(' codegen.quanta` = **0**; `grep -rn 'fphys(' compiler/0.0.247/`
(excluding the definition) = **0 call sites anywhere in the compiler**. The FP
paths instead use the *integer* allocator and move bits by hand:
```
codegen.quanta:1470-1476  IR_ADD float path: aphys(a0)/aphys(a1) + fopld_rr + fst_x
emitter.quanta:846-849    fadd/fsub/fmul/fdiv — operate on xmm, but callers load via GPR
```
Emitted cost of one `f + g` (`lo_fopadd`, 38-instruction body) and one
`fmul(f, x)` (`float`, 6 instructions of real work spread over ~15):
```
 mov    -0x40(%rbp),%rax      HOME-LOAD
 mov    -0x60(%rbp),%rcx      HOME-LOAD
 movq   %rax,%xmm0            GPR->XMM      <- a float round-trips through a GPR
 movq   %rcx,%xmm1            GPR->XMM
 mov    %rax,-0x40(%rbp,%riz,1) HOME-STORE
 mov    %rcx,-0x60(%rbp,%riz,1) HOME-STORE
 addsd  %xmm1,%xmm0           the actual arithmetic
 movq   %xmm0,%rdx            XMM->GPR
```
gcc: `vaddsd %xmm1,%xmm0,%xmm0`. Measured XMM↔GPR moves per hot loop: `float`
**17**, `heavy_float` **7**.

**Latent landmine in the same block.** `fspill_home(v) = -(48 + 8192 + (v+1)*8)`
puts float homes ~8 KB below `%rbp`, but the frame formula
(`codegen.quanta:1374`) reserves `48 + vreg_n*8` with a 1024 floor and **does not
add the 8192**. Today that is harmless only because `fphys` is never called. The
moment the float allocator is wired up, the first spilled float writes ~8 KB
below `%rbp` — into the caller's frame. **Enabling D2's fix requires growing the
frame to cover `8192 + vreg_n*8` first**, or moving float homes into the same
region as integer homes with a disjoint index range.

### D3 — `loop_depth` is never updated, so the "no overflow trap inside a loop" guard is dead code.
```
codegen.quanta:1433   let loop_depth = 0                      <- only assignment in the file
codegen.quanta:1478   ... if loop_depth == 0 { ovf_trap_emit(ii) } ...
codegen.quanta:1490   ... if loop_depth == 0 { ovf_trap_emit(ii) } ...
codegen.quanta:1507   ... if loop_depth == 0 { ovf_trap_emit(ii) } ...
codegen.quanta:1881   ... if loop_depth == 0 { ovf_trap_emit(ii) } ...
```
MEASURED: `grep -n 'loop_depth' codegen.quanta` returns exactly 5 lines — the
declaration and 4 uses. There is no `loop_depth = loop_depth + 1` anywhere, so
`loop_depth == 0` is **always true**. Every integer `add`/`sub`/`imul`/`neg`
anywhere in the program pays `jno +0x2; ud2`:

```
 15e: imul   %rax,%rdx
 162: jno    166 <main+0xbc>
 164: ud2
```
Measured trap count per hot loop: `regpressure` **33** (66 instructions of a
310-instruction body, **21 %**), `arith` 5, `div_const` 5, `heavy_div` 3,
`heavy_mem` 4, every other loop 1-4.

**This one needs a decision, not just a fix** (see §7, and the standing rule that
semantics must not change): honouring the guard's evident intent removes a trap
that fires on real overflow, which *is* a semantic change for a program that
overflows in a loop. Options in §7.

### D4 — no loop-invariant code motion. Loop bounds and invariant expressions are recomputed every iteration.
```
  f6: mov    $0x1312d00,%eax        <- the loop BOUND, re-materialised at the top of every iteration
 102: mov    %rax,-0x78(%rbp,%riz,1)
 10a: mov    %rcx,-0x50(%rbp,%riz,1)
```
and for an invariant product (`lo_linv`, `s + k*1000` with `k` loop-invariant):
```
21d9: mov    $0x3e8,%eax
21de: mov    -0x60(%rbp),%rcx
21e5: mov    %rax,-0xa8(%rbp,%riz,1)
21ed: mov    %rcx,-0x60(%rbp,%riz,1)
21f5: mov    %rcx,%rdx
21f8: imul   %rax,%rdx            <- recomputed every iteration
```
MEASURED: 6-8 instructions per loop of pure invariant rematerialisation, present
in every case. gcc compares against an immediate (`cmp $0x4c4b40,%eax`) and hoists
the product. There is no separate optimizer module, so this is a new pass, not a
tweak.

### D5 — comparison results are spilled to a home slot and reloaded to branch on them.
```
 118: setl   %dl
 11b: movzbq %dl,%rdx
 11f: mov    %rdx,-0x70(%rbp,%riz,1)   <- store the boolean
 127: mov    -0x70(%rbp),%rax          <- reload it immediately
 12e: test   %rax,%rax
 131: je     2f9 <main+0x24f>
```
**Eight instructions for a loop test**, where gcc emits `cmp $imm,%eax; jne` — two.
Also present per-iteration for the `if i < s { … }` shape (`lo_min`/`lo_max`, 45
instructions each). Cause: the comparison's result vreg is not `aset()`-mapped to
the register it was computed into, so `sdef` (`emitter.quanta:1146-1158`) takes
its `afind(vr)<0` branch and stores, and the consumer's `aphys` (`:410-415`)
reloads. Same shape as D1 but one op earlier.

### D6 — multiply by a constant is never lowered to `shl`/`lea`/`add`.
```
 529: mov    $0x8,%eax
 53d: mov    %rax,-0x98(%rbp,%riz,1)
 545: mov    %rcx,%rdx
 548: imul   %rax,%rdx            <- i*8 as imul, not shl $3 or lea 0x0(,%rcx,8)
```
MEASURED: `imul` appears in every case that multiplies (`arith` 5, `div_const` 1,
`heavy_div` 1); `regpressure`'s gcc twin uses **4 `lea`s** where Quanta uses adds.
Also seen on the address path (`lo_arr`): `imul $0x8,%rcx,%rcx`. This is a small
per-op win (bytes + latency), not a marshalling win — rank it after D1/D2/D5.

### D7 — no CSE / redundant-load elimination.
MEASURED: 3-11 in-loop reads occur immediately after a write of the same slot in
each case (§2.2). Partly a consequence of D5/D1; a real value-numbering or
"register-first reload" pass is a new pass.

### D8 — shift by a variable amount carries a bounds check inside the loop.
```
18c8: mov    -0x50(%rbp),%rax
18cf: mov    -0xa8(%rbp),%rcx
18d6: cmp    $0x40,%rcx
18da: jb     18de <lo_shl+0xb8>
18dc: ud2
18de: shl    %cl,%rax
```
Two extra instructions plus a branch per shift. For a *constant* shift amount
this is provably unnecessary (the emitter could fold the check when the shift
count is an `IR_CONST`).

### D9 — cosmetic, code size only: home **stores** use the wasteful SIB form.
Stores are emitted as `mov %rcx,-0x50(%rbp,%riz,1)`; loads as
`mov -0x50(%rbp),%rcx`. `(%rbp,%riz,1)` is `(%rbp)` plus one byte, on 26-101
stores per loop body (≈ 0.5-1.5 KB of extra text per hot loop). No instruction
count effect, so it is last.

### D10 — branchless min/max/abs do not exist.
`lo_min`/`lo_max` are branchy (45 instructions); `abs` is a call-shaped sequence
with an overflow-trapped `neg` (76). `cmov`/`vpminmaxsd` are unused. This is a new
optimisation, not a defect.

---

## 6. Which candidate optimizations already exist, and which do not

The brief asked for negative results as much as positive ones. Verified by
disassembly, per case and per probe:

| candidate | already there? | evidence |
|---|---|---|
| Constant division strength reduction | **YES, and it is correct** | `div_const`'s divisor is 128/64/32 and the hot loop contains **no `idiv`** — the only `idiv` in the whole object is `mov $0xa,%ecx; idiv %rcx` in the inlined itoa printer. `i/8` → `sar $0x3`; `i/3` → magic `0x5555555555555556` + `sar $0x0` + sign fix; `i%977` → magic `0x86285a231c8f9731` + floor correction. The `op_is_iconst` guard holds. **Do not re-open this as a defect.** |
| Power-of-two divide as a shift | **YES** | `lo_div8` body: `mov -0x50(%rbp),%rax; sar $0x3,%rax`. |
| Power-of-two **multiply** as a shift / `lea` | **NO** | `imul $0x8,%rcx,%rcx` (lo_arr); `mov $0x8,%eax … imul %rax,%rdx` (lo_mul8). |
| Multiply-by-constant as `lea`/`add` chain | **NO** | same evidence; gcc's `regpressure` twin is 4 `lea`s. |
| FMA contraction | **NO** | 0 `vfmadd`/`vfmsub` in `lib/std/jit_x86*.quanta`; `float`'s gcc twin uses `vfmadd231sd`, Quanta uses `mulsd`. Changes bits — needs opt-in. |
| `*ps` (8-lane) FP forms | **NO** | every FP instruction is `*pd`/scalar `*sd`. Gated on f32 existing (0.0.247/0.0.248). |
| Induction-variable strength reduction (`i*8` → pointer bump) | **NO** | `i*8` recomputed with `imul` every iteration in `lo_arr`. |
| Loop-invariant hoisting | **NO** | §D4 — bound and invariant product recomputed per iteration. |
| Redundant-load elimination / CSE | **NO** | §D7. |
| Branchless min/max/abs | **NO** | §D10. |
| Dead-store elimination | **NO** | 30-67 % of stores provably dead (§2.2). |
| Register-pool eviction policy | partly — next-use eviction exists (0.0.244) but is **not the lever** | 5 evictions across the suite; D1 (map destruction) is. |
| Home-slot store elimination on the mapped path | **YES** (0.0.245, `sdef` writes back only when unmapped) | but `adistinct` (D1) and the unmapped comparison result (D5) bypass it. |
| Overflow trapping on integer arithmetic | **YES, by design** — but the loop exemption is dead (D3) | `jno`/`ud2` after every add/sub/mul/neg. |
| `-O` optimization-level plumbing | **NO** — `-O` is a verified no-op (`entry.quanta:211`) | one fixed optimisation level. |

---

## 7. Fix designs, in measured-impact order

Ordering is by measured instruction count that the fix can remove, not by
implementation difficulty. Expected deltas are labelled: **PROJECTED** means the
number is an estimate for a change that has not been made and must be re-measured
with `bench_instr.sh` in phase 2.

### F1 — `adistinct`: stop evicting the operands (attacks D1, D3-adjacent, D5 partly)

Delete the eviction loop `emitter.quanta:476-488`. Its stated purpose ("evict
everything mapped to a1 or a2 so the result cannot reuse them") is already
achieved by the free-register scan at `:493-502`, which explicitly skips `a1` and
`a2`, and by the degenerate branch at `:503-517`, which evicts a vreg that is
*neither* operand. The eviction loop is only reachable-as-necessary when every map
entry is an operand — impossible for more than 2 entries.

The degenerate branch needs a guard while doing this: if `allocfc` reaches 0 the
`while ev_pr==a1 || ev_pr==a2` loop at `:508-513` reads `alloc-16`. With the
resident-map change this becomes reachable, so bound it (`&& allocfc > 0`) and
fall back to a free register from `REGS` that is not `a1`/`a2` (always available,
13 registers vs 2 excluded).

- Removes per binary op: 1-2 home stores (D1) + the 1-2 home loads the operands'
  next uses no longer need.
- **PROJECTED**: `float` q_l_st 44 → ~18, q_l_ld 30 → ~14; loop body 127 → ~85
  (**-33 %**). `arith` 98 → ~65. `regpressure` 310 → ~200. To be confirmed.
- Semantics: none. Values are not observable through home slots while mapped —
  0.0.245 already made that the invariant ("home is current whenever the vreg is
  **unmapped**"). Risk: any remaining direct `spill_home` reader (i.e. a reader
  that bypasses `loadhome`/`aphys`) would now read a stale slot. Phase 2 must
  audit those readers first — `argp8` (`emitter.quanta:1172-1177`) and the
  div/shift paths are documented as already converted, but that must be
  re-verified against the current tree, because this fix is what makes it
  load-bearing.
- Red-first guard: add a gate row for the `divmod_floor_semantics_test` shape
  (already the red-first guard for 0.0.245) plus a home-slot-staleness probe;
  and re-run `bench_instr.sh` for the loop/store columns.

### F2 — dead-store elimination inside a loop body (attacks D1's residue, D5's store half)

A backward pass over each loop body: a home store with no read before the next
write of the same slot (cyclically) is dead. This is provable from the emitted IR
and removes 30-67 % of the stores that F1 does not.

- **PROJECTED**: another -10 to -20 % of loop body on top of F1; it also deletes
  the `mov %rdx,-0x70(%rbp,…)`/`mov -0x70(%rbp),%rax` pair in D5 when it can
  prove the reload is the same value.
- Semantics: none — by construction a dead store is unread.
- Safer and narrower than F1; consider landing it **first** if F1's stale-home
  audit turns out to need more work, since it is unconditionally correct.

### F3 — map the comparison result, and branch on the register (attacks D5)

`setl %dl; movzbq %dl,%rdx` already leaves the boolean in `rdx`; the store/reload
is because the result vreg is not `aset()`-mapped. Either `aset(res, rd)` before
`sdef`, or teach the `IR_BR`/`IR_JZ` consumer to take the producing register when
the comparison's result is still mapped.

- Removes 3 instructions per comparison and the store+load pair: loop test 8 → 5,
  and `lo_min`/`lo_max` 45 → ~30, `lo_cmp2` 52 → ~38.
- Semantics: none (the boolean's value is unchanged).

### F4 — keep FP values in xmm (attacks D2) — **the largest single arithmetic win, and it is gated**

Wire up the existing-but-dead float allocator (`emitter.quanta:747-839`) for the
FP paths at `codegen.quanta:1470-1476`, `1482-1488`, `1498-1504`, `1617-1624`,
etc. This removes the GPR↔XMM round-trip (`movq %rax,%xmm0` /
`movq %xmm0,%rdx`) and the operand staging for FP builtins.

**Prerequisite, in the language/compiler, not optional:** the frame formula
(`codegen.quanta:1374`) does not reserve `fspill_home`'s 8192-byte region. Wiring
the float allocator before fixing that writes 8 KB below `%rbp` on the first
spilled float. Either grow the frame by 8192 for functions with float vregs, or
re-base float homes into the same region as integer homes at a disjoint index
range.

- **PROJECTED**: `float` loop 127 → ~65; XMM↔GPR moves 17 → ~0; `heavy_float`
  65 → ~30. Combined with F1/F2/F3 this is where `float`'s 15.88× moves most.
- Semantics: need care. `faddf`/`fmulf`/`fdivf`/`i2f` results are currently
  integer-tagged vregs carrying float bit patterns; the float allocator's
  `fvr_init`/`vfloat` tagging must agree with `is_float_vr` (`emitter.quanta:628`).
  A mismatch would silently feed bit patterns to integer ops — the
  `fadd(3.0,4.0)`-returns-bits class of defect already recorded.

### F5 — FMA contraction (attacks the FP op count) — opt-in only, moves bits

`vfmadd231sd`/`vfmadd231pd` for `a*b+c` chains. `float`'s twin uses it, Quanta
cannot. **One rounding instead of two, so it moves bits** and every benchmark's
output must still match its C twin bitwise. Per the standing rule this needs an
explicit opt-in flag, not a silent replacement — `docs/plans/performance.md`
already records that decision. Gate it behind a flag whose default preserves the
current sequence, and add a bit-identity row for the affected twins.

### F6 — multiply by a constant (attacks D6)

Lower `IR_MUL` with an `IR_CONST` operand to `shl`/`lea`/`add` when cheaper.
`i*8` → `shl $3` (or `lea 0x0(,%rcx,8)`); `i*3` → `lea (%rcx,%rcx,2)`; `i*7` →
`lea` chain. Small per-op, and it is the one place where the *arithmetic* is
genuinely suboptimal — worth doing because it is cheap once the marshalling is
fixed and afterwards it will be visible.

### F7 — loop-invariant hoisting (attacks D4)

At minimum: hoist the loop bound and hoist `IR_CONST` operands whose result is
loop-invariant. 6-8 instructions per loop now, and it compounds with F1 (an
invariant parked in a register stays resident once F1 stops evicting it). This is
a new pass; scope it to "no optimizer module exists" — keep it in `codegen.quanta`
next to the existing `IR_ADD … v1==0` rewrites at `:307-353`, which are a
precedent for small inline IR rewrites.

### F8 — shift-amount bounds check for a constant count (attacks D8)

Fold `cmp $0x40,%rcx; jb; ud2` away when the shift count is an `IR_CONST` ≤ 63.
2 instructions per constant shift, semantics-preserving.

### F9 — `loop_depth` (D3): decision required, and it is a semantics change

Three options, in order of preference:

1. **Wire `loop_depth` correctly and keep the trap.** Then the guard reads as
   written and the trap is still emitted everywhere, i.e. *no* instruction
   saving. Only worth doing to make the code honest — the `loop_depth == 0`
   condition should be deleted, not fixed, if the intent is to always trap.
2. **Add a language-level "unchecked" region** (an attribute or block form) so a
   program that knows its arithmetic cannot overflow opts out — this is the
   standing policy's shape: implement the language capability, then the
   optimisation. It preserves default semantics exactly.
3. Delete the guard only in loops proven not to overflow (needs range analysis).

**Recommendation: option 2**, and *not* option 3. Option 3 silently changes
overflow behaviour inside loops — exactly the class of change the campaign's
constraints forbid. Option 1 costs nothing but also buys nothing; it is the
honest cleanup if 2 is deferred. Measured size of the prize if 2 lands: 21 % of
`regpressure`'s loop, 5-6 instructions of `arith`/`div_const`'s loops — real, but
smaller than F1/F2/F4.

### F10 — reductions with tiny payoff

Branchless min/max/abs (D10); SIB store encoding (`emitter.quanta` store emitter,
D9, code size only); `min_spill` reduction (frame size is not a runtime cost and
the floor is also the recursion clamp — **do not** spend a version on it).

### Sequencing

F2 is unconditionally correct and can land alone if F1's audit stalls. F1 is the
biggest lever. F4 is the biggest *arithmetic* lever but needs the frame fix first.
F5 needs a flag. F9 needs a language capability first, per the standing policy.
One lever per version, each with a red-first gate row, a 4-generation self-host
fixpoint and `verify-release` green.

---

### F1 PREREQUISITE — AUDITED (done here, read-only, so F1 does not stall)

F1's risk is a *stale home read*: any reader that goes straight to `spill_home()`
instead of through `loadhome()` (`emitter.quanta:540` / `:566`) or `aphys()` would
see a home slot that the 0.0.245 invariant no longer keeps current for a **mapped**
vreg. Measured, in `codegen.quanta`:

- **20** direct reads of the form `rbp(reg, spill_home(...))` (there are **87**
  direct `spill_home` reads in `codegen.quanta` + `emitter.quanta` in total,
  against only **13** calls to the safe `loadhome()`).
- **16 of the 20 sit inside a `flush_all()` scope** — they are the memory-builtin
  and call-argument paths, and `flush_all` stores every mapped vreg, so their home
  slots are current by construction. (5 share the flush at `codegen.quanta:2066`;
  3 share the one documented at `:2786`, "flush_all() above spilled every live vreg
  to its home"; the rest have their own.)
- **2 (`:1823`, `:1882`, the div/mod floor-correction paths) are self-protected**:
  each is preceded by an explicit `wbp(spill_home(res), 0)` that writes the home
  slot before reading it back (`// res home = q`).
- **0 of the 20 read a mapped vreg's home without one of those two guards.**

So F1's hazard list on the codegen side is **closed**: no direct reader depends on
a home slot that F1 would allow to go stale. The remaining 67 direct reads live in
`emitter.quanta` inside the emitter's own builtin sequences, which the same audit
pattern should spot-check per builtin — that is the one piece of F1 prerequisite
work still open, and it is bounded.

## 8. State at hand-off: 0.0.248 landed, and every defect carries forward unchanged

`VERSION` was bumped to **0.0.248** by a peer unit while this phase ran
(commit `acfd5822`, "feat(f16/f32): type parameters and returns…"). Every defect
above was re-located in `compiler/0.0.248/src/x86/` and **all of them are still
present, unchanged**:

| defect | 0.0.247 | 0.0.248 | still present? |
|---|---|---|---|
| `adistinct()` operand eviction | `emitter.quanta:473`, eviction comment `:475` | `:499`, `:501` | **yes**, identical body |
| float allocator dead (`fphys` call sites) | `emitter.quanta:760`, 0 calls | `:786`, **0 calls** | **yes** |
| `fspill_home` 8192 region unre- served by the frame | `emitter.quanta:758` vs `codegen.quanta:1374` | `:784` vs `:1387` | **yes** |
| `loop_depth` never incremented | `codegen.quanta:1433`, 0 increments | `:1446`, **0 increments** | **yes** |
| comparison result spilled | `codegen.quanta:1597-1627` | +13 lines | **yes** |
| `loadhome` (the safe reader) | `emitter.quanta:540` | `:566` | unchanged |

Line-number mapping for phase 2: **`emitter.quanta` +26 lines, `codegen.quanta`
+13 lines** from 0.0.247 to 0.0.248. All disassembly byte offsets in this document
are from **0.0.247** (`./compiler/0.0.247/bin/x86/qc`, pinned explicitly) and are
not affected by the bump.

- **`VERSION` is 0.0.248 and HEAD moved from `9c1e96ef` → `90635f1e` during this
  phase** (peers landed `acfd5822` and later commits). Phase 2 (any `compiler/**`
  edit) was **not** started, because the brief reserved the compiler slot and the
  version-tree work for a re-dispatch. No competing version tree was created.
  **The phase-2 gate is now OPEN** — `compiler/0.0.248/` is present, tracked and
  built (`compiler/0.0.248/bin/x86/qc`), and `VERSION` names it.
- The tree was dirty with peer work the whole time and it was left untouched: on
  arrival `M tests/lfm2_decode_bench.conf`, `?? compiler/0.0.248/`; during the run
  `M lib/std/gguf_mm.quanta`, `?? tests/lfm2_pool_dispatch_probe.quanta`, and an
  intermittent `.git/index.lock` from a peer's own commit. Two peer commits landed
  while this phase ran, which is also why `git pull --rebase` could not be used
  mid-phase; the phase-1 commit was pushed **fast-forward** (4 ahead / 0 behind)
  and `origin/main` was read back to confirm it (`origin/main == 3b0e7336`).
- This phase's commit: **`3b0e7336`**, 6 files, verified with
  `git show --name-status` to contain only `benchmarks/BENCHMARK.md` and the five
  `docs/research/` artefacts — no peer path was swept.
- **One untracked file is not mine and was left alone:**
  `docs/research/suite_instr_247.txt` (4950 bytes, byte-identical to the committed
  `docs/research/suite-instr-0.0.247.txt`, mtime 11:55 — i.e. written before this
  phase's own copy at 13:04, so it is most likely a peer's identically-named
  artefact). Preserved rather than deleted; the owner should confirm or drop it.
- No gate run was performed (the gate is a capacity-1 resource and the brief
  reserved it). No compiler edit was made, so no gate result is owed.

