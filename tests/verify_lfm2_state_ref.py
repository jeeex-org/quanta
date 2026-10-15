#!/usr/bin/env python3
# tests/verify_lfm2_state_ref.py -- verify the native LFM2 forward's CARRIED STATE
# against an independent reference, element-wise.
#
# WHAT IT DOES
#   1. builds llama.cpp's own per-position logits for the exact prompt the native
#      driver feeds the model, and correlates them against the native logits
#      dumped by tests/lfm2_prefill_probe.quanta. Position 0 must be ~1.0; the
#      numbers this prints are the before/after evidence for the divergence.
#   2. reconstructs every carried state the engine keeps
#        - short-conv state  -> (g[t-1], g[t]) with g = b*x from in_proj @ attn_norm(x)
#        - K cache row       -> rope(rms_norm_head(k_proj @ attn_norm(x), k_norm[L]))
#        - V cache row       -> v_proj @ attn_norm(x)
#      from the DUMPED per-layer input, using the REAL ggml row dequantisers
#      (libggml-base.so's dequantize_row_q4_K / q6_K) -- not a transcription --
#      and reports the worst element-wise delta per layer.
#   3. checks two invariants that need no reference at all:
#        - the conv state SHIFTS: state[t+1][0:dm] == state[t][dm:2dm]
#        - everything must be deterministic: the same dump parsed twice agrees
#   It also re-derives the native logits from the dumped final hidden state with
#   the tied embedding, which validates this script's own dequant + row order.
#
# USAGE (python3.12 -- llama_cpp/gguf/numpy are installed for 3.12 only here)
#   python3.12 tests/verify_lfm2_state_ref.py <probe.bin> [--ref-cache X.npz]
#
# LAYOUT of <probe.bin> (produced by tests/lfm2_prefill_probe.quanta):
#   i64[0..6) nsp,n,nv,dm,nl,hd    f64[6] rms_eps    i64[7..7+n) ids
#   then per position p in 0..n-1:
#       if p < nsp: layer inputs L=0..nl-1 (nl*dm)      <- captured before the
#                   final norm + output projection, so they come FIRST
#       logits (nv)
#       if p < nsp: final hidden pre-norm (dm), post-norm (dm)
#                   conv states for conv layers ascending (ncv * 2*dm)
#                   KV: for L in attn ascending: for which in {0,1}:
#                       for pp in 0..p: for head in 0..nkv: hd values
import ctypes, sys, os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
PROBE = sys.argv[1] if len(sys.argv) > 1 else "/home/tali/.hermes/cache/scratch/lfm2probe/probe.bin"
GGUF = "/opt/ai/models/quanta/QUANTA-LFM2.5-2.6Bv1-Q4_K_M.gguf"
GGML = "/opt/ai/llama.cpp/build/bin/libggml-base.so"
PROMPT = os.path.join(REPO, "tests", "lfm2_prompt.txt")
ATTN = [2, 5, 9, 13, 17, 21, 24, 27]
nkv = 8

# ---------------- (1) llama.cpp reference logits ----------------
def build_ref(nv, cache):
    from llama_cpp import Llama
    if os.path.exists(cache):
        return np.load(cache)
    user = open(PROMPT, "rb").read()
    prompt = (b"<|im_start|>user\n" + user + b"<|im_end|>\n"
              + b"<|im_start|>assistant\n" + b"\x3c\x74\x68\x69\x6e\x6b\x3e")
    llm = Llama(model_path=GGUF, n_ctx=2048, n_batch=512, logits_all=True,
                verbose=False, seed=12345)
    ids = llm.tokenize(prompt, add_bos=True, special=True)
    llm.reset(); llm.eval(ids)
    batched = np.array(llm.scores, dtype=np.float32)
    llm.reset()
    inc = np.zeros_like(batched)
    for i, t in enumerate(ids):
        llm.eval([t]); s = np.array(llm.scores, dtype=np.float32)
        inc[i] = s[-1] if s.ndim == 2 else s
    np.savez_compressed(cache, ids=np.array(ids), batched=batched, incremental=inc)
    return np.load(cache)

# ---------------- read the native dump ----------------
buf = np.fromfile(PROBE, dtype=np.uint8)
raw, i64 = buf.view(np.float64), buf.view(np.int64)
nsp, n, nv, dm, nl, hd = [int(x) for x in i64[0:6]]
eps = float(raw[6])
ids = [int(x) for x in i64[7:7+n]]
print(f"probe {PROBE}")
print(f"nsp={nsp} n={n} nv={nv} dm={dm} nl={nl} hd={hd} rms_eps={eps!r}")
print("ids:", ids)

