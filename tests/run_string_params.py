#!/usr/bin/env python3
"""Verify tests/test_string_params.quanta by COMPARING ITS STDOUT.

The string tag has exactly one observable effect in Quanta: it decides whether
print/println write the string's bytes or render the heap address as digits.
Nothing in-language can capture stdout, so an in-program assertion cannot see it.

An earlier version of this test asserted only len() of literals passed into the
callee, and PASSED on a compiler that printed every parameter as a pointer --
len() reads the length header, which is present either way. So this harness
exists: it compares the program's output against the exact expected text, where
a pointer shows up as digits.

A compiler that prints pointers fails here. Verified against the pre-fix binary:
    old ->  1109393992 / 1109394008 / ... / s=1109394040
    new ->  A / B / ... / s=D

Usage:  python3 tests/run_string_params.py [path/to/qc]
"""
import subprocess
import sys
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    REPO, 'compiler', open(os.path.join(REPO, 'VERSION')).read().strip(),
    'bin', 'x86', 'qc')
SRC = os.path.join(REPO, 'tests', 'test_string_params.quanta')
OUT = '/tmp/run_string_params_bin'

# Note: no blank line before the final status. locals_still_work() ends with
# println("literal"), and the status follows directly.
EXPECTED = """A
B
C
n=42
len=1
s=D
a=E
b=F
local
literal
test_string_params: PASS"""


def main():
    if os.path.exists(OUT):
        os.remove(OUT)
    c = subprocess.run(['timeout', '400', QC, SRC, OUT],
                       capture_output=True, text=True, cwd=REPO)
    if not os.path.exists(OUT):
        print("COMPILE-FAIL")
        print(c.stdout[:800])
        return 1
    r = subprocess.run(['timeout', '60', OUT], capture_output=True, text=True)
    # Trailing newlines are not interesting; only the line content is.
    got = r.stdout.rstrip('\n')
    expected = EXPECTED.rstrip('\n')
    if got != expected:
        print("STDOUT MISMATCH")
        gl = got.split('\n')
        el = expected.split('\n')
        for i in range(max(len(gl), len(el))):
            g = gl[i] if i < len(gl) else '<none>'
            e = el[i] if i < len(el) else '<none>'
            if g != e:
                # A bare integer where text was expected is the pointer bug.
                note = '   <-- POINTER, not text' if g.replace(' ', '').isdigit() and not e.replace(' ', '').isdigit() else ''
                print(f"  line {i}: got {g!r}  want {e!r}{note}")
        return 1
    if r.returncode != 0:
        print(f"rc={r.returncode} with correct output")
        return 1
    print("run_string_params: PASS")
    return 0


if __name__ == '__main__':
    sys.exit(main())
