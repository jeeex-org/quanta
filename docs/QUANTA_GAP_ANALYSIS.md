# Quanta Design → Quanta Reality: Gap Analysis

> **Scope:** *This document compares Quanta's full design (see
> `docs/LANGUAGE_DESIGN.md`) against what Quanta actually implements at 0.0.86.
> There is exactly one language and one project: Quanta. The design and the
> implementation are the same thing at different points in time. This is the
> honest "what's built vs what the design calls for" map, so we know what to
> build next.*

**Verification baseline (2026-08-25, 0.0.86):**
- Single backend: `compiler/0.0.86/src/x86/` only. No `wasm/`, `gpu/`, or `mcu/` tree exists.
- 117 gated tests; 10 stdlib files in `lib/std/` (big, crypto, fs, io, linalg, map, math, quantum, str, vec).
- No package manager, no content-addressed imports, no concurrency primitives.
- `big` is a lexer token (`TT_BIGNUM`) + library convention; **not** a first-class type.
- Build = manual `qc <src> <bin>` (two positional argv). No declarative manifests.

---

## 1. Gap Matrix (Design Pillar by Pillar)

| # | Design Pillar | Quanta 0.0.86 State | Gap |
|---|---|---|---|
| 1 | **Intent-first / zero ceremony** | ✅ Strong. `fn`, `let`, inferred calls, short syntax already minimal. | *Minor.* `println` is the builtin (not `show`); top-level `name=val`=global already matches. |
| 2 | **Precision Ladder (5 rungs)** | 🟡 Partial. Untyped today (Rung 0–1); Rung-2 annotations are *parsed and recorded* for codegen width but **not enforced** — there is no type checker. | **Rung 3 (refinement/dependent types) absent. Rung 4 (ownership) absent. No compile-time type errors exist yet — a type mismatch is not caught.** |
| 3 | **One language, every machine** | 🔴 Native x86 only. | **WASM, GPU, MCU backends absent.** Doc claims "interpreter/JIT/WASM modes" but 0.0.86 source is native-only. |
| 4 | **Regions-first memory** | 🔴 None. Bump mmap allocator; `real allocator` is ❌ todo. | Region inference not started. Leak/double-free still possible. |
| 5 | **Safety by construction** | 🟡 Partial. Bounds/overflow *not* auto-checked; `unsafe`/`raw` exist but aren't a safety boundary. | No automatic bounds/overflow proofs. |
| 6 | **Compiler as tutor** | 🔴 Errors are raw `rc=` codes + aborts. No explanatory layer. | No `quanta explain`, no cause/fix/hint. |
| 7 | **Literacy: examples=tests=docs** | 🟡 FEATURES.md now synced, but docs not *executed* as tests. | Doc-example-as-test enforcement absent. |
| 8 | **Domain dialects** | 🔴 None registered. `crypto/quantum/linalg/math` are plain libs, no notation sugar. | No dialect registry; `laplace`, music, bio notation absent. |
| 9 | **Accessibility / multilingual** | 🔴 English keywords only; no i18n keyword layer; no voice/visual entry. | Full gap. |
| 10 | **No separate build system** | 🔴 `qc src bin` manual; no content-addressed modules; no hash-pinned imports. | Package manager ❌ todo. |
| — | **Structured concurrency** | 🔴 No `parallel`, threads, async. | Full gap. |
| — | **AI-native AST editing** | 🟡 Quanta-native code-writing tool is ❌ todo (0.0.90 slot). | Not built. |

---

## 2. What Quanta Already Has That the Design Needs (Don't Rebuild)

These are **assets**, not gaps — the design's foundation already partly exists:

