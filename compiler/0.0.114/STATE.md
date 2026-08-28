# Quanta 0.0.114 — Release State

- **Version:** 0.0.114
- **Date:** 2026-08-28
- **Source entry:** `compiler/0.0.114/src/x86/main.quanta` (16 modules)
- **Build seed:** 0.0.113 (`compiler/0.0.113/bin/x86/qc`)
- **Self-host fixpoint:** BYTE-VERIFIED — md5 `637c7c694f04a7579468715c1f0c8b97`.
  The promoted binary compiles its own source to a byte-identical binary
  (verified across multiple independent builds). The self-host chain —
  systemically broken (stage2 SIGSEGV `si_addr=0xfffffffffffffff4`) in
  0.0.109–0.0.113 — is fully restored at 0.0.114.
- **Promoted from:** 0.0.114 (this version; copied from 0.0.113)

## What changed
Lang core: `big` becomes a FIRST-CLASS TYPE KEYWORD (was: library convention).

- **Type keyword:** `big` is context-sensitive (`ktext` ID 62, stays `TT_ID`,
  so `let big = 70000` still works). New `vreg_is_big` tag array (1 = big,
  -1 = not), analogous to `vreg_is_str`.
- **Annotations:** `: big` param annotations recorded in `fn_parbig`;
  `-> big` return annotations detected by `scan_retbig()` (explicit annotation
  supersedes the old return-name heuristic, which missed `return r`). Big tag
  propagates through `let`, reassignment (`q = big_add(q, ONE)`), and call
  results of `-> big` functions.
- **Operator routing:** `+ - * / % == !=` on big operands route to
  `big_add/sub/mul/div/mod/eq` with automatic int→big promotion of the other
  operand. Ordering compares (`< > <= >=`) on big operands are rejected at
  compile time (compile_error kind 6).
- **Call-site promotion:** arguments to `: big` params are auto-promoted
  (int → `big_from_i64`) in a pre-pass that rewrites argstack entries before
  the contiguous `IR_MOV` arg records are emitted (codegen reads args as
  contiguous records; promotion uses `arg_tgt[pk]` for the target param index
  so `self`/named args stay correct). Already-big values are never re-wrapped.
- **Literals:** overflowing decimal literals lex as a single `TT_BIGNUM`
  token (fixed a lexer double-emit that produced `TT_BIGNUM` + a stray
  truncated `TT_NUM`, causing an IR explosion to VREG_CAP). `TT_BIGNUM`
  literals lower through the resolved-callee call convention.
- **println(big):** parse-level rewrite to `big_println` (requires
  `import std/big`).
- **stdlib:** `lib/std/big.quanta` public API fully annotated — `: big` on
  every pointer-taking param, `-> big` on every big-returning function — so
  raw-int args auto-promote and big-returning calls never double-wrap.
  `big_eq` is signed equality (signs must match).

## Tests
- `big_test.quanta` (rc=0): 30-digit add/sub/mul/div/mod against Python
  reference values (a+b, a*b 60-digit, b/a=8, b%a), signed equality via
  `big_eq`, `println(big)` output. Registered in EXPECTED.tsv (147 rows).
- Double-wrap regression probes: direct `big_div`/`big_add` call results
  passed to `: big` params compare correctly (no double-wrap).
- Full gate: 147/147 functional + extern-c/security/performance/valgrind/
  fuzz/differential/generics-negative all GREEN.

## Gate result
- functional : GREEN (147/147)
- extern-c   : GREEN
- security   : GREEN (fail-closed; overflow traps fire as designed)
- performance: GREEN (3/3, baseline 4000ms)
- valgrind   : GREEN (0 errors)
- fuzz       : GREEN (fail-closed on all fuzzed inputs)
- differential: GREEN (120-run optimizer differential + vs-seed consistent)
- generics    : GREEN (negative compile-time checks)
- self-host   : BYTE-VERIFIED (md5 637c7c694f04a7579468715c1f0c8b97;
                promoted binary compiles its own source byte-identically)
