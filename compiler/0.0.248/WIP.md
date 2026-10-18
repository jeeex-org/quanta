# 0.0.246 — WIP · **LEVER: keyword-named function parameters (the `closure_call` "imported module" miscompile, correctly located)**

```
0.0.245 golden  md5 cbdd5c6f02fb763a46e173fc1efe68e6   (frozen baseline, untouched)
0.0.246 gen1    md5 094020ff498e993d4888c41965584fe4   (0.0.245 golden compiling the edited source)
0.0.246 fixed   md5 094020ff498e993d4888c41965584fe4   (gen1==gen2==gen3==gen4 -- fixpoint from gen1)
```

Three files changed, everything else the 0.0.245 snapshot copied verbatim:

| file | change |
|---|---|
| `src/x86/helpers.quanta` | new `is_param_name_tok(tk)` — which token classes may carry a parameter NAME |
| `src/x86/funcscan.quanta` | the signature scan calls it instead of `tk==TT_ID` |
| `src/x86/method.quanta` | `parse_primary` resolves a keyword token that names a bound param/local |

The lever is a **one-predicate widening plus one token rewrite**. Nothing in the
emitter, the register allocator, or the IR was touched.

---

## 1. The defect, and why the handed-down diagnosis was wrong

The brief this version answers was: *"`qc` miscompiles `closure_call` when it is
reached from a function defined in an IMPORTED module — SIGSEGV at runtime;
compiler SIGILL on larger TUs."* The observation is real and reproduces exactly.
**The attribution is not.** `closure_call` codegen is correct; the module
boundary is incidental.

Measured: the byte sequence `closure_call` emits is **identical** at both sites.
Inline in `main` (file offset 0x40ab75) and in the imported module's
`jit_f_apply` (0x40c973):

```
mov (%rax),%rdx         48 8b 10
mov 0x8(%rax),%r10      4c 8b 50 08
mov %rdx,%r11           4c 8b da
mov -0x60(%rbp),%rdi    <- arg0
mov -0x68(%rbp),%rsi    <- arg1
call *%r11              41 ff d3
```

The fault is that **`rdi` was 0 when the kernel was entered**: gdb at the fault
reports `rax=0x7ffff7fe6000 rdi=(nil)`, RIP `0x7ffff7fe7000` = the JIT entry, whose
first instruction is `mov (%rdi),%r9` — a load through 0. In the working inline
case the same slot held the argument-area pointer.

The pointer was never delivered because of the parameter NAME. `jit_f_apply` is
declared `fn jit_f_apply(as) -> i64`, and `as` lexes as `TT_AS` (the cast
operator), not `TT_ID`. `funcscan`'s signature scan recorded a parameter only
`if … tk==TT_ID`, so **`as` was silently dropped** — `jit_f_apply` was registered
with ZERO parameters, no prologue store was emitted for the incoming `rdi`, and
the body reference `as` (a `TT_AS` token, which `parse_primary` has no atom
branch for) compiled to the constant 0.

The module boundary looked causal only because `jit_f_apply` happens to live in
an imported module. **It is not necessary**: the identical failure occurs in the
top-level module with no import at all. Nor is it specific to `closure_call`:

```
fn f(as)  -> i64 { return as }           f(41)     -> 0     (module-independent)
fn f(type)-> i64 { return type }         compiler SIGILL rc=132
fn f(as, b) -> i64 { return b*100+as }   f(41,42)  -> 41    (every later param shifts)
```

The last row is the dangerous one: dropping a parameter **mis-numbers every
parameter after it**, so each argument is delivered to the wrong slot with no
diagnostic at all.

### The "SIGILL on larger TUs" is the same root cause, not a second defect

`fn f(type) -> i64 { return type }` traps the compiler (rc=132) on 0.0.245. In
the body, `type` is a `TT_TYPE` token; with no parameter binding recorded and no
atom branch for it, the parser desynchronised. Nothing about TU size is involved
— the reported `qc -O tests/lfm2_generate.quanta` SIGILL does **not** reproduce
on 0.0.245 at this HEAD (measured: `qc -O tests/lfm2_generate.quanta` rc=0,
`qc -O tests/lfm2_jit_mm_test.quanta` rc=0); the reproducible trigger is the
keyword-named parameter reference, and it is one defect with two faces (wrong
code, or a compiler trap).

## 2. The fix

1. **`is_param_name_tok(tk)`** (helpers.quanta): `TT_ID`, plus `TT_AS`, `TT_TYPE`,
   `TT_IMPL`, `TT_IN`. The lexer already stores the **source offset** as the token
   value for every one of these (`stok(tokc, ty, sp, l, sc, nl)` — value = `sp`),
   so `tokv`/`tokln` name them exactly like an identifier; the scan only ever
   refused them on the token *type*. Those four are the reserved words that occur
   as parameter names in this tree (`as` in `jit_x86_fused`, `type` in `ast` and
   `supply_chain`, `impl` in `patterns`/`pattern_library`).
