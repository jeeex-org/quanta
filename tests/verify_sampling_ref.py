#!/usr/bin/env python3
# Independent reference check of lib/std/sampling.quanta (0.0.240).
#
# Input: the stdout of the Quanta harness (tests/sampling_ref.quanta), which
# prints f64 BIT PATTERNS as integers. Decoding the bits means numpy computes the
# softmax of EXACTLY the vector Quanta saw -- no assumption about how the literal
# formula rounded.
#
# Checks
#   1. numpy softmax(logits)  vs  Quanta sample_softmax  -> elementwise rel err
#   2. sum of Quanta probabilities == 1
#   3. argmax(logits) == ARGMAX == sample_full(temp=0)  (greedy semantics)
#   4. top-k kept set == numpy top-k
#   5. DRAWS: a bit-exact Python replica of rng_next (LCG) + the cumsum walk over
#      the QUANTA probabilities must reproduce the SAME id sequence
#   6. fixed seed reproducibility: REPRO_A == REPRO_B, and REPRO_C differs
import struct, sys
import numpy as np

TOL = 1e-11          # probabilities: expf is 7e-14 rel worst, plus a few ULP
SUM_TOL = 1e-12

def dec(bits):
    return np.array([struct.unpack('<d', struct.pack('<q', (int(x) - 2**64) if int(x) >= 2**63 else int(x)))[0]
                     for x in bits], dtype=np.float64)

data = {}
for line in open(sys.argv[1] if len(sys.argv) > 1 else 'ref_out.txt'):
    line = line.strip()
    if not line:
        continue
    tag, *rest = line.split()
    data.setdefault(tag, []).append(rest)

logits = dec(data['LOGITS'][0])
probs  = dec(data['SOFTMAX'][0])
n = logits.size
fails = []

def check(name, ok, detail=''):
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")
    if not ok:
        fails.append(name)

# ---- 1. numpy reference softmax ----
m = logits.max()
ref = np.exp(logits - m)
ref /= ref.sum()
abs_err = np.abs(probs - ref)
rel_err = abs_err / np.maximum(ref, 1e-300)
check('softmax vs numpy', abs_err.max() <= TOL and rel_err.max() <= TOL,
      f"max_abs={abs_err.max():.3e} max_rel={rel_err.max():.3e} tol={TOL:.0e}")

# a naive non-stable softmax for the record
naive = np.exp(logits); naive /= naive.sum()
check('softmax matches naive (numpy)', np.abs(ref - naive).max() <= 1e-15,
      f"max_abs(ref,naive)={np.abs(ref-naive).max():.3e}")

# ---- 2. sum == 1 ----
s = probs.sum()
check('probabilities sum to 1', abs(s - 1.0) <= SUM_TOL, f"sum={s:.17g}")

# ---- 3. argmax / greedy ----
am = int(logits.argmax())
check('argmax', int(data['ARGMAX'][0][0]) == am, f"quanta={data['ARGMAX'][0][0]} numpy={am}")
check('sample_full(temp=0) == argmax', int(data['FULL_T0'][0][0]) == am,
      f"quanta={data['FULL_T0'][0][0]}")

# ---- 4. top-k ----
k = int(data['TOPK_KEPT'][0][0])
kept = set(int(x) for x in data['TOPK'][0])
npref = set(int(x) for x in np.argsort(-logits)[:k])
check('top-k kept set == numpy top-k', kept == npref,
      f"k={k} kept={sorted(kept)} numpy={sorted(npref)}")

# ---- 5. bit-exact draw replica ----
#   rng_next(): state = (state*a + c) - ((state*a + c)/2^31)*2^31   (mod 2^31)
#   u = r / 2^31 ; walk cumsum, first i with cumsum > u
state = 4242
def rng_next():
    global state
    state = (state * 1103515245 + 12345) % 2147483648
    return state
pred = []
cs = np.cumsum(probs)
for _ in range(len(data['DRAWS'][0])):
    r = rng_next()
    u = r / 2147483648.0
    idx = int(np.searchsorted(cs, u, side='right'))
    if idx >= n:
        idx = n - 1
    pred.append(idx)
got = [int(x) for x in data['DRAWS'][0]]
check('draw sequence == replica', pred == got,
      f"n={len(got)} first10 got={got[:10]} pred={pred[:10]}")

# ---- 6. reproducibility ----
a = [int(x) for x in data['REPRO_A'][0]]
b = [int(x) for x in data['REPRO_B'][0]]
c = [int(x) for x in data['REPRO_C'][0]]
check('same seed -> same samples', a == b, f"A={a} B={b}")
check('different seed -> different samples', a != c, f"C={c}")

# ---- 7. top-k path stays inside the top-k pool ----
pool = set(int(x) for x in np.argsort(-logits)[:16])
tp = [int(x) for x in data['TOPKPATH'][0]]
check('sample_full(k=16) draws only from top-16', set(tp) <= pool,
      f"drawn={sorted(set(tp))} pool={sorted(pool)}")

# ---- 8. large-magnitude logits: the max subtraction must actually happen ----
big = dec(data['BIGLOG'][0])
bp  = dec(data['BIGPROB'][0])
mb = big.max()
rbig = np.exp(big - mb); rbig /= rbig.sum()
check('large-logit softmax vs numpy (max subtracted)', np.all(np.isfinite(bp)) and np.abs(bp - rbig).max() <= TOL,
      f"max_abs={np.abs(bp-rbig).max():.3e} sum={bp.sum():.17g}")
check('large-logit sum == 1', abs(bp.sum() - 1.0) <= SUM_TOL, f"sum={bp.sum():.17g}")

negp = dec(data['NEGPROB'][0])
check('all-equal -1000 logits -> uniform 0.25', np.allclose(negp, 0.25, atol=1e-15, rtol=0),
      f"probs={negp.tolist()}")

print()
print(f"=== {len(fails)} failure(s) ===" if fails else "=== ALL CHECKS PASSED ===")
sys.exit(1 if fails else 0)
