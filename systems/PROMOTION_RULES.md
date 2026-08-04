# Quanta Compiler Promotion Rules

## Versioning Scheme
- **Stable**: `src/qc-X.Y.Z.quanta` — promoted, frozen, no changes allowed
- **WIP**: `src/qc-X.Y.(Z+1)-wip.quanta` — active development, all changes here
- **Bootstrap**: `src/qc-X.Y.(Z-1).quanta` — previous stable, used to build new stable
- **Binary**: `bin/{x86_64,aarch64}/qc-X.Y.Z` — promoted compiler binaries

## Current state (2026-08-04)

> Snapshot of where the project stands today. The generic workflow below is unchanged.

- **Stable (frozen)**: `src/qc-0.0.13.quanta` (P9)
- **WIP (active)**: `src/qc-0.0.14-wip.quanta` (P10) — current focus is P10 generics; `for-in` support is **done**
- **Bootstrap binary**: `bin/x86_64/qc-0.0.13` is the gsz-patched bootstrap; `bin/aarch64/` holds ARM64 binaries
- **Symlink**: `bin/qc -> x86_64/qc-0.0.13`
- **Promotion mechanics**: a promotion flips `src/qc-X.Y.(Z+1)-wip.quanta` → new stable, creates the next `-wip`, updates `bin/x86_64/qc-X.Y.(Z+1)` + `bin/aarch64`, and flips the `bin/qc` symlink
- **Fix-forward workflow**: new feature/bug development happens in `-wip` and moves forward only
- **Bootstrap integrity exceptions**: per the gsz BSS fix (`7421bbb`), a bootstrap bug-fix is NOT just a WIP change — because ELF layout comes from the compiler that RUNS `write_elf`, an integrity fix touches the **stable source + binary as a pair** (both `src/qc-0.0.13.quanta` and `bin/x86_64/qc-0.0.13` rebuilt together). Such fixes are the one carve-out to the "stable is frozen" rule.

## Promotion Workflow

### 1. Development Phase (WIP Only)
```
All edits → src/qc-X.Y.(Z+1)-wip.quanta
```
- Never edit stable source (`src/qc-X.Y.Z.quanta`)
- Never edit bootstrap source
- Cross-compile tests use promoted stable compiler (`bin/x86_64/qc-X.Y.Z`)
- Self-host tests use WIP-built compiler (stored in `temp/`)

### 2. Verification Phase (Temporary Artifacts in `temp/`)
```bash
# Build artifacts go to temp/
temp/
  qc-X.Y.(Z+1)-stage1    # bootstrap → WIP
  qc-X.Y.(Z+1)-stage2    # stage1 → WIP
  qc-X.Y.(Z+1)-stage3    # stage2 → WIP (fixed-point check)
  qc-X.Y.(Z+1)-arm64     # cross-compiled ARM64 binary for device testing
  *.quanta               # test files
```

**Required Gates:**
1. x86_64 self-host fixed-point: `stage2` == `stage3` (byte-identical)
2. ARM64 cross-compile succeeds
3. ARM64 device test suite passes **(ALL tests must match x86_64 expected results)**
4. x86_64 test suite passes
5. 3-char function regression test passes (5 runs, median)

### 3. Promotion Phase
```bash
# 1. Promote WIP source to new stable
mv src/qc-X.Y.(Z+1)-wip.quanta src/qc-X.Y.(Z+1).quanta

# 2. Promote verified binaries (architecture-checked)
file temp/qc-X.Y.(Z+1)-stage2 | grep -qi 'x86-64'   || { echo "ERROR: stage2 is not x86-64"; exit 1; }
file temp/qc-X.Y.(Z+1)-arm64  | grep -qi 'aarch64'   || { echo "ERROR: arm64 binary is not AArch64"; exit 1; }
cp temp/qc-X.Y.(Z+1)-stage2 bin/x86_64/qc-X.Y.(Z+1)
cp temp/qc-X.Y.(Z+1)-arm64  bin/aarch64/qc-X.Y.(Z+1)

# 3. Create fresh WIP for next cycle
cp src/qc-X.Y.(Z+1).quanta src/qc-X.Y.(Z+2)-wip.quanta

# 4. Clean ALL temp artifacts
rm -rf temp/*

# 5. Update symlink
ln -sf x86_64/qc-X.Y.(Z+1) bin/qc
```

