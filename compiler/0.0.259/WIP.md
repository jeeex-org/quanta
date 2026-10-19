# 0.0.259 — WIP · **TWO LEVERS: phase6 VA reclaim + ATOMICS**

Two independent levers land in this version, developed concurrently in the same tree.

1. **phase6 VA reclaim** — full write-up: `docs/research/phase6-arena-reclaim-0.0.259.md`
   (the file below is the previous version's WIP and is kept for the lever it documents).
2. **Atomics: the ordering model, a sound `&global`, and the optimiser memory-clobber
   barrier** — full write-up: `docs/research/atomics-0.0.259.md`. Summary:
   the atomic *instructions* already existed and were correct (x86-64, since 0.0.105);
   three things that made them usable did not. **(a)** `&global` returned the address of
   an `IR_LOADG` TEMPORARY, so `atomic_add(&next,1)` was a no-op on a private cell — that
   is the `931 of 2048 rows wrong` measurement, a MISCOMPILE and not a race, and it made a
   work-stealing loop hang. **(b)** `atomic_store` was a plain `mov` (release) while every
   call site and comment called it `seq_cst`. **(c)** no pass could even ask whether a
   record was an atomic access. 0.0.259 adds `0 relaxed / 1 acquire / 2 release /
   3 acq_rel / 4 seq_cst` as a compile-time trailing literal (default seq_cst, so every
   existing call site keeps its meaning and finally gets it), fixes `&global`, and adds
   `ir_isbar()`/`bar_in_range()`. `lib/std/atomic.quanta` carries the ordinals as `const`.
   Acceptance: `atomic_ws_test` (2048-row claim loop, exact totals, N=1/2/4/8; RED 11 -> 0)
   and `atomic_addrglobal_test` (RED 1 -> 0). Guard: `tests/atomic_guard.sh`.

Fixpoint (measured, this tree): `0.0.258 golden e7fc8cd4` -> F1 `1e72692806ed8f650a2942d8bc38fc0c`
-> F2 `1e72692806ed8f650a2942d8bc38fc0c` (identical, so the committed binary is F1).

---

# 0.0.258 — WIP · **LEVER: CS1 — callee-saved ELISION (remove, don't pad)**

One lever, one version. Golden parent `f047748f7eddb3991b7b5306656ceae4` (0.0.257,
the address-space reclaim). Full write-up with every measurement:
**`docs/research/phase5-cs1-callee-saved-0.0.258.md`**.

This is the delayed round-2 lever: built and measured there, reverted because the
gate caught a `qobj` G6 failure. **That failure does not reproduce** (see §3), the
reclaim in 0.0.257 removed the ceiling it was tangled up with, and the lever
lands here on its own measured delta.

Changes confined to `codegen.quanta` and `emitter.quanta`:

| file | change |
|---|---|
| `src/x86/emitter.quanta` | `cs_mask` + `cs_mark(pr)`, called from every allocator entry point that hands out a destination (`aset`, `aremap`, `afree`, `afree_x`, `apick_free`, `ascratch`, `aevict_*`). Scalars, not arenas — 1-16-entry tables. |
| `src/x86/codegen.quanta` | `cs_risky(op)` fail-closed op guard for the six ops whose emitted body writes a callee-saved register with no allocator involvement (`IR_ARRNEW`, `IR_APUSH`, `IR_CLOSURE`, `IR_FREE`, `IR_THROW`, `IR_ASM`); a builtin `IR_CALL` (inline emit) also sets `cs_hard`; `cs_finish` DELETES the unused pushes/pops and compacts the buffer, widening the frame's rsp adjustment by 8 per elided register so the body's rsp is byte-for-byte where it was, and fixing up the three tables that can hold an absolute code offset for the function (`patches`, `lblmap`, `gpatches`) |

```
0.0.257 golden  md5 f047748f7eddb3991b7b5306656ceae4   (frozen baseline, untouched)
0.0.258 g1      md5 89861b8577fc28fda25dc8031a9bec27
0.0.258 g2      md5 e7fc8cd4430ef3d4ef8e99067354bfcf   (COMMITTED GOLDEN = fixpoint)
0.0.258 g3      md5 e7fc8cd4430ef3d4ef8e99067354bfcf
0.0.258 g4      md5 e7fc8cd4430ef3d4ef8e99067354bfcf   (distinct(g2,g3,g4) == 1)
```

## 1. The measured delta — the author's #1 row

`mutual_recursion`, function `is_odd` (whole function, all epilogues included;
`--emit-obj` + objdump):

| compiler | `is_odd` emitted instructions | frame |
|---|---|---|
| 0.0.256 | **64** | 1104 |
| 0.0.257 (reclaim only) | **64** (unchanged — 0.0.257 is codegen-inert) | 1104 |
| **0.0.258 (CS1)** | **44** | 1144 (+40 = 8x5) |

**-20 instructions per call, -31.25%.** `is_odd` writes none of RBX/R12-R15, so
0.0.256 pushed all five in the prologue and popped all five in every epilogue for
nothing.

## 2. Red-first: the new stage is RED on 0.0.257, GREEN on 0.0.258

New row `test_suites/codes/csave_probe.quanta` (registered in `EXPECTED.tsv` in
this same commit) + Stage **1.6m `csave-guard`** in `test_suites/scripts/run_tests.sh`
(+ summary line, + folded into `FUNCTIONAL_RC`). `probe_fn` writes none of the
five. Whole function from the object bytes:

| compiler | `probe_fn` instructions | callee-saved push/pop | verdict |
|---|---|---|---|
| 0.0.257 | **86** | 15 | **FAIL** (>80) |
| 0.0.258 | **74** | 3 | **PASS** (<=80) |

## 3. The round-2 blocker does not reproduce

Round 2 reverted this lever because `scripts/g6_selfcache.sh` (cache the
327-function compiler, delete every source, rebuild from the cache alone)
segfaulted, putting the gate's `QOBJ` stage at 16/17. Re-measured here:

| instrument | result |
|---|---|
| the shipped `scripts/g6_selfcache.sh`, 0.0.258 binary, pinned source, 3 runs | **5/5, 5/5, 5/5** |
| the same for the CS1-only tree (no reclaim), rebuilt from round 2's own apply script | **5/5 x3**, and 5/5 x4 in each of 4 further configurations |
| parameterized G6 over writer x consumer x source (0.0.256/reclaim/CS1 x same x pinned-tree/own-tree), g1 and g2 | **5/5 in all 12+ cells** |
| the gate's own `QOBJ` stage | **17/17 GREEN** |

The one failure mode that *is* reproducible on the cache path is the address-space
ceiling, and 0.0.257 fixed it (`--emit-qobj` under `qcrun.sh`'s 6,291,456 KB cap:
0.0.256 rc=1 with no file, 0.0.257/0.0.258 rc=0 with a 37534-byte cache). The
deliberate isolation round 2 could not complete — "disable the elision and G6
passes" — was consistent with the ceiling, not with offset bookkeeping.

## 4. Accounting: 249 rows, with the mechanical cross-check

| check | result |
|---|---|
| rows whose instruction count SHRANK | **247** |
| rows whose instruction count GREW | **0** |
| rows whose instruction count is identical | **2** |
| total emitted instructions | 680,211 -> 659,069 (**-21,142, -3.11%**) |
| byte-identity, same 249 rows | identical **2**, differing **247**, compile-fail 0 |

The 2 count-identical rows are EXACTLY the 2 byte-identical rows —
`mmap1.quanta` and `test_many_globals.quanta` — so the cross-check holds: the
count-identical set EQUALS the byte-identical set. Both rows' functions genuinely
WRITE RBX (verified in the emitted object: `mov %rdi,%rbx`), so correctly keeping
every save for them is a positive result, not a null one.

## 5. Behaviour and release

| check | result |
|---|---|
| gate `run_tests.sh` (249 rows) | **249/249 pass, 0 fail, 0 compile-fail**; all stages GREEN incl. `QOBJ 17/17`, `csave-guard`, `cache-precond-guard`; exit 0 |
| `bench.sh --runs 3` | **38/38 rows compiled, 0 MISMATCH**, 0 folded twins |
| byte-identity | identical 2, differing 247, compile-fail 0 |
| 4-generation fixpoint | `f047748f -> e7fc8cd4 -> e7fc8cd4 -> e7fc8cd4`, distinct(g2,g3,g4) == 1 |
| `verify-release.sh 0.0.258 0.0.257` | **14/14 PASS** |

## 6. The nine target rows, AFTER 0.0.258 (hot-loop body, vs `gcc -O2`)

`scripts/bench_instr.sh` (load-free emitted code), in the author's order. `q_loop`
is the innermost backward branch and its target — the number that decides a loop
row's runtime.

| # | row | q_loop | c_loop | ratio | <=1.00x? |
|---|---|---|---|---|---|
| 1 | `mutual_recursion` (`--fn is_odd`, whole fn) | **44** | 12 | 3.67x | no |
| 2 | `heavy_float2` | 54 | 6 | 9.00x | no |
| 3 | `heavy_int2` | 45 | 7 | 6.43x | no |
| 4 | `float` | **116** | **8** | **14.50x** | no |
| 5 | `heavy_float` | 54 | 6 | 9.00x | no |
| 6 | `heavy_int` | 45 | 7 | 6.43x | no |
| 7 | `heavy_div2` | 31 | 7 | 4.43x | no |
| 8 | `arith` | 73 | 20 | 3.65x | no |
| 9 | `div_const` | 55 | 15 | 3.67x | no |

**None of the nine is at <=1.00x.** The three float rows are the worst and are all
F4 (xmm-resident FP) territory: `float` at 14.50x is the single worst row in the
campaign. Wall-clock ratios on these rows are NOT quoted — the box ran at load
average 10-18 during this work and within-arm spread has been measured at
1.24-1.54x, so an absolute ms number would not travel.
