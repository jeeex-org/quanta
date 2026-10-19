# 0.0.260 — WIP · **LEVER: the two discarded-return WRITER fixes (fail loud, or you have not written a binary)**

One lever, one version. Golden parent `0.0.259` (the ATOMICS release), which
**already contains this line's arena reclaim** — see §0. Full write-up with every
measurement: **`docs/research/phase6-arena-reclaim-0.0.260.md`**.

```
0.0.258 golden  md5 e7fc8cd4430ef3d4ef8e99067354bfcf   (frozen baseline, untouched)
0.0.259 golden  md5 (ATOMICS release; its tree carries the arena reclaim)
0.0.260 g1      md5 d34ef3109a12bfc8b3057c541ed5d8df   (built by 0.0.258's qc)
0.0.260 g2      md5 d34ef3109a12bfc8b3057c541ed5d8df
0.0.260 g3      md5 d34ef3109a12bfc8b3057c541ed5d8df
0.0.260 g4      md5 d34ef3109a12bfc8b3057c541ed5d8df   (distinct(g2,g3,g4) == 1)
0.0.260 -O == no-O == d34ef310, and the tree is seeded from compiler/0.0.259/src
                (src-tree md5 f42b868e8a1dedd9bb649f73d64f79e5, MATCHED against
                 the committed 0.0.259 tree before building)
```

## 0. VERSION LINEAGE — read this before judging the delta

`compiler/0.0.260/src` is **seeded from `compiler/0.0.259/src`**, the ATOMICS
tree. Verified before building, not assumed:

```
$ grep -c atomic compiler/0.0.260/src/x86/codegen.quanta   -> 17
$ grep -c atomic compiler/0.0.260/src/x86/emitter.quanta   -> 16
$ grep -c atomic compiler/0.0.260/src/x86/features.quanta  -> 17
$ grep -c atomic compiler/0.0.260/src/x86/parse.quanta     ->  2
$ diff -rq compiler/0.0.259/src compiler/0.0.260/src
  Files .../0.0.259/src/x86/elf.quanta   and .../0.0.260/src/x86/elf.quanta   differ
  Files .../0.0.259/src/x86/objfmt.quanta and .../0.0.260/src/x86/objfmt.quanta differ
$ grep -c 'mmap(41943040)|mmap(VREG_CAP \* 8)|mmap(32000000)|mmap(96000000)|\
mmap(1052672)|mmap(134217728)' compiler/0.0.260/src/x86/globals.quanta  -> 12 (the reclaim, carried)
```

So the atomics capability is **present**, the arena reclaim is **carried**, and
the ONLY source delta against 0.0.259 is this version's own lever.

The reclaim itself was developed in the 0.0.259 window and is **committed by
0.0.259's own commit** (a concurrent sibling unit owned that version number and
took the reclaim edits with it). This version adds the two red-first rows that
guard it, so the reclaim is now enforced rather than merely true.

## 1. The lever: `write_elf` and `p5_elf_obj` discarded BOTH return values

`elf.quanta` (the ELF writer) and `objfmt.quanta` (the `--emit-obj` writer) each
ended with the same two lines:

```
let ofd = file_open(outp, 577, 493)          // objfmt: let ofd=file_open(out_p,577,493)
if ofd >= 0 { file_write(ofd, elfb, elf_total); file_close(ofd) }
```

A failed open left `ofd` negative, the guarded body was **skipped**, and the
writer returned normally. **`qc SRC <unwritable>` therefore exited 0 having
written nothing.** Same class as the `--emit-qobj` discard that 0.0.257 fixed one
layer up; one layer down it was still open, on **both** 0.0.258 and 0.0.259.

Measured, three independent unwritable shapes (raw rc, both directions):

| invocation | 0.0.258 | 0.0.259 | 0.0.260 |
|---|---|---|---|
| `qc SRC <dir chmod 555>/out.bin` | **rc=0, no file, NOTHING on stderr** | **rc=0** | rc=1, `qc: error: cannot open the output file for writing` |
| `qc --emit-obj SRC <dir chmod 555>/out.o` | **rc=0, no file** | **rc=0** | rc=1, same diagnostic |
| `qc SRC <missing-parent>/out.bin` | **rc=0, no file** | **rc=0** | rc=1, same diagnostic |

Two things this establishes. (a) The `--emit-obj` path does **not** go through
`write_elf` at all — `entry.quanta` calls `p5_elf_obj(out_p)` and exits — so
fixing one writer leaves half the defect; the red-first row covers both modes.
(b) The failure is *silent*, which is why "an oversized alloc died silently (exit
0, no binary)" was mistakable for success for three units.

