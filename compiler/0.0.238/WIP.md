# 0.0.238 — WIP · **PROMOTED** (gate fully green, 225/225, STDLIB 108/108)

**Lever: constant division and modulo by strength reduction.** `/` and `%` by a positive
compile-time constant no longer emit `idiv`. One lever, one version, one mechanism.

Committed golden: `compiler/0.0.238/bin/x86/qc`, md5 `a87e6e1f1e4cacb7f94507a6b54d0093`
(the self-host fixed point — see "Reproducibility").

## 1. What landed

- `src/x86/emitter.quanta` — four encodings: `rsar_imm` (sar r64, imm8), `rand_imm` (and r64,
  imm32), `rimul1` (one-operand `imul`, the mulhi half of a 128-bit product) and `rimul_imm`
  (`imul r64, r/m64, imm32`).
- `src/x86/codegen.quanta` — `op_is_iconst`/`op_iconst_val` (IR_CONST only, never IR_FCONST),
  `emit_cdiv_core` (the magic-multiply core, with the derivation in its header comment), and the
  rewritten `IR_DIV` / `IR_MOD` integer arms.
- `test_suites/codes/divmod_floor_semantics_test.quanta` + `divmod_const_strength_test.quanta`,
  both in `EXPECTED.tsv` at rc 42 (180 and 550 hand-derived checks respectively).
- `test_suites/EXPECTED.tsv` — the missing A6 row restored (see §7).
- `benchmarks/` — four repaired cases and two new harness behaviours (§8).
- `scripts/bench_ab.sh` (new), `scripts/bench.sh` (resolution floor + quarantine marker),
- `scripts/verify-release.sh` check 6 corrected for codegen-changing releases (§6).

## 2. The defect this also removes

The tree already had a "P3: power-of-2 division -> arithmetic shift right" path. It emitted the
`sar` and then **fell through** into the `idiv` sequence below it, so every constant division paid
BOTH. Disassembly of `sum = sum + i/128 + i/3 + i%5` on 0.0.237:

```
  mov -0x50(%rbp),%rax ; sar $0x7,%rax        <- the power-of-two path DOES fire ...
  mov %rax,-0x90(%rbp)                        <- ... stores its result ...
  mov -0x50(%rbp),%rax ; mov -0x98(%rbp),%rcx
  cqto ; idiv %rcx                            <- ... and then recomputes the same value with idiv
  ...  mov %rax,-0xb0(%rbp) ; sar $0x0,%rax   <- shift 0 (a NO-OP, d=3 is not a power of two)
  cqto ; idiv %rcx                            <- and recomputes THAT with idiv too
```

The `else { opt_i = ii+1 }` that was meant to make the shift branch skip the idiv assigned the
*optimizer pass'* cursor, not the *emit loop's* `ii`, so it did nothing. 0.0.238 replaces the whole
arm: the idiv sequence is now reached only for a variable divisor, a non-positive constant, or a
constant above 2^31-1. Same program on 0.0.238 — 5 `idiv` -> 1 (the remaining one is `print`'s
decimal conversion), and the output is identical (`170637414635`).

## 3. Semantics: floor, and the correctness argument

Quanta's integer division is FLOOR and the remainder takes the DIVISOR's sign. Re-verified on the
real binary this version (not inherited from the docs):

```
  -7 / 2 = -4    -7 % 2 = +1      7 / -2 = -4    7 % -2 = -1
  -7 / -2 =  3   -7 % -2 = -1    -8 / 2 = -4    -8 % 2 =  0
  INT64_MIN / 3 = -3074457345618258603   INT64_MIN % 3 = 1
```

That is what makes the reduction both simple and safe:

