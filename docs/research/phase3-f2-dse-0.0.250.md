# 0.0.250 — F2: dead-store elimination at the block-boundary `flush_all()`

Phase 3, lever one. `VERSION` 0.0.249 -> **0.0.250**. Source changed:
`src/x86/emitter.quanta` (the `flush_all()` filter + the query), `src/x86/codegen.quanta`
(the block-liveness analysis that feeds it). Gate: one new row, one new stage.

```
0.0.249 golden  md5 14fd1086617bb1b37a502a33c624c802   (frozen baseline, untouched)
0.0.250 g1      md5 3bcfc3de1291dd68085c8afec427bc66   (0.0.249 golden building the edited source)
0.0.250 g2      md5 e2f04027d8b87623da94d7df0245573b   (g1 building the edited source = COMMITTED GOLDEN)
0.0.250 g3      md5 e2f04027d8b87623da94d7df0245573b
0.0.250 g4      md5 e2f04027d8b87623da94d7df0245573b   (distinct(g2,g3,g4) == 1)
```

Instrument of record: `scripts/bench_instr.sh` (load-independent emitted-byte counts).
Every pre/post pair below is MEASURED in this session, 0.0.249 golden vs the 0.0.250
golden.

---

## 1. Where the term came from

0.0.249 (F1) removed `adistinct`'s per-binary-op operand eviction and with it the
accidental side effect that the register map was emptied on every op. The audit's
projected -33 % was refuted: the measured result was **-6.9 % of the loop body**, and
`phase2-f1-adistinct-0.0.249.md` §6 then named what was left. The largest remaining
in-loop term is the **block-boundary `flush_all()`**: every `IR_LABEL`, `IR_JMP`,
`IR_BR` and `IR_RET` calls it, and it stores EVERY mapped vreg to its home slot.

That is the right shape to attack, and it is provably wasteful on this IR. A Quanta
expression body is a chain of temporaries: `sum = sum + i * 7 - i / 3 + i % 5` emits
`i*7`, then `i/3`, then `i%5`, and each one dies at the end of the statement. At the
back edge of `arith`'s loop the flush stores **11** vregs, of which exactly **2** —
`i` and `sum` — are read by the loop header or the exit block. The other nine stores
are dead, and (under the 0.0.245 invariant) `flush_all()` is the ONLY thing that ever
reads them.

Measured on the emitted object of `benchmark_arith.quanta` (0.0.249 golden), the whole
back-edge flush:

```
 26f: mov %r8,-0xb0   ; i/3         dead   27f: mov %rsi,-0x88   ; sum+i*7   dead
 277: mov %rdi,-0xb8  ; const 3     dead   287: mov %rbx,-0x40   ; sum       LIVE
 27f..                                     
 28f: mov %rax,-0xa8  ; partial     dead   297: mov %rcx,-0xd0   ; i%5       dead
 29f: mov %rdx,-0xc8  ; result      dead   2a7: mov %r9,-0xf0    ; const 1   dead
 2af: mov %r10,-0x50  ; i           LIVE   2b7: mov %r12,-0xe8   ; i+1       dead
```

## 2. The lever

`flush_all()` is a store-only pass whose whole purpose is to make a value findable in
its home slot by the NEXT block. So it only has to store a vreg that is **live** at the
flush point. Which values those are is decided by a block-level liveness fixpoint,
computed once per function by `f2_analyze()` and published through per-block
`live-in` / `live-out` byte tables plus a per-IR-index block map.

The filter applies **only at the four block-boundary opcodes**, and that restriction is
the soundness argument itself. There, `live_out(block)` is a SUPERSET of "live after
the flush point":

- flush before an `IR_LABEL` -> store `live_in` of the block the label starts;
- flush before `IR_JMP`/`IR_BR`/`IR_RET` -> store `live_out` of the block that ends
  there, plus the one operand the handler reads from its home AFTER the flush
  (`IR_BR`'s condition, `IR_RET`'s value), which dies at the terminator and so is not
  in `live_out`.

A **mid-block** flush (the call path, every memory/FFI/closure builtin) is left exactly
as it was, store-everything: there `live_out(block)` is NOT a superset, because a value
whose last use is inside the block is live at a mid-block point but not live out of it.
That asymmetry is deliberate, not an oversight — it is what makes "use `live_out`
only at boundaries" correct rather than nearly correct. It costs the call-path stores,
which are not the measured term.

