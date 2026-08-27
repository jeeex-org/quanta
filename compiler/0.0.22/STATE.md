# Quanta Compiler 0.0.22 — STATE

> Internal status tracker for the compiler build in THIS folder. **Gitignored —
> never committed or pushed.** Deeper SME handoff: `agents/memory/quanta.md`.

## How versioning works (DYNAMIC — do not hard-code literals)
- Version = the **folder name** `compiler/<VER>/`. Never hard-code version literals.
- Promotion: run self-host pipeline (qc_boot→qc_self→qc), gate = 62/62 on gen2
  `qc`, then keep only `qc`, save as `bootstrap/qc-bootstrap-<VER>`, commit,
  scaffold `<NEXT>` with `Status: WIP`.

## Current state
- **Status:** `WIP` (scaffolded from promoted 0.0.21; not yet promoted).
- **Version:** `0.0.22` (this folder).
- **Target:** x86-64 ONLY. ARM64 = future clean-from-scratch stage (not this version).
- **Dev source:** `compiler/0.0.22/src/x86/main.quanta` (single self-hosting file).
- **Bootstrap seed:** `bootstrap/qc-bootstrap-0.0.21` (regenerated from promoted 0.0.21).

## CORE ROADMAP (verified-against-source, 2026-08-13)
> Reality check from source inspection + re-tests THIS session:
> - `#import` — EXISTS as inline-expansion scaffold (line 6773) but BROKEN: 2-file
>   import → "error: call to undeclared function: add". NOT functional.
> - Generics — EXISTS as scaffold (`IR_GENERIC_INST`, monomorph cache, lines 170-272)
>   but BROKEN: `id<T>(x T)` → "wrong argument count for: id". NOT functional.
> - Interpreter — NO backend (`interp_run` absent; IR_DEREF is a codegen op, not an
>   interpreter). NOT landed.
> - Basic type errors — WORK: undeclared fn/var/arity (`compile_error`, line 1212).
> - Optimizer — ON by default (const-fold, DCE, tail-call, loop strength-reduction).

### CORE ROADMAP — 1 FEATURE PER WIP VERSION (fix-forward)
Discipline (user rule, 2026-08-13): **only 1 feature per WIP version.** Each
version: implement ONE feature → run full green gate → if green, PROMOTE
(commit + scaffold next, `Status: WIP`). If a dependency must land first, it is
called out in the roadmap and done in its own version. The minor version number
is just a counter — completing each objective is what matters, not the number.

| Version | Feature (1 only) | Gate |
|---------|------------------|------|
| **0.0.22** | **F0: P0 arity fix** (DONE) — function calls with args now work | 63/63 ✅, fixed point ✅ |
| **0.0.23** | **F1: Fix `#import`** — 2-file import compiles+runs (`#import` currently → "undeclared") | 2-file `#import` test passes |
| **0.0.24** | **F2: Fix generics** — `id<T>(x T)` instantiates (currently → "wrong argument count") | `id(42)` compiles+runs |
| **0.0.25** | **F3: Strengthen type checker** — clear, located type-mismatch errors (rc=1, no crash) | type-error tests give messages |
| **0.0.26** | **F4: Advanced native features** — defer interpreter; focus on native parity first | see survey below |

- **Deferred (NOT in 0.0.22–0.0.26):** interpreter, ARM64, WASM, JIT, pre-compilation, concurrency, full Unicode, macros.
- **Interpreter explicitly deferred per 2026-08-13 directive** — native compiler first.

### LANGUAGE SURVEY — native parity targets (to scope F3–F6+)
> Survey of best-in-class native languages (2026): Rust, Zig, Odin, Go, C++23,
> Carbon, Swift. Goal: identify features Quanta MUST have to be competitive
> as a full-featured native compiler, plus where it can differentiate.

#### 1. Type System & Safety (Rust/Zig/Carbon baseline)
| Feature | Status in Quanta | Priority |
|---------|------------------|----------|
| **Tagged unions / sum types** (Zig `union(Tag)`, Odin `union`, Rust `enum`) | ❌ Missing | P0 — core safety; enables exhaustive matching |
| **Option/Result types** (built-in `Option<T>`, `Result<T,E>`) | ❌ Missing | P0 — error handling without exceptions |
| **Pattern matching with exhaustiveness** | ❌ Missing | P0 — pairs with tagged unions |
| **Memory ownership / borrow checking** (Rust-like) | ⚠️ Partial (basic ownership, mmap/free) | P1 — key differentiator; "secure by default" claim needs it |
| **Lifetimes / borrow regions** | ❌ Missing | P1 — if ownership lands |
| **Algebraic data types / custom enums** | ❌ Missing | P0 — pairs with pattern matching |
| **Traits / interfaces with generics** (Rust traits, Zig `anytype`/`comptime`) | ⚠️ Partial (P9 traits exist but incomplete) | P0 — abstraction mechanism |
| **Null safety / non-nullable by default** | ❌ Unknown | P1 — baseline safety |