| divisor | `/` | `%` |
|---|---|---|
| `d = 1` | copy | 0 |
| `d = 2^k` | `sar` (an arithmetic shift IS floor, correct for all of int64) | `a & (2^k - 1)` (two's-complement low bits = floor mod) |
| `3 <= d <= 2^31-1`, not a power of two | magic multiply + floor fix | magic multiply + `d & (r>>63)` |

Magic case, with `(M, sh) = compute_magic(d)` (the generator already in `emitter.quanta`):

```
  q0 = mulhi_s(a, M)          ; signed high half of a 128-bit product (imul rdx)
  if M < 0: q0 += a           ; the add arm -- M is LEGITIMATELY negative for d = 15, 100, ...
  q0 >>= sh                   ; arithmetic shift
  q_t = q0 + (a<0 ? 1 : 0)    ; == trunc(a/d)
  r_t = a - q_t*d             ; == the truncation remainder (sign of a)
  floor(a/d) = q_t + (r_t >> 63)        ; r_t>>63 is -1 iff a<0 and d does not divide a
  floor(a%d) = r_t + (d & (r_t >> 63))
```

Both correction steps are load-bearing: the `+1` alone gives TRUNCATION (it equals floor only when
`d | a`), and the `add a` arm is needed because the magic's `M` can be negative for a positive `d`.

**Python verification: 4,913,317 (d, a) pairs, ZERO mismatches** against Python's `//` and `%`.
Every `d` in 3..400 plus a spread of large divisors; for each `d`, every `a` in -4000..4000 plus
`2^63-1`, `-2^63`, `+-2^62`, and 4000 random full-range int64 values.

**End-to-end verification through the real compiler: 1,556 checks, 0 mismatches, table below.**

| check | how | result |
|---|---|---|
| generated values vs Python floor | a 1,556-value sweep compiled by 0.0.238 and diffed against Python | **1556/1556 match**, including INT64_MIN/INT64_MAX, +-2^62, 4 negative divisors, and a runtime-divisor loop |
| the lever changes NO result | the same sweep compiled by 0.0.237 vs 0.0.238 | **byte-identical stdout** |
| floor semantics is pinned in the gate | `divmod_floor_semantics_test` (180 cases, runtime divisors) | rc 42 on 0.0.237 AND 0.0.238 |
| the constant path is pinned in the gate | `divmod_const_strength_test` (550 checks, literal divisors) | rc 42 on 0.0.237 AND 0.0.238 |
| those two rows are NOT vacuous | both compiled by a variant with the floor corrections removed | **rc 101 / rc 105** (rc 105 names divisor index 2 = `3`, the `-7/3` case) — red-first |

## 4. Measured effect — and a recorded premise that this REFUTES

### 4a. The noise-free A/B (`scripts/bench_ab.sh`, same source, both Quanta compilers, 15 runs
interleaved, load ~9.8). This is the table that answers "did the codegen change help?"

**25 of 37 cases produce BYTE-IDENTICAL machine code on both compilers.** For those, any timing or
ratio difference is noise *by definition* — and the swings reach +-17 % (`mem_ops` +16.7 %,
`recursion` +14.3 %, `fib_recursive` +12.0 %, `struct` -11.1 %) on code that did not change by a
single byte. **Every one of the 12 cases whose code DID change is neutral-to-faster:**

| case | best-of-15 A->B | median A->B |
|---|---|---|
| arith | 199->192 ms (-3.5%) | 254->229 ms (-9.8%) |
| big_array | 7->7 ms (+0.0%) | 10->9 ms (-10.0%) |
| div_const | 127->114 ms (-10.2%) | 148->142 ms (-4.1%) |
| file_io | 4->4 ms (+0.0%) | 7->7 ms (+0.0%) |
| fileio | 90->87 ms (-3.3%) | 102->99 ms (-2.9%) |
| heavy_div | 73->70 ms (-4.1%) | 88->76 ms (-13.6%) |
| heavy_div2 | 686->672 ms (-2.0%) | 852->724 ms (-15.0%) |
| heavy_int | 433->380 ms (-12.2%) | 481->420 ms (-12.7%) |
| heavy_int2 | 1622->1503 ms (-7.3%) | 1919->1666 ms (-13.2%) |
| q4k | 9->8 ms (-11.1%) | 11->10 ms (-9.1%) |
| q4k_heavy | 22->22 ms (+0.0%) | 27->26 ms (-3.7%) |
| q4k_matmul | 6->6 ms (+0.0%) | 7->7 ms (+0.0%) |

