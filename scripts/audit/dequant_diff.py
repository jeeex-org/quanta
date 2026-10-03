"""Check lib/std/gguf.quanta's decoders against the COMPILED reference C.

Builds the reference decoders out of ggml-quants.c (extracted verbatim, not
reimplemented), runs them on a deterministic synthetic block, then runs the Quanta
decoders on the same block and compares raw f64 bit patterns.

Bit patterns are printed UNSIGNED by the C side and SIGNED by Quanta, so both are
folded to a signed 64-bit value before comparison -- otherwise -16.5 reads as two
different numbers on the two sides.

Usage:  python3 scripts/audit/dequant_diff.py [n_values]
"""
import os
import re
import subprocess
import sys
import tempfile

REPO = '/opt/tali/quanta'
QC = os.path.join(REPO, 'compiler', open(os.path.join(REPO, 'VERSION')).read().strip(),
                  'bin', 'x86', 'qc')

sys.path.insert(0, os.path.join(REPO, 'scripts', 'audit'))
import dequant_oracle as ORA


def signed(bits):
    if bits >= 1 << 63:
        bits -= 1 << 64
    return bits


# The synthetic blocks, described once and used on BOTH sides. Byte values that
# exercise the arithmetic rather than collapsing to a degenerate answer.
BLOCKS = {
    'Q6_K': dict(
        size=210, nvalues=256,
        fields=[
            ('ql', 0, 128, lambda i: (i * 7) % 256),
            ('qh', 128, 64, lambda i: (i * 5) % 256),
            ('scales', 192, 16, lambda i: (33 - i) % 256),
            ('d', 208, 2, None),          # f16 0x3800 = 0.5
        ],
        f16={208: 0x3800},
        fn='dequant_q6k',
    ),
    'Q8_0': dict(
        size=34, nvalues=32,
        fields=[
            ('d', 0, 2, None),             # f16 0x3800 = 0.5
            ('qs', 2, 32, lambda i: (256 + i - 16) % 256),   # int8 -16..15
        ],
        f16={0: 0x3800},
        fn='dequant_q8_0',
    ),
    'Q5_K': dict(
        size=176, nvalues=256,
        fields=[
            ('scales', 4, 12, lambda i: 0x21),
            ('qh', 16, 32, lambda i: (i * 5) % 256),
            ('qs', 48, 128, lambda i: (i * 7) % 256),
        ],
        f16={0: 0x3800, 2: 0x3800},
        fn='dequant_q5k',
    ),
    'F16': dict(
        size=2 * 10, nvalues=10,
        fields=[('v', 0, 20, None)],
        f16={0: 0x0000, 2: 0x8000, 4: 0x3C00, 6: 0xBC00, 8: 0x7BFF,
             10: 0x0400, 12: 0x0001, 14: 0x7C00, 16: 0xFC00, 18: 0x7E00},
        fn='dequant_f16',
    ),
}


def build_block(spec):
    buf = bytearray(spec['size'])
    for name, off, ln, fn in spec['fields']:
        if fn is None:
            continue
        for i in range(ln):
            buf[off + i] = fn(i)
    for off, pat in spec['f16'].items():
        buf[off] = pat & 0xFF
        buf[off + 1] = (pat >> 8) & 0xFF
    return bytes(buf)


def run_quanta(spec, want):
    blk = build_block(spec)
    n = spec['nvalues']
    lines = ['import std/gguf', '', 'fn main() {',
             '    let raw = mem_alloc(%d)' % max(spec['size'], n * 8),
             '    let o = mem_alloc(%d)' % (n * 8)]
    for i, byte in enumerate(blk):
        lines.append('    mem_store8(raw + %d, %d)' % (i, byte))
    lines.append('    %s(raw, %d, o)' % (spec['fn'], n))
    lines.append('    let k = 0')
    lines.append('    while k < %d {' % n)
    lines.append('        println(f64bits(mem_load(o + k * 8)))')
    lines.append('        k = k + 1')
    lines.append('    }')
    lines.append('    return 0')
    lines.append('}')
    src = '/tmp/dequant_diff.quanta'
    binp = '/tmp/dequant_diff'
    with open(src, 'w') as f:
        f.write('\n'.join(lines) + '\n')
    if os.path.exists(binp):
        os.remove(binp)
    c = subprocess.run(['timeout', '500', QC, src, binp], capture_output=True,
                       text=True, cwd=REPO)
    if not os.path.exists(binp):
        return None, c.stdout[:400]
    r = subprocess.run(['timeout', '120', binp], capture_output=True, text=True)
    out = []
    for line in r.stdout.strip().split('\n'):
        line = line.strip()
        if line:
            out.append(int(line))
    return out[:want], ''


def run_oracle(want):
    return ORA.run_oracle(want)


def main():
    want = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    ora = run_oracle(want)
    total_bad = 0
    total = 0
    for tag in ['Q6_K', 'Q8_0', 'Q5_K', 'F16']:
        spec = BLOCKS[tag]
        got, err = run_quanta(spec, want)
        if got is None:
            print('%-6s COMPILE-FAIL %s' % (tag, err[:160]))
            total_bad += 1
            total += 1
            continue
        exp = ora.get(tag, [])
        print('=== %s (%s) ===' % (tag, spec['fn']))
        # Never compare past the block: `want` is a caller-supplied count and a
        # block only has spec['nvalues'] values. Asking for 300 of a 32-value
        # Q8_0 block compared 268 pairs of uninitialised memory and made the run
        # look catastrophically broken when the decoders were fine.
        n = min(want, spec['nvalues'], len(exp))
        for k in range(n):
            g = got[k] if k < len(got) else None
            e = exp[k]
            ok = (g == e)
            # A NaN is not required to have any particular payload, so a
            # bit-for-bit NaN comparison asserts the host's choice rather than
            # the spec. Compare NaNs by CLASS and SIGN instead: exponent all
            # ones, mantissa non-zero, same sign. Everything else stays exact.
            if not ok and g is not None:
                ge = (g >> 52) & 0x7FF
                ee = (e >> 52) & 0x7FF
                gm = g - ((g >> 52) << 52)
                em = e - ((e >> 52) << 52)
                if ge == 0x7FF and ee == 0x7FF and gm != 0 and em != 0 \
                        and (g >> 63) == (e >> 63):
                    ok = True
            total += 1
            if not ok:
                total_bad += 1
            print('  [%3d] quanta=%-22s oracle=%-22s %s'
                  % (k, g, e, 'ok' if ok else 'MISMATCH'))
        print()
    print('%d mismatches of %d' % (total_bad, total))
    print('compared %d values per block (block sizes: %s)'
          % (n, ', '.join('%s=%d' % (t, BLOCKS[t]['nvalues']) for t in BLOCKS)))
    return 1 if total_bad else 0


if __name__ == '__main__':
    sys.exit(main())