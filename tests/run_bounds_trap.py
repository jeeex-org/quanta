#!/usr/bin/env python3
"""Assert that out-of-range indexing TRAPS rather than reading adjacent memory.

A SIGILL from an out-of-range index is not a missing bounds check -- it IS the
check. codegen.quanta's IR_IDX handler emits `cmp [rax], rcx ; jb +2 ; ud2` in both
the string and the array branch, and IR_ISTORE does the same.

That SIGILL kills the process, so each case has to be its own program; the
in-range half lives in tests/test_indexing_bounds.quanta. The point of both is
that a validator must be SELECTIVE: every valid index works (there) and every
invalid one traps (here). A validator that accepts everything is as broken as one
that rejects everything.

Usage:  python3 tests/run_bounds_trap.py [path/to/qc]
"""
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    REPO, 'compiler', open(os.path.join(REPO, 'VERSION')).read().strip(),
    'bin', 'x86', 'qc')

# (name, program, expected stdout before the trap)
CASES = [
    # `want_prefix` is what the body prints BEFORE it traps. Most bodies do not
    # print anything, so their prefix is empty -- the in-range coverage is
    # tests/test_indexing_bounds.quanta's job. These cases assert only that the
    # trap fires, which is the half that cannot live in-process.
    ('array one past the end',
     'let a = [10, 20, 30]\nprintln(a[3])', ''),
    ('array two past the end',
     'let a = [10, 20, 30]\nprintln(a[9])', ''),
    ('array negative index',
     'let a = [10, 20, 30]\nprintln(a[0 - 1])', ''),
    ('empty array index',
     'let a = []\nprintln(a[0])', ''),
    ('array read at runtime index',
     'let a = [10, 20, 30]\nlet i = 0\nwhile i < 3 { println(a[i]) i = i + 1 }\nprintln(a[3])',
     '10\n20\n30\n'),
    ('array write out of range',
     'let a = [10, 20, 30]\na[3] = 99', ''),
    ('string one past the end',
     'let s = "abc"\nprintln(s[3])', ''),
    ('string far out of range',
     'let s = "abc"\nprintln(s[99])', ''),
    ('string negative index',
     'let s = "abc"\nprintln(s[0 - 1])', ''),
    # len() of a string element goes through the pointer, so a string-array
    # element prints its LENGTH (3), not the pointer -- unless the index is out
    # of range, which is what traps here.
    ('string array element out of range',
     'let p = ["one", "two"]\nprintln(len(p[0]))\nprintln(len(p[2]))', '3\n'),
]


def main():
    failures = []
    for name, body, want_prefix in CASES:
        src = 'fn main() {\n    ' + body + '\n    return 0\n}\n'
        path = '/tmp/bounds_case.quanta'
        out = '/tmp/bounds_case_bin'
        with open(path, 'w') as f:
            f.write(src)
        if os.path.exists(out):
            os.remove(out)
        c = subprocess.run(['timeout', '400', QC, path, out],
                           capture_output=True, text=True, cwd=REPO)
        if not os.path.exists(out):
            failures.append(f'{name}: COMPILE-FAIL -- {c.stdout.strip()[:120]}')
            continue
        r = subprocess.run(['timeout', '30', out], capture_output=True, text=True)
        if r.returncode == 0:
            failures.append(
                f'{name}: exited 0, so the trap did NOT fire -- this index is '
                f'reading memory it should not. stdout={r.stdout!r}')
        elif r.returncode != -4:
            failures.append(
                f'{name}: rc={r.returncode}, expected -4 (SIGILL). '
                f'stdout={r.stdout!r}')
        elif not r.stdout.startswith(want_prefix):
            failures.append(
                f'{name}: trapped as expected but the in-range output was '
                f'wrong. got {r.stdout!r} want prefix {want_prefix!r}')
        else:
            print(f'  {name:34} traps (rc=-4) after correct in-range output')

    if failures:
        print('run_bounds_trap: FAIL')
        for f in failures:
            print('  ' + f)
        return 1
    print('run_bounds_trap: PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
