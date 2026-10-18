# 0.0.249 — F1: `adistinct` stops evicting live operands (A31)

Phase 2, lever one. `VERSION` 0.0.248 -> **0.0.249**. Source changed:
`src/x86/emitter.quanta`, `src/x86/codegen.quanta`.

```
0.0.248 golden  md5 b9e36271373d108eb52989f08d841365   (frozen baseline, untouched)
0.0.249 g1      md5 e2769a4374b472abf7d1f14b2ba98084   (0.0.248 golden building the edited source)
0.0.249 g2      md5 14fd1086617bb1b37a502a33c624c802   (g1 building the edited source = COMMITTED GOLDEN)
0.0.249 g3      md5 14fd1086617bb1b37a502a33c624c802
0.0.249 g4      md5 14fd1086617bb1b37a502a33c624c802   (distinct(g2,g3,g4) == 1)
```

Instrument of record: `scripts/bench_instr.sh` (load-independent emitted-byte
counts). Every pre/post pair below is MEASURED in this session with
`./compiler/0.0.248/bin/x86/qc` vs `./compiler/0.0.249/bin/x86/qc`.

---

## 1. The lever

`adistinct(res, a1, a2)` began with a loop that un-mapped every allocation entry
bound to `a1` or `a2`, storing each operand's **live** value to its home slot, and
then recovered `res` by reloading its (just-overwritten) home. Both operands of
the operation about to be emitted were therefore spilled on **every binary op**,
their next use reloaded what had just been stored, and the register map was
emptied on every op — which is why residency never accumulated in a 13-register
pool.

0.0.249 deletes that loop. What remains:

- `apick_free(a1,a2)` — a register holding no live vreg and neither operand (this
  scan is what actually guarantees the non-aliasing property; it excluded `a1/a2`
  before too, so nothing is weakened).
- `aevict_nop(a1,a2)` — when the pool is full, evict a mapped vreg that is
  **neither** operand (spilling it, because it *is* being un-mapped). The
  fallback pops from the end, **bounded by `allocfc>0`** — the old degenerate
  loop read `alloc-16` when it reached zero.
- `aremap(res, old, new)` — re-point an existing mapping instead of appending a
  duplicate.
- When `res` is *already* mapped to `a1` or `a2` (`x = x + y` in place, the case
  that becomes common now that residency accumulates), the value is moved out of
  that register with a register-to-register `rr(p, f)`. It must not come from the
  frame: under the 0.0.245 invariant a **mapped** vreg's home may be stale.

### 1b. Two latent defects F1 exposed, fixed in the same version

Removing the eviction removed an accidental side effect that two sites had been
relying on. Both are real miscompiles in the *previous* compiler that were
unreachable only because the old `adistinct` emptied the map on every op.

**D-a — `width_mask` treated RAX as "no register".** The guard was
`... && rd != 0`, i.e. `rd == 0` read as "no result register was supplied". 0 is
RAX. It never fired because RAX was always occupied when `adistinct` ran and so
was never returned. With residency, `adistinct` returns RAX and the truncation
was **silently dropped**:

```
pre-F1 : r15 = g + h ... and $0xff,%r15      <-- the u8 wrap, present
post-F1: rax = g + h ... (no mask emitted)    <-- wrap lost
```

MEASURED: `test_suites/codes/mixed_width_mask_test.quanta` exited **103** instead
of 7 (`let i = g + h`, u8 255+1 no longer wrapped to 0). All three call sites pass
the live register from `adistinct`, so the correct guard is just "a width type is
in play"; there is no sentinel to preserve.

**D-b — `f2i` left live vregs mapped across registers it destroys.** The builtin
loads the operand with `aphys`, stages it into `xmm0`, and `cvttsd2si rax` writes
RAX. It used `adistinct(res, rs, -1)`, whose *eviction* of the operand was what
un-mapped any vreg sitting in the operand's register and in RAX. F1 removes that,
so:

- any vreg still mapped to RAX/RCX/RDX from earlier in the block was clobbered
  while its mapping (and therefore its home write-back) still named that register;
- and if the operand itself was mapped to RAX, the CVT overwrote it.

