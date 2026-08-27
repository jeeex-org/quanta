# Quanta Compiler 0.0.25 — STATE

> Internal status tracker for the compiler build in THIS folder. **Gitignored —
> never committed or pushed.** Deeper SME handoff: `agents/memory/quanta.md`.

## How to read this file
- WIP status of the 0.0.25 build. Read first for current green status.
- Canonical CORE ROADMAP (1-feature-per-version, 0.0.22→0.0.26) lives in
  `compiler/0.0.22/STATE.md`. This file scopes ONLY the 0.0.25 feature.
- `<VER>` = `0.0.25`. `<PRIOR>` = `0.0.24`. `<NEXT>` = `0.0.26`.

## Current state (verify date against `agents/memory/LAST_UPDATED`)
- **Status:** `WIP` (scaffolded from promoted 0.0.24; not yet promoted).
- **Target:** x86-64 ONLY (ARM64 deleted in 0.0.21; clean from-scratch later).
- **Seed for this version:** `bootstrap/qc-bootstrap-0.0.24` (previous stable's `qc`).
- **Self-hosting:** inherited working (0.0.24 promoted with byte-identical fixed point).

## This version's feature (1 ONLY — fix-forward discipline)
- **F3: Located diagnostics (file:line) for compile errors** — DONE.
  `compile_error()` now prints `line N:` (1-based, computed from source offset)
  before each error message. Verified: `undeclared function`, `undeclared
  variable`, `wrong argument count` all show `line N: error: ...`.
  - **Scope note (honest):** The original F3 plan aimed to also ADD a
    return-type-consistency check (typed fn with bare `return`). Investigation
    found Quanta does NOT capture return types at all in `scanfns` — the existing
    `-> Type` parse is DEAD CODE (it checks `tokv(j)==45`, but `->` is lexed as
    `TT_OP` value **1** because `mopv()` collapses ALL two-char ops to 1). So
    there is no return-type data to check. Implementing that check requires
    FIRST fixing return-type capture (a separate, larger change) — deferred to a
    dedicated version (not F3, to respect 1-feature-per-version + no-scope-creep).
    F3 ships ONLY the located-diagnostics improvement (safe, no behavior change
    to valid programs, self-host fixed point preserved).
  - Gate: existing error cases show `line N:` prefix; 64/64 suite green; fixed point.
  - Dependency: NONE — F3 is independent of F1/F2.

## Green gate (must pass before promotion)
1. `bootstrap/qc-bootstrap-0.0.24 compiler/0.0.25/src/x86/main.quanta compiler/0.0.25/bin/x86/qc_boot`
2. `compiler/0.0.25/bin/x86/qc_boot compiler/0.0.25/src/x86/main.quanta compiler/0.0.25/bin/x86/qc_self`
3. `compiler/0.0.25/bin/x86/qc_self compiler/0.0.25/src/x86/main.quanta compiler/0.0.25/bin/x86/qc`
4. `QC=compiler/0.0.25/bin/x86/qc bash test_suites/scripts/run_tests.sh` → 64/64, 0 fail.
5. Self-host fixed point: `qc_self` (gen1) == `qc` (gen2), byte-identical.
- Fail → roll back this version's source to 0.0.24 base; NEVER declare done without green.

## What is done (inherited)
- x86-only self-hosting compiler (byte-identical fixed point)
- F0: P0 arity fix (function calls with args work)
- F1: `#import`/`#include`/`import` multi-file include
- F2: generics (`id<T>`, `swap<T>`, etc.) compile + run
- Tier-1 optimizer, arena bounds-checks, lexer errors, secure-by-default

## What is NOT done (deferred)
- F4 interpreter (0.0.26)
- ARM64, WASM, JIT, pre-compilation, concurrency, full Unicode, macros
