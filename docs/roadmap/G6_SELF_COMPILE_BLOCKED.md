# G6 — self-compile from module caches

**Status: SUPERSEDED — this finding no longer holds. The gate now passes G6.**

Measured 2026-09-30 with binary `0768168f`, this document concluded:

> not achievable as written. G6 as specified requires a module boundary
> the compiler's source does not have.

and recorded `modules cacheable: ok=3 fail=16 of 19`.

That is no longer true. The current official gate reports:

```
qobj : GREEN  (module cache write/read/cache-only, G1+G3+G5+G4, plus G6 cache self-compile)
```

as of `0.0.223` (`6454f037`). The G4/G5 work that followed resolved the
per-module cacheability problem this document identified — see
`G4_TRANSITIVE_DESIGN.md` and `QOBJ_FEATURE_COVERAGE.md`.

The rest of this document is kept because the original measurement is still the
clearest record of *why* the problem existed, and because a future regression
in cache self-compile would look exactly like this. **Do not read the
conclusion above as current.**

## What G6 asks

> | G6 | Self-host with `.qobj` | Quanta compiles itself using cached modules |

## What I measured

Emitting a cache for each of the compiler's own 19 source modules, with the
G4-capable binary (`0768168f`):

```
modules cacheable: ok=3  fail=16   of 19
```

The 3 that succeed (`tokens`, `_bb`, `gguf_reader`) are the only ones with no
dependency on a sibling module.

## Why the other 16 cannot be cached

The compiler is split across 19 files, but it is **one translation unit, not 19
modules**. `main.quanta` pulls them in with `include "file.quanta"` —
compile-time *textual* expansion, and the comment at the top of `main.quanta`
says the order preserves the original monolith's line order so behaviour is
byte-identical.

The definitions are mutually dependent:

| module | needs | defined in |
|---|---|---|
| `globals.quanta:321` | `r64` | `helpers.quanta:5` |
| `helpers.quanta` | `TKS`, `toks` | `globals.quanta` / `tokens.quanta` |
| `codegen.quanta:32` | `irres`, `irop` | declared in earlier modules |
| `borrow`, `entry`, `method`, … | each other | — |

So `helpers` and `globals` are a cycle. Neither can be compiled alone, and no
ordering of the other 17 files makes them separable. Compiling any of the 16
fails at a real symbol:

```
$ qc --emit-qobj globals.quanta g.qobj
line 321: error: call to undeclared function: r64
$ qc --emit-qobj helpers.quanta h.qobj
line 16: error: undeclared variable: toks
```

## What *is* verified

Self-hosting itself, which is the substantive claim, and it holds exactly:

```
gen0 (installed):                    0768168fe2a6
gen1 = gen0 compiles the compiler:   0768168fe2a6
gen2 = gen1 compiles the compiler:   0768168fe2a6
gen3 = gen2 compiles the compiler:   0768168fe2a6
gen1 gate: 14 stages, 0 RED, exit 0
gen3 gate: 14 stages, 0 RED, exit 0
```

A four-generation fixed point, with the third-generation compiler running the
full suite green. See `scripts/selfhost_test.sh`.

## What would be needed for G6 proper

Not a cache change. A **source-level** change, in this order:

1. **Break the `helpers`/`globals` cycle** — move the primitives (`r64`, `w64`,
   `mem_load*`) into a leaf module that depends on nothing.
2. **Turn `include` into `import`** for the module boundary, or extract one real
   module with no back-references.
3. Then each extracted module is independently compilable, and G6 becomes
   meaningful: cache the modules, delete their sources, and compile the compiler
   from the caches.

Step 1 is a prerequisite for step 2, and both are source work on the compiler
itself, not cache work. Attempting G6 before them would mean caching modules
that cannot be compiled on their own — which is the thing G6 is meant to test.

## Recommendation

Treat the compiler as a single translation unit for caching purposes, which is
what it is. `include`-based textual expansion means the only unit that can be
cached is the whole program, and a whole-program cache would have to be the
binary itself — at which point the cache has no work to do.

G6 should be re-specified as: *given a self-hosting compiler at a fixed point,
does the cache round-trip preserve that fixed point?* That is answerable today
and would exercise G1/G3/G4/G5 against the real compiler rather than a
three-module fixture. Say the word and I will build it.