#### 2. Memory & Allocation (Zig/Odin baseline)
| Feature | Status | Priority |
|---------|--------|----------|
| **Explicit allocator pattern** (pass allocator everywhere) | ❌ Missing (mmap/free are globals) | P0 — Zig's key design |
| **Custom allocators / arena / pool / stack** | ⚠️ Arena caps exist | P1 — composable memory |
| **Defer / RAII / scope-based cleanup** | ❌ Missing | P0 — `defer` is Zig's killer feature |
| **Stack allocation with escape analysis** | ❌ Missing | P1 — performance |

#### 3. Compile-time & Metaprogramming (Zig/Carbon)
| Feature | Status | Priority |
|---------|--------|----------|
| **Comptime / const-eval** (Zig `comptime`, Carbon `constexpr`) | ❌ Missing | P1 — enables generics without bloat, compile-time validation |
| **Reflection / introspection** (Odin `reflect`, Zig `@TypeOf`) | ❌ Missing | P1 — serialization, generic code |
| **Type-driven codegen** (Zig `comptime` types as values) | ❌ Missing | P2 — advanced |

#### 4. Error Handling (Zig/Rust/Odin)
| Feature | Status | Priority |
|---------|--------|----------|
| **Error unions** (`!T`, `Result<T,E>`) | ❌ Missing | P0 — no exceptions, explicit propagation |
| **Error set inference** (Zig) | ❌ Missing | P1 — ergonomics |
| **Try / catch / defer error handling** | ❌ Missing | P0 |

#### 5. Modularity & Build (Zig/Odin/Go)
| Feature | Status | Priority |
|---------|--------|----------|
| **Package manager / build system** | ⚠️ `#import` flat-global only | P0 — Zig's build.zig is gold standard |
| **C/C++ interop** (headers, linking) | ⚠️ FFI exists (extern "C") | P1 — migration path |
| **Cross-compilation** | ❌ Missing | P1 — Zig's killer feature |

#### 6. Concurrency (Go/Rust/C++20)
| Feature | Status | Priority |
|---------|--------|----------|
| **Async/await or lightweight threads** | ❌ Missing | P2 — post-native parity |
| **Channels / message passing** | ❌ Missing | P2 |
| **Data-race freedom** (Rust Send/Sync) | ❌ Missing | P2 |

#### 7. Developer Experience (Go/Zig)
| Feature | Status | Priority |
|---------|--------|----------|
| **Fast incremental compilation** | ❌ Missing (full recompile) | P1 |
| **LSP / IDE support** | ❌ Missing | P2 |
| **Built-in test / bench / doc** | ⚠️ test_suites exist | P1 |
| **REPL / interpreter** | ❌ Deferred | P3 (explicitly deferred) |

---

### QUANTA ROADMAP REFINEMENT (post-F2)

| Version | Feature (1 per WIP) | Rationale |
|---------|---------------------|-----------|
| **0.0.25** | **F3: Type checker + diagnostics** (already scoped) | Foundation for all safety features |
| **0.0.26** | **F4: Tagged unions + pattern matching** | P0 — enables Option/Result, error handling |
| **0.0.27** | **F5: Option/Result + error unions + try/!** | P0 — error handling without exceptions |
| **0.0.28** | **F6: Explicit allocator pattern + defer** | P0 — Zig-style memory model |
| **0.0.29** | **F7: Comptime / const-eval + reflection** | P1 — metaprogramming, zero-cost generics |
| **0.0.30** | **F8: Package/build system + C interop** | P0 — real projects |
| **0.0.31+** | Concurrency, IDE/LSP, incremental, cross-compile | P2+ |

> **Note:** This survey replaces the deferred "interpreter" slot. Interpreter is
> explicitly deferred per 2026-08-13 directive — native parity comes first.
> The roadmap extends to ~0.0.30 for native parity; each feature = 1 WIP version
> (fix-forward discipline enforced).

---

## Green gate (every change MUST pass)
1. `./bootstrap/qc-bootstrap-0.0.21 compiler/0.0.22/src/x86/main.quanta compiler/0.0.22/bin/x86/qc_boot`
2. `compiler/0.0.22/bin/x86/qc_boot compiler/0.0.22/src/x86/main.quanta compiler/0.0.22/bin/x86/qc_self`
3. `compiler/0.0.22/bin/x86/qc_self compiler/0.0.22/src/x86/main.quanta compiler/0.0.22/bin/x86/qc`
4. `QC=compiler/0.0.22/bin/x86/qc bash test_suites/scripts/run_tests.sh` → 62/62, 0 fail.
- Fail → roll back; never declare done without green.

## What is done (inherited from 0.0.21)
- x86-only self-hosting compiler (byte-identical fixed point)
- Tier-1 optimizer ON by default
- Arena bounds-checks + lexer error reporting
- Secure-by-default (overflow/bounds traps)
- 62/62 test_suites
- Basic semantic errors (undeclared fn/var/arity)