MEASURED: the argmax loop of `test_suites/codes/sampling_test.quanta` stopped
updating its running maximum (`v` mapped to RAX, `cvttsd2si` overwrote RAX, the
next eviction stored the truncated integer into `v`'s home). Fixed with an
explicit `flush_clob(0,1,2)` (the same tool the SHL/SHR and div paths use for
fixed-register clobbers), an explicit operand un-map (`aunmap(srcv)`) after its
last use, and `aunmap(res)` before the RAX result binding. `aunmap(vr)` is new:
drop a mapping, storing first, so nothing is lost. Also fixed on the same line:
the `movq xmm0, rd` staging emitted a fixed REX byte, so it encoded the wrong
register for rd >= 8 (r8-r15) — now REX.B is set from `rd`.

MEASURED with the two fixes reverted one at a time: the mixture fails; with both,
`mixed_width_mask_test` = 7, `sampling_test` = 0, `std_vfloat_result_test` = 0,
and the four bisection probes (a=1, b=50, c=3, d=1) are correct.

**These are correctness fixes, not part of the optimisation.** They are what F1's
removal of the eviction *requires*; the campaign's rule is fix-forward, not
work-around, so the two sites were made explicit rather than re-adding an eviction
that only incidentally repaired them.

### 1c. Stale-home audit (why leaving operands mapped is safe)

Every direct `spill_home` READER was re-checked against the 0.0.249 tree.

- `codegen.quanta`: 20 direct reads. 16 sit inside a `flush_all()` scope (the
  memory-builtin and call-argument paths, and `IR_CALL` calls `flush_all()` as its
  first statement); 2 are self-protected by an explicit write-then-read. 0 read a
  mapped vreg's home unguarded.
- `emitter.quanta`: every reader is either inside `aphys`/`aphys_x`/`loadhome`/
  `adistinct`'s home path — all of which are taken only when `afind(vr) < 0`, i.e.
  the vreg is un-mapped and its home *is* current by the 0.0.245 invariant — or
  behind a `flush_all()` at the head of its builtin branch. Measured mechanically:
  for all 75 direct read sites, the nearest preceding `flush_all()` lies in the
  same branch; the two largest gaps (`emit_bltn2:2768`, `emit_bltn2:2980`,
  `thread_create`) were read by hand and contain only raw `eb()`/`sysc()` emission
  between the flush and the read, no `aset`/`sdef`. `ft_arg` (`:5058`) is guarded
  by construction — all 9 of its call sites are literally `flush_all(); ft_arg(...)`.

**0 hazards.** The gate confirms it (below): the two miscompiles that did appear
came from the two fixed-register sites, not from a stale home.

## 2. Measured effect — the instrument of record

38 rows; all `q_*` columns; `q_loop` = hot-loop body, `lst`/`lld` = frame-relative
stores/loads inside it.

**30 of 38 rows changed codegen** (8 unchanged: the loop-free or call-dominated
rows). Aggregate:

| metric | 0.0.248 | 0.0.249 | delta |
|---|---|---|---|
| `q_instr` (whole `main`) | 9031 | 8825 | **-2.3 %** |
| `q_loop` (hot-loop body) | 2257 | 2101 | **-6.9 %** |
| `q_mem` (frame ops in `main`) | 2856 | 2645 | **-7.4 %** |
| `q_hst` (home stores, `main`) | 1963 | 1859 | -5.3 % |
| `q_hld` (home loads, `main`) | 892 | 785 | **-12.0 %** |
| `q_lst` (home stores in the loop) | 712 | 633 | **-11.1 %** |
| `q_lld` (home loads in the loop) | 352 | 273 | **-22.4 %** |

| case | loop | loop st | loop ld | case | loop | loop st | loop ld |
|---|---|---|---|---|---|---|---|
| regpressure | 310 -> **268** | 102 -> **81** | 33 -> **12** | params8 | 81 -> **77** | 29 -> 27 | 15 -> 13 |
| match | 148 -> **146** | 34 -> 33 | 15 -> 14 | fnptr_indirect | 76 -> **70** | 25 -> 22 | 16 -> 13 |
| float | 127 -> **125** | 44 -> 43 | 30 -> 29 | mutual_recursion | 73 -> **67** | 25 -> 22 | 12 -> 9 |
| fileio | 101 -> **95** | 34 -> 31 | 21 -> 18 | heavy_int _int2 | 65 -> **59** | 19 -> 16 | 9 -> 6 |
| arith | 98 -> **92** | 27 -> 23 | 13 -> 9 | heavy_float _float2 | 65 -> **63** | 22 -> 21 | 13 -> 12 |
| div_const | 84 -> **76** | 30 -> 26 | 14 -> 10 | q4k q4k_heavy | 62 -> **60** | 20 -> 19 | 10 -> 9 |

Loop-home share median **49.2 % -> 45.6 %**; mean loop body 62.7 -> 58.4.

**The audit's PROJECTED -33 % is REFUTED by this measurement.** The projection
assumed the entire store/load traffic of a hot loop came from `adistinct`'s
operand eviction. It did not: the eviction loop could only store the operands that
were actually *mapped* when a binary op ran, and at block boundaries everything is
already flushed by `flush_all()`. What remains in the loops is (a) the
block-boundary `flush_all()` itself — measured here as the dominant term — (b)
`sdef`/`sdefr` home stores for results that are un-mapped, (c) the `flush_clob`
spills of the div/shift paths (which spill any vreg parked in rax/rcx/rdx, not
just their operands), and (d) the D5 comparison round trip. A31 was real and is
measured at **-6.9 % of the loop body**; it was not half the loop. The
`float`/`heavy_float` rows barely move (-2 instructions) because FP ops do not go
through `adistinct`'s operand path at all — they use `fopld_rr`/`aphys`. Those two
rows need F4 (xmm-resident FP), exactly as the audit sequenced.

## 3. Red-first row, registered in this commit

The lever has no functional symptom — it deletes dead stores — so no exit-code row
can see it. Following the precedent of stage 1.6d (F16C independence, an opcode
scan of emitted bytes), a new **marshalling guard** stage was added to
`test_suites/scripts/run_tests.sh` plus one new gate row:

- `test_suites/codes/arith_marshalling_probe.quanta` — `a=i+1; b=a*3; c=b-i;
  s=s+a+b+c` in a loop, so **both** operands of every binary op are registered.
  No division/shift (their `flush_clob` stores are not A31 and would blur the
  metric) and no printer (print pulls the inlined itoa loop into `main`, and the
  guard picks the largest-span backward branch). Hand-derived golden
  `6i+7` summed over `i<100` = **30400**, asserted by exit code; the row is in
  `EXPECTED.tsv` (238 -> 239 rows).
- The stage compiles it with `--emit-obj` and counts frame-relative stores/loads in
  the hot loop, using the same AWK metric definition as `bench_instr.sh`. Counts
  are emitted bytes: exact, no tolerance, no wall clock.

**Proven to fail for the reason it exists:**

| compiler | loop | loop stores | loop loads | verdict |
|---|---|---|---|---|
| 0.0.248 (pre-F1) | 79 | 26 | 10 | **FAIL** (stores 26 > 23) |
| 0.0.249 (F1) | 67 | 20 | 4 | PASS |

Thresholds 73 / 23 / 7 sit between the two on all three counts.

## 4. Verification

- `bash scripts/bench.sh` with the 0.0.249 golden: **`# OK: every row compiled and
  every C twin kept its loop.`**, 0 `MISMATCH`, 0 compile failures — all 38
  benchmark outputs still equal their C twins.
- `scripts/selfhost_consistency.sh` on the 0.0.248 tree (pre-change): **SELFHOST 7/7**.
- Fixpoint chain from the frozen 0.0.248 golden: `b9e36271 -> e2769a43 -> 14fd1086
  -> 14fd1086 -> 14fd1086`; `distinct(g2,g3,g4) == 1`; committed golden = g2.
- Drift check against the new seed (`0.0.249 golden` building `0.0.249/src`):
  **IDENTICAL**.
- Full gate on the committed golden: see `compiler/0.0.249/WIP.md` for the
  stage-by-stage result.
- Byte-identity of every gate row between the two compilers: see §5.

## 5. Byte-identity — which rows the lever intentionally changes

Every one of the 239 `EXPECTED.tsv` rows was compiled with **both** compilers
(`-O`, byte compare of the emitted executables):

| | count |
|---|---|
| **byte-identical** | **33 / 239** |
| differing | **206 / 239** |
| compile-fail | 0 |

This is a much wider footprint than the 0.0.248 unit's own result (232/238 with
only the 6 f16/f32 rows differing), and the difference is expected rather than
alarming: that lever was a flag/type change, while F1 changes the **operand and
allocation path of every binary op**. Two mechanisms make a row differ:

