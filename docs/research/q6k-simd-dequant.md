# Q6_K dequantisation in AVX2: 45.8 -> 2.0 ns/element, bit-identical

Status: measured on `0.0.243` (compiler md5 `26430066a4e04f61a687ccf6291b61d7`, built
from `0.0.241`'s `02b15543…`). One lever: **the `dq6`() compiler builtin**, plus the
two defect fixes it was blocked behind (separate doc). This is the ordered item 2 of
the prefill-batching work: `docs/research/prefill-batching.md` §4 named it as the
next lever and estimated 5.0 s/token decode and 5.9 s prefill.

## 0. The environment, recorded next to every number

The box is **not idle and not at full clock**. Every figure below carries its own
load line; the ratios are the honest quantity, because each before/after pair was
taken **back to back, in one process or in immediate succession**.

| | |
|---|---|
| governor | `powersave` (intel_pstate; 2.2-2.8 of a 5.4 GHz ceiling) |
| cores | 20 |
| ambient load | 13.68 / 12.42 / 12.19 at the start of the A/B, 16.65 at the peak |
| top CPU consumer | `Hermes` (Electron) **PID 2971875, 742 % CPU** (7.4 of 20 cores) for the whole session |
| throughput runs | `nice 0`. `nice -n 19` starves a throughput measurement to ~1 core on this box (see prefill-batching.md §10) and was NOT used |

Consequence: the absolute times are **~1.5x larger than the quiet-box figures** in
prefill-batching.md (§4 quotes 22.93 s for the no-logits token; the same code
measured 34.63 s here). Absolute numbers below are therefore labelled with their
load, and the before/after ratio is what the change is claimed on.

## 1. What was slow, and why the estimate was too small

`dequant_q6k` was a scalar loop, and it is not an ordinary scalar loop: per element
it performs **six integer divisions** to unpack the bit fields --

    let h0 = qhb - (qhb / 4) * 4
    let q1 = (ql0 - (ql0 / 16) * 16 + h0 * 16) - 32

-- and `idiv` is 20-40 cycles with no overlap. Measured, on a real Q6_K row:

| term | before | after |
|---|---:|---:|
| `FFN_DOWN_DEQ` (one 10752-element Q6_K row) | 492,105 ns | 21,376 ns |
| ns per element | **45.8** | **1.99** |
| ratio | | **23.0x** |

That is far past the 6.1x the previous unit predicted from the Q4_K comparison,
because the prediction compared *instruction counts*; the scalar Q6_K loop's cost is
dominated by `idiv`, which the SIMD form removes entirely. The isolated measurement
agrees (`tests/q6k_dequant_simd_test.quanta`, 2,097,152 real Q6_K elements, best of
3, interleaved in one process):

```
scalar: 89325 us total  = 42593 ps/elem  (89 ms for 2097152 elements)
dq6():  5292 us total  =  2523 ps/elem  (5 ms)
ratio scalar/dq6 x1687/100          (16.9x)
```

(The isolated ratio is lower than the in-forward 23.0x because the isolated run
re-reads the same 1.7 MB buffer, which is L3-resident after the first pass; the
in-forward number is the one that matters. Both are quoted rather than picking one.)

## 2. The builtin

`dq6(dst, ql, qh, dbits, scptr)` -- one call per **128-element half** of a Q6_K
super-block, so a 256-element block costs two calls. Five arguments, all in
registers (`rdi, rsi, rdx, rcx, r8`), no shared scratch: `dbits` is `d` as a raw
f64 bit pattern, so two pool workers dequantising different rows cannot race on a
scale cell -- the same reasoning that shaped `dq32*`.

### Why ONE name and not `dq6lo`/`dq6hi`

`dq32lo`/`dq32hi` split Q4_K because its `ql` is ONE nibble plane read twice: 32
contiguous outputs come from 32 contiguous raw bytes, so "low nibbles" and "high
nibbles" are two independent halves of the work. A Q6_K block is a 4-bit plane
(`ql`, 64 bytes) **plus a 2-bit plane (`qh`, 32 bytes)** whose 2-bit groups do **not**
line up with 32-element `ql` chunks:

    y[l]    = d*sc[is+0] * ((ql[l]    &15) | (((qh[l]>>0)&3)<<4) - 32)
    y[l+32] = d*sc[is+2] * ((ql[l+32] &15) | (((qh[l]>>2)&3)<<4) - 32)
    y[l+64] = d*sc[is+4] * ((ql[l]   >>4) | (((qh[l]>>4)&3)<<4) - 32)
    y[l+96] = d*sc[is+6] * ((ql[l+32]>>4) | (((qh[l]>>6)&3)<<4) - 32)      is = l/16

so the work is four `(nibble plane, qh shift, ql half, scale pair)` combinations x
two 16-element halves x four 4-element vector groups -- **32 vector groups** for the
128 outputs. Splitting that across two names would only divide the sections; the
caller needs all four, so it gets one call per 128 elements instead of eight per 32,
which also pays the fixed per-call cost (`flush_all`, the argument load, `ret`)
once instead of eight times.

### Bit-identity is the bar, and it is a multiply-order claim

The scalar loop computes `fmul(d, fmul(i2f(sc), i2f(q)))`, i.e. **`d * (sc*q)` with
the inner product first**. `sc` is a signed 8-bit scale and `q` in `[-32,31]`, so
`sc*q` is an integer in `[-4064,4064]` and is **exact** in binary64. The builtin
therefore multiplies by `sc` **before** `d`:

```
vcvtdq2pd  exact (q in [-32,31])
vmulpd     by (double)sc     exact (product is a small integer)
vmulpd     by d              the ONE rounding, in the same place as the scalar
```

Pre-folding `d*sc` at the caller would round twice and is **not** equivalent. This is
the single thing that must not be "optimised" here, and there is no FMA and no
reassociation. As with `dq32*`, only the **dequantised values** are produced -- never
a sum -- so no caller's accumulation order is touched.

### The emitted sequence

Per 4-element group (12 instructions): `vpmovzxbd xmm0,[rsi+qo]`; the nibble plane
(`vpand xmm0,xmm0,xmm4` for the low nibble, or `vpsrld xmm0,xmm0,4` for the high);
`vpmovzxbd xmm6,[rdx+hb]`; `vpsrld xmm6,xmm6,sh` (skipped when `sh == 0`);
`vpand xmm6,xmm6,xmm5`; `vpslld xmm6,xmm6,4`; `vpor`; `vpaddd xmm0,xmm0,xmm3`
(the `-32`); `vcvtdq2pd`; two `vmulpd`; `vmovupd [rdi+oo],ymm0`.

The three constants need **no general-purpose register**: `-32`, `15` and `3` all
come out of `vpcmpeqd` (all-ones) plus one shift, which keeps the builtin from
clobbering any GPR the caller's frame is using. The scales are
`vpbroadcastb xmm2,[r8+k]` + `vpmovsxbd` + `vcvtdq2pd` -- **sign-extended from the
i8 byte exactly as `i8_at()` does**, which is why a negative sub-scale is handled.

Byte encodings were verified against GNU as (`objdump` of an assembled `.s`) and
transcribed, not derived. Two transcription errors were caught by measurement rather
than by reading: `vmovq xmm1,rcx` is `…6e c9` (201), not `…ca` (202, which reads
**rdx** -- the `qh` pointer -- as `d`), and `vpbroadcastb`'s ModRM is the fixed byte
`0x50` with the scale index a **separate** disp8, not `0x50+k`. The second one
merged the two and produced a SIB byte, so the CPU raised **SIGILL** -- a loud
failure, which is why both were found in two builds.

## 3. Bit-identity evidence

Three independent checks, because "the same arithmetic" is an argument and this
needs a measurement:

1. **`test_suites/codes/q6k_dequant_ref_test.quanta` -- the llama.cpp oracle.**
   Pre-existing gate row. Compares `dequant_q6k()` (now the SIMD path) against
   **committed bit patterns dumped from `dequantize_row_q6_K`**, the hand-computed
   `ql[0]=0x21, sc[0]=2 -> -62.0` case, and the f64 **sum** and **sumsq** over all
   1024 elements. It passes unchanged:

       q6k_dequant_ref: PASS (bit-exact vs dequantize_row_q6_K)     rc=0

   This is the check that matters: it is an *external* oracle, so two paths that
   share a bug cannot pass by agreeing with each other.

2. **`tests/q6k_dequant_simd_test.quanta` -- scalar vs `dq6`, bit for bit.**
   A 256-block synthetic sweep (every `ql`/`qh`/`sc` byte through its whole range,
   `d` alternating 1.0 / -0.5 so the sign is exercised) plus **2,097,152 elements of
   the model's own Q6_K tensor**, plus the same comparison again *after* the timed
   repeats (a builtin that corrupts its own inputs would agree once and diverge on
   the third call):

       synthetic: differing f64 bit patterns = 0 / 65536
       real:      differing f64 bit patterns = 0 / 2097152
       real bit-identity after repeats = 0
       Q6K_SIMD PASS

3. **The correlation table is untouched by construction**, and it was checked
   rather than argued: the dequantised values are the same bits, so every downstream
   accumulation is unchanged.

## 4. End-to-end: a decode token and a prefill token

`tests/lfm2_op_profile.quanta`, serial (`mm_workers = 1`), one thread, back to back.
Load 13.68 before / 16.65 between the pair; governor `powersave`; top consumer
`Hermes` 742 %.

| measurement | before (scalar Q6_K) | after (`dq6`) | ratio | delta |
|---|---:|---:|---:|---:|
| `FULL_TOKEN_NO_LOGITS_POS0` (a **prefill** token) | 34.63 s | **24.16 s** | **1.43x** | -10.47 s |
| `FULL_TOKEN_WITH_LOGITS_POS0` (a **decode** token) | 49.52 s | **28.72 s** | **1.72x** | -20.80 s |
| tied output projection (WITH - NO) | 14.89 s | **4.56 s** | **3.27x** | -10.33 s |
| `FFN_DOWN_DEQ` ns/element | 45.8 | 1.99 | 23.0x | |
| `FFN_GATE_DEQ` ns/element (Q4_K, unchanged) | 8.4 | 5.7 | -- | noise |

The same binary pair, same process shape, same load: the only difference is one
`return dequant_q6k_scalar(...)` at the top of `dequant_q6k`, so this is a clean A/B
of the dequant and nothing else.

**Decode is the bigger win and the reason is structural:** the output projection is
73 % Q6_K dequant by element count, and it is the only place Q6_K is dequantised
once per *token* rather than once per row per batch. The task predicted 5.0 s/token
decode and 5.9 s prefill; measured **10.3 s** and **10.5 s**.

## 5. What is left, and what was NOT done

- **The `mm_embed_logits` scalar dot is still scalar.** The output projection after
  the fix is 4.56 s for 262.1 M elements = 17.4 ns/element, of which the dequant is
  ~2 ns; the remainder is the **left-to-right scalar accumulate at ~9-15 ns/element**
  against `mm_dot4`'s 2.73. That is the next lever, it is worth ~1.6-3 s/token, and
  it was deliberately **not** taken: switching it to `mm_dot4` changes the logits
  BITS (4-lane partial sums vs left-to-right), so it cannot be one lever with a
  bit-identity bar -- the correlation table would have to be re-measured and the
  bit-identical probes would go red by design.
- **`FFN_DOWN_DOT` is now the top term** of that op (39.5 us vs 21.4 us for the
  dequant, previously 45.2 vs 492.1).
- **Only AVX2 was implemented.** No AVX-512 path; a Q6_K `q4k_dot`-style fused
  matvec (never materialising f64) was not attempted.
- **The absolute times are load-dependent** and are ~1.5x the quiet-box figures in
  prefill-batching.md. The quiet-box post-fix rate was not measured: the box could
  not be freed.
- `B` beyond 8 and the 20-worker batched rate were not re-measured here (the
  prefill-batching bench, conf `1 8 8`, was started and abandoned because the
  op-profile A/B above already answers the before/after question and the bench runs
  are 8x longer).

## 6. Reproduce

    <qc> tests/q6k_dequant_simd_test.quanta /tmp/q6simd.bin && ( ulimit -c 0 -v 8000000; /tmp/q6simd.bin </dev/null )
    <qc> test_suites/codes/q6k_dequant_ref_test.quanta /tmp/q6r.bin && ./scripts/quanta_run.sh /tmp/q6r.bin </dev/null
    <qc> tests/lfm2_op_profile.quanta /tmp/op.bin && ( ulimit -c 0 -v 8000000; nice 0 /tmp/op.bin </dev/null )

    # the A/B: make dequant_q6k start with `return dequant_q6k_scalar(raw, nelements, out)`,
    # rebuild the driver, restore, rebuild, run both at nice 0 and record /proc/loadavg.
