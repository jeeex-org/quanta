# Quanta 0.0.110 — Release State

- **Version:** 0.0.110
- **Date:** 2026-08-27
- **Source entry:** `compiler/0.0.110/src/x86/main.quanta` (16 modules)
- **Build seed:** 0.0.109 (`compiler/0.0.109/bin/x86/qc`)
- **Self-host fixpoint:** stage2 == stage3, md5 `84a8b9f429141138bc7945f1a0a22748` (byte-identical)
- **Promoted from:** 0.0.110 (this version; copied from 0.0.109)

## What changed
Types: typed array / slice `T[]` annotation. Added `let a: i64[] = [...]` parsing —
after consuming the element type keyword in `parse_let`'s `:` branch, a trailing `[]`
suffix sets vtype=11 (VT_ARRAY) on the binding. Indexing `a[idx]` and subscript
assignment `a[i]=v` already worked at runtime via IR_IDX (header-carrying base,
elements at base+8+i*8); the annotation only records the type tag.

Also corrected a stale FEATURES row: `String` type annotation (`let s: String`) was
ALREADY implemented in 0.0.95 (VT_STRING=10, wired in parse_let) — the B-core
`string (real type)` row was marked ❌ todo erroneously. Now ✅.

## Tests
- `typed_array_test.quanta` (rc=0): `let a: i64[] = [10,20,30,40]`, index read,
  index read+arith, second array, subscript assignment `a[0]=99`; early-exit per-check.
- Carried forward: bitops_test (rc=0), fs_meta_test (rc=11), intrinsic_test (rc=0).
- Full gate: 143/143 functional + extern-c/security/performance/valgrind/fuzz/
  differential/generics-negative all GREEN.

## Gate result
- functional : GREEN (143/143)
- extern-c   : GREEN
- security   : GREEN (fail-closed)
- performance: GREEN
- valgrind   : GREEN
- fuzz       : GREEN
- differential: GREEN
- generics    : GREEN
- self-host   : byte-identical (stage2 == stage3, md5 84a8b9f429141138bc7945f1a0a22748)
