# Next queue (ordered by the author, after the SI/Stage-1 unit finishes)

Three levers, in this order. Each entry carries the measured premise so it does not
have to be re-derived, and a pointer to where the detail lives.

## 1. Fix A1b — block bindings are never popped (best practice, secure, AND performance)

**DONE (0.0.237).** Watermark on the binding stack at every block entry/exit, fail-closed, warn-first
blast radius measured at **26 sites in 6 files** (1052 compile units), all migrated; gate 222/222 +
STDLIB 108/108 all stages GREEN; fixpoint `dca6b4ab…74e401`. Detail: `compiler/0.0.237/WIP.md`. The
0.0.236 attempt's "819/824" figures were a HOISTING transformation on an 821-row suite — not this
fix's cost. The A4 lever (home-slot reuse, 1104-byte frames) is still open: this version only makes
the live ranges non-overlapping.

**Behaviour:** an inner-block `let` rebinds the enclosing name's storage and stays
visible after the block. Verified live: `fn f(n) { let a = 1; if a == 1 { let p = 99 }; p = 77; print(p) }`
compiles and prints `77`.

**Why it is a defect, not a preference:** the failure mode is a store into a
*different variable's storage* — that is what A1 was (a `let fi` shadowing `ci_func`'s
`fi` parameter, then `SIGSEGV`). With raw pointers, `mem_alloc`, FFI, `asm!`, MMIO and a
ring-0 target, that is a memory-corruption primitive. SPEC.md §4.2 requires
out-of-contract operations to fail secure rather than corrupt silently; SPEC.md:94
already calls a bare `{ }` block "(scoping)".

**Required shape (from the earlier attempt's measurements):**
- Watermark the binding table on block entry, restore on exit.
- **Symmetric on every exit path** — `break`, `continue`, `return`, `defer`, traps. A
  partially-restored table is worse than the leak (non-deterministic scoping).
- Reset the per-vreg side tables with it (`vfloat`, `vreg_is_str`, ...): stale per-vreg
  tags caused two silent-wrong-value defects in one day.
- Fail closed: after the fix, leak-dependent code becomes a compile error, not a silent
  rebind.
- Roll out **warn-first** so the real blast radius is measured instead of assumed.

**Do not reuse the earlier attempt's conclusion:** the "38 compile failures / STDLIB
74/108" figures came from preserving the old behaviour by *hoisting* 12 sites, which is
**not** semantics-preserving (a `let x = f()` in a loop, hoisted, initialises once).
Those numbers are the cost of a wrong transformation, not of this fix. The honest figure
comes from the warn-first phase.

**Performance angle (why this is lever 1 and not just hygiene):** block scoping gives
non-overlapping live ranges, which is what allows home slots to be *reused* instead of
one slot per vreg — the same lever as A4 (1104-byte frames, ~8,000 recursion depth vs C's
262,000). So this and lever 2 are complementary rather than independent.

Detail: `docs/research/let-scope-inventory.md` (11 leak-dependent sites in the compiler's
own source, two honest routes). Owner's decision needed on which side is authoritative
(spec or implementation) — the source is the authority for behaviour, not SPEC.md, which
is known stale (flagged in `docs/INDEX.md`).

## 2. Speed up Quanta vs C

**DONE (0.0.238) — but it was NOT the lever this entry expected, and that is the finding.**
Constant division/modulo by strength reduction landed (0.0.238): `/` and `%` by a positive
compile-time constant no longer emit `idiv`. It also removed a real defect — the old
power-of-two path emitted the `sar` and then fell through into the idiv sequence, so
constant division paid both.

**Measured effect: 0-12 % on the 12 rows whose machine code changed** (`heavy_int` -12.2 %,
`div_const` -10.2 %, `heavy_int2` -7.3 %, best-of-15 interleaved A/B; the other 25 rows are
byte-identical and swing +-17 %, i.e. noise). The premise below — that this cluster's
6.8-32.3x is caused by `idiv` and will "move toward <=3x" — is **REFUTED**: `heavy_int2`
moved 35.5x -> 27.7x, `arith` 14.4x -> 14.7x, `heavy_int` 22.0x -> 22.0x.

**The real cost is the spill/reload traffic** (one home slot per vreg; `work()` = 254
instructions vs gcc's 9; 1104-byte frames). So the next lever is **A4 / next-use eviction**,
which A1b unblocked. Evidence: `compiler/0.0.238/WIP.md`, `benchmarks/BENCHMARK.md`,
`scripts/bench_ab.sh` (the tool that made the answer decidable — comparing two compilers on
the same source, and reporting whether they even emitted the same machine code).

Original premise, kept for the record and now marked wrong:

**Premise (measured on 0.0.233, suite in `benchmarks/`):** the gap is bimodal —
12 cases at 0.7-2.3x (several faster than gcc), 9 arithmetic-loop cases at 6.8-32.3x.
Worst offenders divide by a constant in a hot loop (`div_const` 19.9x, `heavy_int2`
24.9x, `arith` 15.1x). Root cause is `idiv` (40-80 cycles) for constant division, **not**
"no register allocation" — a 13-reg pool with LIFO eviction exists. `-O` is verified
inert. Integer division is floor semantics (verified), which makes strength reduction
simple: pow2 divisor = one `sar`, modulo = one `and`.

Plan: `docs/plans/performance.md`. Method: one lever per version, gate green before
promotion, `scripts/bench.sh` for the twin-fold + output-equality guards.

## 3. Speed up the Quanta loader so SI can use it

**Premise (measured today):** the native engine loads `QUANTA-LFM2.5-2.6Bv1-Q4_K_M.gguf`
in ~3.6 s inside **201-264 MB RSS** under a 4 GiB cap — memory discipline is good and
beats llama.cpp's footprint. But decode is the wall: this project's own
`docs/plans/lfm2-native-inference-perf.md` reports **69.4 s/token serial, 25.8 s/token at
8 workers**, with the parallel paths **defaulted off**. llama-server, on the same CPU and
a *larger* 7.5B model, measured **8.24 tok/s** decode and **11.40 prompt tok/s** (my own
bounded probe). That is a 200-500x gap.

**Why it is the SI blocker:** at ~26 s/token a 300-token generation is hours, so the
self-improvement loop cannot iterate on the native runtime. Three separate harness runs
were also killed at the interactive envelope, which is itself the argument that the loop
must run as a scheduled background job rather than inside a session.

**Also needed for the loop:** a generation driver end-to-end (prefill -> KV-cached decode
-> sample -> print). The parts all exist (`gguf`, `lfm2_forward`, `lfm2_bpe`,
`lfm2_chat.chat_build`, `sampling.sample_full`) but there is no assembled entry point;
a first one was written by the Stage-1 unit under `stage1/`.

**Prompt cost is the other half, independent of runtime:** a 10,583-byte retrieved
context is ~2.6k tokens, i.e. ~4 minutes of prefill at the measured prompt rate before the
first generated token. Prompt trimming and prefix caching matter whichever runtime is
used.
