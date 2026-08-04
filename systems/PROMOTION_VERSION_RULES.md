# Versioning, Fix‑Forward, and Promotion Rules

## Versioning scheme
The project follows **Semantic Versioning** `MAJOR.MINOR.PATCH` (e.g. `5.6.4`).

* **MAJOR** – incompatible API or ABI changes.  
* **MINOR** – backward‑compatible feature additions.  
* **PATCH** – backward‑compatible bug fixes.

The version number is reflected in the source file names:

* Stable release: `src/qc-X.Y.Z.quanta`  
* Work‑in‑progress (next version): `src/qc-X.Y.(Z+1)-wip.quanta`

## Never edit the stable source
* The file `src/qc-X.Y.Z.quanta` (the current stable) **must never be modified**.  
* All development, bug‑fixes, and experiments go exclusively into the WIP file `src/qc-X.Y.(Z+1)-wip.quanta`.

## Fix‑forward workflow
1. **Work in WIP** – make changes only in `src/qc-*.wip.quanta`.  
2. **Verify locally** – run the test suite, ensure the x86_64 self‑host fixed point remains byte‑identical, and test on the ARM device (`ai-arm-01`).  
3. **Record measurements** – use **N ≥ 3** runs, report the **median**; never rely on estimates.  
4. **Prepare for promotion** – once all gates pass, the WIP is ready to become the new stable.

## Promotion (`rebuild.sh --promote`)
Running `rebuild.sh --promote` (or the equivalent script) performs the following steps automatically:

1. **Validate** that the WIP binary (`bin/x86_64/qc-X.Y.(Z+1)`) builds successfully and passes the full test suite on both x86_64 and ARM64.  
2. **Confirm** the x86_64 self‑host fixed point is still bit‑identical (stage1 == stage2).  
3. **Promote**  
   * Rename `src/qc-X.Y.(Z+1)-wip.quanta` → `src/qc-X.Y.(Z+1).quanta` (new stable).  
   * Optionally increment the version (e.g. if the change was a MINOR bump, the new stable becomes `X.(Y+1).0`).  
   * Create a fresh WIP file for the next development cycle: `src/qc-X.Y.(Z+2)-wip.quanta` (or appropriate based on version bump).  
4. **Update binaries**
   * Verify architecture: `file temp/qc-X.Y.(Z+1)-stage2 | grep -qi 'x86-64'` or abort.
   * Verify architecture: `file temp/qc-X.Y.(Z+1)-arm64 | grep -qi 'aarch64'` or abort.
   *   promoted x86_64 binary to `bin/x86_64/qc-X.Y.Z`.
   * promoted ARM64 binary to `bin/aarch64/qc-X.Y.Z`.  
   * Adjust the symlink `bin/qc` to point to the latest **x86_64** stable binary (`bin/x86_64/qc-X.Y.Z`).  
5. **Clean temporary artefacts** – the `temp/` directory may be cleared; its contents are not considered part of the repository.  
6. **Commit** the updated source files and any documentation changes (still residing under `systems/`).

## Summary of prohibited actions
* **Do not** edit `src/qc-X.Y.Z.quanta` (the current stable).  
* **Do not** place binaries, object files, or test artefacts in the repository root.  
* **Do not** commit files outside the whitelisted directories (`bin`, `src`, `systems`, `bootstrap`, `temp`, `test_suites`, and `.gitignore`).  
* **Do** keep all Markdown documentation under `systems/`.  

Following these rules guarantees a clean, predictable development flow and ensures the x86_64 baseline never regresses while the ARM64 target is brought to a working self‑host fixed point.