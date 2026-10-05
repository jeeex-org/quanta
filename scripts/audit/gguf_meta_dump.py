#!/usr/bin/env python3
"""Dump LFM2 GGUF metadata (offset arithmetic only, no bulk reads).

Read-only inspection helper for Stage 2 (tokenizer). Prints every metadata key
with its value type, and for the tokenizer arrays prints element type, count and
a few sampled elements by seeking directly to their offsets.

This is an audit/inventory tool. It is not on any test or inference path.
"""
import struct
import sys

GGUF_SCALAR = {
    0: ('u8', 1), 1: ('i8', 1), 2: ('u16', 2), 3: ('i16', 2),
    4: ('u32', 4), 5: ('i32', 4), 6: ('f32', 4), 7: ('bool', 1),
    10: ('u64', 8), 11: ('i64', 8), 12: ('f64', 8),
}
# GGUF value types: 8 = STRING, 9 = ARRAY. Swapping these silently reads the
# array header out of the wrong bytes and yields an absurd element count.
GGUF_STRING = 8
GGUF_ARRAY = 9


def elem_size(et):
    if et in GGUF_SCALAR:
        return GGUF_SCALAR[et][1]
    if et == GGUF_STRING:
        return -1   # variable
    if et == GGUF_ARRAY:
        return -2   # variable, recursive
    raise ValueError('unknown elem type %d' % et)


def scan_array_header(f):
    et = struct.unpack('<I', f.read(4))[0]
    cnt = struct.unpack('<Q', f.read(8))[0]
    return et, cnt


def skip_array(f, et, cnt):
    """Advance past an array body, recording string element offsets."""
    str_offsets = []
    sz = elem_size(et)
    for i in range(cnt):
        pos = f.tell()
        if et == GGUF_STRING:
            n = struct.unpack('<Q', f.read(8))[0]
            str_offsets.append((pos, f.tell(), n))
            f.seek(n, 1)
        elif et == GGUF_ARRAY:
            sub_et, sub_cnt = scan_array_header(f)
            f.seek(0, 1)
            # position is now wrong; re-derive by scanning properly
            str_offsets.append((pos, -1, -1))
            # can't cheaply skip nested arrays without recursion; handle below
            raise SystemExit('nested array at %d - handle explicitly' % pos)
        else:
            f.seek(sz, 1)
    return str_offsets


def main():
    path = sys.argv[1]
    f = open(path, 'rb')
    magic, ver, n_tensors, n_kv = struct.unpack('<4sIQQ', f.read(24))
    print('path     : %s' % path)
    print('magic    : %s  version: %d' % (magic.decode(), ver))
    print('tensors  : %d' % n_tensors)
    print('metadata : %d KVs' % n_kv)
    print()

    tensors_meta = []
    for _ in range(n_kv):
        klen = struct.unpack('<Q', f.read(8))[0]
        key = f.read(klen).decode('utf-8', 'replace')
        vtype = struct.unpack('<I', f.read(4))[0]

        if vtype == GGUF_ARRAY:
            et, cnt = scan_array_header(f)
            if et == GGUF_STRING:
                offs = skip_array(f, GGUF_STRING, cnt)
                tensors_meta.append((key, 'array<string>', cnt, offs))
            elif et == GGUF_ARRAY:
                sub_et, sub_cnt = scan_array_header(f)
                offs = skip_array(f, sub_et, sub_cnt)
                tensors_meta.append((key, 'array<array<%s>>' % (
                    GGUF_SCALAR.get(sub_et, ('type%d' % sub_et, 0))[0],
                ), sub_cnt, offs))
            else:
                name = GGUF_SCALAR[et][0]
                sz = GGUF_SCALAR[et][1]
                f.seek(sz * cnt, 1)
                tensors_meta.append((key, 'array<%s>' % name, cnt, None))
        elif vtype == GGUF_STRING:
            slen = struct.unpack('<Q', f.read(8))[0]
            print('%-36s %-10s %r' % (key, 'string', f.read(slen)[:70]))
        else:
            name = GGUF_SCALAR[vtype][0]
            raw = f.read(GGUF_SCALAR[vtype][1])
            if vtype == 6:
                val = struct.unpack('<f', raw)[0]
            elif vtype == 5:
                val = struct.unpack('<i', raw)[0]
            elif vtype == 4:
                val = struct.unpack('<I', raw)[0]
            elif vtype == 7:
                val = bool(raw[0])
            else:
                val = raw.hex()
            print('%-36s %-10s %s' % (key, name, val))

    print()
    print('=== arrays ===')
    for key, kind, cnt, offs in tensors_meta:
        print('%-36s %-22s count=%d' % (key, kind, cnt))

    print()
    print('=== tokenizer arrays: first 5 and last 5 elements ===')
    for key, kind, cnt, offs in tensors_meta:
        if not key.startswith('tokenizer'):
            continue
        print('-- %s (%s, %d elements)' % (key, kind, cnt))
        if offs is None:
            print('   (non-string, not sampled)')
            continue
        picks = list(range(min(5, cnt))) + list(range(max(0, cnt - 5), cnt))
        for i in picks:
            _, dstart, n = offs[i]
            f.seek(dstart)
            s = f.read(n)
            print('   [%6d] len=%-4d %r' % (i, n, s[:70]))

    print()
    print('tensor data starts at byte %d' % f.tell())


if __name__ == '__main__':
    main()