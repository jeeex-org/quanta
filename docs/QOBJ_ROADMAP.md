# Quanta .qobj Roadmap — Full Module System

Consolidated from compiler audit (`compiler/0.0.184/src/x86/`). VERSION 0.0.184. All artifacts in workspace `docs/`. Target: replace textual `include` with binary `.qobj` module system.

---

## Part A — Extension/Replacement of Existing Components

### A1. Symbol Table (objfmt.quanta)

**Current**: In-memory only. `p5_add_symbol_b()`, `STB_GLOBAL`, `STB_LOCAL`, `UNDEF`. Single-TU scope.

**Extension needed**:

| Change | What | Why |
|---|---|---|
| Add export flag | `symtab[idx].st_flags |= STF_EXPORTED` | Mark symbols visible to other modules |
| Add serialization | `qobj_write_symtab(fd, symtab, symcount)` | Write symtab + strtab to `.qobj` |
| Add deserialization | `qobj_read_symtab(fd)` | Load symtab from `.qobj` |
| Add merge | `qobj_merge_symtabs(base, imported)` | Merge imported module's exports into current TU |

**Location**: `objfmt.quanta` — extend existing `p5_*` functions with `qobj_*` variants.

**Effort**: Low. Structure exists, just add I/O.

---

### A2. Relocation Records (objfmt.quanta)

**Current**: x86-64 specific. `p5_add_reloc()`, `R_X86_64_PLT32`. Single-TU scope.

**Extension needed**:

| Change | What | Why |
|---|---|---|
| Generic relocation format | `qobj_reloc { offset, type, symidx, addend }` | Arch-neutral, works for x86/ARM/GPU |
| Cross-TU relocation | `qobj_add_extern_reloc(sym_name)` | Reference symbol defined in another module |
| Relocation serialization | `qobj_write_relocs(fd, relocs, count)` | Write to `.qobj` |
| Relocation merge | `qobj_merge_relocs(base, imported, offset_adjust)` | Combine relocations from multiple modules |

**Location**: `objfmt.quanta` — extend `p5_add_reloc` with `qobj_*` variants.

**Effort**: Low. Structure exists, generalize the format.

---

### A3. IR Opcodes (globals.quanta)

**Current**: Arch-neutral, in-memory. `IR_MOV`, `IR_CALL`, `IR_CONST`, etc. Written directly to `src` buffer during codegen.

**Extension needed**:

| Change | What | Why |
|---|---|---|
| Binary IR format | `qobj_instr { opcode: u8, operands: [i64; 4] }` | Compact, fast to read/write |
| IR serialization | `qobj_write_ir(fd, ir_buf, ir_len)` | Write IR stream to `.qobj` |
| IR deserialization | `qobj_read_ir(fd)` | Load IR stream from `.qobj` |
| IR linking | `qobj_link_ir(base, imported)` | Merge IR streams, fix up cross-module calls |

**Location**: `globals.quanta` — add `qobj_ir_*` functions. IR opcodes already arch-neutral.

**Effort**: Low. IR is already structured, just needs binary format.

---

### A4. Include Dedup (objfmt.quanta)

**Current**: In-memory hash dedup. `imp_already()`, `imp_seen[]`. Prevents re-including same file within one TU.

**Replacement**: **Delete**. With `.qobj`, the OS file system handles dedup (same path = same file). Module-level dedup replaces file-level dedup.

**Location**: `objfmt.quanta` — remove `imp_already()`, `imp_seen[]`, `imp_seenc`.

**Effort**: Trivial (deletion).

---

### A5. Textual Inclusion (entry.quanta)

**Current**: `expand_includes()` — textually concatenates included files into single `src` buffer before tokenizing. Re-tokenizes, re-parses, re-IR-generates everything every compilation.

**Replacement**: `load_qobj()` — load pre-compiled `.qobj` (IR + symbol table) instead of re-tokenizing source.

**Hybrid approach** (backward compatibility):

```
if module has .qobj AND .qobj is newer than source:
    load .qobj (fast path)
else:
    expand_includes() + compile + emit .qobj (slow path, cached)
```

**Location**: `entry.quanta` — replace `expand_includes()` with `resolve_module()` that checks for `.qobj` first.

**Effort**: Medium. Need to handle both paths during transition.

---

## Part B — Priority Roadmap for Full .qobj

### Priority 1: Module Boundaries

**Why first**: Everything depends on this. What IS a module?

**Design decision**:

