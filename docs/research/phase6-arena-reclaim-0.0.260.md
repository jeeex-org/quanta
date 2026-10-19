# 0.0.260 — the ARENA RECLAIM (4.90 GB → 1.01 GB) and the two discarded-return writer fixes

> **VERSION LINEAGE, because it matters for reading every number here.** The
> reclaim was developed in the 0.0.259 window and its source edits are present in
> `compiler/0.0.259/`, which a **concurrent sibling unit owns** and which also
> carries an unrelated ATOMICS lever (see §10). The reclaim is therefore
> *committed* by 0.0.259's commit, not by this one. **0.0.260 is seeded from the
> peer's `compiler/0.0.259/src` (verified atomics-present before building, per
> `grep -c atomic`), carries the reclaim forward, and adds this version's own
> lever: the two `write_elf` / `p5_elf_obj` fail-loud fixes (§11).** Every
> measurement in §0-§8 was taken on a *reconstruction containing the reclaim and
> nothing else* (`apply_reclaim.py`, md5 `1e1edbe91f06e645483e8f965409ff61`), so
> no figure below is credited to the atomics lever.


**One lever, one version. MEASURED: 249/249 gate rows BYTE-IDENTICAL to 0.0.258,
0 instruction-count rows changed (0 shrank, 0 grew).** The reclaim changes no
emitted instruction; it removes up-front address-space reservations that were
sized "big enough" instead of from a measured high-water.

Baseline `c99ce5d7` (0.0.258, golden `e7fc8cd4430ef3d4ef8e99067354bfcf`). Every
number below is MEASURED on this box; the instrumentation is described in §2 so
each figure can be reproduced.

---

## 0. The finding this acts on

A full self-compile of `main.quanta` (497 registered functions, 26 s, exit 0) has
**max RSS 183,356 KB** while **reserving multi-GB address space**. The compiler's
memory *problem* is not memory. Bisected `ulimit -v`, 0.0.258 needs:

| input | min `ulimit -v` (KB) | RSS |
|---|---|---|
| `test_suites/codes/abort_test.quanta` | **4,743,820** | ~112,000 |
| the compiler's own `main.quanta` (worst case) | **4,903,320** | 183,356 |

So **~4.7 GB of the 4.9 GB is a fixed reservation**, paid to compile *any* input,
including a 5-line test. It is not touched by the workload: `abort_test` and the
self-compile need the same 4.7 GB and differ by 160 MB.

That reservation — not memory — is what `scripts/qcrun.sh`'s
`COMPILER_MEM_MB=6144` (6,291,456 KB) ceiling constrains, and it is why a
compiler that runs out of address space **dies silently**: 0.0.257's write-up
measured the whole `--emit-qobj` step producing *no file* and exiting 0. Three
separate units lost time to a fragility class that is, at bottom, a `mmap` size
chosen by guess.

## 1. What was actually reserved, per arena

The predecessor reclaimed one arena (`ir_unsafe`, 1.6 GB → 26.8 MB, 0.0.257).
Measuring the rest with an instrumented tree (§2) gives, for each of the six
remaining up-front arenas, its **real high-water mark** and the honest size:

| arena | 0.0.258 | measured high-water (what it actually uses) | 0.0.259 | margin | basis |
|---|---:|---|---:|---:|---|
| `ir` | 1,073,741,824 | **19,969 records** = 798,760 B (one function, self-compile; gate max 7,452) | 41,943,040 | **52x** | `ir` is reset by `vclr(); irc=0` per source function — it holds ONE function, it never accumulates |
| `lit_addr` | 1,073,741,824 | **13,842** = the max vreg INDEX written | 3,200,000 | **28.9x** | keyed by `res*8`, `res` < `VREG_CAP` (400000) by construction |
| `qir_mod` | 1,073,741,824 | **153,487 records** = 6,139,480 B (G6: the WHOLE COMPILER imported as one cached module) | 32,000,000 | **5.2x** | the only arena that genuinely accumulates: total imported cache IR |
| `ir_unsafe` | 26,847,641 | must cover `max(IR_CAP, qir_mod cap)` = 1,048,576 B | 1,052,672 | exact | one byte per live IR index, written by `iremit` and by `objfmt` |
| `toks` | 512,000,000 | **203,378 tokens** = 9,762,144 B (self-compile; 765,423 B of expanded source) | 96,000,000 | **9.8x** | linear in source size |
| `code` | 536,870,912 | **2,388,233 B** of machine code (G6 cache-only build of the whole compiler) | 134,217,728 | **56x** | output size |

