#!/usr/bin/env python3
"""gen_boot32.py -- generate the Quanta byte table for the PVH 32-bit stub.

Inputs:
  scripts/boot/boot32.S            (assembled by gas; the source of truth)

Output:
  compiler/<ver>/src/x86/boot32_bytes.quanta

The generated file contains emit_boot32_prefix(), which appends the 20-byte Xen
ELF note (XEN_ELFNOTE_PHYS32_ENTRY) followed by the stub's machine code, plus
the constants the compiler asserts against. Every byte carries the assembler's
own disassembly as a comment, so the emitted prefix can be audited line by line
against boot32.S.

Layout (must match the compiler's bare-mode ELF: BASE=0x400000, phc=5 -> ht=344):
  file offset ht .. ht+20   Xen note   (p_offset/p_vaddr of the PT_NOTE phdr)
  file offset ht+20 ..      stub code  (= STUB_BASE, what QEMU jumps to)
  file offset ht+20+len ..  the 64-bit Quanta startup stub (= ENTRY_BASE)

Usage: python3 scripts/boot/gen_boot32.py compiler/$(cat VERSION)
"""
import os
import subprocess
import sys

BASE = 0x400000
PHDR_COUNT = 5                 # --bare mode: PHDR, LOAD, LOAD, GNU_STACK, NOTE
EHDR = 64
PHDR = 56
HT = EHDR + PHDR * PHDR_COUNT  # 0x158
NOTE_LEN = 20                  # namesz/descsz/type/name/desc, 4-aligned
# The stub section must land on a 16-byte boundary: gas gives .boot32 16-byte
# alignment (the .balign 16 in the source), and if the section's VMA is not
# 16-aligned ld inserts padding INSIDE it — which silently shifts every
# absolute address the stub was linked with. Measured: at ht+20 the linker
# padded 4 bytes and the GDT descriptor address came out 4 bytes late. So the
# prefix is [note 20][pad 4][stub], putting the stub at ht+24 = 0x400170.
PAD = 4