### 2b. Everything errs toward "store"

Correctness does not rest on the analysis being complete; it rests on every gap
degrading to 0.0.249 behaviour.

| gap | handling |
|---|---|
| reads | OVER-reported (the `a4_reads` op classification + all three operand slots of the general case) |
| definitions | UNDER-reported (`IR_LABEL/JMP/BR/RET/STOREG/FREE` never define) |
| vreg outside the table (`vr >= f2_w`) | never skipped |
| home address escaped (`vr_at`: closure capture, `&local`) | never skipped — read/written through a pointer liveness cannot see |
| `IR_CLOSURE` | whole function refused: it hands the closure the ADDRESS of a captured home slot, which the flush must have made current, and `vr_at` is only set AFTER that flush |
| try/catch/throw cluster, `IR_MATCH`, `IR_ASM`, `IR_FFI_CALL`, `IR_VEC128`, `IR_CAPREAD/WRITE`, `IR_FNVAL` | whole function refused |
| unresolved jump/branch target label | whole function refused |
| fixpoint does not converge, or tables would not fit | whole function refused |
| `is_cache == 1` | refused: a cached function's `IR_CALL` argument list is re-based by the module loader |
| the emit loop is not running (`f2_at < 0`) | store everything |

The multi-op refusals are not hypothetical: every one of them is a control-flow edge or
a direct `spill_home` reader that this CFG does not model, and an unmodelled edge makes
a live set too SMALL, which is the one direction that miscompiles.

**Arena sizes are load-bearing.** The compiler's own mmap total already sits within a
few tens of MB of the ceiling `scripts/qcrun.sh` gives it, so the tables are small
(13 MB total) and `f2_analyze` refuses anything that would not fit. MEASURED: with
the tables at 200 MB the compiler stopped producing binaries under the default
6144 MB cap (exit 0, no output — the "dies silently below ~6 GB" failure); at 13 MB
it is inside the cap again.

## 3. Measured effect — the instrument of record

38 rows; `q_loop` = hot-loop body, `q_lst`/`q_lld` = frame-relative stores/loads inside
it. **28 of 38 rows changed codegen** (the 10 unchanged are the loop-free or
call-dominated rows: `enum string fib file_io float_ops int_ops nested_calls struct
closure_call closure_capture finptr_indirect`).

| metric | 0.0.249 | 0.0.250 | delta |
|---|---|---|---|
| `q_instr` (whole `main`) | 8825 | 8420 | **-4.6 %** |
| `q_loop` (hot-loop body) | 2101 | 1926 | **-8.3 %** |
| `q_mem` (frame ops in `main`) | 2645 | 2240 | **-15.3 %** |
| `q_hst` (home stores, `main`) | 1859 | 1454 | **-21.8 %** |
| `q_hld` (home loads, `main`) | 785 | 785 | +0 |
| `q_lst` (home stores in the loop) | 633 | 458 | **-27.6 %** |
| `q_lld` (home loads in the loop) | 273 | 273 | +0 |

`q_hst` falls by **405** and `q_instr` falls by **405**: every single instruction this
lever removes is a home store. Nothing was renamed, nothing was traded, and **not one
home load was added** (`q_hld` and `q_lld` are unchanged to the instruction) — which is
the shape a pure dead-store pass must have, and is the strongest evidence available
that it is doing what it claims rather than perturbing the allocator.

| case | loop | loop st | loop ld | | case | loop | loop st | loop ld |
|---|---|---|---|---|---|---|---|---|
| regpressure | 268 -> **254** | 81 -> **67** | 12 | | params8 | 77 -> **71** | 27 -> 21 | 13 |
| match | 146 -> **141** | 33 -> 28 | 14 | | q4k/_heavy | 60 -> **53** | 19 -> 12 | 9 |
| float | 125 -> **120** | 43 -> 38 | 29 | | heavy_int/_int2 | 59 -> **52** | 16 -> 9 | 6 |
| fileio | 95 -> **83** | 31 -> **19** | 18 | | mem / mem_ops | 55 -> **50** | 18 -> 13 | 7 |
| arith | 92 -> **82** | 23 -> **13** | 9 | | mutual_recursion | 67 -> **56** | 22 -> 11 | 9 |
| div_const | 76 -> **66** | 26 -> **16** | 10 | | heavy_float/_2 | 63 -> **58** | 21 -> 16 | 12 |
| big_array | 55 -> **50** | 18 -> 13 | 7 | | loop_sum | 32 -> **27** | 10 -> 5 | 4 |
| heavy_div/_2 | 48 -> **40** | 16 -> **8** | 6 | | heavy_recursion | 39 -> **33** | 13 -> 7 | 5 |

