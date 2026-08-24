# Lumen — The Design of Quanta

> **One-line clarity (read this first):** *Lumen is the design of the Quanta
> programming language — its principles, its target user (every human), and its
> goals. Quanta is that design made real, version by version. There is exactly
> one language and one project: Quanta. "Lumen" names *how Quanta is designed*,
> not a separate product, not a code name, not a replacement. Design and
> implementation of the same language.*

> *If I were to design a programming language from scratch, for every human, so
> that anyone — regardless of background — could build anything with software:
> this is what I would build. There are no limits here. The only constraint is
> that it must actually work.*

---

## 0. The Mandate

Most languages are built for *computers* and tolerate *programmers*. The few
built for programmers still assume a certain kind of programmer: someone who is
comfortable with the machine's concerns — types, memory, build systems,
toolchains — before they are allowed to express a single idea.

That is backwards. The machine is cheap and patient. Human attention and
confidence are the scarce resource. A language for *all* humans must invert the
burden: **the language should carry the machine's concerns for you, and only
hand them back when you ask for them.**

This document describes **Lumen**. It is not a proposal to replace anything. It is
a thought experiment taken seriously enough to have concrete syntax, a concrete
type system, and honest tradeoffs. Where it overlaps with ideas already alive in
Quanta (simple syntax, multiple execution modes, self-hosting), that is no
accident — but Lumen is the fuller vision, unconstrained by what already exists.

---

## 1. The Central Thesis: *Intent Over Apparatus*

The single design decision that drives everything else:

> **You write what you mean. The compiler infers everything it can. You never
> declare a type, an allocator, a lifetime, a build target, or a memory model
> until the moment you actually need to.**

The barrier to software is not syntax. It is the *mismatch* between how humans
think — in **intent**, in **context**, in **gradually increasing precision** —
and how machines demand we think: in exact types, explicit ownership, manual
builds, from day one.

Lumen collapses that mismatch with a **gradient of precision**. The same program
can begin as near-pseudocode and end as hard real-time embedded code, using the
*identical* syntax. Precision is something you *add*, never something you are
*required* to supply. A child's first program and a kernel hacker's fifteenth
revision are written in the same language, at different points on the ladder.

This is the opposite of "batteries-included" and the opposite of "you must
understand the borrow checker." It is: **start human, become machine only on
purpose.**

---

## 2. The Ten Principles

1. **Intent-first.** Say what you want done; the apparatus is inferred.
2. **Precision on demand.** No required ceremony. Annotations are opt-in powers, not tolls.
3. **One language, every machine.** Native, WASM, GPU, microcontroller, distributed cluster — same source, chosen target.
4. **Memory without fear.** Region inference by default; ownership only when you opt in. No GC pauses for most programs, no manual `free` for most programs, no borrow-checker fight for beginners.
5. **Safety by construction, not by restriction.** Bounds, overflow, null, data races — handled by the system by default, invisible unless you descend into `unsafe`.
6. **The compiler is a tutor.** Errors explain *why* and show the *fix* in plain language.
7. **Literacy by default.** Examples are executable. Tests are examples. Docs cannot drift from code.
8. **Domain dialects are first-class.** Physics, music, biology, finance, crypto ship as vocabularies with real syntax — not stringly-typed libraries.
9. **Accessible & multilingual.** Keywords and diagnostics in the programmer's own language; notation close to the discipline's native notation; voice/visual entry for those who cannot type.
10. **No separate build system.** One command. Content-addressed modules. No "works on my machine."

---

## 3. The Language Itself

### 3.1 Syntax Philosophy

Lumen syntax is **spatial, not ceremonial**. There is no `public static void main(String[] args)`.
There is no boilerplate to "earn the right" to print. The top of a file is a
program.

```
# This is a complete, runnable program.
show "Hello, world"
```

Indentation defines structure (like Python), but Lumen forbids the classic
Python footgun: **a tab is a tab and a space is a space** — the lexer accepts
exactly one indentation unit per level and rejects mixed sources at parse time
with a precise message, not a mysterious `IndentationError` 40 lines later.

Expressions read left-to-right and top-to-bottom. Side effects are explicit via
verb-like builtins (`show`, `write`, `send`) so that pure computation is visibly
distinct from action.

### 3.2 The Precision Ladder

This is the heart of the design. Five rungs. You climb only as far as you need.

**Rung 0 — Intent (pseudocode that runs):**
```
double(x) = x * 2
show double(21)        # 42
```
No types. No return. No `def`/`fn`. The compiler infers `x: Int`, infers the
return, infers everything. This is valid and shipped.

**Rung 1 — A little structure:**
```
ages = ["Ada": 36, "Alan": 41]
show ages["Ada"]
```
Maps, lists, strings — all inferred. You name a thing; the compiler figures out
what kind of container it is.

