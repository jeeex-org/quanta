# Quanta — Language Design

Quanta is a programming language engineered from the proven strengths of the
languages that came before it, and built to remove the recurring friction they
carry. It is described here by what it *is* and what it *does*.

*Status note: this is the design target. Quanta's current implementation is
0.0.86 — a self-hosting native compiler (byte-identical fixpoint) with an
intent-level syntax, a primitive layer (syscalls, mmap, file I/O, floats,
closures, generics, big-int), and stdlib seeds for crypto, quantum, linalg, and
math. The properties below are reached incrementally, gate-green before each
promotion. The sequenced plan lives in `docs/ROADMAP.md` and
`docs/QUANTA_GAP_ANALYSIS.md`.*

---

## 1. What Quanta Absorbs

Each strength below is drawn from a language that demonstrated it; each weakness
is a friction Quanta designs out.

- **Fast start (scripting languages).** The common case is terse; the environment
  is invisible. Quanta keeps this — one command, no build file, no venv.
- **Memory safety outcome (ownership/borrow models).** The *safety* is absorbed;
  the *per-line cognitive tax* is not — ownership is inferred where possible and
  only required where the task demands.
- **Fast feedback (interpreted loops).** Edit-run stays sub-second; slow compiles
  and heavy build graphs are avoided.
- **Domain notation (array/matrix languages, SQL, shaders).** Experts are
  dramatically more effective in their own vocabulary. Quanta generalizes this
  via first-class dialects.
- **Verifiability (languages that age well).** Where a machine can check a claim
  cheaply, the language lasts. Quanta maximizes this — the source is a
  machine-readable, verifiable artifact from the first token.
- **Fragile-text failure (text-based languages).** Correctness that lives only in
  strings is unverifiable and drifts. Quanta makes the AST the canonical artifact
  and the compiler a fast, scriptable verifier — checking is a primitive, not an
  afterthought.
- **Packaging/environment pain (manual dependency and venv management).** Quanta
  designs this out: content-addressed, hash-pinned imports; no name-typosquat, no
  dependency sprawl; build is one command.

---

## 2. What Quanta Is

Quanta is a **machine-readable, verifiable artifact from the first token**. The
source is a syntax tree, not text. Whoever writes it gets clear, teaching errors;
whatever processes it operates on a structure it can check. The compiler is the
shared verifier, available after every change, locally and cheaply.

Quanta is **concise**. Programs are short; the surface is small and regular. That
makes the common case fast to write and inexpensive to process at scale.

Quanta is **self-hosting**. The compiler is written in Quanta. The same language
that builds your application compiles itself and is the natural substrate for the
tooling around it — no second language for tooling.

Quanta is **one language across machines**. Native, WASM, GPU, microcontroller,
and cluster from a single source; the runtime adapts, the program does not
change.

Quanta is **dialect-rich**. Physics, music, biology, finance, and cryptography
ship as first-class vocabularies with real notation, desugaring to core forms
anyone can read. Experts write in their discipline; the translation moves from
the writer to the compiler.

---

## 3. What Quanta Does

- **Removes setup as a gate.** First hour is intent, not tooling.
- **Lowers the concept tax.** Types, allocators, and build targets are inferred;
  apparatus is the compiler's job to pursue, not the writer's to supply.
- **Meets experts in their notation.** `laplace(potential)` instead of
  `matrix_multiply(...)`; the discipline's vocabulary is first-class.
- **Teaches as it fails.** Errors explain cause, rule, and fix.
- **Edits without breaking.** Structure is invariant under edit — a change to the
  tree cannot produce a syntactically broken program.
- **Verifies in the loop.** `quanta check` runs after every change; the signal is
  real, not asserted.
- **Scales to large code.** Concise surface and verifiable structure keep
  processing cost and context load low.
- **Secures the execution layer.** Region/ownership memory, bounds, races, and
  side channels are pursued by the compiler; `unsafe` is an explicit, auditable
  escape, not the default path.
- **Enforces domain invariants.** A `secure` dialect refuses variable-time or
  unreduced cryptographic operations; a blockchain dialect rejects replay and
  non-deterministic RNG. The unsafe form cannot be compiled where the dialect
  governs.
- **Keeps docs honest.** Examples are executed as tests; a broken example fails
  the build.

---

## 4. Why It Holds Together

One property drives all of it: **code as a machine-verifiable artifact.** Because
the source is a checkable tree from token one, the writer gets clarity, the
processor gets reliability, the surface stays small, and the compiler stays the
single source of truth. The strengths absorbed from earlier languages — fast
start, safety outcome, fast feedback, domain notation, verifiability — reinforce
each other instead of competing for the writer's attention. The recurring
weaknesses — ceremony, packaging, fragile text, unverifiable claims — are
designed out at the foundation.

Quanta is the language that results.
