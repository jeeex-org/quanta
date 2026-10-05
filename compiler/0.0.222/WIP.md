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

## Current state (SUPERSEDED by 0.0.223 — kept as history)

> Corrected 2026-10-05: the three claims below were FALSE at the time and are
> left visible rather than deleted, because a corrected record is worth more
> than a clean-looking one.
>
> 1. `compiler/VERSION 0.0.222` — the file said `0.0.192` and was never updated
>    across 30 promotes. Nothing read it, so it drifted silently. It has since
>    been DELETED (commit 3631dd95): root `VERSION` is the single source of
>    truth. There is no `compiler/VERSION`.
> 2. `size=2933376 / md5=1d71a016...` — stale. The real 0.0.222 binary was
>    `size=2974472 md5=650f03c6d6ce13bb6f575b5056e07d3d`.
> 3. "full suite: 129 tests, each compiled AND run individually -> all pass" —
>    false. The official gate is 817 cases and measured 813/817 with 4 compile
>    failures (the trait tests). `EXPECTED.tsv` has 813 entries.
>
> The claim that `dequant_diff.py` covers "all 256 elements of Q4_K/Q5_K/Q6_K"
> is also wrong: that harness exercises Q5_K, Q6_K, Q8_0 and F16
> (0 mismatches of 32) and does NOT cover Q4_K.

    compiler/VERSION                 0.0.192  (DELETED in 3631dd95; never updated)
    full suite: 129 tests, each compiled AND run individually -> all pass  [FALSE]
    scripts/audit/run_gguf_tests.py PASS=129 FAIL=0 COMPILE-FAIL=0
    scripts/audit/dequant_diff.py 0 mismatches of 554 (all 256 elements of
      Q4_K/Q5_K/Q6_K, all 32 of Q8_0, all 10 F16 patterns, vs the compiled C) [Q4_K NOT COVERED]
    tests/run_bounds_trap.py PASS, tests/run_string_params.py PASS
    compiler/0.0.222/bin/x86/qc
    size=2933376 [stale; real size=2974472]
    md5=1d71a0165d0f409ce8381d679f3e68fb [stale; real md5=650f03c6d6ce13bb6f575b5056e07d3d]
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
- dequant_f32() added to lib/std/gguf.quanta. 99 of the reference model's 266
  tensors are F32 -- 37% -- and it was the only dtype with no decoder. They went
  unnoticed because they are the SMALL per-layer vectors, 1/260th the size of the
  weight matrices, so a run that only ever touched the k-quants looked complete:

      token_embd_norm.weight   [2048]     x61
      ...                      [3, 2048]  x22
      ...                      [64]       x16

  F32 has no quantisation, so the decoder is a widening over the existing
  (already exact) f32_to_f64. Decoder coverage is now 266 of 266.

## OPEN DEFECTS

### No decoder for F16, Q5_K, Q8_0 or any IQ type

`std/gguf.quanta` now covers every dtype THIS model uses (F32, Q4_K, Q6_K =
266/266), but the other families are absent. `gguf_type_size` returns a byte size
for types 0..13 plus 30, and a caller can therefore size a buffer it has no way to
decode -- the same shape of defect F32 had, one step further out:

    Q8_0  (type 8)   32 values / 34 B     -- the standard KV-cache quant
    Q5_K  (type 13) 256 values / 176 B
    F16   (type 1)    1 value  / 2 B
    IQ2_XXS .. IQ4_XS (16..23)

Nothing in the reference model needs them, so this is not blocking today. It is
recorded because `gguf_type_size` succeeding where no decoder exists is the exact
trap that hid the F32 gap: a caller allocates correctly and then reads garbage.

### RESOLVED: a nested index / a non-name base CRASHED THE COMPILER

    print(m[1][0])            SIGILL while COMPILING
    print(len(m[1][0]))       SIGILL while COMPILING
    print([70,80][0])         SIGILL while COMPILING
    print(g()[0])             SIGILL while COMPILING
    print(len([1,2,3][1:3]))  SIGILL while COMPILING

Two independent defects, both in parse_primary's postfix handling.

1. The `[` arm resolved its base with vfind(nm,nl)/gfind(nm,nl) and RETURNED
   after the first `[...]`. So a base that is not a name -- an array literal, a
   call result, a parenthesised expression -- had nothing to resolve, and
   `n[1][0]` left the `[0]` in the token stream.

