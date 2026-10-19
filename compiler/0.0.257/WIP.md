# 0.0.257 — WIP · **LEVER: the `ir_unsafe` ADDRESS-SPACE RECLAIM (1.57 GB) + located cache-path diagnostics**

One lever, one version. Golden `21c868f418797c86d7db68728ed01917` (0.0.256,
frozen, verified to rebuild bit-for-bit). Full write-up with every measurement:
**`docs/research/phase5-irunsafe-reclaim-0.0.257.md`**.

This version is **CODEGEN-INERT**: it changes no compiled program's bytes. It
reclaims 1.57 GB of address space and makes two cache-path failures attributable
instead of silent. It carries **no code-generation improvement** and is not a
parity row; it is the fix for a pre-existing fragility that blocked every
codegen change from being *gated* safely.

Four files changed, everything else the 0.0.256 snapshot copied verbatim:

| file | change |
|---|---|
| `src/x86/globals.quanta` | `ir_unsafe` was `mmap(1610612736)` — 1.6 GB for a **BYTE**-per-IR-record table, sized against the wrong `IR_CAP` (40000000; the real one is 26843545 in `helpers.quanta:35`), i.e. **40.3 bytes per record where 1 byte is used**. Now `mmap(IR_CAP+4096)` = 25.6 MB. |
| `src/x86/qobj_write.quanta` | after `file_close`, the header is read back and the write is VERIFIED (`qobj_write` returns 0 when it did not land) |
| `src/x86/entry.quanta` | `--emit-qobj` no longer discards `qobj_write`'s result and no longer runs `exit(0)` unconditionally; a failed cache write prints a NAMED diagnostic and exits 1 |
| `src/x86/objfmt.quanta` | `qobj_import` refuses a TRUNCATED cache by name instead of consuming a partial module |

```
0.0.256 golden  md5 21c868f418797c86d7db68728ed01917   (frozen baseline, untouched)
0.0.257 g1      md5 f047748f7eddb3991b7b5306656ceae4
0.0.257 g2      md5 f047748f7eddb3991b7b5306656ceae4   (COMMITTED GOLDEN = fixpoint)
0.0.257 g3      md5 f047748f7eddb3991b7b5306656ceae4
0.0.257 g4      md5 f047748f7eddb3991b7b5306656ceae4   (distinct(g2,g3,g4) == 1)
```

## Why the bytes per record matter

`ir_unsafe` is indexed by IR index and touched as `r8(ir_unsafe+ii)` at every
use — it is one byte per record. At `IR_CAP` 26843545 it needs 25.6 MB. It was
allocated 1,610,612,736 bytes: **1.57 GB of pure address-space waste**, on a
compiler whose total mmap therefore sat **13 KB** under `scripts/qcrun.sh`'s
`COMPILER_MEM_MB=6144` ceiling (6,291,456 KB):

| compiler | need, `benchmark_file_io` under a bisected `ulimit -v` | margin under the 6,291,456 KB cap |
|---|---|---|
| 0.0.256 | 6,291,443 KB | **13 KB** |
| 0.0.257 | 4,744,797 KB | **1,546,659 KB (1.47 GB)** |

## Red-first: the new gate stage is RED on 0.0.256, GREEN on 0.0.257

New Stage **1.6l `cache-precond-guard`** in `test_suites/scripts/run_tests.sh`
(+ a summary line, + folded into `FUNCTIONAL_RC`), three raw-rc assertions:

| assertion | 0.0.256 (RED) | 0.0.257 (GREEN) |
|---|---|---|
| `cache-cap` — `--emit-qobj` under a 6,291,456 KB cap must WRITE a cache | rc=1, **0 bytes** | rc=0, **37534 bytes** |
| `cache-failloud` — an unwritable cache path must exit NON-ZERO | exits **0** with no cache: a silent success | exits **1**, named diagnostic |
| `cache-trunc` — a 200-byte cache must be REFUSED, by name | rc=0, **builds a binary from the partial module** | rc=1, `qc: error: module cache is TRUNCATED: m.qobj` |

The RED column was captured with the stage run against the 0.0.256 binary
(`QC` pinned in the environment; log `gate_RED_on_0.0.256.log`), the GREEN column
with the 0.0.257 binary. Both runs otherwise reported **248/248 rows pass, 0
fail** and **QOBJ 17/17 GREEN**.

## Verification, all measured

| check | result |
|---|---|
| byte-identity, 248 gate rows, 0.0.256 vs 0.0.257 (`--emit-obj`+cmp) | **identical 248, differing 0, compile-fail 0** |
| gate (`run_tests.sh`, 248 rows) | **248/248 pass, 0 fail, 0 compile-fail**; every stage GREEN incl. `QOBJ 17/17` and `cache-precond-guard` |
| `bench.sh --runs 3` | **38/38 rows compiled, 0 MISMATCH, 0 folded twins** ("every row compiled and every C twin kept its loop"); 12 of 38 at ratio 1.00x |
| 4-generation self-host fixpoint | `21c868f4 -> f047748f -> f047748f -> f047748f`, distinct(g2,g3,g4)==1 |
| `verify-release.sh 0.0.257 0.0.256` | **14/14 PASS** |
| `--emit-qobj` need under the cap, vs 0.0.256 | 6,291,456 KB: 0.0.256 rc=1 no file / 0.0.257 rc=0 37534 bytes |

## What this version does NOT do

* It does not change a single emitted instruction. **There is no parity delta to
  report** — the campaign's row-by-row work (callee-saved elision, comparison/jcc
  fusion, xmm-resident FP) is unblocked by this version but is not in it.
* It does not name a *failed mmap* at the point of failure: the guard at
  `emitter.quanta:2744` exits 1 with no message, so a shortfall is loud in the
  exit status but not in attribution. Naming it means emitting code inside the
  `mmap` builtin, which is a **codegen change** and would break this version's
  byte-identity (rows that call `mmap` would grow). Deliberately left for its own
  version.
* It does not fix the same silent-success on the **executable** output path:
  `qc SRC OUT` to an unwritable directory exits 0 with no binary on BOTH 0.0.256
  and 0.0.257 (measured). Same class as `cache-failloud`; separate change.
