# Quanta 0.0.131 — closure self-recursion by name (partial core, DONE)

## Summary
A named closure body can now refer to its OWN name to recurse:
```
let fact = fn fact(n: i64): i64 {
  if n <= 1 { return 1 }
  return n * fact(n - 1)
}
```

## What changed
- `method.quanta` (named-closure literal, `parse_primary` value-position):
  - After emitting the closure tuple (`IR_CLOSURE`), bind the closure's self-name
    as a REAL enclosing-scope local (`vadd(nm, nl, vr)`) tagged type-11, exactly
    like `let f = fn..{}` does for `f`. This ensures `vr`'s home slot is
    materialized (the closure tuple is written to memory).
  - Also register the self-name as a CAPTURE of that home slot
    (`cap_add(cidx, nm, nl, vr)`) so the body can read it.
- `globals.quanta`: added `clo_selfnm` / `clo_selfnl` arrays recording each named
  closure body's self-name (set in method.quanta).
- `entry.quanta` (closure-body capture binding): when binding a capture whose name
  matches the body's `clo_self*` self-name, tag the capture vreg as a fn-value
  (type 11). This lets the self-call `fact(n-1)` resolve via `vfind` to a type-11
  local and route through `IR_CLOSURE_CALL` (same path as `f(5)`).

## Bug fixed (real, reproduced)
Before 0.0.131:
- `error: undeclared function: fact` — the self-name was never registered (the
  closure body fn has an empty name in the fn table, so `findfn` couldn't resolve
  it; `vadd(nm,nl,-1)` was a placeholder that resolved to an invalid vreg).
- An intermediate attempt bound the self-name to an UNDEFINED vreg (a leftover from
  a renamed variable), which compiled but SEGFAULTED at runtime — the self-call
  jumped to a garbage codeptr from an uninitialized slot.

## Verification (real)
- Fixpoint: gen1==gen2==gen3, qc md5 `8e1bb23fc7e626ee4b8513dc690197c1`.
- `closure_selfrec_test.quanta` → rc=0 (fact(5)=120).
- Regression: existing closure tests still GREEN (closure_named_fn rc=0,
  closure_basic rc=6, closure_capture rc=15).
- Gate: functional **163/163**, stdlib 7/7, multi-TU 3/3, all 11 layers GREEN.

## Next core
0.0.132 — json (AI/data interchange)
