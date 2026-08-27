# Quanta Compiler 0.0.29 — STATE

> Internal status tracker for the compiler build in THIS folder. **Gitignored —
> never committed or pushed.** Deeper SME handoff: `agents/memory/quanta.md`.

## How to read this file
- **Status: WIP** = actively building this version. **Status: DONE** = promoted
  (binary verified, regression test green, committed as `0.0.XX`).
- The single feature for this version is listed under **Scope (this version)**.
- One feature per WIP version (fix-forward). Do not pile extras onto a WIP.

## Status: WIP
## Version: 0.0.29
## Feature: F7 — comptime / const-eval + reflection (TBD at implementation)

### Scope (this version)
F7: a compile-time evaluation mechanism (e.g. `comptime` blocks or `const` that
are folded during compilation) and/or basic reflection (type introspection).
Investigate existing `opt_func` constant-folding first — comptime may partly
reuse it. Keep scope tight: ONE coherent capability this version.

### What already works (from prior versions, do NOT re-break)
- F0 arity, F1 import, F2 generics, F3 located diagnostics.
- F4 tagged unions (`enum`) + `match` (expression arms; block arms deferred).
- F5 `Option`/`Result` construction + exhaustive `match`; `?` = unwrap (propagation deferred).
- F6 `defer` statement: LIFO at scope exit, local-variable capture, nested scopes
  (verified rc=15/9/30). Allocator: `mem_alloc`/`free` + P2 auto-ownership-free.

### Known gaps carried forward (candidates for later versions)
- F4: `match` **block arms** (`1 => { ... }`) — only expression arms work.
- F5: `?` **propagation** (early-return on Err/None) — currently unwrap only.
- `if`/`while` are not expression-valued.
- Return-type consistency checking (F3 scope cut; capture logic buggy).

### Promotion checklist (run before flipping to DONE)
1. Build full self-host: `bootstrap/qc-bootstrap-0.0.28 src/x86/main.quanta bin/x86/qc_boot`
   then `qc_boot ... qc_self`, `qc_self ... qc`. All RC=0, `cmp qc_self qc` identical.
2. `qc` passes the 65-suite regression gate (65/65).
3. Keep only `qc` in bin/x86; `cp qc ../../bootstrap/qc-bootstrap-0.0.29`.
4. Commit as `0.0.29: ...`. Scaffold 0.0.30 (F8 package/C-interop) with this STATE.md.
