#!/usr/bin/env python3
"""Generate the f16/f32 conversion fixtures from the linked ggml oracle.

WHY THIS EXISTS
---------------
The new f16/f32 language types must round EXACTLY like the reference library -
zero tolerance, not "close enough". A hand-written expectation is a third
implementation that can disagree with both sides (and did, twice, on the quant
formats). So every fixture here is produced by calling the real exported symbols
of the installed libggml-base:

    ggml_fp16_to_fp32(ggml_fp16_t) -> float        (f16 -> f32, exact widening)
    ggml_fp32_to_fp16(float)       -> ggml_fp16_t  (f32 -> f16, RNE narrowing)

plus the host compiler's own `(float)d` for the f64 -> f32 narrowing, which
ggml has no entry point for. test_suites/scripts/fp16_conv_oracle.c is that
program; this script compiles it, drives it, and writes the fixtures.

The fixtures are COMMITTED (tests/fixtures/*.bin is un-ignored by .gitignore on
purpose) so a fresh clone re-runs the comparison without linking anything.

COVERAGE
--------
  fp16_to_f32_table.bin      EXHAUSTIVE: all 65,536 f16 bit patterns.
  fp32_to_fp16_cases.bin     all 512 (sign x exponent) combinations x 128
    + ..._expect.bin         mantissa patterns (every boundary/tie shape, then
                             LCG-filled), PLUS an exhaustive sweep of all 8,192
                             low-13-bit patterns (the bits f16 drops, including
                             the round bit and the sticky bits) at the four
                             exponents where the boundary behaviour changes:
                             0 (f32 subnormal), 112 (f16 subnormal/normal),
                             143 (f16 finite/overflow), 254 (near inf).
  fp64_to_f32_cases.bin      all 4,096 (sign x exponent) combinations x 16
    + ..._expect.bin         mantissa patterns; exhaustive in the exponent,
                             boundary-and-random in the mantissa.

Usage:  python3 test_suites/scripts/gen_fp16_fixtures.py [--check]
        --check regenerates to a temp dir and compares against the committed
        fixtures instead of overwriting them (the audit that re-derives every
        committed expectation).
"""
import hashlib
import os
import struct
import subprocess
import sys
import tempfile

REPO = '/opt/tali/quanta'
FIX = os.path.join(REPO, 'tests', 'fixtures')
SP = '/home/tali/.local/lib/python3.12/site-packages'
ORACLE_C = os.path.join(REPO, 'test_suites', 'scripts', 'fp16_conv_oracle.c')

H2F = 'fp16_to_f32_table.bin'
F2H_C = 'fp32_to_fp16_cases.bin'
F2H_E = 'fp32_to_fp16_expect.bin'
D2F_C = 'fp64_to_f32_cases.bin'
D2F_E = 'fp64_to_f32_expect.bin'


class LCG:
    """Deterministic pseudo-random source, so a fixture can be regenerated and
    its spread audited. Numerical Recipes constants; 32-bit state."""

    def __init__(self, seed):
        self.s = seed & 0xFFFFFFFF

    def next(self):
        self.s = (1664525 * self.s + 1013904223) & 0xFFFFFFFF
        return self.s


def mantissa_patterns(rand, bits, count):
    """`count` mantissa values of `bits` width: the shapes a rounding
    implementation can get wrong first, then LCG-filled for spread."""
    full = (1 << bits) - 1
    half = 1 << (bits - 1)          # top mantissa bit only
    drop = bits - (10 if bits == 23 else 0)
    picks = [0, 1, 2, full, full - 1, half, half - 1, half + 1]
    if bits == 23:
        # the 13 bits f16 drops: the exact-tie bit, one below, one above, and
        # the all-ones/zero sticky extremes
        tie = 1 << (13 - 1)         # 0x1000
        for off in (-2, -1, 0, 1, 2, 0x1FFF, 0x2000, 0x2001):
            picks.append(tie + off)
        picks.append(0x7FE000)      # top 10 bits set (f16 max mantissa)
        picks.append(0x7FDFFF)
    else:
        tie = 1 << (29 - 1)         # f64 -> f32 drops 29 bits
        for off in (-2, -1, 0, 1, 2, (1 << 29) - 1, 1 << 29, (1 << 29) + 1):
            picks.append(tie + off)
    out = []
    seen = set()
    for p in picks:
        p &= full
        if p not in seen:
            seen.add(p)
            out.append(p)
    while len(out) < count:
        p = rand.next() & full
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out[:count]


