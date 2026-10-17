# JIT fused Q4_K dot — corrected cadence, open crash

Status: emitter cadence corrected and committed; the emitted kernel still
SEGFAULTS when executed. Not usable yet. This file records exactly where it
stands so the next session does not re-derive it.

## Fixed (commit 73466aed and after)

1. **DMD overrun.** `jit_f_dmd_alloc` reserves 128 bytes per super-block
   (8 (scale,min) pairs). The old kernel looped 32 groups advancing rdx by
   32 bytes each = 1024 bytes per super-block — reading 8x past the row.
2. **Pair ownership.** `j_f_group` advanced rdx itself, but per
   `lib/std/matmul_q4k.quanta q4k_block_dot` ONE pair covers 32 quant bytes,
   so 8 consecutive 4-byte steps share it. rdx is now owned by the chunk.
3. **Low/high factor split.** The low nibbles and high nibbles need DIFFERENT
   (scale,min) pairs; y6/y7 are now broadcast separately per half
   (`[rdx],[rdx+8]` for low, `[rdx+16],[rdx+24]` for high).
4. **Branch reach.** The corrected body is ~4 KB, far outside the ±127-byte
   rel8 window, so the backward branch is now `jne rel32` (0F 85) with a new
   `j_patch32` helper.
5. **Addressing model.** Q4_K maps low nibbles to weights [i] and high nibbles
   to weights [32+i], which ONE linear x cursor cannot express. The body is now
   8 low steps + `sub r9,32` rewind + 8 high steps per chunk (4 chunks), so x
   advances 64 doubles per chunk = 256 per super-block.

## Open — the crash

`tests/jit_fused_exact_test.quanta` emits the kernel successfully
(`kernel emitted at <addr>`), then SEGFAULTS on the first call.

Ruled out:
- buffers are large enough for nsuper=1 (raw 160 B > 128 used, dmd 128 == 128
  used, x 2112 B > 2048 used)
- prologue instructions are each individually verified (`mov r9,[rdi]`,
  `mov r10,[rdi+8]`, `mov rdx,[rdi+16]`, `mov rcx,[rdi+24]`, xor ymm0)
- the emit region is not exhausted (no overflow message at 64 KiB)
- JIT execution itself works on this box: `tests/lfm2_jit_probe.quanta` Q1-Q3
  PASS via the same `closure_call` route

NOTE: a `nsuper=0` probe CRASHES BY DESIGN and is not a kernel defect — the
loop is a do-while (`sub rcx,1; jne`), so 0 underflows to -1 and spins.

Next diagnostic (cheapest first):
1. Disassemble the emitted bytes (dump the 64 KiB region) and compare the
   prologue/epilogue instruction-by-instruction against intent.
2. Single-step under gdb at the entry address; the faulting instruction will
   name the bad register or the address that is out of range.
3. Verify at nsuper=1 with x/raw/dmd allocated as ONE mmap'd block, so an
   overrun is a contiguous read rather than an unmapped fault.

## Second pass — the crash is FIXED, the arithmetic is not

### Root cause of the segfault: `jbytes(n, hex)` silently truncates

`lib/std/jit_x86.quanta jbytes(n, hexstr)` writes exactly the FIRST n bytes of the
hex string. The loop counter decrement was written as

    jbytes(3, "4883e901")     // sub rcx,1 -- a FOUR-byte instruction

so the trailing `01` was DROPPED and the kernel executed `sub rcx,15` followed by
garbage (`test %edx,%edi`, `out %al,(%dx)`) and a mis-aimed branch. Found by
dumping the emitted bytes, converting to a binary, and reading the disassembly --
the source hex strings each looked correct in isolation; only the SEQUENCE showed
the fault.

An audit of every `jbytes` call in both JIT modules found **9 mismatches**:
this one plus 8 in `j_push`/`j_pop` (REX-prefixed push/pop declared as 1 byte when
they are 2). All 9 are now fixed and a re-audit reports 0 remaining.

### Other real bugs fixed

