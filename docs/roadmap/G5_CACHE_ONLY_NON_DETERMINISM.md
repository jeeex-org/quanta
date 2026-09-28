# G5 cache-only failure: non-deterministic memory corruption

## Symptom

With `lib/std/str.quanta` and `lib/std/aux.quanta` removed from disk and
their v7 `.qobj` caches present, a two-module cross-module program
compiles on some runs and exits 17 ("source too many tokens/IR limit") on
others. Every run that produces a binary produces the *correct* one.

Success rate across 8 identical runs has been measured at 2/8, 3/8, 4/8
and 6/8 at different points in the investigation. A deterministic
compiler on deterministic input cannot do this, so the fault is memory
corruption, not a logic bug in the call-patch or import paths.

Early in the investigation a second symptom appeared: up to 66 MB of
error spew plus a wall-clock timeout. That turned out to be a *different*
fault. `emit_ovf` calls `exit(17)` and cannot loop, so the 49-66 MB runs
were a runaway emitter writing patch records; after the arena bounds
below were added, the spew stopped and only the 39-byte
`emit_ovf` message remains. Do not conflate the two.

## Confirmed and fixed (gate-verified, commit 78b660fb)

Several caps were inherited from an era with much larger arenas, so they
admitted more than the mapping behind them could hold. The cap fired only
after the arena had already been overrun into whichever neighbour the
allocator placed next.

| cap | was | now | arena | real capacity |
|---|---|---|---|---|
| TOK_CAP | 500,000,000 | 8,000,000 | toks 320 MB, TKS 40 | 8,000,000 |
| IR_CAP | 1,000,000,000 | 26,843,545 | ir 1 GiB, IRS 40 | 26,843,545 |
| IMPSEEN_CAP | 8,100 | 1,000 | imp_seen 8 KB | 1,024 |
| qir_mod_n | unbounded | 26,843,545 | qir_mod 1 GiB | 26,843,545 |
| qobj_import fnc+fn_count | unchecked | <= FN_CAP | fns | — |
| qobj_import fn_pnames base | unchecked | <= 4,000,000 | fn_pnames | — |
| imp_load imp_seenc | write-then-check | check-then-write | imp_seen | — |

Gate: 12/12 GREEN (13 GREEN, 0 RED) with all of the above in the tree.
Self-host fixed point `692941ddafa9634916449168e7665026`.

## Attempted and rejected

- `FN_CAP` 250,000 -> 35,714 and `VAR_CAP` 250,000 -> 83,333. Arithmetically
  correct (fns 2 MB / FNS 56; vars 2 MB / VRS 24) but every cache-only run
  then failed 0/8, so these caps are evidently not the live constraint and
  tightening them breaks a legitimate compile. Reverted. **Worth a second
  look with measured peak values rather than derived ones.**
- A poison build filling all 89 arenas with distinct bytes. Stage 1 built;
  stage 2 segfaulted, so the instrumented build cannot self-host. Abandoned.
- Instrumenting `emit_ovf` to name the failing counter. Every attempt
  printed raw bytes instead of `name=value` and, being on the failure path,
  produced up to 66 MB of output. Four attempts, all reverted.

## What is still unexplained

The success rate is still 2-6/8. The corruption is allocation-layout
dependent, which is consistent with a single unguarded write into a shared
arena reached by a pointer that is sometimes valid and sometimes not.

Leading hypothesis, unproven: something in the cached-function path in
`ci_func` (codegen.quanta) writes through a base/index computed from
`fn_ir_start[fi]`, `fn_pcount[fi]` or `fn_pbase[fi]` without validating
that the index is within the function's own slice. The reader populates
those from the cache metadata, and the metadata is read with `r64` at
byte offsets `mo`, `mo+16`, `mo+20`, `mo+24+k*8`, `mo+112` out of a
128-byte record that the writer fills only partially.

## How to investigate without breaking the session

Never instrument a failure path. The probes above all failed for the same
two reasons: they print in a loop, and they are built into a compiler that
must self-host.

Instead, capture and reduce first:

- `scripts/g5_head.sh` — first 300 bytes of stderr from a failing run.
  Cheapest discriminator between failure modes.
- `scripts/g5_determinism.sh` — N identical runs, one line each.
- `scripts/run_gate.sh` — the 12-gate suite, summary only.
- `scripts/prune_scratch.sh` — bounded scratch cleanup.

A dump of the per-function metadata record (128 bytes, as written by
`qobj_write.quanta` and read by `qobj_import`) is the next artifact worth
capturing, and it can be read straight off disk from a generated cache
without running the compiler at all.

## Gate state

`78b660fb` + the `TOK_CAP` correction is the current best state: 12/12
GREEN, deterministic self-host, correct source builds, and single-function
cache-only cases working. G5 remains open: a multi-function cached module
does not reliably compile cache-only.

## Ruled out (real bugs, but not the source of the variance)

Each of these is a genuine memory-safety defect, fixed, and then measured
against the 8-run determinism test without moving the success rate off its
2-6/8 band. Listed so they are not re-investigated.

- `TOK_CAP` on a 32B stride. `TKS` is 40, so 10000000 overran `toks` by
  80 MB. Corrected to 8000000. Success rate unchanged.
- `qobj_import` fn_partype/fn_parbig/fn_parstr written at `(fn*200 + k)`.
  Those three tables are `mmap(2000000)` = 250000 slots, so at 200 slots
  per function they hold only **1250** functions, while the guard allowed
  `FN_CAP` = 250000. Any import past 1250 functions walked off the end.
  Guard corrected to 1250. Success rate unchanged (5/8).
- `FN_CAP` 250000 -> 35714 and `VAR_CAP` 250000 -> 83333. Arithmetically
  correct against `fns` 2 MB / FNS 56 and `vars` 2 MB / VRS 24, but every
  run then failed 0/8, so these are not the binding constraint and
  tightening them breaks a legitimate compile. Reverted.
- `qobj_import` metadata record offsets. Writer writes 0,8,16,20,24+k*8,
  48+k*8,80+k*8,112; reader reads 8,16,20,24,48,80,112. Symmetric, correct.
- `qobj_import` slot handling. `qimp_slot[i] = fnc` with `fnc` advanced
  once per function, and `fn_ir_count` written at the function's own slot.
  Correct.

## Why static analysis has stopped paying

Five candidate defects found by reading code have all been real, and none
of them changed the success rate. That is the signal: the fault is a
specific write whose index is sometimes valid and sometimes not, and
static reading cannot see its provenance. The next step has to be a
runtime observation, and every runtime observation attempted so far has
been defeated by two facts:

  1. `emit_ovf` is on the failure path, so a probe there can print 66 MB.
  2. The compiler must self-host, so an instrumented build that cannot
     self-host yields nothing (the poison build died at stage 2).

The way through is to observe WITHOUT modifying the compiler: run the
cache-only compile under a tool that records memory accesses, or dump
the full compiler state at the point of divergence from a core file. Both
avoid editing a failure path and both survive self-hosting because they
are external to the binary.
