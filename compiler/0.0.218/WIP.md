# 0.0.218 — WIP

Created from 0.0.217 (STABLE). `VERSION` points here; this is the only tree
whose `bin/x86/qc` may be modified.

Gate: 14 GREEN / 0 RED. Caches: G5 7/7, G4 8/8, G4-transitive 8/8, G6 5/5.

## Work in progress: `--emit-dynamic` with `extern "C"`

**Still not working.** A program with no externs builds and runs correctly
(`--emit-dynamic` returns 3, 7, 42). A program with one extern compiles without
the compiler crashing — a real advance over 0.0.217, where the compiler
segfaulted — but the resulting binary segfaults instead of returning 126.

### What changed from 0.0.217

0.0.217's failure was `DT_RELASZ` reporting 24 externs for a program with one,
so `.rela.plt` was the wrong size and the loader had nothing to bind. Fixed by
holding everything the dynamic path needs in a global (`g_dyn_ext`) instead of
locals: the extern count, the four region cursors, and the region sizes. Locals
in `write_elf` do not reliably survive its long body — this compiler reuses
bootstrap registers, and a value read back at its point of use had picked up a
stale offset.

Also fixed: `fn_name()` returns a source-relative offset, so the extern name is
read as `src + fn_name(fi)`. Reading it as an absolute address walked into
unmapped memory.

### Where it is stuck

`DT_RELASZ` is now correct (24, one extern) and the `.rela.plt` entry on disk is
correct (`r_offset` 0x42200328, `r_info` sym=1 type=7 JUMP_SLOT). The failure is
that every **vaddr in the dynamic table is one byte low**: `DT_JMPREL`,
`DT_PLTGOT` and `DT_RELA` all report `0x...4f` where the data is at `0x...50`.

`dynamic_vaddr` is derived as `gdata_vaddr + gdata_size + data_off`, mirroring
the file layout, but the RW `PT_LOAD`'s `p_vaddr` is not `gdata_vaddr` — the two
differ by a byte, and every address built on top of that base inherits the skew.
Deriving `dynamic_vaddr` from the LOAD segment's own `p_vaddr` rather than from
`gdata_vaddr` is the obvious next step, but it has not been done or verified.

This is the same class of defect as the two fixed in 0.0.217 (`e_phentsize`
written as 0, and a PLT cursor read back as 16 instead of 4984). Three
independent instances in one function is enough to say the real problem is the
codegen's handling of long-lived locals, not any single site in `write_elf`.
Fixing it properly means working in `codegen.quanta` / `funcscan.quanta`, not
adding more globals.

### Not blocking

`extern "C"` is supported and tested through `--emit-obj` plus a real linker —
the `extern-c` and `extern-ld` gate stages, both GREEN.
