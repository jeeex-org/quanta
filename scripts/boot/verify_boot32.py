#!/usr/bin/env python3
"""verify_boot32.py -- independently verify the 32-bit PVH prefix in a --bare ELF.

The prefix in the image is generated data (src/x86/boot32_bytes.quanta, produced
from scripts/boot/boot32.S by gen_boot32.py). This verifies the bytes that
actually shipped, without trusting the generator:

  1. the ELF has a PT_NOTE that really is the Xen PHYS32_ENTRY note
     (namesz 4, descsz 4, type 18, name "Xen", desc == the stub address);
  2. the note is at the expected file offset (ht = 64 + 56*5 = 344) and its
     descriptor address is inside the first LOAD segment;
  3. the stub bytes in the image are byte-identical to a fresh assembly of
     boot32.S linked at the same STUB_BASE with the same ENTRY_BASE, and
     disassemble instruction-for-instruction (which also proves the stub's
     internal absolute references — the GDT descriptor and the far-jump target —
     were resolved for this image).

Usage: scripts/boot/verify_boot32.py <bare-elf> [<compiler-version-dir>]
Exit 0 = verified; non-zero prints the mismatch.
"""
import os
import re
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "boot32.S")
BASE = 0x400000
HT = 344              # 64 + 56*5 program headers in --bare mode


def sh(cmd, **kw):
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True, **kw)
    if p.returncode != 0:
        sys.exit(f"FAIL: {cmd}\n{p.stdout}\n{p.stderr}")
    return p.stdout


