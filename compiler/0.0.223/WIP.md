# 0.0.223 — WIP

> **FROZEN BASELINE.** Promoted to stable as `0.0.224` (commit `602bab90`).
> `src` is frozen and must never be modified again; it reproduces its own
> committed binary bit-for-bit (`md5=ff78dcbbb0cbfb94a1127c7813595f83`).
> This release measured 813/817 with four trait COMPILE failures — those were
> real and were fixed in `0.0.224`. The body below is this release's own
> record and is kept accurate to `0.0.223`, not updated to `0.0.224`.

Promoted from `0.0.222` by copy. `0.0.222/src` is frozen and never modified; it
is the stable fallback. Verified before the copy:

    compiler/0.0.222/src rebuilt -> size=2974472 md5=650f03c6d6ce13bb6f575b5056e07d3d
    i.e. the frozen source reproduces its own committed binary BIT-FOR-BIT.

`0.0.223` opened clean from that baseline — no carried-over dirty edits.

The body below the "Done in 0.0.222" heading is inherited history and remains
accurate as history. Everything it says about the CURRENT tree has been
re-measured; see below.

## Current state (measured, not asserted)

    compiler/0.0.223/bin/x86/qc
    size=2978568
    md5=ff78dcbbb0cbfb94a1127c7813595f83
    source rebuilds to the same md5 (SRC and BIN in lockstep)

    official gate:  813/817 pass, 4 fail (all 4 are COMPILE failures)
    self-host:      gen0 == gen1 == gen2 == gen3  (fixed point holds)
    SELFH: 4/8      — fails only because the gate demands 0 RED and
                     `functional` is still red from the 4 trait tests below.

18 gate stages logged, every stage covered by the summary, RED only on
`functional`. GREEN: native, extern-c, extern-ld, float-oper, float-builtin,
float-return, float-operpath, generics, stdlib, multi-tu, qobj, valgrind, fuzz,
differential, verify-status, performance, security.

Note: the header this file inherited from 0.0.222 asserted three things that
were false — a `compiler/VERSION` that did not exist as described, a stale
binary md5, and "129 tests, each compiled AND run individually -> all pass".
It also claimed `dequant_diff.py` covered "all 256 elements of Q4_K/Q5_K/Q6_K";
that harness actually covers Q5_K, Q6_K, Q8_0 and F16 only (0 mismatches of 32)
and does NOT exercise Q4_K. Nothing below is claimed unless a command in this
session produced it.

## What is in THIS increment

Two files, 88 insertions. Both extend fixes already proven in earlier versions.

1. `src/x86/parse.quanta` — the nested-function skip consumed `(` and stopped at
   `)`, which made its own signature-skipping branch unreachable. The corrected
   skip consumes the nested `fn`'s name, balanced parameters, body, return type
   and optional semicolon. This removed the compiler SIGILL cluster.

2. `src/x86/helpers.quanta` — `vclr()` now also clears the four per-vreg side
   tables `vreg_struct`, `vreg_is_str`, `vreg_str_arr`, `vreg_is_big` to the
   same `-1` sentinel used by the initialisation loop in `entry.quanta`.
   This is the identical fix already shipped for `vfloat` in `e3f6af85`:
   `vclr()` resets `vreg_n` to 0, so every vreg index is immediately reusable,
   but the previous function's tags were still in those tables.
   `vreg_struct` is what `method.quanta` reads to resolve `x.field`, so a stale
   struct index made a field lookup miss and the name fall through to a call.

Gate result: 813/817, matching the measured prediction for this change set
exactly. No regression, no unexpected movement.

## Deliberately EXCLUDED from this increment

**`funcscan.quanta` — held back, not carried forward.**

The dirty tree carried an 83-line `funcscan.quanta` change with two unrelated
parts:

- `w64(imethods + slot + 8, fi)` was suspected of storing one-past-end.
  Investigated and REJECTED as a fix: the search loop `break`s with `fi` already
  at the matched index, so on a match the original line is correct. It is only
  wrong on the no-match path, which nothing reads.
- `found_f` was changed from a boolean into an index. Built and measured: an
  ordinary top-level method then returned 176 instead of 10. A regression.

Decisive finding: **`imethods` is written in two places and read nowhere.**
`grep -rn imethods *.quanta` returns two writes in `funcscan.quanta`, one
allocation in `globals.quanta`, and no consumer in the whole compiler. The
dispatch table is dead code today. Neither change is observable, and a change
no test can detect is not evidence of anything.

`compiler/0.0.223/src/x86/funcscan.quanta` is byte-identical to 0.0.222.

## What is still broken (measured)

    FAIL (compile) trait_min.quanta   rc=7
    FAIL (compile) trait_only.quanta  rc=7
    FAIL (compile) trait_test.quanta  rc=7
    FAIL (compile) trait_test2.quanta rc=7

Root cause, from direct source inspection rather than behaviour bisection:

    lexer.quanta       `impl` lexes as TT_IMPL; `self` is an ordinary identifier
    parse.quanta       no dedicated TT_IMPL branch exists anywhere
    entry.quanta:749   tokp = fn_btok(fi) + 1  — the body brace
    funcscan.quanta    fn_btok can be the signature's `)` rather than the body `{`

so an impl-contained method's body can begin parsing in the wrong place and
function identity is unreliable.

For `trait_test.quanta` / `trait_test2.quanta` this is not a parser bug at all:
they need trait-typed parameters and dynamic dispatch. CORRECTION — an earlier
note here claimed no writer of a negative trait encoding into `fn_partype`
exists anywhere in the compiler. That was WRONG and was repeated without
re-reading the source. `globals.quanta:849` writes `ptyp = 0 - (ti + 2)` and
`entry.quanta:770` consumes it into `vreg_trait`. Both ends exist.

The actual missing link is narrower: `method.quanta:1699-1707`, the
trait-tagged-receiver branch, resolves the method by NAME rather than by trait
(its own comment says "a real vtable dispatch can replace this later"), and
`imethods` — the (impl, trait-method) -> fn-index table — is written at
`funcscan.quanta:574,586` and read NOWHERE. So the dispatch data is all recorded
and then never consulted. This is why no parser work can supply it.

Plan for the fix: docs/research/trait-dispatch-increment-plan.md

## Native inference status

Loader (verified):

    dequant_diff.py  0 mismatches of 32 vs compiled ggml-quants.c
      Q6_K (block 256), Q5_K (256), Q8_0 (32), F16 (10)
    dequant_q4k      verified separately against a pure-Python oracle
    absent: Q2_K, Q3_K, IQ variants — unused by this model

Inference engine: still non-operational. Tokenizer, 30-layer forward pass,
short-conv cache, KV cache, logits/sampling and the generation loop are all
missing. `native_inference.quanta` lines 537-551 are comments where execution
belongs. `q4k_dot` / `q4k_matvec` emitter builtins are unsafe stubs; use
`lib/std/matmul_q4k.quanta`, which is oracle-verified.

## Working method notes

- Generated and freshly built binaries MUST run under
  `systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0`.
  `ulimit -v` and `prlimit` were both tried on this host and returned rc=1
  without taking effect — a capped-looking command is not a bounded run.
  A 4,816-byte binary once reached 50.7 GB anon-rss and OOM-killed the host.

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
