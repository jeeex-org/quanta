# Quanta 0.0.130 — extern-C variadic (partial core, DONE)

## Summary
extern-C variadic function support: `extern "C" fn printf(fmt: i64, ...): i64;`
declares a variadic libc function and `printf(fmt, a, b, ...)` passes the
variadic arguments through to the C ABI.

## What changed
- `codegen.quanta` (call emission, SysV x86-64):
  - The internal stack-args spill (args 6+) was **deferred** until AFTER
    `is_ext_call` is resolved (previously it ran unconditionally before the
    extern flag was known).
  - Non-extern (internal) variadic calls: spill 6+ args highest-index-first
    before the call (unchanged behavior, now correctly gated).
  - Extern "C" calls: spill 6+ args in reverse order **AFTER** the
    `push r11` rsp-alignment push, immediately before the `call`. This puts
    the stack args directly above the return address, where the callee reads
    them (`[rsp+8]`, `[rsp+16]`, ...).

## Bug fixed (real, reproduced)
`printf(s, 1,2,3,4,5,6,7)` under the 0.0.129 compiler printed
`1 2 3 4 5 582 6` — the `push r11` alignment push landed **between** the
return address and the first stack arg, shifting every stack arg by 8 bytes:
arg 6 read garbage (`582`), arg 7 was never passed. Reproduced on the
0.0.129 golden binary; fixed and re-verified under 0.0.130.

## Verification (real)
- Fixpoint: gen1==gen2==gen3, qc md5 `85f4122ae7b9626fe529d2b94eb79158`.
- `extern_var_test.quanta` → sentinel `EXTERN_VAR_OK`; prints
  `11 22`, `1 2 3 4 5 6 7`, and the sentinel. Passes under BOTH gcc-link and
  gcc-free `ld` link (EXTERN_EXPECTED.tsv now 2 suites).
- ≤6-arg variadic (`printf("%d %d", A, B)`, float args, string args) still
  correct (regression-checked).
- Gate: functional **162/162**, stdlib 7/7, multi-TU 3/3, all 11 layers GREEN.

## Next core
0.0.131 — closure self-recursion by name