1. `adistinct` no longer un-maps the operands, so every binary op's marshalling
   (the store/load pair and the chosen registers) changes wherever an operand was
   registered; and
2. residency now accumulates, so `afree()`/`aphys()` hand out **different
   registers** for the rest of the function — a renaming with no semantic content,
   which is why rows containing no arithmetic operator at all still differ.

Instruction-*shape* (the opcode sequence) was compared too, and the two sets are
identical: all 206 byte-differing rows also have a different opcode sequence,
because the marshalling being removed is itself a sequence of `mov` opcodes. So
opcode-sequence identity is not a finer discriminator here; it measures the same
thing.

The equivalence claim therefore does not rest on byte-identity for this version —
it rests on the four behavioural oracles, all measured in this run: the gate
**239/239** exit-code match, the 38 benchmark outputs matching their C twins
(`bench.sh` OK, 0 MISMATCH), `differential` GREEN (optimizer `-O`==no-`-O` and
vs-seed), and the self-host fixpoint `g2 == g3 == g4`.

## 6. What this version does NOT fix

Everything else in the campaign is still open and now measured against a fair
baseline: **F2** dead-store elimination (the provably-dead 30-67 % of the
remaining stores), **F3** the comparison round trip (8-instruction loop test),
**F4** xmm-resident FP (gated on the A32 frame/offset fix — `fspill_home` still
writes ~8 KB below `%rbp` while the frame reserves 1120 bytes), **F5** opt-in FMA,
**F6** constant multiply as `lea`/`shl`/`add` (`i*8` is still `imul $0x8`), **F7**
LICM, **F8** the constant shift-range check. A33 (`loop_depth`, 21 % of
`regpressure`'s loop) remains a semantics decision and needs the language
capability first.

The measured rank has changed: the **block-boundary `flush_all()`** is now the
largest remaining in-loop term, ahead of A31's residue — which is exactly what
`docs/plans/performance.md` predicted as "the next lever after 0.0.245:
cross-block liveness".
