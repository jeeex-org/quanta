# Quanta — Language Design

Quanta is a programming language for every human: anyone, regardless of
background, can build anything with software. This document is its design
specification — what the language is and how it behaves. It is not a proposal or
a thought experiment. Quanta is built to this design, version by version, with a
green test gate before every promotion.

The one constraint: it must actually work. A language for everyone that does not
compile, run, and stay correct is worthless.

---

## 1. Core Principle: Intent Over Apparatus

Most languages are built for computers and tolerate programmers. The few built
for programmers still demand the machine's concerns up front — types, memory,
build systems, toolchains — before a single idea may be expressed.

That is backwards. The machine is cheap and patient; human attention is the
scarce resource. Quanta inverts the burden: **the language carries the machine's
concerns, and hands them back only when the task requires them.**

> **The precision ladder is the compiler's, not the human's.** The human always
> writes at the intent level, in their own field's terms. The system elaborates
> downward — inferring types, proving bounds, scheduling the GPU, tracking
> ownership — on the user's behalf, invisibly. Specialization stays in the user's
> domain; it never leaks into Quanta.

A child's first program and a cryptographer's signature circuit are written in
the same language, at the same plain level. They differ only in what the
*compiler* must elaborate to satisfy the machine — not in what the *person* must
know. Specializing in biology does not mean specializing in Quanta.
Specializing in post-quantum cryptography does not mean studying type theory.
You write your field; the compiler carries the apparatus.

---

## 2. Ten Principles

1. **Intent-first.** State what is wanted; the apparatus is inferred.
2. **Precision on demand.** No required ceremony. Annotations are opt-in powers, not tolls.
3. **One language, every machine.** Native, WASM, GPU, microcontroller, cluster — same source, chosen target.
4. **Memory without fear.** Region inference by default; ownership only when the task demands it. No GC pauses, no manual `free`, no borrow-checker fight for beginners.
5. **Safety by construction.** Bounds, overflow, null, data races handled by the system by default; visible only inside `unsafe`.
6. **The compiler is a tutor.** Errors explain *why* and show the *fix*.
7. **Literacy by default.** Examples are executable; tests are examples; docs cannot drift from code.
8. **Domain dialects are first-class.** Physics, music, biology, finance, crypto ship as vocabularies with real syntax.
9. **Accessible & multilingual.** Keywords and diagnostics in the programmer's own language; notation close to the discipline's; voice/visual entry for those who cannot type.
10. **No separate build system.** One command, content-addressed modules, no "works on my machine."

---

## 3. The Language

### 3.1 Syntax

Spatial, not ceremonial. No `public static void main(String[] args)`; no
boilerplate to earn the right to print. The top of a file is a program.

```
# Complete, runnable Quanta.
println "Hello, world"
```

Indentation defines structure. Quanta forbids the classic Python footgun: a tab
is a tab and a space is a space — the lexer accepts exactly one indentation unit
per level and rejects mixed sources at parse time with a precise message. Side
effects are explicit via verb-like builtins (`println`, `write`, `send`) so pure
computation is visibly distinct from action.

### 3.2 The Precision Ladder (the compiler's, not yours)

Five levels of elaboration the *compiler* performs — not five things the user
learns. The human writes at the top; the system descends only as far as the
machine requires.

**Rung 0 — Intent.** What the human writes.
```
double(x) = x * 2
println double(21)        # 42
```
No types, no return, no `fn`. This is where everyone starts — the child, the
biologist, the driver engineer.

**Rung 1 — Structure, inferred.** Maps, lists, strings resolved by the system
when values are named.

**Rung 2 — Named types, optional.** Written when *the human* wants readability,
never because the language demands it. The compiler would infer them regardless.

**Rung 3 — Proof, when the task needs it.** Refinement and dependent types
elaborated by the compiler. If a bound matters, the system proves it and turns a
runtime crash into a compile error — without the human reading a type-theory
paper.

**Rung 4 — Machine control, when the task demands it.** Ownership and linearity
tracked by the compiler for code where double-free or aliasing is fatal.

