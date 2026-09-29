# G5 Prerequisite — root cause: the cache was written unreadable

**Status: four defects fixed; one remaining (see "Still open").**

## Symptom

Every cache-only build (imported `.quanta` source removed, `.qobj` present) failed
with `rc=16` — `imp_err`, the "include not found" exit — even though the cache file
existed on disk. Source-present builds, with or without a cache, worked.

## What was ruled out first

A long stretch of the investigation chased the wrong thing. These are recorded so
they are not re-derived:

- **"The crash happens before `scantraits()`."** False. Those marker probes never
  printed because the run exited `rc=16` *cleanly* at the `imp_err` check — it was
  never a crash. The `fnc += 1` "minimal reproducer" was a red herring: the slot
  bump is the last thing a successful import does, so any import that reaches it
  and then hits the same later failure looks identical.
- **Memory corruption / arena overrun / stack overflow.** False. Valgrind reports
  **0 errors** and produces correct output. `strace` shows all 152 `mmap`s
  succeeding with no overlaps and no failures. Stack size is irrelevant (8 MB /
  64 MB / 256 MB / 1 GB behave identically). `SIGILL` vs `SIGSEGV` varying between
  builds is address-layout sensitivity in an already-failing process.
- **Metadata overlap, IR staging, `is_param_vreg`, optimizer liveness bounds.**
  All real bugs, all fixed, none of them the cause of *this* failure.

## Fixed defects

### 1. The cache was written unreadable (the `rc=16` blocker)

`qobj_write()` created the cache with a **two-argument** `file_open`:

```
let fd = file_open(path, 577)      // 577 = O_WRONLY|O_CREAT|O_TRUNC
```

`O_CREAT` requires a **third** argument, the file mode. The emitter only loads
argument registers the call site actually supplies, so `rdx` retained a stale
syscall value; the kernel masked that against the umask and produced mode `0111`
— execute-only, unreadable. Observed directly:

```
open("std/one.qobj",     O_RDONLY) = -1 ENOENT
open("lib/std/one.qobj", O_RDONLY) = -1 EACCES (Permission denied)
```

Every cache probe treats a failed open as "no cache", so the lookup reported the
cache absent, fell through to the source path, found no source, and raised
`imp_err` → `exit(16)`. Fixed by passing the mode (493 = 0755), matching what
the ELF writer already does.

**Consequence:** until this was fixed the cache was never read at all, so every
downstream symptom was second-hand. This is why the failure looked like a reader
problem, a resolver problem and a layout problem simultaneously.

### 2. Metadata stride mismatch (128 written vs 144 emitted)

The function entry's `meta_off` advanced by 128 while `qobj_write` emits a
144-byte record (`meta_bytes = emitted * 144`). Every function after the first
pointed 16 bytes *before* its real record, landing in the previous function's
`partype`/`parbig`/`parstr` arrays, so the reader loaded another function's
`fn_retstruct`/`fn_retbig`. A **single-function module cannot expose this**, which
is why every one-function test passed while multi-function modules were broken.
This is why G5 must be validated with multi-function modules, not one.

### 3. Pool scan bounded on absolute pointers (SIGILL)

```quanta
while L < 4096 && pool + pool_cur + L < pool + pool_bytes && ...
```

`pool` is a kernel-chosen mmap address near 2^47, so the left-hand sum passes
2^63 and the compiler killed *itself* on its own `jno` overflow guard
(`ud2` → SIGILL). Now compares offsets: `pool_cur + L < pool_bytes`.

### 4. `FN_CAP` was 7x past the real `fns` capacity

`FN_CAP = 250000` with the comment `fns arena 2MB / 40B (FNS=40)`, but `FNS` is 56
and `fns` is `mmap(2000000)` — 35,714 real entries. Every registration site checks
`FN_CAP` before writing `fns[fnc*FNS]`, so the guard admitted 7x more functions
than the mapping holds and then wrote past its end. The stale comment is what let
the two drift apart unnoticed. Now 35714, with the derivation recorded.

## Still open

Cache-only builds still fail, now with **SIGILL at `rip=0x4271b1`**. The call chain
has now been recovered from the stack (the binary has no unwind info, so the
return addresses were scanned off `$rsp` directly):

```
0x4271b1  FAULT   fn @ 0x427164  (77 bytes)
0x43ef83  caller  fn @ 0x43d998  (5611 bytes)
0x43d48c  caller  fn @ 0x43d3a8  (228 bytes)
```

**The faulting function is a one-line accessor.** Its whole body is:

```
mov  -0x38(%rbp),%rcx     ; the pointer argument
mov  -0x40(%rbp),%rdi
mov  (%rdi),%rax          ; <-- FAULT
mov  %rax,-0x48(%rbp)
```

That is `r64(p)` / `mem_load(p)` — a plain 8-byte load. It is not doing any
arithmetic; it is dereferencing a pointer it was handed.

**The pointer is wild.** At the fault, `rdi = 0x7fffda400018`, which is unmapped
(gdb: "Cannot access memory"). The instruction immediately before the trapping
`add`/`jno` pair loads a global from `0x422006a0`, whose runtime value is `3` — not
an arena base. So the sequence is roughly `rbx = local + 3` and the `local` it
loaded was already the bad `0x7fffda400018`.

**What this rules out.** Every value dumped inside the reader is small and sane
(`fnc=1`, `k=0`, `pcount=1`, `mo=0`, `meta_bytes=144`, `nm=49`, `srclen=56`,
`name_len=6`), the metadata region decodes cleanly (`retstruct=-1`,
`partype[0]=-1`, `parstr[0]=0`), all six region reads succeed with the right byte
counts (7, 144, 2, 200), and all 152 `mmap`s succeed with no overlaps. So this is
not an out-of-range index, a short read, or a failed allocation — a *pointer value
itself* is wrong by the time it reaches a load.

**The recurring confound.** This compiler is layout-sensitive: adding or removing
any statement in the failing path shifts code addresses and can move or change the
fault. Cut-point bisection here indicates a *region*, not a statement — which is
why several earlier conclusions in this investigation were wrong. Do not trust a
cut-point that "fixes" the crash.

Next step: find which local in the 5611-byte caller (`0x43d998`) holds
`0x7fffda400018`. That caller is large enough to be a merged/optimised function, so
the next useful move is to dump its frame slots at the call site
(`x/200gx $rbp`) and see which slot holds the wild value, then map that offset
back to a source local.

## Note on stale artifacts

Caches generated before fix 1 are mode `0111` and unreadable, and caches generated
before fix 2 have wrong metadata offsets. They must be regenerated
(`--emit-qobj`) after these fixes, or they will keep failing in a way that looks
like the fixes did not work.
