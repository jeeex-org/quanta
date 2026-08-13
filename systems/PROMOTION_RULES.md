# Quanta Compiler — Promotion Rules (current, 2026-08-13)

> Supersedes the old `src/qc-X.Y.Z-wip.quanta` / ARM64 dual-arch promotion model.
> Version is the **folder name** (`compiler/<VER>/`); use `<VER>` / `<NEXT>` /
> `<PRIOR>` placeholders — never hard-code a version literal.

## Versioning scheme
- **Dev source (one only):** `compiler/<VER>/src/x86/main.quanta` — all edits here.
  No `-wip` duplicate files. Experiments go in `/tmp` or `temp/`.
- **Binaries (built, mostly intermediate):** `compiler/<VER>/bin/x86/{qc_boot,qc_self,qc}`.
- **Bootstrap seed:** `bootstrap/qc-bootstrap-<PRIOR>` — the **promoted `qc` of the
  previous version**, regenerated each promotion (NOT a fixed historical file).

## Self-host promotion pipeline
The real self-hosting proof is the **final compile** (gen1 → gen2), not just
bootstrap → qc. Three steps:

```
bootstrap (qc-bootstrap-<PRIOR> = last stable)  compiles source →
  qc_boot    (gen 0: built by previous stable)   compiles source →
    qc_self  (gen 1: FIRST self-hosting test)    compiles source →
      qc     (gen 2: built by a self-hosted compiler — the real proof)
```

Concrete for `<VER>=0.0.21`, `<PRIOR>=0.0.20`:
```bash
bootstrap/qc-bootstrap-0.0.20  compiler/0.0.21/src/x86/main.quanta  compiler/0.0.21/bin/x86/qc_boot
compiler/0.0.21/bin/x86/qc_boot  compiler/0.0.21/src/x86/main.quanta  compiler/0.0.21/bin/x86/qc_self
compiler/0.0.21/bin/x86/qc_self  compiler/0.0.21/src/x86/main.quanta  compiler/0.0.21/bin/x86/qc
```

## Gate
Run the suite against the **gen2 `qc`** binary:
```bash
QC=compiler/<VER>/bin/x86/qc bash test_suites/scripts/run_tests.sh   # expect 62/62, 0 fail
```

- **All 62/62 pass** → self-hosting works → **PROMOTE**:
  1. Keep only `qc` (delete `qc_boot` + `qc_self` — intermediates).
  2. Save the promoted `qc` as `bootstrap/qc-bootstrap-<VER>` (becomes the seed
     for `<NEXT>`).
  3. Update `compiler/<VER>/STATE.md` date + `agents/memory/quanta.md` LAST VERIFIED
     STATE; bump `agents/memory/LAST_UPDATED`.
- **Tests FAIL** → self-hosting is NOT working at gen2. Fall back: **`qc = qc_self`**
  (use the gen1 binary — it proved at least one generation of self-hosting), then
  promote `qc_self` as `qc` and save it as `bootstrap/qc-bootstrap-<VER>`.

## Promotion sequence (full, per version bump `<VER>` → `<NEXT>`)
When `<VER>` passes the gate (62/62 on `qc`):

1. **Promote `<VER>`:** keep only `qc` (delete `qc_boot` + `qc_self`); save `qc`
   as `bootstrap/qc-bootstrap-<VER>`.
2. **COMMIT `<VER>`:** commit the promoted folder (source + `qc` + the regenerated
   `bootstrap/qc-bootstrap-<VER>` seed). Message e.g. `Promote Quanta <VER>:
   self-host qc_boot→qc_self→qc, 62/62`. The committed version is frozen.
3. **Create `<NEXT>`:** `mkdir -p compiler/<NEXT>/src/x86 compiler/<NEXT>/bin/x86`.
4. **Copy source from previous stable:** `cp compiler/<VER>/src/x86/main.quanta
   compiler/<NEXT>/src/x86/main.quanta`. (The next version starts from the last
   promoted source — no `-wip` fork.)
5. **STATE.md for `<NEXT>` = `Status: WIP`:** scaffold `compiler/<NEXT>/STATE.md`
   with `Status: WIP` (work-in-progress), version `<NEXT>`, date today. It becomes
   `STABLE` only after `<NEXT>` itself passes the gate and is committed.
6. Continue development in `compiler/<NEXT>/src/x86/main.quanta` until `<NEXT>`
   passes its own pipeline + gate, then repeat this sequence.

> Note: the `WIP` is a **status field inside STATE.md**, not a separate `-wip`
> source file. There is exactly ONE source file per version.

## After promotion (summary)
- Only `qc` is kept in the promoted `<VER>` folder.
- The `<NEXT>` folder is the active work tree (typically uncommitted until it
  passes its own gate).
- The bootstrap seed for `<NEXT>` is `qc-bootstrap-<VER>` (regenerated above).

## Rules
- NEVER edit a promoted `qc` (frozen). All dev in the single `main.quanta`.
- NEVER declare "done"/"fixed" without the gate (62/62 on `qc`) passing.
- Bootstrap is regenerated from each promoted `qc` — not hand-maintained.