Everyone writes at Rung 0. The compiler descends as far as the *machine* (not the
human) requires.

### 3.3 Type System: Human Untyped, System Typed

The human writes no type declarations. The compiler maintains a precise internal
type model and uses it to verify and optimize. This is not "untyped" in the
sloppy sense — it is *typed on behalf of the human*.

- Where correctness is cheap to prove, the system proves it silently.
- Where the domain demands formal guarantees (packet bounds, modular reduction,
  constant-time execution), the system enforces them because the *dialect*
  requires it, not because the human remembered to ask.

The human is never taxed for precision up front; the system still pays it where
the stakes demand.

### 3.4 Precision Where It Is Required

Quanta is **not** loose. It is a precise language. Looseness is a property of the
*task's stakes*, not the *user's skill* — and the compiler sets strictness from
the domain, not the person.

Domains with non-negotiable invariants are **mandatory dialects with enforced
rules**:

- **Blockchain** — no replay, deterministic RNG, correct modular arithmetic,
  verified Merkle construction. A transaction that violates these is rejected by
  the dialect, not left to chance.
- **Quantum-resistant cryptography** — constant-time execution, no
  secret-dependent branches, correct lattice/field arithmetic. A variable-time
  AES or an unreduced field op is a compile error in the `secure` dialect.

These are not "features you might use." They are vocabularies whose *rules are
baked in*, so a cryptographer gets precision without hand-annotating it, and a
beginner never sees them. A child's drawing is loose because nothing breaks; a
ZK-proof circuit is precise because everything breaks. The compiler carries that
precision for both. **"For every human" never means "loose everywhere" — it
means no human pays the precision tax up front, while the system still pays it
where the stakes demand.**

### 3.5 Memory: Regions First, Ownership Second

Default memory is **region inference**. Every value belongs to a region derived
from its scope; when the region ends, memory is released deterministically — no
pause, no sweep, no manual `free`. For the large majority of programs this is
memory-safe by construction: use-after-free and leaks are structurally
impossible in normal code.

When a value must outlive its scope (long-lived cache, lock-free structure,
2 KB microcontroller), the human opts into **linear ownership**. Ownership is a
mode entered for that code, not a tax paid everywhere — avoiding the "everyone
must learn the borrow checker" failure while keeping its zero-cost safety.

### 3.6 Concurrency: Structured by Default

Raw threads and shared mutable state are not in the beginner vocabulary.
```
results = parallel for url in urls:
    fetch(url)
println results
```
`parallel` blocks are structured: they cannot leak a thread or outlive their
scope. Distributed execution is the same shape with a target — `parallel at
cluster`. The mental model is identical; only the *where* changes.

### 3.7 Errors That Teach

A Quanta error is a conversation, not a verdict:
```
error: `age` cannot be negative here.
  → line 12:  let age = birth_year - 2026
  why:  declared as `Nat` (non-negative) on line 9.
  fix:  allow negatives with `Int`, or guard `if birth_year > 2026`.
  hint: working example at examples/age-guard.qx
```
The compiler shows the cause, the rule, the repair, and a reference. No one is
shamed for not knowing; everyone is taught.

### 3.8 Domain Dialects

A biologist writes `field = laplace(potential) + source`. A musician writes
`melody = C4 >> eighth ++ E4 >> eighth ++ G4 >> quarter`. A cryptographer writes
`state |= round_key` and it means what it means.

Dialects are vocabularies with first-class notation, registered and versioned,
desugaring to core forms anyone can read. The core stays small; disciplines
bring their own language, all compiling to the same efficient machine code. This
is how a child and a quant both feel native — Quanta meets each where their
discipline already thinks.

---

## 4. One Language, Every Machine

```
quanta build --target native      # laptop
quanta build --target wasm        # browser
quanta build --target gpu         # kernel
quanta build --target mcu         # microcontroller (region model shrinks to RAM)
quanta build --target cluster     # distributed
```

The runtime adapts; the program does not change. Native gets the fast region
allocator, MCU a static allocator sized to the chip, WASM the sandbox model,
cluster the distributed runtime. There is no Python-problem vs Rust-problem vs
C-problem. There is Quanta, at the rung the problem needs.

