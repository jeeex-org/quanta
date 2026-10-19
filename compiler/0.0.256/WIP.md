# 0.0.256 — WIP · **LEVER: V1 — a single-use constant operand is consumed as an IMMEDIATE**

Lever: **V1** — the first row of the parity campaign (close the Quanta-vs-gcc-O2
gap row by row, in the author's order). One lever, one version. Golden
`21c868f418797c86d7db68728ed01917`.

Full write-up, with the emitted-code evidence and every measurement:
**`docs/research/phase5-v1-immconst-0.0.256.md`**. One file changed, everything
else the 0.0.255 snapshot copied verbatim:

| file | change |
|---|---|
| `src/x86/codegen.quanta` | `IR_CONST` emits NOTHING when `c1_analyze` has proved its one reader folds the literal into an immediate form; new `add/sub/cmp r,imm32` reader paths; the new `c1_intv` / `c1_skip` / `c1_val` / `c1_rdrs` tables and the `c1_reads` / `c1_const_vr` / `c1_analyze` helpers |

```
0.0.255 golden  md5 2fe5e2844b9c3a74cf7922152a69ea46   (frozen baseline, untouched)
0.0.256 g1      md5 54c885b407a533008d49673cace847c4
0.0.256 g2      md5 21c868f418797c86d7db68728ed01917   (COMMITTED GOLDEN = fixpoint)
0.0.256 g3      md5 21c868f418797c86d7db68728ed01917
0.0.256 g4      md5 21c868f418797c86d7db68728ed01917   (distinct(g2,g3,g4) == 1)
```

Gate-side, in the same commit: the new `immconst-guard` stage in
`test_suites/scripts/run_tests.sh` (+ summary line, folded into the exit status),
and the new rows `test_suites/codes/arith_immconst_probe.quanta` (the guard's
kernel, `EXPECTED.tsv` rc=33) and `test_suites/codes/immconst_semantics_test.quanta`
(all six comparisons with the constant in BOTH operand slots, both true and false,
the imm32 boundaries, and a two-reader constant; rc=12), so the row count moves
**246 -> 248**.

---

## 1. What landed

A constant used to be materialised (`mov $imm,%reg`) and its home slot kept
current, because a constant is an ordinary vreg defined by an earlier `IR_CONST`
record — already emitted by the time the reader is reached. F6 (0.0.255) removed
only the COPY of the multiplicand, and its own note recorded "the constant's own
materialisation is a separate record and is NOT removed here (that is a dead-const
lever, not this one)". This is that lever:

```
       0.0.255                                  0.0.256
  mov  $0x7,%eax                          (gone)
  mov  -0x50(%rbp),%rcx                   mov  -0x50(%rbp),%rcx
  imul $0x7,%rcx,%rdx                     imul $0x7,%rcx,%rdx
  mov  %rax,-0x98(%rbp,%riz,1)            (gone)
```

`add/sub/cmp r64, imm32` set OF/ZF/SF/CF on the same condition as their register
forms, so `ovf_trap_emit()` fires exactly where it did — the same argument F6 used
to choose `imul rd,rsrc,imm32` over `shl`/`lea`.

## 2. Correctness — the part that mattered

Eliding a DEFINITION is only sound if the reader (a) takes the literal from the IR
record and (b) is GUARANTEED to be on its integer path; a float path would
`aphys()` a register that was never written.

(b) is `c1_intv`: a per-function fixpoint over the IR records ALONE that marks a
vreg INTEGER only when its producer cannot yield a float bit pattern. A float is
produced by `IR_FCONST`, by `i2f`/`fadd`/…/`f64_load`, by a parameter declared
f64/f32/f16, or by a call to a function declared `-> f64` — none of which is an
integer-producing op, and a call result is never marked. Every float branch in the
emit loop is guarded on `r8(vfloat+operand)==1`, so `c1_intv[v]==1` implies
`vfloat[v]==0` at emit time. The fixpoint only ever RAISES a bit, so an unproven
vreg keeps its materialisation — the safe direction.

`c1_reads()` (does record k read vreg v) is **fail-safe by DEFAULT**: `return 1`,
with every `return 0` an opcode whose operand layout was read and verified. The
opcodes whose operand list is not `a0..a2` (`IR_CLOSURE`'s `a1..an` captures with n
not in the record, `IR_MATCH`, `IR_ENUM`, `IR_VTABLE`, `IR_DYN`, `IR_VEC128`,
`IR_GENERIC_INST`, `IR_FFI_CALL`, `IR_SHCMD`, the `IR_TRY` family, `IR_CAPREAD`,
the pointer/volatile/idx family) all report a read, which merely leaves their
function unoptimised. `IR_CALL`/`IR_CALL_IDX` model the argument vector (a1 = argc,
a2 = arg base, vregs at `irres(argbase+j)`) because a call argument is consumed
from its HOME SLOT, not from a register. An over-report costs an elision; an
under-report is a miscompile.

Four more gates, each failing closed: the value must fit a sign-extended imm32;
the reader's OTHER operand must also be `c1_intv` (this is what stops `1.0 + 2`
and `f() + 1`); the constant must have exactly one reader, identified by SLOT; and
the constant must not be redefined anywhere in the function.

