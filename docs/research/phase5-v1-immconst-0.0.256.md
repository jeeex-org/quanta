# 0.0.256 — V1: a single-use constant operand is consumed as an IMMEDIATE

First lever of the *parity* campaign (close the Quanta-vs-gcc-O2 gap row by row).
`VERSION` 0.0.255 -> **0.0.256**. Source changed: `src/x86/codegen.quanta` only.

```
0.0.255 golden  md5 2fe5e2844b9c3a74cf7922152a69ea46   (frozen baseline, untouched)
0.0.256 g1      md5 54c885b407a533008d49673cace847c4   (0.0.255 golden building the edited source)
0.0.256 g2      md5 21c868f418797c86d7db68728ed01917   (g1 building the edited source = COMMITTED GOLDEN)
0.0.256 g3      md5 21c868f418797c86d7db68728ed01917
0.0.256 g4      md5 21c868f418797c86d7db68728ed01917   (distinct(g2,g3,g4) == 1)
```

Instrument of record: `scripts/bench_instr.sh` (load-independent emitted bytes).
Every pre/post pair below is MEASURED in this session against
`compiler/0.0.25{5,6}/bin/x86/qc`.

---

## 1. The defect

A constant is an ordinary vreg, defined by an `IR_CONST` record that sits EARLIER
in the instruction stream than the operation that consumes it. So by the time a
binary op is reached the constant has already been materialised *and* its home
slot kept current:

```
 ee: mov    $0x1312d00,%eax          ; IR_CONST 20000000   <- the loop bound
 f3: mov    -0x50(%rbp),%rcx         ; i
 fa: xor    %rdx,%rdx
 fd: cmp    %rax,%rcx
100: setl   %dl
103: movzbq %dl,%rdx
107: mov    %rcx,-0x50(%rbp,%riz,1)
10f: mov    %rdx,-0x70(%rbp,%riz,1)
117: test   %rdx,%rdx
11e: je  ...
...
118: mov    $0x7,%eax                ; IR_CONST 7
11d: mov    -0x50(%rbp),%rcx
124: imul   $0x7,%rcx,%rdx           ; F6 (0.0.255) uses up the immediate ...
145: mov    %rax,-0x98(%rbp,%riz,1)  ; ... and the constant is STILL stored
```

`benchmark_arith`'s hot loop, 0.0.255, 79 instructions. gcc's, same function, 20.
Five of the 58-instruction gap are constants that gcc never materialises at all:
the literal is an operand of the instruction (`imul $7,%rcx,%rdx`,
`cmp $0x1312d00,%rcx`) and there is nothing to hold.

**This is the lever F6 named and then deliberately did not take.** F6's own note
says "the constant's own materialisation is a separate record and is NOT removed
here (that is a dead-const lever, not this one)". This is that lever.

## 2. The lever

Decide, per `IR_CONST`, whether its materialisation can be skipped; if so emit
NOTHING for it (no `mov $imm,%reg`, no `sdef`, and because the vreg is never
mapped, no flush keeps its home current either), and let its single reader fold
the literal into its own instruction. The new reader forms:

| reader | 0.0.255 | 0.0.256 |
|---|---|---|
| `IR_ADD` with the constant in a1 | `mov $c,%r; … add %r,%d` | `add $c, %d` |
| `IR_ADD` with the constant in a0 | same | `add $c, %d` (commutative; flags identical) |
| `IR_SUB` with the constant in a1 | `mov $c,%r; … sub %r,%d` | `sub $c, %d` |
| `IR_MUL` (either slot) | `mov $c,%r; … imul %r,%d` | `imul rd,rsrc,imm32` (already F6) |
| `IR_EQ/NE/LT/GT/LE/GE` | `mov $c,%r; cmp %r,%o; setcc` | `cmp $c,%o; setcc` |
| `IR_DIV/IR_MOD`, positive divisor | const still materialised | divisor read from the RECORD (already 0.0.238); materialisation now skipped |

`add/sub/cmp r64, imm32` set OF/ZF/SF/CF on the same condition as their
register forms, so `ovf_trap_emit()` fires exactly where it did — the same
argument F6 used to choose `imul rd,rsrc,imm32` over `shl`/`lea`.

### 2.1 The correctness argument

Eliding a DEFINITION is only sound when (a) the reader takes the literal from the
IR record (never from a register) and (b) the reader is GUARANTEED to take its
INTEGER path — a float path would `aphys()` a register that was never written.

(b) is `c1_intv`: a per-function fixpoint over the IR records alone that marks a
vreg INTEGER only when its producer cannot yield a float bit pattern. A float is
produced by `IR_FCONST`, by `i2f`/`fadd`/…/`f64_load`, by a parameter declared
f64/f32/f16 (`fn_parflt`/`fn_parft`), or by a call to a function declared
`-> f64` (`fn_retflt`) — none of which is an integer-producing op, and a call
result is never marked. Every float branch in the emit loop is guarded by
`r8(vfloat+operand)==1`, so

    c1_intv[v] == 1   =>   the value IS an integer AND vfloat[v] == 0 at emit time