---

## 5. Tooling & Literacy

**No build files.** No Makefile, CMake, package.json, or Cargo.toml. Source is
content-addressed; `import "crypto/sha256"` resolves by hash, not by
name-typosquat — supply-chain attacks are mitigated by construction.

**The compiler is the tutor.** `quanta explain <error>` opens a guided lesson;
`quanta why <line>` explains the inferred type and region of any value. Learning
and using are the same act.

**AI-native by construction.** Quanta's source of truth is its AST. Refactors,
completions, and translations are structural operations, not regex surgery — so
a machine assistant edits verified trees without breaking them. This is the home
of Quanta's native code-writing tool.

**Docs are code.** Every example is executed as a test; a broken doc example
fails the build. Documentation cannot drift from implementation.

---

## 6. Accessibility & Multilingualism

- **Your language, your keywords.** `println`, `mostrar`, `显示`, `පෙන්වන්න` are the
  same builtin; semantics identical. Disability is not a barrier to entry.
- **Notation closeness.** Math is written in math notation where possible; `∑`,
  `∫`, `∂` are real operators.
- **Non-typing entry.** Voice and visual interfaces compile to the same AST.

---

## 7. Honest Tradeoffs

- **Region inference has escape limits.** A value that must outlive an
  unpredictable scope cannot always be region-inferred; there, ownership is
  required. The ladder has a ceiling; the top rungs demand real understanding —
  but not everyone must climb them.
- **Gradual typing has a dynamic edge.** Untyped paths rely on runtime checks,
  made visible and cheap. Hot loops in performance-critical code are annotated to
  erase them.
- **Dialects risk fragmentation.** Governed: registered, versioned, desugaring to
  readable core forms.
- **Compile time.** Inference, proof, and multi-target codegen are not free;
  incremental compilation and a fast self-hosted compiler keep the loop
  sub-second.
- **Teaching the compiler to teach** is real engineering, not a chat window.

None are fatal. They are the price of the thesis, and the thesis is worth it.

---

## 8. Three People, One Language

All three start at the same plain level and write their field in their field's
words. None studies Quanta. They differ only in what the compiler must elaborate.

```
# Ada, age 11 — a drawing
draw circle at (100,100) size 40 color blue
when clicked: color = random_color
```
She writes what she means; the compiler handles types, memory, build.

```
# Dr. Okafor, biologist
concentration = [1, 2, 3, 2, 1]
smoothed = average_neighbors(concentration)
println smoothed
```
Plain biology, no Quanta concepts. When she later writes
`diffusion = D * laplace(concentration) - uptake(concentration)` and simulates
it, the *compiler* proves bounds and schedules the GPU. She never studies
parallelism or linear algebra — the system does.

```
# Ravi, systems engineer — a device driver
buf = device.alloc(256)
on irq: process(buf)
```
Driver words, no ownership study. The compiler sees `buf` is used by the
interrupt handler, infers it must be owned and single-use, and warns only on
conflict. The linear-type machinery is the system's concern, not his.

The same `process` function all three use is written at the same plain level.
What differs is the machine work the compiler performs behind each — never the
human's burden.

Three humans. One language. One starting level. The ladder is the compiler's, not
theirs.

---

## 9. Current State

Quanta does not yet implement all of this; that is by design, not accident. It
is built incrementally, one feature per version, gate-green before promotion.
The current state (0.0.86) and the sequenced plan live in `docs/ROADMAP.md` and
`docs/QUANTA_GAP_ANALYSIS.md`.

Already real: a self-hosting native compiler with a byte-identical fixpoint; a
low-ceremony intent-level syntax; a primitive layer (syscalls, mmap, file I/O,
floats, closures, generics, big-int); and differentiating stdlib seeds
(`crypto`, `quantum`, `linalg`, `math`). Remaining is architectural — region/
ownership memory, multi-backend codegen, dialect notation, package management,
the tutor/accessibility layer, and enforced precision for blockchain and
post-quantum crypto dialects.

The direction is constant: **lower the floor without lowering the ceiling.**