| Option | Definition | Pros | Cons |
|---|---|---|---|
| **A: File = Module** | Each `.quanta` file is a module | Simple, like Python/Go | Large files = large modules |
| **B: Directory = Module** | Each directory under `lib/std/` is a module | Like Rust crates | More complex resolution |
| **C: Namespace = Module** | `module foo;` declaration in source | Explicit, flexible | New keyword, more syntax |

**Recommendation**: **Option A (file = module)**. Simplest, proven (Python/Go/Java), easy to implement.

**What to define**:
- Module name = file path relative to project root (e.g., `std/big`, `std/io`)
- Module file = `<modname>.quobj` (e.g., `std/big.qobj`)
- Module interface = exported symbols + types (written to `.qobj`)
- Module implementation = IR stream (written to `.qobj`)

**Deliverable**: Design doc in `docs/QOBJ_MODULES.md`.

---

### Priority 2: IR Serialization

**Why second**: Can't cache what you can't write to disk.

**Binary format**:

```
.qobj IR section:
  [u32] instruction_count
  [instruction_count × qobj_instr] instructions

qobj_instr:
  [u8]  opcode        (IR_* code from globals.quanta)
  [i64] operand_0     (a0)
  [i64] operand_1     (a1)
  [i64] operand_2     (a2)
  [i64] operand_3     (a3)
```

**Total**: 33 bytes per instruction. A 10K-instruction module = 330KB.

**Functions to add**:

| Function | Purpose |
|---|---|
| `qobj_write_ir(fd, ir_buf, ir_len)` | Write IR stream to `.qobj` |
| `qobj_read_ir(fd, &len)` | Read IR stream from `.qobj` |
| `qobj_ir_emit(op, a0, a1, a2, a3)` | Emit to IR buffer (same as current `iremit`) |

**Location**: `globals.quanta` — add `qobj_ir_*` functions alongside existing `iremit`.

**Effort**: Low. IR is already structured.

---

### Priority 3: Symbol Table Serialization

**Why third**: Modules need to declare what they export.

**Binary format**:

```
.qobj symbol section:
  [u32] symbol_count
  [symbol_count × qobj_symbol] symbols

qobj_symbol:
  [u32] name_offset    (offset into .qobj string table)
  [u32] name_length
  [u8]  st_info        (STB_LOCAL | STB_GLOBAL)
  [u8]  st_flags       (STF_EXPORTED for cross-module visibility)
  [u16] st_shndx       (section index)
  [i64] st_value       (offset within section)
```

**Functions to add**:

| Function | Purpose |
|---|---|
| `qobj_write_symtab(fd, symtab, count)` | Write symbol table to `.qobj` |
| `qobj_read_symtab(fd, &count)` | Read symbol table from `.qobj` |
| `qobj_merge_symtabs(base, imported)` | Merge imported exports into current TU |

**Location**: `objfmt.quanta` — extend existing `p5_*` functions.

**Effort**: Low. Structure exists.

---

### Priority 4: Import Resolution

**Why fourth**: This is the core benefit. Load `.qobj` instead of re-tokenizing source.

**Algorithm**:

```
resolve_module(modname):
    qobj_path = modname + ".qobj"
    src_path  = modname + ".quanta"
    
    if qobj_exists(qobj_path) AND qobj_mtime > src_mtime:
        # Fast path: load pre-compiled .qobj
        qobj = load_qobj(qobj_path)
        merge_symtabs(current_symtab, qobj.exported_symbols)
        link_ir(current_ir, qobj.ir_stream)
    else:
        # Slow path: textual include + compile + cache
        source = read_file(src_path)
        expand_includes(source)
        compile_to_ir()
        emit_qobj(qobj_path)  # Cache for next time
```

**Functions to add**:

| Function | Purpose |
|---|---|
| `load_qobj(path)` | Load `.qobj` file (IR + symtab) |
| `emit_qobj(path)` | Write current compilation to `.qobj` |
| `resolve_module(modname)` | Resolve import (fast or slow path) |
| `qobj_mtime(path)` | Check if `.qobj` is stale |

**Location**: `entry.quanta` — replace `expand_includes()` with `resolve_module()`.

**Effort**: Medium. Need to handle both paths during transition.

---

### Priority 5: Linker Integration

**Why fifth**: Cross-module symbol resolution for real use.

**Algorithm**:

```
link_modules(main_qobj, imported_qobjs[]):
    # Collect all symbols from all modules
    global_symtab = merge_all_symtabs(imported_qobjs)
    
    # Resolve UNDEF symbols
    for each relocation in main_qobj:
        if relocation.target is UNDEF:
            target_sym = lookup(global_symtab, relocation.name)
            if target_sym found:
                patch_relocation(relocation, target_sym.address)
            else:
                error("undefined symbol: " + relocation.name)
    
    # Combine IR streams
    combined_ir = concatenate_all_ir(imported_qobjs)
    
    # Emit final binary
    emit_elf(combined_ir, global_symtab)
```

**Functions to add**:

| Function | Purpose |
|---|---|
| `qobj_link(main, imported[])` | Link multiple `.qobj` files |
| `qobj_resolve_undefs(symtab, relocs)` | Resolve undefined symbols |
| `qobj_patch_reloc(reloc, target_addr)` | Patch relocation with resolved address |

**Location**: `objfmt.quanta` — extend existing relocation handling.

**Effort**: Medium. Relocation infrastructure exists, needs cross-TU merge.

---

### Priority 6: Incremental Driver

**Why sixth**: Optimization — track dirty modules, rebuild only changed.

**Algorithm**:

```
incremental_build(main_file):
    # Build dependency graph
    dep_graph = parse_imports(main_file)
    
    # Find dirty modules (source newer than .qobj)
    dirty = []
    for each module in dep_graph:
        if module.src_mtime > module.qobj_mtime:
            dirty.append(module)
    
    # Recompile only dirty modules
    for each module in dirty:
        compile_to_qobj(module)
    
    # Link all modules
    link_modules(main_qobj, all_imported_qobjs)
```

**Functions to add**:

| Function | Purpose |
|---|---|
| `qobj_dep_graph(main_file)` | Parse imports, build dependency graph |
| `qobj_is_dirty(module)` | Check if module needs recompilation |
| `qobj_incremental_build(main_file)` | Rebuild only dirty modules |

**Location**: New file `qobj_driver.quanta` — incremental build orchestration.

**Effort**: Medium. Needs dependency tracking + mtime checks.

---

## Part C — Implementation Order

| Phase | Priorities | Deliverable | Effort |
|---|---|---|---|
| **Phase 1** | 1 (Module boundaries) | Design doc `QOBJ_MODULES.md` | Low |
| **Phase 2** | 2 + 3 (IR + Symtab serialization) | `.qobj` binary format spec | Low |
| **Phase 3** | 4 (Import resolution) | Fast-path `.qobj` loading | Medium |
| **Phase 4** | 5 (Linker integration) | Cross-module symbol resolution | Medium |
| **Phase 5** | 6 (Incremental driver) | Dirty-module tracking | Medium |
| **Phase 6** | Cleanup | Remove `expand_includes()`, `imp_already()` | Low |

**Total estimated effort**: ~2-3 weeks for a working .qobj system (Phases 1-4). Phases 5-6 are optimizations.

---

## Part D — File Changes Summary

| File | Action | Priority |
|---|---|---|
| `globals.quanta` | Add `qobj_ir_*` (IR serialization) | 2 |
| `objfmt.quanta` | Add `qobj_symtab_*` (symbol serialization) | 3 |
| `objfmt.quanta` | Add `qobj_reloc_*` (generic relocations) | 3 |
| `objfmt.quanta` | Remove `imp_already()`, `imp_seen[]` | 6 |
| `entry.quanta` | Replace `expand_includes()` with `resolve_module()` | 4 |
| `entry.quanta` | Add `load_qobj()`, `emit_qobj()` | 4 |
| `qobj_driver.quanta` | **NEW** — incremental build driver | 6 |
| `QOBJ_MODULES.md` | **NEW** — module boundary design doc | 1 |

---

## Part E — Verification Gates

| Gate | Test | Pass Criteria |
|---|---|---|
| G1 | Compile `lib/std/big.quanta` to `big.qobj` | `.qobj` file created, readable |
| G2 | Load `big.qobj` from another module | Symbols resolved, no re-tokenization |
| G3 | Cross-module call (`std/io` calls `std/big`) | Call resolves via `.qobj` import |
| G4 | Stale `.qobj` detection | Recompiles when source is newer |
| G5 | Incremental build | Only changed modules recompile |
| G6 | Self-host with `.qobj` | Quanta compiles itself using cached modules |

---

VERSION: 0.0.184
Workspace: /opt/tali/quanta/
All artifacts in docs/ and compiler/0.0.184/
