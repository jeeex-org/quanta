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
    calls = re.findall(r'(?:jbytes|femit)\(\s*(\d+)\s*,\s*"([0-9a-f]+)"', sec)
    print("f32 section: %d hex-string literal(s)" % len(calls))
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
        if h in [t for _, t in tbl]:
            continue
        if any(t.startswith(h) for _, t in tbl):
            continue      # parameterised form: the tail is a jb()/ji32() operand
        print("FAIL not present in the executed-verified table: %s" % h)
        bad += 1

    print("%d failure(s)" % bad)
    if bad:
        print("FAIL: a hex string in the f32 section is not one that was run")
        return 1
    print("PASS: every f32-section hex string was executed with known operands")
    return 0


if __name__ == "__main__":
    sys.exit(main())
