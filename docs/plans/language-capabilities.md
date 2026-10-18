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
| 1 | **f16/f32 types + narrowing conversion** | `lexer.quanta:375-386` — `f16`/`f32`/`f64` are literal suffixes that are discarded ("A no-op for the value -- one float representation"); no compiler builtin exists; widening is hand-written bit math at `gguf.quanta:1592 fn f32_to_f64` / `:1719 fn f16_to_f64`; the only `f64_to_f32` in the tree is `cuda_daemon.quanta:653 gpu_f64_to_f32`, which ships the job to the GPU | Every float is f64 = 8 bytes. **All 49 `mem_alloc` sites in `gguf_mm.quanta` + `lfm2_forward.quanta` multiply by 8** — not one by 4 or 2. KV at 128k = **32.21 GB** vs llama.cpp's 2.15 GB; KV read **8.59 GB/token** vs 2.15 GB | f16 KV cache, f32/f16 activations, every narrow-storage win; the 128k context wall. **LANDED in `compiler/0.0.247`** — types, real 2/4-byte widths, conversions pinned against ggml at zero tolerance, f32 arithmetic, promotion rules and typed literal suffixes; see `docs/research/f16-f32-language-types.md`. The loader adopting it is a separate follow-on, and it will hit #11 and #12 first |
| 2 | **Atomics / concurrency primitives** | `mm_matvec_par` distributes work as disjoint STATIC row slices; a work-stealing counter was measured **931 of 2048 rows wrong** | Static partitioning ⇒ load imbalance; pool measured at **595–811% CPU of ~2000% available**, ceiling ~5.3×; **achieved concurrency 11.2 of 20** measured 2026-10-18 — the static slice, not the kernel, is what caps the pool | Dynamic work distribution; the pool-scaling lever (one of the two levers named for 15 tok/s) |
| 3 | **Debug info / symbols** | Compiler emits a symbol-less blob — no `perf`, no callgrind, no symbols in traces | Hand-instrumented timers and hand-built stage probes; segfaults diagnosed with gdb on raw addresses | Real profiling, post-mortem debugging, stack traces. Every JIT defect this session was found by manual byte-dumping |
| 4 | **Typed buffers / safe indexing** | Buffers are raw byte pointers with hand-computed strides: `mem_alloc(c * 8)`, `fc_kv_at` returns `+ (…)*8`. The KV index bug reached **byte 503,315,968 of a 249,856-byte buffer** because two expressions disagreed about the unit stride | Every index expression must be manually audited against its allocation; the same class recurred (KV layer stride, 8× DMD overrun, the 503 MB overshoot) | Bounded-safety for buffer access; eliminates the project's most expensive recurring bug class |
| 5 | **Safe allocation lifetime** | `mem_alloc` inside a loop is unsafe — the next iteration clobbers the pointer (`gguf_mm.quanta:27`, `:246` "ONE cell for the whole loop") | Allocations hoisted by hand; state kept in globals (`fc_kvbuf = 0` sentinel-initialized, lazily filled) | Composable memory usage; a real ownership/allocator model |
| 6 | **No silently-truncating emitter** | `jbytes(n, hex)` writes only the first `n` bytes; `n` must equal `len(hex)/2` or bytes vanish. Caused **9 mis-encodings** (one 4-byte `sub rcx,1` declared as 3) and a kernel segfault | Every `jbytes` call site must be manually audited against its hex string | Correct-by-construction machine-code emission; the JIT has no safety net |
| 7 | **Located diagnostics for unbound names** | An unbound keyword token in expression position **traps the compiler** instead of erroring (`docs/plans/bugs.md` A25) | None — the compiler dies | Basic developer ergonomics; any new keyword-named binding |
| 8 | **String-keyed brace literals** | `fn f() { return { "a": 1 } }` → **compiler SIGILL rc=132** on both 0.0.245 and 0.0.246 (A24) | None — `lib/std/ast.quanta` simply does not build | `lib/std/ast.quanta`; any map-shaped literal |
| 9 | **f32 SIMD / vector arithmetic** | No f32 arithmetic at all today; the fused kernels are f64/AVX2 (`ymm`), 8-byte operands | Kernel operands are f64, so every load/store moves 2× (or 4×) the necessary bytes | Halving the fused kernels' operand traffic once f32 exists (#1) |
| 10 | **f128** | Absent from the lexer's suffix list and from hardware (x86-64 has none) | — | Nothing today. Listed for completeness because "all the features" was the instruction; cost/benefit is unfavourable and it should be an explicit decision, not a silent omission |
| 11 | **f16/f32 parameter and return declarations** | `fn f(x: f32) -> f32` parsed, but `fn_parft`/`fn_retft` in `globals.quanta` were written by nothing — the declared format was lost at the call boundary (A26, probe-verified) | A typed float could not cross a function boundary: the parameter arrived untagged and a call result was an untagged f64 carrier, so the first `+` on it silently became f64 arithmetic | **LANDED in `compiler/0.0.248`.** Declared types are recorded (`fn_parft` from the signature, `fn_retft` from `fn_rettype_name` via the new `scan_floattypes()`) and applied at both ends: the CALLEE narrows a parameter on entry and a declared return before `ret`, and the caller tags the call result so chained arithmetic stays in binary32. THE CONVENTION: an f16/f32 argument crosses as its widened f64 carrier in the ordinary ABI register (rdi/rsi/rdx/rcx/r8/r9, stack from arg 6) and the callee narrows once — narrowing in the callee is forced by the fused parse/emit order, since a callee can be emitted before any call site exists. Pinned on raw 64-bit patterns by `test_suites/codes/f32_f16_calling_convention_test.quanta`; see `docs/research/f16-f32-boundary-and-integer-conversions.md` |
| 12 | **Runtime CPU dispatch for ISA extensions** | f16 conversion emitted `vcvtph2ps`/`vcvtps2ph` unconditionally; on a target without F16C the same binary SIGILLs | Every ISA-dependent builtin had to be assumed present; no CPUID gate and no integer fallback | **RESOLVED in `compiler/0.0.248` by REMOVING the dependency rather than dispatching it.** Every f16 conversion is now integer bit manipulation (f64→f16 with one RNE rounding, exact f16→f32), which is the same arithmetic `lib/std/gguf.quanta` already used; f64↔f32 keeps `cvtsd2ss`/`cvtsst2sd`, both SSE2 and part of the x86-64 baseline, so nothing is left to dispatch on. Dispatch alone could NOT have fixed the f64→f16 direction: `vcvtps2ph` takes an f32, so f64→f16 through it rounds twice. Verified mechanically — gating stage 1.6d scans the emitted bytes (0.0.247 emitted 58 F16C opcodes in `f16_single_round_test`, 0.0.248 emits 0). A F16C fast path behind a cached-CPUID check is a footprint/speed follow-on, not a correctness need, and is named here as such |
| 13 | **Single-rounding f64→f16 cast** | `x as f16` narrowed to f32 and then to f16 — two roundings by construction, and the f64→f16 builtin itself went through `cvtsd2ss` first, so three | A cast was not one rounding, so its result depended on the intermediate format the implementation happened to name | **LANDED in `compiler/0.0.248`: ONE rounding, integer.** The "no counterexample was found" note was WRONG and is corrected here: compared against an exact-rational reference over 2,000,000 random f64 bit patterns, the double-rounded chain differs on 2 of them (e.g. `4997.9998123605865` → 0x6CE1 single, 0x6CE2 double), and the discrepancy is dense near f16 midpoints. `as f16` is now one `ft_narrow(l,2)`, the f16 buffer store is one rounding too, and `f16_single_round_test` pins it with CONSTRUCTED witnesses (an even f16 pattern H, the exact midpoint of H and H+1, and m + 2^-37: single rounding must give H+1, the double-rounded chain gives H) |
| 14 | **Typed allocator / declared element count** | `let b: f32[N] = mem_alloc(K)` takes its runtime length from the allocator header (`K` qwords) — exactly as `i64[K]` does; `N` records the element type only, and the bounds check is against `K` | Every typed buffer's storage must be hand-computed in qwords, and a declared `N` larger than the allocator's capacity is silently unreachable instead of an error | **SEMANTICS MEASURED AND PINNED in `compiler/0.0.248` (not yet enforced).** Two forms, and they differ: `let b: T[N] = <init>` — N is INFORMATIONAL (parsed, discarded; the stride follows the declared element type, the bound is the allocator's header), so `let b: f32[2] = mem_alloc(8)` legally indexes 0..7. `let d: T[N]` with NO initialiser — N IS the allocation (`IR_ARRNEW` with N elements, header N). Verified by `f32_buffer_semantics_test` (exit 0) and `f32_buffer_bound_trap_test` (exit 132: the same declaration with a smaller allocator traps at the allocator's count, which is what identifies the bound). ENFORCEMENT OF THE DECLARED N is the next lever and is deliberately NOT half-done here: the shape is a capacity check emitted at the binding (`header >= N` for a sized annotation with an initialiser, trapping like the index check), which needs an IR op or a reuse of the index trap that the dead-def pass cannot rewrite — see `docs/research/f16-f32-boundary-and-integer-conversions.md`. Until then no row in the tree claims the declared N is checked |
| 15 | **A clock that does not allocate** | `clock()` is a compiler builtin that does `mmap(16)` + `clock_gettime` + `munmap(16)` **per call** — `emitter.quanta:3142`; measured **5,148 ns/call** vs **135 ns** for one raw `syscall(228)` | `lib/std/gguf_mm.quanta:1129-1147` documents it and bypasses it with `mm_prof_now_b()`, a raw syscall mark, explicitly "Not clock()" | Fine-grained profiling; the instrument currently costs more than most operations being measured (A27) |
| 16 | **Locally-stable type inference** | Adding one untyped `let` binding a function's result propagated an **f64 format tag into a different function's return type**, so an unrelated gate row stopped compiling — caught by the gate, 2026-10-18 | None yet: adding instrumentation can change a signature callers see | Instrumentation and refactoring generally; a return type should not depend on an unrelated local (A28) |
| 17 | **A fused multiply-add you can actually write** | No `fma` builtin and no automatic contraction: source cannot express `a*b+c` as one operation, while the emitted kernels do `vmulpd`+`vaddpd` as two instructions (`/proc/cpuinfo` reports `fma`) | FMA is reachable ONLY by hand-emitting raw bytes through the JIT, so lib/std code cannot use it at all; noted by the decode unit 2026-10-18 | ~2x on every MAC chain. Needs a language decision on whether to expose `fma(a,b,c)` explicitly, contract automatically (moves bits), or both (`docs/plans/performance.md`) |

