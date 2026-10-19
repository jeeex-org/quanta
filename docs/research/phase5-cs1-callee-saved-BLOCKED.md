# CS1 (callee-saved ELISION) — implemented and measured, BLOCKED by the qobj cache path

**No version was promoted.** The lever was built, measured, and reverted. This
document is the record: what it does, every number measured, and the exact
blocker, so the next unit can finish it. `VERSION` stays **0.0.256**; the tests,
probe, gate stage and tree added during the attempt were all reverted.

Working from `173e3386` (0.0.256 golden `21c868f4`, gate 248/248, verify-release
14/14). All numbers below are MEASURED in that session on this box.

---

## 1. The defect

The prologue pushed all five ABI callee-saved registers (RBX, R12-R15) and every
epilogue popped all five, whether the function wrote them or not
(`codegen.quanta:1917` prologue; `:3285` epilogue). In `is_odd` — the hot function
of the author's row #1, `mutual_recursion` — **none** of the five is written.

```
0.0.256 is_odd, per call       0.0.257 CS1 is_odd, per call
push %rbp                      push %rbp
mov  %rsp,%rbp                 mov  %rsp,%rbp
push %rbx                      sub  $0x478,%rsp      <-- 0x450 + 8*5
push %r12
push %r13
push %r14
push %r15
sub  $0x450,%rsp
...
pop  %r15 ... pop %rbx         (no pops)
pop  %rbp                      pop  %rbp
ret                            ret
```

10 of ~64 emitted instructions per call were pure overhead. A binary-patch
experiment (nop the unused push/pop pairs, output byte-identical) had already
measured best-of-7 at 0.51 s -> 0.40 s (~22 %).

## 2. The implementation (as built)

One lever, one version. Changes were confined to `codegen.quanta`,
`emitter.quanta` and (for the reclaim, see §5) `globals.quanta`.

* **Tracking** — `cs_mask`, a 5-bit scalar. `cs_mark(pr)` is called from every
  allocator entry point that hands out a destination (`aset`, `aremap`, `afree`,
  `afree_x`, `apick_free`, `ascratch`, `aevict_nop`): for the ops codegen emits a
  normal path for, that is the ONLY way a callee-saved register enters use.
* **Fail-closed op guard** — `cs_risky(op)` marks the six ops whose emitted body
  writes a callee-saved register by hand with no allocator involvement:
  `IR_ARRNEW`, `IR_APUSH`, `IR_CLOSURE`, `IR_FREE`, `IR_THROW`, `IR_ASM`.
  Established by grepping the emitter for the five register numbers and by
  decoding every raw `eb(72/73); eb(...)` ModRM in the emit loop. A builtin
  `IR_CALL` (emit_bltn succeeded) also sets `cs_hard`, because builtins are
  emitted inline and some (str_split) deliberately clobber RBX and rely on the
  caller's prologue.
* **Removal, not padding** — the bytes of the unused pushes (prologue) and pops
  (every epilogue, recorded per `IR_RET`) are DELETED and the buffer is compacted
  (`cs_finish`). The frame's rsp adjustment grows by 8 per elided register
  (`frame_size + 8*need`) so the body's rsp is byte-for-byte where it was; every
  epilogue's `add rsp,fsize` cancels it. Compact-ing shifts every offset after a
  removed range, so the three tables that can hold an absolute code offset for the
  function are fixed up: its own `patches` entries, its `lblmap` label positions,
  its `gpatches` data patches. Function-start offsets need NO fixup: removal
  begins at `func_start+4` (after `push rbp; mov rsp,rbp`), and later functions
  read `codelen` after this one returns.
* **Scalars, not arenas** — see §5: the compiler's total mmap sits ~15 KB under
  qrun.sh's 6144 MB COMPILER ceiling, so the bookkeeping is 1-16-entry scalars.

## 3. Measured effect (source path) — the lever WORKS here

Instrument of record `scripts/bench_instr.sh` (load-free emitted bytes) and
`objdump` over `--emit-obj`.

