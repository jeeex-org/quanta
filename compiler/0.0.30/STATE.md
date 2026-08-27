# Quanta Compiler 0.0.30 — STATE

> Internal status tracker for the compiler build in THIS folder. **Gitignored —
> never committed or pushed.** Deeper SME handoff: `agents/memory/quanta.md`.

## How to read this file
- Status: WIP | GREEN | BLOCKED — current build state for THIS version only.
- Scope: the single feature being added in this WIP version (one feature per WIP
  version — see project discipline rule).
- Promotion: when GREEN (self-host + all test_suites pass), save
  `qc` as `bootstrap/qc-bootstrap-<VER>`, copy this source to
  `src/qc-<VER>.quanta`, commit, and scaffold the next WIP version.

## Status: WIP
## Feature: F8 — package/build system + C-interop (extern "C")

### Scope (this version)
- [ ] `extern "C"` function declarations + call C symbols (FFI)
- [ ] `#import` of local modules / package paths (F1 already does single-file import)
- [ ] build system: object-mode `--emit-obj` + linker for multi-TU (P5.1 already
      has `--emit-obj`/`--no-start` flags and named-global relocations — wire FFI)

### Notes
- P5.1 cross-TU data globals (`global`/`extern "C" global`) already implemented
  in scanner + ELF emitter. F8 reuses that for C-interop data.
- Function-level `extern "C"` (calling external C functions) is the main gap.
- Self-host status of 0.0.30: NOT YET VERIFIED (scaffolded from 0.0.29).

### Known limitations carried from prior versions
- F4: `match` block arms (`1 => { ... }`) not supported (expression arms only).
- F5: `?` operator does unwrap, NOT error propagation (early-return on Err).
- F7: `const` supports literal arithmetic + const-refs only (no function calls in
      const expressions; no const arrays/structs).
