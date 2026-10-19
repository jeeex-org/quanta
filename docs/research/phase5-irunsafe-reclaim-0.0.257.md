# 0.0.257 — the `ir_unsafe` address-space reclaim, and the located cache-path diagnostics

**One lever, one version. Codegen-inert: 248/248 gate rows BYTE-IDENTICAL to
0.0.256.** This is not a parity row — it changes no emitted instruction. It is
the fix for a *pre-existing* address-space fragility that made every codegen
change unsafe to gate, plus the step-0 located diagnostics for the cache path.

Baseline `173e3386` / golden `21c868f418797c86d7db68728ed01917` (0.0.256; verified
to rebuild bit-for-bit). Every number below is MEASURED on this box.

---

## 1. The defect

`globals.quanta:182` (0.0.256):

```
let ir_unsafe = mmap(1610612736)   // sized to IR_CAP (40000000) = 1.6GB
```

`ir_unsafe` is read as `r8(ir_unsafe+ii)` — **one byte per IR record**. The
comment justified 1.6 GB against `IR_CAP` 40000000, but the real `IR_CAP` is
**26843545** (`helpers.quanta:35`). So a 25.6 MB byte-table was given
1,610,612,736 bytes:

```
1,610,612,736 / 26,843,545 = 60.0 bytes per record   (comment's own basis)
1,610,612,736 - 26,847,641 = 1,583,765,095 bytes wasted  (1.57 GB)
```

The compiler's total mmap therefore sat **13 KB below its own hard ceiling**:

| compiler | need for `benchmark_file_io`, bisected `ulimit -v` | margin under `qcrun.sh`'s 6,291,456 KB (`COMPILER_MEM_MB=6144`) |
|---|---|---|
| 0.0.256 golden | **6,291,443 KB** | **13 KB** |
| 0.0.257 (reclaimed) | **4,744,797 KB** | **1,546,659 KB (1.47 GB)** |

The cache-**write** path needs slightly MORE than a plain compile, so
`--emit-qobj` failed under the cap outright:

| `--emit-qobj benchmark_file_io` under `ulimit -v 6291456` | 0.0.256 | 0.0.257 |
|---|---|---|
| exit status | 1 | 0 |
| bytes written | **0 (no file)** | 37534 |

That is the concrete way the 13 KB margin bites: a codegen change worth a few
hundred bytes of arena (or of bookkeeping) can make the compiler unable to write
a cache or compile a row at all — *silently*, with no diagnostic naming the
cause. Round 2's blocker on the callee-saved elision was a symptom of this, not
of the elision. **The causality inverts: this reclaim is the fix, not the cause.**

## 2. What changed (four files)

| file | change |
|---|---|
| `src/x86/globals.quanta` | `mmap(1610612736)` -> `mmap(26847641)` (= `IR_CAP`+4096). The only codegen-relevant change, and it is inert. |
| `src/x86/qobj_write.quanta` | `qobj_write` now VERIFIES its own output: after `file_close` it re-opens the path, reads the 48-byte header back, and returns 0 unless the magic (`0x514F424A`) and version (11) read back. Reuses the existing `hdr` buffer — **zero new address space**. |
| `src/x86/entry.quanta` | `if emit_qobj == 1 { qobj_write(out_p, srcp); exit(0) }` — the return value was **discarded** and `exit(0)` ran **unconditionally**. Now a non-1 return prints a named diagnostic and exits 1. |
| `src/x86/objfmt.quanta` | `qobj_import` refuses a TRUNCATED cache: `file_lseek(fd,0,2)` for the real size vs a header-declared lower bound, named message, exit 1. `declared` deliberately omits the ambiguous regions so it UNDER-estimates a good cache and can never trip on a valid one; the seek is restored to 48 so the sequential region reads are unaffected. |

## 3. Red-first evidence (raw rc, both directions)

New Stage **1.6l `cache-precond-guard`** in `test_suites/scripts/run_tests.sh`
(+ summary line + folded into `FUNCTIONAL_RC`). RED column = same stage run with
the 0.0.256 binary; GREEN column = 0.0.257.

| assertion | 0.0.256 | 0.0.257 |
|---|---|---|
| `cache-cap`: `--emit-qobj` under a 6,291,456 KB cap writes a cache | rc=1, 0 bytes — **FAIL** | rc=0, 37534 bytes — **PASS** |
| `cache-failloud`: an unwritable cache path exits non-zero | exits **0** with nothing written — **FAIL** | exits **1** — **PASS** |
| `cache-trunc`: a 200-byte cache is refused, by name | rc=0, **builds a binary from the partial module** — **FAIL** | rc=1, `qc: error: module cache is TRUNCATED: m.qobj` — **PASS** |

`cache-trunc` is the sharpest: on 0.0.256 a 200-byte cache is consumed and a
binary is produced — a **wrong answer instead of a diagnostic**, which is the
same shape as the cache-only build round 2 saw "return 80 where 7 was wanted".

