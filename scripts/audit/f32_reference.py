"""Ground truth for the real model's F32 tensors.

Independent of lib/std/gguf.quanta so it can CHECK the library rather than
restate it. GGUF v3 layout (verified against scripts/audit/gguf_walk_reference.py
and the committed test_gguf_metadata.quanta):

  header   4s magic, u32 version, u64 n_kv, u64 n_tensors        (24 bytes)
  kv       u64 key_len, key, u32 vtype, value
             vtype 8 STRING  : u64 len, len bytes
             vtype 9 ARRAY   : u32 elem_type, u64 count, payload
             scalar          : 0,1,7 -> 1B   4,5,6 -> 4B   10,11,12 -> 8B
  tensor   u64 n_dims, n_dims x u64 dim, u32 type, u64 name_len, name, u64 offset
  align to general.alignment (default 32)

Usage:  python3 scripts/audit/f32_reference.py [n_values]
"""
import struct
import sys
import collections

MODEL = '/opt/ai/models/quanta/QUANTA-LFM2.5-2.6Bv1-Q4_K_M.gguf'

# GGML block layouts: type -> (values_per_block, bytes_per_block)
BLOCK = {
    0: (1, 4), 1: (1, 2), 2: (32, 18), 3: (32, 20), 6: (32, 22), 7: (32, 24),
    8: (32, 34), 9: (32, 36), 10: (256, 84), 11: (256, 110), 12: (256, 144),
    13: (256, 176), 14: (256, 210), 15: (256, 292),
}
NAME = {
    0: 'F32', 1: 'F16', 2: 'Q4_0', 3: 'Q4_1', 6: 'Q5_0', 7: 'Q5_1', 8: 'Q8_0',
    9: 'Q8_1', 10: 'Q2_K', 11: 'Q3_K', 12: 'Q4_K', 13: 'Q5_K', 14: 'Q6_K',
    15: 'Q8_K',
}
VT_SIZE = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}


def f64_bits(x):
    return struct.unpack('<q', struct.pack('<d', x))[0]


