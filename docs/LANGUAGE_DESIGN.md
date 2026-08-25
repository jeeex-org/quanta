# Quanta — Language Design (Research-Grounded)

*Revision basis: how programs are learned and consumed, and the documented
strengths and weaknesses of existing languages — studied so Quanta can absorb the
strengths and avoid the weaknesses. Cross-checked against Quanta's actual state
(self-hosting compiler 0.0.86; single x86 backend; untyped; 117-test gate; no
package manager; no dialects). Research drawn from established knowledge of PL
design, programming-education research, and 2024–2025 coding-agent behavior.*

No language can guarantee safety or correctness. Quanta is designed to *pursue*
specific, achievable properties, and to be explicit about what it does not
achieve.

---

## 1. What the Evidence Says

### 1.1 How programs are learned and used
- **The barrier is ceremony, not logic.** Education research (Ko & Myers;
  Guzdial) consistently shows novices lose most time to *syntax errors* and
  *environment setup*, not to algorithmic thinking. The machine's scaffolding —
  not the problem — is what blocks them.
- **Every required concept is a tax.** Types, ownership models, build configs:
  each is paid by everyone, every time, even when the task doesn't need it.
- **Experts think in their own notation.** A biologist, a quant, a musician
  already have precise notation. Forcing them through general-purpose syntax is
  translation overhead they should not pay.

