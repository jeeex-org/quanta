# 0.0.236 — WIP · **DO NOT PROMOTE — one gate row regresses (see "Gate")**

**Lever: A6 + A7, one fix — an untyped parameter takes the type of the argument the caller passes.**

## What landed

- `src/x86/funcscan.quanta`: new pass **`scan_call_types()`** (plus helpers `sct_args`, `sct_mark`,
  `sct_param_ev`, `sct_ret_ev`, `sct_nm_eq`), called from `entry.quanta` right after `scan_retstr()`.
- `src/x86/globals.quanta`: four scratch tables for it (`sct_tok`, `sct_fi`, `sct_stk`, `sct_sdp`).

`scan_call_float()` already inferred a float parameter from a call site, but **only from a float
LITERAL**. That leaves the forwarding case dead:

    fn qmult(x) -> f64 { let y = x * (2.0/3.14159...) ... }   // x UNTYPED
    fn reduce(x) -> f64 { ... let nf = qmult(x) ... }         // x is an IDENTIFIER here
    reduce(0.5)                                               // reduces param marked, qmult's not

and that is the whole of A6 — including the "a dead `qmult(0.5)` fixes it" puzzle: that unreachable
call has the literal the old rule needs, and this pass reads the TOKEN stream, so reachability never
enters into it. A7 (string) had **no call-site scan at all**: `fn_parstr` was written only from a
declared `: str` signature (`funcscan.quanta:319`) and from cached-import metadata
(`objfmt.quanta:1252`) — verified by grep, no string analogue existed.

New rule (monotone fixpoint over the token stream, run to a fixed point because a mark made in one
round is the evidence a later call site needs): for every call `name(args)` inside function `g`,
argument `k` carries a type when

1. it contains a float/string literal at argument depth, or
2. it names a parameter of `g` whose `fn_parflt`/`fn_parstr` slot is already set, or
3. it is a call to a function whose `fn_retflt`/`fn_retstr` flag is set,

and then parameter `k` of every top-level function called `name` is marked float/string — under
`scan_call_float`'s existing guard (never overwrite a slot with a declared type) and only when a slot
actually flips, so integer call sites are untouched and the fixpoint terminates.

The enclosing function `g` is resolved with a **brace stack over a body-token-ordered function list**,
not from a name: "this identifier is spelled like some function's float parameter" is not evidence, and
a wrongly-float parameter is the same miscompile class the fix removes (movq over an integer, or
cvtsi2sd over an f64 bit pattern). Method calls (`s.push(x)`) are skipped (a preceding `.`).

## Verification (raw)

| check | 0.0.235 golden | 0.0.236 |
|---|---|---|
| A6 repro `/tmp/g9/iso_B.quanta` | `-4336984033343832063` | **`4602678819172646912`** |
| A7 repro `tests/a7_untyped_str_param_defect.quanta` | `11093937761109393744` / `11093938081109393840` | **`untyped tag: GLOBAL`** / **`untyped lit: TEXT`** |
| `tests/f64_call_order_defect.quanta` (already correct) | `0` then `4602678819172646912` | `0` then `4602678819172646912` |
| gate row `codes/f64_call_order_test.quanta` | compile 0, **run rc=1** | compile 0, **run rc=0** |
| `codes/embedding_test.quanta` (must not regress) | run rc=0 | run rc=0 |
| build of the tree by the previous golden | — | rc=0, 0 errors |
| fixpoint, 3 generations | `7e48d93cfaa822c0eb9bde9565b1cda3` | **`203e0d772ca38e903ad27c921645d10a`** (3/3 identical, = the installed binary) |
| STDLIB suite (108 rows, float-heavy) | GREEN | **GREEN** |

One change fixed both A6 and A7: the string evidence is the same rule on `fn_parstr`/
`vreg_is_str` (which `entry.quanta:893` turns into the parameter's tag at parse time). Measured
directly, an untyped parameter used as a path: `file_open(p, 0)` returned **-2** on 0.0.235 and
**3** on 0.0.236, while `fn p: str` returns 3 on both — i.e. the untyped parameter now behaves
exactly like the annotated one.

## Gate

    QC=compiler/0.0.236/bin/x86/qc bash test_suites/scripts/run_tests.sh   -> rc=1
    === Results: 818/821 pass, 3 fail (incl. 1 compile-fail) ===
      FAIL (compile) recv_loop_test.quanta  rc=14                    <- pre-existing, same on 0.0.235
      FAIL std_code_synthesizer_const_test.quanta (expected rc=0, got rc=135)   <- SIGBUS
      FAIL std_code_synthesizer_const_test.quanta (expected rc=0, got rc=124)   <- timeout
    layers: functional RED (that row); stdlib GREEN; every other layer GREEN

Same-environment baseline, `QC=compiler/0.0.235/bin/x86/qc`, same tree:

    === Results: 820/821 pass, 1 fail (incl. 1 compile-fail) ===   rc=1
      FAIL (compile) recv_loop_test.quanta  rc=14

(The row count is 821 because `EXPECTED.tsv` lists `std_code_synthesizer_const_test.quanta` twice;
`recv_loop_test.quanta` fails to compile on the PRISTINE golden too, so it is not ours. Note the
baseline already exits rc=1 in this environment — the meaningful comparison is the row delta:
**+1 distinct row**, listed twice.)

### The one regressing row is NOT this fix — proven

`scan_call_types` flips exactly two slots for that row (**dumped** with the mark-dump recipe in the
`sct_mark` comment): `synthesize_all` p0 and `register_pattern` p0, both **string**. `synthesize_all`
is entered with the literal `"gap_specs.json"`, so its parameter is now correctly a string and
`file_open` succeeds for the first time — before, it returned -2 and the function returned 0
immediately. The module's now-live code path is broken on its own:

- `lib/std/code_synthesizer.quanta` reads up to 16 MB into `mmap(2097152)` — a 2 MB buffer.
- With that buffer enlarged locally (a one-line experiment, reverted) and the parameter typed
  EXPLICITLY `: str` so that **the pristine 0.0.235 compiler** compiles it, nine runs give
  **rc=0 ×3, rc=124 (timeout) ×2, rc=135 (SIGBUS) ×4**; the 0.0.236 build of the same program gives the
  same set of three outcomes (rc=0 ×3, rc=124 ×5, rc=135 ×2 over nine runs). So the flakiness
  (SIGBUS / timeout / "Generated modules: 0" or "47") is inherent to the module under EITHER compiler,
  and the row was green only because `file_open` rejected the untyped string path.
- The module also writes its output to the hard-coded path `lib/std/…`, so when it does run it drops
  generated files into the source tree (observed: `lib/std/ng` from a gate run — removed).

The gate result above was taken with the enlarged buffer reverted, i.e. the only change in the tree is
the A6+A7 inference.

## Next step before promotion

1. Decide the `std_code_synthesizer_const_test.quanta` row: give `lib/std/code_synthesizer.quanta` a
   memory-safe buffer (2 MB -> `16777216 + 16`) AND a crash-free scan/output path (its parse produces
   garbage triplets, its generated names are truncations), or mark the row known-broken. It has been
   green only because the A6/A7 defect short-circuited it.
2. Promote `tests/a7_untyped_str_param_defect.quanta` into a gate row alongside
   `codes/f64_call_order_test.quanta` (both red-first; the A6 row is not in `EXPECTED.tsv` yet).
3. VERSION is untouched at **0.0.235**; nothing is promoted.
