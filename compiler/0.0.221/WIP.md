# 0.0.221 — WIP

Promoted from `0.0.220` at commit `caa372c5`, whose state was verified before
the copy:

    compiler/0.0.220/bin/x86/qc
    size=2921088
    md5=c4194801bd7d4540d321129d557fa536
    self-hosted 3 generations byte-identical
    suite PASS=118 CFAIL=0 RFAIL=33 of 151

`0.0.220` is a good state and stays as the stable fallback. All new work
happens here; `0.0.220/src` is never modified.

(The WIP.md copied from an older tree was stale — 0.0.218's, describing
`--emit-dynamic` work. Replaced, not appended to.)

## Current state (measured, not asserted)

    compiler/0.0.221/bin/x86/qc
    size=2921088
    md5=33df91c3bcf9a091632edffa43f93c4b
    self-hosted 3 generations byte-identical
    gate PASS=117 CFAIL=0 RFAIL=34 of 151    deterministic over repeated runs

An earlier "PASS=118 ... RFAIL=33" in this file was WRONG -- it was measured
against a stale failure list in /tmp. The baseline above is the verified one.

## Done in 0.0.221

- `expf` in lib/std/math.quanta, replacing gguf_exp's private copy. Three
  overflow/underflow defects fixed: 2^1024 is unrepresentable so the 2^k
  scaling had to be split; the mirror bug at x=-745 where 2^1075 overflows the
  divisor; and a guard that returned 1.0e308 for anything above 709.0, wrong by
  ~600x across the whole finite 709..709.78 band. Now 278 of 278 finite audit
  cases within 1e-12 relative, median 3.8e-15.
- `pow` renamed to `ipow` in std/math. A user function SHADOWS a builtin of the
  same name, so std/math's integer `pow` was replacing the float `pow` builtin
  for every importer and SIGILLing two inference tests. Verified directly: with
  a user `fn pow`, `pow(2.0, 3.0)` returned the integer result.
- Float literals with more than 17 significant digits were silently wrong --
  a scaling error of 10x per extra digit, because the lexer froze the mantissa
  while still counting fraction digits. Found via fdlibm's pi/2 high word
  (21 digits), which materialised as 3.86e+03. Now exact to within 2 ULP for
  every literal, and that residual is the token format's 55-bit mantissa field,
  not the algorithm.

## RFAIL=34: the cause is the TESTS, not the compiler

All 34 are GGUF tests that hand-roll the parse with `read_raw`. They
mis-implement one rule: **a GGUF array of strings is `count x (u64 len + len
bytes)`** -- length-prefixed, no offset table, no per-element NUL. They skip
`alen * 4` instead.

    698  u64 key_len = 12
    706  "general.tags"
    718  u32 vtype = 9        (ARRAY)
    722  u32 elem_type = 8   (STRING)
    726  u64 count = 4
    734  u64 6    "liquid\0"
    750  u64 6    "lfm2.5\0"
    766  u64 4    "edge\0"
    782  u64 15   "text-generation\0"

The failure chain: wrong skip -> parse desyncs -> `klen` becomes
`0x666c000000000000` (ASCII "lf") -> seek runs past EOF -> `read_raw` returns
junk -> `alen * 4` overflows -> the inline trap (`jno +2 ; ud2`) fires
CORRECTLY on garbage. The SIGILL is the fourth symptom.

`std/gguf` already implements this correctly with a per-element loop, and it
parses the real model: 266 tensors, 37 kv entries, data_offset 8239136.

Header order is `magic[4], version u32, tensor_count u64, kv_count u64` --
**tensor count comes first**. This model has 266 tensors and 37 metadata
entries. Walking all 37 metadata records with the corrected rules lands exactly
on offset 8222781, where the tensor-info section begins.

## Compiler changes TRIED AND REVERTED (each regressed the gate)

- LRU eviction in `afree` (evict the oldest mapping instead of the newest).
- Adding R11 to the allocator's 14 register slots.
- Making `aphys` reload from the home slot instead of trusting the register.

All three are in /tmp/keep/ for reference only. Do not re-apply. The operand was
never stale -- the program was wrong.

## Next

1. Rewrite the failing tests against `std/gguf` with real assertions. They
   currently print values and exit 0 or crash; none compare.
2. `test_all_final` is a false pass: it prints `Matvec: 0, 0 (expect 17, 39)`
   then `All 7 tests PASSED`.
3. `abs`, `min`, `max` in std/math still shadow builtins. Integer-only callers
   today, but rename to iabs/imin/imax before any float use lands there.

## Carried over

New values must be parked in a global when they must survive more than a few
dozen lines in one function; codegen/funcscan lose long-lived locals.
