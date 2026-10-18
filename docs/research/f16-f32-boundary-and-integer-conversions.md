# f16/f32 across a function boundary, and integer f16 conversion — 0.0.248

Companion to `docs/research/f16-f32-language-types.md` (0.0.247), which landed the types, the real
2/4-byte widths, the ggml-pinned conversions and the promotion rules. This version closes the four
gaps that document named as follow-ons: **#11** (the declared type was dropped at a function
boundary), **#12** (F16C was required unconditionally), **#13** (`as f16` rounded twice) and **#14**
(the declared `[N]` of a typed buffer).

Everything below was measured on this box with `./compiler/<ver>/bin/x86/qc` and
`./scripts/quanta_run.sh`. Where a number appears, the command that produced it appears with it.

---

## 1. A26 — the declared parameter/return type was dropped, silently

**The defect (0.0.247).** `compiler/0.0.247/src/x86/globals.quanta:500-501` allocated `fn_parft`
and `fn_retft` as 2 MB tables; grep found the declarations and their comment and nothing else.
Both compile rc=0:

    fn id32(x: f32) -> f64 { return x }
    fn ret32() -> f32 { return 1.0000001 }

**The probe, and why its oracle is not a hand-computed constant.** The expected bit pattern is
produced by the compiler itself — `w[0] = 1.0000001` into an `f32[2]` buffer stores the correctly
rounded binary32 value, so a mistake in the probe's arithmetic cannot manufacture a pass:

    let w: f32[2] = mem_alloc(2)
    w[0] = 1.0000001
    f64bits(id32(1.0000001)) != f64bits(w[0])   // 0.0.247: FIRES (exit 4)
    f64bits(ret32())         != f64bits(w[0])   // 0.0.247: FIRES (exit 5)

Control: `fn id64(x: f64) -> f64 { return x }` leaves the value unchanged, so the harness is sound.
`ret16()` was unreached in the 0.0.247 probe — untested, not known-good.

**The fix, in four places.**

| where | what |
|---|---|
| `funcscan.quanta` (parameter scan) | `fn_parft[fi*200+ord] = 1` for `: f32`, `= 2` for `: f16`, byte-compared next to the existing `fn_parflt` `: f64` line |
| `funcscan.quanta` (new `scan_floattypes()`, called from `entry.quanta`) | `fn_retft[fi] = 1/2` from `fn_rettype_name`/`fn_rettype_len` — the token after `->`, the same (offset,len) pair `scan_retstructs` and `scan_retbig` read, so the index cannot drift |
| `codegen.quanta` `IR_PARAM` | the incoming ABI register is narrowed in the CALLEE with one RNE rounding and the parameter vreg is tagged (`vreg_ftype`, `vfloat`) |
| `codegen.quanta` `IR_RET` | a declared `-> f32`/`-> f16` narrows its value before `ret`; `method.quanta`'s call-result tagging plus the post-aclr re-derivation give the caller the declared float type so chained arithmetic stays in binary32 |

`entry.quanta` also tags the parameter vreg at parse time, because the operator routing (`ft_arith`
/ `ft_cmp`) reads `vreg_ftype` while the body is being parsed, and `aclr()` does not clear that
table — the emit pass therefore sees the same tag.

---

## 2. The calling convention for an f16/f32 argument and return

**Statement.** An f16/f32 argument crosses the boundary as its **widened f64 bit pattern** in the
ordinary ABI register — `rdi`, `rsi`, `rdx`, `rcx`, `r8`, `r9`, then the stack from arg 6 — and the
**callee** narrows it, once, with the same RNE rounding the conversion builtins use. A return
crosses back the same way in `rax`.

**Why the callee narrows, and not the call site.** Parse and emit are FUSED per function and
functions are emitted in source order, so a callee can be emitted before any call site is reached.
Nothing at the call site is available at emit time, and the argument's type is not knowable in
general. The callee's own declared signature is the only source of truth that exists at the moment
the narrowing has to be emitted. (This is the same structural fact that makes an untyped parameter's
floatness inferable only from a token-level pre-pass — see `scan_call_types`.)

