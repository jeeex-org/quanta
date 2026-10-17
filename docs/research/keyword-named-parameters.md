# Keyword-named function parameters: the real cause of the "`closure_call` from an imported module" crash

Status: **FIXED in 0.0.246.** The defect was not in `closure_call` and not in
module boundaries. It is that `funcscan`'s signature scan recorded a parameter
only when its name lexed as `TT_ID`, so any parameter named with a reserved
keyword token (`as`, `type`, `impl`, `in`) was **silently dropped** — the
function lost that parameter, every later parameter was mis-numbered, and a body
reference to the dropped name compiled to 0 (or trapped the compiler with
SIGILL). This file records how the wrong attribution was reached, the
measurements that replaced it, and the fix.

Companion corrections: `docs/research/jit-fused-dot-status.md` and
`tests/lfm2_jit_cc_probe.quanta` still carry the original (incorrect)
attribution — they are historical records and were deliberately not rewritten.

---

## 1. The symptom as reported, and as reproduced

Reported: `qc 0.0.245` miscompiles `closure_call` when it is reached from a
function defined in an IMPORTED module.

* `closure_call` inline in `main` -> works, returns `4700186342854754304`
* the identical call inside a function in an imported module -> **SIGSEGV (139)**
* larger TUs make the **compiler** trap (SIGILL, 132)

Reproduced exactly, from the committed header of `tests/lfm2_jit_cc_probe.quanta`
(written out as a 2-case TU and run under `scripts/quanta_run.sh`):

```
=== A: inline closure_call in main ===
4700186342854754304
=== C: closure_call via imported-module helper ===
Segmentation fault   rc=139
```

## 2. What the emitted code actually says (the module boundary is innocent)

Two single-path binaries were built from the same setup — one calling
`closure_call(tbl, asz, 0)` inline, one calling `jit_f_apply(asz)`. The
`closure_call` byte sequence is **byte-identical** at both sites:

```
main (0x40ab75)                        jit_f_apply in jit_x86_fused (0x40c973)
 48 8b 10      mov (%rax),%rdx          48 8b 10      mov (%rax),%rdx
 4c 8b 50 08   mov 0x8(%rax),%r10       4c 8b 50 08   mov 0x8(%rax),%r10
 4c 8b da      mov %rdx,%r11            4c 8b da      mov %rdx,%r11
 48 8b bd ..   mov -0x60(%rbp),%rdi     48 8b bd ..   mov -0x740(%rbp),%rdi
 48 8b b5 ..   mov -0x68(%rbp),%rsi     48 8b b5 ..   mov -0x748(%rbp),%rsi
 41 ff d3      call *%r11               41 ff d3      call *%r11
```

Same instructions, same operand sources (a home slot each). The difference is
only *which slot*, and what was in it.

gdb at the fault, with a breakpoint on the `call *%r11` in the imported path:

```
at call: rdi=0x7ffff7fbe000 rsi=(nil) rax=0x7ffff7fe6000 r11=0x7ffff7fe7000
0x7ffff7fe7000: mov (%rdi),%r9        <- the emitted kernel's first instruction
```

so the argument *was* delivered there for that run. But a run without the
breakpoint faults with `rdi=(nil)` and `RIP=0x7ffff7fe7000` — a load through 0:

```
Program received signal SIGSEGV
0x00007ffff7fe7000 in ?? ()
rax=0x7ffff7fe6000  rdx=0x7ffff7fe7000  rdi=0x0  rsi=0x0
```

`0x7ffff7fe7000` is the JIT entry (the page after the fnb tuple at
`0x7ffff7fe6000`), and its first instruction dereferences `rdi`. The kernel was
entered with a **null argument pointer**.

## 3. Reduction: it is the parameter NAME, and the module is irrelevant

`jit_f_apply` is declared (in `lib/std/jit_x86_fused.quanta`):

    fn jit_f_apply(as) -> i64 { return closure_call(jf_tbl, as, 0) }

`as` lexes as **`TT_AS`** (the cast operator; `lexer.quanta` maps `kt==41` to
`TT_AS`), not `TT_ID`. Dropping the module/`closure_call`/JIT machinery entirely,
in a **single self-contained file with no imports**:

| program | 0.0.245 result |
|---|---|
| `fn f(x) -> i64 { return x }`, `f(41)` | 41 (correct) |
| `fn f(as) -> i64 { return as }`, `f(41)` | **0** |
| `fn f(impl) -> i64 { return impl }`, `f(41)` | **0** |
| `fn f(in) -> i64 { return in }`, `f(41)` | **0** |
| `fn f(as, b) -> i64 { return b*100+as }`, `f(41,42)` | **41** (expected 4241) |
| `fn f(type) -> i64 { return type }` | **compiler SIGILL rc=132** |

The module boundary dropped out of the picture on the first row: the fault
happened identically **in the top-level module**. It only ever *looked* like a
module bug because `jit_f_apply` — the one library function that calls
`closure_call` — is also the one whose parameter is named `as`.

The fifth row is the most dangerous shape: the dropped parameter **mis-numbers
every parameter after it**, so a call delivers each argument to the wrong slot.
`f(41,42)` returned 41 because `b` had become parameter 0.

