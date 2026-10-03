# Struct return types and struct literals: what is fixed, what is not

Found 0.0.222 while trying to make `lib/std/native_inference.quanta` compile. It
declares `fn gguf_load_model(path: str) -> *GGUFModel` and builds a dozen
structs in helper functions, and it had never compiled — exit 16, no diagnostic.

`tests/test_struct_return.quanta` is the regression gate for the fixed parts.

## Fixed

### 1. `-> StructName {` was read as a struct literal

`rewrite_struct_literals()` rewrites `Name { f: v }` into `Name(v)` so the parser
sees a constructor call. A function's return type is `-> StructName {`, which is
byte-identical in shape. The rewrite fired on the return type, turned `-> P {`
into `-> P(`, and consumed the function body — the compiler then core-dumped on
every `fn f() -> SomeStruct`.

It needed a *declared* struct to match, which is why `-> Q` with `Q` undefined
compiled fine and `-> P` with `P` declared did not.

The guard skips an identifier preceded by the `->` arrow, scanning back over any
run of `*` or `&` so `-> P`, `-> *P`, `-> **P` and `-> &P` are all covered. (The
first attempt handled only the two-token form and left `-> **P` broken.)

### 2. The token compaction invalidated recorded token indices

The rewrite shifts the tail of the token stream down by `gap`. Three consequences,
all needed:

- the scan position stayed inside the region that had just shifted and walked
  past the new token count, reading stale slots;
