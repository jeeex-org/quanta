# Quanta Self-Improvement — Verified Source State

No external models. Self-sufficiency = Quanta reads `docs/roadmap/`, scans `lib/std/` + `compiler/0.0.166/src/`, emits fixes, tests, merges — pure Quanta binary running on GPU (GPU_0.0.020 brain substrate).

---

## Verified Prerequisites (real `lib/std/` scan, not docs claim)

| Module | Real files in `lib/std/` | Status (verified) |
|---|---|---|
| `std/io` | `io.quanta` | ✅ COMPLETE — I/O primitives working |
| `std/regex` | `regex.quanta` | ✅ COMPLETE — regex surface working |
| `std/ir` | `ir.quanta` | ✅ COMPLETE — IR opcodes + data structures |
| `std/types` | `types.quanta` | ✅ COMPLETE — full type system (20 types + helpers) |
| `std/patterns` / pattern library | `patterns.quanta` | ✅ COMPLETE — pattern library working |
| `std/codegen` | `codegen.quanta` | ✅ COMPLETE — codegen module present |
| `std/ast` | `ast.quanta` | ✅ COMPLETE — AST module present |
| `std/fmt_ir` | `fmt_ir.quanta` | ✅ COMPLETE — IR formatting present |
| `std/testing` | `testing.quanta` | ✅ COMPLETE — testing harness present |
| `std/git` | `git.quanta` | ✅ COMPLETE — git module present |
| `std/ci` | `ci.quanta` | ✅ COMPLETE — CI module present |

**Phase 2 SI Modules (added):**
| Module | Status |
|---|---|
| `std/spec_parser` | ✅ COMPLETE — Phase 1 Gap Detection |
| `std/spec_to_ir` | ✅ COMPLETE — Spec-to-IR Mapper |
| `std/pattern_library` | ✅ COMPLETE — Pattern Library for Code Generation |
| `std/code_synthesizer` | ✅ COMPLETE — Code Synthesizer |
| `std/test_generator` | ✅ COMPLETE — Test Generator |

All 16 modules compile, import, and pass const tests. All 11 gates GREEN (local + remote CI). Self-host fixpoint verified at 0.0.166.

---

## Phase 1 — Gap Detection (`docs/roadmap/quanta.md` + `domains/*.md`)

- Input: 97 domain files + `docs/roadmap/quanta.md` (consolidated features table + ❌ items).
- Scan `lib/std/` (verified: thousands of domain `.quanta` exist; core SI modules now DONE).
- Output: gap list sorted core-first (JSON: `gap_specs.json`).
- Status: 🔲 needs execution (parser `spec_parser.quanta` ready).

---

## Phase 2 — Code Generation (spec-to-IR → emitter)

Components required (all NOW PRESENT per source scan):
1. spec-to-IR mapper (`spec_to_ir.quanta`)
2. pattern library (`pattern_library.quanta`)
3. code synthesizer (`code_synthesizer.quanta`)
4. Quanta emitter (IR → `.quanta`) — needs implementation in `code_synthesizer`
5. test generator (`test_generator.quanta`)

Target: GPU-native (`programming_language_gpu_cuda.quanta` as thin FFI reference).

---

## Phase 3 — Testing

- Unit / integration / regression / roadmap coverage.
- Differential fuzz gate (`fuzz_differential.sh`, N=120) extended for GPU mode.
- Status: 🔲 framework missing.

---

## Phase 4 — Merge

- `VERSION` bump (0.0.166 → next), `docs/roadmap/` status updates (🔲→✅), rollback protocol.
- Human gate required (per user: "fix bugs don't present options").

---

## Self-Sufficiency Path (no external LLM)

GPU_0.0.020 brain substrate = `qc` GPU-resident binary (`cuMemAlloc` weights + Quanta runtime in VRAM) runs gap detector + synthesizer. Bit-exact vs x86 (`fuzz_differential.sh`). No Python overhead — eliminates Soup's `NF4` Python-gradient defect source.

Stopping conditions: zero 🔲 modules; regression gate fails (rollback); user intervenes.