- 8x DMD overrun (32 groups of 8 vs 8 pairs of 128 bytes per row)
- pair ownership: rdx is advanced by the chunk, not by each 4-byte group
- per-half factor broadcast: low nibbles and high nibbles need different pairs
- backward branch widened to `jne rel32` (the corrected body is ~4.4 KB)
- **super-block header skip**: the kernel started reading quant bytes at `W+0`,
  i.e. it treated the f16 d, f16 dmin and 12 scale bytes as quant data.
  `q4k_block_dot` uses `q = raw + bo + 16`. Fixed in the prologue and per
  iteration (128 quant bytes + 16 header = the 144-byte stride).
- addressing model: 8 low steps + `sub r9,32` rewind + 8 high steps per chunk,
  because Q4_K maps low nibbles to weights [i] and high nibbles to [32+i]

### Test infrastructure that now exists

- `tests/jit_oracle_test.quanta` — degenerate inputs, hand-computable answer
- `tests/jit_diag_test.quanta` — (A) x=0, (B) d=0, (C) constant, (D) varied x,
  (E) varied bytes, (F) x=i, (G) both varied
- `tests/jit_dump_kernel.quanta` — prints the emitted bytes so objdump can read
  them; this is what found the truncation bug
- `tests/jit_plumb_test.quanta` — pointer plumbing probe (WIP, currently faults)
- `tests/jit_argconv_test.quanta` — CONFIRMED: `closure_call` delivers a0 in rdi

The scalar reference is now independently verified against theory: case (C)
computes 1248.0 and case (F) computes 258960.0, both exactly as hand-derived.

### OPEN: the kernel returns ~1e12 where the scalar returns 1248

- with d = 0 the kernel returns ~0 (correct)
- with real factors it returns huge values in EVERY case, (C) included
- the DMD table contents are verified correct by read-back
  (1.0/2.5, 2.0/3.0, 3.0/3.5, 4.0/4.0, 9/0, 10/0, 11/0, 12/0)
- so the kernel is applying factors that are not the table's

Next: fix the plumbing probe (it currently faults on its own emitted bytes) to
print what the kernel actually loads from each argument slot. That is the one
measurement that separates "wrong pointer" from "wrong offset".

### Harness false positive worth remembering

The first version of `tests/jit_diag_test.quanta` wrote the f16 scale's low byte
and left the high byte 0, silently making d = 0.0. Every case then compared two
near-zero numbers and "matched". A test that agrees because both sides are zero
proves nothing.

## Third pass — the bug is now PINNED to one instruction class

### Everything upstream is verified correct

- **Pointer plumbing** (`tests/jit_plumb_test.quanta`, fixed): the emitted kernel
  loads exactly the addresses we set up -- slot 0 -> raw, 8 -> x, 16 -> dmd,
  24 -> 1. All four match.
- **DMD contents**: read back as 1.0/2.5, 2.0/3.0, 3.0/3.5, 4.0/4.0, 9/0, 10/0,
  11/0, 12/0 -- correct.
- **x is used as f64**: with constant x, the kernel scales EXACTLY linearly
  (x=1.0 -> 4.4624e11, x=2.0 -> 8.9248e11, x=4.0 -> 1.7850e12; ratios 2.0000 and
  2.0000), matching the scalar's ratios. So the data is not being mis-typed in
  the multiply itself.
- **Disassembly** of the emitted bytes reads correctly instruction by instruction.

### The smoking gun: a single step returns a double's HIGH DWORD as an integer

`tests/jit_onestep_test.quanta` emits ONE fused step (no loop, no accumulation)
with d=1.0, dmin=0.5, scale[0]=1, min[0]=5, all quant bytes 0x11, all x = 1.0.

    correct answer:  weight = 1.0*1 - 0.5*5 = -1.5, four lanes -> -6.0
    measured answer: 1072693240.0

`1072693248` is DECIMAL FOR `0x3FF00000`, which is the **high 32-bit half of the
double 1.0** (`0x3FF0000000000000`). The measured value is that integer minus 8 --
i.e. the correctly-computed -6 term (rounded) sitting on top of an int32
reinterpretation of an x value.

This also explains the full kernel's error precisely: its result is the correct
value multiplied by ~(1072693248/3) for x=1.0, and the multiplier tracks the same
int32-of-a-double quantity.

