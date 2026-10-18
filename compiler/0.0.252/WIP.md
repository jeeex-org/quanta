# 0.0.252 — WIP · **LEVER: F3 — the block terminator's store+reload round trip**

```
0.0.251 golden  md5 cd0fc7bf61e066b731a533c1bd3589ea   (frozen baseline, untouched)
0.0.252 g1      md5 f357252469fdf4dd0e974a9867675655   (0.0.251 golden compiling the edited source)
0.0.252 g2      md5 1d1e2d04a2acc5cdaabcd23e26fdf354   (COMMITTED GOLDEN, = fixpoint)
0.0.252 g3      md5 1d1e2d04a2acc5cdaabcd23e26fdf354
0.0.252 g4      md5 1d1e2d04a2acc5cdaabcd23e26fdf354   (distinct(g2,g3,g4) == 1)
```

Two files changed, everything else the 0.0.251 snapshot copied verbatim:

| file | change |
|---|---|
| `src/x86/codegen.quanta` | `IR_BR` and `IR_RET` take their operand into a register BEFORE `flush_all()` instead of reading it back out of the home slot the flush just wrote |
| `src/x86/emitter.quanta` | `f2_live_q` no longer force-marks the terminator's own operand (`ira0`) live at `IR_BR`/`IR_RET` — that special case existed only to compensate for the old order |

Gate-side, in the same commit: the new `terminator-guard` stage in
`test_suites/scripts/run_tests.sh` (+ its summary line, folded into the exit status).
No new gate row: the probe (`arith_deadstore_probe.quanta`, 0.0.250) is reused, so
`EXPECTED.tsv` stays at 242.

---

## 1. What landed

At a block terminator, `flush_all()` used to run BEFORE the handler read its operand, so
the condition (or return value) was stored to its home slot and immediately reloaded —
on every loop test and every return. `flush_all()` is a **store-only** pass (`mov
[rbp+disp], reg`), so it cannot disturb a physical register; the handler now takes the
value into a register first and the test reads the register.

Emitted loop test, before and after (from `benchmark_arith.quanta`):

```
 f3: mov -0x50(%rbp),%rcx            f3: mov -0x50(%rbp),%rcx
 fd: cmp %rax,%rcx                   fd: cmp %rax,%rcx
100: setl %dl                       100: setl %dl
103: movzbq %dl,%rdx                103: movzbq %dl,%rdx
107: mov %rcx,-0x50(%rbp,%riz,1)    107: mov %rcx,-0x50(%rbp,%riz,1)
10f: mov %rdx,-0x70(%rbp,%riz,1)    10f: test %rdx,%rdx      <-- register, directly
117: mov -0x70(%rbp),%rax           112: je 25d
11e: test %rax,%rax
121: je 26c
```

## 2. Measured effect (instrument of record: `scripts/bench_instr.sh`)

**All 38 benchmark rows changed codegen** (every row has a branch or a return).

| metric | 0.0.251 | 0.0.252 | delta |
|---|---|---|---|
| `q_instr` (whole `main`) | 8420 | 8273 | **-1.7 %** |
| `q_loop` (hot-loop body) | 1926 | 1864 | **-3.2 %** |
| `q_mem` (frame ops in `main`) | 2240 | 2055 | **-8.3 %** |
| `q_hst` (home stores in `main`) | 1454 | 1360 | **-6.5 %** |
| `q_hld` (home loads in `main`) | 785 | 694 | **-11.6 %** |
| `q_lst` (home stores in the loop) | 458 | 427 | **-6.8 %** |
| `q_lld` (home loads in the loop) | 273 | 242 | **-11.4 %** |

Uniform signature on every looped row: **loop body -2, loop stores -1, loop loads -1**
(one terminator round trip per iteration). `q_hld` falls further than `q_lst` because the
`RET` round trip is gone too and those are non-loop loads (`match`, `fnptr_indirect`).
Full per-case table and the emitted-byte evidence:
`docs/research/phase3-f3-comparison-roundtrip-0.0.252.md`.

## 3. Red-first row — proven RED on the previous version

New stage `terminator-guard`: same probe and same byte metric as `deadstore-guard`
(emitted bytes, exact, load-independent, no tolerance).

| compiler | loop | loop stores | loop loads | verdict |
|---|---|---|---|---|
| 0.0.251 golden (pre-F3) | 52 | 7 | 4 | **FAIL** (`52 > 51`, `4 > 3`) |
| 0.0.252 golden (F3) | 50 | 6 | 3 | PASS |

## 4. A REAL regression the gate caught, and the latent invariant behind it

The FIRST build of this version reordered `IR_RET` unconditionally, and the gate went
**RED: `FAIL question_mark.quanta (expected rc=0, got rc=173)`** — it printed the right
numbers (`7`, `0`) and then returned garbage.

Cause: the `?`-on-Err unwind jumps to `early_ret_lbl` with `rax` already holding the
whole `Option`/`Result` base pointer, and it was relying on a side effect of the old
statement ORDER — `flush_all()` emptied the register map, so the following `aphys(a0)`
got `RAX` back from `afree()` (first entry of `REGS`) and loaded the return value
straight into it, making the following `if rv!=0 { rr(0,rv) }` a no-op. Materialising the
value first allocates a different register, and the `rr(0,rvz)` then overwrites the
early-returned pointer.

