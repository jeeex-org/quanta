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

# ==================== EOS POLICY (queued for the next promotion) ==========
# The defect: EOS inside the sampled candidate set truncates a generation at
# random. Vector EOSLOG has the EOS id inside the top-k = 4 candidate set but
# NOT as the argmax; EOSARGLOG has EOS as the argmax. Every expectation
# below is computed by numpy from the RAW logits, and the two -1e30 masks the
# library writes are modelled explicitly (exp(-1e30 - max) == 0.0), so this is
# a reference check, not a restatement of the library's own output. The draw
# replica is the same bit-exact LCG + cumsum walk as check 5.
EOS = 2

def softmax_ref(lg):
    r = np.exp(lg - lg.max())
    return r / r.sum()

def walk(probs, count, seed):
    """Bit-exact replica of rng_next() + sample_draw's cumsum walk."""
    st, out, cs = seed, [], np.cumsum(probs)
    for _ in range(count):
        st = (st * 1103515245 + 12345) % 2147483648
        u = st / 2147483648.0
        idx = int(np.searchsorted(cs, u, side='right'))
        out.append(idx if idx < probs.size else probs.size - 1)
    return out

ev = dec(data['EOSLOG'][0])
raw_top4 = set(int(x) for x in np.argsort(-ev)[:4])
check('EOS vector (sanity): EOS is inside top-k=4 (rank 3), not the argmax',
      EOS in raw_top4 and int(ev.argmax()) != EOS and int(np.argsort(-ev)[2]) == EOS,
      f"rank3={int(np.argsort(-ev)[2])} argmax={int(ev.argmax())} raw_top4={sorted(raw_top4)}")

# disabled policy must not touch a single bit
check('policy disabled -> logits bit-identical (no-op)',
      data['EOSLOG'][0] == data['EOSOFF_LOG'][0], '8/8 f64 bit patterns equal')

# ---- BEFORE: EOS is a live candidate and the draw lands on it -------------
kept_off = set(int(x) for x in data['EOSOFF_K_TOPK'][0])
check('policy OFF: kept top-4 == numpy top-4 and CONTAINS EOS',
      kept_off == raw_top4 and EOS in kept_off, f"kept={sorted(kept_off)} numpy={sorted(raw_top4)}")
foff = [int(x) for x in data['EOSOFF_FULL_DRAWS'][0]]
check('policy OFF: 200 sampled ids at temp 0.8 / k=4 DO hit EOS (the defect)',
      EOS in foff, f"eos drawn {foff.count(EOS)}/{len(foff)}")

# ---- AFTER: EOS rank-2 not argmax -> excluded -----------------------------
order_on = [i for i in np.argsort(-ev) if i != EOS][:4]
kept_on = set(int(x) for x in data['EOSON_K_TOPK'][0])
check('policy ON: EOS EXCLUDED from the kept set (the replacement is pulled in)',
      kept_on == set(order_on) and EOS not in kept_on,
      f"kept={sorted(kept_on)} expected={sorted(order_on)}")
check('policy ON: kept count still == k', int(data['EOSON_K_TOPK_COUNT'][0][0]) == 4,
      f"count={data['EOSON_K_TOPK_COUNT'][0][0]}")

pon = dec(data['EOSON_PROB'][0])
masked = ev.copy(); masked[EOS] = -np.inf
ref_on = softmax_ref(masked)
check('policy ON: EOS probability is EXACTLY 0 and the rest matches numpy softmax',
      pon[EOS] == 0.0 and abs(pon.sum() - 1.0) <= SUM_TOL and np.abs(pon - ref_on).max() <= TOL,
      f"p[eos]={pon[EOS]} max_abs={np.abs(pon-ref_on).max():.3e} sum={pon.sum():.17g}")

seq_on = [int(x) for x in data['EOSON_DRAWSEQ'][0]]
check('policy ON: 200 draw ids == numpy replica and EOS is never drawn',
      seq_on == walk(pon, len(seq_on), 4242) and EOS not in seq_on,
      f"n={len(seq_on)} eos_drawn={EOS in seq_on}")