The fixpoint only ever RAISES a bit, so it is an under-approximation: an unproven
vreg keeps its materialisation. Five further gates, each failing closed:

1. the value must fit a sign-extended imm32 (`ei()` writes 4 bytes and
   `add/sub/cmp r64, imm32` sign-extend);
2. the reader's OTHER operand must also be `c1_intv` — this is what stops
   `1.0 + 2` (a0 = IR_FCONST) and `f() + 1` (a0 = a call result) from reaching the
   imm path with an elided constant;
3. the constant must have exactly ONE reader, and that reader is identified by
   slot (a SUB/DIV/MOD needs it in a1);
4. the constant must not be REDEFINED anywhere in the function
   (`op_is_iconst` finds the LAST definition, so a reuse would fold a stale value —
   the hazard `constmul_reuse_test.quanta` already pins for F6);
5. **the reader's other operand must not itself be a constant**
   (`c1_const_vr`). See §3.

`c1_reads()` — the "does record k read vreg v" test — is **fail-safe by
construction**: the default is "yes", and every `return 0` is an opcode whose
operand layout was read and verified. An over-report costs an elision; an
under-report elides a definition the reader still needs, which is a silent
miscompile. The opcodes that would be a GUESS (IR_CLOSURE's `a1..an` captures with
n not in the record, IR_MATCH, IR_ENUM, IR_VTABLE, IR_DYN, IR_VEC128,
IR_GENERIC_INST, IR_FFI_CALL, IR_SHCMD, the IR_TRY family, IR_CAPREAD, the
pointer/volatile/idx family) therefore all report a read, which simply leaves
their functions unoptimised. `IR_CALL`/`IR_CALL_IDX` model the argument vector
(a1 = argc, a2 = arg base, vregs at `irres(argbase+j)`) because a call argument is
consumed from its HOME SLOT, not from a register.

## 3. Two defects the lever exposed, and neither was in the lever's own logic

### 3.1 A constant-vs-constant reader (`chain_assign_test`, red)

`a = b = 6 * 7` — the Tier-1 optimiser does **not** fold `6 * 7`, so the multiply
has an `IR_CONST` in BOTH operand slots. Each has exactly one reader, so both
qualified, and the `IR_MUL` imm path then used one elided constant as the SOURCE
of the other:

```
 3f9: imul   $0x7,%rsi,%rdi     <- %rsi is the ELIDED const 6's register
```

(`mov $0x6,%esi` gone.) The row returned 31 instead of 42. Gate-visible and
caught by the campaign's own 248-row sweep, not by the gate alone — the sweep was
run after every build for exactly this reason. Fix: `c1_const_vr` (gate 5 above)
leaves BOTH constants materialised, symmetrically. Re-measured after the fix:
`mov $0x6,%esi` / `mov $0x7,%edi` / `imul $0x7,%rsi,%r8` — identical to 0.0.255.

### 3.2 Two independent scans of the same fact (`sampling_eos_test`, red)

The readers originally re-derived the constant's VALUE with `op_iconst_val()`, a
second backward scan of the IR bounded by `[opt_beg, opt_i)`, while the ELISION
decision was made by a scan of `[ir_beg, ir_end)`. The two disagreed:

* the reader saw `r8(c1_skip+cvr)==1`, i.e. the decision pass HAD found an
  `IR_CONST` for `cvr` in `[ir_beg, ir_end)`;
* `op_is_iconst(cvr)` returned 0 over `[opt_beg, opt_i)` — it found none, and
  `op_iconst_val` then returned 0.

The emitter folded a ZERO into the instruction (`add $0x0`) instead of the real
literal. Isolated with a one-line instrumented build:
`if op_is_iconst(c1s)==0 { exit(201) }` fired on exactly that compile of
`test_suites/codes/sampling_eos_test.quanta` (which then returned 1 instead of 0).
Enlarging the clear range to the whole table changed nothing, so it is not stale
cross-function state — the two scans read the same records and still disagreed.

Lesson, and it is the campaign's own: **one decision, one place.** `c1_analyze`
already reads the value (to range-check it), so it records it in `c1_val` and the
reader consumes the record. The two scans can no longer disagree. Re-measured:
the row is green, and the `exit(201)` build fires nowhere.

Neither defect was reachable before this lever, so neither is a regression of a
previous version; both are hazards that any "fold a constant into an instruction"
work will meet again.

## 4. Measured effect — the instrument of record

38 rows, `q_*` columns from `bench_instr.sh`, 0.0.255 vs 0.0.256.