2. That leftover token was harmless in a `let` and fatal as a CALL argument.
   parse_call_impl:101 saw `[` where it expected `,` or `)`, and mpnct() is
   lenient -- parse.quanta:13 returns 0 on a mismatch and every caller ignores the
   result. The argument count silently over-counted, the permutation at 139-146
   read an arg_tgt slot that was never written, and that garbage index reached
   `ir + idx*IRS + field`. The multiply overflowed and the COMPILER's own
   checked-arithmetic trap (jno/ud2, confirmed at 0x42fd9a) fired.

The worst part is the failure SHAPE: a caller-side mistake reported as an
illegal instruction inside the compiler, with no diagnostic and no line number.
The traceback points at the compiler, not at the code that caused it.

Fix: `parse_index_on(base_vr)` consumes one `[...]` against an already-produced
VREG and returns the result VREG; `parse_postfix_expr(vr)` loops it. The named-base
path resolves nm/nl once and then chains; the non-name primaries -- array literal,
call result, parenthesised expression, numeric literal -- return through
parse_postfix_expr.

`n[1][0]` on a FLAT array is not valid Quanta and is not tested: n[1] is the
integer 80, and indexing an integer reads a header off whatever 80 points at.
tests/test_postfix_index.quanta uses real nested arrays. That mis-designed probe
was mine, and it is worth naming -- `n[1][0]` looks like the obvious test and it
is not one.

tests/test_postfix_index.quanta: 38 checks over nested arrays, three-deep,
runtime indices at every level, literal/call/paren bases, string arrays, slicing a
non-name base, the named forms that had to keep working, and a nested index passed
straight to a user function with other arguments. Verified to crash the pre-fix
compiler and pass on this one.

### RESOLVED: a slice did not clamp its HIGH bound

    let b = [10, 20, 30, 40, 50]
    b[0:99]        SIGILL
    b[3:99]        SIGILL
    [1,2,3][0:99]  SIGILL
    g()[0:99]      SIGILL

Every in-range slice was already correct; only `hi > len` trapped. method.quanta's
lowering clamped ONE side:

    nraw = hi - lo
    neg  = nraw < 0
    n    = neg ? 0 : nraw        // clamps nraw < 0 only

`hi` was never bounded by the length, so the copy loop ran n iterations reading
base[lo+idx], the IR_IDX bounds trap fired once lo+idx reached len, and the whole
program died -- for what is an entirely ordinary slice expression. Python, Rust
and Go all clamp the high bound.

Fixed to `lo = max(lo,0); hi = min(hi,len); n = max(0, hi-lo)`.

The clamp is BRANCHLESS on purpose:

    oc  = hi < len
    om  = 1 - oc
    hic = hi*oc + len*om          // min(hi, len)

The obvious branch form

    BR(oc, l_hi); MOV(hic, len); LABEL(l_hi)

compiled and was WRONG: it broke even the slices that used to work
(`b[3:3]` returned 2 instead of 0, `b[4:2]` returned 1 instead of 0). A value
defined before a branch and used after it does not survive here -- codegen's
dead-definition pass rewrites a def whose result is not read back along the same
path, so `hic` came back as garbage. Empirically confirmed: the same code with a
branch is wrong, the same code branchless is right.

That is a second-order trap worth remembering: a value live ACROSS an IR_BR or
IR_LABEL in parser-emitted IR is not reliably live. Prefer arithmetic selection
in generated IR.

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

## Done in 0.0.222

### Postfix index chaining (`1f21f927` and earlier in this tree)

- `parse_index_on`/`parse_postfix_expr` chain trailing `[...]`, so `n[1][0]`,
  three-level indexing, string-array elements and nested expressions used as
  call arguments all parse. Before, the second `[` was left in the token stream
  and `parse_call_impl` consumed the commas and the `)`.
- Slice high bounds clamp to the array length. `b[0:99]` on a 5-element array
  entered the copy loop with an out-of-range bound and trapped. Branchless
  arithmetic, because parser-emitted values live across IR_BR/IR_LABEL are not
  reliably preserved by codegen's dead-definition pass -- the branch version
  broke `b[3:3]` and `b[4:2]`.
- `scripts/audit/run_gguf_tests.py` reads VERSION; it had defaulted to 0.0.221
  and silently tested the previous stable after promotion.

### GGUF decoders, verified against the compiled C (`4352c9e2`)

The reference is not hand-written: `scripts/audit/dequant_oracle.py` extracts
`dequantize_row_q8_0`, `_q4_K`, `_q5_K` and `_q6_K` verbatim out of
ggml-quants.c, links them against a driver, and dumps raw f64 bit patterns.
`dequant_diff.py` runs the Quanta decoders on the same synthetic blocks and
compares. Every value is bit-exact: these decoders only widen, multiply and
subtract, so anything short of exact is a defect.

