# Quanta ROADMAP — consolidated single source of truth

> **Last updated: 2026-08-22. Current compiler: 0.0.64** (x86-64 ELF emitter,
> multi-file tree, Valgrind-clean, self-host `fp=YES`). ARM64 (AArch64) backend
> is DEFERRED POST-1.0 (see #2 schedule below); the working compiler is x86-64 only.
>
> Version sequence: each feature lands in its own directory. 0.0.55 = P2
> builtins + grammar/bug-fix window; **0.0.56 = simplified surface** (optional
> `fn`/`let`/`return`, `${}`/`$[]` sigils); **0.0.57 = `$$(cmd)` external
> command substitution** (built on 0.0.56); **0.0.61 = float literals**
> (parse + print); **0.0.62 = float literals fully consumable by float builtins**
> (f2i/fadd/fsub/fmul/fdiv read float args correctly).
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
- **0.0.57** `$$(cmd)` external-command substitution (P2 builtin; raw-syscall OS
  capability, **no libc**). `unsafe`-gated. `$$(str)` → `/bin/sh -c str` (bash-style
  convenience); `$$(arr)` → direct `execve` (no shell — injection-safe, the
  better-than-libc form). Returns `CmdResult{stdout, stderr, status}`; capture grown
  via `mem_alloc`/`realloc` (no fixed cap). Reuses the existing `syscall()` builtin
  (fork 57 / execve 59 / pipe 22 / wait4 61 / dup2 33).

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
| SIMPLE-SURFACE | 0.0.56 | **Simplified syntax landed**: `fn` keyword optional (bare `name(){}` works everywhere, `init()`/`main()` bare OK), `let` optional (bare `name = expr` = local/global), `return` optional (last-expr auto-returns), condition parens optional, `${name}` global / `$[]` local explicit sigils (bare + inside-string interpolation). Goal: bash-like, extremely simple surface. Docs (README/SYNTAX/SPEC) + test_suites + security script synced. |
| P2 builtins | 0.0.55–0.0.60 | float cmp ✅(0.0.55), proc/env ✅(0.0.55), stdin ✅(0.0.55), fs meta ✅(0.0.55 — path-string remap fixed), string ops, math ✅(sqrt/floor/ceil/abs; sin/cos/tan/pow/log/min/max TODO), atomics, net, introspection ✅(abort/debugbreak), random ✅(getrandom), **`$$(cmd)` external-command substitution (0.0.57)** — `unsafe`-gated runtime `fork`/`execve`/`pipe`/`wait4` via the raw `syscall()` builtin (no libc); `$$(str)`→`/bin/sh -c`, `$$(arr)`→direct `execve` (no shell, injection-safe). Returns `CmdResult{stdout,stderr,status}`. |
| P3 language | 0.0.61–0.0.71 | **float literals ✅(0.0.61)**, **float-arg-to-builtin ✅(0.0.62: f2i/fadd/fsub/fmul/fdiv read float vregs correctly)**, **user enums ✅(0.0.63: qualified+bare variant resolution, explicit tags, match)**, **modules ✅(0.0.64: mod Name { fn ... } + Mod.fn() qualified calls)**; remaining: tuples, generics, traits, real char/byte/string/bool, ref/mut/move, op-overload, closure literals, and/or/not/true/false/global |
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

### Current status (0.0.63)

Shipped + verified (x86-64 only; ARM64 deferred POST-1.0): self-host
fixed-point; fail-closed memory model (overflow/bounds→SIGILL 132, MAP_FAILED→rc=1,
undeclared/cyclic→rc=7); grammar 0 errors on all 15 modules; Valgrind-clean;
differential vs seed. Standards docs: SPEC/SAFETY_MANUAL/SECURITY_TOOLING/
MEMORY_SAFETY_ARGUMENT.

P2 builtins landed through 0.0.57 (gate green, 91/91): float comparisons
(`feq/flt/fgt/fle/fge/fisnan/fisinf`), float math (`sqrt/floor/ceil/abs`),
float arith (`fadd/fsub/fmul/fdiv`), process/env (`getpid/getppid/arg_count/environ`;
`getenv` is a stub returning 0), stdin (`getc`), random (`getrandom`),
introspection (`abort`/`debugbreak`). Simplified surface: `fn`/`let`/`return`
optional, no-parens conditions, `${name}`/`$[]` global/local sigils.

**0.0.61** float literals: `3.14`/`-0.5`/`123.456` parse and `println(3.14)`
prints `3.140000`.
**0.0.62** float-arg fix: the float builtins (`f2i`, `fadd`, `fsub`, `fmul`,
`fdiv`) now read float-literal / float-vreg arguments correctly (was a known gap
in 0.0.61). Verified: `f2i(3.14)`→3, `fadd(1.5,2.5)`→4, `fmul(2.5,4.0)`→10,
`fdiv(10.0,4.0)`→2, `fsub(5.0,2.0)`→3; int args still work (`fadd(3,4)`→7).
**0.0.63** user enums: `enum Name { A, B, C }` and explicit tags
(`enum Pri { Low=1, Mid=5, High=9 }`); qualified (`Color.Red`) and bare (`Green`)
variant resolution; both usable in `match` arms (integer-tag comparison). Variants
are heap-allocated tagged values (Rust-style sum types) — use `match` for value
comparison, not `==`. Gate: 93/93 functional, 8/8 security, 3/3 performance.
**0.0.64** modules: `mod Name { fn ... }` registers functions with `Name.fn` names;
qualified calls `Mod.fn()` resolve via a module registry. Nested modules
supported. Basic trait/struct/impl compatibility verified. Gate: 94/94 functional,
8/8 security, 3/3 performance.

Known gap: `getenv` is a stub; string ops (concat via `..` and `${}`/`$[]`
interpolation) work. See FEATURES.md §I.

