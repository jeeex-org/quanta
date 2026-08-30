#!/usr/bin/env python3
"""Map a Valgrind/backtrace PC to the enclosing Quanta function.

The Quanta x86 compiler emits a stripped ELF (no DWARF/.symtab), so
Valgrind reports crash addresses as raw PCs. The --debug build emits a
sym sidecar: one line per function "<name> <code_offset>", where
code_offset is the byte offset of the function entry within the text
segment (virtual base 0x400000).

The emitted symbol table records each function's START offset, but the
"end" used for range lookups is the NEXT function's start, which can be
misaligned when function emission order != declaration order. So we map
a PC by "largest start <= PC" -- this is correct regardless of end
overlap.
"""
import sys

def main():
    if len(sys.argv) < 3:
        print("usage: symbolize.py <symfile> <pc> [<pc> ...]")
        sys.exit(2)
    symfile, pcs = sys.argv[1], sys.argv[2:]
    BASE = 0x400000
    funcs = []  # (start, name)
    try:
        with open(symfile) as f:
            for line in f:
                parts = line.split()
                if len(parts) < 2:
                    continue
                name, off = parts[0], parts[1]
                try:
                    funcs.append((int(off), name))
                except ValueError:
                    pass
    except FileNotFoundError:
        print(f"(no sym file {symfile})")
        return
    funcs.sort()

    for pc_s in pcs:
        try:
            pc = int(pc_s, 16) if pc_s.lower().startswith("0x") else int(pc_s)
        except ValueError:
            print(f"{pc_s} -> <bad pc>"); continue
        off = pc - BASE
        if off < 0:
            print(f"PC {pc_s} (offset {off}) -> <before first function>")
            continue
        # largest start <= off
        owner = None
        for start, name in funcs:
            if start <= off:
                owner = name
            else:
                break
        if owner is None:
            print(f"PC {pc_s} (offset {off}) -> <before first function>")
        else:
            print(f"PC {pc_s} (offset {off}) -> {owner}")

if __name__ == "__main__":
    main()