def sh(cmd):
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if p.returncode != 0:
        sys.exit(f"FAILED: {cmd}\n{p.stdout}\n{p.stderr}")
    return p.stdout


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    verdir = sys.argv[1].rstrip("/")
    here = os.path.dirname(os.path.abspath(__file__))
    src = os.path.join(here, "boot32.S")
    stub_base = BASE + HT + NOTE_LEN + PAD

    # The stub contains one absolute reference (movl $gdt_desc, %eax) whose
    # value only resolves at link time, so each pass assembles AND links with
    # .boot32 placed at STUB_BASE. objcopy then extracts the final bytes.
    def build(entry, tag):
        obj = f"/tmp/boot32_{tag}.o"
        elf = f"/tmp/boot32_{tag}.elf"
        ld_script = f"/tmp/boot32_{tag}.ld"
        with open(ld_script, "w") as f:
            f.write(f"SECTIONS {{ . = {stub_base}; .boot32 : {{ *(.boot32) }} }}\n")
        sh(f"as --64 --defsym STUB_BASE={stub_base} --defsym ENTRY_BASE={entry} "
           f"-o {obj} {src}")
        sh(f"ld -T {ld_script} -o {elf} {obj}")
        return elf

    # Pass 1: placeholder entry, just to learn the stub's size.
    elf1 = build(0, "p1")
    size = int(sh(f"size -A -d {elf1} | awk '$1==\".boot32\" {{print $2}}'").strip())
    boot32_addr = int(sh(f"nm {elf1} | awk '$3==\"boot32\" {{print $1}}'").strip(), 16)
    if boot32_addr != stub_base:
        sys.exit(f"linker placed boot32 at 0x{boot32_addr:x}, expected 0x{stub_base:x} "
                 f"(section alignment padding — is STUB_BASE 16-byte aligned?)")
    if size <= 0 or size % 16 != 0:
        sys.exit(f"unexpected .boot32 size {size} (must be a positive multiple of 16)")

    # Pass 2: real entry address; the ljmp imm32 is always 4 bytes, so the size
    # is unchanged (asserted below).
    entry = stub_base + size
    elf2 = build(entry, "p2")
    size2 = int(sh(f"size -A -d {elf2} | awk '$1==\".boot32\" {{print $2}}'").strip())
    if size2 != size:
        sys.exit(f"stub size changed between passes: {size} -> {size2}")

    raw = "/tmp/boot32.bin"
    sh(f"objcopy -O binary --only-section=.boot32 {elf2} {raw}")
    data = open(raw, "rb").read()
    if len(data) != size:
        sys.exit(f"extracted {len(data)} bytes, expected {size}")

    # Disassembly of the linked section, used ONLY to annotate the exact bytes
    # taken from the raw section above (never as the source of those bytes).
    listing = sh(f"objdump -d -M i386 {elf2}")
    insns = []          # (offset, nbytes, mnemonic), offsets relative to boot32
    cur = None
    for line in listing.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        try:
            addr = int(parts[0].strip().rstrip(":"), 16)
        except ValueError:
            continue
        try:
            bytefield = parts[1].strip()
            insn = parts[2].strip() if len(parts) > 2 else ""
        except IndexError:
            continue
        try:
            bs = [int(b, 16) for b in bytefield.split()]
        except ValueError:
            continue
        if insn:                       # a real instruction starts here
            cur = [addr - stub_base, len(bs), insn]
            insns.append(cur)
        elif cur is not None:          # continuation of a long instruction
            cur[1] = cur[1] + len(bs)
    # Tile the raw bytes with the annotated instructions. Any byte the listing
    # failed to describe is emitted as its own row, so the table is exact by
    # construction and the generator still fails if the tiling runs past the end.
    rows = []                          # (offset, [bytes], comment)
    pos = 0
    for off, n, insn in insns:
        if off > pos:                  # bytes the listing skipped (e.g. (bad))
            rows.append((pos, list(data[pos:off]), "undecoded"))
            pos = off
        if off != pos or n <= 0:
            continue
        rows.append((off, list(data[off:off + n]), insn))
        pos = off + n
    if pos < len(data):
        rows.append((pos, list(data[pos:]), "undecoded"))
    total = sum(len(r[1]) for r in rows)
    if total != len(data):
        sys.exit(f"byte table tiling produced {total} bytes, section has {len(data)}")

    out = []
    out.append("// boot32_bytes.quanta -- GENERATED. DO NOT EDIT BY HAND.")
    out.append("//")
    out.append("// Source of truth: scripts/boot/boot32.S")
    out.append("// Regenerate:      python3 scripts/boot/gen_boot32.py <verdir>")
    out.append("// Verified by:     scripts/boot/verify_boot32.py (validates the")
    out.append("//                  prefix back out of a built ELF and diffs boot32.S)")
    out.append("//")
    out.append("// This is the 32-bit PVH entry stub: the only non-Quanta code in the")
    out.append("// image. QEMU enters STUB_BASE in 32-bit protected mode (paging off)")
    out.append("// after reading the Xen PHYS32_ENTRY note below; the stub builds the")
    out.append("// 1 GiB identity map and jumps to ENTRY_BASE in long mode.")
    out.append("")
    out.append(f"let boot32_note_len = {NOTE_LEN}")
    out.append(f"let boot32_stub_len = {size}")
    out.append(f"let boot32_prefix_len = {NOTE_LEN + PAD + size}")
    out.append(f"let boot32_stub_base = {stub_base}       // 0x{stub_base:x}")
    out.append(f"let boot32_note_off = {HT}             // file offset of the note (== ht)")
    out.append(f"let boot32_pad_len = {PAD}")
    out.append(f"let boot32_entry_base = {entry}       // 0x{entry:x}")
    out.append("")
    out.append("// emit_boot32_prefix(): append [Xen note][32-bit stub] to the code")
    out.append("// buffer. Callers must have already verified boot32_stub_base matches")
    out.append("// BASE + ht + boot32_note_len for the ELF being written (the compiler")
    out.append("// asserts this and fails closed otherwise).")
    out.append("fn emit_boot32_prefix() {")
    out.append("    // ---- Xen ELF note: XEN_ELFNOTE_PHYS32_ENTRY (type 18) ----")
    out.append(f"    eb(4); eb(0); eb(0); eb(0)      // namesz  = 4")
    out.append(f"    eb(4); eb(0); eb(0); eb(0)      // descsz  = 4")
    out.append(f"    eb(18); eb(0); eb(0); eb(0)     // type    = XEN_ELFNOTE_PHYS32_ENTRY")
    out.append('    eb(88); eb(101); eb(110); eb(0) // name    = "Xen" + NUL')
    for k in range(4):
        b = (stub_base >> (8 * k)) & 0xFF
        out.append(f"    eb({b})" + ("      // desc    = STUB_BASE (32-bit phys entry)" if k == 0 else ""))
    if PAD:
        out.append(f"    // ---- {PAD} pad bytes: place the 16-aligned stub at ht+{NOTE_LEN + PAD} ----")
        out.append("    " + "; ".join("eb(0)" for _ in range(PAD)))
    out.append("    // ---- 32-bit stub (from scripts/boot/boot32.S) ----")
    for off, bs, insn in rows:
        cells = "; ".join(f"eb({b})" for b in bs)
        out.append(f"    {cells}   // {off:4d}  {insn}")
    out.append("}")
    out.append("")

    dst = os.path.join(verdir, "src/x86/boot32_bytes.quanta")
    with open(dst, "w") as f:
        f.write("\n".join(out))
    print(f"wrote {dst}")
    print(f"  note {NOTE_LEN} bytes at ht+0 (file offset 0x{HT:x})")
    print(f"  pad  {PAD} bytes")
    print(f"  stub {size} bytes at ht+{NOTE_LEN + PAD} (STUB_BASE 0x{stub_base:x})")
    print(f"  64-bit entry ENTRY_BASE 0x{entry:x} = BASE + ht + {NOTE_LEN + PAD + size}")


if __name__ == "__main__":
    main()
