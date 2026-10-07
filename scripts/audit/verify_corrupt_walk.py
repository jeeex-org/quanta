"""Verify gen_corrupt_gguf's offset walk against Quanta's parsed values.

Fails loudly if the derived byte offsets disagree, so the generator can never
patch an unrelated region of a 1.6 GB file.
"""

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_corrupt_gguf as G

M = "/opt/ai/models/quanta/QUANTA-LFM2.5-2.6Bv1-Q4_K_M.gguf"

# Measured by Quanta itself:
#   gguf_tinfo_start           = 8222781  (read_tensor_info)
#   gguf_tensor_offset(0)  - data_start = 0
#   gguf_tensor_offset(5)  - data_start = 245506048
#   gguf_tensor_offset(6)  - data_start = 245514240
#   gguf_tensor_offset(7)  - data_start = 257900544
TINFO_START = 8222781
EXPECT_REL = {0: 0, 5: 245506048, 6: 245514240, 7: 257900544}

with open(M, "rb") as f:
    head = f.read(24)
n_tensors = struct.unpack_from("<Q", head, 8)[0]
print("n_tensors", n_tensors, "tinfo_start", TINFO_START)

ok = True
for idx, want in sorted(EXPECT_REL.items()):
    got = G.rel_offset(M, TINFO_START, idx)
    status = "MATCH" if got == want else "MISMATCH"
    if got != want:
        ok = False
    print("  tensor %-3d rel %-14d want %-14d %s" % (idx, got, want, status))

dims_at, dtype_at, off_at = G.tensor_fields(M, TINFO_START, 0)
with open(M, "rb") as f:
    dt = struct.unpack("<I", G.read_at(f, dtype_at, 4))[0]
    d0 = G.u64(G.read_at(f, dims_at, 8), 0)
print("  tensor 0 dtype %d (want 14=Q6_K)  dim0 %d (want 2048)" % (dt, d0))
if dt != 14 or d0 != 2048:
    ok = False

# the generator's own guard must reject a wrong start
try:
    G.verify_walk(M, TINFO_START + 8, n_tensors, 0, 245506048)
    print("  BAD: verify_walk accepted a wrong tinfo_start")
    ok = False
except SystemExit as e:
    print("  verify_walk correctly refused a wrong start: %s" % str(e)[:60])

print("WALK_OK" if ok else "WALK_BAD")
sys.exit(0 if ok else 1)