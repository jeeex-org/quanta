# G5 follow-up — qobj gate found a real bug my matrix missed

**Status: RESOLVED. The bug is fixed (101bbc00) and the gate is wired into the
suite as a blocking stage (02c629f2). Full gate 14 GREEN / 0 RED.**

## The gap in my own verification

`scripts/g5_matrix_full.sh` (gitignored) checks cache-only builds by comparing
**stdout**. `test_suites/scripts/qobj_gate.sh` checks the process **exit code**.
For a program that returns its result instead of printing it, those disagree — and
the matrix passed while the binary segfaulted with rc=139.

The matrix is the weaker test and I treated it as sufficient. It is not.

## The defect (measured, not inferred)

Fixture: three modules, `main` imports `agg`, `agg` imports `inc` and `dbl`.

```
fn inc(x) { return x + 1 }        # pure arithmetic
fn dbl(x) { return x * 2 }        # pure arithmetic
import std/inc
import std/dbl
fn agg(x) { return dbl(inc(x)) - 1 }
```

`--emit-qobj` on `agg.quanta` produces a cache whose function table is:

```
agg   ir_n=9  CALLS
inc   ir_n=5  CALLS   <-- WRONG: inc makes no calls
dbl   ir_n=5  plain
```

`inc` carries `agg`'s `IR_CALL` records. Consuming that cache yields a binary that
segfaults.

Instrumenting the writer shows the state it is given:

```
fnc=3
  fn0 (agg)  fn_ir_start=0  fn_ir_count=9
  fn1 (inc)  fn_ir_start=0  fn_ir_count=5     <-- same start as fn0
  fn2 (dbl)  fn_ir_start=5  fn_ir_count=5
```

`fn_ir_start` **repeats**, so `agg`'s slice `[0,9)` and `inc`'s slice `[0,5)`
overlap. `qobj_write` serialises each function from `qir[fn_ir_start[i]]` with
that function's own count, so `inc` is written from `agg`'s records.

Instrumenting the compile loop shows why:

```
fi=0  btok=5  is_cache=0  ir_count=0    <- agg, a real source function
fi=1  btok=1  is_cache=1  ir_count=5    <- inc, registered from a sibling CACHE
fi=2  btok=1  is_cache=1  ir_count=5    <- dbl, likewise
```

`inc` and `dbl` were satisfied from their own existing `.qobj` files, so they took
the **cached** compile path: `sfn()` was never called for them, so
`fn_ir_start[1]` was never written this run — it still held 0 from that import,
while `fn_ir_count[1]=5` was a live value. The writer paired them.

## Why the obvious fixes fail

- **Gate `qobj_import_pending()` on `emit_qobj`.** Breaks normal builds: a
  *program* run with `--emit-qobj` still needs imports. `rc=4` on a plain
  two-import source build.
- **Gate the cache staging in `expand_includes` / `imp_load`.** Then the imports
  are not textually inlined into `src` either, and the module loses its imported
  functions entirely (cache with 1 function instead of 3).
- **Clear `qimp_is_cache` after import.** Cached functions have no source body
  token, so re-parsing them reads the wrong thing; every function ends up with
  `agg`'s 9 records.
- **Assign the slice from `qir_len` at post-parse `sfn()`.** Correct in itself,
  but it does not help: the cached functions never reach that branch, so their
  start is still never written. Verified — identical output.
- **Emit only functions recorded this run (`fn_ir_recorded`).** Produces a
  correct, self-consistent 1-function cache, but the module then genuinely lacks
  `inc`/`dbl`, and a consumer fails with rc=4. That is the real requirement
  stated plainly: **a module cache must be self-contained, so `--emit-qobj` has
  to compile the module's imports from source and record them.**

## The fix that is actually needed

During `--emit-qobj`, imports must be resolved from **source only** — never from
an existing `.qobj` — while still being textually inlined into `src` so they are
compiled and recorded as part of this module. The staging gates I tried removed
the inlining along with the cache lookup; the change has to suppress only the
cache lookup, not the source expansion, and it has to apply to a module build
without disabling cache import for ordinary program builds.

## What is verified at HEAD

- `scripts/g5_verify.sh`: 7/7 — correct cache content, correct cache-only result,
  controls intact
- `test_suites/scripts/qobj_gate.sh`: 10/10, and a blocking stage in
  `run_tests.sh`. Confirmed it has teeth: **8/10 with exit 1** against the
  pre-fix binary, **10/10 with exit 0** after the fix
- full gate **14 GREEN / 0 RED** against the installed binary `f8cb669a`
- compiler self-build byte-identical across two runs

## Remaining

- **G4** (stale-cache detection) and **G6** (self-compile from real caches) are
  untouched and now unblocked.
- The functional gate still runs 869 of 18,569 tests. The qobj stage adds real
  coverage, but that ratio is a separate question and is unchanged.