- **Self-hosting native compiler** (0.0.86 fixpoint byte-identical) — the trust anchor the tutor/AI-editing layer needs.
- **Multiple *declared* execution modes** (native/interpreted/JIT/WASM per Quanta's own description) — even if 0.0.86 only ships native, the *concept* of mode selection exists to extend.
- **Inferred, low-ceremony syntax** — Rung 0–2 of the ladder already real.
- **Solid primitive layer**: syscalls, mmap, file I/O, floats, closures, generics (type-erased), big-int *library*, crypto/quantum/linalg/math stdlib.
- **Differentiating stdlib seeds**: `crypto`, `quantum`, `linalg`, `math` exist as real code — the *content* of dialects, even without the notation sugar.
- **CI gate + SYNCED docs discipline** — the literacy principle (docs can't drift) is already enforced culturally.

---

## 3. The Real Gaps, Ranked by Leverage

### Tier A — Foundational (blocks everything above it)
1. **`big` as a first-class type** (lexed + lib-only today). Without a real type
   system hook, refinement types (Rung 3) and dialect value-types can't sit on top.
   *Already tracked in ROADMAP remaining list; sequenced ~0.0.88–0.1.0.*
2. **Region / ownership memory model** (Rung 4 + region inference). This is the
   single biggest architectural gap vs the design. Today: bump mmap, manual.
   *Not yet started; 0.1.0+ work.*
3. **Multi-backend codegen** (WASM first, then MCU, then GPU/cluster). The "one
   language every machine" pillar is impossible until codegen is backend-pluggable.
   *0.0.86 source is x86-only; needs an IR → backend split.*

### Tier B — Differentiating (the "exceptional at math/physics/crypto/quantum/AI" mandate)
4. **Missing stdlib**: `chain` (blockchain), `secure` (constant-time I/O),
   `ai` (tensors/inference), `physics` (ODE/PDE). These *are* the dialects' content.
   *Not in code; part of the user's explicit differentiation mandate.*
5. **Dialect registry + notation sugar**. Even with the libs, `laplace(potential)`
   must desugar to `linalg` calls. Needs a notation-registration mechanism.
6. **`big` gate test + `quantum`/`linalg` gate tests** — shipped code, untested in
   gate (found during SYNCED audit). Closes the "docs vs code" gap at the stdlib level.

### Tier C — Experience (makes it "for every human")
7. **Tutor error layer** over the existing compiler (cause/rule/fix/hint). Pure
   UX; reuses the self-host. High leverage, low risk.
8. **Package manager + content-addressed imports** (hash-pinned, supply-chain safe).
   Replaces `qc src bin`; closes build-system gap.
9. **i18n keyword layer + non-typing entry** (voice/visual → AST). Full
   accessibility pillar.
10. **Structured concurrency** (`parallel for`, `at cluster`). New runtime + type
    support.

---

## 4. Sequencing Against the Existing ROADMAP

The current ROADMAP's "remaining to 0.1.0" lists: generics monomorphisation,
borrow-checking, operator overloading. The design gaps **extend and re-rank** that:

- **0.0.87–0.0.91 (already planned):** types as real types (`big`, u8/u16/bool/
  char/byte), `as`, `where`/`raw`/`ref`/`move`, range, operator overloading,
  try/catch, real allocator, ownership/borrow. → *Directly fills Tier A #1, #2
  partial, and #3's ownership half.*
- **0.0.92–0.0.93:** generics monomorphisation (ROADMAP) → enables dialect
  value-types. Add `chain`/`secure`/`ai`/`physics` stdlib (Tier B #4) — the
  differentiation mandate.
- **0.0.94–0.0.96:** dialect registry + notation sugar (Tier B #5); tutor error
  layer (Tier C #7); package manager (Tier C #8).
- **0.0.97–0.1.0:** multi-backend IR split → WASM target (Tier A #3); borrow-
  checking completion (Tier A #2 finish); i18n keywords (Tier C #9) start.
- **POST-0.1.0 (explicitly deferred per ROADMAP):** ARM64 backend, then GPU/MCU,
  structured concurrency, full accessibility entry.

The honest takeaway: **Quanta is ~30% of the way to its own full design
foundation** (it has the syntax ladder base, the self-host, the primitive layer,
and the differentiation *content* as libs). The missing 70% is architectural —
region/ownership memory, multi-backend codegen, dialect notation, package
management, and the tutor/accessibility experience layer.

---

## 5. The One-Sentence Gap

> Quanta can already *express intent simply and compile itself natively*; it
> cannot yet *infer memory safety, target other machines, speak domain notation,
> manage its own packages, or teach the programmer* — and those four are exactly
> what make the design "for every human."

---

## 6. Recommended Next Concrete Step (highest leverage)

Close **Tier B #6 + Tier A #1** together: write `big_test.quanta`,
`quantum_test.quanta`, `linalg_test.quanta` (gate them), and promote `big` from
library-convention to a first-class type. This is low-risk (stdlib already works),
directly advances the differentiation mandate, and is the prerequisite hook for
Rung-3 refinement types later. It is also exactly the "one remaining big-int task"
already identified as outstanding.
