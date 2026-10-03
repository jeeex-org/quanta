"""Ground truth for the remaining GGML decoders, by COMPILING the reference C.

The Quanta decoders are transcribed by hand from ggml-quants.c, so a misread
layout produces a plausible wrong answer rather than a build failure. This builds
just the decoder FUNCTIONS out of that file -- extracted verbatim, not
reimplemented -- links them against a tiny driver, and dumps raw f64 bit patterns
for a deterministic synthetic block. Same arithmetic, compiled by the host
compiler instead of by Quanta and instead of by my reading of it.

Only the five needed functions are extracted. The whole ggml-quants.c cannot be
compiled here: it includes ggml-impl.h, which needs AVX intrinsics headers the
image lacks, and its fp16 conversion is POWER8 inline assembly.

Types covered: Q8_0 (type 8), Q5_K (type 13), and F16 (type 1). The f16 widening
in the driver is a self-contained IEEE 754 half->float, which is exact by spec
and so carries no transcription risk -- unlike the k-quant bit layouts.

Usage:  python3 scripts/audit/dequant_oracle.py [n_values]
"""
import os
import re
import struct
import subprocess
import sys
import tempfile

SRC = '/opt/tali/ti/ai/LINKS_CLONE_GH/PowerInfer'
QUANTS_C = os.path.join(SRC, 'ggml-quants.c')
QUANTS_H = os.path.join(SRC, 'ggml-quants.h')

FUNCS = ['get_scale_min_k4', 'dequantize_row_q8_0', 'dequantize_row_q4_K',
         'dequantize_row_q5_K', 'dequantize_row_q6_K']
BLOCKS = ['block_q8_0', 'block_q4_K', 'block_q5_K', 'block_q6_K']