- every token index recorded *before* the rewrite was stale — the per-function
  body index (`fns + i*FNS + 16`, `sfn`'s `bt`) and the default-argument token
  ranges (`fn_defargs`). `shift_tok_indexes()` subtracts `gap` from every stored
  index greater than the rewrite point. Note slot **24** is `co`, a code offset
  that the cache path overwrites, not the token index; the first version shifted
  it and corrupted every cached function;
- nested literals need more than one pass. `Q { p0: P { f0: 3 } }` — compacting
  the outer copies the inner across verbatim, braces and field name intact, and
  the scan resumes past it, so the inner is never rewritten. The pass is bounded
  at 4 iterations.

Symptom of 2 before the fix: `fn mk() { let p = P { a: 1 } } fn main() {
println(1) }` core-dumped, while either half alone compiled.

### 3. A declared `-> StructName` return type did not set `fn_retstruct`

`scan_retstructs()` only looked for `return StructName(` in a function body. A
function that *declared* its return type and then returned a local —
`fn mk() -> P { let p = P { f0: 3 }  return p }` — left the flag at −1.
`parse_call_impl()` reads it to tag the caller's result vreg, so the tag was
missing.

`fn_rettype_name`/`fn_rettype_len` hold the token *after* `->`. For `-> *P` that
token is `*`, so a pointer return does not match — and does not need to: a
pointer is a raw address and its fields go through an explicit deref.

### 4. `.field` on a call result had no path

`parse_postfix_expr()` handled `[...]` only. `parse_primary`'s `.`-handling
resolves its receiver by *name* (`vfind`/`gfind`), and a call result has no
name, so `mk().f0` parsed `f0` as a bare identifier: "undeclared variable: f0"
followed by a core dump. `parse_dot_chain()` now applies `.field` repeatedly to a
vreg that is already in hand.

## Still broken, verified

### A. A struct-typed field read off a call result core-dumps the compiler

```quanta
struct A { a0: i64 }
struct B { b0: A }
fn mk() -> B { return B { b0: A { a0: 4 } } }
fn main() { println(mk().b0.a0) return 0 }   // core dump
```

One level works (`mk().b0`), and the same chain on a local works
(`b.b0.a0` prints 4). So the first link resolves and the second does not.

Ruled out by direct test: the `sfldtyp` tag being unpopulated (the local chain
reads the same table and works); the recursion in `parse_postfix_expr` re-running
the `[` loop (splitting the chain into its own `parse_dot_chain` changed
nothing); and the arg counter being rewound by a nested call (`argsp` save and
restore around each argument expression — see below — was needed but is not
sufficient).

Not yet localised to a line. The next thing to instrument is the second entry
into `parse_dot_chain`, where `out`'s `vreg_struct` tag is written before the
recursive call that consumes it.

### B. A scalar field read off a call result gives 0 in a non-first argument

```quanta
fn two(a, b) { println(b) }
two(mk().f0, 99)   // prints 99  -- correct
two(99, mk().f0)   // prints 0   -- wrong; mk().f0 is 3
```

Compiles, runs, and returns the wrong number. `let x = mk().f0` then
`println(x)` prints the correct value, and `println(mk().f0)` prints the correct
value, so it is specific to the argument-collecting path with a preceding
argument.

`check 51` in an earlier draft of the test asserted this and failed, which is how
it was confirmed; the assertion was removed so the test is a clean gate for the
fixed parts.

### C. A bad `import` fails silently

```quanta
import std/mem    // no such module, anywhere, and never in git history
```

exits 16 with **no output at all**. That is why `native_inference.quanta`
"compiled" with no complaint until the line was removed by hand, and it is why
this file sat broken without anyone noticing. Not a struct defect, but it is the
reason a real one survived.

## Not a defect

- `pow`, `str_eq`, `mem_load4`, `mem_store4` all exist as builtins. `q4_1`,
  `scale_min`, `rms` and `scales` are struct fields or comment text.
- `sizeof` exists.
- Nested and triple-nested struct literals work, including the field values.
- Field assignment through a call result works (`let p = mk() p.f0 = 9` → 9).
## 0.0.222 follow-up: the `lstyped` runaway scan (FIXED)

**Symptom.** `struct P { f1: i64 }` followed anywhere earlier in the file by a
`let` and later by any function with TWO OR MORE parameters failed to compile:

    struct P { f1: i64 }
    fn a() -> i64 { let p = P { f1: 1 } return p.f1 }
    fn b(x: i64, y: i64) -> i64 { return x+y }

    line 4: error: call to undeclared function: f1

**Root cause.** `parse_let` looks ahead to decide whether the declaration is a
comma-separated BINDING LIST (`let a: i64, b: i64 = 1, 2`). The scan walked the
token array from the current cursor looking for a depth-0 comma, and stopped only
on a newline (token value 10) or a `;` (59). The lexer emits NEITHER: newlines
are discarded during tokenisation. The scan therefore ran on past the brace that
closes the enclosing block, into the next function, and found the depth-0 comma
in `fn b(x: i64, y: i64)`. It set `lstyped = 1`, so a plain `let p = P ( 1 )`
took the multi-binding branch -- which propagates only string and big tags and
never `vreg_struct`. The binding lost its struct type, so the following `p.f1`
found no struct on the base vreg, fell through to method-call resolution, and
reported a field name as an undeclared function.

The same run-on scan is what made the failure depend on a LATER function: no
comma anywhere in the token stream means `lstyped` stays 0 and the single-binding
path (which does propagate `vreg_struct`) is taken.

**Fix.** `compiler/0.0.222/src/x86/parse.quanta` -- the lookahead is now bounded
structurally instead of lexically:

* a closing brace encountered at depth 0 ends the block the `let` lives in
* depth dropping below 0 means the scan left the enclosing construct
* `;` and the 64-step cap still terminate it

## 0.0.222: other fixes in this batch

* `parse_primary`'s struct-constructor argument loop is driven by the DECLARED
  FIELD COUNT (`sdefs[si*64+16]`), not by commas. The literal rewriter compacts
  `S { a: 1 b: 2 }` to `S(1 2)`, and the old loop stopped at the first non-comma
  token, parsing one field and leaving the rest in the stream.
* `nv()` and the startup loop now initialise EVERY per-vreg tag
  (`vreg_struct`, `vreg_is_str`, `vreg_str_arr`, `vreg_is_big`) across the full
  `VREG_CAP = 400000` table. The startup loop had covered only the first 8192
  entries of a 400000-entry mmap table; the remainder read as 0, which is a
  VALID struct index, so an uninitialised vreg silently claimed struct 0.

## OPEN (not yet fixed)

1. `mk().b0.a0` -- a chained field read on a call result still core-dumps the
   COMPILER (not the compiled program). `mk().b0` alone compiles and runs;
   `let x = mk(); x.b0.a0` compiles and prints 4 correctly.
2. `two(99, mk().f0)` -- a call result in a NON-FIRST argument position evaluates
   to 0. `two(mk().f0, 99)` prints 99 correctly, and `two(99, 5)` prints 5, so
   the first argument is unaffected.
