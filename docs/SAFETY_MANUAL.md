# Quanta Safety Manual & Qualification Status

> Companion to `docs/SPEC.md` and `docs/LANGUAGE_DESIGN.md`.
> Purpose: record the safety-relevant properties of the Quanta native
> compiler, the evidence supporting each claim, and the gaps that block
> formal tool qualification under ISO/IEC 26262 (automotive functional
> safety, ASIL A–D) and IEC 61508 (industrial, SIL 1–4).

Last updated: 2026-08-16. Compiler version: 0.0.53.

---

## 1. Scope & intended use

Quanta's native AOT backend (x86-64; AArch64 backend planned POST-1.0) compiles Quanta source to
standalone ELF executables. This manual covers the **compiler toolchain**
only. It does NOT cover:
- Application logic written in Quanta (that is the integrator's safety case).
- Interpreter / JIT / WASM backends (not yet built — LANGUAGE_DESIGN.md
  Stages 1/3/5).

**Intended safety integrity level (target):** IEC 61508 SIL 1–2 /
ISO 26262 ASIL A–B, contingent on closing the gaps in §6. Higher levels
(ASIL C–D, SIL 3–4) are NOT achievable with the current architecture
(see §6.3).

---

## 2. Qualification route mapping (ISO 26262-8 Clause 11 / IEC 61508-3 Annex F)

| Clause | Requirement | Quanta status |
|--------|-------------|---------------|
| TCL assessment | Tool Confidence Level from impact + error detection | Partially: impact = high (codegen), detection = low → would require qualification |
| Documentation | Tool spec + safety manual | **SPEC.md (v0.0.53) + this manual exist** |
| Validation | Demonstrate correct behavior | Partial: self-host fixed-point (2-stage, byte-identical) + 96-test gate + fail-closed tests (§4) |
| Configuration mgmt | Version-controlled, reproducible | **Yes**: per-version `compiler/0.0.XX/` dirs, git-tagged |
| Independent implementation | Cross-check tool | **PARTIAL** — differential vs bootstrap-SEED qc (5/5 parity, 0.0.53); full x86↔ARM64 differential tracked at 0.0.72+ (ROADMAP §Standards) |
| Formal proof | Mathematical correctness | **NO** — semantics defined by emitter behavior (§6.1) |

See also `docs/MEMORY_SAFETY_ARGUMENT.md` (the structured safety argument:
claim → evidence → assumption chain for memory safety).

**Verdict:** Quanta is at the *documentation + partial-validation* stage.
It is NOT yet a qualified tool. The path to SIL 1–2 qualification is
plausible within a defined effort; SIL 3–4 requires an independent
implementation and/or formal semantics.

---

## 3. Language-level safety mechanisms (fail-closed, not prove-safe)

Quanta follows a **"fail-secure, not prove-safe"** model (LANGUAGE_DESIGN.md
§Memory-safety posture): undefined/unsafe operations trap at runtime rather
than corrupt silently.

| Mechanism | Behavior | Evidence |
|-----------|----------|----------|
| Integer overflow | `ud2` → SIGILL, rc=132 | Self-host; `unsafe{}` opts out |
| OOB array access | `ud2` → SIGILL, rc=132 | `idx_trap_emit` in emitter; `unsafe{}` opts out |
| `mmap` OOM | abort rc=1 (was SIGSEGV 139) | **Verified 0.0.49**: `ulimit -v 60000` → rc=1 |
| Undeclared identifier | compile error rc=7 | Verified 0.0.48 |
| Cyclic struct def | compile error rc=7 | Verified 0.0.48 |
| Executable output | ELF mode 0755 | Verified 0.0.53 (binary runs directly) |

---

## 4. Verification evidence (what was actually run)

All evidence below was produced this session (2026-08-16) against
`compiler/0.0.53/`:

1. **Self-host fixed point**: 2-stage bootstrap
   `committed bin/x86/qc → 0.0.65 source → qc`, all rc=0,
   rebuilt `qc` byte-identical to committed `qc` (and to a 2nd-stage rebuild). (A miscompiling
   compiler almost always fails to bootstrap — this is a strong
   end-to-end correctness signal.)

2. **Valgrind**: `valgrind --leak-check=summary qc <crash-repro>` →
   **0 errors** on all repro programs (memory-safe w.r.t. leaks/UB
   in the compiler itself).

3. **Fail-closed tests** (all PASS):
   - `ulimit -v 60000 ./qc ...` → exit **1** (MAP_FAILED handled),
     NOT 139 (SIGSEGV).
   - Undeclared fn → exit **7**.
   - `struct S { x S }` (cyclic) → exit **7**.

4. **Grammar / static-analysis readiness**: all 15 compiler modules
   parse with **0 errors** under `tree-sitter-quanta` at v0.0.53
   (was ~1000 errors/file at v0.0.51). Enables CodeRabbit / CI
   static review of every module.

5. **Latent-defect caught**: keyword-hash constants `H_ENUM`/`H_MUT`/
   `H_MOVE` in `tokens.quanta` had mismatched parentheses, causing the
   lexer to compute **WRONG hashes** for `enum`/`mut`/`move` keywords —
   silent data corruption, no crash. Fixed and verified balanced at
   v0.0.53. This is exactly the class of defect a safety process must
   catch (see §5).

---

## 5. Defect tracking (safety-relevant)

| ID | Defect | Severity | Status |
|----|--------|----------|--------|
| S-001 | `mmap` failure unchecked (SIGSEGV under OOM) | High (crash, not corruption) | **FIXED 0.0.49** (fail-closed rc=1) |
| S-002 | cyclic struct not rejected | High (infinite-type) | **FIXED 0.0.48** (rc=7) |
| S-003 | undeclared fn not rejected | Med | **FIXED 0.0.48** (rc=7) |
| S-004 | keyword-hash paren imbalance → wrong lexer hash | **High (silent corruption)** | **FIXED 0.0.53** |
| S-005 | emitted binary missing exec bit | Med (usability) | **FALSE ALARM** — mode 0755 confirmed |
| S-006 | grammar module-parse cascade (~1000/file) | Med (no CI review) | **FIXED 0.0.53** (0 errors) |

---

## 6. Qualification gaps (blockers)

### 6.1 Formal semantics (HIGH)
The language/IR is defined by **emitter behavior**, not by axioms. ISO
qualification requires a precise spec. Partial: `docs/SPEC.md` v0.0.53
captures lex/syntax/type/memory/IR contracts from source. **Still needed:**
operational semantics for IR ops, formal overflow/bounds semantics.

### 6.2 Independent implementation (HIGH for SIL 3–4)
Qualification via "alternative tool" or "increased confidence" routes
benefit from a second, independently-implemented compiler to cross-check.
Quanta has exactly ONE implementation (self-hosting). No independent
validator exists. **Blocks ASIL C–D / SIL 3–4.**

### 6.3 Manual memory model (MED-HIGH)
The native backend emits raw `mmap`/pointer arithmetic with no language
level ownership proof. Even with runtime traps, memory safety is
**enforced at runtime, not proven at compile time**. This is acceptable
for SIL 1–2 (with qualification) but insufficient for SIL 3–4, which
need compile-time guarantees (borrow checking — LANGUAGE_DESIGN.md
Stage 6, NOT yet built).

### 6.4 Process artifacts (MED)
- No requirements traceability matrix (each IR op / builtin → requirement
  → test).
- No documented verification plan beyond the 96-test gate.
- No change-impact analysis procedure.
- No tool-version qualification record per ISO 26262-8 §11.4.

### 6.5 Untested input space (MED)
Fail-closed behavior is proven on 3 specific cases (MAP_FAILED, undeclared
fn, cyclic struct). Unknown/garbage inputs are NOT fuzz-tested. A
fuzzing/adversarial corpus is required before claiming broad input safety.

---

## 7. Roadmap to qualification (recommended sequence)

1. **Close S-006 grammar** (done 0.0.53) → enables CI static analysis.
2. **Write SPEC.md operational semantics for IR** (§6.1) — ongoing.
3. **Add requirements traceability** (each builtin/IR op → test) (§6.4).
4. **Fuzz the compiler** (§6.5) — prove fail-closed on arbitrary input.
5. **Optional borrow checking** (Stage 6) → raises ceiling to SIL 3.
6. **Independent validator / cross-implementation** → required for SIL 4.

---

## 8. Version

Manual corresponds to compiler `0.0.53` (commit `be00162`).
Update on every safety-relevant change; record the defect ID (§5) and
the verification evidence (§4) for each.
