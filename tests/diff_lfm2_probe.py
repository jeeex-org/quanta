#!/usr/bin/env python3
"""tests/diff_lfm2_probe.py -- element-wise diff of two LFM2 state dumps.

Compares tests/lfm2_prefill_probe.quanta's dump (one forward per prompt token)
against tests/lfm2_prefill_batched_probe.quanta's dump (the batched prefill path)
in the layout the verifier documents, region by region, and prints for each
region:

    differing f64 bit patterns / total   and   max |delta|

Batching claims BIT-IDENTITY, not closeness, so the expected answer everywhere is
0 differing bit patterns. A non-zero count with a tiny max|delta| is a
summation-order change (which would still be a regression against the stated
claim); a large one is a real bug.

The oracle is NOT this script: tests/verify_lfm2_state_ref.py holds a dump to
llama.cpp. Run it on the batched dump as well, so a defect present in both paths
cannot pass by agreeing with itself.

USAGE
    python3.12 tests/diff_lfm2_probe.py A.bin B.bin
"""
import sys
import numpy as np

A_PATH = sys.argv[1] if len(sys.argv) > 1 else "/home/tali/.hermes/cache/scratch/lfm2probe/probe.bin"
B_PATH = sys.argv[2] if len(sys.argv) > 2 else "/home/tali/.hermes/cache/scratch/lfm2probe/probe_batched.bin"
ATTN = [2, 5, 9, 13, 17, 21, 24, 27]
NKV = 8
HD = 64

total_bad = 0
worst = 0.0


def load(path):
    buf = np.fromfile(path, dtype=np.uint8)
    raw = buf.view(np.float64)
    i64 = buf.view(np.int64)
    nsp, n, nv, dm, nl, hd = (int(x) for x in i64[0:6])
    eps = float(raw[6])
    ids = [int(x) for x in i64[7:7 + n]]
    return raw, (nsp, n, nv, dm, nl, hd, eps, ids)


ra, ha = load(A_PATH)
rb, hb = load(B_PATH)
print(f"A {A_PATH}")
print(f"B {B_PATH}")

labels = ("nsp", "n", "n_vocab", "d_model", "n_layers", "head_dim", "rms_eps")
for k, (x, y) in enumerate(zip(ha[:7], hb[:7])):
    flag = "OK " if x == y else "DIFF"
    print(f"  {flag} header {labels[k]:9s} A={x!r} B={y!r}")
if ha[7] != hb[7]:
    print(f"  DIFF ids differ ({len(ha[7])} vs {len(hb[7])})")
else:
    print(f"  OK  header ids ({len(ha[7])} values)")
assert ha[:7] == hb[:7] and ha[7] == hb[7], "headers differ: not the same prompt/config"

nsp, n, nv, dm, nl, hd = ha[:6]


def cmp(name, pa, pb, cnt):
    """compare cnt f64 starting at index pa / pb; accumulate totals"""
    global total_bad, worst
    x, y = ra[pa:pa + cnt], rb[pb:pb + cnt]
    bad = int(np.count_nonzero(x.view(np.int64) != y.view(np.int64)))
    d = np.abs(x - y)
    md = float(d.max()) if cnt else 0.0
    total_bad += bad
    worst = max(worst, md)
    if bad:
        i = int(np.argmax(d))
        print(f"  DIFF {name:26s} {bad:8d}/{cnt:<8d} max|d|={md:.3e} (at {i}: {x[i]!r} vs {y[i]!r})")
    else:
        print(f"  OK   {name:26s} {'0':>8s}/{cnt:<8d} max|d|={md:.3e}")
    return cnt


pa = pb = 7 + n
for pos in range(n):
    if pos < nsp:
        for L in range(nl):
            cmp(f"pos{pos} layer_in[{L}]", pa, pb, dm); pa += dm; pb += dm
    cmp(f"pos{pos} logits", pa, pb, nv); pa += nv; pb += nv
    if pos < nsp:
        cmp(f"pos{pos} fin_pre", pa, pb, dm); pa += dm; pb += dm
        cmp(f"pos{pos} fin_post", pa, pb, dm); pa += dm; pb += dm
        for L in range(nl):
            if L not in ATTN:
                cmp(f"pos{pos} conv[{L}]", pa, pb, 2 * dm); pa += 2 * dm; pb += 2 * dm
        for L in ATTN:
            for wh in range(2):
                cnt = (pos + 1) * NKV * HD
                cmp(f"pos{pos} kv[{L}][{wh}]", pa, pb, cnt); pa += cnt; pb += cnt

print()
print(f"A consumed {pa} of {ra.size} f64")
print(f"B consumed {pb} of {rb.size} f64")
if pa != ra.size or pb != rb.size:
    print("LAYOUT MISMATCH: dump sizes disagree with the consumed layout")
print(f"TOTAL differing f64 bit patterns: {total_bad}   worst |delta| = {worst:.3e}")
if total_bad == 0 and pa == ra.size and pb == rb.size:
    print("DIFF PASS (bit-identical)")
    sys.exit(0)
print("DIFF FAIL")
sys.exit(1)
