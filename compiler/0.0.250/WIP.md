# 0.0.250 — WIP · **LEVER: F2 — dead-store elimination at the block-boundary `flush_all()`**

```
0.0.249 golden  md5 14fd1086617bb1b37a502a33c624c802   (frozen baseline, untouched)
0.0.250 g1      md5 3bcfc3de1291dd68085c8afec427bc66   (0.0.249 golden compiling the edited source)
0.0.250 g2      md5 e2f04027d8b87623da94d7df0245573b   (COMMITTED GOLDEN, = fixpoint)
0.0.250 g3      md5 e2f04027d8b87623da94d7df0245573b
0.0.250 g4      md5 e2f04027d8b87623da94d7df0245573b   (distinct(g2,g3,g4) == 1)
```

Two files changed, everything else the 0.0.249 snapshot copied verbatim:

| file | change |
|---|---|
| `src/x86/emitter.quanta` | `flush_all()` consults `f2_live_q()` and skips a store whose value no later code reads; new F2 tables + `f2_live_q()` |
| `src/x86/codegen.quanta` | new block-liveness analysis (`f2_analyze` + helpers), called once per source function before the emit loop; `f2_at` published alongside `a4_at` |

Gate-side, in the same commit: `test_suites/codes/arith_deadstore_probe.quanta`
(new row; `EXPECTED.tsv` 239 -> 240) and the new `deadstore-guard` stage in
`test_suites/scripts/run_tests.sh` (+ its summary line, folded into the exit status).

---

## 1. What landed

0.0.249 (F1) removed the per-binary-op operand eviction. The measured largest remaining
in-loop term was then the **block-boundary flush**: `IR_LABEL`/`IR_JMP`/`IR_BR`/`IR_RET`
each call `flush_all()`, which stores EVERY mapped vreg. In `arith`'s loop the back-edge
flush is 11 stores and only 2 of them (`i`, `sum`) are ever read again.

0.0.250 computes block liveness once per function and, **at the four block-boundary
opcodes only**, stores just the vregs that are live there. A mid-block flush is left
store-everything on purpose: at a mid-block point `live_out(block)` is not a superset of
"live after the flush" (a value whose last use is inside the block is live at a mid-block
point but not live out of it), so the boundary restriction is the soundness argument,
not a shortcut.

Every ambiguity degrades to "store": reads are over-reported, definitions
under-reported, an out-of-range vreg is never skipped, an escaped-home vreg (`vr_at`:
closure capture / `&local`) is never skipped, and a whole function is refused (0.0.249
behaviour) if its IR carries an op the CFG cannot model — the closure cluster (it hands
the closure the ADDRESS of a captured home, which the flush must have made current),
the try/catch/throw cluster, match/asm/FFI/vec128/capread/capwrite, an unresolved jump
target, non-convergence, tables that would not fit, or the module-cache path.

## 2. Measured effect (instrument of record: `scripts/bench_instr.sh`)

`q_loop` = hot-loop body; `q_lst`/`q_lld` = frame stores/loads inside it.
**28 of 38 benchmark rows changed codegen.**

| metric | 0.0.249 | 0.0.250 | delta |
|---|---|---|---|
| `q_instr` (whole `main`) | 8825 | 8420 | **-4.6 %** |
| `q_loop` (hot-loop body) | 2101 | 1926 | **-8.3 %** |
| `q_mem` (frame ops in `main`) | 2645 | 2240 | **-15.3 %** |
| `q_hst` (home stores in `main`) | 1859 | 1454 | **-21.8 %** |
| `q_hld` (home loads in `main`) | 785 | 785 | **+0** |
| `q_lst` (home stores in the loop) | 633 | 458 | **-27.6 %** |
| `q_lld` (home loads in the loop) | 273 | 273 | **+0** |

`q_hst` and `q_instr` both fall by **405**: every instruction this lever removes is a
home store, no home load is added anywhere, and nothing is renamed. Largest rows:
`arith` loop stores 23 -> 13, `heavy_div`/`heavy_div2` 16 -> 8, `loop_sum` 10 -> 5,
`regpressure` 81 -> 67. Full per-case table and the emitted-byte evidence:
`docs/research/phase3-f2-dse-0.0.250.md`.

## 3. Red-first row — proven RED on the previous version

New stage `deadstore-guard`: compiles `arith_deadstore_probe.quanta` with `--emit-obj`
and counts frame-relative stores/loads in the hot loop with the same AWK metric
definition as `bench_instr.sh`. Emitted bytes — exact, load-independent, no tolerance.

| compiler | loop | loop stores | loop loads | verdict |
|---|---|---|---|---|
| 0.0.249 golden (pre-F2) | 66 | 21 | 4 | **FAIL** (`66 > 60`, `21 > 12`) |
| 0.0.250 golden (F2) | 52 | 7 | 4 | PASS |

Thresholds 60 / 12 / 6 sit between the two on all three counts. Golden of the row is
hand-derived: `sum over i in 0..7 of ((i*3+1)*2 - i*3)` = `3*28 + 16` = 100.

## 4. Gate, fixpoint, verification

