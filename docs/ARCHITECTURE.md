# Quanta — SME HANDOFF (read this first when taking over)

Last updated: 2026-08-22. Author: JEEEX.ORG. Status: x86-64 (AArch64 backend planned POST-1.0)
native AOT compiler verified + hardened; multi-mode architecture designed
but only the native AOT backend is built.

## WHAT IS REAL (verified, not claimed)
- `compiler/0.0.68/src/x86/` — multi-file x86-64 Quanta compiler (AArch64 backend planned POST-1.0)
  (main.quanta + helpers/lexer/parse/codegen/emitter/elf/globals/quanta).
  Self-hosts (2-stage: `bin/x86/qc` -> source -> `qc`, byte-identical fixed point).
- `compiler/0.0.68/bin/x86/qc` is the golden compiler; it compiles the 0.0.68
  source to a faithful `qc` (the verified self-host path). See README verification block.
- Security (fail-closed): overflow trap (ud2 -> SIGILL rc=132), bounds trap,
  `unsafe{}` opt-out; MAP_FAILED -> abort rc=1 (NOT SIGSEGV 139, fixed 0.0.49);
  undeclared fn / cyclic struct -> compile error rc=7 (fixed 0.0.48).
- Valgrind-clean: 0 errors on self-compile and all crash-repro programs.
- Grammar: `tree-sitter-quanta` parses ALL 15 compiler modules with 0 errors
  (v0.0.53). Enables CodeRabbit / CI static review.
- Latent-defect caught & fixed (0.0.53): keyword-hash constants H_ENUM/H_MUT/
  H_MOVE had mismatched parens -> wrong lexer hashes for enum/mut/move
  (silent corruption). Now balanced + verified.
- **New (standards work):** `docs/SPEC.md` (language spec, v0.0.53) and
  `docs/SAFETY_MANUAL.md` (ISO 26262-8 / IEC 61508-3 qualification status).
  Quanta is at the documentation + partial-validation stage — NOT yet a
  qualified tool. See SAFETY_MANUAL.md §6 for blockers (formal semantics,
  independent implementation, manual memory model).

## INVARIANTS (never break these)
1. Self-host: `cd compiler/0.0.68/src/x86; SEED=../../../../compiler/0.0.68/bin/x86/qc; $SEED main.quanta qc && ./qc main.quanta qc2` must produce byte-identical qc==qc2 (2-stage fixed point).
2. 105/105 test_suites must pass after any change (plus security 8/8, perf 3/3).
3. No ARM emitter code in the x86-only source (ARM is a SEPARATE future
   backend, built from scratch). The x86 emitter was de-duplicated in 0.0.46
   (the entire emitter had been copy-pasted as two blocks; only the second
   was live — last-definition-wins — and the dead first block was removed).

## VOCABULARY (do not violate)
- "frontend"/"backend" = DOMAIN capability ONLY (web UI vs server/systems).
  The language targets both. NOT compiler stages.
- Compiler stages: core/ scan/ parse/ opt/ codegen/ run/. Never name a
  folder frontend/ holding the lexer. Capability libs live in lib/<domain>/
  (web, sys, ai, chain).

## ARCHITECTURE (the one decision that matters)
ONE IR, N BACKENDS. Front-end + optimizer written once; modes are backends:
  run/interp (Stage 1), codegen/x86_64 (DONE), codegen/aarch64 (Stage 4),
  run/jit (Stage 5), run/wasm (Stage 3), precompile (Stage 2).
The IR (ops/accessors at src/x86/main.quanta ~L120-L150, IRS=40 record)
is the STABILITY BOUNDARY every backend agrees on. See docs/LANGUAGE_DESIGN.md.

## WHERE WE LEFT OFF
- Multi-mode architecture designed; only the x86 AOT backend is built.
- The source is now a MULTI-FILE tree (main.quanta + helpers/lexer/parse/
  codegen/emitter/elf/globals/features.quanta under compiler/0.0.46/src/x86/),
  not the old single file. The modular migration is DONE.
- Interpreter (Stage 1) still NOT implemented.

## HOW TO RESUME
1. Read docs/ARCHITECTURE.md (this file), docs/LANGUAGE_DESIGN.md, docs/SYNTAX.md, docs/FEATURES.md.
2. Re-establish green state: run `bash test_suites/scripts/run_tests.sh` (expect
   105/105 functional + 8/8 security + 3/3 perf, exit 0). Self-host: see INVARIANTS #1.
3. Next concrete task = Stage 1 interpreter. Mirror emit_bltn builtin
   semantics (src/x86/emitter.quanta) in a register VM. Wire
   `--interp` in main() to bypass ci_func/write_elf and run the IR directly.
   Verify identical exit codes vs the AOT path on the 81-suite.

## KNOWN GOTCHAS
- The source is a multi-file tree (main.quanta splits into helpers/lexer/
  parse/codegen/emitter/elf/globals/features.quanta). The Quanta tokenizer is
  hand-rolled; do NOT trust naive brace-counting tools on .quanta files
  (comments/strings confuse them). Compile with the bootstrap binary to truly
  validate braces.
- `emit_bltn` is the builtin x86 emitter; the interpreter must reproduce its
  exact semantics (esp. string layout [base]=len,[base+8..]=bytes; array
  layout mem_alloc [base]=n; GDATA fixed base 0x42200000).
- Self-host timing ~0.6s. Fast already; "make it faster" is not the bottleneck.