| metric | 0.0.255 | 0.0.256 | delta |
|---|---|---|---|
| `q_instr` (whole `main`, 38 rows summed) | 8237 | 8062 | **-2.1 %** |
| `q_loop` (hot-loop body, summed) | 1849 | 1732 | **-6.3 %** |
| `q_lst` (loop home stores) | 427 | 401 | **-6.1 %** |
| `q_lld` (loop home loads) | 242 | 250 | +3.3 % |
| `q_hst` (home stores in `main`) | 1360 | 1318 | **-3.1 %** |
| `q_hld` (home loads in `main`) | 694 | 702 | +1.2 % |

32 of 38 rows changed. The loop body shrinks by exactly the number of
single-use constants the loop contains — the signature of a removed
materialisation, not of a reallocation. Per row (loop body before -> after):

| case | loop | | case | loop | | case | loop |
|---|---|---|---|---|---|---|---|
| arith | 79 -> **73** | | heavy_div | 37 -> **31** | | q4k | 50 -> **48** |
| div_const | 63 -> **55** | | heavy_div2 | 37 -> **31** | | q4k_heavy | 50 -> **48** |
| heavy_int | 49 -> **45** | | mem | 46 -> **40** | | q4k_matmul | 46 -> **44** |
| heavy_int2 | 49 -> **45** | | mem_ops | 46 -> **40** | | regpressure | 252 -> **225** |
| float | 118 -> **116** | | big_array | 47 -> **41** | | match | 138 -> **134** |
| heavy_float | 56 -> **54** | | heavy_mem | 44 -> **40** | | loop_sum | 25 -> **23** |
| heavy_float2 | 56 -> **54** | | mutual_recursion | 52 -> **48** | | recursion | 31 -> **29** |
| fileio | 79 -> **75** | | heavy_recursion | 31 -> **29** | | generic_call | 37 -> **35** |
| params8 | 69 -> **67** | | higher_order | 42 -> unchanged | | closure_call | 41 -> unchanged |

**11 rows are byte-identical** — `closure_capture`, `enum`, `fib`,
`fib_recursive`, `file_io`, `float_ops`, `fnptr_indirect`, `int_ops`,
`nested_calls`, `string`, `struct`. Every one of them has no loop or no
single-use constant that qualifies, so a byte-identical row is the CORRECT
result for it, not a null result.