Largest relative row: `arith` loop stores **23 -> 13 (-43 %)**, `heavy_div`/`heavy_div2`
**16 -> 8 (-50 %)**, `loop_sum` **10 -> 5 (-50 %)**.

## 4. Red-first row, registered in this commit

New stage `deadstore-guard` in `test_suites/scripts/run_tests.sh`, plus one new gate row
`test_suites/codes/arith_deadstore_probe.quanta` (`EXPECTED.tsv` 239 -> 240; hand-derived
golden: `sum over i in 0..7 of ((i*3+1)*2 - i*3)` = `sum of (i*3+2)` = `3*28 + 16` = **100**).

The probe's loop body is *entirely* dead temporaries — `d` is the only value the body
produces that is read again. The stage compiles it with `--emit-obj` and counts
frame-relative stores/loads in the hot loop with the SAME AWK metric definition as
`bench_instr.sh`. Emitted bytes: exact, no tolerance, load-independent.

| compiler | loop | loop stores | loop loads | verdict |
|---|---|---|---|---|
| 0.0.249 golden (pre-F2) | 66 | 21 | 4 | **FAIL** (66 > 60, 21 > 12) |
| 0.0.250 golden (F2) | 52 | 7 | 4 | PASS |

Thresholds 60 / 12 / 6 sit strictly between the two on all three counts, so
re-instating the unconditional flush turns the gate RED for the reason the stage exists.

## 5. Verification

- **Gate** on the committed golden: **`=== Results: 240/240 pass, 0 fail (incl. 0
  compile-fail) [rows: EXPECTED.tsv] ===`**, every stage GREEN — including
  `deadstore-guard`, plus `valgrind`, `fuzz` fail-closed (0 crashes), `differential`
  (`-O` == no-`-O` + vs-seed), `stdlib`, `security`, `performance`, `qobj`,
  `verify-status`, `f16c-indep`, `marshal-guard`.
- **Fixpoint** from the frozen 0.0.249 golden: `14fd1086 -> 3bcfc3de -> e2f04027 ->
  e2f04027 -> e2f04027`; `distinct(g2,g3,g4) == 1`; the committed golden is g2.
- **Self-host**: 0.0.250 rebuilds from source and the rebuild is a fixed point
  (g2 == g3 == g4), which is the strongest correctness test in the tree — the compiler
  exercises its own arithmetic far harder than any gate row.
- `scripts/bench.sh` (0.0.250 golden): see the run attached to this commit; all 38
  benchmark outputs are compared against their C twins.

## 6. Byte-identity across the gate rows

All 240 `EXPECTED.tsv` rows compiled with both compilers, byte compare: see the
per-version WIP.md for the counts. Like F1 — and unlike a flag change — this lever
alters the store set of every block boundary, so a wide footprint is expected; what is
NOT expected, and is the useful measurement, is that the *opcode multiset* shrinks by
exactly the number of removed `mov [rbp+disp], reg` forms and grows by nothing.

## 7. What this version does NOT fix

Still open and now measured against this baseline: **A33** (`loop_depth` dead guard +
untested `unsafe{}` escape hatch), **F3** (the comparison round trip — still an
8-instruction loop test), **A32** (the `fspill_home` frame/offset mismatch, the
prerequisite for xmm-resident FP and for the 32-byte-aligned vector spill region),
**F4** (xmm-resident FP), **F5** (opt-in FMA), **F6** (`i*8` is still `imul $0x8`),
**F7** (LICM), **F8** (constant shift-range check), and the **vector types** under the
`@isa(avx2)` contract.

Two further dead-store classes are now visible and are NOT in this lever:

1. **`sdef`'s own redundant store.** `arith`'s loop still emits
   `217: mov %rcx,%rdx` / `21a: mov %rdx,-0xd0` immediately after
   `20f: mov %rcx,-0xd0` — the same value stored to the same slot twice in a row
   (a `sdef` under a mid-block flush_clob, then the result's own definition). That is
   intra-block store-store elimination, not block-boundary.
2. **The comparison round trip** is unaffected by construction: F2 removes stores, and
   `IR_LT`'s store is live (the branch reads it back), which is exactly F3.
