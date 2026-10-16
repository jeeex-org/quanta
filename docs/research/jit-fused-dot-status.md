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
