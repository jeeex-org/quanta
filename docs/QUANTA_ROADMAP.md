# QUANTA ROADMAP — "One Language to Replace Them All"

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