Left alone, with the reason:

| arena | size | why it is NOT "big enough" padding |
|---|---:|---|
| `impbufs` | 134,217,728 | 8 slots x 16 MB indexed by `depth%8`. The 16 MB is the **maximum includable file size** (`file_read(fd, ib, 16777216)`), and the 8 is the wrap point of the include depth. MEASURED max include depth over the corpus: **5** (6 slots used) and the largest file actually included is 181,636 B. The size is a real capability bound, not padding — shrinking a slot silently truncates a large include. |
| `data` | 33,554,432 | string-literal buffer. MEASURED max `data_off`: 17,744 (source compile), 85,952 (G6 cache-only, where every imported literal lands here). 390x over, but 32 MB of a 1 GB budget: not worth the risk this version. |
| `qir` | 16,777,216 | holds a module cache's IR region while it is read. The G6 cache of the whole compiler is 6,405,655 B of which 6,139,480 is IR — so 16 MB is only **2.6x** a real, exercised input. Correctly sized already. |
| `patches`, `gpatches`, `vars`, `fns`, `alloc`, the `vreg_*` tables | — | already derived from their caps, and the caps from the arenas, by earlier fixes (`FN_CAP`, `ALLOC_CAP`, `VREG_CAP`). MEASURED `patchc` max 32,969 against `PATCH_CAP` 330,000. |

### Caps lowered IN LOCKSTEP

An arena may never be smaller than the cap that guards it — that is the defect
class `FN_CAP`/`ALLOC_CAP`/`IR_CAP` were each fixed for once. Every lowered arena
has its guard lowered in the same commit:

| cap | 0.0.258 | 0.0.259 | guard |
|---|---:|---:|---|
| `IR_CAP` (helpers) | 26,843,545 | **1,048,576** | `iremit`: `irc >= IR_CAP` → `emit_ovf()` (site 2) |
| `TOK_CAP` (helpers) | 10,000,000 | **2,000,000** | `stok`/`stoke`/`tokln`: `i >= TOK_CAP` (site 1) |
| `CODE_CAP` (globals) | 536,870,912 | **134,217,728** | `eb`/`ei`/`eq`, `codelen+7 > CODE_CAP` |
| `qir_mod` bound (objfmt) | 26,843,545 | **800,000** | `qir_mod_n >= 800000` → fail closed, `return 0`, no binary |

