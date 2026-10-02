# 0.0.222 — WIP

Promoted from `0.0.221` at commit `658f9859`, whose state was verified before the
copy:

    compiler/0.0.221/bin/x86/qc
    size=2929280
    md5=46e64c2ec6c47abc28fac2471572039c
    self-hosted 3 generations byte-identical
    suite PASS=125 CFAIL=0 RFAIL=0 of 125
    independent audit scripts/audit/run_gguf_tests.py: PASS=125 FAIL=0

`0.0.221` is a good state and stays as the stable fallback. All new work happens
here; `0.0.221/src` is never modified.

(The WIP.md copied from the previous tree describes 0.0.221, which is correct as
history but wrong as a header. Replaced, not appended to.)

## Current state (measured, not asserted)

    compiler/VERSION                 0.0.222
    gate                             see below -- not yet run for this tree
    fallback compiler/0.0.221/bin/x86/qc
    md5=46e64c2ec6c47abc28fac2471572039c
    self-hosted 3 generations byte-identical

## Done in 0.0.221 (inherited, for reference)

- `expf` in lib/std/math.quanta; three overflow/underflow defects fixed; 278 of 278
  finite audit cases within 1e-12 relative, median 3.8e-15.
- `pow` renamed `ipow` in std/math: a user function SHADOWS a same-named builtin
  in every importing scope.
- Float literals with >17 significant digits were silently wrong, ~10x per extra
  digit, because the lexer froze the mantissa while still counting fraction
  digits. Now within 2 ULP.
- 26 broken GGUF reader tests replaced by one asserting test (16/16 mutations
  detected). They all skipped a string array as `alen * 4`; the format is
  `u32 elem_type, u64 count, (u64 len, bytes)*` -- length-prefixed.
- Six float kernels in lib/std/gguf did INTEGER arithmetic on float buffers:
  matvec, softmax_arr, vec_add, vec_mul, rms_norm, swiglu all read with mem_load()
  and no f64of(). rms_norm also divided by sqrt(1+mean) rather than sqrt(mean),
  swiglu used 1/(1+2^-x), and softmax_arr computed 1+e^x, which sums to n+1.
  RFAIL reached 0 here.
- String parameters print as text for all three spellings (str/string/String).
  Three causes: `w8` where `w64` was required (nv() initialises cells to -1);
  `: string` lexes as TT_STRING, which funcscan's type-annotation guard excluded;
  and `String` missed a case-sensitive compare.
- std/math's abs/min/max no longer shadow the f64 builtins. Importing std/math
  turned `abs(-5.0) / 2.0` from 2.5 into 9223372036854.775808. Integer forms are
  iabs/imin/imax; float min/max needed adding as fmin/fmax because the untyped
  `fn min` was the only implementation in the language.
- pow honoured an integer exponent, and then six more builtins with the same
  omission: sqrt, log, sin, cos, tan, abs.

## OPEN DEFECTS

### Nested indexing into a string-array element CRASHES THE COMPILER

    let p = ["one", "two", "three"]
    println(p[1][0])        // SIGILL while COMPILING, before any run

This is not a miscompilation -- the compiler itself dies with SIGILL on this
source. `p[1]` alone works (it yields the element's string pointer), so the crash
is specific to indexing a second time into an IR_IDX result.

The emitter already has the machinery for it: `vreg_str_arr` is set on a string
array's result vreg, and the IR_IDX array branch reads it to tag the RESULT as a
byte-stride string, which is what would make the second index stride by 1. That
tagging is at codegen.quanta:1580. So the intent is implemented and something in
the path still faults -- worth an actual diagnosis before guessing.

Not asserted in tests/test_indexing_bounds.quanta on purpose: a compile-time
SIGILL would take the whole suite down and hide every other check in the file.

### A slice whose HIGH bound exceeds the length traps instead of clamping

    let b = [10, 20, 30, 40, 50]
    b[3:5]   -> len 2   correct
    b[3:3]   -> len 0   correct
    b[3:99]  -> SIGILL

method.quanta's slice lowering clamps only the LOW side:

    nraw = hi - lo
    neg  = nraw < 0
    n    = neg ? 0 : nraw        // clamps nraw < 0 to an empty slice
    dst  = TALLOC(n)
    loop idx in 0..n: dst[idx] = base[lo+idx]

So `hi` is never bounded by the array length, and when `hi > len` the loop walks
past the end and `idx_trap_emit` fires. Python, Rust and Go all clamp the high
bound; this does not. Whether that is the right choice is a design question --
but it is currently silent, since the comment at method.quanta describes the
clamp as if it covered both ends.

### CORRECTION: array indexing IS bounds-checked


## Verified pitfalls for this tree

- `mem_load` always reads 8 bytes. Reading a u32 field into a 4-byte buffer
  overreads the allocation; read 8 wide and mask.
- `mem_store` takes a VALUE, not a bit pattern. `mem_store(p, 4607182418800017408)`
  stores the float 4.6e18, and a round-trip returns that same wrong value, so a
  store/load test passes while asserting nothing.
- An UNTYPED `fn` returning `f64of(...)` returns the integer bit pattern. Needs an
  explicit `-> f64`.
- `mem_alloc` inside a loop body is unsafe -- the next iteration clobbers it.
  Allocate up front, as lib/std/gguf.quanta does.
- `lseek` returns the resulting ABSOLUTE offset, not a 0-on-success status.
- A user `fn` shadows a same-named builtin in every importing scope.
- `print`/`println` and indexing of a string PARAMETER give a pointer / garbage;
  locals and array literals are fine. Pass flat integer arrays instead.
- x87/SSE byte encodings: the direction of `0F 7E` vs `0F 6E` is fixed by the
  opcode, not by the ModRM fields. `fld_x` is the load, `fst_x` the store.
  `66 48 0F 7E` is movq; `66 0F 7E` is movd and truncates.
- `is_float_vr` must be read BEFORE `flush_all()`, which spills live vregs and
  makes the float tag unreliable.

## Rules for anything added here

- Assert. A test that prints an expectation next to a result is not a test.
  test_full_final printed `Matvec: 0, 0 (expect 17, 39)` and then `SUCCESS`.
- Compare on raw bits or a ULP tolerance, never on formatted output. Print rounds,
  so `1/3` and `0.3333333333` are indistinguishable.
- Take every expected value from the real data, not from a plausible guess. Five
  values in the GGUF tests were wrong that way, and the file was right each time.
- Prove a branch fires before debugging what it writes: set a value that is
  consumed downstream and produces a loud failure.
- Verify a new test fails on the pre-fix binary. Otherwise it is a false pass.
