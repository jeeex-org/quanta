# 0.0.217 — STABLE

Promoted 2026-09-30. Guards met at promotion time:

| guard | result |
|---|---|
| x86 self-host fixed point | installed = gen1 = gen2 = `4d11ea7b73d9` (byte-identical) |
| authoritative gate | 14 GREEN / 0 RED |
| qobj gate (blocking) | 13/13 |
| self-host suite | 8/8, four-generation fixed point |
| cache suites | G5 7/7, G4 8/8, G4-transitive 8/8, G6 5/5, features 7 full / 0 gaps |

`VERSION` points here. `compiler/0.0.218` is the WIP for work after this point;
it starts as a copy of this tree, and its `bin/x86/qc` is the only binary that
may be modified.

## What this version contains

**Module cache (`.qobj`), format v10 — the qobj roadmap is complete.**

- G1 write, G2 read, G3 consume, G5 cross-module calls, G4 staleness including
  the transitive case, G6 self-compile. All six verified; the qobj gate is 13/13
  and blocking, so a regression in any of them turns the gate red.
- v10 added a dependency-fingerprint region. A cache now rejects itself when an
  *imported* module changes, not only when its own source does. v8 and v9
  caches are rejected outright, since neither can establish that.
- G6 is satisfied at the granularity the source has: the compiler is one
  translation unit, so it caches as a single 4.7MB module holding 327 functions,
  and builds working binaries from that cache with every `.quanta` deleted.
  Per-file caching of the 19 source files is still structurally blocked — they
  are mutually dependent — and needs source work, not cache work.

**`--emit-dynamic` works.** It previously crashed on every program, including
`fn main() { return 3 }`. Five defects fixed: an unaligned `.dynamic` table, a
`PT_DYNAMIC` offset recomputed 13 bytes from where the section actually landed,
`dynamic_size` reserving 12 entries for 15, `e_phentsize` written as 0 because a
local had been clobbered, and a PLT cursor that read back as 16 instead of 4984
and so wrote stubs on top of `e_phoff`. The last two are the same class: this
compiler's bootstrap register reuse aliases a slot between a `let` and its use
across a long block.

## Known limitation at promotion

`--emit-dynamic` with an `extern "C"` call returns 126 instead of calling the
function. `DT_RELASZ` reports 24 externs for a program that has one, so
`num_extern` is inflated — the same slot-aliasing defect one level deeper than
the two fixed above. Carried into 0.0.218 to be fixed at the codegen level.

This does not block `extern "C"`, which is supported and tested through
`--emit-obj` plus a real linker: the `extern-c` and `extern-ld` gate stages, both
GREEN.

## A note on measurement

Three separate debugging rounds in this cycle produced *no usable output* before
the cause was found, and the reasons are worth recording:

- `file_write(2, "...", n)` passes a Quanta string literal, which carries an
  8-byte header. Writing from the literal writes the header. Writing to fd 1/2
  from compiled code produces nothing at all; writing to a real file handle
  works and returns the byte count.
- Expectations written by hand were repeatedly wrong. The process exit code is
  the returned value mod 256, not the value itself, and several fixtures
  returned 0 or segfaulted. Probes now *measure* the source build and compare the
  cached build against it, so they ask one question: does the cache reproduce the
  source?
- One conclusion was wrong and shipped: five `.qobj` emit pointers were believed
  to double-add `elfb` and had it stripped, which caused the very crash the
  change claimed to fix. They are `elfb`-relative, like every sibling writer.
  Reverted in `29865d33`.