### 4b. The premise is refuted

`docs/plans/performance.md` recorded (measured on 0.0.233) that the 6.8-32.3x arithmetic-loop cluster
was caused by `idiv` for constant division, and predicted those rows would "move toward <=3x".
Measured on 0.0.238 they barely move (`heavy_int2` 35.5->27.7, `div_const` 13.3->12.2, `arith`
14.4->14.7, `heavy_int` 22.0->22.0). Removing essentially every hot-loop `idiv` buys **0-12 %**, not
multiples. So `idiv` was NOT the dominant cost.

What is left is the per-operation spill/reload traffic the same document measures as `work()` = 254
instructions vs gcc's 9. **The remaining lever is A4 / next-use eviction** (home-slot reuse;
1104-byte frames), which 0.0.237's A1b work unblocked and this version does NOT touch. That is the
thing to do next, and this measurement is the argument for it.

### 4c. Per-case table, 0.0.237 baseline -> 0.0.238, with gcc

Load: baseline 10.14, 9.78, 9.79 / after 11.72, 10.36, 9.99. Rows under 30 ms are tagged — they are best-of-15 and still at the
harness resolution floor (the SAME unchanged C binary reported 10 ms then 6 ms across baseline runs).

| case | Q 0.237 | Q 0.238 | dQ | C 0.237 | C 0.238 | ratio 0.237 | ratio 0.238 | note |
|---|---|---|---|---|---|---|---|---|
| arith | 202 | 206 | +2.0% | 14 | 14 | 14.43 | 14.71 | best-of-15 (<30ms row) |
| big_array | 9 | 8 | -11.1% | 7 | 7 | 1.29 | 1.14 | best-of-15 (<30ms row) |
| closure_call | 15 | 15 | +0.0% | 8 | 8 | 1.88 | 1.88 | best-of-15 (<30ms row) |
| closure_capture | 16 | 14 | -12.5% | 9 | 8 | 1.78 | 1.75 | best-of-15 (<30ms row) |
| div_const | 120 | 110 | -8.3% | 9 | 9 | 13.33 | 12.22 | best-of-15 (<30ms row) |
| enum | 7 | 5 | -28.6% | 7 | 5 | 1.00 | 1.00 | best-of-15 (<30ms row) |
| fib | 6 | 6 | +0.0% | 6 | 6 | 1.00 | 1.00 | best-of-15 (<30ms row) |
| fib_recursive | 23 | 23 | +0.0% | 8 | 8 | 2.88 | 2.88 | best-of-15 (<30ms row) |
| file_io | 6 | 6 | +0.0% | 6 | 6 | 1.00 | 1.00 | best-of-15 (<30ms row) |
| fileio | 90 | 82 | -8.9% | 23 | 19 | 3.91 | 4.32 | best-of-15 (<30ms row) |
| float | 103 | 104 | +1.0% | 18 | 17 | 5.72 | 6.12 | best-of-15 (<30ms row) |
| float_ops | 6 | 6 | +0.0% | 6 | 6 | 1.00 | 1.00 | best-of-15 (<30ms row) |
| fnptr_indirect | 23 | 20 | -13.0% | 8 | 7 | 2.88 | 2.86 | best-of-15 (<30ms row) |
| generic_call | 19 | 20 | +5.3% | 8 | 7 | 2.38 | 2.86 | best-of-15 (<30ms row) |
| heavy_div | 75 | 74 | -1.3% | 8 | 8 | 9.38 | 9.25 | best-of-15 (<30ms row) |
| heavy_div2 | 789 | 715 | -9.4% | 24 | 21 | 32.88 | 34.05 | best-of-15 (<30ms row) |
| heavy_float | 89 | 104 | +16.9% | 14 | 14 | 6.36 | 7.43 | best-of-15 (<30ms row) |
| heavy_float2 | 493 | 493 | +0.0% | 42 | 44 | 11.74 | 11.20 |  |
| heavy_int | 417 | 396 | -5.0% | 19 | 18 | 21.95 | 22.00 | best-of-15 (<30ms row) |
| heavy_int2 | 1881 | 1664 | -11.5% | 53 | 60 | 35.49 | 27.73 |  |
| heavy_mem | 23 | 21 | -8.7% | 8 | 8 | 2.88 | 2.62 | best-of-15 (<30ms row) |
| heavy_recursion | 10 | 8 | -20.0% | 7 | 5 | 1.43 | 1.60 | best-of-15 (<30ms row) |
| higher_order | 17 | 20 | +17.6% | 6 | 7 | 2.83 | 2.86 | best-of-15 (<30ms row) |
| int_ops | 6 | 6 | +0.0% | 6 | 6 | 1.00 | 1.00 | best-of-15 (<30ms row) |
| loop_sum | 10 | 9 | -10.0% | 6 | 5 | 1.67 | 1.80 | best-of-15 (<30ms row) |
| match | 6 | 6 | +0.0% | 6 | 7 | 1.00 | 0.86 | best-of-15 (<30ms row) |
| mem | 18 | 20 | +11.1% | 7 | 7 | 2.57 | 2.86 | best-of-15 (<30ms row) |
| mem_ops | 6 | 5 | -16.7% | 6 | 6 | 1.00 | 0.83 | best-of-15 (<30ms row) |
| mutual_recursion | 659 | 605 | -8.2% | 60 | 63 | 10.98 | 9.60 |  |
| nested_calls | 6 | 6 | +0.0% | 6 | 6 | 1.00 | 1.00 | best-of-15 (<30ms row) |
| params8 | 27 | 25 | -7.4% | 7 | 6 | 3.86 | 4.17 | best-of-15 (<30ms row) |
| q4k | 8 | 8 | +0.0% | 6 | 8 | 1.33 | 1.00 | best-of-15 (<30ms row) |
| q4k_heavy | 18 | 22 | +22.2% | 6 | 8 | 3.00 | 2.75 | best-of-15 (<30ms row) |
| q4k_matmul | 6 | 7 | +16.7% | 6 | 7 | 1.00 | 1.00 | best-of-15 (<30ms row) |
| recursion | 6 | 5 | -16.7% | 6 | 5 | 1.00 | 1.00 | best-of-15 (<30ms row) |
| string | 6 | 5 | -16.7% | 6 | 6 | 1.00 | 0.83 | best-of-15 (<30ms row) |
| struct | 6 | 5 | -16.7% | 6 | 5 | 1.00 | 1.00 | best-of-15 (<30ms row) |