| 18 | **Hex literals wider than 32 bits** | A hex literal with more than 8 digits is silently wrong (A29): `0x100000000` → 1152921504606846976, `0x1FFFFFFFFF` → 0x1FFFFFFF000000FF. The first 8 digits land in the high 32 bits and the rest in the low bits; ≤8 digits and decimals are correct | Large constants must be built from shifts — the 0.0.248 f16 rounding constant (2^41-1) had to be written `ri(0,1); rshl_imm(0,41); rdec(0)` because the literal was wrong | Every >32-bit hex constant in user code; a silently wrong rounding mask is exactly the failure mode the f16 work is trying to remove. Own version, own red-first row |
| 19 | **Exact decimal → f64 literals** | One 17-digit decimal literal rounds 1 ULP away from the correctly rounded f64 (A30): `4997.9998123605865` → ...594, correct ...595. Three other 17-digit literals are correct, so it is a specific input, not a global digit limit | A long decimal literal cannot be used as an exact oracle; tests must build witnesses from bit patterns or powers of two | Any test that pins a bit pattern from a long literal. Fixture-driven against the host `strtod` |

## Ordering

Items are ordered by **what they block**, not by size:

1. **#1 (f16/f32 + narrowing)** — **LANDED in `compiler/0.0.247`**; it was the prerequisite for the entire
   narrow-storage class and for the 128k context wall. Its three immediate follow-ons landed in
   **`compiler/0.0.248`**: **#11** (typed floats across a call boundary), **#12** (the F16C
   dependency, removed rather than dispatched) and **#13** (single-rounding f64→f16). **#14**'s
   semantics are measured and pinned there, with enforcement left as its own lever. **#9** (f32 SIMD)
   follows naturally as its own version, and **#18/#19** (two silently-wrong literal classes found on
   the way) are queued as their own front-end levers.
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