Seven library defects, all of which returned plausible floats rather than
crashing:

- `dequant_q6k` was not Q6_K at all -- a 2-byte scale at offset 0 and 3-byte
  quant groups from offset 2, which is no GGML layout. It decoded 19 of the
  reference model's 266 tensors including `token_embd.weight`.
- and, once the layout was right, it ran one pass of 128 per 256-element block
  instead of the C's two, leaving elements 128..255 as zero. Every Q6_K tensor
  was half garbage; the first eight values matched the oracle.
- `std/fs.f16_to_f64` never masked the exponent, so the sign bit leaked into it:
  every negative half was wrong by a power of two (0xC000, -2.0, came back as
  -8589934592.0). Inf was faked as 1e308 and NaN as 0.0, so `Inf - Inf` did not
  produce NaN; subnormals used the decimal literal 1e-27 where 2^-24 belongs.
  std/gguf imports std/fs, so this shadowed gguf's correct copy.
- int8 conversion subtracted 128 AND 256, so 0xF0 became -144. Every negative
  quant in every decoder was off by 128.
- Q5_K's high-bit masks are 4^n (the C does `u1 <<= 2`), not 2^n. Group 0 agrees
  either way, so 192 of 256 elements disagreed.
- the mask test `qh & u1` was implemented as `qh % u1`; modulo is 0 for every
  u1 == 1, so bit 0 was never set.
- NaN came from `Inf - Inf`, which on x87 is a NEGATIVE quiet NaN, so a positive
  input NaN came out with its sign flipped.

Three more defects were in the audit itself and are fixed in the same commit:
the C driver's Q6_K block wrote `d` at offset 192 on top of `scales[0..1]`; its
Q5_K block used Q4_K's field layout; and its F16 subnormal conversion was off by
one exponent (it now uses the host's exact `_Float16`).

`tests/test_dequant_k.quanta` asserts every element of every block -- 800 exact
comparisons -- plus a three-block Q8_0 decode, because a one-block test cannot
see the block stride. Every expected value is generated by
`scripts/audit/dequant_k_expect.py`; none is typed by hand, because hand-typed
ones were how three of them came to be wrong. Twelve negative controls confirm
each defect is caught.

### Still open

- **A `-> f64` call's result depends on what the program called before it.**
  Found while implementing fdlibm argument reduction for `sinf`. A `-> f64`
  function returns the right bits in some programs and a constant wrong value in
  others, with no difference in its own source: `reduce(0.5)` is correct only if
  `qmult` is called somewhere in the program BEFORE it, and `reduce` calls
  `qmult` itself, so an extra earlier call appears to fix it. Only `qmult`
  matters -- it is the one callee whose body holds the 2^52 magic constant and a
  pair of guarded early returns. The argument-passing ABI, untyped-float-return,
  callee call-site count, module definition order, stack depth and `mem_alloc`
  inside the callee are all ruled out by direct test; each individual step is
  correct when executed alone. Full diagnosis, the ruled-out list, and where to
  look next are in `docs/research/call-order-f64-defect.md`. A `-> f64` call to a
  USER function is a different path from the builtin path that 0d7950b6's
  `as_f64_rdi()` fixed, and nothing equivalent exists there.

  The fdlibm reduction itself is done and every step of it is verified correct
  in isolation; it is held back at /tmp/negctl/math.sin-attempt rather than
  shipped, because a transcendental that is right only in some programs is worse
  than one with a known 57-ULP worst case. Re-applying that file is the whole
  change once the defect is fixed.

- `sin` near roots: x87 gives 73/88 bit-exact with a worst case of 57 ULP.
  Common arguments are exact; relative error near a root is not. Measured
  against the host: sin(pi + 1e-9) is 19558 ULP out, sin(1e15) is 7.7e-7 relative
  out. x87's FSIN does no accurate reduction above about 2^20.
- Long decimal literals: 160/222 exact, 58 at 1 ULP, 4 at 2 ULP, none worse.
- `mem_alloc` inside a loop body is unsafe; the next iteration can clobber it.
- Raw-pointer vs Quanta-string separation is still unresolved, so `print` on a
  string PARAMETER emits text but other string paths can still emit a pointer.
- Q8_0 exists and is now exact, but the full model has not been run end to end:
  KV cache, sampling, vector store and RAG ingestion are still to build.
