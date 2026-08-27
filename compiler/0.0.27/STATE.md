# Quanta Compiler 0.0.27 — STATE

> Internal status tracker for the compiler build in THIS folder. **Gitignored —
> never committed or pushed.** Deeper SME handoff: `agents/memory/quanta.md`.

## How to read this file
- WIP status of the 0.0.27 build. Read first for current green status.
- Canonical CORE ROADMAP (1-feature-per-version, 0.0.22→0.0.30+) lives in
  `compiler/0.0.22/STATE.md`. This file scopes ONLY the 0.0.27 feature.
- `<VER>` = `0.0.27`. `<PRIOR>` = `0.0.26`. `<NEXT>` = `0.0.28`.

## Current state (verify date against `agents/memory/LAST_UPDATED`)
- **Status:** `WIP` (scaffolded from promoted 0.0.26; not yet promoted).
- **Target:** x86-64 ONLY (ARM64 deleted in 0.0.21; clean from-scratch later).
- **Seed for this version:** `bootstrap/qc-bootstrap-0.0.26` (previous stable's `qc`).
- **Self-hosting:** inherited working (0.0.26 promoted with byte-identical fixed point).

## This version's feature (1 ONLY — fix-forward discipline)
- **F5: Option/Result + error handling** — `Option<T>`, `Result<T,E>` types with
  `?` / `try!`-style propagation and exhaustive `match` on `Some`/`None`/`Ok`/`Err`.
  (Builtin Some/None/Ok/Err variants + IR_SOME/IR_NONE already exist in codegen;
  wire them into a usable error-propagation story.) Scope minimally first.
  - Dependency: NONE hidden — F5 is independent of F1/F2/F3/F4.

## Green gate (must pass before promotion)
1. `bootstrap/qc-bootstrap-0.0.26 compiler/0.0.27/src/x86/main.quanta compiler/0.0.27/bin/x86/qc_boot`
2. `compiler/0.0.27/bin/x86/qc_boot compiler/0.0.27/src/x86/main.quanta compiler/0.0.27/bin/x86/qc_self`
3. `compiler/0.0.27/bin/x86/qc_self compiler/0.0.27/src/x86/main.quanta compiler/0.0.27/bin/x86/qc`
4. `QC=compiler/0.0.27/bin/x86/qc bash test_suites/scripts/run_tests.sh` → 64/64, 0 fail.
5. Self-host fixed point: `qc_self` (gen1) == `qc` (gen2), byte-identical.
- Fail → roll back this version's source to 0.0.26 base; NEVER declare done without green.

## What is done (inherited)
- x86-only self-hosting compiler (byte-identical fixed point)
- F0: P0 arity fix | F1: #import | F2: generics | F3: located diagnostics
- F4: tagged unions (`enum`) + `match` (expression arms; enum/wildcard/literal/identifier patterns)
- Tier-1 optimizer, arena bounds-checks, secure-by-default

## What is NOT done (deferred)
- F4 block arms (`1 => { ... }`) — documented limitation (block-value plumbing)
- F5 Option/Result + error handling (THIS version, WIP)
- F6 allocator+defer, F7 comptime+reflection, F8 package/build+C interop
- Interpreter, ARM64, WASM, JIT, concurrency, full Unicode, macros