**Rung 2 — Named types when *you* want clarity:**
```
type Person = { name: Text, age: Int }
celebrate(p: Person) = show "Happy birthday, {p.name}!"
```
Annotations appear the moment they *help you*, not because the language demands
them.

**Rung 3 — Proof when it matters (refinement types):**
```
type Adult = Int where it >= 18
serve(alcohol: Bool, age: Adult) = ...
# Calling serve(true, 15) is a compile error, not a runtime bug.
```
Dependent/refinement types are available to anyone who needs the compiler to
*prove* a property — but you only pay for them on the functions where you write
the `where`.

**Rung 4 — Machine control (opt-in ownership):**
```
own buffer: Bytes = alloc(4096)
send(socket, buffer)   # buffer is MOVED; use after send is a compile error
```
Here, and only here, you descend to explicit memory ownership. Beginners never
see this. Systems programmers opt in deliberately.

### 3.3 The Type System: Gradual, Then Deep

- **Bottom rung:** untyped / inferred. `x = 5` just works.
- **Middle:** optional annotations, checked structurally.
- **Top:** refinement and dependent types for those who need formal guarantees.

Crucially, these mix freely in one program. A game's UI logic can stay inferred
while its netcode uses refinement types to prove packet bounds. The type checker
unifies them; you are never forced to annotate the whole program to annotate one
function.

### 3.4 Memory: Regions First, Ownership Second

The default memory model is **region inference**. Every value belongs to a region
derived from its scope and structure. When the region ends, the memory is
released — deterministically, with no pause, no GC sweep, no manual `free`.

```
process(raw)
    cleaned = sanitize(raw)     # region: process
    report = summarize(cleaned) # cleaned freed when process returns
    return report               # report outlives via explicit return
```

For ~90% of programs this is all you ever need, and it is **memory-safe by
construction**: use-after-free and leaks are structurally impossible in normal
code because the region graph is checked at compile time.

When you need fine control — a cache that outlives its creator, a lock-free
structure, an allocator for a device with 2 KB of RAM — you opt into **linear
ownership** (Rung 4). Ownership is a *mode you enter*, not a tax you pay
everywhere. This avoids Rust's "everyone must learn the borrow checker" problem
while keeping its zero-cost safety for those who want it.

### 3.5 Concurrency: Structured by Default

Raw threads and shared mutable state are not in the beginner vocabulary. Instead:

```
results = parallel for url in urls:
    fetch(url)          # each runs concurrently, all joined automatically
show results
```

`parallel` blocks are **structured**: they cannot leak a thread, cannot outlive
their scope, and their errors propagate predictably. Distributed execution is the
same shape with a target:

```
results = parallel at cluster for shard in shards:
    aggregate(shard)
```

The mental model is identical; only the *where* changes.

### 3.6 Errors That Teach

A Lumen compile error is a *conversation*, not a verdict:

```
error: `age` cannot be negative here.
  → line 12:  let age = birth_year - 2026
  why:  `age` was declared as `Nat` (non-negative integer) on line 9.
  fix:  either allow negatives with `Int`, or guard:  `if birth_year > 2026: ...`
  hint: similar code at examples/age-guard.lum works.
```

The compiler points at the *cause*, explains the *rule*, shows the *repair*, and
offers a *working reference*. No one is shamed for not knowing; everyone is
taught.

### 3.7 Domain Dialects

A biologist should not write `matrix_multiply(generator_current, ...)`. They
should write:

```
field = laplace(potential) + source
```

A musician should not call `midi_note_to_frequency(60)`. They should write:

```
melody = C4 >> eighth ++ E4 >> eighth ++ G4 >> quarter
```

A cryptographer should write `state |= round_key` and have it mean what it means.

Lumen ships **dialects** — vocabularies with first-class syntax sugar — for
physics, music, biology, finance, crypto, and more. They are just libraries that
register notation. The "universal" core stays small; the disciplines bring their
own language, and all of it compiles to the same efficient machine code. This is
how a kid and a quant both feel native — the language *meets them where their
discipline already thinks*.

---

## 4. One Language, Every Machine

You write once. You choose a target:

```
lumen build --target native      # your laptop
lumen build --target wasm        # the browser
lumen build --target gpu         # a shader / kernel
lumen build --target mcu         # a microcontroller (region model shrinks to RAM)
lumen build --target cluster     # distributed
```

The *runtime* adapts. Native gets the fast region allocator; MCU gets a static
allocator sized to the chip; WASM gets the sandbox model; cluster gets the
distributed runtime. **You do not rewrite your program to change targets.** The
precision ladder lets you write target-agnostic code at the top and
target-specific code only at the bottom rungs where hardware demands it.

This kills the "which language for which job" anxiety. There is no Python problem
vs Rust problem vs C problem. There is Lumen, at the rung your problem needs.

---

## 5. Tooling & Literacy