fon = [int(x) for x in data['EOSON_FULL_DRAWS'][0]]
check('policy ON: 200 sample_full ids never EOS and stay inside the EOS-free top-4',
      EOS not in fon and set(fon) <= set(order_on), f"drawn={sorted(set(fon))} pool={sorted(order_on)}")
check('same seed: policy OFF vs ON -> different id sequence',
      foff != fon, f"off[:10]={foff[:10]} on[:10]={fon[:10]}")
check('greedy unchanged (EOS not the argmax) -> argmax id still returned',
      int(data['EOS_GREEDY'][0][0]) == int(ev.argmax()), f"got={data['EOS_GREEDY'][0][0]} argmax={int(ev.argmax())}")

# ---- EOS IS the argmax: still returnable ---------------------------------
ea = dec(data['EOSARGLOG'][0])
check('EOS IS the argmax (sanity)', int(ea.argmax()) == EOS and int(np.argsort(-ea)[0]) == EOS,
      f"argmax={int(ea.argmax())}")
check('EOS IS the argmax -> greedy returns EOS (a turn can still end deliberately)',
      int(data['EOSARG_T0'][0][0]) == EOS, f"got={data['EOSARG_T0'][0][0]}")
kept_arg = set(int(x) for x in data['EOSARG_K_TOPK'][0])
order_arg = set(int(x) for x in np.argsort(-ea)[:4])
check('EOS IS the argmax -> kept in the candidate set (not masked)',
      kept_arg == order_arg and EOS in kept_arg, f"kept={sorted(kept_arg)} expected={sorted(order_arg)}")
parg = dec(data['EOSARG_PROB'][0])
check('EOS IS the argmax -> carries real mass and matches numpy softmax',
      parg[EOS] > 0.9 and np.abs(parg - softmax_ref(ea)).max() <= TOL,
      f"p[eos]={parg[EOS]:.6f} max_abs={np.abs(parg-softmax_ref(ea)).max():.3e}")
seq_arg = [int(x) for x in data['EOSARG_DRAWSEQ'][0]]
check('EOS IS the argmax -> 200 draw ids == numpy replica and EOS IS drawn',
      seq_arg == walk(parg, len(seq_arg), 1234) and EOS in seq_arg,
      f"n={len(seq_arg)} eos_drawn {seq_arg.count(EOS)}/{len(seq_arg)}")
farg = [int(x) for x in data['EOSARG_FULL_DRAWS'][0]]
check('EOS IS the argmax -> sample_full(temp=1, k=4) still returns EOS',
      EOS in farg, f"eos drawn {farg.count(EOS)}/{len(farg)}")

# ---- minimum length ------------------------------------------------------
mins = [int(x) for x in data['EOSMIN_DRAWS'][0]]
# NOTE: this case draws from EOSARGLOG (ea), not ev -- the mask has to come from ea.
masked_a = ea.copy(); masked_a[EOS] = -np.inf
pm, pf = softmax_ref(masked_a), softmax_ref(ea)     # EOS masked for the first 3 calls
st, exp_m = 99, []
csm, csf = np.cumsum(pm), np.cumsum(pf)
for j in range(6):
    st = (st * 1103515245 + 12345) % 2147483648
    cs = csm if j < 3 else csf
    idx = int(np.searchsorted(cs, st / 2147483648.0, side='right'))
    exp_m.append(idx if idx < ea.size else ea.size - 1)
check('min_len=3: the first 3 draws are NOT EOS even though EOS is the argmax',
      EOS not in mins[:3], f"first3={mins[:3]}")
check('min_len=3: EOS is drawable again once the floor is met',
      mins[3:] == [EOS] * 3, f"last3={mins[3:]}")
check('min_len=3: 6/6 ids == numpy replica (masked for 3 calls, then unmasked)',
      mins == exp_m, f"got={mins} replica={exp_m}")

print()
print(f"=== {len(fails)} failure(s) ===" if fails else "=== ALL CHECKS PASSED ===")
sys.exit(1 if fails else 0)
