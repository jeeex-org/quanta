# Language capability backlog — fix the language, never work around it

## The policy (author, verbatim)

> "make sure you never do workaround again. if the language has limitation then implement in the
> lnauage as a prerequisite before implementing the features. Quanta must be best of breed language
> so it must have all the features and capability"

**Rule.** When a feature needs a capability the language does not have, the capability is implemented
**in the language first**, as its own version, with its own red-first gate rows, fixpoint and
`verify-release`. Nothing is built on top of a workaround. A workaround is a defect with a
respectable-sounding name: it converts a missing language feature into permanent, invisible cost
spread across every caller.

**Why it costs more than it looks.** Every item below was paid for twice — once when the feature was
built without the capability, and again when the capability was added and every caller had to be
revisited. The f64-everywhere case is the clearest: 49 call sites hard-code `× 8`, one `mem_alloc`
per buffer, all of which have to be found and repaired by hand the moment f16/f32 exist.

**What counts as done for an item here.** Its own version tree; a test that FAILS before and PASSES
after; the 4-generation self-host fixpoint holds; the gate is green with the new rows registered in
the same commit as their sources; `verify-release` passes; and the item names the call sites that
can now stop working around it.

## Backlog (evidence is file:line in the live source, not in docs)

| # | Missing capability | Evidence in source | Workaround it forces today | What it blocks |
|---|---|---|---|---|
| 1 | **f16/f32 types + narrowing conversion** | `lexer.quanta:375-386` — `f16`/`f32`/`f64` are literal suffixes that are discarded ("A no-op for the value -- one float representation"); no compiler builtin exists; widening is hand-written bit math at `gguf.quanta:1592 fn f32_to_f64` / `:1719 fn f16_to_f64`; the only `f64_to_f32` in the tree is `cuda_daemon.quanta:653 gpu_f64_to_f32`, which ships the job to the GPU | Every float is f64 = 8 bytes. **All 49 `mem_alloc` sites in `gguf_mm.quanta` + `lfm2_forward.quanta` multiply by 8** — not one by 4 or 2. KV at 128k = **32.21 GB** vs llama.cpp's 2.15 GB; KV read **8.59 GB/token** vs 2.15 GB | f16 KV cache, f32/f16 activations, every narrow-storage win; the 128k context wall. **IN PROGRESS — `compiler/0.0.247`** |
| 2 | **Atomics / concurrency primitives** | `mm_matvec_par` distributes work as disjoint STATIC row slices; a work-stealing counter was measured **931 of 2048 rows wrong** | Static partitioning ⇒ load imbalance; pool measured at **595–811% CPU of ~2000% available**, ceiling ~5.3× | Dynamic work distribution; the pool-scaling lever (one of the two levers named for 15 tok/s) |
| 3 | **Debug info / symbols** | Compiler emits a symbol-less blob — no `perf`, no callgrind, no symbols in traces | Hand-instrumented timers and hand-built stage probes; segfaults diagnosed with gdb on raw addresses | Real profiling, post-mortem debugging, stack traces. Every JIT defect this session was found by manual byte-dumping |
| 4 | **Typed buffers / safe indexing** | Buffers are raw byte pointers with hand-computed strides: `mem_alloc(c * 8)`, `fc_kv_at` returns `+ (…)*8`. The KV index bug reached **byte 503,315,968 of a 249,856-byte buffer** because two expressions disagreed about the unit stride | Every index expression must be manually audited against its allocation; the same class recurred (KV layer stride, 8× DMD overrun, the 503 MB overshoot) | Bounded-safety for buffer access; eliminates the project's most expensive recurring bug class |
| 5 | **Safe allocation lifetime** | `mem_alloc` inside a loop is unsafe — the next iteration clobbers the pointer (`gguf_mm.quanta:27`, `:246` "ONE cell for the whole loop") | Allocations hoisted by hand; state kept in globals (`fc_kvbuf = 0` sentinel-initialized, lazily filled) | Composable memory usage; a real ownership/allocator model |
| 6 | **No silently-truncating emitter** | `jbytes(n, hex)` writes only the first `n` bytes; `n` must equal `len(hex)/2` or bytes vanish. Caused **9 mis-encodings** (one 4-byte `sub rcx,1` declared as 3) and a kernel segfault | Every `jbytes` call site must be manually audited against its hex string | Correct-by-construction machine-code emission; the JIT has no safety net |
| 7 | **Located diagnostics for unbound names** | An unbound keyword token in expression position **traps the compiler** instead of erroring (`docs/plans/bugs.md` A25) | None — the compiler dies | Basic developer ergonomics; any new keyword-named binding |
| 8 | **String-keyed brace literals** | `fn f() { return { "a": 1 } }` → **compiler SIGILL rc=132** on both 0.0.245 and 0.0.246 (A24) | None — `lib/std/ast.quanta` simply does not build | `lib/std/ast.quanta`; any map-shaped literal |
| 9 | **f32 SIMD / vector arithmetic** | No f32 arithmetic at all today; the fused kernels are f64/AVX2 (`ymm`), 8-byte operands | Kernel operands are f64, so every load/store moves 2× (or 4×) the necessary bytes | Halving the fused kernels' operand traffic once f32 exists (#1) |
| 10 | **f128** | Absent from the lexer's suffix list and from hardware (x86-64 has none) | — | Nothing today. Listed for completeness because "all the features" was the instruction; cost/benefit is unfavourable and it should be an explicit decision, not a silent omission |

## Ordering

Items are ordered by **what they block**, not by size:

1. **#1 (f16/f32 + narrowing)** — in progress; it is the prerequisite for the entire narrow-storage
   class and for the 128k context wall.
2. **#2 (atomics)** — the prerequisite for the pool-scaling lever, and therefore for any future
   parallelism work. Doing pool tuning before this means tuning a static partition that has to be
   thrown away.
3. **#3, #4, #5** — capability that every future defect hunt pays for again until it exists.
4. **#6–#8** — correctness and ergonomics of the toolchain itself.
5. **#9** — follows #1 naturally, as its own version.
6. **#10** — explicit decision required; not scheduled.

## Enforcement

Before dispatching or starting any feature, ask: **does this feature need a capability that does not
exist yet?** If yes, the capability is its own version, listed here, and it goes first. If a feature
was already built on a workaround, that is recorded here as the workaround's cost and the item's
priority is raised — the workaround is debt against this list, not a design.