def fail(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    elf = sys.argv[1]
    verdir = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(os.path.dirname(os.path.abspath(elf)))
    gen = os.path.join(verdir, "src/x86/boot32_bytes.quanta")
    for f in (elf, SRC, gen):
        if not os.path.exists(f):
            fail(f"missing file: {f}")

    txt = open(gen).read()

    def const(name):
        m = re.search(rf"^let {name} = (\d+)", txt, re.M)
        if not m:
            fail(f"cannot read {name} from {gen}")
        return int(m.group(1))

    stub_base = const("boot32_stub_base")
    stub_len = const("boot32_stub_len")
    note_len = const("boot32_note_len")
    pad_len = const("boot32_pad_len")
    prefix_len = const("boot32_prefix_len")
    entry_base = const("boot32_entry_base")
    print(f"verifying {elf}")
    print(f"  stub_base=0x{stub_base:x} stub_len={stub_len} note_len={note_len} "
          f"pad={pad_len} prefix_len={prefix_len} entry=0x{entry_base:x}")

    img = open(elf, "rb").read()
    if img[:4] != b"\x7fELF" or img[4] != 2:
        fail("not an ELF64 file")
    e_entry = struct.unpack_from("<Q", img, 24)[0]
    if e_entry != BASE + HT + prefix_len:
        fail(f"e_entry 0x{e_entry:x} != BASE + ht + prefix_len "
             f"(0x{BASE + HT + prefix_len:x})")
    print(f"  e_entry=0x{e_entry:x} (start of the Quanta startup stub)")

    # --- program headers ------------------------------------------------------
    phoff = struct.unpack_from("<Q", img, 32)[0]
    phentsize = struct.unpack_from("<H", img, 54)[0]
    phnum = struct.unpack_from("<H", img, 56)[0]
    notes = []
    loads = []
    for i in range(phnum):
        o = phoff + i * phentsize
        t, fl, off, va, pa, fsz, msz, al = struct.unpack_from("<IIQQQQQQ", img, o)
        if t == 4:
            notes.append((off, va, fsz, al))
        if t == 1:
            loads.append((off, va, fsz, msz))
    if len(notes) != 1:
        fail(f"expected exactly 1 PT_NOTE, found {len(notes)}")
    noff, nva, nfsz, nal = notes[0]
    if noff != HT:
        fail(f"PT_NOTE file offset {noff}, expected {HT} (ht)")
    if nfsz != note_len:
        fail(f"PT_NOTE filesz {nfsz}, expected {note_len}")
    if nal != 4:
        fail(f"PT_NOTE align {nal}, expected 4")
    if noff % 4:
        fail("PT_NOTE file offset is not 4-aligned")
    print(f"  PT_NOTE at file {noff} / vaddr 0x{nva:x}, filesz {nfsz}, align {nal}")

    # note contents
    namesz, descsz, ntype = struct.unpack_from("<III", img, noff)
    name = img[noff + 12: noff + 12 + namesz]
    desc = struct.unpack_from("<I", img, noff + 12 + namesz)[0]
    if (namesz, descsz, ntype) != (4, 4, 18):
        fail(f"note header is (namesz={namesz}, descsz={descsz}, type={ntype}), "
             f"expected (4, 4, 18 = XEN_ELFNOTE_PHYS32_ENTRY)")
    if name != b"Xen\x00":
        fail(f"note name {name!r}, expected b'Xen\\x00'")
    if desc != stub_base:
        fail(f"note desc 0x{desc:x} != STUB_BASE 0x{stub_base:x}")
    in_load = any(va <= desc < va + msz for _, va, _, msz in loads)
    if not in_load:
        fail(f"note desc 0x{desc:x} is not inside any PT_LOAD segment")
    print(f"  note: Xen/{ntype} -> 0x{desc:x} (the stub, inside the code LOAD)")

    # --- stub bytes vs a fresh assembly --------------------------------------
    stub_off = noff + note_len + pad_len
    if stub_off != stub_base - BASE:
        fail(f"stub file offset {stub_off} != STUB_BASE - BASE ({stub_base - BASE})")
    shipped = img[stub_off: stub_off + stub_len]
    if len(shipped) != stub_len:
        fail(f"only {len(shipped)} stub bytes in the file")

    with tempfile.TemporaryDirectory() as tmp:
        obj = f"{tmp}/ref.o"
        ld_script = f"{tmp}/ref.ld"
        ref_elf = f"{tmp}/ref.elf"
        ref_bin = f"{tmp}/ref.bin"
        open(ld_script, "w").write(
            f"SECTIONS {{ . = {stub_base}; .boot32 : {{ *(.boot32) }} }}\n")
        sh(f"as --64 --defsym STUB_BASE={stub_base} --defsym ENTRY_BASE={entry_base} "
           f"-o {obj} {SRC}")
        sh(f"ld -T {ld_script} -o {ref_elf} {obj}")
        sh(f"objcopy -O binary --only-section=.boot32 {ref_elf} {ref_bin}")
        ref = open(ref_bin, "rb").read()
        if len(ref) != stub_len:
            fail(f"reference stub is {len(ref)} bytes, image has {stub_len}")

        if shipped == ref:
            print(f"  stub bytes: identical to a fresh assembly of boot32.S "
                  f"({stub_len} bytes)")
        else:
            for i, (a, b) in enumerate(zip(shipped, ref)):
                if a != b:
                    fail(f"stub byte {i} is 0x{a:02x}, reference has 0x{b:02x}")

        # instruction-level cross-check (absolute references included)
        def insns(cmd):
            out = sh(cmd)
            lines = []
            for line in out.splitlines():
                m = re.match(r"^\s*([0-9a-f]+):\t([0-9a-f ]+)\t?(.*)$", line)
                if m:
                    lines.append((int(m.group(1), 16), m.group(3).strip()))
            return lines

        open(f"{tmp}/shipped.bin", "wb").write(shipped)
        a = insns(f"objdump -D -b binary -m i386 -M i386 "
                  f"--adjust-vma={stub_base} {tmp}/shipped.bin")
        # Decode BOTH from raw bytes in the same mode: objdump on the ELF64
        # container decodes .boot32 as 64-bit regardless of -M i386, so comparing
        # that against a raw i386 decode compares two different decoders (it
        # "found" a mismatch on identical bytes).
        b = insns(f"objdump -D -b binary -m i386 -M i386 "
                  f"--adjust-vma={stub_base} {ref_bin}")
        if a != b:
            print("  instruction streams differ:")
            for (aa, ai), (ba, bi) in zip(a, b):
                if (aa, ai) != (ba, bi):
                    print(f"    0x{aa:x} {ai!r}   vs   0x{ba:x} {bi!r}")
            fail("disassembly mismatch")
        print(f"  stub disassembly: matches the reference "
              f"instruction-for-instruction ({len(a)} instructions)")

    print(f"OK: PVH prefix verified (Xen note + {stub_len} stub bytes from boot32.S)")


if __name__ == "__main__":
    main()
