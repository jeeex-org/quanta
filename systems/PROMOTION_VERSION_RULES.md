# Quanta Compiler — Versioning, Fix-Forward & Promotion (current, 2026-08-13)

> Supersedes the old Semantic-Versioning + `src/qc-X.Y.Z-wip.quanta` model.
> Version is the **folder name**; all version references are dynamic
> (`<VER>` / `<NEXT>` / `<PRIOR>`). Never hard-code a version literal anywhere.

## Versioning scheme
- Version = `compiler/<VER>/` folder name (e.g. `0.0.21`). Next: `0.0.22`,
  `0.0.23`, … by incrementing the patch. Major/minor bumps use `X.Y.0` form when
  ABI/API changes warrant it, but the mechanism is identical: a new folder.
- **Single dev source:** `compiler/<VER>/src/x86/main.quanta`. No `-wip` files,
  no separate stable/WIP split. Experiments live in `/tmp` or `temp/`.

## Never edit a promoted artifact
- A promoted `qc` (and its `qc-bootstrap-<VER>` seed) is **frozen**.
- All development goes in the single `main.quanta` of the current `<VER>` folder.
- If you must fix the *bootstrap* itself (e.g. an ELF-layout bug), the fix lands
  in `main.quanta`, is promoted through the pipeline, and the promoted `qc` becomes
  the new `qc-bootstrap-<VER>`. There is no separate "stable source" to patch.

## Fix-forward workflow
1. **Work in the dev source** — `compiler/<VER>/src/x86/main.quanta` only.
2. **Verify locally** — run the self-host promotion pipeline (qc_boot → qc_self →
   qc) and the test suite on `qc`.
3. **Record measurements** — real tool output, not estimates. The gate is
   binary: 62/62 pass on `qc` or it does not promote.
4. **Promote** once the gate passes (see PROMOTION_RULES.md for the full chain).

## Promotion
Promotion = the successful completion of the 3-step self-host chain + 62/62 gate:
1. `qc_boot` (bootstrap) → `qc_self` (gen1) → `qc` (gen2, the real proof).
2. Suite passes on `qc` → keep only `qc`; delete `qc_boot` + `qc_self`.
3. Save `qc` as `bootstrap/qc-bootstrap-<VER>` (seed for `<NEXT>`).
4. **COMMIT `<VER>`** (source + `qc` + regenerated seed) — frozen.
5. **Scaffold `<NEXT>`:** create `compiler/<NEXT>/`, `cp` the source from `<VER>`,
   and set `compiler/<NEXT>/STATE.md` → `Status: WIP`. `<NEXT>` is the active work
   tree until it passes its own gate, then repeats this sequence.
6. On gate failure: fall back to `qc = qc_self` and promote that.

## No script magic required
The pipeline is a fixed 3-command chain (documented in PROMOTION_RULES.md and
STATE.md). A `rebuild.sh`/promote script is optional; the convention is the source
of truth. If a script is added later, it must reproduce exactly the qc_boot →
qc_self → qc chain and the gen2 gate — not the old `-wip` flow.
