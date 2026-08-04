# Proposal: Folder-Based Versioning + Architecture Split

## Status
**DRAFT** — awaiting approval to implement as first step of 0.0.8-wip

---

## Problem Statement

The current single-file `qc-X.Y.Z.quanta` with `if target_arch == 1` branches has caused:
1. **ARM64 regressions**: `_start` ABI flip-flop, `e_type` confusion, register allocator collisions
2. **Unmaintainable code**: 3,700+ lines with architecture logic interleaved
3. **Bootstrap fragility**: One bug in shared code breaks both targets
4. **No clean promotion**: Manual file renames, stray binaries in project root

---

## Proposed Solution

### 1. Folder-Based Versioning

```
src/
├── 0.0.7/                 # STABLE (promoted, immutable)
│   ├── common.quanta
│   ├── x86_64.quanta
│   ├── arm64.quanta
│   └── qc-main.quanta
├── 0.0.8-wip/             # WIP (single active development folder)
│   ├── common.quanta
│   ├── x86_64.quanta
│   ├── arm64.quanta
│   └── qc-main.quanta
├── build.sh               # Concatenates version → single .quanta for bootstrap
└── bootstrap.quanta       # Symlink to latest stable concatenated output
```

### 2. Architecture Split (per version folder)

| File | Responsibility |
|------|----------------|
| `common.quanta` | Lexer, parser, AST, IR definitions, typechecker, vtable logic, ELF skeleton (phdrs, sections, write_elf framework) |
| `x86_64.quanta` | x86_64 codegen, register allocator, calling convention, `_start` (stack argc/argv), syscall ABI |
| `arm64.quanta` | ARM64 codegen, register allocator, calling convention, `_start` (stack argc/argv), syscall ABI, static-PIE ELF quirks |
| `qc-main.quanta` | Pipeline driver: imports common + target arch, orchestrates passes, CLI flags |

### 3. Build Script (`src/build.sh`)

```bash
#!/bin/bash
# Usage: ./build.sh [version]  →  prints path to concatenated .quanta
VER="${1:-0.0.8-wip}"
OUT="/tmp/qc-${VER}.quanta"
cat src/${VER}/common.quanta \
    src/${VER}/x86_64.quanta \
    src/${VER}/arm64.quanta \
    src/${VER}/qc-main.quanta \
    > "${OUT}"
echo "${OUT}"
```

### 4. Bootstrap Flow

```bash
# 1. Build stable compiler (once)
./bin/x86_64/qc-0.0.6-fixed $(src/build.sh 0.0.7) bin/x86_64/qc-0.0.7

# 2. Compile WIP using stable
./bin/x86_64/qc-0.0.7 $(src/build.sh 0.0.8-wip) /tmp/qc-0.0.8

# 3. Cross-compile ARM64 WIP
./bin/x86_64/qc-0.0.7 --target=arm64 $(src/build.sh 0.0.8-wip) bin/aarch64/qc-0.0.8
```

---

## Migration Plan (0.0.8-wip First Steps)

| Step | Action | Verification |
|------|--------|--------------|
| 1 | Create `src/0.0.8-wip/` with 4 split files (extracted from `qc-0.0.7-wip.quanta`) | `diff` concatenated output vs original |
| 2 | Write `src/build.sh` | Produces byte-identical `.quanta` to current WIP |
| 3 | Compile with `qc-0.0.6-fixed` → `/tmp/qc-0.0.8` | x86_64: `simple.quanta` → exit 42 |
| 4 | Cross-compile ARM64 → `bin/aarch64/qc-0.0.8` | Device: `simple.quanta` → exit 0, `arithmetic.quanta` → exit 30 |
| 5 | **Only then**: implement trait field access, generics, etc. | All 6 test gates pass on both archs |

---

## Rules Update (Add to `systems/FOLDER_STRUCTURE.md`)

```markdown
## Versioning & Source Layout

- **Stable versions**: `src/X.Y.Z/` (immutable after promotion)
- **WIP version**: `src/X.Y.Z-wip/` (exactly one at any time)
- **Promotion**: `mv src/X.Y.Z-wip src/X.Y.Z` (atomic, no file rewrites)
- **Bootstrap input**: Concatenated via `src/build.sh <version>` → `/tmp/qc-<version>.quanta`
- **Binaries**: `bin/x86_64/qc-X.Y.Z`, `bin/aarch64/qc-X.Y.Z`
- **No loose .quanta files** in `src/` root
- **No binaries** in project root (enforced by .gitignore)
```

---

## Benefits

| Dimension | Before | After |
|-----------|--------|-------|
| ARM64 bugs | Frequent (shared logic) | Isolated to `arm64.quanta` |
| Adding RISC-V | Touch 3,700-line file | Add `riscv64.quanta` to each version |
| Promotion risk | Manual rename + verify | Folder `mv` (atomic) |
| Code review | Hard (arch mixed) | Per-arch diffs |
| Onboarding | Read 3,700 lines | Read `common` + one arch |

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Concatenation breaks bootstrap | `build.sh` output byte-compared to current WIP before switch |
| Module imports not yet in language | Build-time concatenation is temporary; proper modules come after generics |
| Two copies of common code (stable + WIP) | Acceptable — `common.quanta` diverges slowly; `diff` on promotion catches drift |

---

## Decision Required

**Approve** to begin 0.0.8-wip with this structure. First commit = split files + build.sh + verification that concatenated output matches current `qc-0.0.7-wip.quanta` byte-for-byte.

No new features until ARM64 native execution passes all 6 test gates (N≥3, median reported).