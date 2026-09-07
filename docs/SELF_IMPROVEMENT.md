# Quanta Self-Improvement — Verified Source State

No external models. Self-sufficiency = Quanta reads `docs/roadmap/`, scans `lib/std/` + `compiler/0.0.166/src/`, emits fixes, tests, merges — pure Quanta binary running on GPU (GPU_0.0.020 brain substrate).

---

## Verified Prerequisites (real `lib/std/` scan, not docs claim)

|| Module | Real files in `lib/std/` | Status (verified) ||
||---|---|---||
|| `std/io` | many `.quanta` (io-related) | PARTIAL — I/O primitives present, markdown parser MISSING |
|| `std/regex` | `programming_language_regex_*.quanta` patterns present | PARTIAL — regex surface exists; full parser MISSING |
|| `std/ir` | none named `ir` | MISSING |
|| `std/types` | `programming_language.md` token module (line 354) referenced; no `types.quanta` | MISSING |
|| `std/patterns` / pattern library | none | MISSING |
|| `std/codegen` | none | MISSING |
|| `std/ast` + `std/fmt_ir` | none | MISSING |
|| `std/testing` | `test_suites/EXPECTED_STDLIB.tsv` (9026 rows) exists; harness MISSING | PARTIAL |
|| `std/git` | none | MISSING |
|| `std/ci` | `.github/` exists; Quanta-native CI MISSING | MISSING |

Previous doc falsely claimed "ALL DONE ✅". Real state above — no fabrication.

---

## Phase 1 — Gap Detection (`docs/roadmap/quanta.md` + `domains/*.md`)

- Input: 97 domain files + `docs/roadmap/quanta.md` (197 lines).
- Scan `lib/std/` (verified: thousands of domain `.quanta` exist but core SI modules missing).
- Output: gap list sorted core-first (same format as doc line 43).
- Status: 🔲 needs pure Quanta parser (not Python).

---

## Phase 2 — Code Generation (spec-to-IR → emitter)

Components required (all MISSING per source scan):
1. spec-to-IR mapper
2. pattern library
3. code synthesizer
4. Quanta emitter (IR → `.quanta`)
5. test generator

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
