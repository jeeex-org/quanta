#!/usr/bin/env python3
"""Independent oracle for read_tensor_f64().

Pure stdlib. Parses GGUF v3 with mmap and dequantizes F32/F16/Q4_K/Q6_K
independently of lib/std/gguf.quanta, so its numbers are a genuine second
opinion rather than a restatement of the same code.

Prints, for each (model, tensor) probe, the same summary the native test
prints: first 6 values, sum, sumsq, min, max over the probed prefix.

usage: python3 scripts/audit/read_formats_oracle.py [NPROBE]
"""
import struct
import sys
import mmap

Q4_PATH = '/opt/ai/models/quanta/QUANTA-LFM2.5-2.6Bv1-Q4_K_M.gguf'
F16_PATH = '/opt/ai/models/quanta/QUANTA-LFM2.5-2.6Bv1.gguf'

ALIGN = 32


class Gguf:
    def __init__(self, path):
        self.f = open(path, 'rb')
        self.m = mmap.mmap(self.f.fileno(), 0, access=mmap.ACCESS_READ)
        magic, ver = struct.unpack_from('<II', self.m, 0)
        assert magic == 0x46554747, 'bad magic'
        o = 8
        self.ntens, self.nkv = struct.unpack_from('<QQ', self.m, o)
        o += 16
        for _ in range(self.nkv):
            o = self._skip_kv(o)
        self.infos = []
        for _ in range(self.ntens):
            name, o = self._rstr(o)
            nd = struct.unpack_from('<I', self.m, o)[0]
            o += 4
            dims = struct.unpack_from('<%dQ' % nd, self.m, o)
            o += 8 * nd
            tt = struct.unpack_from('<I', self.m, o)[0]
            o += 4
            toff = struct.unpack_from('<Q', self.m, o)[0]
            o += 8
            self.infos.append((name, dims, tt, toff))
        self.data = (o + ALIGN - 1) // ALIGN * ALIGN

    def _rstr(self, o):
        n = struct.unpack_from('<Q', self.m, o)[0]
        o += 8
        return self.m[o:o + n].decode('utf-8', 'replace'), o + n

    def _rval(self, o, t):
        # Standard GGUF metadata types:
        # 0 u8 1 i8 2 u16 3 i16 4 u32 5 i32 6 f32 7 bool 8 string 9 array
        # 10 u64 11 i64 12 f64
        if t == 8:
            s, o = self._rstr(o)
            return s, o
        if t == 9:
            et = struct.unpack_from('<I', self.m, o)[0]
            o += 4
            cnt = struct.unpack_from('<Q', self.m, o)[0]
            o += 8
            arr = []
            for _ in range(cnt):
                v, o = self._rval(o, et)
                arr.append(v)
            return arr, o
        fmt, sz = {0: ('<B', 1), 1: ('<b', 1), 2: ('<H', 2), 3: ('<h', 2),
                   4: ('<I', 4), 5: ('<i', 4), 6: ('<f', 4), 7: ('<?', 1),
                   10: ('<Q', 8), 11: ('<q', 8), 12: ('<d', 8)}[t]
        v = struct.unpack_from(fmt, self.m, o)[0]
        return v, o + sz

    def _skip_kv(self, o):
        _, o = self._rstr(o)
        t = struct.unpack_from('<I', self.m, o)[0]
        o += 4
        _, o = self._rval(o, t)
        return o

    def find(self, name):
        for i, (nm, dims, tt, off) in enumerate(self.infos):
            if nm == name:
                return i
        return -1

    def meta(self, i):
        return self.infos[i][1], self.infos[i][2], self.infos[i][3]

    def nelem(self, dims):
        n = 1
        for d in dims:
            n *= d
        return n

    # --- dequantizers (written from the GGUF block layouts, not from the .quanta) ---
    def deq_f32(self, base, n):
        a = struct.unpack_from('<%df' % n, self.m, base)
        return [float(x) for x in a]

    def deq_f16(self, base, n):
        a = struct.unpack_from('<%de' % n, self.m, base)
        return [float(x) for x in a]

    def deq_q4k(self, base, n):
        # Q4_K superblock = 144 bytes -> 256 weights:
        #   +0   f16 d      super-block scale for the 6-bit sub-scales
        #   +2   f16 dmin   super-block scale for the 6-bit sub-mins
        #   +4   u8  sc[12] 8 x (6-bit scale, 6-bit min), bit-packed
        #   +16  u8  qs[128] 4-bit quants
        #
        # Element ORDER is not interleaved. dequantize_row_q4_K() walks the
        # block in 64-element chunks, and within a chunk writes all 32 LOW
        # nibbles (using sub-scale `is`) and then all 32 HIGH nibbles (using
        # sub-scale `is+1`):
        #     for l in 0..31: y[l]        = d1 * (q[l] & 0xF) - m1
        #     for l in 0..31: y[32 + l]   = d2 * (q[l] >>  4) - m2
        # Interleaving the two nibbles per byte instead puts every element in
        # the wrong place -- the values stay plausible, which is why this is
        # easy to miss, but they do not correspond to the right weights.
        out = []
        nblk = (n + 255) // 256
        for b in range(nblk):
            o = base + b * 144
            d = _f16(self.m, o)
            dmin = _f16(self.m, o + 2)
            sc = self.m[o + 4:o + 16]
            qs = self.m[o + 16:o + 144]
            scales, mins = _unpack_q4k_k4(sc, d, dmin)
            is_ = 0
            for j in range(0, 128, 32):
                d1 = scales[is_]
                m1 = mins[is_]
                d2 = scales[is_ + 1]
                m2 = mins[is_ + 1]
                for l in range(32):
                    out.append(d1 * (qs[j + l] & 0xF) - m1)
                for l in range(32):
                    out.append(d2 * (qs[j + l] >> 4) - m2)
                is_ += 2
        return out[:n]

    def deq_q6k(self, base, n):
        # Q6_K superblock = 210 bytes -> 256 weights:
        #   +0   u8  ql[128]   low 4 bits
        #   +128 u8  qh[64]    high 2 bits
        #   +192 i8  scales[16] (8 per 128-element pass)
        #   +208 f16 d
        #
        # The reference writes FOUR SCATTERED groups inside one loop over l:
        #     y[l]     = d * scales[is+0] * q1
        #     y[l+32]  = d * scales[is+2] * q2
        #     y[l+64]  = d * scales[is+4] * q3
        #     y[l+96]  = d * scales[is+6] * q4
        # with is += 8 every 16 iterations, so all 16 scale bytes are used and
        # the scale index reaches 15. Reading only the first 8 scale bytes, or
        # emitting the four values contiguously instead of scattered, both
        # yield wrong weights.
        out = []
        nblk = (n + 255) // 256
        for b in range(nblk):
            o = base + b * 210
            ql = self.m[o:o + 128]
            qh = self.m[o + 128:o + 192]
            sc = struct.unpack('<16b', self.m[o + 192:o + 208])
            d = _f16(self.m, o + 208)
            y = [0.0] * 256
            for npass in range(2):
                qlo = ql[npass * 64:npass * 64 + 64]
                qhi = qh[npass * 32:npass * 32 + 32]
                # Each 128-element pass advances the scale pointer by 8, and
                # within a pass `is = l // 16` picks which half (0 or 1) of that
                # 8-byte group is used. With the +0/+2/+4/+6 strides this covers
                # all 16 scale bytes: 0..6 for pass 0 and 8..14 for pass 1.
                # Treating `is` itself as the absolute byte index (l//16 * 8)
                # reads past the scale array into the trailing `d`.
                for l in range(32):
                    is_ = npass * 8 + (l // 16)
                    h = qhi[l]
                    q1 = ((qlo[l] & 0xF) | ((h & 3) << 4)) - 32
                    q2 = ((qlo[l + 32] & 0xF) | (((h >> 2) & 3) << 4)) - 32
                    q3 = ((qlo[l] >> 4) | (((h >> 4) & 3) << 4)) - 32
                    q4 = ((qlo[l + 32] >> 4) | (((h >> 6) & 3) << 4)) - 32
                    y[npass * 128 + l] = d * sc[is_ + 0] * q1
                    y[npass * 128 + l + 32] = d * sc[is_ + 2] * q2
                    y[npass * 128 + l + 64] = d * sc[is_ + 4] * q3
                    y[npass * 128 + l + 96] = d * sc[is_ + 6] * q4
            out.extend(y)
        return out[:n]

    def read(self, i, n):
        dims, tt, off = self.meta(i)
        base = self.data + off
        if tt == 0:
            return self.deq_f32(base, n)
        if tt == 1:
            return self.deq_f16(base, n)
        if tt == 12:
            return self.deq_q4k(base, n)
        if tt == 14:
            return self.deq_q6k(base, n)
        raise Exception('unsupported dtype %d' % tt)


def fmt_key(t):
    return {0: '<b', 1: '<B', 2: '<h', 3: '<H', 4: '<i', 5: '<I',
            6: '<f', 7: '<?', 8: '<d'}[t]


def _f16(m, o):
    return struct.unpack_from('<e', m, o)[0]


def _unpack_q4k_k4(b, d, dmin):
    """12 packed bytes -> 8 sub-block scales and 8 mins.

    get_scale_min_k4() from ggml-quants.c:
        j < 4:  scale = b[j]     & 63
                min   = b[j + 4] & 63
        j >= 4: scale = (b[j + 4] & 0xF) | ((b[j - 4] >> 6) << 4)
                min   = (b[j + 4] >>  4) | ((b[j - 0] >> 6) << 4)
    Note the j < 4 min is masked with 63, NOT shifted right by 6 -- using >> 6
    here silently loses every min and produces all-positive garbage weights.
    """
    sc = [0] * 8
    mn = [0] * 8
    for j in range(4):
        sc[j] = (b[j] & 63) * d
        mn[j] = (b[j + 4] & 63) * dmin
    for j in range(4, 8):
        sc[j] = ((b[j + 4] & 0xF) | ((b[j - 4] >> 6) << 4)) * d
        mn[j] = ((b[j + 4] >> 4) | ((b[j] >> 6) << 4)) * dmin
    return sc, mn


def _unpack_q6k_scales(b):
    """16 bytes -> 16 signed 6-bit scales (get_scale_min_k4 packing)."""
    out = []
    i = 0
    n = 0
    while i < 16 and n < 16:
        if i % 3 == 0 and i + 3 <= 16:
            a, bb, c = b[i], b[i + 1], b[i + 2]
            out += [a & 63, bb & 63, (bb >> 6) | ((c & 0xF) << 2)]
            i += 3
            n += 3
        else:
            out.append(b[i] & 63)
            i += 1
            n += 1
    return [x - 32 if x > 31 else x for x in out[:16]]


def summarize(vals):
    n = len(vals)
    s = 0.0
    ss = 0.0
    mn = vals[0]
    mx = vals[0]
    for x in vals:
        s += x
        ss += x * x
        if x < mn:
            mn = x
        if x > mx:
            mx = x
    return dict(n=n, first=[float(x) for x in vals[:6]],
                s=s, ss=ss, mn=mn, mx=mx)


PROBES = [
    (Q4_PATH, 'blk.0.ffn_norm.weight', 2048),
    (Q4_PATH, 'blk.0.ffn_gate.weight', 8192),
    # The Q6_K window MUST match the native test's 4096 elements. It read 8192
    # here before, which made the two sides reduce different prefixes and report
    # different sums (0.707706 vs -0.074374) -- a window mismatch, not a
    # dequantizer defect.
    (Q4_PATH, 'blk.0.ffn_down.weight', 4096),
    (Q4_PATH, 'blk.0.shortconv.conv.weight', 6144),
    (Q4_PATH, 'token_embd_norm.weight', 2048),
    (F16_PATH, 'blk.0.ffn_norm.weight', 2048),
    (F16_PATH, 'blk.0.ffn_gate.weight', 8192),
    (F16_PATH, 'token_embd_norm.weight', 2048),
]

if __name__ == '__main__':
    cache = {}
    for path, name, n in PROBES:
        if path not in cache:
            cache[path] = Gguf(path)
        g = cache[path]
        i = g.find(name)
        if i < 0:
            print('MISSING', name)
            continue
        dims, tt, _ = g.meta(i)
        vals = g.read(i, n)
        r = summarize(vals)
        tag = 'F16' if 'Q4_K_M' not in path else 'Q4'
        print('%s %s dtype=%d dims=%s n=%d' % (tag, name, tt, list(dims), r['n']))
        print('   first=%s' % ['%.6f' % x for x in r['first']])
        print('   sum=%.6f sumsq=%.6f min=%.6f max=%.6f'
              % (r['s'], r['ss'], r['mn'], r['mx']))