**Why no sub-word width is in flight.** A `f64`-carrier convention means caller and callee have no
width to disagree about. The alternative — passing the raw 4-byte or 2-byte pattern — has to be
known by both sides, and a disagreement is invisible in a value comparison: a 4-byte transfer of a
widened carrier reads as `0` for almost every value (every f32 value's carrier has its low 29 bits
zero) and a raw f32 pattern read as an f64 is a denormal.

**The test pins RAW values, not round trips.**
`test_suites/codes/f32_f16_calling_convention_test.quanta` reads the exact 64-bit content the callee
holds with `f64bits` (a bit readout, no arithmetic) and compares against hard-coded patterns for
`x = 1.0000001`, which is not representable in f32 or f16 so all four of its numbers are distinct:

    f64(x)                                        4607182419250377371
    f32(x)  raw binary32                          1065353217
    f32(x)  widened carrier                       4607182419336888320
    f16(x)  raw binary16  15360 (0x3C00)
    f16(x)  widened carrier                       4607182418800017408

It asserts the carrier in EVERY register slot and on the stack (arg 6 and beyond is a different path
in both the caller's marshalling and the callee's `IR_PARAM`), in mixed f64/f32 calls, that the
neighbours of the f32 argument are bit-identical, and — as explicit negatives — that the value is
not 0 (the 4-byte-truncation signature), not the raw binary32 pattern, and not the unrounded f64
pattern.

Red first: `0.0.247` exit 10, `0.0.248` exit 0.

---

## 3. F16C removed: the f16 conversions are integer, and single-rounding

**The dependency.** 0.0.247 emitted `vcvtph2ps` / `vcvtps2ph` unconditionally for every f16
conversion, `as f16`, f16 buffer load and f16 buffer store: no CPUID dispatch and no fallback. On
this box (`avx2 f16c fma`) that runs; on any x86-64 without F16C the same binary is SIGILL.

**The decision: remove the dependency instead of dispatching it — and the f64→f16 direction FORCES
that.** `vcvtps2ph` takes an f32, so f64→f16 through it is `cvtsd2ss` (round 1) then `vcvtps2ph`
(round 2). Two roundings are not one. Measured against an independent exact-rational reference
(nearest, ties-to-even, computed with `Fraction`) over **2,000,000 random f64 bit patterns**, the
double-rounded result differs on **2** of them:

    4997.9998123605865  ->  0x6CE1 single     0x6CE2 double
    0.01067733750483339 ->  0x2177 single     0x2178 double

Rare by frequency, dense near f16 midpoints by structure — which is where an unlucky or adversarial
value sits. A CPUID dispatch would have kept the F16C path for the cases where it is exact and would
still have needed the integer path for this one, i.e. the integer path is required either way; given
that, using it unconditionally also removes the per-site branch, the cached feature word and the
program-startup hook a dispatch needs.

**What replaced it.** Two emitted routines, both integer:

    ft_f64_to_f16_bits()   rax = f64 bits -> eax = f16 bits, ONE round-to-nearest-even
    ft_f16_to_f32_bits()   eax = f16 bits -> eax = f32 bits, exact widening (nothing to round)

Round-to-nearest-even is the standard carry trick, one add chain instead of a second branch: to
round `x` right by `s` bits,
`q = (x + (1 << (s-1)) - 1 + ((x >> s) & 1)) >> s` — it adds 1 exactly when the dropped bits exceed
a half, and exactly when they equal a half AND `q` is odd.

