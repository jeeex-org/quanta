# Quanta Compiler Import Fix — Plan

## Root Cause

`import` = **textual inlining**. The compiler (`expand_includes` in `objfmt.quanta`) recursively reads ALL imported source files into a single `src` buffer. The entire blob is then lexed (`stok()` → `TOK_CAP=500M`), parsed, and IR'd (`iremit()` → `IR_CAP=1B`) as ONE unit.

Consequences:
- `import std/spec_parser` re-lexes `std/json` + `std/str` + `std/vec` + `std/map` + `std/fs`
- 5 imports → 5× their deps → exponential token growth
- No caching between compilations — re-tokenize everything every time
- `undeclared variable` errors happen because the lexer aborts (`emit_ovf()` → exit(17)) before completing funcscan

## Fix: Separate Compilation with `.qobj` Artifacts

### Phase 1: Module Frontend (lex → parse → AST → symbol table)

Change per-module pipeline:
1. Lex module source → token stream
2. Parse → AST
3. Extract symbol table (function names, signatures, types, exports, globals)
4. Serialize symbol table + compressed AST → `.qobj` file
5. **Discard tokens** — they're not needed after this

### Phase 2: Import Resolution (load `.qobj`, not source)

When encountering `import std/foo`:
1. Check if `lib/std/foo.qobj` exists and is newer than `lib/std/foo.quanta`
2. If yes → load `.qobj` (few KB), merge symbol table
3. If no → compile `foo.quanta` to `.qobj` first (recursively)
4. **Never re-tokenize** already-compiled modules

### Phase 3: Module Backend (IR gen per module)

1. Generate IR only for the current module's functions
2. Reference imported symbols via symbol table offsets (not inlined)
3. Emit `.o` object file with relocations for external references

### Phase 4: Linker

1. Link `.o` files + `.qobj` symbol tables
2. Resolve cross-module references
3. Emit final executable

## What Changes in Compiler

### New files in `compiler/0.0.185/src/x86/`:

| File | Purpose |
|------|---------|
| `qobj.quanta` | `.qobj` serialization/deserialization |
| `link.quanta` | Multi-module linker |
| `frontend.quanta` | Lex → parse → AST → symbol table (extracted from entry) |
| `backend.quanta` | IR gen per module (extracted from method/codegen) |

### Modified files:

| File | Change |
|------|--------|
| `entry.quanta` | Orchestrates: frontend → import resolution (via `.qobj`) → backend → link |
| `objfmt.quanta` | `expand_includes` → `resolve_imports` (loads `.qobj`) |
| `funcscan.quanta` | Works on per-module token streams, not inlined blob |
| `method.quanta` | IR gen uses symbol table for cross-module refs |
| `globals.quanta` | Add `.qobj` arena, import cache |
| `helpers.quanta` | Add import cache caps (separate from TOK_CAP/IR_CAP) |

### New globals:

```
let QOBJ_CACHE = mmap(...)     // loaded .qobj symbol tables
let QOBJ_CAP = ...             // max cached modules
```

## Migration Strategy

### Step 1: `.qobj` format (1-2 days)
- Define binary format: magic, version, exports count, export entries (name, type, signature)
- Implement `qobj_write()` and `qobj_read()`
- Cache compiled `.qobj` files alongside sources

### Step 2: Import resolution rewrite (1 day)
- Replace `expand_includes` with `resolve_imports`
- Check `.qobj` cache first
- Fall back to source compilation for cache miss
- Merge symbol tables

### Step 3: Per-module compilation (2-3 days)
- Extract frontend (lex+parse+AST) into separate pass
- Extract backend (IR gen) into separate pass
- Each module gets its own `.o`
- Linker combines `.o` files

### Step 4: Build system update (0.5 day)
- `qc` detects multi-module projects
- Only recompile changed modules
- Link final executable

## Estimated Effort

| Task | Duration |
|------|----------|
| `.qobj` format + serialization | 1 day |
| Import resolution rewrite | 1 day |
| Per-module frontend/backend split | 2 days |
| Linker | 1 day |
| Testing with SI modules | 1 day |
| **Total** | **6 days** |

## Benefits

1. **Import explosion fixed** — importing a module loads few KB, not MB
2. **Incremental compilation** — only recompile changed modules
3. **Faster builds** — cached `.qobj` for stdlib
4. **Scalable** — can handle 8000+ module projects
5. **No token limit** — per-module token streams are small

## Verification

After fix, `si_gap_resolver` with 5+ imports should compile without hitting `TOK_CAP`. The entire SI pipeline (`si_main` + all deps) should link correctly.