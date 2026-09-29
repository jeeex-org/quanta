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

### Follow-up: the frame dump identifies the shape of the bug

Breaking at the faulting load itself and dumping the caller's frame gives the
whole chain:

```
[caller_rbp+0x00] (array base) = 0x7ffe7986ca18      <- changes every run
[caller_rbp-0x08] (index)      = 0x3
rdi = base + 8                                    (i.e. base + index*8)
```

`x/2gx $base` on the base succeeds — it is a **readable, mapped** region, and the
qwords stored there are stack-range values (`0x7ffe7986e5d0`, `0x7ffe7986e5fd`),
not arena pointers.

So the failure is not a wild pointer. It is this: a `[ptr + i*8]` array read where
`ptr` legitimately points into the **relocated stack** region, the contents there
are leftover stack words, and one of those words is loaded as a data pointer and
dereferenced. The value read is stack garbage, which is exactly why it differs on
every run while the crash is deterministic.

`0x43d998` is `fn main` in `entry.quanta` (line 172) — the top-level driver, which
inlines the reader's call sites. So a **vreg** (a compiler-allocated register
slot) is being used as an array base without ever having been assigned a real
value. The reader's own arrays are all correctly-sized arenas and are not the
culprit; the uninitialised vreg is one the reader reads before assigning.

Prime suspect, in `codegen.quanta` `ci_func()` on the cached path:

```quanta
let pbase_c = r64(fn_pbase + fi*8)
...
let pnm_c = r64(fn_pnames + pbase_c + ppi*16)   // pbase_c is NEVER bounds-checked
```

`ppi` is validated (`ppi >= 0 && ppi < 8`) but `pbase_c` is not. If `fn_pbase[fi]`
is stale for a cached function, this indexes `fn_pnames` at an arbitrary offset.
Note also that `pseen` is compared in the loop condition but never incremented in
the visible code, so the loop runs to `ir_end` regardless.

### Follow-up 2: the faulting function is a spill-slot bug in the register allocator

Disassembling the faulting function again, with the stack dump alongside, settles
the mechanism:

```
0x42719d:  and    $0xffffffc0,%eax        <- stack alignment mask: base = rsp & ~63
0x4271a2:  mov    %rcx,-0x38(%rbp)
0x4271aa:  mov    -0x40(%rbp),%rdi       <- loads a DISPLACEMENT as a value
0x4271b1:  mov    (%rdi),%rax            <- FAULT: dereferences it as a POINTER
```

The array base is `rsp & ~63` — the compiler's own **aligned frame base**. And in
`emitter.quanta`:

```quanta
let SPILL_BASE = 48
fn spill_home(v) { return -(SPILL_BASE + (v + 1) * 8) }   // a NEGATIVE displacement
```

`spill_home()` returns a *displacement*, not an address. It is correct to use as
the `disp32` of `mov reg, [rbp+disp]` (which is what `rbp(r,d)` emits). The faulting
code instead **loads that displacement into a register and dereferences it as a
pointer**. So a vreg that holds a `spill_home` displacement is reaching a call
that expects a real pointer.

This is a register-allocator / spill-slot bug on the cached path, not a
cache-format bug. It explains why every cache-carrying build dies at the same
place regardless of cache content, and why the faulting value is leftover stack
content that differs every run.

Corroborating detail: the call site at `0x43ef7e` in the caller is `call 0x427545`
(the `mmap` emitter), and its result is stored to `-0x820(%rbp)`. Immediately after,
`mov 0x41dc170e(%rip),%rcx` loads a global whose runtime value is `3`, and the
sequence `mov %rdx,%rbx; add %rcx,%rbx; jno; ud2` is the overflow-trap idiom. The
bad displacement is therefore flowing through the same spill machinery that stores
`mmap` results — consistent with `spill_home` being applied to a value that is not
a vreg slot.

Next step: audit every use of `spill_home()` for one that feeds a value (rather
than a `[rbp+disp]` memory operand). That is the specific defect to fix.

### Follow-up 3: the spill-slot hypothesis is WRONG — audited and cleared

All `spill_home()` uses were audited. `spill_home(v)` returns
`-(SPILL_BASE + (v+1)*8)`, a negative displacement, correct as the `disp32` of an
rbp-relative memory operand. Every call site uses it that way:

- `emitter.quanta` allocator: `rbp(p, spill_home(vr))`, `wbp(spill_home(vr), pr)`
  — memory operands.
- `codegen.quanta:1493` `leabp(1, spill_home(cvr))` — `lea rcx,[rbp+disp]`, the
  correct idiom for "address of a local".
- `codegen.quanta:1527` `let hm=spill_home(av)` then `rbp(R_RDI, hm)` etc. — still
  a memory operand.
- `codegen.quanta:1836` `let off=spill_home(a0)` then a hand-emitted
  `lea rd,[rbp+off]` — correct.

So **no use dereferences a `spill_home` displacement as a pointer**, and the
register allocator is not the culprit. That hypothesis is cleared.

What the disassembly does establish, and what is worth keeping: the faulting
function loads a value and dereferences it, and that value is
`rsp & ~63` — the compiler's own aligned frame base — at the moment of the fault.
Combined with the caller being `fn main` (which inlines the reader's call sites),
this still points at a **vreg used as an array base before it is assigned**, but
the specific mechanism is not yet identified. Resolving it needs the source
statement, and the binary carries neither symbols nor section headers to map
`0x4271b1` back to one.

## Note on stale artifacts

Caches generated before fix 1 are mode `0111` and unreadable, and caches generated
before fix 2 have wrong metadata offsets. They must be regenerated
(`--emit-qobj`) after these fixes, or they will keep failing in a way that looks
like the fixes did not work.