## 4. Byte-identity, with the mechanical cross-check

`test_suites/scripts/byte_identity.sh 0.0.256 0.0.257` compiles every
`EXPECTED.tsv` row with both compilers and `cmp`s the products:

```
rows=248 identical=248 differing=0 compile-fail=0
```

For a codegen-inert change the expected signature is the degenerate one — every
row identical — and that is exactly what was measured. The cross-check that
matters here is the *instruction* counterpart: since every row is byte-identical,
the instruction counts must be identical on all 248 rows, **0 shrank, 0 grew**.
The count-identical set necessarily EQUALS the byte-identical set (all 248),
which is the consistent answer for a change that touches no emitter.

## 5. Behaviour, fixpoint, gate, release

| check | result |
|---|---|
| byte-identity, 248 rows | identical 248, differing 0, compile-fail 0 |
| gate `run_tests.sh` (248 rows) | 248/248 pass, 0 fail, 0 compile-fail; all stages GREEN incl. `QOBJ 17/17` + `cache-precond-guard`; exit 0 |
| `bench.sh --runs 3` | 38/38 rows compiled, **0 MISMATCH**, 0 folded twins; 12/38 at 1.00x |
| 4-generation fixpoint | `21c868f4 -> f047748f -> f047748f -> f047748f`, distinct(g2,g3,g4) == 1 |
| `verify-release.sh 0.0.257 0.0.256` | **14 passed, 0 failed** (incl. `<VER>` bit-for-bit rebuild, `<NEXT>` src/bin lockstep, self-host fixed point on `f047748f`) |

## 6. The one-root-cause hypothesis: REFUTED as stated

The hypothesis under test was that the callee-saved elision's G6 failure and the
`ir_unsafe` reclaim's G6 failure were ONE root cause in the cache path's offset
bookkeeping. Measured outcome:

* **The reclaim has no G6 failure.** A parameterized G6 harness (writer x
  consumer x source: 0.0.256/reclaim x 0.0.256/reclaim x pinned-0.0.217-tree /
  own-tree, g1 and g2 fixpoints) is **5/5 GREEN in every one of 12+ cells**.
  Round 2's "the reclaim also breaks G6 (4/4)" did not reproduce.
* **The elision's G6 failure did not reproduce either.** The CS1 tree rebuilt
  from round 2's own apply script (g1 md5 `1bd406dd8b03b8b8f0f2d196b9066dee`,
  byte-identical to round 2's) is **5/5 GREEN**, pinned source and own source,
  as writer and as consumer.
* **No segfault was observed in any configuration**, including elision+reclaim
  combined — which is what round 2's failing gate actually ran.
* The offset-accounting class was never demonstrated. The one measurable,
  reproducible cache-path failure is the **ceiling**: 0.0.256 itself fails
  `--emit-qobj` under `qcrun.sh`'s cap. That is a clean exit 1, not a segfault.

Honest limits on this: the gate's G6 path sets **no `ulimit -v`**, and a failed
`mmap` **cannot** segfault — the guard at `emitter.quanta:2744` is
`cmp rax,0; jge +12; mov edi,1; mov eax,60; syscall`, i.e. `exit(1)`. So the
ceiling explains the *cap* failures but not a segfault in an uncapped G6 either.
**The gate G6 segfault remains unreproduced; the failure mode that IS
reproducible and attributable is the ceiling plus the two silent-success paths
fixed here.**

## 7. Latent defects exposed, and what is left

* **Silent success on the cache path** (fixed here): `qobj_write`'s return value
  was discarded and `exit(0)` ran unconditionally. `--emit-qobj SRC /unwritable/x.qobj`
  on 0.0.256 -> **exit 0, no file, no message**. Same class, **NOT fixed**: the
  executable path. `qc SRC /unwritable/x` exits **0** with no binary on both
  0.0.256 and 0.0.257 (measured).
* **A partial module was a valid input** (fixed here): a truncated cache was
  consumed and produced a binary.
* **An unnamed `mmap` failure** (NOT fixed, deliberately): the guard at
  `emitter.quanta:2744` exits 1 without naming what failed or for how many bytes.
  Naming it means emitting code inside the `mmap` builtin, which is a codegen
  change and would break this version's byte-identity (rows that call `mmap`
  would grow). Own version.

## 8. Measurement hygiene note

An early probe of mine reported `--emit-qobj` as "rc=0 with no cache", i.e. a
silent success. That was a **measurement artifact**: `rc=$?` appeared in the same
`echo` as a `$(basename $(dirname ...))` command substitution, which had already
overwritten `$?`. With `rc=$?` as its own statement the same invocation is
`rc=1`. The real silent success is the *unwritable-output-path* case in §3(b),
which is deterministic. Any `$?` captured in a word that also contains a command
substitution is untrustworthy.
