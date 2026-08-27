# Quanta Compiler — STATE

> Internal status tracker for the compiler build in THIS folder. **Gitignored —
> never committed or pushed.** The deeper SME handoff + changelog is in
> `agents/memory/quanta.md` (also gitignored, machine-local). Keep the two in sync.

## How versioning works (DYNAMIC — do not hard-code literals)
- The version is the **folder name**: this file lives in `compiler/<VER>/`
  (e.g. `compiler/0.0.21/` → version `0.0.21`). The next versions are
  `0.0.22`, `0.0.23`, … — derived by incrementing the patch number.
- **Never write a hard-coded `0.0.21` / `qc-0.0.22` anywhere that should track
  the current version.** Use `<VER>` and let the folder name be the source of
  truth. When the version advances, create `compiler/<NEXT>/` and move the dev
  source there; update this block's "Current state" date, not the version literal.

## Current state (verify date below against `agents/memory/LAST_UPDATED`)
- **Status:** `STABLE` (promoted, frozen). A newly scaffolded next version is `WIP`.
- **Version:** `<VER>` = the name of this folder (`basename $(dirname $PWD)`)
- **Target:** x86-64 ONLY (ARM64 backend deleted — clean from-scratch rewrite is a future stage)
- **Dev source:** `compiler/<VER>/src/x86/main.quanta` (single self-hosting file)
- **Built binary (kept):** `compiler/<VER>/bin/x86/qc`
- **Bootstrap seed:** `bootstrap/qc-bootstrap-<PRIOR>` (x86-only; `<PRIOR>` = previous
  promoted version, e.g. `0.0.20` for `0.0.21`). The bootstrap is **regenerated
  each promotion**: the promoted `qc` of version N becomes `qc-bootstrap-<N>` used
  to build N+1. It is NOT a fixed historical file.

## Self-host promotion pipeline (DYNAMIC — the real self-hosting test)
Building version `<VER>` from bootstrap `qc-bootstrap-<PRIOR>` is a 3-step chain.
The **real self-hosting proof** is the final step (gen1 → gen2), not just
bootstrap → qc.

```
bootstrap (qc-bootstrap-<PRIOR>, = last stable)   compiles source →
  qc_boot      (gen 0: built by previous stable)   compiles source →
    qc_self    (gen 1: FIRST self-hosting test)    compiles source →
      qc       (gen 2: built by a self-hosted compiler — the real proof)
```

Concrete (for `<VER>=0.0.21`, `<PRIOR>=0.0.20`):
1. `bootstrap/qc-bootstrap-0.0.20  compiler/0.0.21/src/x86/main.quanta  compiler/0.0.21/bin/x86/qc_boot`
2. `compiler/0.0.21/bin/x86/qc_boot  compiler/0.0.21/src/x86/main.quanta  compiler/0.0.21/bin/x86/qc_self`
3. `compiler/0.0.21/bin/x86/qc_self  compiler/0.0.21/src/x86/main.quanta  compiler/0.0.21/bin/x86/qc`

**Gate:** run `bash test_suites/scripts/run_tests.sh` against `qc` (the gen2 binary).
- **All 62/62 pass** → self-hosting works → **promote**: keep only `qc`
  (delete `qc_boot` + `qc_self` — they are intermediates). Save the promoted `qc`
  as `bootstrap/qc-bootstrap-<VER>` for the next version.
- **Tests FAIL** → self-hosting is NOT working at gen2. Fall back: **`qc = qc_self`**
  (use the gen1 binary, which at least proved one generation of self-hosting),
  then promote `qc_self` as `qc`. Save `qc` as `bootstrap/qc-bootstrap-<VER>`.
- After promotion, **only `qc` is kept** for the version. `qc_boot` is rebuilt from
  the previous bootstrap next time; `qc_self` was just the first self-hosting test.

> Legacy note: the `qc` / `qc_self` currently in `bin/x86/` predate this pipeline
> (qc_self was built before the current source; no qc_boot exists). They pass
> 62/62 but do NOT satisfy the 3-step chain above. Regenerate via this pipeline
> at the next promotion.

## Workflow (replaces the old `-wip` file convention)
- ONE dev source only: `compiler/<VER>/src/x86/main.quanta`. No floating
  `qc-X.Y.Z-wip.quanta` files. Experiments go in `/tmp` or `temp/`.
- State is tracked HERE (`STATE.md`), not by filename.
- **Promotion / version bump:** apply the Self-host promotion pipeline above to
  build `compiler/<NEXT>/` from `compiler/<VER>/`. Copy the dev source into
  `compiler/<NEXT>/`, then run the 3-step chain + gate. Update this block's date.
- **Every change MUST pass the green gate** (the pipeline + 62/62 on `qc`). If it
  fails, roll back to the last promoted `qc`.

## What is done
- x86-only self-hosting compiler (byte-identical fixed point)
- Tier-1 optimizer ON by default (const-fold, DCE, tail-call, loop strength-reduction)
- Arena bounds-checks + lexer error reporting
- Secure-by-default (overflow/bounds traps)
- 62/62 test_suites

## What is NOT done (open)
- Interpreter (`--interp`): designed, NOT landed
- Pre-compilation (`go run` style): not started
- WebAssembly backend: not started
- ARM64 backend: deleted; clean from-scratch rewrite is a future stage (NOT derived from prior)
- JIT: not started
- `#import` / module system: NOT functional — blocks the modular `core/scan/parse/ir/opt/codegen/run/` tree
- Modular source split: design target, blocked on `#import`
