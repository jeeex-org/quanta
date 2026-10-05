#!/usr/bin/env python3
"""Generate GGUF block fixtures for the uniform-scale formats that have no
local model tensor: Q2_K, Q3_K, Q4_1, Q5_0, Q5_1, Q8_K.

Run ONCE, offline. The output is committed as binary fixtures that the Quanta
test reads natively. Nothing in the test path calls upstream, and regenerating
these files is never part of running the tests.

Why ctypes and not a C extension
--------------------------------
The authority here is upstream llama.cpp's compiled code, reached through its C
ABI. ctypes calls exactly the same symbols out of libggml-base.so, so it is the
same oracle with no compiler and no .c file. This is the only reason the earlier
Python transcriptions were wrong: they re-implemented the dequantizer instead of
calling it, and a wrong re-implementation agrees with a wrong test. Calling the
symbol removes that failure mode.

The method is a ROUND TRIP through upstream, both ends of it:
  1. synthesise deterministic f32 (no RNG, so bytes are stable everywhere),
  2. quantize with upstream quantize_row_<fmt>_ref,
  3. dequantize with upstream dequantize_row_<fmt>,
  4. reduce sum/sumsq/min/max over the dequantized values.

The result is the format's reference semantics. Quanta's dequantizer is asserted
against it.

Note step 3 does NOT return step 1's values -- a 2-bit quantizer discards most
of them. That is the format working as defined, so the test compares against the
ROUND-TRIPPED values and never against the input.

Q8_1 IS DELIBERATELY ABSENT
---------------------------
Q8_1 has no per-element meaning, so it cannot be a dequantization target and is
excluded here. Upstream never exports dequantize_row_q8_1 because it never needs
one: in ggml-cpu/quants.c the ONLY consumer of a block_q8_1 is the dot product
against a matching weight block, where its qs[] bytes are used directly as int8
multipliers:

    const int v0 = (x[ib].qs[j] & 0x0F);
    const int v1 = (x[ib].qs[j] >>   4);
    sumi0 += (v0 * y[ib].qs[j]);
    sumi1 += (v1 * y[ib].qs[j + qk/2]);
    sumf += (d_x*d_y)*sumi + m_x*s_y;

There is no element -> float mapping to reproduce; the block is only ever
consumed in pairs. Supporting Q8_1 therefore means implementing a matvec kernel
for it, not a dequantizer, and an earlier hand-written deq_q8_1 in
scripts/audit/c_oracle.c invented a rule that upstream does not define. That
fabricated path is called out rather than trusted.

Usage:  python3 scripts/audit/gen_fixtures.py [--out-dir DIR]
"""

import argparse
import ctypes
import os
import struct

SO = "/opt/ai/llama.cpp/bin/libggml-base.so"

# Block layout, from ggml/src/ggml-common.h. LAYOUT ONLY -- no arithmetic from
# these files; every value below comes from calling upstream.
FORMATS = {
    # name: (bytes per block, elements per block, ctypes struct for the block)
    "q2_K": (84, 256, None),
    "q3_K": (110, 256, None),
    "q4_1": (20, 32, "<HH16s"),
    "q5_0": (22, 32, "<H4s16s"),
    "q5_1": (24, 32, "<HH4s16s"),
    "q8_K": (292, 256, "<i256s32s"),
}


class Q4_1(ctypes.Structure):
    _fields_ = [("d", ctypes.c_uint16), ("m", ctypes.c_uint16),
                ("qs", ctypes.c_uint8 * 16)]


class Q5_0(ctypes.Structure):
    _fields_ = [("d", ctypes.c_uint16), ("qh", ctypes.c_uint8 * 4),
                ("qs", ctypes.c_uint8 * 16)]


class Q5_1(ctypes.Structure):
    _fields_ = [("d", ctypes.c_uint16), ("m", ctypes.c_uint16),
                ("qh", ctypes.c_uint8 * 4), ("qs", ctypes.c_uint8 * 16)]


class Q2_K(ctypes.Structure):
    _fields_ = [("scales", ctypes.c_uint8 * 16), ("qs", ctypes.c_uint8 * 64),
                ("d", ctypes.c_uint16), ("dmin", ctypes.c_uint16)]