### Conclusion for the next attempt

The fault is in ONE of the conversions in the chain -- `vpmovzxbd`,
`vpslld/vpsrld $28`, `vcvtdq2pd`, or `vpsrldq`/`vinsertf128` -- where a *double*
is being fed through the int->double path (or the reverse). The byte encodings
were each checked by hand against the Intel manual and by objdump and appeared
correct, so the next step is to single-step the emitted kernel under gdb at the
entry address and watch ymm1 after each instruction. That will name the exact
instruction rather than inferring it.

### Verification status

`tests/jit_plumb_test.quanta` and `tests/jit_onestep_test.quanta` are committed.
The gate passes with all `lib/std` changes in place (229/229 native, 24/24
stages, GATE_EXIT=0).

## RESOLVED — the fused kernel is bit-exact and 14.5x faster than the scalar path

### The actual root cause

`vcvtdq2pd %xmm1,%ymm1` writes **ymm1, whose low 128 bits ARE xmm1**. So it
destroys the very dwords it is converting. The old order then ran
`vpsrldq $8,%xmm1,%xmm2` to fetch dwords 2,3 -- but by then xmm1 held converted
DOUBLES, so psrldq sliced the high half of a double (0x3FF00000 out of 1.0) and
`vcvtdq2pd` re-converted it as int32, giving exactly 1072693248.

That single misordering explains every observation:
- a one-step kernel returned 1072693240.0 instead of -6.0 (= 0x3FF00000 - 8)
- the full kernel returned a constant ~3.575e8x the correct value
- the result scaled perfectly linearly in x (the corrupted term is still
  multiplied by x downstream)
- with d = 0 the result was 0 (the factor multiply zeroes it regardless)

Fix: capture dwords 2,3 into xmm2 BEFORE the first conversion, in both `j_f_low`
and `j_f_high`.

### Verification (all bit-exact, no tolerance)

- one-step kernel: **-6.0** exactly (hand-derived)
- `tests/jit_diag_test.quanta`: (D) varied x 4033.25, (E) varied bytes 11776,
  (F) x=i **258960** (hand-derived), (G) both varied 37796.2 -- jit == scalar in
  every case
- `tests/jit_fused_exact_test.quanta`: BIT-EXACT on varied data
- `tests/jit_perf_test.quanta` at NSUPER=8: bit-exact, and **14.47x faster** than
  the scalar path over 409,600 elements

### Caveats before this becomes a tok/s number

- The speedup is a MICRObenchmark of the dot kernel. It is not an end-to-end
  tok/s figure and must not be reported as one.
- `clock()`'s absolute unit is unverified, so only the RATIO is trustworthy.
- The kernel is not yet wired into `lfm2_forward`; the integration and the
  128/512/1024-token e2e table are still to do, along with the dispatch ceiling
  (811% CPU vs the 1,600-1,900% target) that the earlier campaign named as the
  other joint requirement for 15 tok/s.
- Load context: governor powersave, Hermes holding ~750% CPU.

## Measured against the REAL production path (not the naive scalar)

The earlier 14.47x was against `q4k_block_dot`, a naive scalar reference. The
comparison that decides integration is against `q4k_matvec_real` -- the matvec
that `lfm2_forward` actually reaches through `mm_matvec`, which dequantizes the
row and then dots it.

`tests/jit_vs_prod_test.quanta`, 2048 weights, 200 reps, same bytes and same x:

    jit  bits = 4700186342854754304
    prod bits = 4700186342854754304      <- BIT-EQUAL to the production matvec
    production (dequant + dot): 5,200,572
    fused jit                 :   595,426
    ratio                     : 8.73x

So the fused kernel is **bit-identical to the production matvec and 8.73x faster**
on the same work. (Against the naive scalar reference it is 14.47x; the honest
number to quote for integration purposes is 8.73x.)

### Still true, still caveats

