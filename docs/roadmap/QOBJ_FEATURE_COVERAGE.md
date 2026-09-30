# QOBJ feature coverage — what a module cache actually round-trips

**Status: 11 features round-trip correctly. One real gap (G4 transitive
staleness). One probe failure that is NOT a cache bug.**

Measured with the installed binary `0768168f`, via `scripts/qobj_features.sh`
and `scripts/qobj_hard_features.sh`. Each case builds the same program twice —
once from source, once cache-only with every source removed — and compares exit
codes.

## Round-trips correctly

| feature | result |
|---|---|
| scalars + cross-module call | PASS |
| >6 args (callee-saved spill path) | PASS |
| recursion in a cached module | PASS |
| struct value param/return | PASS |
| const/global access | PASS |
| while loop in a cached module | PASS |
| nested module calls, depth 3 | PASS |
| 3-module dependency chain | PASS |
| diamond import (two importers share a dep) | PASS |
| generic-typed function | PASS |
| a real `lib/std/` module | PASS |

The diamond case matters: it is the shape that produced unbounded re-expansion
before import-cycle handling existed (`imp_seenc` climbing to the cap, rc=17).

## The one real gap: G4 transitive staleness

A cache fingerprints **its own module's source only**. If A imports B and B
changes, A's cache is reused and is stale — A never reads B's source, so there
is nothing to compare against. Detected only by rebuilding.

Not a defect in the mechanism; it is the limit of what a single fingerprint can
express. Closing it needs the cache to record its dependencies' fingerprints and
check them, which is a format change (v10). Until then: **when you change a
module, rebuild the caches of everything that imports it.**

## extern "C" in EXEC mode segfaults — pre-existing, not a cache bug

The probe reports `extern C call in cached module (src=139, CACHE-ONLY=251)`.
Both sides fail, which means the cache is not the cause. Reduced to a
three-line program with no import and no cache at all:

```
extern "C" fn abs(x);
fn useabs(x) { return abs(x) }
fn main() { return useabs(0 - 5) }
```

→ **segfault, rc 139**, on the installed binary.

So `extern "C"` is broken in EXEC mode generally. The gate's `extern-c` and
`extern-ld` stages are GREEN because they exercise **object mode**
(`--emit-obj` + gcc/ld link), which is a different code path. The EXEC-mode
extern path has no coverage, and it is broken.

This is outside QOBJ's scope and is recorded here only so the probe result is
not mistaken for a cache defect. It deserves its own bug.

## How these probes were written

Two mistakes in the first version made them worthless, and both are worth
recording because they are easy to repeat:

1. **Hand-written expected exit codes.** The process exit code is the returned
   value mod 256 (measured: 0,1,2,5,7,11,12,23,36,45,120,255,256→0). My
   arithmetic was wrong for every case, so all eight reported `SKIP` and the
   probe proved nothing while looking like it was running. The probes now
   **measure the source build** and compare the cache-only build against it, so
   the only question asked is whether the cache reproduces the source.
2. **`extern "C" fn f(x)` without a semicolon.** The parser swallows the next
   `fn` and the caller is reported undeclared — which looks exactly like a cache
   import failure.

## Not covered by any probe

- Concurrent access to a cache from two compilations (no locking).
- Cache corruption: truncated or bit-flipped files (only the magic and version
  are checked, plus lengths).
- Cache invalidation across a toolchain change — a cache written by one compiler
  version and read by another. Only the format version is checked, and it is not
  a build identity.
