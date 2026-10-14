# 0.0.239 — WIP

**Lever: vector-register SIMD dequantisation of Q4_K weights.** One lever, one version,
one mechanism: two new emitter builtins (`dq32lo` / `dq32hi`) that turn 32 raw Q4_K bytes
into the 32 f64 of one sub-block half inside ymm registers, and the two call sites in
`dequant_q4k` that use them.

Committed golden: `compiler/0.0.239/bin/x86/qc`, md5 `6f83fe08a7f8819a725fe50c81680ef1`
(the self-host fixed point).

---

## 1. The profile this comes from (measured first, as required)

All of this is from raw output in this session, on the golden 0.0.238 compiler, load
~10 on 20 cores (another unit was running; that matters for the CPU% figures, see §7).

### 1a. Per-forward syscalls — the "per-row pread" hypothesis, tested and REFUTED

`strace -f -c -e trace=read,pread64,lseek,mmap,munmap,futex,clone,madvise` over ONE
serial 30-layer forward (`stage1/native_bench_w.quanta`, `NW=1`):

| syscall | calls | note |
|---|---|---|
| `pread64` | **1,055,745** | exactly one per matvec row (1.32 M rows/token; the FFN/attn matvecs) |
| `read` | 1,944,160 | tokenizer metadata at LOAD time, not per token |
| `lseek` | 1,099,349 | pairs with `read` |
| `futex` | 7,225 (20 workers) | the pool protocol |
| `clone` | 20 | the pool — the A9 fix holds |

The `read`/`lseek` pair is **load-time**, not per-token: a matvec-only workload
(`par_one.quanta`, 60 x ffn_gate) shows **645,120 preads = 60 x 10,752 rows** and
**423,797 `read` + 421,777 `lseek`**, i.e. the reads come from walking the tokenizer
metadata arrays (128,000 tokens + 293,320 merges ~= 421,320 entries), independent of
forward count.

**Cost, measured without strace** (`/usr/bin/time -v`, 60 x ffn_gate, serial):
User 32.23 s, **System 0.49 s** -> syscall time is **~1.5%** of the matvec. It does not
grow with worker count (System 0.49 s @1 worker, 0.73 s @8, 0.86 s @20). Walking the
existing mmap instead of `pread` is therefore a **~1% lever, not the lever** — the
matvec's own per-row split below confirms it (I/O is 485-535 ns of a ~42,000 ns row).

### 1b. Where per-row time goes — dequant is 70%

A probe that times the three terms separately on a REAL Q4_K row (`ffn_gate` [10752x2048],
1152 raw bytes/row), best of interleaved runs in one process:

| term | ns per row (2048 elements) | share |
|---|---|---|
| I/O (`gguf_read_tensor_bytes_at`) | 485-535 | **1.2%** |
| **dequant** (`read_block_f64` -> `dequant_q4k`) | 29,134-35,006 | **~70%** |
| dot (`mm_dot4`) | 6,021-8,281 | ~15% |
| full serial matvec | 42,104-45,241 | — |

The same probe over the full forward gives `matvec_ms=543` for a 22 M-MAC FFN matvec.

### 1c. Why no lib/std reformulation can fix it

`micro.quanta` / `micro2.quanta`, ns per element on real bytes:

