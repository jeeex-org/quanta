# 0.0.128 — `big` div-by-zero guard (FIX-0.0.19)

**Status:** ✅ DONE — self-hosting, gate-green, all 11 layers GREEN.

## What landed

A genuine hole in `lib/std/big.quanta` was closed: `big_div` and `big_mod`
(previously `big / 0` and `big % 0`) had **no zero-divisor guard**. They
delegated to `big_udiv`, whose doc-comment says "Caller must ensure 0 < y" but
nothing enforced it. With `y == 0`, `big_ge(0, x)` is false for `x > 0`, so the
function fell into the shift-subtract loop and **looped forever** (hang — no
termination, no error).

**Fix:** added a `big_is_zero` helper and guarded both entry points:

```
fn big_is_zero(a: big) -> i64 { ... }     // scans all limbs
fn big_div(a, b) { if big_is_zero(b)==1 { exit(1) } ... }
fn big_mod(a, b) { if big_is_zero(b)==1 { exit(1) } ... }
```

On a zero divisor the program now performs a **fatal `exit(1)`** (matching the
existing `IR_UNWRAP` panic convention) instead of hanging.

## Verification

- **Fixpoint:** gen1==gen2==gen3 byte-identical, md5
  `e1d5ed96d9df41f69297c4bcd2b50b4c` (identical to 0.0.127 — the change is
  library-only and does not affect the compiler's self-compilation).
- **Gate:** functional **161/161** (incl. new `big_divzero_test.quanta` rc=1),
  stdlib 7/7, multi-TU 3/3, all 11 layers GREEN.
- **Behavioral checks (manual):**
  - `big / 0` → `exit(1)` (was: infinite hang) ✓
  - `big % 0` → `exit(1)` (was: infinite hang) ✓
  - `987654321098765432109876543210 / 123456789012345678901234567890 == 8` ✓
  - `... % ... == 9000000000900000000090` (unchanged) ✓

## Scope note

This is a **library fix** in `lib/std/big.quanta`, not a compiler-core change.
The `big` type itself was completed in 0.0.114; this closes the last verified
gap (FIX-0.0.19). The change is conservative: only the two div/mod entry points
got a guard; the arithmetic is untouched.

## Next

0.0.129 — `fs` missing ops (stat / unlink / mkdir / chdir / rename / rmdir).