DRIVER = r'''
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <assert.h>

typedef uint16_t ggml_fp16_t;

/* Defined below; declared here because the extracted ggml functions use the macro
   above this point. */
static float f16_to_f32(ggml_fp16_t h);

/* ggml's own alias. In ggml-impl.h it is POWER8 inline assembly; here it points
   at the self-contained IEEE 754 conversion defined below, which produces
   identical results -- every binary16 is exactly representable in binary32, so
   there is nothing to round. */
#define GGML_FP16_TO_FP32(x) f16_to_f32(x)

/* Block-size macros the typedefs use. The 256-wide k-quant variant is the one
   PowerInfer builds by default (GGML_QKK_64 is not defined), so QK_K = 256. */
#define QK4_0 32
#define QK4_1 32
#define QK5_0 32
#define QK5_1 32
#define QK8_0 32
#define QK8_1 32
#define QK_K 256
#define K_SCALE_SIZE 12

@@EXTRACTED@@

/* IEEE 754 binary16 -> binary32.
   The host compiler does this conversion: binary16 -> binary32 is exact and
   fully specified by IEEE 754, so there is nothing to transcribe and nothing to
   get wrong. An earlier hand-written version here was off by one in the
   subnormal exponent normalisation -- it produced 2^-25 for mant=1 instead of
   2^-24 -- which is exactly the class of bug this oracle exists to catch, so it
   does not write one. */
static float f16_to_f32(ggml_fp16_t v) {
    _Float16 h;
    uint16_t raw = (uint16_t)v;
    float f;
    memcpy(&h, &raw, 2);
    f = (float)h;
    return f;
}

static void put16(uint8_t *p, uint16_t v) { p[0] = (uint8_t)(v & 0xFF); p[1] = (uint8_t)(v >> 8); }

static void dump(const char *tag, const float *y, int n) {
    for (int i = 0; i < n; i++) {
        double d = (double)y[i];
        uint64_t b;
        memcpy(&b, &d, 8);
        printf("%s %d %llu\n", tag, i, (unsigned long long)b);
    }
}

int main(void) {
    /* --- F16: the scale every k-quant block starts with --- */
    {
        static const uint16_t pats[] = {0x0000, 0x8000, 0x3C00, 0xBC00, 0x7BFF,
                                        0x0400, 0x0001, 0x7C00, 0xFC00, 0x7E00,
                                        0x3800, 0x4900, 0x6B4D, 0x0B57};
        for (unsigned i = 0; i < sizeof(pats)/sizeof(pats[0]); i++) {
            float v = f16_to_f32(pats[i]);
            double d = (double)v;
            uint64_t b;
            memcpy(&b, &d, 8);
            printf("F16 %u %llu\n", pats[i], (unsigned long long)b);
        }
    }

    /* --- Q8_0: 34 B, d f16@+0, int8 qs[32]@+2 --- */
    {
        block_q8_0 blk;
        memset(&blk, 0, sizeof(blk));
        uint8_t *p = (uint8_t *)&blk;
        put16(p, 0x3800);                       /* d = 0.5 */
        for (int i = 0; i < 32; i++) blk.qs[i] = (int8_t)(i - 16);
        float y[32];
        dequantize_row_q8_0(&blk, y, 32);
        dump("Q8_0", y, 32);
    }

    /* --- Q5_K: 176 B, d@+0 dmin@+2 scales[12]@+4 qh[32]@+16 qs[128]@+48 --- */
    {
        block_q5_K blk;
        memset(&blk, 0, sizeof(blk));
        uint8_t *p = (uint8_t *)&blk;
        put16(p + 0, 0x3800);                   /* d    = 0.5 */
        put16(p + 2, 0x3800);                   /* dmin = 0.5 */
        /* Q5_K is Q4_K plus the qh high-bit plane: qh[32] @16, qs[128] @48.
           Writing qs at +16 and qh at +144 is Q4_K's layout and made the oracle
           and the Quanta decoder read different fields -- the disagreement looked
           like a decoder bug and was not one. 176 = 2+2+12+32+128, and only
           this arrangement sums correctly. */
        for (int i = 0; i < 12; i++) p[4 + i] = 0x21;   /* six-bit (scale,min) pairs */
        for (int i = 0; i < 32; i++) p[16 + i] = (uint8_t)(i * 5);   /* qh  */
        for (int i = 0; i < 128; i++) p[48 + i] = (uint8_t)(i * 7);  /* qs  */
        float y[256];
        dequantize_row_q5_K(&blk, y, 256);
        dump("Q5_K", y, 256);
    }

    /* --- Q4_K and Q6_K regression: unchanged behaviour must be preserved --- */
    {
        block_q4_K blk;
        memset(&blk, 0, sizeof(blk));
        uint8_t *p = (uint8_t *)&blk;
        put16(p + 0, 0x3800);
        put16(p + 2, 0x3800);
        for (int i = 0; i < 12; i++) p[4 + i] = 0x21;
        for (int i = 0; i < 128; i++) p[16 + i] = (uint8_t)(i * 7);
        float y[256];
        dequantize_row_q4_K(&blk, y, 256);
        dump("Q4_K", y, 256);
    }
    {
        block_q6_K blk;
        memset(&blk, 0, sizeof(blk));
        uint8_t *p = (uint8_t *)&blk;
        /* ql[128] @0, qh[64] @128, scales[16] @192, d f16 @208. d is LAST --
           at 208, not 192. Writing it at 192 landed it on scales[0..1] and made
           every value -0.0, which looked like a decoder disagreement. */
        for (int i = 0; i < 128; i++) p[i] = (uint8_t)(i * 7);
        for (int i = 0; i < 64; i++) p[128 + i] = (uint8_t)(i * 5);
        for (int i = 0; i < 16; i++) blk.scales[i] = (int8_t)(33 - i);
        put16(p + 208, 0x3800);
        float y[256];
        dequantize_row_q6_K(&blk, y, 256);
        dump("Q6_K", y, 256);
    }
    return 0;
}
'''


def extract(path, names, kinds):
    t = open(path).read()
    out = []
    for n in names:
        if kinds == 'type':
            # Every k-quant block appears TWICE: once in the GGML_QKK_64 branch and
            # once in the #else. A greedy `typedef struct {[^}]*} NAME;` spans from
            # the FIRST typedef to the LAST name and silently grabs half the
            # header; and rfind() lands on whichever branch comes first, which is
            # the 64-wide one. That variant has the WRONG LAYOUT: block_q4_K
            # becomes d[2] + scales[2] + qs[32] = 38 B instead of
            # d + dmin + scales[12] + qs[128] = 144 B. The model's own Q4_K block
            # size (144 B) is what proves which branch is in use, so take the LAST
            # occurrence -- the #else, i.e. QK_K = 256.
            spans = []
            for m in re.finditer(r'\}\s*' + n + r'\s*;', t):
                i = m.start()
                j = t.rfind('typedef struct', 0, i)
                spans.append(t[j:m.end()])
            if not spans:
                raise SystemExit('could not extract %s from %s' % (n, path))
            chunk = spans[-1]
        else:
            m = re.search(r'^(?:static\s+inline\s+)?void\s+%s\s*\(.*?^\}' % n, t, re.S | re.M)
            if not m:
                raise SystemExit('could not extract %s from %s' % (n, path))
            chunk = m.group(0)
        if kinds == 'type':
            # static_assert needs C11 and adds nothing here.
            chunk = re.sub(r'\n?static_assert\([^;]*\);', '', chunk)
        out.append(chunk)
    return out


