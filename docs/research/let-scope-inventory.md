# Block-scoped `let`: migration inventory

**Status: APPLIED in 0.0.237 — route 2 below, done properly.** Route 1 (keep the leak, correct the
documents) was **rejected**: the leak is a memory-corruption primitive, not a documented extent — on
0.0.236 it SIGSEGVs the compiler on a tuple-payload enum, makes a bare `Ok(7)` payload read back as
5, and in `lib/std/gguf.quanta` passed an uninitialised pointer to six dequant routines and then to
`mem_free`.

**Where the shipped numbers are:** `compiler/0.0.237/WIP.md`. Measured warn-first over 1052 compile
units: **26 sites in 6 files** (gguf 12, method 6, entry 3, lexer 2 — one silent, funcscan 1,
parse 1, plus a frozen fuzz seed), all migrated; gate 222/222 + STDLIB 108/108, all stages GREEN;
3-generation fixpoint `dca6b4ab…74e401`.

**What is history below, not measurement of the fix:** the reverted 0.0.236 attempt applied the
one-line patch and then HOISTED 12 sites, which is not semantics-preserving (`let x = f()` inside a
loop, hoisted, initialises once), and it reported against a suite that then had 821 `EXPECTED.tsv`
rows (214 core rows now). Its "819/824, 38 compile failures, STDLIB 74/108" are the cost of that
transformation plus that suite, not of block scoping. The pre-fix preparation text is kept unchanged
so the reasoning that led to the decision stays legible.

## What the language does today

`parse_block()` (`compiler/<VER>/src/x86/parse.quanta:153`) pushes/pops only the *ownership* scope
(`owned_scope_push()` … `owned_scope_pop_one(my_scope)`, single exit at the end of the function). Local
bindings live in the `vars` table with `varc` as the count, appended once per `let`, and `vfind()`
(`helpers.quanta:493`) resolves by scanning **newest-first** — deliberately, so that a re-`let` inside a
loop or branch binds to itself. Nothing truncates `varc` when a block ends, so the innermost binding of a
name stays the resolution target for the rest of the function.

Measured on the **shipping** compiler, both 0.0.233 and 0.0.234:

```quanta
fn f(p) { let a = 1
 if a == 1 { let p = 99 }
 print(p) }          // 99 -- the parameter is gone
fn g(p) { let q = 0
 while q < 1 { let p = 77; q = q + 1 }
 print(p) }          // 77
```

## The one-line patch (block scoping)

```quanta
fn parse_block() {
    let my_scope = owned_sctop
    owned_scope_push()
    let my_varc = varc                 // <-- save
    ...
    defer_replay_range(my_scope)
    owned_scope_pop_one(my_scope)
    varc = my_varc                     // <-- restore: drop this block's bindings
    blk_depth = blk_depth - 1
```

Every block entry point in the compiler routes through `parse_block()` (`parse.quanta` call sites at
`if`/`else`/`while`/`for`/`match` arms/`unsafe`), so one save/restore pair covers them all. Nesting is
handled naturally (each invocation saves its own `varc`).

## Why it must be its own version

Applying exactly that patch and rebuilding the compiler **from its own source** makes the fixed compiler
reject 11 sites in its own 23k lines — code that declares inside a block and reads after it. That is the
migration list, and it is the compile-time proof that the current behaviour is load-bearing:

```
is_novf (1), init_call (1), sc (1), rp (1), zr (1), a (3), vr (3)
```

(sites, from the merged-stream line numbers the compiler prints). Two of them sit in `fn main()` of
`entry.quanta`: `stub_call` (declared in the startup-stub `if`, read at the ELF patch ~500 lines later) and
`init_call` (same shape) — hoisting those to function scope and turning the declaration into an assignment
fixed the first two. Regenerate the full list the same way at any time:

```bash
cd /opt/tali/quanta
ulimit -c 0 -v 8000000
# with a compiler built from the patched parse_block:
<patched-qc> compiler/<NEXT>/src/x86/main.quanta /tmp/out 2>&1 | grep "undeclared variable" | sort -u
```

## MEASURED (0.0.236 attempt, reverted): this is a migration, not a version

The one-line patch was applied to a `compiler/0.0.236` tree, the 12 leak-dependent sites in the compiler's own
source were hoisted (54 individual edits, mechanical), and the result was fully built and gated:

| measurement | result |
|---|---|
| self-build of the compiler's own source | **OK** after the hoists |
| semantics | correct: the shadow probe prints `11` where it printed `9977`, i.e. an inner `let` no longer clobbers a parameter |
| fixpoint (3 generations) | `4badeb351ed47212d7797f0c039f3891`, distinct = 1 |
| full gate | **RED** — 819/824 pass, 5 fail, 38 compile failures, `STDLIB` **74/108** |

So `lib/std` and the corpus depend on the leak in far more places than the compiler's own 12: fixing the
language semantics requires migrating the whole tree, and **the hoist is NOT semantics-preserving in general** —
a `let x = f()` inside a loop, hoisted to the function top, initialises once instead of per iteration, so every
site needs a human decision about whether the binding should be per-iteration or per-function. That is why this
was reverted rather than shipped: it is a dedicated migration, not the lever for a version.

Two honest routes, in preference order:
1. **Keep the current semantics and correct the documents** (`SPEC.md:94`, `SYNTAX.md:126-127`) to say a binding
   lives to the end of its enclosing FUNCTION, and add the re-`let` warning — the warning alone would have
   caught A1 at build time, and this costs one version.
2. Do the migration with the hoist tooling as a starting point, but with per-site review of loop-carried
   bindings, and a gate row per migrated module.

## Decision inputs

- `docs/SPEC.md:94` lists a bare `{ … }` block as "(scoping)", and `docs/SYNTAX.md:126-127` says a bare
  `name = expr` "at function-top-level or in a block" introduces a new local binding — the spec leans
  **block-scoped**.
- `docs/SYNTAX.md:400` documents shadowing for `match` arm patterns ("Binds the matched value to a new
  identifier (shadows outer)") — shadowing is a recognised concept, so the question is about its *extent*.
- Cost of the change: the 11 hoists, then the full gate + self-host fixpoint. Risk is concentrated in the
  compiler's own source, not in user programs.
- Cheap non-breaking mitigation available regardless: warn on "re-`let` of an existing binding"
  (a diagnostic, no semantics change) — that alone would have caught A1's trigger at build time.
