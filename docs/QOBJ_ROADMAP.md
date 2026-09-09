# Quanta .qobj Roadmap — Accurate (based on compiler/0.0.185 audit)

VERSION: 0.0.185
Last updated: 2026-09-09

---

## Actual Compiler Structure

### Compilation Pipeline
```
entry.main() → expand_includes() → tokenize() → scanfns() → parse_block() → ci_func() → p5_elf_obj()
```

### File Map

| File | Key Functions | Purpose |
|------|---------------|---------|
| `entry.quanta` | `main()`, `link_object_with_libc()` | Entry point, source loading, include expansion |
| `lexer.quanta` | `tokenize()` | Lexer: source → tokens |
| `funcscan.quanta` | `scanfns()`, `scantraits()`, `scanimpls()` | Pre-pass: scan function signatures |
| `parse.quanta` | `parse_block()`, `parse_primary()`, `user_binop()` | Parser: tokens → IR via `iremit()` |
| `features.quanta` | `findfn()`, `gfind()`, `emit_patch()`, `nv()`, `nl()` | Symbol lookup, vreg allocation, patches |
| `method.quanta` | `parse_call()`, `resolve_fn()`, `build_str()` | Expression parsing, method calls |
| `emitter.quanta` | `emit_bltn()` | Builtin emission |
| `codegen.quanta` | `ci_func()`, `opt_func()`, `opt_tailcall()` | IR → machine code |
| `globals.quanta` | IR opcodes (`IR_MOV`, `IR_CALL`, etc.), `findstruct()`, `scannenums()` | IR definitions, type scanning |
| `helpers.quanta` | `iremit()`, `stok()`, `ktext()`, `emit_ovf()` | Core utilities |
| `objfmt.quanta` | `p5_add_symbol_b()`, `p5_add_reloc()`, `p5_elf_obj()`, `expand_includes()`, `imp_already()` | ELF output, include expansion, symbol table |
| `elf.quanta` | `STB_LOCAL`, `STB_GLOBAL` | ELF constants |

### Actual Symbol Table (objfmt.quanta)
- `symtab[idx*24 + 0]` = st_name (offset into strtab)
- `symtab[idx*24 + 4]` = st_info (bind << 4 | type)
- `symtab[idx*24 + 6]` = st_shndx
- `symtab[idx*24 + 8]` = st_value
- Functions: `p5_add_symbol_b()`, `p5_add_symbol_l()`, `p5_sym_for_name()`

### Actual Relocations (objfmt.quanta)
- `p5_add_reloc(po, symidx)` — generic RELA
- `p5_add_reloc_pc32(po, symidx)` — PC-relative

### Actual IR (helpers.quanta)
- `iremit(op, res, a0, a1, a2)` — emit IR instruction
- IR opcodes defined in `globals.quanta`

### Actual Include Dedup (objfmt.quanta)
- `imp_already()` — hash-based dedup
- `imp_seen[]` — seen includes array
- `imp_seenc` — count

---

## Fix Plan (Accurate)

### Phase 1: Module Boundaries
**What**: Define module = file. Each `.quanta` → `.qobj` artifact.
**Where**: `entry.quanta` — add module cache check
**Effort**: 1 day

### Phase 2: IR Serialization
**What**: Serialize `ir[]` array to `.qobj`
**Where**: `helpers.quanta` — add `qobj_write_ir()`, `qobj_read_ir()`
**Functions**: 
- `qobj_write_ir(fd, ir, irc)` — write IR stream
- `qobj_read_ir(fd, &len)` — read IR stream
**Effort**: 1 day

### Phase 3: Symbol Table Serialization
**What**: Serialize `symtab[]` to `.qobj`
**Where**: `objfmt.quanta` — add `qobj_write_symtab()`, `qobj_read_symtab()`
**Functions**:
- `qobj_write_symtab(fd, symtab, symcount)` — write symtab
- `qobj_read_symtab(fd, &count)` — read symtab
- `qobj_merge_symtabs(base, imported)` — merge imports
**Effort**: 1 day

### Phase 4: Import Resolution Rewrite
**What**: Replace `expand_includes()` with `resolve_module()` that checks `.qobj` cache
**Where**: `entry.quanta` — replace `expand_includes()` call
**Algorithm**:
```
resolve_module(modname):
    if .qobj exists AND .qobj newer than .quanta:
        load .qobj (fast)
    else:
        expand_includes() + compile + emit .qobj (slow)
```
**Effort**: 2 days

### Phase 5: Linker Integration
**What**: Cross-module symbol resolution
**Where**: `objfmt.quanta` — extend `p5_elf_obj()`
**Functions**:
- `qobj_link(main, imported[])` — link multiple `.qobj`
- `qobj_resolve_undefs(symtab, relocs)` — resolve undefined symbols
**Effort**: 2 days

### Phase 6: Incremental Driver
**What**: Track dirty modules, rebuild only changed
**Where**: New file `qobj_driver.quanta`
**Functions**:
- `qobj_dep_graph(main)` — parse imports
- `qobj_is_dirty(module)` — check mtime
- `qobj_incremental_build(main)` — rebuild dirty only
**Effort**: 1 day

---

## Verification Gates

| Gate | Test | Pass Criteria |
|------|------|---------------|
| G1 | Compile `lib/std/big.quanta` to `.qobj` | `.qobj` file created |
| G2 | Load `.qobj` from another module | Symbols resolved |
| G3 | Cross-module call | Call resolves via `.qobj` |
| G4 | Stale `.qobj` detection | Recompiles when source newer |
| G5 | Incremental build | Only changed modules recompile |
| G6 | Self-host with `.qobj` | Quanta compiles itself |

---

## File Changes

| File | Action | Phase |
|------|--------|-------|
| `entry.quanta` | Replace `expand_includes()` with `resolve_module()` | 4 |
| `helpers.quanta` | Add `qobj_write_ir()`, `qobj_read_ir()` | 2 |
| `objfmt.quanta` | Add `qobj_write_symtab()`, `qobj_read_symtab()` | 3 |
| `objfmt.quanta` | Add `qobj_link()`, `qobj_resolve_undefs()` | 5 |
| `objfmt.quanta` | Remove `imp_already()`, `imp_seen[]` | 6 |
| `qobj_driver.quanta` | **NEW** — incremental build | 6 |

---

Total effort: ~8 days (1 week+)