2. **`funcscan.quanta`**: the scan's `tk==TT_ID` becomes `is_param_name_tok(tk)`,
   so such a parameter is recorded, counted, and index-numbered like any other.
3. **`method.quanta` `parse_primary`**: if the current token is one of those
   keyword classes AND `vfind(pval(), plen()) >= 0` — i.e. it names a bound
   parameter or local — rewrite the token's type to `TT_ID` in place and fall
   through, so the existing identifier path (`vfind`/`gfind`/fn-value/field-index-
   method postfix) handles it exactly as a plain name. Rewriting a token in place
   is what `funcscan` already does to reshape `fn` signatures.

The `vfind(...) >= 0` guard is what keeps every existing keyword path intact: a
keyword token that is NOT a bound name is left untouched. Verified explicitly —
`(x as u8)` still truncates (300 -> rc 44), `type MyInt = i64` still declares
(rc 42), `for x in a[0:3]` yields byte-identical behaviour under 0.0.245 and
0.0.246 (both rc=13).

## 3. Verification

| check | result |
|---|---|
| functional gate (`QC=./compiler/0.0.246/bin/x86/qc`, ulimit -v 8000000) | **231/231 pass, 0 fail, 0 compile-fail**, exit 0 (229 baseline + 2 new rows) |
| STDLIB | **113/113 GREEN** (112 baseline + 1 new row) |
| stages | **24/24 GREEN**, no RED, GATE_EXIT=0 |
| self-hosting | gen1 `094020ff` -> gen2 `094020ff` -> gen3 `094020ff` -> gen4 `094020ff` (fixpoint from gen1, byte-stable through gen4; 2 distinct binaries) |
| source≡binary | editing a comment and rebuilding reproduced `094020ff…` byte-for-byte, so the lockstep claim survives the last edit |
| verify-release.sh (pre-promotion, VERSION=0.0.245) | **14 passed / 0 failed**, incl. 0.0.245 bit-for-bit baseline rebuild and the seed-chain fixed point |
| 0.0.245 golden untouched | md5 still `cbdd5c6f02fb763a46e173fc1efe68e6` |
| new gate rows | **3** — see §5 |

## 4. What is now UNBLOCKED, and what is not

**`jit_f_setup()` / `jit_f_ready()` / `jit_f_apply(as)` now work when called from
an imported module.** `stdlib_jit_dispatch_test` dispatches the fused Q4_K kernel
through `jit_f_apply` — the shape the loader needs, a call below `main` inside a
library module — and gets bit-identical output to the inline route
(`4700186342854754304`). The `closure_call` dispatch route is therefore usable,
and the BLOCKED status the loader recorded against those three functions is no
longer accurate.

Not here, and named so it is not read as done:

* **The loader wiring itself** (`lib/std/jit_x86_fused`'s BLOCKED note, and
  `lfm2_mm`'s dispatch) is a different unit's scope — `lib/std/**` was not touched.
* **The misdiagnosis in the historical record.** `docs/research/jit-fused-dot-status.md`
  and `tests/lfm2_jit_cc_probe.quanta`'s header both attribute the fault to the
  module boundary and to `closure_call`. They are historical records and were left
  as written; the correction is a NEW research file, not a rewrite.
* **A separate, still-open defect**: the string-keyed brace literal
  `{ "k": v }` traps the compiler with SIGILL (rc=132) on **both** 0.0.245 and
  0.0.246 (minimal case `fn f() { return { "a": 1 } }`). That is why
  `lib/std/ast.quanta` — which also uses a `type` parameter — still does not
  build. It is a different fault with a different owner.
* Writing a keyword-named parameter is now accepted, not diagnosed. An **unbound**
  keyword token in expression position (e.g. `return type` with no such binding)
  still traps the compiler rather than producing a located error; that
  diagnostic-quality gap is unchanged by this version and recorded in the
  research file.

## 5. Red-first (measured on 0.0.245, then re-run on 0.0.246)

| row | 0.0.245 | 0.0.246 |
|---|---|---|
| `param_kwid_name_test.quanta` (`as`/`impl`/`in` params + the shifted-parameter case) | compiles, **rc=1** (wrong values: `f(41,42)` -> 41) | **rc=0** |
| `param_kwid_type_test.quanta` (`type` param, compiler trap) | **COMPILE-FAIL, qc SIGILL rc=132**, no binary | compiles, **rc=0** |
| `stdlib_jit_dispatch_test.quanta` (JIT kernel via `jit_f_apply` in the imported module, vs the inline route) | compiles, **rc=139** (SIGSEGV) | **rc=0** (`vc == va == 4700186342854754304`) |

Rows and their sources land in ONE commit.
