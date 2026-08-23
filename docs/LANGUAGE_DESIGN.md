# Quanta — Language Design & Roadmap

## Vision (from brief)
A single language for AI, blockchain, web, and systems work that runs on
almost any device, in many execution modes:
  - Interpreter   (like Python)        — fast edit/run, no compile step
  - JIT           (like Java)           — warm-up then near-native
  - Pre-compile   (like `go run`)       — compile-to-temp then exec
  - Native AOT    (like Rust/C/Go)      — standalone binary
  - WASM          (browser + edge)      — portable sandbox
Target **domains**: backend (services/systems), frontend (web UI), AI,
blockchain, embedded.

## VOCABULARY (read first — avoids confusion)
- "frontend" / "backend" = DOMAIN CAPABILITY ONLY:
    frontend = web UI (the JS/HTML niche)
    backend  = server / systems (the Rust/C niche)
  Quanta targets BOTH. That is a property of the language, not the compiler.
- Compiler STAGES are NOT called frontend/backend. They are:
    core/   (lexer, token, arena, bootstrap primitives)
    scan/   (keyword/decl scanners)
    parse/  (parser, expr, stmt, AST->IR)
    opt/    (IR optimizer)
    codegen/ (native x86-64 / ARM64 ELF emit)
    run/    (interpreter VM, JIT, WASM)
  So you will NEVER see a folder named frontend/ holding the lexer. That was
  a naming mistake; the corrected tree is below.
- Capability (domain) libraries live in lib/<domain>/.

## Hard truth (scope)
"Faster than Rust/C", "JIT beating V8/HotSpot", and "more secure than all
languages" are multi-year, team-scale efforts. This doc is the honest
architecture + a STAGED plan. Each stage is independently verifiable.

## Core architectural decision: ONE IR, N BACKENDS
The front-end (lexer -> parser -> IR) and the Tier-1 optimizer are written
ONCE. Every execution mode is a backend over the same IR:

    source.quanta
        -> core/scan/parse   (exists, verified)
        -> IR                (exists: ~40 ops, const-fold, DCE, TCE, loop-SR)
        -> opt/              (exists, ON by default)
        |
        +-- run/interp.quanta      [Stage 1]  register VM over IR
        +-- codegen/x86_64.quanta  [DONE]      emits ELF directly
        +-- codegen/aarch64.quanta [Stage 4]   clean backend (from scratch)
        +-- run/jit.quanta         [Stage 5]   IR -> x86 at runtime
        +-- run/wasm.quanta        [Stage 3]   IR -> wasm
        +-- precompile (go run)    [Stage 2]   compile to temp + exec

Because the IR and optimizer are shared, a correctness/security fix benefits
every mode at once. This is the only sane way to support 5 modes.

## IR contract (the stability boundary)
All backends MUST agree on IR semantics. Current ops: CONST, MOV, ADD, SUB,
MUL, DIV, MOD, NEG, NOT, BNOT, AND, OR, BAND, BOR, BXOR, EQ, NE, LT, GT,
LE, GE, SHL, SHR, LOADG, STOREG, LOAD, STORE, CALL, RET, LABEL, JMP, BR,
PARAM, STR, FREE, ASM, FFI_CALL, plus float ops. Security gates (overflow
trap, bounds trap) are IR-level properties, so every backend inherits them.

## Builtin contract (single source of truth)
emit_bltn (codegen/x86_64) currently hardcodes x86 per builtin. The BEHAVIOR
of each builtin must be the contract; each backend implements HOW. When the
interpreter lands, its builtins must reproduce emit_bltn semantics exactly so
both backends pass the 62-suite with identical exit codes. Builtins: exit,
free, i2f/f2i/fadd/fsub/fmul/fdiv, vec_*, mem_alloc, mmap, mem_load/
mem_store(+8), file_*, print/printi/println/newline/printsp/prints,
udiv/umod/ult/ugt/ulte/ugte, mk_any, len, u8/u32/u64 casts, str, push/pop,
argc/argv.

## Memory-safety posture (the "more secure" claim)
Current: secure-by-default via runtime traps (overflow -> SIGILL rc=132,
OOB array -> SIGILL), opt-out via `unsafe {}`. "Fail-secure", not "prove-
safe". Staged hardening:
  - done:     traps + emit-arena bounds checks (commit 8571fda)
  - Stage 6:  IR-level borrow checking (unique/borrow per vreg)
  - Stage 7:  optional managed GC mode for web/AI domains
  Real "more secure than C/Rust" needs Stage 6+. Until then we are "as safe
  as Rust's unsafe-default + traps", already better than C.

## RECOMMENDED FILE STRUCTURE (concern-oriented; backends split per TARGET)
    compiler/<ver>/src/
      main.quanta                 # thin driver: arg parse + phase orchestration
      core/      lexer tokens arenas bootstrap
      scan/      keyword/decl scanners
      parse/     parser expr stmt ast_to_ir
      ir/        ir contract (ops, layout, accessors) — STABILITY BOUNDARY
      opt/       optimizer driver + passes
      codegen/   common helpers + x86_64 (done) + aarch64 (Stage 4)
      run/       interp (Stage 1) + jit (Stage 5) + wasm (Stage 3)
      lib/       web/ sys/ ai/ chain/  (DOMAIN capability, not compiler stages)
    docs/        ARCHITECTURE.md (SME handoff), LANGUAGE.md, SYNTAX.md
  NOTE: no folder is named "frontend" or "backend". Domain libs are under
  lib/<domain>. The compiler now lives as a MULTI-FILE tree at
  `compiler/0.0.73/src/x86/` (main.quanta + helpers/lexer/parse/codegen/
  emitter/elf/globals/features.quanta) — the modular migration is DONE.

## Staged roadmap (effort = rough engineer-months)
  Stage 1  Interpreter VM mode (--interp)         ~1-2   [NEXT]
  Stage 2  `go run`-style precompile              ~0.5
  Stage 3  WASM backend                           ~2-3
  Stage 4  ARM64 backend (clean, from scratch)   ~2-3
  Stage 5  JIT (func-at-a-time + trace)          ~4-6
  Stage 6  IR-level borrow checking               ~3-4
  Stage 7  Managed GC mode + std libs (AI/web)    ~6-12
  Stage 8  Blockchain/web/AI stdlib + package mgr ~12+
Each stage gates on: recompile + 2-stage self-host (byte-identical fixed point) + 110/110 tests
(existing gate: functional 93 + security 8 + perf 3),
plus new tests for the mode. Green state is the invariant.