def build_oracle(work=None):
    """Compile the extracted reference decoders and return the exe path."""
    if work is None:
        work = tempfile.mkdtemp(prefix='qoracle')
    types = extract(QUANTS_H, BLOCKS, 'type')
    funcs = extract(QUANTS_C, FUNCS, 'fn')
    body = DRIVER.replace('@@EXTRACTED@@', '\n'.join(types + funcs))
    src = os.path.join(work, 'oracle.c')
    with open(src, 'w') as f:
        f.write(body)
    exe = os.path.join(work, 'oracle')
    p = subprocess.run(['cc', '-std=c11', '-O0', '-o', exe, src, '-lm'],
                       capture_output=True, text=True)
    if p.returncode != 0:
        sys.stderr.write(p.stdout + p.stderr)
        return None
    return exe


def run_oracle(want):
    """Return {tag: [signed f64 bit patterns]} from the compiled reference."""
    exe = build_oracle()
    if exe is None:
        raise SystemExit('oracle build failed')
    p = subprocess.run([exe], capture_output=True, text=True)
    got = {}
    for line in p.stdout.strip().split('\n'):
        tag, i, bits = line.split()
        got.setdefault(tag, []).append((int(i), int(bits)))
    out = {}
    for tag, rows in got.items():
        vals = [int(b) for _, b in rows[:want]]
        out[tag] = [v - (1 << 64) if v >= (1 << 63) else v for v in vals]
    return out


def main():
    want = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    exe = build_oracle()
    if exe is None:
        print('BUILD-FAILED')
        return 1
    p = subprocess.run([exe], capture_output=True, text=True)
    if p.returncode != 0:
        print('RUN-FAILED')
        sys.stderr.write(p.stderr)
        return 1

    unsigned = {}
    for line in p.stdout.strip().split('\n'):
        tag, i, bits = line.split()
        unsigned.setdefault(tag, []).append((int(i), int(bits)))

    def signed(bits):
        # -0.0's pattern is 2**63, which does not fit a signed q. Fold the top
        # bit, which is exactly how the two sides store it: C prints uint64,
        # Quanta prints i64.
        return bits - (1 << 64) if bits >= (1 << 63) else bits

    def as_f64(bits):
        return struct.unpack('<d', struct.pack('<q', signed(bits)))[0]

    def is_nan(bits):
        return ((bits >> 52) & 0x7FF) == 0x7FF and (bits & ((1 << 52) - 1)) != 0

    def show(tag, note, keyed_by_pattern=False):
        rows = unsigned.get(tag, [])
        print('=== %s %s ===' % (tag, note))
        for i, b in rows[:want]:
            tagstr = '0x%04X' % i if keyed_by_pattern else '[%3d]' % i
            note2 = '  NaN' if is_nan(b) else ''
            print('  %s -> bits=%-22s value=%r%s'
                  % (tagstr, signed(b), as_f64(b), note2))
        print('  ... %d rows total' % len(rows))
        print()

    show('F16', '(type 1) 1 value / 2 B -> f64', keyed_by_pattern=True)
    show('Q8_0', '(type 8) 32 values / 34 B, d f16@+0, int8 qs[32]@+2')
    show('Q4_K', '(type 12) 256 values / 144 B  [regression]')
    show('Q5_K', '(type 13) 256 values / 176 B, d@0 dmin@2 scales[12]@4 qh[32]@16 qs[128]@48')
    show('Q6_K', '(type 14) 256 values / 210 B  [regression]')

    print('--- MACHINE ---')
    for tag in ['F16', 'Q8_0', 'Q4_K', 'Q5_K', 'Q6_K']:
        for i, b in unsigned.get(tag, [])[:want]:
            print('%s %d %d' % (tag, i, signed(b)))
    print('# F16 rows are keyed by the 16-bit pattern, not a sequential index.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