The sixth row is the compiler trap. `type` lexes as `TT_TYPE`; with no binding
recorded and no `parse_primary` atom branch for that token, the parser
de-synchronised. **This is the same root cause**, not a second defect. The
reported "SIGILL on larger TUs" does not otherwise reproduce on 0.0.245 at HEAD
(measured: `qc -O tests/lfm2_generate.quanta` rc=0, `qc -O tests/lfm2_jit_mm_test.quanta`
rc=0); the reproducible trigger is a keyword-named parameter, and TU size is
incidental.

### Which keywords exist in the tree as parameter names

A scan of `lib/std`, `tests`, `test_suites/codes` and the compiler source found
these reserved-word parameter names:

    lib/std/jit_x86_fused.quanta:359   as        <- the loader blocker
    lib/std/ast.quanta:48,56,140       type
    lib/std/supply_chain.quanta:370    type
    lib/std/patterns.quanta:35         impl
    lib/std/pattern_library.quanta:36  impl
    lib/std/gguf_bpe.quanta:93,104,105,109   packed   (lexes TT_ID -- unaffected)
    lib/std/config.quanta:178,373,381,387    section  (lexes TT_ID -- unaffected)

`packed` and `section` are context keywords the lexer already remaps to `TT_ID`,
so they were never affected — and they are the in-tree precedent for treating a
reserved word as a usable name.

## 4. The code path

`funcscan.quanta`, signature scan (0.0.245:265):

    if depth==1 && in_default==0 && tk==TT_ID {
        w64(fn_pnames + fn_poff, tokv(k)); …; saw_param=saw_param+1
        …
    }

Only `TT_ID` was accepted, so `as`/`type`/`impl`/`in` were skipped both as
`fn_pnames` entries **and** in `saw_param`, which is what sets the function's
arity and the index of every later parameter (`fn_pcount`). No diagnostic: the
scan built a shorter parameter list and carried on.

The lexer is not at fault and needs no change: its identifier branch ends with
`stok(tokc, ty, sp, l, sc, nl)`, storing the **source offset** `sp` as the token
value for every keyword class too, so `tokv`/`tokln` address these names exactly
like an identifier.

Two consumers then had to agree on it:

1. **`funcscan`** must record the name (arity, indices, named-arg lookup).
2. **`parse_primary`** must resolve the *body reference*. With no atom branch for
   `TT_AS`/`TT_TYPE`/`TT_IMPL`/`TT_IN`, `return as` silently produced 0 (the
   fall-through), and `return type` desynchronised into SIGILL.

## 5. The fix (0.0.246)

* `helpers.quanta`: new `is_param_name_tok(tk)` — `TT_ID`, `TT_AS`, `TT_TYPE`,
  `TT_IMPL`, `TT_IN`.
* `funcscan.quanta`: `tk==TT_ID` -> `is_param_name_tok(tk)`.
* `method.quanta` `parse_primary`: if the cursor is on one of those keyword
  classes **and** `vfind(pval(), plen()) >= 0` (it names a bound parameter/local),
  rewrite the token's type to `TT_ID` in place and fall through to the existing
  identifier path. Rewriting a token in place is already the established
  mechanism (`funcscan` reshapes `fn` signatures that way).

The `vfind` guard is the safety property that makes this a one-site change
instead of a sweep: a keyword token that does **not** name a binding is left
exactly as before, so no existing keyword path changes.

### Explicitly re-verified as unaffected

| construct | 0.0.245 | 0.0.246 |
|---|---|---|
| `let x = 300; (x as u8)` | rc=44 | rc=44 |
| `type MyInt = i64; let v: MyInt = 41` | rc=42 | rc=42 |
| `for x in a[0:3] { … }` | rc=13 | rc=13 |
| full gate | 229/229 + 112/112 | 231/231 + 113/113 |

## 6. Evidence summary

| claim | measurement |
|---|---|
| inline vs imported `closure_call` emit identical code | byte-identical 6-instruction sequences at 0x40ab75 / 0x40c973 |
| the kernel is entered with a null argument pointer | gdb: `rdi=(nil)` at `RIP=0x7ffff7fe7000`, first insn `mov (%rdi),%r9` |
| root cause is the parameter name | `fn f(as) -> i64 { return as }` returns 0 with no import, no JIT, no `closure_call` |
| dropping a parameter shifts later ones | `fn f(as,b) { return b*100+as }`, `f(41,42)` -> 41 |
| the SIGILL is the same root cause | `fn f(type) -> i64 { return type }` -> qc rc=132 |
| the fix closes all three gate rows | `param_kwid_name_test` rc 1->0, `param_kwid_type_test` compile-fail->0, `stdlib_jit_dispatch_test` 139->0 |
| the loader's route works | `jit_f_apply(as)` returns `4700186342854754304`, bit-identical to the inline route |

## 7. Open, unrelated or diagnostic-quality gaps

* **String-keyed brace literals trap the compiler.** `fn f() { return { "a": 1 } }`
  -> SIGILL rc=132 on **both** 0.0.245 and 0.0.246. This is why
  `lib/std/ast.quanta` (which also has `type` parameters) still does not build.
  Separate defect, separate owner; 0.0.246 does not touch it.
* **An unbound keyword token in expression position still traps.** `return type`
  with no binding named `type` reaches `parse_primary` as `TT_TYPE`, is not
  rewritten, and the parser desynchronises — the compiler should emit a located
  error instead. Out of scope here (the fix deliberately does not change any
  keyword's behaviour when it is not a binding), but it is the natural follow-on:
  the same three lines could route to `compile_error` when the token is a keyword
  with no binding.
