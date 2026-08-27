# Quanta Compiler 0.0.24 — STATE

> Internal status tracker for the compiler build in THIS folder. **Gitignored —
> never committed or pushed.** Deeper SME handoff: `agents/memory/quanta.md`.

## How to read this file
- WIP status of the 0.0.24 build. Read first for current green status.
- Canonical CORE ROADMAP (1-feature-per-version, 0.0.22→0.0.26) lives in
  `compiler/0.0.22/STATE.md`. This file scopes ONLY the 0.0.24 feature.
- `<VER>` = `0.0.24`. `<PRIOR>` = `0.0.23`. `<NEXT>` = `0.0.25`.

## Current state (verify date against `agents/memory/LAST_UPDATED`)
- **Status:** `WIP` (scaffolded from promoted 0.0.23; not yet promoted).
- **Target:** x86-64 ONLY (ARM64 deleted in 0.0.21; clean from-scratch later).
- **Seed for this version:** `bootstrap/qc-bootstrap-0.0.23` (previous stable's `qc`).
- **Self-hosting:** inherited working (0.0.23 promoted with byte-identical fixed point).

## This version's feature (1 ONLY — fix-forward discipline)
- **F2: Fix generics** — make `id<T>(x T)` and similar generic calls actually
  instantiate (monomorphization). Currently `id<T>(x T)` → "wrong argument count"
  (monomorph scaffold `IR_GENERIC_INST` exists but wiring is broken).
  - Gate: a program using a generic fn (e.g. `id(42)` + `id("s")`) compiles + runs.
  - Caveat: generics is the RISKIEST feature — the monomorph path is partially
    wired. If it proves too deep for one version, document the blocker in this
    STATE.md and re-scope (do NOT pile other features on top).
  - Dependency: NONE hidden — F2 is independent of F1.

## Green gate (must pass before promotion)
1. `bootstrap/qc-bootstrap-0.0.23 compiler/0.0.24/src/x86/main.quanta compiler/0.0.24/bin/x86/qc_boot`
2. `compiler/0.0.24/bin/x86/qc_boot compiler/0.0.24/src/x86/main.quanta compiler/0.0.24/bin/x86/qc_self`
3. `compiler/0.0.24/bin/x86/qc_self compiler/0.0.24/src/x86/main.quanta compiler/0.0.24/bin/x86/qc`
4. `QC=compiler/0.0.24/bin/x86/qc bash test_suites/scripts/run_tests.sh` → 64/64, 0 fail.
5. Self-host fixed point: `qc_self` (gen1) == `qc` (gen2), byte-identical.
- Fail → roll back this version's source to 0.0.23 base; NEVER declare done without green.

## What is done (inherited)
- x86-only self-hosting compiler (byte-identical fixed point)
- F0: P0 arity fix (function calls with args work)
- F1: `#import`/`#include`/`import` multi-file include (64/64 includes import_test)
- Tier-1 optimizer, arena bounds-checks, lexer errors, secure-by-default

## What is NOT done (deferred)
- F3 type-checker, F4 interpreter (0.0.25–0.0.26)
- ARM64, WASM, JIT, pre-compilation, concurrency, full Unicode, macros