The per-call cost is the number that matters for `mutual_recursion`:
`--fn is_odd`, `q_instr` **67 -> 64**, `q_st` 7 -> 6 (gcc's twin: 12).

## 5. Paired wall clock, at matched load

`scripts/bench_ab.sh 0.0.255 0.0.256 --runs 9` (two QUANTA binaries, interleaved,
same source, no gcc denominator — the only wall-clock instrument on this box that
removes cross-run drift). **load 12.20, 17.16, 16.89** on entry, 12.26, 16.45,
16.66 on exit:

| case | A_best | B_best | A_med | B_med | best d% | med d% |
|---|---|---|---|---|---|---|
| mutual_recursion | 556 | **425** | 603 | **524** | **-23.6** | **-13.1** |
| heavy_div2 | 211 | **158** | 246 | **211** | **-25.1** | **-14.2** |
| div_const | 39 | **34** | 55 | **50** | **-12.8** | **-9.1** |
| arith | 100 | 82 | 118 | 125 | -18.0 | +5.9 |
| heavy_int | 151 | 122 | 162 | 168 | -19.2 | +3.7 |
| heavy_int2 | 655 | 527 | 730 | 708 | -19.5 | -3.0 |
| float | 94 | 90 | 105 | 113 | -4.3 | +7.6 |
| heavy_float | 72 | 73 | 78 | 79 | +1.4 | +1.3 |
| heavy_float2 | 321 | 341 | 387 | 373 | +6.2 | -3.6 |

**Honest scope.** At loadavg 12-17 this box cannot resolve an effect below ~20 %:
`arith`, `heavy_int` and `heavy_int2` show a large best-of win and a *positive*
median, which is drift, not code (their instruction counts moved by 2-6 %). Only
`mutual_recursion`, `heavy_div2` and `div_const` are negative in BOTH the best and
the median, and those three also have the largest instruction-count reductions.
The instruction counts are the evidence; these numbers are directional.

`scripts/bench.sh --runs 3` with `QC=0.0.256`: **38/38 compiled, 0 MISMATCH,
0 TWIN_FOLDED**, `# OK: every row compiled and every C twin kept its loop.`
(`getc_test`, a lib/std-dependent gate row, is red under a hand-rolled sweep on
BOTH 0.0.255 and 0.0.256 — external to this lever; the gate itself is green.)

## 6. Red-first row, registered in this commit

New stage `immconst-guard` in `test_suites/scripts/run_tests.sh` (+ summary line,
folded into the exit status via the RC aggregation), and a new probe
`test_suites/codes/arith_immconst_probe.quanta` registered in `EXPECTED.tsv`
(rc 33), so the row count moves **246 -> 248**. Same instrument as
`constmul-guard`/`marshal-guard`: the hot-loop body's instruction count, read out
of the `--emit-obj` object.

| compiler | loop body | verdict |
|---|---|---|
| 0.0.255 golden | **95** | **FAIL** (`95 > 90`) |
| 0.0.256 golden | **85** | PASS |

Threshold 90 sits between. The probe's body holds eight single-use constants
(`i*3`, `a+5`, `b-2`, `c/7`, `d%3`, `e>=2`, `i+1`, the loop bound 8). Its
`EXPECTED.tsv` row (rc 33) is a second, independent check: the comparison is TRUE
for i = 4, 5 and FALSE elsewhere, so an INVERTED setcc would return 75 and turn
the row red — the byte count is the guard, but the row is not a check that cannot
fail. Both directions of all six comparisons, with the constant in BOTH operand
slots, plus the imm32 boundaries (2^32 must NOT take the immediate form), plus a
constant with TWO readers, are pinned separately by the new
`test_suites/codes/immconst_semantics_test.quanta` (rc 12).

## 7. Verification

| check | result |
|---|---|
| gate (`run_tests.sh`, `QC=compiler/0.0.256/bin/x86/qc`) | **248/248 pass, 0 fail, 0 compile-fail**, every stage GREEN, `GATE_EXIT=0` |
| new stages | `PASS immconst-guard: loop=85 (<=90)`; all five prior guard stages GREEN |
| fixpoint (from 0.0.255 golden) | `2fe5e284 -> 54c885b4 -> 21c868f4 -> 21c868f4 -> 21c868f4`; distinct(g2,g3,g4)==1 |
| `bench.sh` | 38/38 compiled, **0 MISMATCH**, 0 folded twins |
| `verify-release.sh 0.0.256 0.0.255` | **14 passed, 0 failed** (incl. `<NEXT>` src/bin lockstep on 21c868f4, and `<VER>` reproducible bit-for-bit) |
| byte-identity vs 0.0.255 | see §8 |

## 8. Byte-identity accounting

`test_suites/scripts/byte_identity.sh 0.0.255 0.0.256` over all 248 EXPECTED.tsv
rows: **identical 143, differing 105, compile-fail 0.**

A lever that removes a materialisation from the emitted stream cannot be
byte-identical on the rows it touches, and removing a materialisation also frees a
register, so downstream allocation moves: the differing rows are expected to
differ by MORE than one instruction. Byte-identity is therefore not the oracle for
this class (0.0.255's own note says the same about F6).

The mechanical claim that IS exact, and it is stronger than a byte count:

| check (all 248 rows, `--emit-obj` + `objdump`, emitted instruction totals) | result |
|---|---|
| rows whose instruction count SHRANK | **105** |
| rows whose instruction count GREW | **0** |
| rows whose instruction count is identical | **143** |
| total emitted instructions | 692540 -> **678491** (**-2.03 %**) |

The 143 count-identical rows are exactly the 143 byte-identical rows, so the two
accountings agree: every row this lever touches is a pure instruction-count
REDUCTION, and no row's emitted code grew by a single instruction. Equivalence
otherwise rests on the behavioural oracles: the gate's 248/248 exit-code match on
every row, all 38 benchmark outputs against their C twins, `differential`
(`-O` vs no-`-O` and vs-seed), `fuzz` fail-closed, `valgrind`, and the
4-generation self-host fixpoint.

## 9. What this lever does NOT close

The 9 target rows, after 0.0.256, by hot-loop instruction count against gcc:

| row | gcc loop | 0.0.256 loop | remaining |
|---|---|---|---|
| arith | 20 | 73 | every live value still round-trips its home slot; 5 ovf traps; the `/3` magic re-materialises `movabs` per iteration |
| div_const | 15 | 55 | same marshalling; 4 home stores in the loop remain |
| float | 8 | 116 | `fphys()` still has ZERO call sites — every FP value lives in a GPR and round-trips `xmm` on every operation (F4) |
| heavy_float / heavy_float2 | 6 | 54 | same (F4) |
| heavy_int / heavy_int2 | 7 | 45 | marshalling; 5 ovf traps (`jno +2; ud2`) |
| heavy_div2 | 7 | 31 | marshalling |
| mutual_recursion | 10 | 48 (and 64 instructions per `is_odd` call vs gcc's 12) | call overhead: 10 push/pop for five callee-saved registers when one is used, the comparison materialised as a boolean (`xor;setcc;movzbq;test` vs `cmp;jcc`), and the argument marshalled through home slots |

The parity campaign continues from here, in the author's row order.
`docs/plans/language-capabilities.md` is unchanged by this version: the lever
needs no new language capability, only a proof that the constant is unused.