- This is a MICRObenchmark of the dot, not an end-to-end tok/s figure.
- `clock()`'s absolute unit is unverified; only the ratios are trustworthy.
- The kernel is NOT yet wired into `lfm2_forward`; integration is the next step.
- The dispatch ceiling (811% CPU vs the 1,600-1,900% target) remains open, and the
  earlier campaign named it as jointly required with fusion for 15 tok/s.
- llama.cpp reference on the same model and CPU: 17.32 tok/s. Native loader: 0.281.

## CORRECTION: the 8.73x is one sample of a load-sensitive ratio

Two runs of the SAME test (`tests/jit_vs_prod_test.quanta`, 2048 weights, 200 reps,
bit-equality asserted in both) produced materially different numbers:

    run 1: production 14,040,377   fused 1,141,098   ratio 12.30x
    run 2: production  5,200,572   fused   595,426   ratio  8.73x

The production figure itself moved 2.7x between runs. This box carries `Hermes` at
~750% CPU permanently and load has been 9.4-10, so BOTH the absolute times and the
ratio are load-sensitive. The honest statement is:

  **the fused kernel is roughly 9-12x faster than the production matvec on this
  box, measured at 12.30x and 8.73x in two runs, with bit-equality to
  `q4k_matvec_real` in both.**

Quoting a single figure (8.73x or 14.47x) as if it were a stable constant
overstates the precision. The direction and magnitude of the win are robust; the
second decimal place is not. Any e2e tok/s number must carry the same caveat until
it is taken on a quiet box.

## INTEGRATION ATTEMPT — the numbers above compare against the WRONG path

### The premise in the sections above is wrong (source is the authority)

`mm_matvec` does **not** call `q4k_matvec_real`. Read `lib/std/lfm2_mm.quanta`:
the row loop calls `mm_load_row` / `mm_deq_row_raw` (which dispatch to
`read_block_f64` -> `dq32lo`/`dq32hi`) and then `mm_dot4_s`. `q4k_matvec_real`
lives in `lib/std/matmul_q4k.quanta` and is the **scalar** `q4k_block_dot` path.
So "8.73x / 12.30x faster than the production matvec" is a comparison against a
path the loader does not execute.

Measured against the shape it DOES execute — 64 real Q4_K rows of the model's
FFN-gate tensor (idx 4, dtype 12, cols 2048, 1152-byte rows, nsuper 8), in
`tests/lfm2_jit_mm_test.quanta`:

    BITIDENT fused_vs_mm_deq+dot4: mismatches=0 / 64

Bit-identical to `mm_deq_row_raw + mm_dot4_s` too, and for a real reason rather
than luck: the per-element `w = q*(d*Kn) - (dmin*Mn)` is the same expression and
the 4-lane summation order matches (`(l0+l1)+(l2+l3)` both sides). So the fused
kernel IS safe to substitute for the production dot.

### The DMD table build is 70-84% of the fused cost — the 8.73x does not survive contact