**No build files.** There is no Makefile, CMake, package.json, or Cargo.toml to
learn. Source is content-addressed. `import "crypto/sha256"` resolves the right
version from a global namespace automatically; supply-chain attacks are mitigated
because imports are by hash, not by name-typosquat.

**The compiler is the tutor.** `lumen explain <error>` opens a guided lesson.
`lumen why <line>` explains the inferred type and region of any value. Learning
the language and using it are the same act.

**AI-native by construction.** Lumen's source of truth is its AST, not raw text.
The grammar is designed to be *manipulated reliably by machines*: refactors,
completions, and translations are structural operations, not regex surgery. An
AI assistant can safely rewrite your code because it operates on the verified
tree. (This is the natural home for the Quanta-native "code-writing tool"
vision — a language the machine can edit without breaking.)

**Docs are code.** Every function's examples are executed as tests. If the doc
example breaks, the build fails. Documentation physically cannot drift from
implementation — the same rule that keeps a project's docs in sync with its code
is enforced by the language itself.

---

## 6. Accessibility & Multilingualism

- **Your language, your keywords.** `show`, `mostrar`, `显示`, `පෙන්වන්න` are all
  the same builtin. The programmer chooses their vocabulary; the semantics are
  identical. Disability is not a barrier to entry.
- **Notation closeness.** Math is written in math notation where possible, not
  in ASCII approximations. `∑`, `∫`, `∂` are real operators.
- **Non-typing entry.** Voice and visual block interfaces compile to the *same*
  AST, so someone who cannot type still writes first-class Lumen.

---

## 7. The Hard Parts (Honest Tradeoffs)

A vision that hides its costs is a fantasy. Here is where Lumen pays:

- **Region inference has escape limits.** A value that must outlive an
  unpredictable scope (long-lived caches, cross-task handoff) cannot always be
  region-inferred. There, you *must* opt into ownership. We accept that the
  ladder has a ceiling and that the top rungs require real understanding — we
  just refuse to make everyone climb them.
- **Gradual typing has a dynamic edge.** Fully untyped code paths rely on runtime
  checks. Lumen makes those checks *visible and cheap*, but they exist. Hot loops
  in performance-critical code should be annotated (Rung 2+) to erase them.
- **Dialects risk fragmentation.** If every domain invents notation, readability
  across disciplines suffers. Lumen governs dialects: they must be registered,
  versioned, and their sugar must desugar to core forms anyone can read.
- **Compile time.** Inference + refinement + multi-target codegen is not free.
  Lumen invests in incremental compilation and a fast self-hosted compiler so the
  edit-run loop stays sub-second for normal projects.
- **Teaching the compiler to teach.** The "tutor" error model is real
  engineering, not a chat window bolted on. It is worth it, but it is work.

None of these are fatal. They are the price of the thesis — and the thesis is
worth it.

---

## 8. Three People, One Language

**Ada, age 11, has never coded:**
```
draw circle at (100,100) size 40 color blue
when clicked: color = random_color
```
She learns cause and effect. No types, no build, instant feedback.

**Dr. Okafor, a biologist, models a cell:**
```
diffusion = D * laplace(concentration) - uptake(concentration)
simulate diffusion for 10 seconds
plot concentration
```
She writes in her discipline's notation. The compiler proves bounds and runs it
natively on her laptop's GPU.

**Ravi, a systems engineer, writes a device driver:**
```
own buf: Bytes = device.alloc(256)
own irq: Irq = device.bind(INT0)
on irq: process(buf)        # linear types guarantee no double-free
```
He opts into ownership and target-specific code. The same `process` function
Ada and Okafor might use is reused here, at a different rung.

Three humans. One language. From "what is a program" to "lock-free interrupt
handler." That is the design goal made concrete.

---

## 9. Relationship to Quanta

Lumen is not a separate language — it *is* the design of Quanta. Quanta is that
design made real, version by version. Quanta already embodies the core of this
design: a simple, position-based syntax; progressive precision over versions; a
self-hosting compiler; the goal of carrying the machine's concerns for you and
handing them back only on purpose, for every human, on every machine.

What this document adds beyond today's Quanta is the *full* statement of the
design — including pieces Quanta has not implemented yet (regions, multi-backend
targets, domain dialects, the tutor layer). Those are gaps in the current build,
not a different language. The direction is the same: **lower the floor without
lowering the ceiling.** Quanta is the implementation; Lumen is its design.

---

## 10. Closing

A programming language for every human is not one with the smallest syntax or
the fastest runtime. It is one that **respects the human's attention above the
machine's demands** — that lets a child's first line run and a kernel dev's
tenth rewrite compile, in the same words, at different points on a ladder of
precision.

No one should have to learn the machine's fears — ownership, lifetimes, build
systems, toolchains — before they are allowed to build the thing they imagined.
Carry those fears for them. Hand them back only when asked.

That is Lumen. That is the design.
