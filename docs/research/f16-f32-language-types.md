# f16 and f32 as first-class Quanta types — 0.0.247

The language had exactly **one** float representation: f64. `lexer.quanta:375-386`
accepted `f16`/`f32`/`f64` as Rust-style *literal suffixes* and threw them away
("A no-op for the value — one float representation — but it MUST be consumed or
it lexes as an identifier"). So `1.0f32` was bit-identical to `1.0`, there was no
f16/f32 type, no f16/f32 arithmetic, and no narrowing anywhere on the CPU: the
only `f64_to_f32` in the tree shipped the job to the CUDA daemon, because the
language could not do it.

This version makes them real types. It is **additive**: every f64 path is
untouched, and the 231 → 233 native rows and 113 → 114 stdlib rows are green with
the pre-existing rows unchanged.

## What landed

| Phase | Capability | Where |
|---|---|---|
| P1 | `f32` declarable (locals, and value-level conversion both ways) at a real **4-byte** storage width | `parse.quanta` (`hk==67`), `globals.quanta` (`vreg_ewidth`), `codegen.quanta` (IR_IDX/IR_ISTORE) |
| P2 | `f32` arithmetic — add/sub/mul/div/compare — in binary32 precision, reachable from the `+ - * / == != < > <= >=` operators | `emitter.quanta` (`fadd32`…`fge32`), `parse.quanta` (`ft_arith`, `ft_cmp`) |
| P3 | `f16` declarable at a real **2-byte** storage width, with f16↔f32 and f16→f64 conversion | `parse.quanta` (`hk==68`), `emitter.quanta` (`f16bits_to_*`) |
| P4 | the literal suffix is REAL typing, plus an explicit promotion rule | `lexer.quanta` (`TT_FNUM32`/`TT_FNUM16`), `fconst.quanta` (`fl_dexp2f32`, `fl_dexp2f16`) |

## The representation, and why the type system works at all

Quanta has one float register file and one float carrier: f64 in an xmm. So an
f32/f16 **value** is carried as an f64 that is *exactly representable in that
format*, and a conversion is a real value transformation:

- **widening** f32/f16 → f64 is exact, hence free (`cvtss2sd`);
- **narrowing** f64 → f32/f16 is one round-to-nearest-even step (`cvtsd2ss`, and
  `vcvtps2ph` with an explicit RNE rounding control).

`vreg_ftype[vreg]` ∈ {0 = untyped, 1 = f32, 2 = f16} is the declared format. The
**payload invariant** — a vreg tagged 1 or 2 holds a value exactly representable
in that format — is established *where the binding or the store happens*, not
repaired on use, so every arithmetic op on tagged operands re-narrows them and
the result is true IEEE binary32 arithmetic rather than f64 arithmetic with a
narrower label.

`vreg_ewidth[vreg]` ∈ {2, 4} is the element width in bytes of a `f16[N]` /
`f32[N]` buffer; **codegen reads it to pick the stride and the load/store width**,
which is what makes the storage actually 2 and 4 bytes instead of 8.

Both tables are cleared in `vclr()` alongside `vreg_type`/`vfloat`. A *stale*
`vreg_ftype` is worse than a missing one: a leftover tag turns an ordinary integer
`a + b` in the next function into a call to the f32 arithmetic builtin, and the
result becomes an f32-rounded value with no diagnostic — the same class of bug
the `vfloat` clear exists for.

## The promotion rule (explicit, because f16 cannot compute here)

```
f16  <  f32  <  f64          an INTEGER operand ranks as f64
```

- Both operands typed float (f16 and/or f32) → **f32 arithmetic**, result typed
  f32. f16 promotes, and the result is therefore f32, not f16 — rounding back to
  f16 happens when the value is *stored* into an f16 buffer.
- Any mixture with f64, or with an integer, → **f64 arithmetic**. An i64 does not
  fit an f32 significand, so silently ranking an integer operand as f32 would lose
  bits; ranking it f64 keeps the existing f64 behaviour bit-identical.

**Why f16 promotes rather than computes.** `/proc/cpuinfo` on this box reports
`avx2 f16c fma` and **no** `avx512f`/`avx512-fp16`. There is therefore no hardware
binary16 arithmetic to compute in — no `addph`, `mulph`, `fmaddph`. f16 here is a
**STORAGE format** that promotes to f32 to compute. That is stated in the source
at `ft_arith`, in the emitter's conversion block, and here, rather than being
hidden behind a silent promotion that pretends f16 arithmetic exists.

## Rounding evidence — the decisive oracle, zero tolerance

`libggml-base` is already linked into this tree (the Q6_K dequant row was proven
bit-exact against it), and it exports

```
ggml_fp16_to_fp32(ggml_fp16_t) -> float        (f16 -> f32, widening)
ggml_fp32_to_fp16(float)       -> ggml_fp16_t  (f32 -> f16, RNE narrowing)
```

`test_suites/scripts/fp16_conv_oracle.c` calls them; the host compiler's own
`(float)` cast stands in for the f64→f32 narrowing, which ggml has no entry point
for. `test_suites/scripts/gen_fp16_fixtures.py` drives it and writes the
committed fixtures (1.5 MB under `tests/fixtures/`); `--check` re-derives them and
diffs against what is committed.

`test_suites/codes/fp16_conv_oracle_test.quanta` then compares, in Quanta, with
**zero tolerance** — one mismatch fails the row, and it prints the input and both
bit patterns:

| direction | coverage | mismatches |
|---|---|---|
| f16 → f32 | **EXHAUSTIVE: all 65,536 f16 bit patterns** | **0** |
| f32 → f16 | 131,072 cases = all 512 (sign × exponent) × 128 mantissas (every boundary and tie shape, then LCG-filled) **plus** an exhaustive sweep of all 8,192 low-13-bit patterns at exponents 0, 112, 143, 254 | **0** |
| f64 → f32 | 65,536 cases = all 4,096 (sign × exponent) × 16 mantissas | **0** |

Two of those numbers are the point of the exercise, because both were **wrong
first** and the oracle said so:

- **8,426 mismatches, all NaN.** `vcvtps2ph` *propagates* the NaN payload
  (`0x7FFFFFFF → 0x7FFF`) while `ggml_fp32_to_fp16` returns the canonical quiet
  NaN (`0x7FFFFFFF → 0x7E00`, `0xFFFFFFFF → 0xFE00`, sign preserved). Every finite
  value matched; only NaNs disagreed. `ft_f16_out_fix` canonicalises them, and is
  applied in the conversion builtins *and* in the f16 store so a stored NaN and a
  converted NaN are the same bits.
- **`vcvtps2ph` writes only the low 16 bits of its destination.** Reading 32 bits
  back returned `(stale high half) | f16` — e.g. `1.0 → 0x3F803C00` instead of
  `0x3C00`. That is a wrong number that still looks like a plausible float
  pattern, which is exactly the shape of bug a value comparison would pass.

Also pinned: the widening direction disagrees with `lib/std/gguf.quanta`'s
hand-written `f16_to_f64` nowhere. That function is the previous bit-level truth
for widening, and the exhaustive f16 table covers every input it can represent —
the same 65,536 patterns, against the same library the hand-written version was
validated against. (A direct head-to-head row importing `std/gguf` is *not* in
this version; see the gap list.)

## Width evidence — proving bytes, not labels

`test_suites/codes/fp16f32_width_test.quanta` is deliberately built so that it
**compiles on 0.0.246 and fails at runtime there** (rc=11), rather than failing to
compile: it names no new function, so the previous compiler runs it, computes the
wrong layout, and gets caught. On 0.0.247 it passes.

The assertions read raw bytes back at explicit offsets with a `0xA5` sentinel
around them:

```
f32 element 0 at base+8 .. base+11   0x3FC00000  (f32 1.5)
f32 element 1 at base+12 .. base+15  0x40100000  (f32 2.25)
f32 element 2 at base+16 .. base+19  0xC0600000  (f32 -3.5)
f32 base+20 .. base+23               0xA5A5A5A5  <- only FOUR bytes were written

f16 element 0  base+8 .. base+9      0x3E00      (f16 1.5)
f16 element 1  base+10 .. base+11    0xC000      (f16 -2.0)
f16 element 2  base+12 .. base+13    0x3400      (f16 0.25)
f16 element 3  base+14 .. base+15    0xC300      (f16 -3.5)
f16 base+16 .. base+19               0xA5A5A5A5  <- FOUR 2-byte elements wrote 8 bytes
```

and one direct contrast: `1.5` stored into an `f32` element and into an `f16`
element must read back as *different* 32-bit words (`0x3FC00000` vs `0x3E00`),
which is false if both are 8-byte f64.

`test_suites/codes/fp16f32_type_test.quanta` covers the semantics: the widths
again, the conversions at the value level, f32 operator arithmetic and all six
comparisons, the f16→f32 promotion, the mixed f32/f64 → f64 rule, `as f32`, the
suffixed literals, and the format edges (signed zero, ±inf, f16 min normal, f16
overflow-to-inf).

Its arithmetic proof is an **absorption pair**, because it is the one assertion
that distinguishes binary32 from binary64 rather than from a rounding tolerance:

```
let big: f32 = 16777216.0        // 2^24
let one: f32 = 1.0
let r32 = (big + one) - big      // 0.0 exactly: 2^24 + 1 IS 2^24 in binary32
let r64 = (16777216.0 + 1.0) - 16777216.0   // 1.0 exactly, the f64 path
```

## Literal suffixes: real typing, and the double-rounding trap

The suffix now types the literal, via two new token classes (`TT_FNUM32`,
`TT_FNUM16`) — no new token field was needed, because `TKS` is 48 with exactly one
side word already taken by the decimal exponent.

**Survey before changing it** (the task asked for it, and it de-risked the whole
change): a comment-aware scan of `test_suites/`, `lib/` and
`compiler/0.0.247/src/` finds **no live suffixed float literal anywhere in the
tree**. The matches are all inside comments or are false positives on the
identifier `fl_dexp2f64` (`…exp2f64`). So *no existing value changed*. What did
exist and still exists unchanged: `1.0f64` and `1.0` produce the same bits
(asserted), and the f64 literal path is untouched.

`0.1f32` must be the nearest **binary32** to the decimal 0.1 — not the nearest
binary32 to the nearest binary64 to 0.1. Those differ, and the difference is not
exotic: `fl_dexp2f32` / `fl_dexp2f16` are exact single roundings of the decimal,
built as structural twins of the proven `fl_dexp2f64` (same base-10^9 limb value,
same sticky bit from the /5 chain, same one-step round-to-nearest-even; only the
target precision, bias, subnormal scale and E clamp change).

Two literals pin that, both computed with an exact `Fraction` rounder on the host
and both **wrong** under f64-then-f32:

| literal | exact → f32 | f64-then-f32 |
|---|---|---|
| `7.038531e-26` (the classic Java float bug) | `0x15AE43FD` | `0x15AE43FE` |
| `1.0000000596046448` | `0x3F800001` | `0x3F800000` |

The test asserts the left column, so it fails if the shortcut is ever substituted
for the exact path.

## Red-first

| row | 0.0.246 | 0.0.247 |
|---|---|---|
| `fp16f32_width_test` | compiles, **runs, rc=11** (element read back as the low half of an f64, which for 1.5 is 0) | rc=0 |
| `fp16f32_type_test` | compile error: `call to undeclared function: f64_to_f32bits`, `undeclared variable: f32` | rc=0 |
| `fp16_conv_oracle_test` | compile error: `call to undeclared function: f32bits_to_f16` | rc=0, **0 mismatches** |

## Self-hosting and the gate

- Fixpoint: `compiler/0.0.246/bin/x86/qc` builds the 0.0.247 source to
  `a17e3cfb056f55d4ee68a0db0dfcfa22`; that binary builds it again to the same
  md5, and the **committed** `compiler/0.0.247/bin/x86/qc` *is* that md5 — the
  seed-chain fixed point (verify-release checks 6 and 7).
- One consequence worth recording: because the compiler is built by the previous
  seed, compile-time code (the literal path in `fconst.quanta`) cannot call the
  new runtime builtins. `fl_widen_f16`/`fl_widen_f32` are therefore an independent
  integer implementation of the widening, and the two are cross-pinned by the
  oracle rows rather than by inspection.

## What is still missing

Named rather than papered over; the loader adopting these types is a separate
follow-on task, and these are the pieces it — or anyone else — will hit:

1. **f16/f32 parameter and return declarations are NOT wired.** `fn f(x: f32) -> f32`
   parses (the annotation is accepted at the parameter list and after `->`), but
   `fn_parft`/`fn_retft` are declared in `globals.quanta` and nothing writes or
   reads them yet, so the format is lost at the call boundary: the parameter
   arrives untagged and the call result is an f64 carrier with no f32 tag. The
   work is in `funcscan.quanta` (set the flags where `fn_parflt`/`fn_retflt` are
   set) plus `entry.quanta` (tag the param vreg) and the three `fn_retflt` sites
   in `codegen.quanta`.
2. **f16 conversion needs F16C.** `vcvtph2ps`/`vcvtps2ph` are emitted
   unconditionally. This box has F16C (`/proc/cpuinfo`), but a target without it
   gets SIGILL instead of a fallback: there is no runtime CPUID dispatch and no
   integer fallback. The *narrowing* direction is one small function away from
   being integer-only (`ft_f16_out_fix` + a shift/mask rounder); the widening
   direction is a normalize-and-rebias loop. The compile-time twins
   (`fl_widen_f16`, `fl_widen_f32`) are already integer-only and are pinned
   against the same oracle.
3. **`as f16` goes through f32.** `x as f16` narrows to f32 and then to f16. For
   finite values that is the correctly rounded f16 of the f64 (an f64 tie for f16
   is also an f32-representable point, and f32→f16 is then exact), but it is two
   roundings by construction rather than a single one; a direct f64→f16 rounding
   would be the honest form.
4. **No f32 `%`.** The modulo operator has no typed-float route (`fmod` does not
   exist for f32 either); `+ - * /` and all six comparisons do.
5. **`2f32` (bare integer + suffix) is still not a float.** The float lookahead in
   the lexer does not treat a trailing `f` as a float marker, so only a DOTTED
   literal takes a suffix. `2f64` is equally unsupported today, and the lexer
   comment that claimed otherwise has been corrected.
6. **A typed buffer's `[N]` is informational.** `let b: f32[N] = mem_alloc(K)`
   takes its runtime length from the allocator header (`K` qwords), exactly as
   `i64[K]` does; `N` records the element type only. `b[i]` is bounds-checked
   against `K`, so `N` larger than `2K` is silently unreachable rather than an
   error. A typed allocator that sized storage from the declared element count
   and width would remove the mismatch.
7. **f32 SIMD.** The fused kernels are still f64/AVX2; the 8-wide f32 path this
   type makes possible is a follow-on (already backlog item 9).