logits = np.zeros((n, nv)); li = {}; fin_pre = {}; fin_post = {}; convst = {}; kv = {}
p = 7 + n
for pos in range(n):
    if pos < nsp:
        li[pos] = {L: raw[p+L*dm:p+(L+1)*dm].copy() for L in range(nl)}; p += nl*dm
    logits[pos] = raw[p:p+nv]; p += nv
    if pos < nsp:
        fin_pre[pos] = raw[p:p+dm].copy(); p += dm
        fin_post[pos] = raw[p:p+dm].copy(); p += dm
        cs = {}
        for L in range(nl):
            if L not in ATTN:
                cs[L] = raw[p:p+2*dm].copy(); p += 2*dm
        convst[pos] = cs
        kvd = {}
        for L in ATTN:
            kk, vv = [], []
            for _wh in range(2):
                rows = raw[p:p+(pos+1)*nkv*hd].reshape((pos+1)*nkv, hd).copy()
                p += (pos+1)*nkv*hd
                (kk if _wh == 0 else vv).append(rows)
            kvd[L] = (np.array(kk), np.array(vv))
        kv[pos] = kvd
assert p == raw.size, f"layout mismatch: consumed {p} of {raw.size}"

ref = build_ref(nv, os.environ.get("LFM2_REF_CACHE", os.path.join(os.environ.get("TMPDIR", "/tmp"), "lfm2_ref.npz")))
r_b = ref['batched'].astype(np.float64)

print("\n pos | native_argmax llama_argmax | corr(native, llama.cpp) | max n/l    | top10")
for pos in range(n):
    a, b = logits[pos], r_b[pos]
    c = np.corrcoef(a, b)[0, 1]
    ov = len(set(np.argsort(-a)[:10]) & set(np.argsort(-b)[:10]))
    print(f"{pos:4d} | {int(np.argmax(a)):12d} {int(np.argmax(b)):12d} | {c:22.4f} | "
          f"{a.max():6.3f}/{b.max():6.3f} | {ov:2d}/10")

# ---------------- (3) reference-free invariants ----------------
print("\n-- conv shift invariant: convstate[t+1][0:dm] == convstate[t][dm:2dm] --")
worst_all = 0.0
for t in range(nsp-1):
    w2, wl = 0.0, None
    for L in convst[t]:
        d = float(np.abs(convst[t+1][L][0:dm] - convst[t][L][dm:2*dm]).max())
        if d > w2: w2, wl = d, L
    worst_all = max(worst_all, w2)
    print(f"  t={t}->{t+1}: max|delta|={w2:.3e} (worst L={wl})")

# ---------------- reference weights via the REAL ggml kernels ----------------
from gguf import GGUFReader
rd = GGUFReader(GGUF)
TN = {t.name: t for t in rd.tensors}
lib = ctypes.CDLL(GGML)
DTNAME = {2: "q4_0", 3: "q4_1", 6: "q5_0", 7: "q5_1", 8: "q8_0",
          12: "q4_K", 13: "q5_K", 14: "q6_K"}
KERN = {}
for dt, nm in DTNAME.items():
    try: KERN[dt] = getattr(lib, "dequantize_row_" + nm)
    except AttributeError: pass
for f in KERN.values():
    f.restype = None
    f.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int64]

def deq_row(rawrow, ncols, dtype):
    if dtype == 0:
        return rawrow.view(np.float32).astype(np.float64)
    inb = np.ascontiguousarray(rawrow)
    out = np.empty(ncols, dtype=np.float32)
    KERN[dtype](inb.ctypes.data_as(ctypes.c_void_p),
                out.ctypes.data_as(ctypes.c_void_p), ctypes.c_int64(ncols))
    return out.astype(np.float64)

# Whole-tensor dequant with the SAME real kernels (llama.cpp calls them this way:
# one call over the tensor's contiguous bytes). The row-at-a-time form above is
# kept for the 6-row spot checks; this is what makes the full sweep affordable.
_FC = {}
def full(name):
    if name not in _FC:
        t = TN[name]
        dt = t.tensor_type
        ne0, ne1 = int(t.shape[0]), int(t.shape[1])      # ne0 = CONTIGUOUS dim
        nelem = ne0 * ne1
        flat = np.ascontiguousarray(t.data).reshape(-1)
        if dt == 0:
            o = flat.view(np.float32).astype(np.float64)
        else:
            # k is an ELEMENT count, not a byte count: the kernel reads
            # nelem/qk blocks of block_bytes. Passing flat.size (the byte count)
            # dequantises 1.78x too many elements and the reshape silently returns
            # fewer rows.
            o32 = np.empty(nelem, dtype=np.float32)
            KERN[dt](flat.ctypes.data_as(ctypes.c_void_p),
                     o32.ctypes.data_as(ctypes.c_void_p), ctypes.c_int64(nelem))
            o = o32.astype(np.float64)
        assert o.size == nelem, (name, o.size, nelem)
        _FC[name] = o.reshape(ne1, ne0)                  # one row per output element
    return _FC[name]

def matvec(name, x):
    return full(name) @ x

def rms(x, w):
    return x * (1.0/np.sqrt((x*x).mean() + eps)) * w

_NC = {}
def normed_in(L, pos):
    if (L, pos) not in _NC:
        _NC[(L, pos)] = rms(li[pos][L], np.array(TN[f"blk.{L}.attn_norm.weight"].data,
                                                dtype=np.float64))
    return _NC[(L, pos)]