def main():
    want = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    f = open(MODEL, 'rb')
    # GGUF v3 header order is magic, version, TENSOR_COUNT, KV_COUNT. Reading
    # these as (kv, tensors) -- the intuitive order -- silently swaps them, and
    # then the walker tries to parse 266 metadata records and dies on the first
    # tensor entry with "unknown vtype 2". The counts being 266 tensors / 37
    # metadata entries is what makes the swap visible.
    magic, ver, ntensors, nkv = struct.unpack('<4sIQQ', f.read(24))
    print('magic=%s v%d n_tensors=%d n_kv=%d' % (magic, ver, ntensors, nkv))

    align = 32
    pos = 24
    for _ in range(nkv):
        f.seek(pos)
        klen = struct.unpack('<Q', f.read(8))[0]
        if klen > 4096:
            raise SystemExit('desync at pos=%d klen=%d' % (pos, klen))
        key = f.read(klen).decode('utf-8', 'replace')
        vt = struct.unpack('<I', f.read(4))[0]
        end = pos + 8 + klen + 4
        if vt == 8:
            sl = struct.unpack('<Q', f.read(8))[0]
            f.seek(sl, 1)
            end += 8 + sl
        elif vt == 9:
            et = struct.unpack('<I', f.read(4))[0]
            count = struct.unpack('<Q', f.read(8))[0]
            end += 12
            if et == 8:
                for _ in range(count):
                    sl = struct.unpack('<Q', f.read(8))[0]
                    f.seek(sl, 1)
                    end += 8 + sl
            else:
                end += count * VT_SIZE.get(et, 0)
        elif vt in (0, 1, 7):
            end += 1
        elif vt in (4, 5, 6):
            end += 4
        elif vt in (10, 11, 12):
            raw = f.read(8)
            if key == 'general.alignment':
                align = struct.unpack('<Q', raw)[0]
        else:
            raise SystemExit('unknown vtype %d for %s' % (vt, key))
        pos = end

    # NO alignment padding between the metadata block and the tensor-info table.
    # gguf writes the KV block and the tensor-info records back to back; only the
    # tensor DATA section is aligned. Padding here lands inside the first
    # tensor record and reads a garbage name length
    # (7741533827821993984 = ASCII "w.GGGG" as a u64).
    data_start = pos
    print('tensor_info_start = %d' % pos)

    tensors = []
    for _ in range(ntensors):
        f.seek(pos)
        # Tensor info is NAME-FIRST: u64 name_len, name, u32 n_dims, dims,
        # u32 type, u64 offset. Reading n_dims first (the order used by the
        # kv section) walks into the middle of a name and reads a huge n_dims.
        nlen = struct.unpack('<Q', f.read(8))[0]
        if nlen > 4096:
            raise SystemExit('desync in tensor info at pos=%d nlen=%d' % (pos, nlen))
        nm = f.read(nlen).decode('utf-8', 'replace')
        nd = struct.unpack('<I', f.read(4))[0]
        if nd > 8:
            raise SystemExit('implausible n_dims=%d for %s at pos=%d' % (nd, nm, pos))
        dims = list(struct.unpack('<%dQ' % nd, f.read(8 * nd)))
        dt = struct.unpack('<I', f.read(4))[0]
        off = struct.unpack('<Q', f.read(8))[0]
        nelem = 1
        for d in dims:
            nelem *= d
        per, nbytes = BLOCK.get(dt, (1, 4))
        tensors.append({'i': len(tensors), 'name': nm, 'dims': dims, 'type': dt,
                        'off': off, 'nelem': nelem, 'nbytes': nbytes * (nelem // per)})
        pos += 8 + nlen + 4 + 8 * nd + 4 + 8

    # Only the DATA section is aligned. The library reported 8239136 for this
    # model, which is the number every raw read is checked against.
    data_start = pos
    if data_start % align:
        data_start += align - (data_start % align)
    print('data_start = %d  (aligned to %d)' % (data_start, align))

    hist = collections.Counter(t['type'] for t in tensors)
    print('\ndtype histogram:')
    for dt in sorted(hist):
        per, nb = BLOCK.get(dt, (1, 4))
        print('   %-6s (%2d) x%-4d  %3d values / %3d B per block'
              % (NAME.get(dt, '?'), dt, hist[dt], per, nb))

    print('\nF32 tensors by shape:')
    shapes = collections.Counter(tuple(t['dims']) for t in tensors if t['type'] == 0)
    for sh, c in shapes.most_common():
        n = 1
        for d in sh:
            n *= d
        print('   %-14s x%-4d (%d values each)' % (str(sh), c, n))

    # Every dtype the model uses, against the decoders the library ships.
    have = {0: 'MISSING', 12: 'dequant_q4k', 14: 'dequant_q6k'}
    print('\ndecoder coverage:')
    for dt in sorted(hist):
        print('   %-6s x%-4d  %s' % (NAME.get(dt, '?'), hist[dt],
                                     have.get(dt, 'MISSING')))
    covered = sum(c for dt, c in hist.items() if dt in (12, 14))
    print('\ncovered %d of %d tensors (%.0f%%)'
          % (covered, sum(hist.values()), 100.0 * covered / sum(hist.values())))

    # Detail on the first F32 tensor.
    f32 = [t for t in tensors if t['type'] == 0]
    if f32:
        t = f32[0]
        print('\nfirst F32 tensor:')
        print('   index   %d' % t['i'])
        print('   name    %s' % t['name'])
        print('   dims    %s' % t['dims'])
        print('   offset  %d  (abs %d)' % (t['off'], data_start + t['off']))
        print('   nbytes  %d' % t['nbytes'])
        f.seek(data_start + t['off'])
        raw = f.read(want * 4)
        bits = struct.unpack('<%dI' % want, raw)
        vals = struct.unpack('<%df' % want, raw)
        print('   first %d bits:' % want)
        for k in range(want):
            signed = bits[k] - (1 << 32) if bits[k] >= (1 << 31) else bits[k]
            print('      %d  %r' % (signed, vals[k]))
        nz = 0
        f.seek(data_start + t['off'])
        allv = struct.unpack('<%df' % t['nelem'], f.read(4 * t['nelem']))
        for x in allv:
            if x != 0.0:
                nz += 1
        print('   non-zero: %d of %d' % (nz, t['nelem']))


if __name__ == '__main__':
    main()