### 2.1 Two defects the lever exposed, neither in the lever's own logic

**`chain_assign_test` (red, then fixed): `a = b = 6 * 7`.** The Tier-1 optimiser
does NOT fold `6 * 7`, so the multiply has an `IR_CONST` in BOTH operand slots.
Each had exactly one reader, so both qualified, and the `IR_MUL` imm path then
used one elided constant as the SOURCE of the other:

```
 3f9: imul   $0x7,%rsi,%rdi     <- %rsi is the ELIDED const 6's register
```

(`mov $0x6,%esi` gone.) The row returned 31 instead of 42. Fixed with
`c1_const_vr`, which leaves BOTH constants of a constant-vs-constant reader
materialised, symmetrically.

**`sampling_eos_test` (red, then fixed): two independent scans of the same fact.**
The readers originally re-derived the constant's VALUE with `op_iconst_val()`, a
second backward scan bounded by `[opt_beg, opt_i)`, while the elision decision was
made over `[ir_beg, ir_end)`. The two disagreed: the reader saw
`r8(c1_skip+cvr)==1` (the decision pass HAD found an `IR_CONST` for `cvr`) while
`op_is_iconst(cvr)` returned 0, so `op_iconst_val` returned 0 and the emitter
folded `add $0x0` instead of the real literal. Isolated with a one-line
instrumented build — `if op_is_iconst(c1s)==0 { exit(201) }` fired on exactly that
compile. Enlarging the clear range to the whole table changed nothing, so it is
NOT stale cross-function state. Fixed by recording the value in `c1_val` in the
decision pass and having the reader consume the record: **one decision, one place.**
Re-measured: the row is green and the `exit(201)` build fires nowhere.

Both were caught by the full 248-row sweep, which was re-run after EVERY build for
exactly this reason — the gate alone would have hidden 3.1 behind 9 other rows.

## 3. Verification

| check | result |
|---|---|
| gate (`run_tests.sh`, `QC=compiler/0.0.256/bin/x86/qc`) | **248/248 pass, 0 fail, 0 compile-fail**, every stage GREEN, `GATE_EXIT=0` |
| new stage | `PASS immconst-guard: loop=85 (<=90)`; all five prior guard stages GREEN |
| fixpoint | `2fe5e284 -> 54c885b4 -> 21c868f4 -> 21c868f4 -> 21c868f4`; distinct(g2,g3,g4)==1 |
| `bench.sh` | 38/38 compiled, **0 MISMATCH**, 0 folded twins, `# OK: every row compiled and every C twin kept its loop.` |
| `verify-release.sh 0.0.256 0.0.255` | **14 passed, 0 failed** (src/bin lockstep on the fixpoint md5; 0.0.255 rebuilds bit-for-bit) |
| byte-identity vs 0.0.255 | **identical 143, differing 105, compile-fail 0** of 248 |
| instruction accounting vs 0.0.255 | **shrank 105, GREW 0, identical 143**; total 692540 -> 678491 instructions (-2.03 %) |

`getc_test` is red under a hand-rolled sweep on BOTH 0.0.255 and 0.0.256 (it is a
`lib/std`-dependent row and a loader peer is live in that tree); the gate itself is
green on both, so it is external to this lever.

## 4. Red-first row