**Strength to absorb:** languages that make the common case terse and the
environment invisible (scripting languages' fast start).
**Weakness to avoid:** languages that require apparatus the task doesn't need
(manual memory, build files, type ceremony).

### 1.2 How code is consumed by automated tooling
- **Context exhaustion.** Automated tooling degrades on large codebases/files;
  it loses structure. Retrieval helps but is lossy.
- **Token cost and latency.** Every file read and retry burns budget. Verbose
  sources are expensive to operate in.
- **Fragile string edits.** Tooling edits raw text; a one-character slip breaks
  compilation silently; the tool cannot see the structure.
- **Verification blindness.** Tooling asserts code works without running/testing
  it; hallucinated APIs are common.
- **No semantic anchor.** Treating code as strings means refactors drift and
  types are guessed.

**Strength to absorb:** languages with small, regular, parseable surfaces that
tooling can manipulate reliably.
**Weakness to avoid:** languages where correctness is textual and unverifiable
without a heavy external toolchain.

### 1.3 Strengths and weaknesses observed in existing languages
- **Memory safety done well** (ownership/borrow models) is a real strength —
  Quanta absorbs the *safety outcome* but should avoid the *per-line cognitive
  tax* that model imposes.
- **Packaging that "just works"** is rare; dependency and environment management
  is a recurring weakness Quanta should design out from the start.
- **Fast feedback** (interpreted edit-run loops) is a strength Quanta keeps;
  **slow compiles / heavy build graphs** are a weakness to avoid.
- **Domain-specific notation** (array/matrix languages, SQL, shaders) shows
  experts are dramatically more effective in their own vocabulary — a strength
  Quanta generalizes via dialects.
- **Verifiability** is the through-line: the languages that age best are those
  where a machine can check a claim cheaply. That is the property to maximize.

---

## 2. Quanta: A Verifiable Artifact From the First Token

> **Quanta is a machine-readable, verifiable artifact from the first token. The
> compiler is the shared verifier — for the novice, the expert, and the machine
> consuming the code.** Both the person writing it and the tooling processing it
> operate on something that can be *checked*, not guessed.

This single design decision resolves the weaknesses above for every consumer at
once:

| Observed weakness | Quanta's response |
|---|---|
| Fragile text edits | Source is an AST; edits target the verified tree, not text. |
| Verification blindness | `quanta check` runs cheaply after every edit; real signal, not assertion. |
| Token/budget cost | Concise surface → fewer tokens per program. |
| Ceremony tax | No required types/build config; apparatus inferred. |
| Packaging/environment pain | Content-addressed, hash-pinned modules; one command, no venv. |
| Memory unsafety | Region/ownership pursued at compile; `unsafe` is explicit, auditable. |
| Domain translation overhead | First-class dialects let experts write their notation. |

Quanta self-hosts — the compiler *is* Quanta. The same language that writes an
app also compiles itself. (Verified this session: 0.0.86 has a byte-identical
self-host fixpoint.)

---

## 3. How Quanta Helps the Person Writing It

1. **Setup is not a gate.** One command, no build file, no venv. The first hour
   is spent expressing intent, not fighting tooling.
2. **Lower concept tax.** Types, allocators, build targets are inferred by the
   compiler. The writer meets the machine at intent level; the apparatus is the
   compiler's job to pursue.
3. **Meets experts in their notation.** Dialects let a domain expert write
   `laplace(potential)` instead of `matrix_multiply(...)`. Translation overhead
   moves from writer to compiler.
4. **Teaches as it fails.** Compile errors explain cause, rule, and fix — failure
   becomes learning, not a cryptic abort.
5. **One language, every machine.** Native, WASM, GPU, MCU, cluster from one
   source.

---

## 4. How Quanta Helps the Tooling That Processes It

1. **AST-native source.** The canonical artifact is the syntax tree, not text. An
   edit to the tree cannot produce a syntactically broken program; structure is
   invariant under edit. This removes the largest source of automated errors.
2. **Cheap verification in the loop.** `quanta check` is fast and local; the
   tooling verifies after *every* change instead of asserting success.
3. **Smaller programs, lower cost.** A concise surface means fewer tokens per
   feature, lower latency, lower bill — a dominant advantage at scale.
4. **Scoped generation via dialects.** Work can be constrained to a dialect's
   grammar — a small, safe generation surface, fewer hallucinated APIs.
5. **Self-hosted tooling.** Tooling is written in the same language it processes;
   no second toolchain to load.

---

## 5. Beyond the Status Quo — Resolutions to Named Weaknesses

Each resolves a specific observed weakness, not a dream feature.

- **Packaging/environment pain:** content-addressed, hash-pinned imports. No
  name-typosquatting, no dependency sprawl, no venv. Build = one command.
- **Build-system hostility:** no separate build system; dependencies resolved by
  content hash.
- **Memory unsafety:** region inference pursued at compile; `unsafe` is explicit.
- **Per-line cognitive tax (borrow models):** ownership inferred where possible,
  required only where the task demands.
- **Verification blindness:** the compiler is a fast, scriptable verifier;
  checking is a primitive.
- **Translation overhead:** dialects make the discipline's notation first-class.
- **Docs/code drift:** examples executed as tests; a broken example fails build.

---

## 6. Honest Limits

- **No guarantee.** Quanta pursues these properties; it warrants none. Compiler
  defects, proof assumptions, and dialect holes exist.
- **Application security is the writer's.** Auth, sessions, authorization, tenant
  isolation for public services remain design responsibilities. A service with no
  login is, like any language's, exposed once public. The real failure mode for
  generated public code is here — the application layer — not the memory layer.
- **Intent is the writer's.** The compiler cannot decide what a program should
  do; it can only pursue making it safe to execute.
- **Raw access is a deliberate escape.** Drivers and hot loops may need `unsafe`.
- **Current state (0.0.86, verified):** single x86 backend; untyped (type
  inference/checking not yet implemented); no package manager; no dialects; 117
  gated tests; self-hosting with byte-identical fixpoint. The properties above
  are the *design target*, reached incrementally — most are not yet implemented.

---

## 7. Positioning

Quanta is engineered so the artifact it produces is **checkable from the first
token** — by whoever writes it, via clear errors; by an expert, via dialects; and
by the tooling that processes it, via a verifiable AST and a fast checker. That
single property — *code as a machine-verifiable artifact* — lets Quanta reduce
the ceremony tax for the writer and the failure rate for the tooling at the same
time. It absorbs the proven strengths of existing languages (safety outcomes,
fast feedback, domain notation, verifiability) while designing out their
recurring weaknesses (ceremony, packaging, fragile text, unverifiable claims).
Everything else follows from it.