class Q3_K(ctypes.Structure):
    _fields_ = [("hmask", ctypes.c_uint8 * 32), ("qs", ctypes.c_uint8 * 64),
                ("scales", ctypes.c_uint8 * 12), ("d", ctypes.c_uint16)]


class Q8_K(ctypes.Structure):
    _fields_ = [("d", ctypes.c_float), ("qs", ctypes.c_int8 * 256),
                ("bsums", ctypes.c_int16 * 16)]


STRUCTS = {"q4_1": Q4_1, "q5_0": Q5_0, "q5_1": Q5_1,
           "q2_K": Q2_K, "q3_K": Q3_K, "q8_K": Q8_K}


def load_symbols():
    so = ctypes.CDLL(SO)
    syms = {}
    for name in FORMATS:
        for kind in ("quantize_row_%s_ref" % name, "dequantize_row_%s" % name):
            fn = getattr(so, kind, None)
            if fn is None:
                raise SystemExit("upstream does not export %s -- cannot be an "
                                 "oracle for %s" % (kind, name))
            fn.restype = None
            # The quantizer reads f32 and writes a block; the dequantizer reads
            # a block and writes f32. Sharing one argtypes for both gets the
            # dequantizer's FIRST argument wrong (it would demand
            # POINTER(c_float) for the const void* source).
            if kind.startswith("quantize"):
                fn.argtypes = [ctypes.POINTER(ctypes.c_float),
                               ctypes.c_void_p, ctypes.c_int64]
            else:
                fn.argtypes = [ctypes.c_void_p,
                               ctypes.POINTER(ctypes.c_float), ctypes.c_int64]
            syms[kind] = fn
    return syms


def synth(n, seed=0x13579BDF):
    """Deterministic f32 in [-0.125, 0.125). No RNG library on purpose: the
    committed fixture must be byte-identical on every machine and every run, or
    the expected values in the test would be unreproducible."""
    out = []
    s = seed
    for _ in range(n):
        s ^= (s << 13) & 0xFFFFFFFF
        s ^= s >> 17
        s ^= (s << 5) & 0xFFFFFFFF
        u = (s >> 8) / 16777216.0
        out.append((u - 0.5) * 0.25)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="tests/fixtures")
    ap.add_argument("--blocks", type=int, default=8)
    args = ap.parse_args()

    syms = load_symbols()
    os.makedirs(args.out_dir, exist_ok=True)
    lines = []

    for name, (bs, qk, _) in FORMATS.items():
        n = qk * args.blocks
        x = synth(n)
        xa = (ctypes.c_float * n)(*x)
        q = ctypes.create_string_buffer(bs * args.blocks)
        y = (ctypes.c_float * n)()

        syms["quantize_row_%s_ref" % name](xa, q, n)
        syms["dequantize_row_%s" % name](q, y, n)

        ys = [y[i] for i in range(n)]
        sm = sum(ys)
        sq = sum(v * v for v in ys)
        mn = min(ys)
        mx = max(ys)

        path = os.path.join(args.out_dir, "blocks_%s.bin" % name)
        with open(path, "wb") as f:
            f.write(q.raw)

        # Guard: the block must be exactly bs bytes, and a misdeclared ctypes
        # struct would silently resize the malloc and corrupt every later read.
        assert ctypes.sizeof(STRUCTS[name]) == bs, (
            "%s: ctypes says %d bytes, table says %d" %
            (name, ctypes.sizeof(STRUCTS[name]), bs))

        lines.append("%s n=%d nbytes=%d" % (name, n, bs * args.blocks))
        lines.append("  sum   = %.6f" % sm)
        lines.append("  sumsq = %.6f" % sq)
        lines.append("  min   = %.6f" % mn)
        lines.append("  max   = %.6f" % mx)
        lines.append("  first = " + " ".join("%.6f" % v for v in ys[:6]))
        lines.append("  file  = %s" % path)
        print("\n".join(lines[-6:]))

    with open(os.path.join(args.out_dir, "expected.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\nwrote %s/expected.txt" % args.out_dir)


if __name__ == "__main__":
    main()
