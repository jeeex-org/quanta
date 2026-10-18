#!/usr/bin/env python3
"""tests/lfm2_f32_hexcheck.py -- mechanical guard for jit_x86_fused.quanta's f32
kernel section.

TWO checks, both mechanical, because the f32 section is 43 hand-typed hex
strings and a single wrong nibble is a silent wrong value or a code-fetch fault:

  1. every `jbytes(n, "...")` / `femit("...", n)` literal in the f32 section is
     either a PRE-EXISTING sequence (the kernel's own load/loop/return stubs) or
     an entry -- or the prefix of an entry whose tail byte is the operand
     immediate passed via jb()/ji32() -- in tests/lfm2_f32_enc_bytes.h, which is
     generated from tests/lfm2_f32_kernels.s by GNU as + objdump and whose every
     entry was RUN with known operands by tests/lfm2_f32_enc_verify.c. Reading a
     hex string is not verification; this ties the kernel to bytes that executed.

  2. every f32-section hex string's DECLARED length equals its byte count (the
     jbytes trap that has bitten this tree twice) -- a superset of what
     tests/lfm2_jbytes_len_check.py does tree-wide, restated here so the f32
     section can be checked on its own.

Exit 0 = both pass. Exit 1 = at least one failure, printed with the string.
"""
import re
import sys
import os

MARK = "// THE f32 KERNEL FAMILY"
ENC = "tests/lfm2_f32_enc_bytes.h"
SRC = "lib/std/jit_x86_fused.quanta"

# sequences the f32 section reuses from the kernels above it, whose bytes are
# exercised by the gate rows for those kernels rather than by the f32 table.
PREEXISTING = {
    "4883e901",        # sub rcx, 1
    "00000000",        # the rel32 placeholder
    "4981c1d2000000",  # add r9, 210
    "4983c220",        # add r10, 32
    "4983e920",        # sub r9, 32  (rewind)
    "4983c110",        # add r9, 16  (skip header)
    "4c8b0f", "4c8b5708", "488b4f18", "c3",
}


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, SRC)).read()
    sec = src[src.index(MARK):]

    tbl = []
    for m in re.finditer(r'\{ "([^"]+)", (\d+), \{ ([^}]*)\} \}', 
                         open(os.path.join(root, ENC)).read()):
        h = "".join(x.strip()[2:] for x in m.group(3).split(",") if x.strip())
        tbl.append((m.group(1), h))

    bad = 0
    # NOTE THE TWO ARGUMENT ORDERS: jbytes(n, "hex") and femit("hex", n). An
    # earlier revision of this check matched only the jbytes form, so every
    # femit() call in the section -- which is most of the factor prologue -- was
    # silently unchecked. That hole let four hand-adapted prologue instructions
    # through with the WRONG SOURCE REGISTER (they read xmm7, the f64 kernel's
    # scratch, instead of this kernel's xmm11). A checker that cannot see half
    # its input is not a checker.
    calls = [(m.group(1), m.group(2))
             for m in re.finditer(r'jbytes\(\s*(\d+)\s*,\s*"([0-9a-f]+)"', sec)]
    calls += [(m.group(2), m.group(1))
              for m in re.finditer(r'femit\(\s*"([0-9a-f]+)"\s*,\s*(\d+)\)', sec)]
    # PARAMETERISED USAGE: a jbytes() whose operand byte(s) are appended by the
    # next call. This is the distinction check 2 alone cannot make -- the correct
    # and the wrong form are BOTH valid table entries, so only the usage tells
    # them apart, and a negative control proved that an exact-match rule passes
    # the wrong one.
    # Comments are stripped FIRST: the kernel's calls carry a mnemonic comment
    # between the jbytes() and the jb() that appends its operand, and a regex that
    # cannot see across a comment finds zero parameterised prefixes and silently
    # exempts nothing.
    nocmt = "\n".join(re.sub(r'//.*$', '', ln) for ln in sec.splitlines())
    params = set(re.findall(r'jbytes\(\s*\d+\s*,\s*"([0-9a-f]+)"\s*\)\s*;?\s*'
                            r'(?:jb|ji32)\s*\(', nocmt))
    print("f32 section: %d hex-string literal(s) "
          "(%d jbytes, %d femit); %d parameterised prefix(es)"
          % (len(calls), len(re.findall(r'jbytes\(', sec)),
             len(re.findall(r'femit\(', sec)), len(params)))
    for declared, h in calls:
        if len(h) % 2:
            print("FAIL odd hex length: %s" % h)
            bad += 1
            continue
        if int(declared) != len(h) // 2:
            print("FAIL declared %s bytes, string is %d: %s"
                  % (declared, len(h) // 2, h))
            bad += 1
        if h in PREEXISTING:
            continue
        if h in params:
            # A parameterised prefix must be STRICTLY SHORTER than a table entry,
            # because a hex string that is itself a COMPLETE instruction has no
            # displacement field for the operand to occupy:
            # `vpmovzxbd ymm6, [r9]` assembles to five bytes with mod=00, and the
            # jb(disp8) byte then lands as the NEXT instruction's first byte and
            # shifts the whole kernel. This shipped once and segfaulted.
            if any(len(t) > len(h) and t.startswith(h) for _, t in tbl):
                continue
            print("FAIL parameterised prefix %s has no longer form in the table"
                  " -- appending an operand byte to a COMPLETE instruction shifts"
                  " the emitted stream" % h)
            bad += 1
            continue
        if h in [t for _, t in tbl]:
            continue
        print("FAIL not present in the executed-verified table: %s" % h)
        bad += 1

    print("%d failure(s)" % bad)
    if bad:
        print("FAIL: a hex string in the f32 section is not one that was run")
        return 1
    print("PASS: every f32-section hex string was executed with known operands,")
    print("      and every parameterised prefix has room for its operand byte")
    return 0


if __name__ == "__main__":
    sys.exit(main())