Fix is a guard, not a revert: the `RET` reorder is taken only when `f2_ok == 1`, which —
because `f2_analyze` refuses every function containing `IR_TRY` — is exactly the
predicate "this function has no early-return label". Functions using `?` keep the
0.0.251 order verbatim. The `IR_BR` half needs no guard: nothing jumps into the middle of
its handler. **This is the third latent invariant the campaign has found being silently
provided by the order of `flush_all()`** (0.0.249 exposed two the same way).

## 5. Gate, fixpoint, verification

- **Gate** on the committed golden: **`=== Results: 242/242 pass, 0 fail (incl. 0
  compile-fail) [rows: EXPECTED.tsv] ===`**, **0 RED stages — GATE_RC=0**, including the
  new `terminator-guard` (`PASS loop=50 home-stores=6 home-loads=3`), `deadstore-guard`,
  `marshal-guard`, `stdlib` (GREEN again in this run), `valgrind`, `fuzz` (fail-closed, 0
  crashes), `differential` (`-O` == no-`-O` + vs-seed), `security`, `performance`,
  `qobj`, `verify-status`, `f16c-indep`.
- **Fixpoint** from the frozen 0.0.251 golden: `cd0fc7bf -> f3572524 -> 1d1e2d04 ->
  1d1e2d04 -> 1d1e2d04`; `distinct(g2,g3,g4) == 1`; the committed golden is g2.
- **`scripts/bench.sh`** (0.0.252 golden): `# OK: every row compiled and every C twin
  kept its loop.` — 0 `MISMATCH`, 0 compile failures: all 38 benchmark outputs still
  equal their C twins.
- **`scripts/verify-release.sh 0.0.252 "$(cat VERSION)"`**: 14 passed, 0 failed.
- **Byte-identity across the 242 gate rows**: see §6.

## 6. Byte-identity — and what the equivalence rests on

Every one of the 242 `EXPECTED.tsv` rows compiled with both compilers (`-O`, byte
compare of the emitted executables):

| | count |
|---|---|
| byte-identical | **5 / 242** |
| differing | **237 / 242** |
| compile-fail | 0 |

Only 5 rows are byte-identical, and that is expected rather than alarming: the change
alters where a terminator's operand is read from, and every non-trivial program has at
least one branch or return — so almost every row moves. 0.0.251 is the opposite extreme
(242/242 identical) precisely because that lever was a codegen no-op; these two versions
bracket the range, and neither number is evidence of anything by itself.

### CORRECTION: an opcode-sequence oracle that was measuring nothing

An earlier version of this campaign's opcode check (`objdump_multiset_diff.py`) read the
emitted *executables* with `objdump -d`. **The executables this compiler writes have no
section headers** (`readelf -S` -> "There are no sections in this file"), so `objdump`
printed zero instructions for them, both sides compared as equal, and every row was
reported as "only home stores were removed" — a VACUOUS pass. The claim it produced for
0.0.250 in `compiler/0.0.250/WIP.md` §6 and in that commit message is therefore
**WITHDRAWN**; §6 of the 0.0.250 WIP now records the correction.

The corrected tool, `test_suites/scripts/objdump_seq_diff.py`, (a) compiles with
`--emit-obj`, which does produce sections, (b) REFUSES to report a verdict when either
side disassembles to fewer than 10 instructions, so a vacuous pass cannot recur, and
(c) compares instruction SEQUENCES with difflib rather than multisets, so a
count-preserving register rename is visible. Its numbers for 0.0.251 -> 0.0.252 and for
0.0.249 -> 0.0.250 are reported in the phase-3 summary, not guessed here.

Equivalence for this version rests on the behavioural oracles, all measured in this run:
the gate's **242/242** exit-code match (including `question_mark.quanta`, which this
version's first build broke and which the gate caught), all 38 benchmark outputs matching
their C twins (`bench.sh` OK, 0 MISMATCH), `differential` (`-O` == no-`-O` and
vs-seed), `fuzz` fail-closed with 0 crashes, `valgrind` clean, and the self-host fixpoint
`g2 == g3 == g4`.

## 7. What is still open

- **F3 is only half closed.** The loop test is now 5 instructions (`cmp; setl; movzbq;
  test; je`) against gcc's 2 (`cmp; jl`). The remaining three are the materialisation of
  the comparison as a first-class i64 plus the `xor` that clears the register before
  `setl` writes its low byte. Closing that is a peephole over two IR ops (`IR_LT`
  immediately followed by `IR_BR` on its result, nothing else reading it) — a different
  lever, needing its own version and red-first row.
- **A32** — `fspill_home` writes ~8 KB below `%rbp` while the frame formula reserves far
  less, and `fphys()` has zero call sites. It is the stated prerequisite for F4
  (xmm-resident FP) **and** for the 32-byte-aligned vector spill region, and it is a
  latent out-of-frame write, not a formality.
- **F4** (xmm-resident FP, gated on A32), **F5** (opt-in FMA), **F6** (`i*8` is still
  `imul $0x8`), **F7** (LICM), **F8** (constant shift-range check).
- The **vector types** (`docs/research/phase2-vector-design.md`, author's directive #21):
  not started. It needs A32 first, plus the `@isa(avx2)` compile-error contract and two
  byte-scanning gate rows, and it is a multi-version feature (lexer/parser/type check,
  ABI, ISA enforcement), not a lever.