| variant | ns/elem |
|---|---|
| store only (2048 stores) | 6.36 |
| + `fsub(fmul(d1, i2f(nib)), mm1)` | 15.5 |
| + the byte load | 16.9 |
| the exact `dequant_q4k` inner shape, scales hoisted | 15.2 |
| the REAL `dequant_q4k` | 19.5 |
| 16-entry per-chunk table (the file's own rejected idea, re-measured) | 22.2 (SLOWER) |
| scale extraction hoisted to const / to runtime values | 13-17 — inside the noise band |

Blunt conclusion: **the scalar dequant is at this compiler's floor, ~15-20 ns/element,
and no rearrangement of the scalar form beats it.** Disassembly of a minimal loop
(`minloop.quanta`) shows why: every operation is a frame round trip. One `mulsd` costs

```
  mov -0x128(%rbp),%rdi ; mov -0x130(%rbp),%rsi
  movq %rdi,%xmm0 ; movq %rsi,%xmm1 ; mulsd %xmm1,%xmm0
  movq %xmm0,%rax ; mov %rax,-0x138(%rbp,%riz,1)
```

~8 memory ops per arithmetic op, and the same value is stored to several slots. This is
the **spill/reload traffic** `compiler/0.0.238/WIP.md` §4b independently identifies
(`work()` = 254 instructions vs gcc's 9). It also explains, correctly, why the file's
recorded attempts failed: the AVX2 f64 dequant (267 ms), the `nib2f64` builtin
(194 ms) and this table all passed their operands **through memory**. A builtin that
keeps the whole 4-element group in **ymm registers** is a different mechanism, and it
is the one `docs/plans/lfm2-native-inference-perf.md` §"block-consuming SIMD kernels"
predicted would be needed.

## 2. What landed

- `src/x86/emitter.quanta` — four builtins: `dq32lo`/`dq32hi` (32 elements/call, the
  form the matvec uses) and `dq4lo`/`dq4hi` (4 elements/call, kept for testing and
  because it is the simpler statement of the contract). Every byte encoding was
  **verified against GNU as** (assembled a `.s`, objdump'd it), not derived by hand.
- `src/x86/features.quanta` — the four names registered in `is_prim_intrin`, without
  which the semantic pass rejects the calls as `call to undeclared function`.
- `lib/std/gguf.quanta` — `dequant_q4k`'s 32-iteration inner loop replaced by
  `dq32lo(op, q, f64bits(d1), f64bits(mm1))` + `dq32hi(op+256, q, f64bits(d2), f64bits(mm2))`.
  The scales go in as **raw f64 bit patterns in registers**, not as pointers: a pointer
  would force a caller-side scratch buffer, and in the row-parallel matvec two workers
  dequantise different rows at once.

The builtins are the contract:

```
dq32lo(dst, q, d, mm)  -> dst[0..31]  = (q[j] & 0x0f) * d - mm
dq32hi(dst, q, d, mm)  -> dst[0..31]  = (q[j] >>   4) * d - mm
```

### The one bug found, and how

The first version used `vpslld 4; vpsrld 4` to mask the low nibble. That returns the
byte **unchanged** ((b<<4)>>4 == b for b < 256), so the high nibbles were right and the
low ones wrong: **985 of 2048 elements mismatched**. The correct mask is
`(b<<28)>>28`, i.e. shift 28 (32-4), not 4. Fixed, re-measured: 0/2048 mismatches.

## 3. Bit-exactness — the correctness bar here is EQUAL, not close

This change touches **only the dequantised values**, never a sum. Each element is
`(double)nib * d - mm`; `cvtdq2pd` is exact for nib in 0..15, `vmulpd` == `mulsd`
(commutative, identical rounding), `vsubpd` == `subsd`. No reassociation, no FMA. So the
f64 row handed to `mm_dot4` is byte-identical, and every downstream accumulation order —
and therefore every logit — is unchanged.

| check | result |
|---|---|
| dequantised row, element-wise bits vs scalar `dequant_q4k` | **0 / 2048 mismatches** (dq4 and dq32) |
| FULL 128,000-element logits vector, one real serial forward, HEAD lib vs patched lib | `cmp` -> **identical**, 1,024,000 bytes each |
| argmax, same run | **5922** on both (== the stored oracle) |
| `logit[argmax]` | **26.922279** on both |
| argmax at every worker count 1/2/4/8/20 | **5922** on all |
| `lfm2_threaded_pool_test` gate row (parallel matvec identity, rc=7) | GREEN |

## 4. Measured effect

### 4a. The dequant itself (best of interleaved runs in one process, real Q4_K row)

| variant | ns/element | vs scalar |
|---|---|---|
| scalar `dequant_q4k` | 15-16 | 1.00x |
| `dq4lo`/`dq4hi` (4/call, pointer scales) | 9 | 1.9x |
| `dq4lo`/`dq4hi` (4/call, register scales) | 6-8 | 2.1-2.3x |
| **`dq32lo`/`dq32hi` (32/call, register scales)** | **3-4** | **4.1-4.5x** |

The jump from 9 to 3-4 is the argument marshalling and `flush_all()` being a fixed cost
paid 16x per chunk by the 4-element form and 2x by the 32-element form.

### 4b. The token, 1/2/4/8/20 workers — the required before/after

Command (both rows): `printf '%d 2\n' $nw > stage1/bench_w.conf; /usr/bin/time -v <bin> </dev/null`

| workers | before s/token (2 runs) | after s/token (2 runs) | speedup | tok/s after |
|---|---|---|---|---|
| 1 | 67.6 / 75.4 | **58.5 / 48.5** | ~1.4x | 0.018 |
| 2 | 41.4 / 40.2 | **26.7 / 26.6** | 1.53x | 0.037 |
| 4 | 22.7 / 23.7 | **14.96 / 14.69** | 1.56x | 0.067 |
| 8 | 16.20 / 15.99 | **10.10 / 10.05** | 1.60x | 0.099 |
| 20 | 12.29 / 12.41 | **7.70 / 8.17** | 1.56x | **0.126** |

RSS held: 127-151 MB before, 147-151 MB after (under the 4-8 GB cap). No regression.
argmax 5922 everywhere. The "before" row reproduces the previous unit's numbers exactly
(70.5 / 41.8 / 24.5 / 16.7 / 12.8 s/token), so the baseline is sound.

### 4c. Why the token is only ~1.5x when the dequant is 4x — measured, not guessed

Same probe, one serial forward each:

| build | full forward | logits skipped | output projection |
|---|---|---|---|
| 0.0.238 + HEAD lib | **73,881 ms** | — | — |
| 0.0.239 (this) | **48,143 ms** | 33,799 ms | **14,344 ms (29.8%)** |

So the Q4_K **layer stack** went ~59.5 s -> 33.8 s (**~1.76x**), while the **tied output
projection** — 128,000 rows of `token_embd.weight`, which is **Q6_K (dtype 14)**, not
Q4_K — is **14.3 s of the 48.1 s token and completely untouched by this version**. That
is the next lever and it is now the single largest item in a token. It is deliberately
NOT attempted here: Q6_K packs 6 bits as a 4-bit plane plus a 2-bit plane, so it needs a
different builtin, and one lever per version is the rule that made the 0.0.238 result
interpretable.

## 5. Gate, fixpoint, reproducibility

```
=== Results: 225/225 pass, 0 fail (incl. 0 compile-fail) [rows: EXPECTED.tsv] ===
  STDLIB: 108/108 GREEN
  all 24 stages GREEN, GATE EXIT=0
```

| check | value |
|---|---|
| fixed point (3 generations, seeded from the 0.0.238 golden) | `6f83fe08a7f8819a725fe50c81680ef1` x3, **distinct = 1** |
| committed binary == that fixed point | yes |
| `verify-release.sh` | **13 passed, 1 failed** — the one FAIL is `NEXT is not VER plus one patch`, an artifact of running it in the POST-bump state (root VERSION is already 0.0.239). Every substantive check passed: source rebuilds bit-for-bit, committed binary IS the seed-chain fixed point, self-host fixed point gen0==gen1==gen2, gate 225/225. |

Note the fixpoint is reached at **generation 1**, unlike 0.0.238: this version adds a
builtin but changes no existing construct's codegen, so even the seed-built compiler
already emits identical code for the compiler's own source.

## 6. Files

| path | change |
|---|---|
| `compiler/0.0.239/src/x86/emitter.quanta` | `dq32lo`/`dq32hi`/`dq4lo`/`dq4hi` builtins |
| `compiler/0.0.239/src/x86/features.quanta` | the four names in `is_prim_intrin` |
| `lib/std/gguf.quanta` | `dequant_q4k` calls `dq32lo`/`dq32hi` |
| `tests/lfm2_generate.quanta`, `tests/run_lfm2_generate.sh` | the tracked generation driver (secondary deliverable) |
| `tests/lfm2_gen.conf`, `tests/lfm2_prompt.txt` | its config + prompt |
| `VERSION`, `compiler/0.0.239/**` | the version bump |

## 7. Not verified / open / stated plainly

1. **The CPU% figures are load-polluted.** A second unit was running throughout (load
   ~10 on 20 cores). Measured process CPU%: before 99 / 187 / 337 / 539 / 877 % at
   1/2/4/8/20 workers; after 91 / 187 / 334 / 533 / 818 %. The falling utilisation is
   best explained by ~8 cores actually being available, and it is confirmed
   independently: a pure matvec workload (no forward, no tokenizer) gets **5.61 cores of
   work at 8 threads and 7.94 at 20**, with total user time inflating 1.75x under
   contention (32.2 s -> 56.3 s for the same 60 matvecs). Threads are not idle at a
   barrier and not blocked on a syscall — System time stays under 1 s. **Not re-measured
   on an idle box.**
2. **The generation driver runs end to end but produces no text yet.** It loads the model
   (4.1 s), applies `lfm2_chat.chat_build`, tokenizes (34 ids), prefills, samples and
   detokenizes — exit **0** — but the first sampled token is `<|im_end|>` (EOS), so
   `new_tokens=0`. The blocker is RECORDED, not worked around: it is a model/prompt
   behaviour, not a driver crash. Prefill costs **7.44 s/prompt-token at 8 workers**
   (34 tokens = 253 s) because prefill is one forward per prompt token, no batching.
3. **A 300-token generation was NOT run.** At the measured decode rate it is 300 x 10.1 s
   = **~50 min at 8 workers** and 300 x 7.9 s = **~40 min at 20 workers**, so the
   arithmetic is from measured per-token times, not from an end-to-end run. This is the
   number that decides whether the SI loop can use the native path: **at 0.126 tok/s and
   ~30% of a token still in an untouched Q6_K projection, it cannot.**
4. **The remaining gap to llama-server is ~65x.** llama-server does 8.24 tok/s decode on
   this CPU with a LARGER 7.5B model; this engine now does 0.126 tok/s at 20 workers on
   the 2.6B. Before this version it was 0.081 tok/s, so this closes ~1.6x of a ~100x
   gap.
5. **Q6_K dequant is untouched** (§4c) — the largest remaining single item.
6. **The unbracketed `mm_matvec_par` leak and the per-call `fc_attn_workers` leak**
   recorded in `docs/research/threaded-forward-defect.md` §8 are unchanged; the driver
   brackets the loop (`mm_pool_begin`/`mm_pool_end`) so it does not hit them.
7. `compiler/0.0.239/lib/**` is a stale snapshot copy (it already differed from the
   repo `lib/std` at 0.0.238 release time, e.g. `gguf.quanta` md5 `a8aa6e70` vs
   `1866da96`). Imports resolve to the REPO `lib/std`, which is what the build and the
   gate use. Left as found rather than partially synced.