The f64→f16 routine handles the f64-subnormal input (always rounds to zero: every f64 subnormal is
below 2^-1022, far under the f16 half-subnormal 2^-25), the normal f16 range (E in [-14,15]), the
subnormal range (E in [-25,-15], `s = 28-E`), overflow (`E >= 16`, and the mantissa carry that
pushes `e16` to 31 — which is exactly the RNE behaviour at 65520), and inf/NaN (sign preserved,
canonical quiet NaN 0x7E00, which is libggml's).

**Every dependent site moved with it**: the conversion builtins (kinds 3, 4, 5, 6, 8), the shared
`ft_narrow_rax(2)` used by parameters, returns, `as f16` and `let x: f16`, the f16 element load
(`IR_IDX`) and the f16 element store (`IR_ISTORE`). `f64 <-> f32` keeps `cvtsd2ss`/`cvtss2sd`, both
SSE2 and therefore part of the x86-64 baseline — nothing is left to dispatch on.

**Evidence, zero tolerance.** `fp16_conv_oracle_test` (fixtures generated by calling the installed
libggml-base's `ggml_fp16_to_fp32` / `ggml_fp32_to_fp16`, plus the host compiler's `(float)` cast):

    f16->f32  exhaustive, all 65,536 patterns   0 mismatches
    f32->f16  131,072 cases                     0 mismatches
    f64->f32  65,536 cases                      0 mismatches

Unchanged from 0.0.247, and now produced by integer code. Two intermediate failures are worth
recording because each was a real, silent shape:

* `test r10, 0` — the immediate form with an immediate of 0 ANDs with zero, so its result is always
  zero and **ZF is always set**; the zero test fired on every input. gdb showed `test r10,0` with
  `r10=0x3ff` and `eflags=0x246` (ZF set) as the tell, and the routine returned the sign bit alone
  for every value. `test r64, r64` is the only correct zero test.
* `test r64, r64` for a HIGH register needs `REX.R` as well as `REX.B` (both the ModRM reg and rm
  fields encode the register), so `rtest0(10)` without `REX.R` emitted `test %rdx,%r10`.

**Mechanical independence check (new gating stage 1.6d).** A functional test cannot see the
dependency on a box that has F16C, so the gate scans the emitted bytes for the two opcodes
(`c4e27913` = `vcvtph2ps`, `c4e3791d` = `vcvtps2ph`):

    0.0.247   f16_single_round_test 58 F16C opcodes   fp16f32_width_test 6
    0.0.248   f16_single_round_test  0                fp16f32_width_test 0

A F16C fast path behind a cached-CPUID check remains available as a footprint/speed lever (both
routines are ~60 and ~25 instructions); it is a performance item, not a correctness one.

---

## 4. `as f16` is one rounding (A26's sibling, item #13)

`parse_as` was `ft_narrow(l, 1)` followed by `ft_narrow(nr, 2)`: an explicit yet unrequested rounding
to binary32, then the f16 rounding — and the f64→f16 builtin it called rounded through `cvtsd2ss`
again. It is now `ft_narrow(l, hk - 66)`, one call, and the routine behind it is single-rounding.

**The witnesses are CONSTRUCTED, not hunted**, which is what makes the row an assertion about the
number of roundings rather than about arithmetic luck:

    H      = an EVEN f16 pattern, so H+1 is the next value up and the tie breaks DOWN
    a, b   = the two f16 values, from their bits via f16bits_to_f64 (exact, no decimal literal)
    m      = (a + b) * 0.5   -- exact: 11-bit significands, halving is exact
    x      = m + eps, eps = 2^-37 (normal) or 2^-45 (subnormal), built as 1.0/2^n

    single rounding: x is strictly above the midpoint      -> H + 1
    double rounding: f32(x) is exactly m, m is a tie       -> ties-to-even -> H

Five cases (midpoints of 0x3C00/0x3C01, 0x4400/0x4401, 0x6CE0/0x6CE1, a subnormal pair
0x0200/0x0201, and 0x7BFE/0x7BFF just under the f16 maximum) assert both `== H+1` and `!= H` through
the conversion builtin, the cast, a declared `-> f16` return and an f16 buffer store. Red first:
0.0.247 exit 11, 0.0.248 exit 0.

---

## 5. The typed-buffer `[N]`: semantics measured, and pinned

Read from the source and then measured, because the two forms differ (item #14):

* `let b: T[N] = <initialiser>` — **N is informational.** `parse_let` records it in `g_arrsz` and
  uses it only on the no-initialiser path. The storage is the initialiser's, and the length the
  runtime checks at every index is the count the allocator wrote into `[base]`. The **element
  stride** does follow the declared type (4 bytes f32, 2 f16) — that part is real, and is what
  `fp16f32_width_test` pins byte by byte.
* `let d: T[N]` with **no initialiser** — **N is the allocation**: `IR_ARRNEW` with N elements and a
  header of N. This is the form `lib/std/ai.quanta` relies on (`let data: i64[1]`).

The enforced bound is one check in both cases (`cmp [base], idx; jb +2; ud2`, armed by default), so
`[N]` is **not** a checked bound in the initialised form. Measured:

    let b: f32[2] = mem_alloc(8)   b[5] = 2.5   -> works; mem_load(b) = 8
    let c: f32[8] = mem_alloc(2)   c[2] = 1.5   -> SIGILL (rc 132); mem_load(c) = 2

`f32_buffer_semantics_test` (exit 0) and `f32_buffer_bound_trap_test` (exit 132) encode exactly that,
including the 2-byte f16 stride and the no-initialiser form. Both pass identically on 0.0.247 and
0.0.248: this item is a **decision made verifiable**, not a defect repair, and the rows say so in
their headers.

**Enforcement of the declared N is deliberately left as its own lever**, not half-done here. The
shape: at a sized binding with an initialiser, emit a capacity check `header >= N` (for the element
count the annotation implies) that traps like the index check does. It needs either a new IR op or a
reuse of the index trap that codegen's dead-definition pass cannot rewrite into `MOV res,res` — the
pass exempts `IR_CONST`/`IR_FCONST` by opcode precisely because a dead-looking record can still be
read through the argument list. Until it exists, no row in the tree claims the declared N is checked,
and `docs/plans/language-capabilities.md` #14 records the semantics verbatim.

---

## 6. Two silently-wrong literal classes found on the way (filed, not fixed)

Both were found by measurements this work needed, and both are pre-existing (identical on 0.0.247
and 0.0.248). Neither is the f16/f32 boundary, so neither was fixed inside this version — one lever
per version — but neither is left as a note in a comment either; both are `docs/plans/bugs.md`
entries with the raw evidence.

**A29 — a hex literal with more than 8 digits is silently wrong.**

    0xFFFFFFF     -> 268435455            correct (7 digits)
    0xFFFFFFFF    -> 4294967295           correct (8 digits)
    0x100000000   -> 1152921504606846976  want 4294967296
    0x1FFFFFFFFF  -> 2305843004918726911  want 2199023255551   (0x1fffffff000000ff)
    0x123456789A  -> 1311768464867721370  want 78187493530    (0x123456780000009a)

The first 8 digits land in the HIGH 32 bits and the remaining digits in the low bits. The `2^41 - 1`
rounding constant in the f16 routine was written as this literal and came out
`movabs $0x1fffffff000000ff` in the emitted code — a wrong rounding mask, in exactly the code that
must be bit-exact. It is written as a shift now (`ri(0,1); rshl_imm(0,41); rdec(0)`), and that
workaround is the reason the item is filed rather than tolerated.

**A30 — one 17-digit decimal literal rounds 1 ULP away.**

    f64bits(4997.9998123605865) -> 4662217373610405594   0x40B385FFF3B3EEDA
    correctly rounded f64       -> 4662217373610405595   0x40B385FFF3B3EEDB

Three other 17-digit literals (`0.30000000000000004`, `1.0000000000000002`,
`1234567890123456.0`) are correct, so it is a specific input rather than a blanket digit limit. It
is why the f16 witnesses are built from bit patterns and exact powers of two instead of from long
decimals, and why every literal the new rows do use is asserted against `f64bits` first.

---

## 7. What is still open, named plainly

* **`lib/std` has not adopted f16/f32.** The loader's f16 arithmetic is still its own hand-written
  integer code (`gguf.quanta:1719 f16_to_f64`), and the 49 `× 8` allocation sites are untouched.
  That is a separate task and a peer unit owns `lib/std/**`.
* **f32 SIMD/vector arithmetic** is not implemented (backlog #9) and was explicitly out of scope.
* **No F16C fast path.** Correct on every x86-64, slower than two instructions per conversion where
  F16C exists. A cached-CPUID dispatch is the shape; it needs a writable feature word at program
  startup.
* **The declared `[N]` is not enforced** (backlog #14, semantics pinned, enforcement designed above).
* **Precompiled `.qobj` modules lose the parameter's declared f16/f32 type.** The cache carries the
  return type name (`fn_rettype_name`, so `-> f32` survives) and the struct/string parameter flags,
  but there is no metadata field for `fn_parft` — a function imported from a cache, with its source
  absent, would narrow nothing. Source inlining (`expand_includes`) is the path every row in the tree
  takes, so this is a cache-format gap rather than a live defect; recorded here rather than hidden.
* **A29 and A30** (above) are open, with their own red-first rows still to be written.

---

## 8. Verification summary (raw)

| check | command | result |
|---|---|---|
| full gate | `bash test_suites/scripts/run_tests.sh` | **238/238 pass, 0 fail** (was 233 rows; +5 new), **stdlib 114/114 GREEN**, every stage GREEN, `GATE_EXIT=0`, new `f16c-indep` stage GREEN |
| release verification | `bash scripts/verify-release.sh 0.0.248 0.0.247` | **14 passed, 0 failed** (exit 0) |
| self-host fixpoint | `setarch -R genN src/x86/main.quanta genN+1` ×3, then `md5sum` | gen1 == gen2 == gen3 == gen4 == the committed binary = `b9e36271373d108eb52989f08d841365` |
| frozen baseline intact | `verify-release` check 8 | 0.0.247's source rebuilds bit-for-bit: `a17e3cfb056f55d4ee68a0db0dfcfa22` |
| ADDITIVE, measured | compile all 238 native rows with both compilers, compare binaries | **232 rows byte-identical**; the 6 that differ are exactly the f16/f32 rows (`fp16f32_width_test`, `fp16f32_type_test`, `a26_f32_f16_paramret_test`, `f32_f16_calling_convention_test`, `f16_single_round_test`, `f32_buffer_semantics_test`) — no existing f64 or integer program emits a different byte |
| oracle unchanged | `fp16_conv_oracle_test` | 65,536 + 131,072 + 65,536 cases, 0 mismatches, on integer code |

The byte-identity row is the strongest available statement that this version is additive: the whole
native corpus is compiled twice, with the previous compiler and with this one, and only programs that
actually use f16/f32 differ. Combined with the fixpoint and the frozen-baseline check, no existing
f64 result — the 128k-logit inference, the tokenizer rows, every gate row — can have moved.

One note on attribution for anyone re-running this: `verify-release`'s gate compiles `lib/std/**`
as the working tree has it, so a peer's UNCOMMITTED edit under `lib/std/` is measured too. The first
run of the check here reported `stdlib RED` on four `stdlib_lfm2_*` rows with
`call to undeclared function: fc_conv_scalar` — a symbol that exists only in a peer's uncommitted
`lib/std/lfm2_forward.quanta` (`git grep fc_conv_scalar HEAD -- lib/std` finds nothing). Verified
not-ours by compiling one of those rows against a PRISTINE `lib/std` from HEAD in a scratch symlink
farm: compile rc=0, run rc=0. The re-run above is 14/0.
