# Quanta Compiler 0.0.23 — STATE

> Internal status tracker for the compiler build in THIS folder. **Gitignored —
> never committed or pushed.** Deeper SME handoff: `agents/memory/quanta.md`.

## How to read this file
- This is the **WIP** status of the 0.0.23 build. Read it first for current green status.
- Canonical CORE ROADMAP (1-feature-per-version, 0.0.22→0.0.26) lives in
  `compiler/0.0.22/STATE.md` (and `agents/memory/quanta.md`). This file scopes
  ONLY the 0.0.23 feature.
- `<VER>` = `0.0.23` (this folder). `<PRIOR>` = `0.0.22`. `<NEXT>` = `0.0.24`.

## Current state (verify date against `agents/memory/LAST_UPDATED`)
- **Status:** `WIP` (scaffolded from promoted 0.0.22; not yet promoted).
- **Version:** `0.0.23` (this folder name).
- **Target:** x86-64 ONLY (ARM64 backend deleted in 0.0.21; clean from-scratch later).
- **Seed for this version:** `bootstrap/qc-bootstrap-0.0.22` (previous stable's `qc`).
- **Self-hosting:** inherited working (0.0.22 promoted with byte-identical fixed point).

## This version's feature (1 ONLY — fix-forward discipline)
- **F1: Fix `#import`** — make `#import "file"` (and `#include "file"`) inline the
  referenced source, same flat-global semantic as the existing `include` directive
  (confirmed working post-F0). Currently `#import` → "call to undeclared function".
  - Gate: a 2-file program using `#import` compiles + runs (prints expected).
  - Reuse: extend `expand_includes` directive detection to accept `import`/`#import`
    (and `#include`) — the loader body already exists for `include`.
  - Dependency: NONE hidden — `include` path is proven working. F1 is isolated.

## Green gate (must pass before promotion)
1. `bootstrap/qc-bootstrap-0.0.22 compiler/0.0.23/src/x86/main.quanta compiler/0.0.23/bin/x86/qc_boot`
2. `compiler/0.0.23/bin/x86/qc_boot compiler/0.0.23/src/x86/main.quanta compiler/0.0.23/bin/x86/qc_self`
3. `compiler/0.0.23/bin/x86/qc_self compiler/0.0.23/src/x86/main.quanta compiler/0.0.23/bin/x86/qc`
4. `QC=compiler/0.0.23/bin/x86/qc bash test_suites/scripts/run_tests.sh` → 63/63, 0 fail.
5. Self-host fixed point: `qc_self` (gen1) == `qc` (gen2), byte-identical.
- Fail → roll back this version's source to 0.0.22 base; NEVER declare done without green.

## What is done (inherited from 0.0.22)
- x86-only self-hosting compiler (byte-identical fixed point)
- F0: P0 arity fix — function calls with args work (63/63 includes func_call_args)
- Tier-1 optimizer ON by default
- Arena bounds-checks + lexer error reporting
- Secure-by-default (overflow/bounds traps)
- Basic semantic errors (undeclared fn/var/arity)

## What is NOT done (deferred — see roadmap)
- F2 generics, F3 type-checker, F4 interpreter (0.0.24–0.0.26)
- ARM64, WASM, JIT, pre-compilation, concurrency, full Unicode, macros