`immconst-guard` (run_tests.sh), reading `main`'s hot-loop body from the
`--emit-obj` object — the same instrument as `constmul-guard`:

| compiler | loop body | verdict |
|---|---|---|
| 0.0.255 golden | **95** | **FAIL** (`95 > 90`) |
| 0.0.256 golden | **85** | PASS |

The probe's body holds eight single-use constants. Its `EXPECTED.tsv` row (rc 33)
is an independent second check: the comparison is true for i = 4, 5 and false
elsewhere, so an inverted setcc would return 75 and turn the row red.

## 5. Measured effect (instrument of record: `scripts/bench_instr.sh`)

38 benchmark rows, 0.0.255 vs 0.0.256, summed:

| metric | 0.0.255 | 0.0.256 | delta |
|---|---|---|---|
| `q_instr` | 8237 | 8062 | **-2.1 %** |
| `q_loop` (hot-loop body) | 1849 | 1732 | **-6.3 %** |
| `q_lst` (loop home stores) | 427 | 401 | **-6.1 %** |
| `q_hst` (home stores in `main`) | 1360 | 1318 | **-3.1 %** |

Loop body, per target row: `arith` 79->73, `div_const` 63->55,
`heavy_int`/`heavy_int2` 49->45, `heavy_div2` 37->31, `float` 118->116,
`heavy_float`/`heavy_float2` 56->54, `mutual_recursion` 52->48 (and `--fn is_odd`
67->64 against gcc's 12). 11 rows are byte-identical and that is the CORRECT
result for them (no loop, or no qualifying constant).

**Paired wall clock** (`scripts/bench_ab.sh 0.0.255 0.0.256 --runs 9` — two Quanta
binaries interleaved, no gcc denominator), loadavg 12.20/17.16/16.89 on entry and
12.26/16.45/16.66 on exit: `mutual_recursion` best 556->425 ms (-23.6 %), median
-13.1 %; `heavy_div2` -25.1 / -14.2 %; `div_const` -12.8 / -9.1 %. Those three
are negative in BOTH estimators. `arith`, `heavy_int` and `heavy_int2` show a large
best-of win and a POSITIVE median — at loadavg 12-17 this box cannot resolve below
~20 %, so those are drift, not code, and the instruction counts are the evidence.

## 6. Byte-identity — why it is not the right oracle here

Removing a materialisation frees a register, so downstream allocation moves; the
105 differing rows are therefore expected to differ by more than one instruction.
The one mechanical claim that IS exact is the instruction accounting: **every one
of the 105 differing rows SHRANK, and 0 of 248 rows grew** (total 692540 -> 678491
instructions). Equivalence otherwise rests on the behavioural oracles: the gate's
248/248 exit-code match, all 38 benchmark outputs against their C twins,
`differential` (`-O` == no-`-O` and vs-seed), `fuzz` fail-closed, `valgrind`, and
the 4-generation self-host fixpoint.

## 7. What is still open, per the author's row order

Named defects, each with emitted-code evidence in the research doc §9:

- **mutual_recursion** — call overhead, not arithmetic: five callee-saved
  registers pushed/popped per call when ONE is used (10 of ~64 instructions per
  `is_odd` call); the comparison materialised as a boolean
  (`xor;setcc;movzbq;test` vs gcc's `cmp;jcc`); arguments marshalled through home
  slots. MEASURED ceiling for the callee-save half alone: patching the emitted
  binary's unused push/pop pairs to nops moved best-of-7 from 510 ms to 400 ms
  (~22 %) with identical output.
- **float / heavy_float / heavy_float2** — `fphys()` still has ZERO call sites, so
  FP values live in GPRs and round-trip `xmm` on every operation (F4; A32 in
  0.0.253 removed its prerequisite). 98 of `float`'s 116 loop instructions are
  marshalling.
- **heavy_int / heavy_int2 / arith / div_const / heavy_div2** — home-slot
  marshalling for every live value, and `jno +2; ud2` on every integer
  add/sub/mul/neg (the `unsafe{}` opt-out exists but is per-operation, and is a
  benchmark-side decision that must be called out when taken).
- `docs/plans/language-capabilities.md` is UNCHANGED by this version: V1 needs no
  new language capability, only a proof that the constant is unused.