- **Gate** on the committed golden (`QC=./compiler/0.0.250/bin/x86/qc bash
  test_suites/scripts/run_tests.sh`): **`=== Results: 240/240 pass, 0 fail (incl. 0
  compile-fail) [rows: EXPECTED.tsv] ===`**, every stage GREEN — the new
  `deadstore-guard`, plus `marshal-guard`, `valgrind`, `fuzz` (fail-closed, 0 crashes),
  `differential` (`-O` == no-`-O` + vs-seed), `stdlib`, `security`, `performance`,
  `qobj`, `verify-status`, `f16c-indep`.
- **Fixpoint** from the frozen 0.0.249 golden: `14fd1086 -> 3bcfc3de -> e2f04027 ->
  e2f04027 -> e2f04027`; `distinct(g2,g3,g4) == 1`; the committed golden is g2.
- **`scripts/bench.sh`** (0.0.250 golden): `# OK: every row compiled and every C twin
  kept its loop.` — 0 `MISMATCH`, 0 compile failures, 0 folded twins: all 38 benchmark
  outputs still equal their C twins.
- **`scripts/verify-release.sh 0.0.250 "$(cat VERSION)"`**: **13 passed, 1 failed** at
  the time of the run — the single failure was `compiler/0.0.250/WIP.md missing`, i.e.
  this file, which did not exist yet. Re-run after writing it: **14/14**.
- **Byte-identity across the 240 gate rows**: 10 identical / 230 differing /
  0 compile-fail. See §6.

## 5. Wall clock (WEAK — labelled, not the instrument of record)

Paired `scripts/bench.sh` runs with both goldens back to back, both at load ~12
(10.4-12.6): the wall ratios move in the same direction as the instruction counts on
every row that has a real loop, e.g. `heavy_div` 3.91x -> 2.15x, `div_const`
3.38x -> 2.21x, `fileio` 2.75x -> 1.74x, `heavy_int` 6.97x -> 5.06x, `heavy_div2`
6.29x -> 4.16x, `arith` 4.32x -> 3.49x, `regpressure` 4.08x -> 3.15x.
Two rows are quoted only to show the noise floor: `heavy_float` 4.44x -> 5.31x (its
Quanta time moved 71 ms -> 69 ms, i.e. -2.8 %, while the ratio moved +19.6 % — the gcc
denominator is what moved), and the sub-10 ms rows (`fib`, `big_array`,
`fnptr_indirect`) swing both ways on jitter. **Wall clock is secondary**: this box
swings +-17 % on byte-identical code, so no claim above rests on it.

## 6. Byte-identity — and what the equivalence actually rests on

Every one of the 240 `EXPECTED.tsv` rows compiled with **both** compilers (`-O`, byte
compare of the emitted executables):

| | count |
|---|---|
| **byte-identical** | **10 / 240** |
| differing | **230 / 240** |
| compile-fail | 0 |

That is much wider than F1's 33/239, and it is expected for the same structural reason:
F1 changed the operand/allocation path of every binary op, and F2 changes the store set
of every block boundary — a row does not need any arithmetic at all to contain a
boundary. Byte-identity is therefore NOT what carries the equivalence claim here, and
for this lever there is a much stronger and more specific oracle available:

**The opcode multiset.** For each of the 230 differing rows, both executables were
disassembled and the full instruction-text multisets compared (`test_suites/scripts/`
`objdump_multiset_diff.py`). The lever's claim is "remove dead home stores and nothing
else", which as a multiset statement is exactly:

```
new_multiset - old_multiset == {}                      (nothing added, nothing renamed)
old_multiset - new_multiset ⊆ { mov *,-N(%rbp...), ... }   (only home stores removed)
```

MEASURED: **all 230 differing rows satisfy both**, 0 rows add or rename a single
instruction (a register rename would show up as one added *and* one removed
instruction, so this check is sensitive to it). 0 further differing rows exist, so the
whole 240-row footprint of this lever is accounted for: **every emitted byte that
changed, changed because a dead home store was deleted.**

Equivalence still rests on the behavioural oracles, all measured in this run: gate
**240/240** exit-code match, all 38 benchmark outputs matching their C twins
(`bench.sh` OK, 0 MISMATCH), `differential` (optimizer `-O` == no-`-O` and vs-seed),
`fuzz` fail-closed with 0 crashes, `valgrind` clean, and the self-host fixpoint
`g2 == g3 == g4`.

## 7. What is still open

**A33** (delete the constant-true `loop_depth` guard; test the `unsafe{}` escape hatch
that already suppresses all three traps), **F3** (the comparison round trip — still an
8-instruction loop test), **A32** (the `fspill_home` frame/offset mismatch: the
prerequisite for xmm-resident FP *and* for the 32-byte-aligned vector spill region),
**F4** (xmm-resident FP), **F5** (opt-in FMA), **F6** (`i*8` is still `imul $0x8`),
**F7** (LICM), **F8** (constant shift-range check), and the **vector types** under the
`@isa(avx2)` compile-error contract.

Two further *in-loop* dead-store classes are now visible and are deliberately NOT in
this lever:

1. **Intra-block store-store redundancy.** `arith`'s loop still emits
   `20f: mov %rcx,-0xd0` / `217: mov %rcx,%rdx` / `21a: mov %rdx,-0xd0` — the same value
   stored to the same slot twice in a row. That is a mid-block `sdef`, not a boundary.
2. **The comparison round trip** is untouched by construction: `IR_LT`'s store is
   LIVE (the branch reads it back), so F2 correctly keeps it. That is F3.
