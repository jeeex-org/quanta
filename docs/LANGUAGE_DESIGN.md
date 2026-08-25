# Quanta — Language Design

Quanta is a programming language engineered to be secure, fast, and flexible,
with a simple syntax that is easy to learn and remember. Its source is a
machine-verifiable artifact from the first token, so the same program is clear to
write, inexpensive to process, and safe to run.

*Status note: this is the design target. Quanta's current implementation is
0.0.86 — a self-hosting native compiler (byte-identical fixpoint) with an
intent-level syntax, a primitive layer (syscalls, mmap, file I/O, floats,
closures, generics, big-int), and stdlib seeds for crypto, quantum, linalg, and
math. The properties below are reached incrementally, gate-green before each
promotion. The sequenced plan lives in `docs/ROADMAP.md` and
`docs/QUANTA_GAP_ANALYSIS.md`.*

---

## 1. What Quanta Is

- **A verifiable artifact.** The source is a syntax tree, not text. Structure is
  invariant under edit — a change cannot produce a syntactically broken program.
  The compiler is a fast, local verifier available after every change.
- **Concise.** The surface is small and regular; programs are short. The common
  case is terse and the environment is invisible — one command, no build file,
  no venv.
- **Self-hosting.** The compiler is written in Quanta. The same language that
  builds an application compiles itself and is the substrate for the tooling
  around it.
- **One language across machines.** Native, WASM, GPU, microcontroller, and
  cluster from a single source; the runtime adapts, the program does not change.
- **Dialect-rich.** Physics, music, biology, finance, and cryptography ship as
  first-class vocabularies with real notation, desugaring to core forms anyone
  can read.
- **Memory-safe by construction.** Region and ownership memory, bounds, races,
  and side channels are handled by the compiler; `unsafe` is an explicit,
  auditable escape, not the default path.

---

## 2. What Quanta Does

- **Removes setup as a gate.** The first hour is spent expressing intent, not
  fighting tooling.
- **Lowers the concept tax.** Types, allocators, and build targets are inferred;
  apparatus is pursued by the compiler, not supplied by the writer.
- **Meets experts in their notation.** `laplace(potential)` instead of
  `matrix_multiply(...)`; the discipline's vocabulary is first-class.
- **Teaches as it fails.** Errors explain cause, rule, and fix.
- **Edits without breaking.** Structure is invariant under edit.
- **Verifies in the loop.** `quanta check` runs after every change; the signal is
  real, not asserted.
- **Scales to large code.** A concise surface and verifiable structure keep
  processing cost and context load low.
- **Secures the execution layer.** Memory, bounds, races, and side channels are
  pursued by the compiler; `unsafe` is explicit and auditable.
- **Enforces domain invariants.** A `secure` dialect refuses variable-time or
  unreduced cryptographic operations; a blockchain dialect rejects replay and
  non-deterministic RNG. The unsafe form cannot be compiled where the dialect
  governs.
- **Keeps docs honest.** Examples are executed as tests; a broken example fails
  the build.

---

## 3. Why It Holds Together

One property drives all of it: **code as a machine-verifiable artifact.** Because
the source is a checkable tree from token one, the writer gets clarity, the
processor gets reliability, the surface stays small, and the compiler stays the
single source of truth. The strengths reinforce each other instead of competing
for attention, and the recurring friction of traditional toolchains — ceremony,
packaging, fragile text, unverifiable claims — is designed out at the foundation.

Quanta is the language that results.