The fix, in both writers: name the open failure and `exit(1)`; then **verify the
byte count** (`file_write` returns the write syscall's result) so a short write — a
full disk — is not the same silent success.

## 2. Red-first rows

Three new cases in `test_suites/scripts/output_path_guard_test.sh` (the stage the
gate already runs as `output-path`), asserting **non-zero exit AND no artifact AND
a named diagnostic**. A row reading only the exit status could not see this defect
— on 0.0.258/0.0.259 the exit status is 0.

```
0.0.258, 0.0.259   9 PASS, 3 FAIL -> OUTPUT-PATH GUARD: FAIL
0.0.260           12 PASS, 0 FAIL -> OUTPUT-PATH GUARD: PASS
```

The pre-existing cases (the `qc SRC SRC` self-overwrite refusals) stay green on all
three versions — the control that the new cases are not passing for an unrelated
reason.

## 3. The reclaim's guard row (new Stage 1.6o)

```
PASS va-reclaim: the compiler self-compiles under a 1,572,864 KB address-space cap
```

| | 0.0.258 | 0.0.259 | 0.0.260 |
|---|---|---|---|
| min `ulimit -v`, self-compile (**bisected**) | **4,903,320 KB** | 1,006,640 KB | 1,005,128 KB |
| VmPeak, self-compile (5 ms sampler) | 4,900,244 KB | 1,005,200 KB | 1,005,128 KB |
| min `ulimit -v`, `abort_test` | 4,743,820 KB | — | 848,784 KB |
| max RSS, self-compile | 183,356 KB | — | 183,356 KB |

`VARG_LIMIT` is **1,572,864 KB = 1536 MiB**, i.e. the new `COMPILER_MEM_MB`
recommendation (was 6144), a **56%** margin over the measured worst case — and the
same number as the compiled-binary ceiling, so the compiler no longer needs
headroom the programs it produces do not. **`scripts/qcrun.sh` is outside this
unit's pathspec; its owner should set `COMPILER_MEM_MB=1536`.** Until then the
reclaim is true but only the gate row enforces it.

## 4. Byte-identity, with the mechanical cross-check

`0.0.260` vs `0.0.258`, all 249 `EXPECTED.tsv` baseline rows, `-O`, `cmp`'d:

```
baseline_rows=249  rows_measured=254  identical=248  differing=1  compile_fail=0
differing: lfm2_threaded_pool_test.quanta
```

**The one differing row is the atomics row**, inherited from 0.0.260's base — and
it is the *expected* signature of that lever, not of this one. Two independent
measurements make that attribution:

| tree | identical / differing |
|---|---|
| reclaim alone (reconstruction, `1e1edbe9`) | **249 / 0** |
| 0.0.259 tree (reclaim + atomics) | 248 / 1 — `lfm2_threaded_pool_test.quanta` |
| 0.0.260 tree (…+ this version's writer fix) | 248 / 1 — **the same row** |

This version's writer fix adds **zero** differing rows: it changes code only on the
failure path, so the count-identical set and the byte-identical set stay equal on
all 248 unchanged rows.

## 5. What this version does NOT do

* **F4 (xmm-resident FP) is NOT landed.** The three worst rows are unmoved. See §6.
* **Comparison → `jcc` fusion is NOT landed.**
* The nine author's rows have therefore **not** been driven to <= 1.00x.

## 6. The nine author's rows, measured under 0.0.260 (all still > 1.00x)

`scripts/bench_instr.sh` hot-loop instruction counts (`q_loop` / `c_loop`), which
are exact and load-free; wall clock on this box has shown 1.24-1.54x spread within
one arm and is not the instrument. Load average 10.20/10.39/10.41 before,
10.66/10.48/10.44 after.

| author's row | q_loop | c_loop | ratio | <= 1.00x? |
|---|---:|---:|---:|---|
| `mutual_recursion` (`main`) | 48 | 10 | 4.80x | **no** |
| `mutual_recursion` (`is_odd`, the function the author's `44/12` names) | — | — | 3.67x (whole-fn 44/12) | **no** |
| `heavy_float2` | 54 | 6 | **9.00x** | **no** |
| `heavy_int2` | 45 | 7 | 6.43x | **no** |
| `float` | 116 | 8 | **14.50x** | **no** |
| `heavy_float` | 54 | 6 | **9.00x** | **no** |
| `heavy_int` | 45 | 7 | 6.43x | **no** |
| `heavy_div2` | 31 | 7 | 4.43x | **no** |
| `arith` | 73 | 20 | 3.65x | **no** |
| `div_const` | 55 | 15 | 3.67x | **no** |

`regpressure` and `float_ops` are deliberately omitted (gcc collapses the affine
temps / constant-folds the loop). `mutual_recursion` had to be measured twice: the
author's `44/12` reproduces exactly for `--fn is_odd` (Quanta 44 whole-function
instructions vs gcc 12 = 3.67x), while the hot-loop reading of `main` is 48/10 =
4.80x — the author's list mixes the two metrics for that one row, so both are given.
