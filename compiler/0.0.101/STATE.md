# Quanta 0.0.101 — Compiler State

## Version
- VERSION pointer: 0.0.101
- Feature: generics — compile-time type-argument validation (monomorphisation foundation)

## Source
- `src/x86/main.quanta` is the compiler entry (split into co-located modules via
  compile-time `include`). Built with the prior stable seed.

## Build / Seed chain
- Seed: `compiler/0.0.100/bin/x86/qc` (md5 `52abed5acf470aabc50d6d11e31b0f2d`)
- 3-stage self-host chain:
  - gen0 (qc_boot):   seed   compiles src -> qc_boot
  - gen1 (qc_self):   qc_boot compiles src -> qc_self
  - gen2 (qc):        qc_self compiles src -> qc
- **Fixpoint verified**: `qc_self == qc` byte-identical
  - md5(qc) = `e29cfb1ea42696be44a431a897efa79d`

## What 0.0.101 changed (method.quanta)
- Generic CALL sites now run compile-time checks (inside the existing
  `if fn_generic!=0` block, no new dispatch chain):
  - Type args are OPTIONAL. Omitted -> type-erased default (single i64),
    preserving existing call sites (`generics_test`, `where_clause_test`).
  - When PROVIDED: arity must equal `fn_genparams`; each type-arg must name an
    existing struct (`findstruct`) or the primitive `i64`.
  - Violations are HARD compile errors (calls `compile_error` then `exit(1)`),
    not silent type-erased calls.
- Per-type body specialization (true monomorphisation) is DEFERRED to 0.0.102.

## Fixpoint safety rationale
- The compiler's OWN source contains zero generic functions, so the new
  generic-call paths are never exercised when the compiler compiles itself.
  Combined with no new `else if` dispatch entries and no `$$()` in source,
  the 3-stage fixpoint is structurally preserved (verified byte-identical).

## Gate (7 layers + generics), all GREEN
- functional: 139/139 (EXPECTED.tsv, +generics_typecheck)
- extern-c: gcc libc link PASS
- security: 8/8
- performance: 3/3 (baselines met)
- valgrind: clean (0 errors)
- fuzz: fail-closed (0 crashes)
- differential: opt -O == no-O + vs-seed consistent
- generics negative: both bad instantiations fail closed (gated)

## Tests added
- `test_suites/codes/generics_typecheck.quanta` (rc=42) -> EXPECTED.tsv
- `test_suites/scripts/generics_neg_tests.sh` -> wired into run_tests.sh
  (id<unknown> and id<i64,i64> must be hard compile errors)
