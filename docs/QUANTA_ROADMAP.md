# QUANTA ROADMAP — "One Language to Replace Them All"

> **Sync note (2026-08-15):** this is the long-range *vision* document. Concrete
> current status lives in README.md / docs/ARCHITECTURE.md / docs/FEATURES.md.
> As of 0.0.46 the compiler is a multi-file x86 self-hoster (81/81 gate,
> Valgrind-clean); the roadmap below describes the campaign toward 0.1.0+.

> Vision (user, 2026-08-13): *Once people use Quanta, they will never need another
> language again. It can do it all.* Quanta must be **differentiated**, not "just
> another language": built-in **security, quantum resilience (post-quantum
> crypto), blockchain/cryptography, and AI**, borrowing the best from other
> languages and discarding the worst — optimized for simple, fast, secure,
> reliable development.
>
> Discipline: **one feature per WIP version**. Each version self-hosts (boot→self→qc
> fixed point) and passes `test_suites` green before promotion. Packaging/install
> is **LAST** (not required yet); features and differentiation come first.
>
> Capability libraries live in `lib/<domain>/` (web, sys, ai, chain, crypto,
> quantum, secure, db, ui) — never a `frontend/` folder holding the lexer.

## North-star principles
1. **Differentiation over parity.** Features that other languages lack or bolt on
   (post-quantum crypto, on-chain types, in-language AI inference, secure-by-
   default memory) are FIRST-CLASS, not libraries you wire up later.
2. **Security by default.** Bounds + overflow traps already exist (`SIGILL`, 132).
   Extend to: capability-checked I/O, constant-time crypto ops, memory-safe owned
   types, compile-time taint tracking for untrusted input.
3. **Self-sufficient.** `std` is written IN Quanta (not C). Quanta talks to the OS
   via syscalls, not libc. FFI (`extern "C"`) is a narrow, opt-in escape hatch —
   never on Quanta's own critical path.
4. **Borrow the best, discard the worst.** Take Rust's safety story, Go's
   simplicity + concurrency, Zig's low-level control, Python's expressiveness,
   SQL/DB ergonomics, JS's UI reach (via WASM) — without their footguns
   (borrow-checker pain, GC pauses, build complexity, dependency hell).

## Phased plan

### Phase 1 — Foundation: make `std` real (usable primitives)
- **0.0.30** `lib/` module mechanism + core modules (`std/io`, `std/math`,
  `std/str`) in Quanta; `import` resolves `lib/<path>.quanta`. **DONE (`572aa67`, 67/67
  green).** Verified: abs,min,max,pow,clamp,gcd,concat,equals,substr,parse_i64,len.
  (Large results checked via `printi` — `exit()` is 8-bit-truncated by the shell.)
- **0.0.31** Byte-level access builtins (`byte_at`/`byte_set`) + `std/str` real
  ops (`concat`, `substr`, `equals`, `parse_i64`) + `std/fs` file I/O
  (`open`/`read`/`write`/`close` via syscall).
- **0.0.32** `std/collections`: `vec` (dynamic array), `map` (hashmap).
  Foundation for DB + general apps.

### Phase 2 — Differentiation pillars (the "never need another language" part)
- **0.0.33** CODEGEN BUG FIX (builtins flush_all). Promoted `cdff03b`. NOT crypto.
- **0.0.34** `lib/crypto`: SHA-256, HMAC, AES-128, CSPRNG (getrandom). ← **NOW**
  (CSPRNG). Pure-Quanta + syscall entropy.
- **0.0.34** `lib/quantum`: **post-quantum crypto** — Kyber (KEM) + Dilithium
  (signatures) reference impls in Quanta. Quantum-resilient by default.
- **0.0.35** `lib/chain`: blockchain primitives — Merkle tree, signed
  transactions, UTXO/account types, a `Block`/`Chain` model. On-chain-native types.
- **0.0.36** `lib/secure`: capability-checked I/O, secrets handling, constant-
  time compare, sandbox/resource-limit primitives.
- **0.0.37** `lib/ai`: tensor ops + a small in-language inference runtime
  (load GGUF/ONNX-shaped weights, run matmul/attention). Local AI, no Python.

### Phase 3 — App capabilities (make it useful for real products)
- **0.0.38** `std/net`: sockets (`socket`/`bind`/`listen`/`accept`/`recv`/`send`).
- **0.0.39** `std/http`: request parse / response build (on net + str).
- **0.0.40** `std/json`: parse/serialize (on str + map) — data interchange.
- **0.0.41** `std/db`: embedded key-value + simple query store (on map + fs).
  ← your "DB" ask.
