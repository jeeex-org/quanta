# Quanta — Language Design

Quanta is a programming language whose design goal is that safety should not
depend on the programmer's expertise. A program written by anyone — expert or
novice, precise or vague — is intended to compile to machine code that is
memory-safe, bounds-checked, race-free, and, in security-critical domains, free
of the side-channel and invariant violations that make naive code dangerous.

This document specifies what Quanta is and how it pursues that goal. It is grounded
in what is technically achievable, not aspiration. **No software can guarantee
safety; Quanta is designed to achieve it to the greatest extent the state of the
art allows, and is explicit about what it does not achieve.**

---

## 1. The Problem Quanta Addresses

Every mainstream language was designed for experts. Its safety depends on the
expert writing correct types, correct bounds, correct ownership, correct
cryptographic constants. Safety was *outsourced to the user's skill*.

Vibe coding makes this acute. The human is vague; an LLM guesses the code; and
the safety that was the expert's job is now *also* guessed. The result is a
security nightmare — not because the model is bad, but because the language was
never safe without an expert driving it.

**Quanta inverts the premise.** Safety is not a property the programmer supplies.
It is a property the *compiler endeavors to enforce* when lowering to machine
code. Therefore vibe coding on Quanta is *intended* to be far safer than elsewhere
— not because the human became careful, but because the substrate is built to
enforce safety.

> Vibe coding is a nightmare on languages designed for expertise. On Quanta it is
> *designed* to be safe, because Quanta pursues safety by construction rather than
> relying on the programmer.

---

## 2. What Can Be Abstracted

The safety substrate can be substantially abstracted away from the writer. These
are solved or well-understood problems in programming-language engineering;
Quanta applies them so the human rarely confronts them:

- **Memory.** Manual `alloc`/`free` is replaced by region inference. The compiler
  *aims* to prove when memory is allocated and released; use-after-free and leaks
  are *intended* to be structurally prevented in normal code.
- **Bounds & overflow.** Index arithmetic and integer overflow are handled by the
  compiler — proven where possible, checked where not. The writer never writes a
  bounds check by hand.
- **Ownership.** Aliasing and double-free are tracked by the compiler. The writer
  does not annotate lifetimes; the system *endeavors to enforce* them where the
  task demands.
- **Concurrency.** Threads and shared state are replaced by structured `parallel`
  blocks the compiler *works to prove* cannot leak or race.
- **Domain invariants.** Cryptographic and blockchain rules are encoded in
  dialects the compiler enforces — constant-time execution, correct modular
  reduction, no replay, deterministic RNG — so a writer cannot easily emit a
  variable-time cipher or an unreduced field operation.
- **Build & supply chain.** No Makefiles; content-addressed, hash-pinned imports
  *mitigate* name-typosquatting and dependency hijack by construction.

What remains for the human is *intent* — what the program should do. Everything
that makes intent *safe to run* is the compiler's responsibility to pursue.

---

## 3. What Cannot Be Abstracted (Honest Limits)

- **Intent is the human's.** The compiler cannot decide what your program should
  do. It can only endeavor to make whatever you wrote *safe to execute*. A Quanta
  program is *designed to be* safe; it is not automatically *correct*.
- **Functional and application security is not assured.** Quanta pursues memory,
  type, concurrency, and side-channel safety. It does **not** assure your
  algorithm is right, your authentication is sound, your sessions are controlled,
  or your authorization rules are complete. A Quanta program with no login check
  is memory-safe and *still wide open*. Application security — auth, sessions,
  authorization, input-validation against business rules — remains the human's
  design responsibility.
- **Raw access is a deliberate escape.** Some code — a device driver, a hot inner
  loop — needs `unsafe`. That is an auditable opt-in, not a leak of unsafety into
  the default path.

These limits are why Quanta is trustworthy as a *design goal*, not why it is weak:
it pursues the things that are *provably achievable in principle*, and is explicit
about the rest. **Quanta makes no warranty, express or implied, of safety,
security, or correctness.**

---

## 4. The Security Objective

Quanta's objective is stated precisely:

> **Any program, regardless of who wrote it or how vaguely, is intended to lower
> to machine code that is memory-safe, bounds-checked, race-free, and — within a
> security dialect — invariant-preserving. Residual insecurity is possible and may
> be reached through the explicit, auditable `unsafe` escape or through compiler
> defect.**

This objective is what makes non-expert and AI-generated code *safer* on Quanta
than on languages that outsource safety to the user. It is an engineering aim,
not a guarantee.

---

## 5. Language Surface

The syntax is minimal and intent-first. No boilerplate earns the right to print;
the top of a file is a program.

```
# Complete, runnable.
println "Hello, world"
```

Indentation defines structure; the lexer rejects mixed tabs/spaces at parse time.
Side effects are explicit via verb-like builtins (`println`, `write`, `send`) so
pure computation is visibly distinct from action.

The human writes at one level — intent. The compiler descends the precision ladder
(inferring types, checking bounds, scheduling targets, tracking ownership) on the
human's behalf. The writer never climbs it.

---

## 6. Domain Dialects Enforce Invariants

Safety in hard domains is not a suggestion; it is the dialect's rule.

- **Blockchain.** No replay, deterministic RNG, correct modular arithmetic,
  verified Merkle construction. A transaction violating these is *rejected* by the
  dialect where the enforcement is sound.
- **Post-quantum cryptography.** Constant-time execution, no secret-dependent
  branches, correct lattice/field arithmetic. A variable-time or unreduced
  operation is a compile error in the `secure` dialect where enforceable.

The human writes `state |= round_key` and it *means* the safe thing, because the
dialect is built to refuse the unsafe thing. Precision is set by the domain, not
the writer's caution.

---

## 7. One Language, Every Machine

```
quanta build --target native
quanta build --target wasm
quanta build --target gpu
quanta build --target mcu
quanta build --target cluster
```

The program is unchanged; the runtime adapts — region allocator for native,
static allocator for MCU, sandbox for WASM, distributed runtime for cluster.
The safety objective is pursued across all targets; the safety substrate is
portable.

---

## 8. Tooling

- **No build files.** Content-addressed modules; hash-pinned imports.
- **The compiler is the tutor.** Errors explain the cause and the fix.
- **AI-native.** The AST is the source of truth; machine edits operate on the
  verified tree. This is what makes AI-generated (vibe) code *safer* to integrate
  — the model edits a structure the compiler then re-checks.
- **Docs are code.** Examples are executed as tests; a broken example fails the
  build.

---

## 9. Current State

Quanta does not yet implement all of this; that is by design, not accident. It
is built incrementally, gate-green before promotion. The current state (0.0.86)
and the sequenced plan live in `docs/ROADMAP.md` and
`docs/QUANTA_GAP_ANALYSIS.md`.

Already real: a self-hosting native compiler with a byte-identical fixpoint; an
intent-level syntax; a primitive layer (syscalls, mmap, file I/O, floats,
closures, generics, big-int); and differentiating stdlib seeds (`crypto`,
`quantum`, `linalg`, `math`). The safety substrate — region/ownership memory,
bounds/overflow checking, multi-backend codegen, dialect-invariant enforcement,
package management — is the remaining architectural work.

The direction is fixed: **safety is the compiler's job to pursue. The human
supplies intent; Quanta endeavors to supply correctness of execution — without
warranty.**