`tests/jit_vs_prod_test.quanta` fills the DMD factor table ONCE, **outside** its
timing loop, so its ratio EXCLUDES the table build. In the real path the table
must be rebuilt for every row (it is derived from that row's raw bytes). Timed
separately and interleaved, 64 real rows, best of 4 (`tests/lfm2_jit_mm_test.quanta`):

| run | A prod (deq+dot4) | B dmd build only | C kernel only | D = build+kernel | A/D | A/C | B/D |
|---|---|---|---|---|---|---|---|
| quiet-ish | 1,261,621 | 338,336 | 115,982 | 450,664 | 2.79x | 10.87x | 75% |
| mid load  | 1,121,472 | 294,582 | 99,904 | 417,543 | 2.68x | 11.22x | 70% |
| loaded    | 772,876 | 204,989 | 58,159 | 258,586 | 2.98x | 13.28x | 79% |
| loaded    | 906,137 | 245,376 | 66,281 | 303,449 | 2.98x | 13.67x | 80% |
| loaded    | 1,135,857 | 601,430 | 131,259 | 714,011 | 1.59x | 8.65x | 84% |

Read it as: **the kernel alone is 8.7-13.7x, but the per-row DMD build is bigger
than the kernel it feeds, so the integrated win on the Q4_K dot is only ~2.7x
(1.6-3.0x across load states).** This is the number that belongs in any e2e
projection, and it is the reason a per-tensor (cached) DMD table is the natural
next lever rather than a kernel change. (A `level 2` cached-DMD design was
implemented and measured-compilable but could not be exercised — see below.)

### Blocked: `closure_call` cannot be reached from an imported module

Wiring the kernel into `lfm2_forward`'s dot path requires the dispatch to happen
inside a library module (`lfm2_mm` / `lfm2_forward`), and that is exactly what
qc 0.0.245 miscompiles. Minimal 2-module reproducer (imports `std/jit_x86` and
`std/jit_x86_fused` only), identical tuple, argument area and bytes:

    let va = closure_call(tbl, asz, 0)   // inline in main
                                         //   -> 4700186342854754304   OK
    let vc = jit_f_apply(asz)            // helper in the imported module
                                         //   -> SIGSEGV, rc=139

Every formulation of the imported-module call faulted: tuple as a module global,
tuple as a parameter, tuple built locally, with and without surrounding
`mem_store`, one caller or five, and from `lib/std/lfm2_mm.quanta`. In **larger**
translation units the same construct traps the **compiler** instead (SIGILL,
rc=132) — `qc -O tests/lfm2_generate.quanta` dies, where pristine `lfm2_mm`
compiles. Bisection of the trap: it needs `mem_store` through a parameter AND
`closure_call` in one body; a local alias makes it compile but the emitted code
still faults; stores through a module global compile (`probe B`). Every splt
shape was tried (stores/call in separate functions, small module, `jit_x86_fused`
instead of `lfm2_mm`) — all fault or trap.

Also worth recording: `mm_matvec`'s dispatch site is a *matrix of modules* (the
decoder bench, `lfm2_forward`, `lfm2_mm`, `jit_x86_fused`), so the workaround
of "dispatch from the top-level module" is not available — the per-row dot is
four frames below `main`.

**Status: the integration is blocked on a compiler fix outside this unit's
scope (`compiler/**`).** A one-line `call r11` emitter bug or a missing
`r11` save in the CLOSURE_CALL lowering would be the thing to look at; the
reproducer above is 12 lines and deterministic.

### What was shipped, and what was deliberately NOT shipped

- `lib/std/lfm2_mm.quanta` — **left PRISTINE** (`git checkout`). The fused
  dispatch was written, compiled and exercised, but every reachable shape faults,
  so shipping it would ship a path that crashes. The flag-guarded branches were
  reverted rather than left dead-and-crashing.
- `lib/std/jit_x86_fused.quanta` — adds `jit_f_setup()` / `jit_f_ready()` and
  `jit_f_apply(as)`, the high-level entry the wiring needs, marked
  **BLOCKED** in place. They compile in every TU that imports them (verified:
  `jit_vs_prod_test`, `jit_diag_test`, `stdlib_lfm2_mm_test`) and are never
  called, so they cannot change behaviour. They exist so the eventual fix has
  one obvious place to land.
- `tests/lfm2_jit_mm_test.quanta` — NEW. Bit-identity against the real mm shape
  (section 1) and the DMD/kernel cost split (section 2), both on real Q4_K rows.
  Section 3 records that the integration measurement is blocked.
- `tests/lfm2_jit_cc_probe.quanta` — NEW. Runs the WORKING half of the
  `closure_call` reproducer (inline dispatch, records the expected bits
  4700186342854754304) and carries the exact broken half in its header, because a
  SIGSEGV cannot be caught in-process.

## END-TO-END — the flag-OFF baseline, 128/512/1024 in one process

`tests/lfm2_decode_bench.quanta` run through `tests/run_lfm2_decode_bench.sh`
(20 workers, `mm_set_workers_uncapped`, mmap path, norm cache on, `ignore_eos=1`),
conf `20 128 512 1024 1 1 1`, temp 0, one process, all three lengths. Environment:
governor `powersave`; load 12.4 at start rising to 20-25 during the run; `Hermes`
holds ~756% CPU permanently and peer `python`/`python3` processes added ~190%
during the run, so these numbers are LOAD-INFLATED — the same build read 3.49-3.69
s/token at load 8-12 in the earlier campaign (section 3b of
`docs/research/decode-fused-dot.md`) against 3.61/3.82/4.15 s/token here.