def f32_to_f16_cases():
    rand = LCG(0xC0FFEE01)
    mans = mantissa_patterns(rand, 23, 128)
    cases = []
    for sign in (0, 1):
        for exp in range(256):
            base = (sign << 31) | (exp << 23)
            for m in mans:
                cases.append(base | m)
    # exhaustive low-13-bit sweep at the four boundary exponents
    for exp in (0, 112, 143, 254):
        for hm in (0x000, 0x7FE):
            for low in range(1 << 13):
                cases.append((exp << 23) | (hm << 13) | low)
    return cases


def f64_to_f32_cases():
    rand = LCG(0xF32F32F3)
    mans = mantissa_patterns(rand, 52, 16)
    cases = []
    for sign in (0, 1):
        for exp in range(2048):
            base = (sign << 63) | (exp << 52)
            for m in mans:
                cases.append(base | m)
    return cases


def build_oracle(tmp):
    exe = os.path.join(tmp, 'fp16_oracle')
    cmd = ['gcc', '-O2', '-w', '-o', exe, ORACLE_C,
           '-I' + os.path.join(SP, 'include'),
           '-L' + os.path.join(SP, 'lib64'),
           '-lggml-base', '-Wl,-rpath,' + os.path.join(SP, 'lib64'), '-lm']
    subprocess.run(cmd, check=True)
    return exe


def u32le(vals):
    return b''.join(struct.pack('<I', v & 0xFFFFFFFF) for v in vals)


def u64le(vals):
    return b''.join(struct.pack('<Q', v & 0xFFFFFFFFFFFFFFFF) for v in vals)


def main():
    check = '--check' in sys.argv
    outdir = tempfile.mkdtemp(prefix='fp16fix') if check else FIX
    os.makedirs(outdir, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix='fp16oracle')
    exe = build_oracle(tmp)

    # 1. exhaustive f16 -> f32
    subprocess.run([exe, 'h2f', os.path.join(outdir, H2F)], check=True)

    # 2. f32 -> f16
    c = f32_to_f16_cases()
    with open(os.path.join(outdir, F2H_C), 'wb') as f:
        f.write(u32le(c))
    subprocess.run([exe, 'f2h', os.path.join(outdir, F2H_C),
                    os.path.join(outdir, F2H_E)], check=True)

    # 3. f64 -> f32
    d = f64_to_f32_cases()
    with open(os.path.join(outdir, D2F_C), 'wb') as f:
        f.write(u64le(d))
    subprocess.run([exe, 'd2f', os.path.join(outdir, D2F_C),
                    os.path.join(outdir, D2F_E)], check=True)

    print('=== fixtures ===')
    rc = 0
    for name in (H2F, F2H_C, F2H_E, D2F_C, D2F_E):
        p = os.path.join(outdir, name)
        data = open(p, 'rb').read()
        md5 = hashlib.md5(data).hexdigest()
        line = '  %-28s %9d bytes  md5 %s' % (name, len(data), md5)
        if check:
            ref = os.path.join(FIX, name)
            same = os.path.exists(ref) and open(ref, 'rb').read() == data
            line += '  ' + ('MATCHES committed' if same else 'MISMATCH vs committed')
            if not same:
                rc = 1
        print(line)
    print('  f32->f16 cases: %d   f64->f32 cases: %d' % (len(c), len(d)))

    # A few headline values, printed so the fixture itself is inspectable.
    tbl = open(os.path.join(outdir, H2F), 'rb').read()
    exp = open(os.path.join(outdir, F2H_E), 'rb').read()
    print('=== spot checks (from the fixtures) ===')
    for pat in (0x0000, 0x0001, 0x03FF, 0x0400, 0x3C00, 0x7BFF, 0x7C00,
                0x7C01, 0x7E00, 0xFFFF):
        bits = struct.unpack_from('<I', tbl, pat * 4)[0]
        print('  f16 0x%04X -> f32 0x%08X' % (pat, bits))
    for i in (0, 1, 2, 3):
        cb = struct.unpack_from('<I', open(os.path.join(outdir, F2H_C), 'rb').read(), i * 4)[0]
        eb = struct.unpack_from('<H', exp, i * 2)[0]
        print('  f32 case[%d] 0x%08X -> f16 0x%04X' % (i, cb, eb))

    if check:
        print('=== --check: %s ===' % ('OK' if rc == 0 else 'FAILED'))
    return rc


if __name__ == '__main__':
    sys.exit(main())
