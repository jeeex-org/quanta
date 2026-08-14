#!/usr/bin/env python3
"""Map a Valgrind/backtrace PC to the enclosing Quanta function.

The Quanta x86 compiler emits a stripped ELF (no DWARF, no .symtab), so
Valgrind reports crash addresses as raw PCs like 0x416748 with no symbol.
`qc --debug <out>` writes a sidecar `<out>.sym` with one line per function:

    <fn_name> <code_offset>

where code_offset is the byte offset into .text. The ELF is loaded at
virtual base 0x400000 (BASE = 4194304 in elf.quanta), so:
    virtual_pc = BASE + code_offset

This tool reads the .sym sidecar and, given a raw PC (decimal or 0x-hex),
prints the function whose [start, next_start) interval contains the offset.

Usage:
    python3 tools/symbolize.py <symfile> <pc> [base=4194304]
    # pc may be decimal or 0x.... ; base is the ELF load base (default 4194304)

Example:
    python3 tools/symbolize.py out.exe.sym 0x416748
"""
import sys

BASE = 4194304  # elf.quanta: let BASE = 4194304


def parse_pc(s, base):
    s = s.strip().lower()
    if s.startswith("0x"):
        pc = int(s, 16)
    else:
        pc = int(s, 10)
    # If the PC looks like a raw virtual address (>= base), convert to a
    # .text offset; otherwise treat it as an already-relative offset.
    if pc >= base:
        pc -= base
    return pc


def load_syms(path):
    syms = []  # list of (offset, name)
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            name, off = parts[0], int(parts[1], 10)
            syms.append((off, name))
    syms.sort()
    return syms


def resolve(syms, offset):
    # Find the last function whose start <= offset (the enclosing fn).
    enclosing = None
    for start, name in syms:
        if start <= offset:
            enclosing = (start, name)
        else:
            break
    if enclosing is None:
        return None
    start, name = enclosing
    # next start for relative size
    nxt = None
    for s, _ in syms:
        if s > start:
            nxt = s
            break
    return start, name, nxt


def main():
    if len(sys.argv) < 3:
        sys.stderr.write(__doc__)
        sys.exit(2)
    symfile = sys.argv[1]
    pc_arg = sys.argv[2]
    base = int(sys.argv[3], 10) if len(sys.argv) > 3 else BASE
    syms = load_syms(symfile)
    if not syms:
        print("no symbols found in %s" % symfile)
        sys.exit(1)
    offset = parse_pc(pc_arg, base)
    res = resolve(syms, offset)
    if res is None:
        print("PC 0x%x (offset %d) -> <before first function>" % (offset + base, offset))
        sys.exit(1)
    start, name, nxt = res
    span = (("..%d" % nxt) if nxt is not None else "..end")
    print("PC 0x%x (offset %d) -> %s [text %d%s]" % (offset + base, offset, name, start, span))
    sys.exit(0)


if __name__ == "__main__":
    main()
