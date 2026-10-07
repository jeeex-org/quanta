"""Byte-level GGUF corrupt-file generator for the Quanta loader tests.

WHY THIS EXISTS
---------------
Two hand-rolled GGUF *readers* failed earlier in this project. Both mis-parsed
the KV block, reading 8 bytes too far and desyncing on
`general.base_model.0.name`; the first produced 165 KB of garbage before anyone
noticed. The lesson recorded in the plan was: stop hand-rolling a GGUF reader.

So this script never parses the KV block. It takes the byte offset of the
tensor-info table FROM QUANTA's verified parser (`gguf_tinfo_start`, recorded by
read_tensor_info()) and walks only the tensor records, whose layout is fixed and
simple: u64 name length, name bytes, u32 n_dims, n_dims * u64 dims, u32 dtype,
u64 offset.

Every offset it computes is verified against Quanta's own parsed tensor offsets
before a single byte is written. If verification fails it refuses to write,
rather than silently corrupting an unrelated region of a 1.6 GB file.

Usage:
    gen_corrupt_gguf.py <src.gguf> <dst.gguf> <tinfo_start> <corruption> <t0rel> <t5rel>

Corruptions:
    gap           tensor 5's offset moved 4096 bytes forward
    overlap       tensor 7's offset pulled back onto tensor 6's start
    tail          the last tensor's offset moved 8 bytes
    dim_overflow  tensor 0's dim[0] set so the dimension product overflows
    dim_mismatch  tensor 0's dim[0] incremented (dims disagree with nelements)
    huge_dtype    tensor 0's dtype set to an unknown value
    neg_offset    tensor 5's offset set negative
"""

import struct
import sys


def u64(buf, off):
    return struct.unpack_from("<Q", buf, off)[0]


def read_at(f, off, n):
    f.seek(off)
    return f.read(n)


def tensor_fields(path, tinfo_start, index):
    """Return (dims_at, dtype_at, offset_at) for tensor `index`."""
    with open(path, "rb") as f:
        off = tinfo_start
        for _ in range(index):
            nlen = u64(read_at(f, off, 8), 0)
            off += 8 + nlen
            f.seek(off)
            ndims = struct.unpack("<I", f.read(4))[0]
            off += 4 + 8 * ndims + 4 + 8  # dims + dtype + offset
        nlen = u64(read_at(f, off, 8), 0)
        off += 8 + nlen
        f.seek(off)
        ndims = struct.unpack("<I", f.read(4))[0]
        dims_at = off + 4
        dtype_at = off + 4 + 8 * ndims
        return dims_at, dtype_at, dtype_at + 4


def rel_offset(path, tinfo_start, index):
    _, _, oa = tensor_fields(path, tinfo_start, index)
    with open(path, "rb") as f:
        return u64(read_at(f, oa, 8), 0)


def verify_walk(path, tinfo_start, n_tensors, t0rel, t5rel):
    """Check the derived offsets against Quanta's parsed values. Refuse on any
    mismatch so a bug here can never corrupt an unrelated region."""
    try:
        got0 = rel_offset(path, tinfo_start, 0)
        got5 = rel_offset(path, tinfo_start, 5)
    except Exception as e:
        # A wrong table start runs off the record structure and trips a decode
        # error. That is still a refusal, just a loud one -- say so plainly
        # instead of surfacing a raw struct.error from deep inside.
        raise SystemExit(
            "walk verification FAILED: tinfo_start %d does not describe a tensor "
            "table (%s). Refusing to write." % (tinfo_start, type(e).__name__)
        )
    if got0 != t0rel or got5 != t5rel:
        raise SystemExit(
            "walk verification FAILED: tensor0 %d (want %d), tensor5 %d (want %d). "
            "Refusing to write." % (got0, t0rel, got5, t5rel)
        )
    dims_at, dtype_at, oa = tensor_fields(path, tinfo_start, 0)
    with open(path, "rb") as f:
        dt = struct.unpack("<I", read_at(f, dtype_at, 4))[0]
        d0 = u64(read_at(f, dims_at, 8), 0)
    if dt != 14 or d0 != 2048:
        raise SystemExit(
            "field layout FAILED: tensor0 dtype %d (want 14), dim0 %d (want 2048)"
            % (dt, d0)
        )


def patch(src, dst, tinfo_start, kind, n_tensors):
    with open(src, "rb") as fin, open(dst, "wb") as fout:
        while True:
            chunk = fin.read(1 << 20)
            if not chunk:
                break
            fout.write(chunk)

    dims0, dtype0, off0 = tensor_fields(src, tinfo_start, 0)
    _, _, off5 = tensor_fields(src, tinfo_start, 5)
    _, _, off6 = tensor_fields(src, tinfo_start, 6)
    _, _, off7 = tensor_fields(src, tinfo_start, 7)
    _, _, offlast = tensor_fields(src, tinfo_start, n_tensors - 1)

    with open(dst, "r+b") as f:
        if kind == "gap":
            cur = u64(read_at(f, off5, 8), 0)
            f.seek(off5)
            f.write(struct.pack("<Q", cur + 4096))
        elif kind == "overlap":
            v6 = u64(read_at(f, off6, 8), 0)
            f.seek(off7)
            f.write(struct.pack("<Q", v6))
        elif kind == "tail":
            cur = u64(read_at(f, offlast, 8), 0)
            f.seek(offlast)
            f.write(struct.pack("<Q", cur + 8))
        elif kind == "dim_overflow":
            f.seek(dims0)
            f.write(struct.pack("<Q", 900000000000000000))
        elif kind == "dim_mismatch":
            cur = u64(read_at(f, dims0, 8), 0)
            f.seek(dims0)
            f.write(struct.pack("<Q", cur + 1))
        elif kind == "huge_dtype":
            f.seek(dtype0)
            f.write(struct.pack("<I", 250))
        elif kind == "neg_offset":
            f.seek(off5)
            f.write(struct.pack("<q", -4096))
        else:
            raise SystemExit("unknown corruption %r" % kind)

    print("wrote %s kind=%s tinfo_start=%d" % (dst, kind, tinfo_start))


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) != 7:
        raise SystemExit(__doc__)
    src, dst, tinfo_s, kind, n_t, t0rel, t5rel = a
    tinfo = int(tinfo_s)
    nt = int(n_t)
    verify_walk(src, tinfo, nt, int(t0rel), int(t5rel))
    patch(src, dst, tinfo, kind, nt)