| metric | 0.0.256 | CS1 | delta |
|---|---|---|---|
| `is_odd` emitted instructions (`--fn is_odd`, whole function incl. 3 epilogues) | **64** | **44** | **-20** |
| `is_odd` frame | 1104 | 1144 | +40 (=8*5) |
| `mutual_recursion` bench output vs C twin | 40000000 | 40000000 | MATCH |

248-row instruction accounting (`--emit-obj` + objdump, instructions in the whole
object, 0.0.256 vs CS1):

| check | result |
|---|---|
| rows whose instruction count SHRANK | **246** |
| rows whose instruction count GREW | **0** |
| rows whose instruction count is identical | **2** |
| total emitted instructions | 678491 -> 657638 (**-3.07 %**) |
| byte-identity (same 248 rows) | identical **2**, differing **246**, compile-fail 0 |

The 2 count-identical rows are exactly the 2 byte-identical rows
(`mmap1.quanta`, `test_many_globals.quanta`) — the mechanical cross-check holds.
Both rows' functions genuinely WRITE RBX (verified in the emitted object:
`mov %rdi,%rbx`), so correctly keeping every save is the right result for them,
not a null result.

Behavioural oracles on the source path — all green:

| check | result |
|---|---|
| gate (`run_tests.sh`, 249 rows after registering the probe) | **249/249 pass, 0 fail, 0 compile-fail** (every guard stage GREEN) |
| `bench.sh --runs 3` | 38/38 compiled, **0 MISMATCH**, 0 folded twins |
| 4-generation self-host fixpoint | `21c868f4 -> 73818f6a -> eca65623 -> eca65623 -> eca65623`, distinct(g2,g3,g4)==1 |
| `differential` / `fuzz` / `valgrind` (inside the gate) | GREEN |
| `is_odd`/`is_even`/`heavy_int`/`float`/`arith` vs C twins | MATCH |

Red-first row (registered in the same commit as its probe during the attempt):
`csave-guard` in `test_suites/scripts/run_tests.sh`, reading `probe_fn`'s emitted
instruction count out of `--emit-obj` for `test_suites/codes/csave_probe.quanta`.

| compiler | probe_fn | verdict |
|---|---|---|
| 0.0.256 golden | **53** | **FAIL** (>40) |
| CS1 | **33** | PASS |

Wal-clock on the row: not re-measured under a clean pin in this session; the
binary-patch experiment's 0.51 s -> 0.40 s remains the reference.

## 4. THE BLOCKER — the qobj module-cache path

`scripts/g6_selfcache.sh` (cache the whole 327-function compiler, delete every
`.quanta`, rebuild from the cache alone) FAILS with CS1 enabled:

```
  PASS compiler cached (=1)
  PASS cache holds >300 functions (=1)
  PASS all sources removed (=0)
  Segmentation fault (core dumped)  "$QC" use.quanta out
  FAIL cache-only build produced nothing
  FAIL cached lookup said: <nothing>
  G6: 3/5          (an earlier instrumented build instead returned 80, want 7)
```

It enters through the GATE: `qobj_gate.sh` G6 -> `QOBJ: 16/17 GREEN`, gate exit 1.
**Never promote a red gate**, so nothing was promoted.

Measured isolation, in order:

| variant | G6 |
|---|---|
| 0.0.256 golden | **5/5** (verified 4/4 runs) |
| CS1 (elision active everywhere) | FAIL — segfault, and once "want 7 got 80" |
| CS1 with `if 1==1 { return 0 }` at the top of `cs_finish` (elision DISABLED, every other byte of the lever still present) | **5/5** — so the elision itself is the trigger, not `cs_mark`/`cs_risky`/the recording |
| CS1 with cache-IMPORTED functions excluded (`is_cache==1 -> cs_hard`) | still FAIL — so it is not a cached function's own elision |
| CS1 "paranoid" tracking: `cs_mark` added to `rw`, `ri`, `ri64`, `rneg`, `rnot`, `rshl`, `rshr`, `rsar_imm`, `rand_imm`, `raddi`, `rsubi`, `rinc`, `rdec`, `rimul1`, `rbp`, `xpop`, `rzero` (over-approximating every operand of every low-level emitter) | still FAIL — so it is NOT a missed usage mark; it is an **offset-accounting interaction of the compacting shift with that path** |
| CS1 + a lazy `elision_ok` decision taken on the first `ci_func` call (exclude any build that consumes/writes a cache) | still FAIL — the exclusion did not fire where needed |