### 4d. The 12 previously-parity cases

| case | code changed? | ratio 0.237 -> 0.238 | held? |
|---|---|---|---|
| nested_calls | IDENTICAL | 1.00 -> 1.00 | yes (byte-identical code, delta is noise) |
| recursion | IDENTICAL | 1.00 -> 1.00 | yes (byte-identical code, delta is noise) |
| float_ops | IDENTICAL | 1.00 -> 1.00 | yes (byte-identical code, delta is noise) |
| match | IDENTICAL | 1.00 -> 0.86 | yes (byte-identical code, delta is noise) |
| mem_ops | IDENTICAL | 1.00 -> 0.83 | yes (byte-identical code, delta is noise) |
| file_io | differs | 1.00 -> 1.00 | yes (code changed, still <=0 delta) |
| fib | IDENTICAL | 1.00 -> 1.00 | yes (byte-identical code, delta is noise) |
| q4k_matmul | differs | 1.00 -> 1.00 | yes (code changed, still <=0 delta) |
| string | IDENTICAL | 1.00 -> 0.83 | yes (byte-identical code, delta is noise) |
| big_array | differs | 1.29 -> 1.14 | yes (code changed, still <=0 delta) |
| q4k | differs | 1.33 -> 1.00 | yes (code changed, still <=0 delta) |
| mem | IDENTICAL | 2.57 -> 2.86 | yes (byte-identical code, delta is noise) |

