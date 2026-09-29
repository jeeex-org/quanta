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

Cache-only builds still fail, now with **SIGILL** at a fixed address
(`rip=0x42886c`) rather than `exit(16)`.

What is proven by behavioural bisection (inserting `return 1` at successive points
and rebuilding):

- The fault is inside `qobj_import()`. Removing the whole body, or removing the
  `qobj_import_pending()` call in `entry.quanta`, makes the build succeed.
- Everything up to and including the six region reads (`ent`, `names`, `meta`,
  `prms`, `pool`, `irb`) and the `qimp_pbase_next` block is safe.
- The fault is in the function-registration loop, at or after the metadata block.

What is **not** proven, and why: every value at the suspected statements is small
and in range. Dumped at the `fn_partype` write: `fnc=1`, `k=0`, `pcount=1`,
`mo=0`, `meta_bytes=144`, `name_len=6`, `nm=49`, `srclen=56`. The metadata region
itself decodes cleanly (`retstruct=-1`, `partype[0]=-1`, `parstr[0]=0`). The
trapping instruction is `imul rax(=10), rcx` where `rcx` holds a **code-range
value** (`0x4298...`), not a data address — a stride of 10 matches none of the
reader's strides (`FNS=56`, `IRS=40`, `VRS=24`, `PCS=24`, `LBS=16`,
`CAP_MAX=32`), so the faulting function is probably **not** `qobj_import` despite
the cut-point results.

**The recurring confound:** this compiler is layout-sensitive. Adding or removing
any statement in the failing path shifts code addresses and can move or change the
fault, so a cut-point that "fixes" the crash does not prove the neighbouring
statement was at fault. Several earlier conclusions in this investigation were
wrong for exactly this reason. Cut-point results here indicate a *region*, not a
statement.

Next step: identify the function containing `0x42886c` from source. The binary has
no section headers (`elf.quanta` writes `e_shoff=0`, `e_shnum=0` by design) and no
symbols, so `objdump -d` is silent and there is nothing to map the address
against. Either emit section headers in a diagnostic build, or build a source-order
function map by compiling each function in isolation and recording its entry
address.

## Note on stale artifacts

Caches generated before fix 1 are mode `0111` and unreadable, and caches generated
before fix 2 have wrong metadata offsets. They must be regenerated
(`--emit-qobj`) after these fixes, or they will keep failing in a way that looks
like the fixes did not work.
