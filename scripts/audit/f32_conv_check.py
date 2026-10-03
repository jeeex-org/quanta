"""Compare lib/std/gguf.quanta's f32_to_f64 against Python, element by element.

The Quanta version is correct for the FIRST call and wrong for the rest, so a
single-value spot check passes and a tensor decode is wrong from element 1 on.
This drives the real function over a table of f32 bit patterns and prints
got/want so the first divergence is visible.

Usage:  python3 scripts/audit/f32_conv_check.py
Writes /tmp/f32_conv_probe.quanta, compiles it, runs it, diffs.
"""
import struct
import subprocess
import os
import sys

REPO = '/opt/tali/quanta'
QC = os.path.join(REPO, 'compiler', open(os.path.join(REPO, 'VERSION')).read().strip(),
                  'bin', 'x86', 'qc')

# f32 bit patterns chosen to hit every branch of f32_to_f64:
#   +0, -0, smallest subnormal, largest subnormal, smallest normal,
#   1.0, -1.0, 2.0, -2.0, 2.25, 2.375, 1.9140625, pi-ish, 1e-38, 1e38,
#   max finite, +inf, -inf, NaN
PATTERNS = [
    0x00000000,  # +0.0
    0x80000000,  # -0.0
    0x00000001,  # smallest subnormal
    0x007FFFFF,  # largest subnormal
    0x00800000,  # smallest normal
    0x3F800000,  # 1.0
    0xBF800000,  # -1.0
    0x40000000,  # 2.0
    0xC0000000,  # -2.0
    0x40100000,  # 2.25
    0x40180000,  # 2.375
    0x3F580000,  # 0.854166... (exp 0x7E? -> 0x7B=123)
    0x40490FDB,  # pi
    0x00800001,  # just above smallest normal
    0x0B800000,  # 2^-100 ish
    0x7F7FFFFF,  # max finite f32
    0xFF7FFFFF,  # -max finite f32
    0x7F800000,  # +inf
    0xFF800000,  # -inf
    0x7FC00000,  # NaN
]


def f32_to_f64_py(bits):
    """Widen an f32 bit pattern to f64, preserving NaN-ness and sign of zero."""
    b = struct.pack('<I', bits)
    return struct.unpack('<f', b)[0]


def bits64(x):
    return struct.unpack('<q', struct.pack('<d', x))[0]


def main():
    lines = []
    lines.append('import std/gguf')
    lines.append('')
    lines.append('fn main() {')
    lines.append('    let s = mem_alloc(%d)' % (4 * len(PATTERNS)))
    for i, pat in enumerate(PATTERNS):
        for k in range(4):
            lines.append('    mem_store8(s + %d, %d)' % (i * 4 + k, (pat >> (8 * k)) & 0xFF))
    for i in range(len(PATTERNS)):
        lines.append('    mem_store(mem_alloc(8) + %d, 0)' % 0) if False else None
    lines.append('    let o = mem_alloc(%d)' % (8 * len(PATTERNS)))
    # One buffer per element, so a wrong store cannot be masked by the next.
    lines.append('    let i = 0')
    lines.append('    while i < %d {' % len(PATTERNS))
    lines.append('        mem_store(o + i * 8, f32_to_f64(s + i * 4))')
    lines.append('        i = i + 1')
    lines.append('    }')
    lines.append('    let k = 0')
    lines.append('    while k < %d {' % len(PATTERNS))
    lines.append('        print("idx ")')
    lines.append('        println(k)')
    lines.append('        print("in ")')
    lines.append('        println(mem_load(s + k * 4) / 1)')
    lines.append('        print("bits ")')
    lines.append('        println(f64bits(mem_load(o + k * 8)))')
    lines.append('        k = k + 1')
    lines.append('    }')
    lines.append('    return 0')
    lines.append('}')

    src = '/tmp/f32_conv_probe.quanta'
    binp = '/tmp/f32_conv_probe'
    with open(src, 'w') as f:
        f.write('\n'.join(lines) + '\n')
    if os.path.exists(binp):
        os.remove(binp)
    c = subprocess.run(['timeout', '500', QC, src, binp], capture_output=True,
                       text=True, cwd=REPO)
    if not os.path.exists(binp):
        print('COMPILE-FAIL')
        print(c.stdout[:400])
        return 1
    r = subprocess.run(['timeout', '120', binp], capture_output=True, text=True)
    got = {}
    cur = {}
    for line in r.stdout.split('\n'):
        line = line.strip()
        if line.startswith('idx '):
            cur = {'i': int(line.split()[1])}
        elif line.startswith('bits ') and cur:
            cur['bits'] = int(line.split()[1])
            got[cur['i']] = cur['bits']
            cur = {}

    bad = 0
    for i, pat in enumerate(PATTERNS):
        want_val = f32_to_f64_py(pat)
        want = bits64(want_val)
        have = got.get(i)
        ok = have == want
        # A NaN has no single correct bit pattern -- any NaN will do, but only a
        # NaN. Test the f32's own EXPONENT field being all ones with a non-zero
        # mantissa. A RANGE test over [0x7F800000, 0xFFFFFFFF] is wrong: it
        # swallows every negative float (-0.0, -1.0, -2.0, -max), which is how
        # this checker first reported four mismatches on values the library
        # decoded correctly.
        exp = (pat >> 23) & 0xFF
        mant = pat & 0x7FFFFF
        is_nan = exp == 0xFF and mant != 0
        if is_nan:
            ok = have is not None and ((have >> 52) & 0x7FF) == 0x7FF \
                and (have & 0xFFFFFFFFFFFFF) != 0
        if not ok:
            bad += 1
        label = 'f32 0x%08X = %-14r' % (pat, want_val)
        print('  %-34s got %-22s want %-22s %s'
              % (label, have, want, 'ok' if ok else 'MISMATCH'))
    print('\n%d mismatches of %d' % (bad, len(PATTERNS)))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())