**All 12 held. No case regressed**: every row whose machine code changed is <= 0 in the 15-run
interleaved A/B, and any row that looks slower in the ratio table is a row whose code is
byte-identical (or an above-30 ms row in the same noise band as the A/B's own identical-code swings).

## 5. Gate, fixpoint, reproducibility

```
=== Results: 225/225 pass, 0 fail (incl. 0 compile-fail) [rows: EXPECTED.tsv] ===
  STDLIB: 108/108 GREEN
  all 24 stages GREEN, GATE EXIT=0
```

Row accounting: 222 at the 0.0.237 baseline + 1 restored A6 row + 2 new div/mod rows = **225**. No
existing row changed rc and no row was removed.

| check | value |
|---|---|
| 0.0.237 baseline is a frozen, reproducible baseline | its own source rebuilds to `dca6b4ab229f17b0b8e2d7e29874e401` bit-for-bit |
| fixed point (3 generations, all built by the committed binary) | `a87e6e1f1e4cacb7f94507a6b54d0093` x3, **distinct = 1**, == the committed binary |
| reproducible from version control alone | 0.0.237 golden + committed source -> `b1623ec1`, then `b1623ec1` + committed source -> `a87e6e1f` == committed |
| `SELFHOST` (`scripts/selfhost_consistency.sh`) | see the run in this version's commit message |

### Why the committed binary is the SECOND generation, not the first

The seed-built compiler (`b1623ec1`, built by 0.0.237 from the 0.0.238 source) is NOT byte-identical
to the committed one, and that is correct for a codegen-changing release: the seed-built binary still
carries the OLD codegen for the compiler's own source. The difference is measurable and confined:
seed-built contains **147 `idiv`**, the committed one **9** — it is this release's whole effect applied
to the compiler. The two compilers are functionally identical: compiling a division-heavy program with
either produces **byte-identical output** (`b1f88d13bb4b921a5f79fe022e15aa38`).
`.github/workflows/ci.yml` promotes exactly this artifact and records the same property ("the fixpoint
is the SECOND generation, not the first").

## 6. `verify-release.sh` check 6 — corrected, not waived

Check 6 used to require `compiler/<NEXT>/bin/x86/qc` == a build of `<NEXT>` source by the `<VER>`
golden. That silently assumes the two releases emit the same machine code, which is true only for a
front-end change; on a codegen-changing release it is a **permanent false red**. It is now the real
invariant: walk the seed chain (`VER` golden -> g1 -> g2 -> ...) to its fixed point and require the
committed binary to BE that fixed point. A committed binary that no chain from the committed tree can
produce still FAILS, so nothing is waived.

Both directions were measured:

| tree | result |
|---|---|
| healthy (committed `a87e6e1f`) | `=== 11 passed, 0 failed ===`, exit 0 |
| `0.0.237`'s binary installed as 0.0.238's (an unreproducible artifact) | check 6 FAIL, `=== 10 passed, 1 failed ===`, **exit 1** |

## 7. The A6 gate row (restored)

`f64_call_order_test.quanta` existed in `test_suites/codes/` but had NO row in `EXPECTED.tsv` — it was
unlisted during an earlier gate cleanup, so nothing stopped the 0.0.236 f64 call-order miscompile from
regressing. Row restored at expected rc 0. Measured red-first on the pre-fix compiler:

| compiler | compile | run |
|---|---|---|
| `compiler/0.0.235/bin/x86/qc` (pre-fix) | rc 0 | **rc 1** (wrong value) |
| `compiler/0.0.236/bin/x86/qc` | rc 0 | rc 0 |
| `compiler/0.0.237/bin/x86/qc` | rc 0 | rc 0 |
| `compiler/0.0.238/bin/x86/qc` | rc 0 | rc 0 |

## 8. Benchmark suite repairs and harness changes (this version)

| item | what was wrong | disposition |
|---|---|---|
| `closure_capture` | a `known-fail: compiler SEGFAULT` marker that outlived the 0.0.237 A1b fix (bench.sh flags that as a structural failure) | marker removed; verified printing `500006500000` = the hand-computed sum |
| `closure_capture.c` | did not COMPILE (`struct env` declared inside the parameter list -> incompatible pointer) — the row measured nothing | declared once before the typedef |
| `closure_capture.c` | then gcc devirtualised the struct-held fn pointer and folded the loop (0 jumps in `main`) | the closure object is `volatile` (1 jump, 2 call sites) |
| `heavy_float2` | the Quanta side called `f64bits("sum=")` — a STRING handed to a bit-pattern extractor — so it printed garbage where the twin printed text. The arithmetic was right: the f64 bit pattern matched gcc's exactly | `print("sum=")` |
| `q4k`, `q4k_heavy` | `MISMATCH -1280 vs 0`. NOT a compiler defect: the DERIVED C twin used `1 << shift` where its Quanta twin uses `1 * shift` (scale_q8 0 vs 24), and C truncation where this language is floor (`-3624/128` = -28 vs -29). Isolation table in `benchmarks/BENCHMARK.md` "Defect 4" | C twin corrected (same algorithm + a `qdiv()` floor helper); both rows now agree exactly at `-1280` |
| `scripts/bench.sh` | a 5-10 ms row's ratio was decided by scheduler jitter (the same unchanged C binary reported 10 ms and 6 ms) | rows under 30 ms now run best-of-15, tagged in the table |
| `scripts/bench.sh` | no way to attach a reason to a known-divergent row | `// mismatch-reason:` marker, which does NOT silence the equality check |
| `scripts/bench_ab.sh` | (new) no way to compare two compilers without the gcc denominator | A/B harness, interleaved, reports byte-identity of the generated code |
| `benchmarks/BENCHMARK.md` | table regenerated; Defect 4/5 and the floor-semantics section updated | see the file |

Filed, deliberately NOT fixed here: the `q4k` Quanta twins write `(1 * shift)` where the standard FP16
scale is `(1 << shift)`. That is a benchmark-DATA question — correcting it makes scale_q8 = 0 for the
current `W` byte, so the payload degenerates and the `W` byte must be retuned in the same change.
Recorded as "Defect 5" in `benchmarks/BENCHMARK.md`.

## 9. A false green that was NOT real (investigated, no defect)

An earlier report claimed `verify-release.sh` printed `=== 10 passed, 1 failed ===` and then exited 0.
Re-measured: the script's real exit status was **1**. The 0 came from the reporting pipeline —
`bash verify-release.sh ... | tail -30; echo "$?"` captures `tail`'s status, not the script's.
`scripts/verify-release.sh` ends with `[[ $FAIL -eq 0 ]] || exit 1`, and the red-first run in §6
confirms it exits 1 with a FAIL. No change was needed; the measurement was wrong, and the same
mistake is worth avoiding everywhere (read `PIPESTATUS`, or redirect instead of piping).

## 10. Not verified / open

- **The payoff is small.** 0-12 % on the 12 changed rows. The version is a strict improvement with no
  regression, but it is NOT the gap-closer `docs/plans/performance.md` predicted, and the plan's
  predicted ratios are explicitly refuted in §4b.
- **Non-power-of-two divisors above 2^31-1 and non-positive constant divisors still use `idiv`.** No
  benchmark or gate row exercises them; they are correct (they take the unchanged path) but unoptimised.
- **`docs/status.json` is stale** on `test_suites_codes_tests` (619 vs 631 actual). It was already stale
  before this version (12 files, of which 2 are this version's) and the verify-status gate stage passes,
  which suggests the stage does not compare that field. `bash scripts/regen_status.sh` refreshes it; not
  run here to keep this version's diff to its own concern.
- **`q4k` ratios are not comparable with pre-repair runs**: the C twins' floor helper made the C side
  slightly slower, by design (the twins now compute the same function).
- **Rows under 30 ms remain noise-dominated** even at best-of-15. Nothing in the tables should be read as
  a sub-10 ms win or loss.