**The root cause is OPEN.** The measured facts that constrain it: the cache write
itself is fine (`--emit-qobj main.quanta m.qobj` -> rc=0 and a byte-size identical
to 0.0.256's cache, 6400300); the G6 cache-only build's only source-path function
is a trivial `fn main() { return 7 }`, which compiles and runs correctly on its
own; the crash therefore needs the cache-consumption build as a whole.

## 5. A second, independent blocker: the VA reclaim the lever needed

The compiler's total mmap sat only **15 KB** below `scripts/qcrun.sh`'s 6144 MB
COMPILER ceiling:

| compiler | MR (measured by bisecting `ulimit -v`, compiling `benchmark_file_io`) |
|---|---|
| 0.0.256 golden | 6,291,441 KB (= 6143.99 MB), cap 6,291,456 KB |
| CS1 v1, with six small (200 KB) arenas for the bookkeeping | 6,291,641 KB -> **FAILS the cap**: `benchmark_file_io` compiled with exit 1 and no binary under `qcrun.sh`, while an 8 GB `ulimit` compiled it fine |
| CS1 v2, bookkeeping as scalars (zero new arenas) | 6,291,454 KB -> fits (2 KB margin — inside environment noise) |

So a reclaim was required. `ir_unsafe` (`globals.quanta:182`) is a **byte** table,
indexed by IR index (`r8(ir_unsafe+ii)` at every use), but was allocated as
`mmap(1610612736)` — the comment justified that as "IR_CAP (40000000) = 1.6GB",
which used the wrong IR_CAP (the real one is 26843545, `helpers.quanta:35`) and
sized a byte table at ~60 bytes per record. Reclaiming it to `mmap(IR_CAP+4096)`
(~25.6 MB):

| check | result |
|---|---|
| emitted-code inertness: 248/248 gate rows compiled by `0.0.256` vs by `0.0.256 + reclaim`, byte-compared | **identical 248, differing 0, compile-fail 0** |
| new MR | **4,718,581 KB (4607 MB)** — 1.5 GB of margin under the cap |
| `benchmark_file_io` under the cap, 20 runs | 0 failures |
| self-host fixpoint (reclaim only) | `21c868f4 -> 0cc917d1 -> f40bf339 -> f40bf339 -> f40bf339` |
| `verify-release.sh 0.0.257 0.0.256` (reclaim only) | 11 PASS, 0 FAIL (incl. `<NEXT>` src/bin lockstep and the self-host fixed point on f40bf339) |
| gate (reclaim only) | 248/248 rows, 0 fail; only `qobj G6` red |

**But the reclaim ALSO breaks G6** (4/4 runs) — and it breaks it while caching
**its own** source, i.e. G6 passes when the cached source is 0.0.256's and fails
when the cached source is the reclaimed compiler's. Since the reclaim changes only
an arena SIZE, it moves every later arena in the mmap layout; the cache path is
therefore sensitive to that layout, which points at a **pre-existing latent
out-of-bounds / capacity defect on the qobj path** that the layout change exposes.
So the reclaim could not be promoted either, and `VERSION` stayed 0.0.256.

## 6. What the next unit should do

1. Find the qobj/cache offset-accounting interaction. The fastest lever found
   here: G6 fails iff the elision runs in the cache-consuming build, and a build
   that consumes ANY cache can be detected (`qimp_is_cache[fi]`); the lazy
   detection attempted here did not fire, so check WHEN `qimp_is_cache` and `fnc`
   are actually populated relative to the first `ci_func` call (entry.quanta's
   compile loop), then exclude that build and re-test.
2. Separately, find the latent qobj OOB the reclaim exposes — it is worth its own
   version regardless of the elision, because 0.0.256's 15 KB of headroom means
   ANY codegen change can silently fail to compile `benchmark_file_io` under the
   cap.
3. Only then re-land CS1, with the `csave-guard` red-first row (probe: 53 FAIL ->
   33 PASS) and the accounting table of §3.
