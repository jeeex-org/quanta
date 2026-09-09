# Quanta .qobj Roadmap — Current Status

VERSION: 0.0.188
Last updated: 2026-09-09

---

## Current State

**Problem**: Quanta imports use textual inclusion. Importing `std/spec_parser` re-lexes, re-parses, and re-IRs `std/json` + `std/str` + `std/vec` + `std/map` + `std/fs`. Deep dependency chains exceed `TOK_CAP`/`IR_CAP` (exit 17).

**Affected modules**: Any stdlib module with >2 levels of transitive deps (e.g., `si_gap_resolver` → `spec_parser` → `json` → `str`).

**Workaround**: Flat imports (no module prefix) work. `si_main` works because it uses `load_gap_specs()` not `spec_parser.load_gap_specs()`.

---

## Phase 1: .qobj Read/Write (DONE)

### What was added

| File | Change |
|------|--------|
| `qobj.quanta` | New file: `qobj_write()`, `qobj_import()` functions |
| `globals.quanta` | Added `emit_qobj` flag |
| `entry.quanta` | Added `--emit-qobj` flag parsing, `qobj_write()` call |
| `main.quanta` | Added `include "qobj.quanta"` |
| `objfmt.quanta` | Modified `imp_load()` to check `.qobj` before `expand_includes()` |

### What works

- `qc --emit-qobj module.quanta module.qobj` creates `.qobj` cache file
- `qobj_import()` loads symbols from `.qobj` file
- `imp_load()` checks for `.qobj` before textual inclusion

### What doesn't work yet

- `.qobj` contains ALL symbols (including from inlined deps), not just the module's own exports
- Token explosion still occurs because source is tokenized BEFORE `.qobj` check
- No IR linking (each module's IR is separate)

---

## Phase 2: Symbol Table Separation (TODO)

### Goal

Track which symbols are owned by the current module vs imported from deps. Write only owned symbols to `.qobj`. When importing, load only owned symbols.

### Changes needed

1. **Add symbol ownership tracking**:
   - During `scanfns()`, mark symbols as `OWNED` (defined in current module) or `IMPORTED` (from deps)
   - Add `sym_owner[]` array (parallel to `symtab[]`)

2. **Modify `qobj_write()`**:
   - Write only `OWNED` symbols to `.qobj`
   - Write only the current module's string table entries

3. **Modify `imp_load()`**:
   - Check `.qobj` BEFORE tokenizing source
   - If `.qobj` exists, load symbols directly (skip `expand_includes()` entirely)
   - If not, fall back to textual inclusion + write `.qobj` after

4. **Add post-compilation `.qobj` emission**:
   - After successful compilation, write `.qobj` for the module
   - This populates cache for future imports

### Estimated effort: 1-2 days

---

## Phase 3: IR Linking (TODO)

### Goal

Compile each module to its own IR stream. Link multiple IR streams together. Resolve cross-module calls.

### Changes needed

1. **Per-module IR**:
   - Each module compiled to separate `ir[]` array
   - Track which IR entries belong to which module

2. **Linker**:
   - Combine per-module IR streams
   - Resolve cross-module call targets
   - Patch relocation entries

3. **Incremental compilation**:
   - Track dirty modules (source changed)
   - Recompile only dirty modules
   - Link all modules

### Estimated effort: 2-3 days

---

## File Changes Summary

| File | Phase 1 | Phase 2 | Phase 3 |
|------|---------|---------|---------|
| `qobj.quanta` | ✅ Added | Modify | Modify |
| `globals.quanta` | ✅ `emit_qobj` flag | `sym_owner[]` | Module IR arenas |
| `entry.quanta` | ✅ `--emit-qobj` flag | Post-compile `.qobj` | Link step |
| `objfmt.quanta` | ✅ `qobj_import()` in `imp_load()` | Skip tokenize if `.qobj` | Symbol resolution |
| `funcscan.quanta` | - | Mark `OWNED` vs `IMPORTED` | - |
| `link.quanta` | - | - | **NEW** IR linker |

---

## Verification Gates

| Gate | Test | Pass Criteria | Status |
|------|------|---------------|--------|
| G1 | `--emit-qobj` creates `.qobj` | File created, readable | ✅ |
| G2 | `qobj_import()` loads symbols | Symbols added to symtab | ✅ |
| G3 | Import with `.qobj` cache | No token explosion | ⏳ |
| G4 | Stale `.qobj` detection | Recompiles when source newer | ⏳ |
| G5 | Cross-module call | Call resolves via `.qobj` | ⏳ |
| G6 | Self-host with `.qobj` | Quanta compiles itself using cached modules | ⏳ |

---

## Conclusion

Phase 1 provides the foundation (`.qobj` read/write). Phases 2-3 are needed for the actual fix. Total remaining effort: ~3-4 days.

Alternative: Document the flat-scope rule and continue building domain cores (blockchain/quantum/math) within current constraints.