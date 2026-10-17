#!/usr/bin/env python3
"""tests/lfm2_jbytes_len_check.py -- mechanical guard for the jbytes() trap.

`jbytes(n, hexstr)` writes only the FIRST n bytes of the hex string. A 4-byte
declared length on a 5-byte instruction SILENTLY drops the ModRM byte, and the
next emitted byte is then consumed as that instruction's operand. It has now cost
two investigations in this project:

  * a 7-byte `vmovupd [reg+disp32]` declared as 7 was fine, an 8-byte one as 7
    segfaulted (recorded in the quanta-cpu-perf skill);
  * `vmovq rax,xmm0` (c4 e1 f9 7e c0, FIVE bytes) declared as 4 dropped `c0`, the
    following `ret` (c3) became its ModRM -> `vmovq %xmm0,%rbx`, and the kernel
    ran off the end of the emitted region: SIGSEGV at `add %al,(%rax)` with
    rax=0xbc, inside the JIT region, with the arithmetic all correct up to that
    point.

There is no source-level check for this: the byte string is only a string. So it
is checked here, mechanically, over every jbytes() call in lib/std/jit_x86*.quanta.

Exit 0 = every declared length equals the hex string's byte count.
Exit 1 = at least one mismatch (printed with file:line).

Usage: python3 tests/lfm2_jbytes_len_check.py
"""
import re
import sys
import glob
import os

CALL = re.compile(r'jbytes\(\s*(\d+)\s*,\s*"([0-9a-fA-F]*)"\s*\)')


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    files = sorted(glob.glob(os.path.join(root, "lib/std/jit_x86*.quanta")))
    if not files:
        print("FAIL: no lib/std/jit_x86*.quanta found under %s" % root)
        return 1
    total = 0
    bad = 0
    for path in files:
        rel = os.path.relpath(path, root)
        with open(path) as fh:
            for ln, line in enumerate(fh, 1):
                for m in CALL.finditer(line):
                    declared = int(m.group(1))
                    hexs = m.group(2)
                    if len(hexs) % 2 != 0:
                        print("FAIL %s:%d odd hex length %d: %s"
                              % (rel, ln, len(hexs), hexs))
                        bad += 1
                        continue
                    actual = len(hexs) // 2
                    total += 1
                    if declared != actual:
                        print("FAIL %s:%d declared %d bytes, hex string is %d "
                              "(%s) -- the last %d byte(s) are SILENTLY DROPPED"
                              % (rel, ln, declared, actual, hexs,
                                 actual - declared))
                        bad += 1
    print("checked %d jbytes() calls in %d file(s); %d mismatch(es)"
          % (total, len(files), bad))
    if bad:
        print("FAIL: a dropped byte shifts every following instruction; this is "
              "a code-fetch fault waiting to happen, not a style issue")
        return 1
    print("PASS: every jbytes() declared length matches its hex string")
    return 0


if __name__ == "__main__":
    sys.exit(main())
