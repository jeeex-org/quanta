# Quanta — SME HANDOFF (read this first when taking over)

Last updated: 2026-08-13. Author: Hermes agent session. Status: x86-only
compiler verified + hardened; multi-mode architecture designed but only the
native AOT backend is built.

## WHAT IS REAL (verified, not claimed)
- `compiler/0.0.21/src/x86/main.quanta` — 7,097-line SINGLE-FILE x86-only
  Quanta compiler. Self-hosts (compiles its own source). Passes 62/62.
- bootstrap/qc-bootstrap-0.0.20 AND qc-bootstrap-0.0.21 are byte-identical
  x86-only binaries (the seed for self-hosting).
- Security: overflow trap (ud2 -> SIGILL rc=132), bounds trap, `unsafe{}`
  opt-out. All emit arenas bounds-checked (commit 8571fda). Lexer reports
  unterminated-string / invalid-char errors instead of silent exit.
- 62-test regression gate: `bash test_suites/scripts/run_tests.sh`
  -> "62/62 pass, 0 fail" and harness exit 0.

## INVARIANTS (never break these)
1. Self-host: `./compiler/0.0.21/bin/x86/qc compiler/0.0.21/src/x86/main.quanta OUT`
   must exit 0.
2. 62/62 test_suites must pass after any change.
3. No ARM emitter code in the x86-only source (ARM is a SEPARATE future
   backend, built from scratch). Past stripping attempts of 0.0.20 FAILED
   (brace imbalance). The current file was built by: copy 0.0.20 verbatim,
   delete ARM backend lines 5894-7114 + cset 7116-7126, hand-fix target_arch
   branches + IR_FFI_CALL + a_idx_trap_emit. See prior session notes.

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
- Just designed the multi-mode architecture and the file-structure plan.
- Did NOT yet implement the interpreter (Stage 1). The user redirected to
  settle file structure / vocabulary first.
- Open decision: whether to (a) keep the 7,097-line single file and add an
  `interp_run()` to it (fastest, self-host-safe), or (b) migrate to the
  modular tree via #import first. The modular tree is cleaner for human
  reviewers but is a refactor that must preserve self-host + 62/62.

## HOW TO RESUME
1. Read docs/ARCHITECTURE.md (this file), docs/LANGUAGE_DESIGN.md, docs/SYNTAX.md.
2. Re-establish green state: run the self-host + 62/62 gate above. If red,
   `git log` to the last green commit (8571fda) and diff.
3. Next concrete task = Stage 1 interpreter. Mirror emit_bltn builtin
   semantics (src/x86/main.quanta ~L3936-L4460) in a register VM. Wire
   `--interp` in main() to bypass ci_func/write_elf and run the IR directly.
   Verify identical exit codes vs the AOT path on the 62-suite.

## KNOWN GOTCHAS
- The single file uses a hand-rolled tokenizer/brace model; do NOT trust
  naive brace-counting tools (comments/strings confuse them). Compile with
  the bootstrap binary to truly validate braces.
- `emit_bltn` is the builtin x86 emitter; the interpreter must reproduce its
  exact semantics (esp. string layout [base]=len,[base+8..]=bytes; array
  layout mem_alloc [base]=n; GDATA fixed base 0x42200000).
- Self-host timing ~0.6s. Fast already; "make it faster" is not the bottleneck.
