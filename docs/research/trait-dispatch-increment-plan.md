# Increment 0.0.224 — trait methods and dynamic dispatch

> **SUPERSEDED — shipped in `0.0.224` (commit `602bab90`).** The plan below was
> written against a wrong root cause: it assumed the trait metadata chain was
> broken (`imethods` never read, no dispatch by trait). It was not. The four
> tests had one unrelated cause in `rewrite_struct_literals()`, which rewrote
> the impl header's `{` into `(` so `scanimpls()` never recognised the method.
> Fix: one line in `funcscan.quanta`. Gate 813/813, self-host fixed point.
> The gated steps below were never needed and are kept only to record what was
> ruled out. See `compiler/0.0.224/WIP.md` for the real root cause.

## Baseline

    compiler/0.0.223/bin/x86/qc
    size=2978568  md5=ff78dcbbb0cbfb94a1127c7813595f83
    gate 813/817 — 4 compile failures, all trait tests
    self-host fixed point holds
    0.0.222 frozen at the time; the baseline is now 0.0.223

## Correction to the previous record

Earlier I recorded that "no writer of a negative trait encoding into `fn_partype`
exists in the compiler". **That was wrong.** `globals.quanta:849` writes it:

    ptyp = 0 - (ti + 2)      // negative = trait type

and `entry.quanta:770` consumes it:

    if ptyp < 0-1 { w64(vreg_trait + vr*8, (ptyp * -1) - 2) }

Both ends of the encoding exist. The claim came from stale context and I did
not re-read the source before repeating it. Everything below is from the source
as it stands at `6454f037`.

## The real state of the trait machinery

The trait system is not absent. It is **built, wired on both ends, and never
read at the point of use.** Traced link by link:

| Link | Location | Status |
|---|---|---|
| `impl` lexes as `TT_IMPL` | `lexer.quanta` `kt==25` | works |
| trait decls scanned, methods recorded | `funcscan.quanta:466` `scantraits` | works — `tdefs`, `tmethods`, stride 24 consistent with the `mmap` |
| impl blocks scanned | `funcscan.quanta:515` `scanimpls` | works — `idefs`, `imethods` |
| trait-typed param → negative `fn_partype` | `globals.quanta:849` | works |
| negative `fn_partype` → `vreg_trait` tag | `entry.quanta:770` | works |
| **method call on a trait-typed vreg → dispatch** | — | **MISSING** |

That last row is the whole defect. `method.quanta:1699-1707`, the branch taken
when a receiver carries a trait tag, is a stub with a comment admitting it:

    // P9: dyn-trait receiver -> dispatch via impl table. The
    // impl method is registered in the fn table under its own
    // name, so the standard method-call path (findfn by name)
    // already resolves and calls it with selfv prepended as
    // arg 0. The vreg_trait tag marks it as a dyn trait so a
    // real vtable dispatch can replace this later.
    adv(); return parse_method_call(selfv, mnm, ml)

It resolves the method by **name**, not by trait. So with two impls of one trait
it picks whichever `findfn` returns first, and the receiver's actual type is
discarded. And `imethods` — the table that maps (impl, trait-method) → concrete
function index — is written in two places and **read nowhere in the compiler**.
`grep -rn imethods *.quanta` returns two writes (`funcscan.quanta:574,586`), one
allocation (`globals.quanta:378`), zero reads.

That is why dispatch cannot work, and why no parser fix can supply it: the table
that would carry the dispatch is never consulted.

## Two distinct failures, not one

### `trait_min.quanta`, `trait_only.quanta` — parser / function identity

`rc=7` at compile. Root cause chain:

    lexer.quanta       `impl` lexes as TT_IMPL
    parse.quanta       NO TT_IMPL branch exists anywhere in the parser
    entry.quanta:749   tokp = fn_btok(fi) + 1 — assumes fn_btok is the body brace
    funcscan.quanta    fn_btok can be the signature's `)` instead of the body `{`

An impl-contained method's body can therefore begin parsing at the wrong token,
and function identity is unreliable. A bare `impl Struct { ... }` block — the
form `trait_min` uses — is not matched by `scanimpls` at all, which requires the
`Trait for Struct` shape (`funcscan.quanta:520-523`).

Fix: make `fn_btok` the actual body-brace token rather than assuming it, and
give bare `impl` blocks a receiver-tagging path. **Guard:** the body-position
recovery must not rescan forward into a later declaration — that exact mistake
produced `/tmp/c16.bin`, a 4,816-byte binary that allocated 50.7 GB.

### `trait_test.quanta`, `trait_test2.quanta` — missing dispatch

These need a trait-typed receiver to pick the right impl at the call site.
`method.quanta:1706` resolves by name, so they cannot pass regardless of parser
fixes. This is a genuine feature increment, not a bug fix.

## Build order

Each step is gated before the next. Any step that does not improve the gate is
reverted, not carried.

1. **Make `fn_btok` reliable.** Function identity and body-token boundaries,
   without forward-rescanning into another declaration. Gate must stay 813/817
   or improve. Reverting cost is one commit.

2. **Bare `impl` receiver tagging.** A bare `impl Struct { fn m(self) ... }`
   tags `self` with the struct so `self.field` resolves. Gate must not regress.

3. **Consume `imethods` at the call site.** Replace name-based resolution on a
   trait-tagged receiver with: trait tag → trait index → method name → method
   slot → `idefs` lookup for (trait, struct) → concrete fn index from
   `imethods`. This is the step that makes `trait_test`/`trait_test2` possible.

4. **Return type and value path.** `tmethods` records param count but stores
   `0-1` for ret struct (`funcscan.quanta:499`, commented "simplified"). A
   method returning a struct needs that resolved before its result can be
   field-accessed.

Steps 1–2 are expected to move `trait_min`/`trait_only` from compile-fail to
running. Steps 3–4 are what `trait_test`/`trait_test2` need. No step is expected
to fix all four at once, and I will not claim one that does not.

## Verification rules for this increment

- Gate under `systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0`.
  `ulimit -v` and `prlimit` both return rc=1 on this host without taking effect.
- SRC and BIN in lockstep: the committed source must rebuild to the committed
  md5. Verified for 0.0.222 and 0.0.223; it is the check that catches an
  increment shipping a stale binary.
- Every claim in WIP.md must come from a command in the same session.
- A change no test can observe is not evidence of a fix. That is why the
  `imethods` one-past-end edit was excluded from 0.0.223 rather than shipped
  unmeasured.
- If a trait test compiles but returns a wrong value, that is a worse state than
  a compile failure and gets fixed before the increment is committed.

## Not in this increment

- Native inference engine (tokenizer, 30-layer forward pass, short-conv cache,
  KV cache, logits/sampling, generation loop). Still entirely absent; the
  loader is verified, the engine is not.
- `q4k_dot` / `q4k_matvec` emitter builtins — unsafe stubs, deliberately unused.
  `lib/std/matmul_q4k.quanta` is the oracle-verified path.
- Q2_K / Q3_K / IQ decoders — unused by this model. Q4_K is verified separately
  against a Python oracle and is **not** covered by `dequant_diff.py`.