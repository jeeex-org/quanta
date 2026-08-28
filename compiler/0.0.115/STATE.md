# Quanta 0.0.115 — Release State

- **Version:** 0.0.115
- **Date:** 2026-08-28
- **Source entry:** `compiler/0.0.115/src/x86/main.quanta` (16 modules)
- **Build seed:** 0.0.114 (`compiler/0.0.114/bin/x86/qc`)
- **Self-host fixpoint:** BYTE-VERIFIED — md5 `50857425ec4be97ddf971074a6b66d48`.
  The promoted binary compiles its own source to a byte-identical binary
  (verified stage1==stage2==stage3). The self-host chain — systemically broken
  (stage2 SIGSEGV) in 0.0.109–0.0.113 — remains restored.
- **Promoted from:** 0.0.115 (this version; copied from 0.0.114)

## Security hardening close-off (0.0.115)

0.0.115 is the **AUDIT_ROADMAP close-off** release. All `AUDIT_ROADMAP`
findings are CLOSED (see `docs/AUDIT_ROADMAP.md`):

- Heap fail-closed on OOM: `MAP_FAILED` guards in `mem_alloc`/`mem_realloc`
  (FIX-0.0.1) — `mmap` failure now hard-exits `exit(1)` instead of writing to a
  faulting address.
- `mem_realloc` writes the new block's count header (FIX-0.0.2).
- Free-list null-guards in `mem_free`/`drop` + `vreg_owned` clear on explicit
  free → double-free eliminated (FIX-0.0.3).
- Include-path and source-expansion overflow caps (FIX-0.0.4/5).
- `owned_stk` cap (8192) (FIX-0.0.8); `fstat` pre-check for >16MB source
  (FIX-0.0.9).
- `stack_trace()` frame-context guard (FIX-0.0.7); `rsp()` promoted from PROBE
  to permanent debug builtin (FIX-0.0.11).
- `big_print_dec_mag` heap-overflow fix: allocate exactly `ndig+1` qwords
  instead of a fixed 2048-qword buffer (FIX-0.0.21, real heap-overflow bug for
  any big with >256 decimal digits).
- Stdlib suite wired into the gate as a 10th verification layer (FIX-0.0.15).
- Pointer-builtin posture documented in `docs/SAFETY_MANUAL.md` §3b (FIX-0.0.6).

## What changed
Lang core: `big` becomes a FIRST-CLASS TYPE KEYWORD (was: library convention),
landed in 0.0.114; 0.0.115 hardens the runtime and closes the security audit.

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
