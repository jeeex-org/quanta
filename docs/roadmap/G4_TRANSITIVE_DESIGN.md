# G4 transitive staleness — design worked out, implementation reverted

**Status: NOT FIXED. The v10 attempt broke the G3/G5 cache-only path and was
reverted. HEAD is unchanged and the gate is green. This records the design and
the blocker so the work is not repeated from nothing.**

## The gap

A v9 cache fingerprints **its own module's source only**. If A imports B and B
changes, A's cache is reused and is stale: A's own bytes are unchanged, so its
fingerprint still matches. A never reads B's source, so there is nothing to
compare against.

Confirmed by measurement, not inference: with `top → mid → leaf`, editing
`leaf.quanta` left `top.qobj` being used, and the build with the cache present
disagreed with the build with the cache removed (11 vs 250).

## Design that was implemented

Format v10, header 40 → 48 bytes:

| offset | field |
|---|---|
| 32, 36 | own source fingerprint (v9) |
| 40 | `dep_count` |
| 44 | `dep_bytes` (informational; derived as `dep_count * 4108`) |

A **dependency region** appended after every other region — `dep_count` records
of 4108 bytes: `[4-byte path length][path bytes, NUL-padded to 4096][4-byte fp
lo][4-byte fp hi]`. Located from the end of the file (`size - dep_count*4108`),
so existing region offsets do not move.

Producer side: `imp_srcpaths` / `imp_srcpc` in `globals.quanta`, appended in
`imp_load` at the same point as the existing dedup record — deliberately *before*
the cache branch, so a module consumed **through its cache** is still recorded.
That case matters: its IR is inside this cache and its source can still change.

Consumer side: `qobj_deps_stale()` re-fingerprints every dependency and returns
stale if any differs. Called from the existing `qobj_cache_is_stale()`, so all
four consume sites inherit it. A dependency whose source is **absent** is not
treated as changed — that is the G3/G5 cache-only contract.

v9 caches are rejected: without a dependency list their transitive validity
cannot be established, and accepting them is exactly the bug being closed.

## What worked, and where it broke

Working and verified:
- the dependency region was written correctly — `dep_count=2`, paths
  `lib/std/mid.quanta` and `lib/std/leaf.quanta`, with fingerprints that matched
  an independent FNV-1a computation
- the region was located correctly from the file size (base 1364, file 9580)
- relative paths resolved correctly from the compile cwd

Two real defects found by instrumenting rather than guessing:

1. **`dep_count` was declared and never assigned.** The header advertised
   `imp_srcpc` dependencies while the region writer tested the local
   `dep_count`, so the region was never emitted and every cache looked like it
   had deps it did not have. Fixed by using `imp_srcpc` throughout.

2. **Cache-only consumption broke.** Once the reader required v10 and read a
   48-byte header, the cache-only build stopped working. The specific cause was
   not isolated before reverting.

## The unresolved question

After fixing (1), instrumentation showed `qobj_deps_stale()` was **never
entered** on a build that demonstrably consumed the cache — the two builds
differed, so the cache *was* being used. All four `qobj_cache_is_stale()` call
sites are correctly gated, and the import resolves through one of them. So
either:

- a fifth, ungated path stages or consumes a cache, or
- the call is being pruned, or
- the function's early returns fire before the dep call

`grep -n 'qobj_cache_is_stale('` shows four call sites, all gated, and the
`qobj_stage_bare` pair is included. That contradiction is the actual blocker and
it needs a clean instrumented run to resolve — not another guess.

## Honest assessment

I burned a lot of iterations on this and did not converge. The design is sound
and the producer half is verified working; the consumer half is not. Reverting
was the right call: a half-finished format change that breaks the cache-only
path is worse than a documented gap, because G5 and G6 both depend on that path
working.

**The gap remains exactly as documented in `QOBJ_FEATURE_COVERAGE.md`: when you
change a module, rebuild the caches of everything that imports it.**

## If this is picked up again

1. Start from `scripts/g4_transitive.sh` (8 assertions, currently 4/8 — the
   four that pass are the non-transitive ones). It is the test that must go
   green.
2. Resolve the contradiction above first: prove which code path consumes a
   cache for `import std/x`, with a single debug print at the top of
   `qobj_cache_is_stale`, before changing anything else.
3. Only then fix the consumer, and re-run `g5_verify.sh` (7/7) and the qobj gate
   (11/11) to confirm cache-only still works. Those are the regression guard.
