"""Build hostile safetensors files for the reader test.

Python can WRITE safetensors correctly (unlike the GGUF case earlier in this
project, where hand-rolling a parser desynced twice). Each file is valid JSON in a
valid header, so it exercises the reader's bounds logic rather than a malformed
parse.

Usage: make_hostile_st.py <outdir>
"""

import json
import os
import struct
import sys


def write(path, header_obj, data_bytes, header_len_override=None, truncate_to=None):
    hdr = json.dumps(header_obj, separators=(",", ":")).encode()
    n = header_len_override if header_len_override is not None else len(hdr)
    with open(path, "wb") as f:
        f.write(struct.pack("<Q", n))
        f.write(hdr)
        f.write(data_bytes)
    if truncate_to is not None:
        with open(path, "r+b") as f:
            f.truncate(truncate_to)


out = sys.argv[1]
os.makedirs(out, exist_ok=True)
DATA = bytes(64)

ok = {"a": {"dtype": "F32", "shape": [16], "data_offsets": [0, 64]}}

# 1. header length declares far more than the file holds. 10^9 is past the 100 MB
#    cap AND past EOF, so either guard rejects it; `over_cap` below isolates the
#    cap by staying inside the file.
write(os.path.join(out, "huge_len.gguf"), ok, DATA, header_len_override=10 ** 9)

# 1b. hlen is over the cap but the FILE IS correspondingly large, so only the cap
#     can reject it. The data is written to fill the declared header.
_path = os.path.join(out, "over_cap.gguf")
_hdr = json.dumps(ok, separators=(",", ":")).encode()
_pad = 200 * 1024 * 1024 - len(_hdr)
_hdr = _hdr + b" " * _pad          # trailing spaces: still valid JSON
with open(_path, "wb") as f:
    f.write(struct.pack("<Q", 200 * 1024 * 1024))
    f.write(_hdr)
    f.write(DATA)



# 3. header length is absurd (wraps a naive 64-bit addition)
write(os.path.join(out, "wrap_len.gguf"), ok, DATA,
      header_len_override=0xFFFFFFFFFFFFFFF0)

# 4. data_offsets point past the end of the file.
#    The byte length here MUST match the shape (16 F32 = 64) so the EOF check is
#    what rejects it. With a mismatched length the byte-length check fires first
#    (-3005) and the EOF check is never reached, which is how an earlier fixture
#    made the EOF guard look redundant when it was simply untested.
write(os.path.join(out, "oob_offsets.gguf"),
      {"a": {"dtype": "F32", "shape": [16], "data_offsets": [0, 64]}}, DATA * 0)

# 5. data_offsets are reversed (b1 < b0)
write(os.path.join(out, "reversed.gguf"),
      {"a": {"dtype": "F32", "shape": [16], "data_offsets": [64, 0]}}, DATA)

# 6. shape disagrees with the declared byte length
#    shape [16] F32 => 64 bytes, but offsets claim 32
write(os.path.join(out, "shape_mismatch.gguf"),
      {"a": {"dtype": "F32", "shape": [16], "data_offsets": [0, 32]}}, DATA)

# 7. unknown dtype
write(os.path.join(out, "unknown_dtype.gguf"),
      {"a": {"dtype": "F7_WHAT", "shape": [16], "data_offsets": [0, 64]}}, DATA)

# 8. a dimension product that overflows to NEGATIVE, caught by the v<=0 guard
big = 1 << 40
write(os.path.join(out, "dim_overflow.gguf"),
      {"a": {"dtype": "F32", "shape": [big, big], "data_offsets": [0, 64]}}, DATA)

# 8b. a product that stays POSITIVE and fits i64 but exceeds the element limit.
#     This is the case only the checked-multiply limit guard rejects: it never
#     goes negative and never trips v<=0, so a plain multiply would accept it and
#     a huge-but-plausible element count would flow into the byte-length check.
#     10^8 * 10^9 = 10^17, which is positive and < 2^63 but > the 9e17... no:
#     pick 10^8 * 10^10 = 10^18, positive, > 9e17, and well inside i64.
a = 10 ** 8
b = 10 ** 10
write(os.path.join(out, "dim_over_limit.gguf"),
      {"a": {"dtype": "F32", "shape": [a, b], "data_offsets": [0, 64]}}, DATA)

# 8b2. THE ISOLATING FIXTURE for the checked-multiply limit.
#
#     Every earlier overflow fixture wraps NEGATIVE or simply exceeds the limit, so
#     another guard (v<=0, or the byte-length check) got there first. Deleting the
#     limit guard left all of them still rejected, which is why this mutation
#     survived.
#
#     This one wraps to a SMALL POSITIVE number that MATCHES the file's real byte
#     length, so every other check passes and only the limit guard can reject it:
#
#         1024 * 18014398509481985 = 18446744073709552640
#         18446744073709552640 mod 2^64 = 1024
#
#     Both dimensions fit in i64 (18014398509481985 < 2^63-1), so json_get_number
#     returns positive values and the v<=0 guard does NOT fire. The product wraps
#     to 1024, which matches the declared data_offsets [0, 4096] for F32 (1024
#     elements * 4 bytes = 4096 bytes). Only the checked-multiply limit guard can
#     reject this file.
#
#     a = 1024 is deliberately innocuous. A shape whose first dimension is 1024
#     is not something a reviewer flags, which is the point: the real extent is
#     ~1.8e19 elements and the wrapped value says 1024.
write(os.path.join(out, "dim_wrap_small.gguf"),
      {"a": {"dtype": "F32", "shape": [1024, 18014398509481985],
             "data_offsets": [0, 4096]}},
      bytes(4096))

# 8c. a header that is valid JSON but not an OBJECT at the root, so json_parse
#     succeeds and the reader must reject it on type. Proves the JSON path is
#     live and the type check is real -- deleting the string-header store
#     (json_parse needs len(buf)) does not break this path, so a passing M3 means
#     the mutation is redundant, not untested.
write(os.path.join(out, "root_array.gguf"), [1, 2, 3], DATA)
write(os.path.join(out, "garbage_header.gguf"), ok, DATA)  # placeholder, rewritten below

# 8d. the header is NOT valid JSON, with a length inside the cap and inside the
#     file, so the ONLY thing that can reject it is the JSON parse failing.
with open(os.path.join(out, "garbage_header.gguf"), "wb") as f:
    bad = b"this is not json at all {{{"
    f.write(struct.pack("<Q", len(bad)))
    f.write(bad)
    f.write(DATA)

# 9. truncated file: header claims a tensor that is not there
write(os.path.join(out, "truncated.gguf"), ok, DATA)
with open(os.path.join(out, "truncated.gguf"), "r+b") as f:
    f.truncate(8 + 40 + 8)   # header present, most of the data gone

# 10. NOT a safetensors file at all (GGUF magic), to prove it is refused
with open(os.path.join(out, "not_st.gguf"), "wb") as f:
    f.write(b"GGUF" + b"\x03\x00\x00\x00" + b"\x00" * 64)

for n in sorted(os.listdir(out)):
    print("  %-22s %d bytes" % (n, os.path.getsize(os.path.join(out, n))))