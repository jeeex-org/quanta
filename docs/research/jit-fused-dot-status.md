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