Flag ON was NOT measurable: the fused dispatch cannot compile or run from
`lfm2_mm` (see the blocker section above). Every row below is therefore the
UNCHANGED baseline, which is also the control the ON side would have been
compared against.

| len | gen_ms | ms/tok avg* | ms/tok med | ms/tok max | tok/s | CPU% | anon MB/tok* | VmPeak MB/tok* | first argmax |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 128 | 461,731 | 3607.3 | 3648 | 3901 | 0.277 | ~774 | 1.03 | 4.34 | 597 |
| 512 | 1,954,669 | 3817.7 | 3816 | 4378 | 0.261 | ~774 | 1.09 | 4.37 | 597 |
| 1024 | 4,247,062 | 4147.5 | 4131 | 5257 | 0.241 | ~774 | 0.63 | 4.37 | 597 |

- `*` = DERIVED (arithmetic on the measured deltas); everything else is measured
  and printed by the bench. `ms/tok avg` = gen_ms / gen_tokens.
- `tok_ms_min` is printed as **2 ms** in every run and is an artifact, not a fast
  token: the final loop iteration has no forward pass (same convention as
  `tests/lfm2_generate.quanta`), so `med`/`max` are the meaningful statistics.
- CPU% is a `ps` lifetime average sampled mid-run3 — the bench does not report
  CPU itself. It is far below the 1,600-1,900% target and slightly below the
  811% previously recorded; under 20 workers on a 20-core box sharing ~950% with
  `Hermes` and peers, that ceiling is the dispatch/bandwidth wall the earlier
  campaign named, and it is untouched here.
- Memory is NOT flat, and this is the BASELINE (no fused code in the path):
  anon grows 0.63-1.09 MB/token and VmPeak 4.34-4.37 MB/token. The 1024-token
  rate (0.626 / 4.37 MB per token) reproduces the recorded 0.59-0.65 / 4.34-4.37
  exactly. So the stability contract FAILS on the baseline build, before any of
  this unit's work — the 1,024-token row is a fresh data point (the earlier
  campaign launched it and never harvested it) and it confirms the leak is
  linear to 13.5 GB VmPeak, not a startup artifact.
- The 1024-token run survived: VmPeak 13.54 GB of the 32 GB `run_lfm2_decode_bench.sh`
  cap.
- Rate is nearly context-independent (0.277 -> 0.241 tok/s across 128 -> 1024
  tokens): decode is weights-dominated at these lengths, so a faster dot path
  would show up almost linearly. That is what makes the fused path worth
  unblocking.
- Oracle: first-token argmax **597** in all three runs, identical to the recorded
  baseline (decode-fused-dot.md section 3b). The `5922` / `The answer is: 2`
  oracle quoted in the integration brief is STALE — the current
  `tests/lfm2_prompt.txt` yields 597 and `The answer is 4`, as that doc already
  records ("the 5922 figure in older docs predates the current prompt file").
  Generated ids begin `597 4695 20589 34 496 2992 355 229 ...` and the text opens
  `The user asks: "What is 2+2? Answer with the number only." ... The answer is 4.`

### The honest gap

    llama.cpp, same model / same box / 20 threads : 17.32 tok/s
    native loader, this session, 512 tokens       :  0.261 tok/s   -> 66x
    native loader, this session, 1024 tokens      :  0.241 tok/s   -> 72x

The fused kernel, IF it could be dispatched, is worth ~2.7x on the Q4_K dot
(measured, section above) — and Q4_K is only part of the per-token work (the tied
Q6_K output projection and the Q6_K down-projection are not fused by this kernel).
Composing honestly: even a perfect, free-dispatch integration of a 2.7x Q4_K dot
lands near 0.4-0.5 tok/s, i.e. ~35-40x from llama.cpp, with the pool-scaling cap
(~5.3x, measured in section 3b) and the 774% CPU ceiling still in the way. The
1,024-token measurement also shows the baseline degrading with the leak, so any
future e2e claim must be quoted WITH its token length.