- **0.0.42** `std/tui`: terminal UI primitives (raw mode, draw, input).

### Phase 4 — UI + multi-mode reach
- **0.0.43** WebAssembly backend (already a named execution mode) — UI in browser.
- **0.0.44** `std/ui`: retained-widget DOM/canvas layer (on WASM + tui).

### Phase 5 — Polish + parity (original end-goal, deferred)
- **0.0.45+** Review top languages, close parity gaps (async/await, trait maturity,
  tooling/LSP), then optimize (perf, code size).

### Phase 6 — LAST: packaging/install (only when features exist to ship)
- Self-hosted `quanta` package/build CLI (own driver; `--emit-obj`/multi-TU
  already present). `extern "C"` FFI as opt-in escape hatch.

## Why this order
- `std` first: nothing is installable or useful without a library ecosystem; it is
  also the independence move (Quanta std in Quanta, not libc).
- Differentiation pillars (crypto/quantum/chain/AI/secure) come BEFORE generic app
  plumbing because they are the reason Quanta exists — they are the moat.
- Apps/DB/UI ride on the pillars + collections + I/O.
- Packaging is literally last: you don't package an empty shelf.

## Honest status (as of 0.0.29, promoted `fc21967`)
- Shipped: F0 arity, F1 `#import` (single-file), F2 generics, F3 diagnostics,
  F4 tagged unions + match, F5 Option/Result + match, F6 defer + allocator,
  F7 `const` comptime. 66/66 test_suites green.
- Existing engine hooks usable by pillars: SIMD vec128 (P11), `mem_alloc`/`free`,
  syscall emission, ELF object/executable + `--emit-obj`/`--no-start` (P5.1).
- Deferred gaps: F4 match block-arms, F5 `?` propagation, F7 const = literals only.
- `lib/` directory does NOT exist yet — 0.0.30 creates it.

---

## Standards & Safety track (added 2026-08-17, runs parallel to pillars)

Quanta's ISO/IEC 26262-8 / IEC 61508-3 qualification work (see
docs/SAFETY_MANUAL.md, docs/SECURITY_TOOLING.md, docs/MEMORY_SAFETY_ARGUMENT.md).
Version assignments below follow the established convention:
0.0.43–0.0.50 debt window (CLOSED), 0.0.51+ P2 builtins, 0.0.61+ P3
language, **0.0.72 = tooling**, 1.0 = stdlib resumes.

- **0.0.51–0.0.55** grammar + bug-fix window (DONE: all 15 modules parse 0
  errors; keyword-hash paren bug fixed).
- **0.0.53** memory-safety hardening (CODE_CAP/DAT_CAP guards) + fail-closed
  fuzzer (20K iters, 0 crashes) + differential cross-check vs bootstrap seed.
  Status: 🟡 hardened, not proven (runtime traps, no compile-time proof).
- **0.0.72+ (tooling phase, BEFORE 0.1.0)** — **#2 INDEPENDENT
  IMPLEMENTATION**:
  - **0.0.72** ARM64 (AArch64) backend (Stage 4 from LANGUAGE_DESIGN.md):
    a SECOND, independently-written emitter over the shared IR. This is the
    real "independent implementation" route for ISO 26262-8 §11 / IEC 61508-3
    Annex F — two separate emitters that must agree.
  - **0.0.73** x86↔ARM64 differential test harness: compile the same program
    on both backends, assert identical exit codes / behavior. Extends
    tools/diff_test/diff_qc.py (currently current-vs-seed). This closes the
    weak-evidence gap from 0.0.53 (seed is same-lineage; ARM64 is
    genuinely independent).
  - (dependent) once a C/LLVM emit path or second backend exists, build `qc`
    under ASan+UBSan+MSan and require 0 errors — unlocks sanitizer-clean
    confirmation of the memory-safety argument (MEMORY_SAFETY_ARGUMENT.md §6).
- **1.0** stdlib resumes (per convention); memory safety target = Stage-6
  borrow checking (compile-time guarantee) to move #1 from 🟡 to ✅.

Why 0.0.72+ and not earlier: the ARM64 backend is a tooling/backend
capability (the 0.0.72 phase), and it is the prerequisite for genuine
independent cross-checking. It must land BEFORE 0.1.0 (the stdlib
resumption point) so that qualification evidence exists before the
language is declared 1.0-ready.

