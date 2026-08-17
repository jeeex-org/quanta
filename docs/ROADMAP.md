# Quanta ROADMAP — consolidated single source of truth

> **Last updated: 2026-08-17. Current compiler: 0.0.53** (x86-64 + AArch64
> ELF emitters, multi-file tree, Valgrind-clean, self-host `fp=YES`).
>
> This document consolidates what was previously spread across the stale
> `ROADMAP.md` (removed — claimed current=0.0.46), `QUANTA_ROADMAP.md`
> (vision), `FEATURES.md` (build order), and `LANGUAGE_DESIGN.md` (stages).
> Feature-by-feature status → `FEATURES.md`; language design →
> `LANGUAGE_DESIGN.md`; safety/standards → `SAFETY_MANUAL.md`,
> `SECURITY_TOOLING.md`, `MEMORY_SAFETY_ARGUMENT.md`, `SPEC.md`.

Vision (from the brief): *Once people use Quanta, they will never need
another language again. It can do it all.* Quanta must be **differentiated**,
not "just another language": built-in **security, quantum resilience
(post-quantum crypto), blockchain/cryptography, and AI**, borrowing the best
from other languages and discarding the worst — optimized for simple, fast,
secure,
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
  simplicity + concurrency, Zig's low-level control, and high-level
  expressiveness — without their footguns
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
  (load GGUF/ONNX-shaped weights, run matmul/attention). Local AI, no external
  language runtime.

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

---

## Standards & Safety track (added 2026-08-17, runs parallel to pillars)

Quanta's ISO/IEC 26262-8 / IEC 61508-3 qualification work (see
docs/SAFETY_MANUAL.md, docs/SECURITY_TOOLING.md, docs/MEMORY_SAFETY_ARGUMENT.md).
This file is now the SINGLE consolidated roadmap (the old stale
`ROADMAP.md` was removed 2026-08-17; its source-derived completeness audit
lives in docs/FEATURES.md).

### Build order to 1.0 (single source of truth)

Convention: one feature per WIP version; each self-hosts (3-stage) and
passes the gate green before promotion. Version numbers are MUTABLE — the
SEQUENCING is the contract, not the literal numbers.

| Phase | Versions | Scope |
|-------|----------|-------|
| Debt window | 0.0.43–0.0.50 | Core correctness (aliasing, `?` propagation, MAP_FAILED guard, cyclic-struct reject). **CLOSED.** |
| Grammar + bug-fix | 0.0.51–0.0.55 | tree-sitter grammar (done 0.0.53), residual compiler bugs. **0.0.53 shipped.** |
| P2 builtins | 0.0.55–0.0.60 | float cmp, proc/env, stdin, fs meta, string ops, math, atomics, net, introspection, random |
| P3 language | 0.0.61–0.0.71 | float literals, user enums, tuples, generics, traits, modules, real char/byte/string/bool, ref/mut/move, op-overload, closure literals, and/or/not/true/false/global |
| **P4 tooling** | **0.0.72** | **Quanta-native code-writing tool** (edit Quanta source reliably without external scripting — the user's stated goal) |
| **1.0** | 1.0.0 | Core + builtins complete → std/lib resumes; borrow-checking target for #1 green |

**0.0.72 is RESERVED for the code-writing tool.** Nothing else takes it.

### #1 / #2 standards status

| Point | Status |
|-------|--------|
| #5 Grammar clean | ✅ 0.0.53 (all 15 modules 0 errors) |
| #3 Formal spec | ✅ SPEC.md |
| #4 Safety manual + process | ✅ SAFETY_MANUAL.md |
| #1 Memory/UB safety | 🟡 hardened (fail-closed, Valgrind-clean, fuzz-proven); not compile-time-proven |
| #2 Independent implementation | 🟡 differential vs seed (0.0.53); full POST-1.0 when ARM64 backend lands |

**#2 schedule (ARM64 DEFERRED POST-1.0 — not before):**
Per debt-first discipline, a second backend must NOT start while x86 core +
builtins still have open items (float literals, generics, traits, real
allocator, etc. — see FEATURES.md audit). The ARM64 backend lands only
AFTER 1.0 core completion.
- **POST-1.0** ARM64 (AArch64) backend (LANGUAGE_DESIGN.md Stage 4): a SECOND,
  independently-written emitter over the shared IR — the real ISO 26262-8
  §11 independent-implementation route. (Does NOT take 0.0.72.)
- **POST-1.0** x86↔ARM64 differential harness: compile same program on both
  backends, assert identical exit codes. Extends tools/diff_test/diff_qc.py
  (currently current-vs-seed, weak evidence — seed is same lineage). This is
  what closes #2 for real.
- (dependent) once a 2nd backend/C path exists, build `qc` under
  ASan+UBSan+MSan, require 0 errors → sanitizer-clean confirmation of the
  memory-safety argument.
- **1.0** Stage-6 borrow checking (compile-time memory safety) → moves #1 to ✅.

Why post-1.0: the ARM64 backend is a new backend; shipping it while x86 debt
remains would violate the debt-first rule and split correctness effort.
Qualification evidence is gathered AFTER the core is complete, not before.

### Current status (0.0.53)

Shipped + verified: x86-64 + AArch64 ELF emitters, self-host fixed-point;
fail-closed memory model (overflow/bounds→SIGILL 132, MAP_FAILED→rc=1,
undeclared/cyclic→rc=7); grammar 0 errors on all 15 modules; keyword-hash
paren bug fixed; fail-closed fuzzer (20K iters, 0 crashes); differential
vs seed (5/5 parity); Valgrind-clean. Standards docs: SPEC/SAFETY_MANUAL/
SECURITY_TOOLING/MEMORY_SAFETY_ARGUMENT.

