# Quanta Compiler 0.0.26 — STATE

> Internal status tracker for the compiler build in THIS folder. **Gitignored —
> never committed or pushed.** Deeper SME handoff: `agents/memory/quanta.md`.

## How to read this file
- WIP status of the 0.0.26 build. Read first for current green status.
- Canonical CORE ROADMAP (1-feature-per-version, 0.0.22→0.0.30+) lives in
  `compiler/0.0.22/STATE.md`. This file scopes ONLY the 0.0.26 feature.
- `<VER>` = `0.0.26`. `<PRIOR>` = `0.0.25`. `<NEXT>` = `0.0.27`.

## Current state (verify date against `agents/memory/LAST_UPDATED`)
- **Status:** `WIP` (scaffolded from promoted 0.0.25; not yet promoted).
- **Target:** x86-64 ONLY (ARM64 deleted in 0.0.21; clean from-scratch later).
- **Seed for this version:** `bootstrap/qc-bootstrap-0.0.25` (previous stable's `qc`).
- **Self-hosting:** inherited working (0.0.25 promoted with byte-identical fixed point).

## This version's feature (1 ONLY — fix-forward discipline)
- **F4: Tagged unions + pattern matching** — sum types with exhaustive `match`.
  Enables safe discriminated unions (Rust `enum`, Zig `union(Tag)`, Odin `union`).
  - Scope: `type T = A | B(int) | C(string)` + `match x { A => .., B(n) => .. }`
    with exhaustiveness check (compile error if a variant is missing).
  - This is a LARGE feature (new type kind, IR, codegen for tagged union layout,
    match lowering, exhaustiveness analysis). Scope it to a MINIMAL working
    subset first (e.g. 2-3 variants, int payloads) and grow.
  - Dependency: NONE hidden — F4 is independent of F1/F2/F3.

## Green gate (must pass before promotion)
1. `bootstrap/qc-bootstrap-0.0.25 compiler/0.0.26/src/x86/main.quanta compiler/0.0.26/bin/x86/qc_boot`
2. `compiler/0.0.26/bin/x86/qc_boot compiler/0.0.26/src/x86/main.quanta compiler/0.0.26/bin/x86/qc_self`
3. `compiler/0.0.26/bin/x86/qc_self compiler/0.0.26/src/x86/main.quanta compiler/0.0.26/bin/x86/qc`
4. `QC=compiler/0.0.26/bin/x86/qc bash test_suites/scripts/run_tests.sh` → 64/64, 0 fail.
5. Self-host fixed point: `qc_self` (gen1) == `qc` (gen2), byte-identical.
- Fail → roll back this version's source to 0.0.25 base; NEVER declare done without green.

## What is done (inherited)
- x86-only self-hosting compiler (byte-identical fixed point)
- F0: P0 arity fix (function calls with args work)
- F1: `#import`/`#include`/`import` multi-file include
- F2: generics (`id<T>`, `swap<T>`, etc.) compile + run
- F3: located diagnostics (`line N:` prefix on compile errors)
- Tier-1 optimizer, arena bounds-checks, secure-by-default

## What is NOT done (deferred)
- F4 tagged unions + pattern matching (THIS version, WIP)
- F5 Option/Result + error unions, F6 allocator+defer, F7 comptime+reflection,
  F8 package/build+C interop
- Interpreter, ARM64, WASM, JIT, concurrency, full Unicode, macros
