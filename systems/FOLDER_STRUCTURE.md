# Quanta Project Folder Structure

## Root Directory (`/opt/tali/quanta/`)

- `src/` -- compiler source files (stable: `src/qc-0.0.13.quanta` **never edit stable**; active WIP: `src/qc-0.0.14-wip.quanta`)
- `bin/` -- compiler binaries
  - `bin/aarch64/` -- ARM64 based compiler binaries only
  - `bin/x86_64/` -- x86_64 based compiler binaries only
- `docs/` -- public documentation (e.g., `SYNTAX.md`)
- `systems/` -- internal system documentation and related markdown files
  - Contains all `.md` files (e.g., `FOLDER_STRUCTURE.md`, `DEVICES.md`, `ROADMAP.md`, etc.)
- `temp/` -- temporary test scripts and binaries; **clean up after each promotion**, do not save permanent files
- `test_suites/` -- test suite
  - `test_suites/bin/` -- binary output from `test_suites/codes`
  - `test_suites/codes` -- test source code files (.quanta)
  ## Git Tracking Rules

  |

  **Only these directories are tracked in git (per `.gitignore` whitelist):**
  - `bin/` — compiler binaries (versioned, promoted)
  - `src/` — compiler source files (stable, WIP, bootstrap)
  - `docs/` — public documentation (`SYNTAX.md`)
  - `bootstrap/` — original bootstrap binary
  - `.gitignore` — the ignore file itself

  |

  **Explicitly NOT tracked (local only):**
  - `systems/` — internal documentation, rules, roadmaps
  - `test_suites/` — test source codes, compiled binaries, scripts
  - `temp/` — build artifacts (cleaned on promotion)
  - Root-level `.md` files — **except** `README.md` which is explicitly allowed

1. **No binaries or object files** in the repository root (`/opt/tali/quanta/`).
2. **All `.md` files** must reside under `systems/` (internal) or `docs/` (public).
3. **`temp/`** is for ephemeral files; its contents may be deleted at any time.
4. **Binaries** belong strictly in `bin/aarch64/` or `bin/x86_64/` according to target architecture.
5. **Source code** lives exclusively in `src/`.
6. **Test suite** follows the `test_suites/` subdivision as described.
7. When promoting a new version, clear `temp/` and rebuild binaries into the appropriate `bin/` subdirectories.
8. **Git commits** must only include whitelisted paths; `systems/` and `test_suites/` are local-only.

## 9. Root Directory Protection (NEW)

**NO files may be created directly in the project root (`/opt/tali/quanta/`).**
- Only the whitelisted directories/files are allowed in root: `src/`, `bin/`, `docs/`, `systems/`, `temp/`, `test_suites/`, `bootstrap/`, `.gitignore`, `README.md`, `.git/`
- All new files, scripts, binaries, logs, test outputs MUST go into appropriate subdirectories (`temp/`, `bin/`, `test_suites/`, etc.)
- Any accidental root-level files are considered build artifacts and will be deleted

## 10. WIP Lifecycle

**Only ONE WIP file exists at any time — always the next unreleased version.**

- **Active WIP:** `src/qc-X.Y.Z-wip.quanta` (version being worked on, `-wip` suffix)
- **Stable:** `src/qc-X.Y.Z.quanta` (promoted, sealed — version only, no suffix)
- **On promotion:** the `-wip` file is **DELETED**; the stable file is the new baseline
- **After promotion:** there is **no WIP file** until work on the next version begins
- **When next-version work starts:** a fresh `src/qc-(X+1).Y.Z-wip.quanta` is created (version bumped)
- **No stale WIPs:** never recreate a WIP for an already-promoted version
- Bootstrap file (`bootstrap/qc-0.0.0.quanta`) is immutable and never promoted

## 11. Fix Forward

**NEVER edit a stable/promoted source file. All fixes and changes go into the current WIP.**

- Stable files (`src/qc-X.Y.Z.quanta`) are **sealed** — they represent released, verified versions
- If a bug is found in stable: fix it in the current WIP (the next version), never in the stable source
- The WIP absorbs the fix, gets verified (self-host + test gates + devices), then is promoted — the bug is **fixed forward** into the next release
- The only exception is the bootstrap file (`bootstrap/qc-0.0.0.quanta`) — immutable, never modified