### 4. Post-Promotion Rules
- **Stable source is frozen**: No edits to `src/qc-X.Y.(Z+1).quanta` ever
- **Promoted binaries are frozen**: No rebuilds of `bin/*/qc-X.Y.(Z+1)`
- **All new work**: Goes to `src/qc-X.Y.(Z+2)-wip.quanta` only
- **Bootstrap preserved**: `src/qc-X.Y.Z.quanta` + `bin/*/qc-X.Y.Z` unchanged for next cycle

## Directory Structure (Enforced by .gitignore)

```
quanta/
├── bin/
│   ├── x86_64/
│   │   ├── qc-X.Y.Z          # promoted stable binaries
│   │   └── qc                # symlink to current stable
│   └── aarch64/
│       └── qc-X.Y.Z
├── src/
│   ├── qc-X.Y.Z.quanta       # stable (frozen)
│   ├── qc-X.Y.(Z+1)-wip.quanta  # WIP (active)
│   └── qc-X.Y.(Z-1).quanta   # bootstrap (frozen)
├── temp/                     # ALL build artifacts, cleaned on promotion
├── test_suites/
│   ├── codes/                # test source files
│   ├── bin/                  # compiled test binaries (x86_64)
│   │   └── arm64/            # compiled test binaries (ARM64)
│   ├── scripts/
│   └── EXPECTED.tsv
├── systems/                  # ALL documentation (.md files)
├── bootstrap/
│   └── qc-bootstrap-0.0.0    # original bootstrap binary
└── .gitignore                # whitelists: bin/, src/, docs/, bootstrap/, temp/
```

## Build Artifact Rules

| Artifact Type | Location | Lifetime |
|--------------|----------|----------|
| Stage binaries (stage1,2,3) | `temp/` | Until promotion, then **deleted** |
| Cross-compiled ARM64 binary | `temp/` | Until promotion, then **deleted** |
| Test binaries (x86_64) | `test_suites/bin/` | Persistent |
| Test binaries (ARM64) | `test_suites/bin/arm64/` | Persistent |
| Promoted compiler binaries | `bin/x86_64/`, `bin/aarch64/` | Permanent (versioned) |
| `out.exe` (compiler output) | Project root | Temporary, cleaned before each build |
| Compiler self-build output | `temp/` | Until promotion, then **deleted** |

## Version Bump Rules

| Change Type | Version Bump |
|-------------|--------------|
| Bug fix (like 3-char fn name) | PATCH: X.Y.Z → X.Y.(Z+1) |
| New feature (backend, syntax) | MINOR: X.Y.Z → X.(Y+1).0 |
| Breaking change / self-host milestone | MAJOR: X.Y.Z → (X+1).0.0 |

## Enforcement

- `.gitignore` whitelists only: `bin/`, `src/`, `docs/`, `bootstrap/`, `.gitignore`
- `temp/` is **always ignored** and **always cleaned** on promotion
- No `.md` files in root or `docs/` — all docs in `systems/`
- Test binaries in `test_suites/bin/` and `test_suites/bin/arm64/`
- Source code **exclusively** in `src/`

## Example: 0.0.1 → 0.0.2 Promotion (Completed)

```
Before:
  src/qc-0.0.1.quanta          (bootstrap, frozen)
  src/qc-0.0.2-wip.quanta      (WIP with fix)
  temp/qc-0.0.2-stage1,2,3     (verification artifacts)
  temp/qc-0.0.2-arm64          (ARM64 test binary)

After:
  src/qc-0.0.1.quanta          (bootstrap, preserved)
  src/qc-0.0.2.quanta          (NEW stable, frozen)
  src/qc-0.0.3-wip.quanta      (NEW WIP, active)
  bin/x86_64/qc-0.0.2          (promoted)
  bin/aarch64/qc-0.0.2         (promoted)
  bin/qc -> x86_64/qc-0.0.2    (symlink)
  temp/                        (EMPTY)
```