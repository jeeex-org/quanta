# Quanta Compiler 0.0.28 — STATE

> Internal status tracker for the compiler build in THIS folder. **Gitignored —
> never committed or pushed.** Deeper SME handoff: `agents/memory/quanta.md`.

## How to read this file
- **Status: WIP** = actively building this version. **Status: DONE** = promoted
  (binary verified, regression test green, committed as `0.0.XX`).
- The single feature for this version is listed under **Scope (this version)**.
- One feature per WIP version (fix-forward). Do not pile extras onto a WIP.

## Status: WIP
## Version: 0.0.28
## Feature: F6 — explicit allocator + defer

### Scope (this version)
F6: `defer` statement (runs at scope exit, LIFO) + an explicit allocator /
arena concept so resource cleanup is predictable. Build on the existing
`alloc`/`free` primitives if present; otherwise add minimal `defer` first.

### What already works (from prior versions, do NOT re-break)
- F0 arity, F1 import, F2 generics, F3 located diagnostics.
- F4 tagged unions (`enum`) + `match` (expression arms; block arms deferred).
- F5 `Option`/`Result` construction + exhaustive `match` on Some/None/Ok/Err.
  `?` is **unwrap** (extracts payload on Ok, no-op on Err path / panics) —
  **`?` propagation (early-return on Err) is DEFERRED** (needs function-exit
  label plumbing; a naive mid-function IR_RET deletes later code in opt).

### Known gaps carried forward (candidates for later versions)
- F4: `match` **block arms** (`1 => { ... }`) — only expression arms work.
- F5: `?` **propagation** (early-return on Err/None) — currently unwrap only.
- `if`/`while` are not expression-valued.
- Return-type consistency checking (F3 scope cut; capture logic buggy).

### Promotion checklist (run before flipping to DONE)
1. Build full self-host: `bootstrap/qc-bootstrap-0.0.27 src/x86/main.quanta bin/x86/qc_boot`
   then `qc_boot ... qc_self`, `qc_self ... qc`. All RC=0, `cmp qc_self qc` identical.
2. `qc` passes the 64-suite regression gate (64/64).
3. Keep only `qc` in bin/x86; `cp qc ../../bootstrap/qc-bootstrap-0.0.28`.
4. Commit as `0.0.28: ...`. Scaffold 0.0.29 (F7 comptime) with this STATE.md.