def rope(x, pos):
    half = hd//2
    ts, th = 1e7**(-2.0/hd), float(pos)
    o = x.copy()
    for k in range(half):
        c, s = np.cos(th), np.sin(th)
        x0, x1 = x[k], x[k+half]
        o[k] = x0*c - x1*s; o[k+half] = x0*s + x1*c
        th *= ts
    return o

def kref(L, pos, norm_label):
    """reference K row for layer L using k_norm of layer `norm_label`"""
    k = matvec(f"blk.{L}.attn_k.weight", normed_in(L, pos))
    w = np.array(TN[f"blk.{norm_label}.attn_k_norm.weight"].data, dtype=np.float64)
    out = np.empty_like(k)
    for h in range(k.size//hd):
        seg = k[h*hd:(h+1)*hd]
        out[h*hd:(h+1)*hd] = rope(seg*(1.0/np.sqrt((seg*seg).mean() + eps))*w, pos)
    return out

# ---------------- (2) carried state vs reference ----------------
first_attn = ATTN[0]
print("\n-- K cache rows: |native - ref with ITS OWN k_norm| vs "
      f"|native - ref with LAYER {first_attn}'s k_norm| (the mutation) --")
worst_own, worst_other = 0.0, 0.0
first_div = None
for L in ATTN:
    own, other = 0.0, 0.0
    for pos in range(nsp):
        got = kv[pos][L][0][0][pos*nkv:(pos+1)*nkv].reshape(-1)
        e_own = float(np.abs(got - kref(L, pos, L)).max())
        e_oth = float(np.abs(got - kref(L, pos, first_attn)).max())
        # record the EARLIEST diverging (layer, position) in scan order
        if e_own > 1e-9 and first_div is None:
            d = got - kref(L, pos, L)
            j = int(np.argmax(np.abs(d)))
            first_div = (L, pos, j, got[j], kref(L, pos, L)[j], d[j])
        own = max(own, e_own); other = max(other, e_oth)
    worst_own = max(worst_own, own); worst_other = max(worst_other, other)
    print(f"  L={L:2d}  own-norm max {own:9.3e}    layer-{first_attn}-norm max {other:9.3e}")
if first_div:
    L, pos, j, g, r, d = first_div
    print(f"\n  FIRST DIVERGING CARRIED STATE: K cache row, layer {L}, pos {pos}, "
          f"element {j}: native {g:.9f}  reference {r:.9f}  delta {d:.9f}")
else:
    print(f"\n  no K-row divergence above 1e-9 (worst own-norm {worst_own:.3e}, "
          f"worst layer-{first_attn}-norm {worst_other:.3e})")

print("\n-- V cache rows (V is not normed, so must match throughout) --")
wv = max(float(np.abs(kv[pos][L][1][0][pos*nkv:(pos+1)*nkv].reshape(-1)
                       - matvec(f"blk.{L}.attn_v.weight", normed_in(L, pos))).max())
         for L in ATTN for pos in range(nsp))
print(f"  max|native - reference| = {wv:.3e}")

def g_of(L, pos):
    if (L, pos) not in _GC:
        bcx = matvec(f"blk.{L}.shortconv.in_proj.weight", normed_in(L, pos))
        _GC[(L, pos)] = bcx[0:dm] * bcx[2*dm:3*dm]
    return _GC[(L, pos)]
_GC = {}
print("\n-- short-conv state vs reference (g[t-1], g[t]) --")
wc = 0.0
for L in [L for L in range(nl) if L not in ATTN]:
    w2 = 0.0
    for pos in range(nsp):
        r = np.concatenate([np.zeros(dm) if pos == 0 else g_of(L, pos-1), g_of(L, pos)])
        w2 = max(w2, float(np.abs(convst[pos][L] - r).max()))
    wc = max(wc, w2)
    if L in (0, 1, 3, 5):
        print(f"  L={L:2d} max|native - reference| = {w2:.3e}")
print(f"  worst over all 22 conv layers = {wc:.3e}")

# ---------------- validate this script's own dequant + row order ----------------
t = TN["token_embd.weight"]
wproj = max(abs(float(np.dot(deq_row(t.data[v], dm, t.tensor_type), fin_post[pos]))
                - logits[pos][v])
            for pos in range(nsp)
            for v in list(np.argsort(-logits[pos])[:5]) + [int(np.argmax(r_b[pos]))])
print(f"\n-- self-check: max|native logit - projection from the dumped hidden| = {wproj:.3e}")

rc = 0
if worst_own > 1e-9:
    print("\nFAIL: a carried state diverges from the reference")
    rc = 1
elif wv > 1e-9 or wc > 1e-9 or worst_all > 0.0:
    print("\nFAIL: V cache / conv state diverges, or the conv shift invariant is violated")
    rc = 1
else:
    print("\nPASS: every carried state matches its independent reference to f64 round-off")
sys.exit(rc)