If a program ever exceeds one of these, it fails **closed and named** (exit 17,
with the cap's site number), which is the behaviour every one of these guards was
written for. What changes is the input size at which that happens: the smallest
headroom is `qir_mod` at 5.2x (imported cache IR) and the largest restriction in
absolute terms is `code`, 56x the largest binary this project has ever emitted.

## 2. How the high-water marks were measured (not guessed)

A **scratch copy** of `src/x86` (`/tmp/g9/instr/x86`, never committed) was patched
to maintain high-water counters and dump them to fd 2 before every `exit(0)`:

| counter | update site |
|---|---|
| `hw_irc` | `iremit` (`irc` after increment) |
| `hw_tokc` | `stok` (`i+1`) |
| `hw_vreg` | `ci_func`'s `vreg_n = maxvr + 1` **and** `nv()` |
| `hw_lit_res` | the `IR_STR` codegen write `w64(lit_addr + res*8, ...)` |
| `hw_qirmod` | `objfmt`'s `qir_mod_n = qir_mod_n + 1` |
| `hw_depth` | `expand_includes` |
| plus `codelen`, `data_off`, `fnc`, `patchc`, `qir_mod_n`, `srclen` at exit |

It was then run over **all 361 sources** in `EXPECTED.tsv` +
`EXPECTED_STDLIB.tsv` + `EXTERN_EXPECTED.tsv` (0 compile failures) and over:

* the compiler's own `main.quanta` (the largest single input in the project), and
* the **G6 cache-only build** — `--emit-qobj main.quanta`, delete every `.quanta`,
  build from the cache alone — which is the only construction that drives
  `qir_mod_n` (153,487) and produces the largest `codelen` (2,388,233).

The G6 run is reproduced by `scripts/g6_selfcache.sh` and is a live gate stage, so
the `qir_mod`/`code` bounds rest on an input the gate actually exercises.

## 3. The two biases that had to be controlled

**(a) An arena that is reset is not an arena that accumulates.** `ir` at 1 GiB
was justified in-source by `IR_CAP = 26843545` records — but `entry.quanta` does
`vclr(); irc=0` at the top of every source function, so the count never reaches
more than one function's IR. Sizing from the cap measured a **bound on a quantity
that never accumulates**: 1 GiB for 19,969 records.

**(b) The worst case is not the gate corpus.** The 249-row gate's own maxima
(`hw_irc` 7,452, `hw_tokc` 55,206, `codelen` 527,429) are 2.7-5x *below* the
self-compile's. Sizing from the gate corpus alone would have under-provisioned by
that factor. Every new size above is set from the **self-compile / G6** maxima,
i.e. the project's largest real inputs.

## 4. Result

| | 0.0.258 | 0.0.259 | delta |
|---|---:|---:|---:|
| fixed reservation, sum of the arenas above | 4,296,944,025 B | 308,413,440 B | **-3,988,530,585 B (-92.8%)** |
| min `ulimit -v`, self-compile (**bisected**) | **4,903,320 KB** | **1,006,640 KB** | **-3,896,680 KB (-79.5%, 4.87x)** |
| VmPeak, self-compile (sampled 5 ms) | 4,900,244 KB | 1,005,200 KB | -3,895,044 KB |
| min `ulimit -v`, `abort_test` | 4,743,820 KB | 848,784 KB | -3,895,036 KB |
| max RSS | 183,356 KB | 183,356 KB | unchanged |
| max RSS, `abort_test` (3 runs) | 110,756-114,832 KB | 110,864-112,740 KB | unchanged |

Per arena, the bytes actually returned:

```
ir         1,073,741,824 ->   41,943,040   saved 1,031,798,784
lit_addr   1,073,741,824 ->    3,200,000   saved 1,070,541,824
qir_mod    1,073,741,824 ->   32,000,000   saved 1,041,741,824
ir_unsafe     26,847,641 ->    1,052,672   saved    25,794,969
toks         512,000,000 ->   96,000,000   saved   416,000,000
code         536,870,912 ->  134,217,728   saved   402,653,184
TOTAL      4,296,944,025 ->  308,413,440   saved 3,988,530,585  (-92.8%)
```

**Cap recommendation: `COMPILER_MEM_MB` 6144 → 1536 (1,572,864 KB).** That is a
**56% margin** over the measured 1,006,640 KB worst case, and it makes the
compiler's ceiling *the same number* as the compiled-binary ceiling
(`MEM_LIMIT_MB`, clamped at 1536) — one number instead of two, and the compiler
no longer needs headroom that the programs it produces do not. The reclaim is
enforced by a new gate row that forces exactly this cap:

```
Stage 1.6n va-reclaim: the compiler SELF-COMPILES under a 1,572,864 KB
address-space cap and writes a binary.
```

`scripts/qcrun.sh` itself is outside this unit's pathspec; the owner of that file
should set `COMPILER_MEM_MB=1536`. Until then the reclaim is still true, it is
just not enforced by the shipped wrapper — the gate row is what enforces it.

## 5. Red-first evidence (raw rc, both directions)

The assertion is the row above, run with each binary:

| | 0.0.258 golden | 0.0.259 reclaim |
|---|---|---|
| self-compile under `ulimit -v 1572864` | **rc=1, binary MISSING**, no stderr text | **rc=0, 2,290,040-byte binary** |

Note the shape: the old failure is *silent* (no diagnostic on stderr) as well as
fatal, and 0.0.257 recorded the same class exiting **0** under a 6,144 MB cap. A
row that read the exit status alone could not see it, which is why the row asserts
**exit 0 AND a >1,000,000-byte artifact**.

## 6. Byte-identity, with the mechanical cross-check

All 249 `EXPECTED.tsv` rows compiled with both compilers (`-O`) and `cmp`'d:

```
baseline_rows=249 new_rows=249
identical=249  differing=0  compile_fail_or_missing=0
```

The instruction-count counterpart (`scripts/bench_instr.sh`, 39 benchmark rows,
load 10.2 before / 10.7 after):

```
identical_rows=39  changed_rows=0      -> 0 shrank, 0 grew
```

For a codegen-inert change the count-identical set must be the whole set, and it
is: every row is byte-identical, so no row's instruction count can move. That is
the consistent, and the degenerate, answer.

## 7. Behaviour, fixpoint, release

| check | result |
|---|---|
| `-O` vs no-`O` on the tree | both `1e1edbe91f06e645483e8f965409ff61` — **`-O` remains byte-inert** |
| 4-generation fixpoint | `1e1edbe9 x4`, distinct(g2,g3,g4) == 1 |
| byte-identity, 249 rows | identical 249, differing 0, compile-fail 0 |
| gate `run_tests.sh` | see the version's commit message / `WIP.md` |

## 8. Growable arenas: priced, and why this version does not use them

Right-sizing an arena is a *bound*, and every bound here is a capability limit: a
single function with >1,048,576 IR records, a `code` section over 128 MB, or a set
of imported caches totalling >800,000 IR records will now be refused (fail-closed,
named) where 0.0.258 would have compiled it. All three are 5-56x beyond the
largest input this project has ever compiled, but they are real limits and the
honest answer for an *accumulating* arena is to make it grow.

The route exists: `mremap(old, oldsz, newsz, MREMAP_MAYMOVE)` is one raw syscall
(25 on x86-64, `rax`=25 / `rdi`=old / `rsi`=oldsz / `rdx`=newsz / `r10`=1 / `r8`=0),
the compiler already emits raw syscalls (`sysc()` in `emitter.quanta`), and it
grows VA only as needed. Costed: a `grow_arena(ptr, old, new)` helper (~15 lines),
a growth check at **each** appender (`iremit`, `stok`, `qobj`'s appender, the
`eb`/`ei`/`eq` code emitters — 4 sites), and the caps become soft. Price: one
lever's worth of work, and it replaces a *static* guarantee with a *dynamic* one
for four arenas at once — i.e. it is exactly the shape of change that should not
be bundled with a reclaim whose whole claim is "no emitted instruction changed".
Recommended as its own version if the measured 5-56x margins ever come under
pressure; **not needed today, and not done here.**

## 9. What this version does NOT do

* It does not touch `scripts/qcrun.sh` (outside this unit's pathspec). The
  recommendation in §4 is unimplemented there; the gate row enforces it instead.
* It does not touch `impbufs` or `data` (§1).
* It does not make any arena growable (§8).
* F4 (xmm-resident FP) and the `xor;setcc;movzbq;test → cmp;jcc` fusion are
  **not** in this version. The nine author's-row measurements that step 4 needs
  are taken and reported, unchanged from 0.0.258, because neither lever landed;
  see `WIP.md` §"not reached".
* The `qc SRC <unwritable>` silent-success leftover IS fixed, in **this**
  version — §11.

## 10. Co-landing: this reclaim shares 0.0.259 with the ATOMICS lever

**Measured environment fact, reported because it changes how this version must be
read.** A **concurrent sibling unit** was editing `compiler/0.0.259/src/x86/`
while this reclaim was being built, and its edits are present in that tree:
`at_isatomic`/`at_ord`/`at_emit` in `features.quanta`/`emitter.quanta`, the
`&GLOBAL` address fix in `parse.quanta`, `lib/std/atomic.quanta`, and five new
`test_suites/codes/atomic_*.quanta` rows. The tree therefore carries **two
levers**, and the reclaim's byte-identity claim must be qualified accordingly:

| measurement | reclaim alone (pristine reconstruction) | 0.0.259 as it stands (reclaim + atomics) |
|---|---|---|
| byte-identity vs 0.0.258, 249 rows | **identical 249, differing 0** | identical 248, **differing 1** |
| which rows differ | none | `lfm2_threaded_pool_test.quanta` — the one row that uses atomics |
| instruction counts, 39 rows | identical 39, changed 0 | not re-taken |
| self-compile under `ulimit -v 1572864` | rc=0, 2,290,040 B | **rc=0, 2,294,040 B** |
| VmPeak, self-compile | 1,005,200 KB | 1,005,032 KB |

The separation is clean and is the useful result: **the reclaim is byte-inert on
all 249 rows, and the single differing row is exactly the row that exercises the
other lever.** Neither lever is credited with the other's delta.

The reclaim was reconstructed deterministically from pristine 0.0.258 by
`/tmp/g9/mine/apply_reclaim.py` (the six hunks are in §1/§4 of this document and
the source comments), and that reconstruction reproduces
`1e1edbe91f06e645483e8f965409ff61` — so the reclaim's own numbers above stand on a
tree containing nothing else. Attribution for the two levers should follow that
split.

## 11. 0.0.260's own lever: the two discarded-return writer fixes

`write_elf` (`elf.quanta`) and `p5_elf_obj` (`objfmt.quanta`) both ended with the
same two lines, and both **discarded both return values**:

```
let ofd = file_open(outp, 577, 493)
if ofd >= 0 { file_write(ofd, elfb, elf_total); file_close(ofd) }
```

If the open failed, `ofd` was negative, the guarded body was skipped, and the
writer returned NORMALLY. **`qc SRC <unwritable>` therefore exited 0 having
written nothing.** This is the same class 0.0.257 opened one layer up (the
`--emit-qobj` write, whose return `entry.quanta` discarded), one layer down, and
still open — and it is the mechanism that makes "an oversized alloc died
silently (exit 0, no binary)" mistakable for success.

Measured, three independent unwritable shapes, on **0.0.258 and 0.0.259 both**:

| invocation | 0.0.258 | 0.0.259 | 0.0.260 |
|---|---|---|---|
| `qc SRC <dir chmod 555>/out.bin` | **rc=0, no file, nothing on stderr** | **rc=0** | rc=1, `qc: error: cannot open the output file for writing` |
| `qc --emit-obj SRC <dir chmod 555>/out.o` | **rc=0, no file** | **rc=0** | rc=1, same diagnostic |
| `qc SRC <missing-parent>/out.bin` | **rc=0, no file** | **rc=0** | rc=1, same diagnostic |

The fix, in both writers: name the open failure and `exit(1)`; then **verify the
byte count** (`file_write` returns the write syscall's result) so a short write —
a full disk — is not the same silent success. The `--emit-obj` path needed its own
fix because it does **not** go through `write_elf` at all: `entry.quanta` calls
`p5_elf_obj(out_p)` and exits, so patching one writer leaves half the defect. That
is why the red-first row covers both output modes.

Red-first row: three new cases in `test_suites/scripts/output_path_guard_test.sh`
(the stage the gate already runs as `output-path`), asserting **non-zero exit AND
no artifact AND a named diagnostic** — a row that read the exit status alone could
not see this defect.

```
0.0.258 / 0.0.259   9 PASS, 3 FAIL  -> OUTPUT-PATH GUARD: FAIL
0.0.260            12 PASS, 0 FAIL  -> OUTPUT-PATH GUARD: PASS
```

The rest of that stage (the `qc SRC SRC` self-overwrite refusals) is untouched and
stays green on all three versions, which is the control that the new cases are not
passing for an unrelated reason.

Byte-identity: these fixes are on the failure path only. 0.0.260 vs 0.0.258 over
the 249 rows gives **248 identical / 1 differing**, and the single differing row is
`lfm2_threaded_pool_test.quanta` — inherited from the atomics lever in 0.0.260's
base, **not** from this fix. See §10.
