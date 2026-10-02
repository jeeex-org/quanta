"""Ground truth for the real GGUF model, established from the actual bytes.

Correct GGUF v3 rules:
  metadata value vtype 8 (STRING): u64 len, then len bytes (no NUL)
  metadata value vtype 9 (ARRAY):  u32 elem_type, u64 count, then payload
      elem_type 8 (STRING): count x (u64 len + len bytes). No offset table.
      otherwise:            count * size(elem_type)
  scalar vtypes: 0,1,7 -> 1B   4,5,6 -> 4B   10,11,12 -> 8B
tensor info: u64 n_dims, n_dims x u64 dim, u32 type, u64 name_len, name bytes
Then align to general.alignment (default 32).
"""
import struct, os, sys

M = '/opt/ai/models/quanta/QUANTA-LFM2.5-2.6Bv1-Q4_K_M.gguf'
SIZE = os.path.getsize(M)
f = open(M, 'rb')
SIZES = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1,
         10: 8, 11: 8, 12: 8}

magic, ver, nkv, ntensors = struct.unpack('<4sIQQ', f.read(24))
out = ["magic=%s v%d n_kv=%d n_tensors=%d size=%d" % (magic, ver, nkv, ntensors, SIZE)]

pos = 24
arrays = 0
align = 32
n_meta = 0
for i in range(nkv):
    f.seek(pos)
    klen = struct.unpack('<Q', f.read(8))[0]
    if klen > 4096:
        out.append("DESYNC at i=%d klen=%d pos=%d" % (i, klen, pos))
        break
    key = f.read(klen).decode('utf-8', 'replace')
    vt = struct.unpack('<I', f.read(4))[0]
    p = pos + 8 + klen + 4
    note = ""
    if vt == 8:
        sl = struct.unpack('<Q', f.read(8))[0]
        f.seek(sl, 1)
        p += 8 + sl
    elif vt == 9:
        arrays += 1
        et = struct.unpack('<I', f.read(4))[0]
        al = struct.unpack('<Q', f.read(8))[0]
        p += 12
        if et == 8:
            strs = []
            for _ in range(al):
                sl = struct.unpack('<Q', f.read(8))[0]
                strs.append(f.read(sl).decode('utf-8', 'replace'))
                p += 8 + sl
            shown = (strs[:4] + ['...']) if al > 4 else strs
            note = "ARRAY[str] n=%d %s" % (al, shown)
        else:
            esz = SIZES.get(et, 0)
            p += al * esz
            note = "ARRAY et=%d n=%d esz=%d bytes=%d" % (et, al, esz, al * esz)
    elif vt in (0, 1, 7):
        p += 1
    elif vt in (4, 5, 6):
        p += 4
    elif vt in (10, 11, 12):
        p += 8
    else:
        # a tensor name: the metadata is over. Rewind to this record's start.
        out.append("metadata ends before i=%d (key=%r vtype=%d)" % (i, key, vt))
        break
    if vt == 9 or i < 3:
        out.append("  i=%-4d rec@%-8d key=%-32r vt=%-2d %s" % (i, pos, key, vt, note))
    pos = p
    n_meta = i + 1

out.append("metadata entries walked: %d (header says %d)" % (n_meta, nkv))
out.append("arrays: %d" % arrays)

f.seek(pos)
for t in range(ntensors):
    start = f.tell()
    nd = struct.unpack('<Q', f.read(8))[0]
    if nd > 8:
        out.append("tensor %d: implausible n_dims=%d at %d" % (t, nd, start))
        break
    dims = [struct.unpack('<Q', f.read(8))[0] for _ in range(nd)]
    ttype = struct.unpack('<I', f.read(4))[0]
    nl = struct.unpack('<Q', f.read(8))[0]
    if nl > 4096:
        out.append("tensor %d: implausible name_len=%d at %d" % (t, nl, start))
        break
    tname = f.read(nl).decode('utf-8', 'replace')
    if t < 3:
        out.append("  t=%-3d name=%-28s type=%-3d ndim=%d dims=%s"
                   % (t, tname, ttype, nd, dims[:4]))

end = f.tell()
aligned = end + (-end % align)
out.append("")
out.append("metadata+tensors end at %d" % end)
out.append("aligned data offset    = %d" % aligned)
out.append("library reported       = 8239136")
out.append("MATCH: %s" % (aligned == 8239136))
sys.stdout.write("\n".join(out) + "\n")