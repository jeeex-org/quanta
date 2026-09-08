# Quanta Independent AI Brain — Design

Learned from DeepSeek Harness (`temp/deepseek-harness/`, everything-is-a-plugin `Cordis` architecture — `packages/core/` session/agent-loop, `packages/llm/` LLM service, `packages/skill/` provider registry, `packages/subagent/` delegation, `packages/self-modification/` agent mounts own plugins, `packages/session/` durable persistence) and Anthropic Cybersecurity Skills (`temp/anthropic-cybersecurity-skills/`, 818 procedural SKILL.md files, flat namespace, framework-mapped, executable — but static/stale-prone). Quanta's brain must be independent of external AI (no DeepSeek API key, no Anthropic dependency) and resilient against staleness.

---

## Independence principle (not copied — designed)

DeepSeek Harness requires `DEEPSEEK_API_KEY` for real API tests (`test:e2e` self-skips without it) and depends on Node ^22.19 || >=24 (`pnpm install`). Anthropic's skills are Markdown documents that decay when framework versions change. Quanta's brain:

1. **Emitted by Quanta compiler** (`qc` at `VERSION` 0.0.166) — not downloaded, not API-called. The brain binary is a compiled `.o` with embedded PTX (GPU_0.0.020 final target) or native x86 ELF (CPU Quanta at 0.0.169+).
2. **Self-hosting fixpoint** (`docs/AUDIT_ROADMAP.md`: self-host verified at 0.0.124+ — `qc` compiles `qc`). The brain runs on the same binary it helps build.
3. **No external LLM provider** — unlike DeepSeek `packages/llm/` which binds to DeepSeek service definition. Quanta's `ai_llm` core (`docs/roadmap/quanta.md`: 0.163–0.172 planned) is native Quanta source (`lib/std/`), not an API wrapper.
4. **No Python** — Anthropic uses `python tools/validate-skill.py`. DeepSeek uses Node/pnpm. Quanta uses `.quanta` source + `qc` binary + `EXPECTED_STDLIB.tsv` gate (pure Quanta, per `SELF_IMPROVEMENT.md` update).

---

## Brain architecture (derived, not copied)

From DeepSeek Harness plugin architecture + Quanta SI prerequisites (`SKILL.md` prerequisites verified at 0.0.166):

```
Quanta Brain Substrate (CPU Quanta 0.0.166 + GPU backend GPU_0.0.020)
├── Core Runtime (compiler/0.0.166/src/x86/ — self-host binary)
│   ├── Spec Parser (std/io + std/regex) → ✅
│   ├── IR system (std/ir + std/types) → ✅
│   ├── Pattern library (std/patterns + std/codegen) → ✅
│   └── Quanta Emitter (compiler + std/ast + std/print) → ✅
├── Brain Engine (new — GPU-resident or CPU-resident binary)
│   ├── ai_llm core (RoPE/RMSNorm/SwiGLU/GQA + KV cache + FlashAttn + BF16 + quantization)
│   │   → implemented as .quanta source in lib/std/, compiled by qc, emitted as native binary
│   ├── Memory / Runtime (fail-closed Valgrind-clean + fuzz-proven — docs/SAFETY_MANUAL.md)
│   └── Self-Improvement Loop (docs/SELF_IMPROVEMENT.md — pure Quanta, no Python)
│       ├── Phase 1: Gap Detection (scans docs/roadmap/domains/*.md vs compiler/ + lib/std/)
│       ├── Phase 2: Code Generation (spec-to-IR → pattern lib → synthesizer → emitter → .quanta source)
│       ├── Phase 3: Testing (EXPECTED_STDLIB.tsv gate — unit + integration + regression + roadmap coverage)
│       └── Phase 4: Merge (VERSION bump + safe merge protocol + rollback — std/git + std/ci)
├── Skill Registry (derived from Anthropic flat namespace — but generated, not authored)
│   ├── skills/DOMAIN.FEATURE/  (e.g., skills/MATH_0.0.001-vector_spaces/)
│   │   ├── SKILL.md  → generated from domain spec (docs/roadmap/domains/*.md) at build time
│   │   ├── references/standards.md → framework mappings (MITRE ATT&CK v19.1, NIST CSF 2.0, D3FEND, ATLAS, AI RMF, F3) computed from STIX bundles at build
│   │   ├── scripts/verify.quanta → executable test script (.quanta, compiled by qc), not .py
│   │   └── assets/template.md → checklist/template derived from spec (optional, only if domain defines)
│   ├── Flat namespace (same as Anthropic — no nesting by category; category in subdomain frontmatter)
│   └── Discovery mechanism (~30 tokens): agent scans skills/*/SKILL.md frontmatter only (name + description + tags + subdomain + framework refs) → selects relevant → loads full body (~500–2000 tokens) only when matched
├── Framework Mapping Engine (build-time derived, not static)
│   ├── MITRE ATT&CK v19.1 (official STIX bundle scanned by build script scripts/gpu_build.sh or scripts/framework_scan.sh)
│   ├── NIST CSF 2.0 / MITRE D3FEND / MITRE ATLAS / MITRE F3 / NIST AI RMF
│   └── Mapping computed: for each skills/*/SKILL.md, extract tags/domain → match against framework technique IDs (T1XXX, F1XXX, etc.) → write references/standards.md
│       → framework versions pinned in build, not in .md file (same mechanism as Anthropic's `mitreattack-python` validation but automated)
├── Durable Session Data (DeepSeek session architecture — docs/session.md: persistence, projection, titles, telemetry)
│   ├── Session persistence: SQLite or file-based (docs/session/), versioned by VERSION
│   ├── Projection: what the agent sees of the world (context from skills + compiler state + framework mappings)
│   └── Stale detection: each session record carries VERSION reference; when VERSION bumps, old session projections are flagged stale and rebuilt automatically (visible failure, not silent decay)
└── Guard Loop (docs/SELF_IMPROVEMENT.md Phase 4 + DeepSeek guard: loop hygiene + timeout)
    ├── Timeout: each skill execution bounded (same as Anthropic verification + DeepSeek timeout plugin)
    ├── Fail-closed: any regression → rollback to previous VERSION binary (VERSION pointer mechanism from user memory: "VERSION should be pointer to latest stable")
    └── Human review gate: Phase 4 merge requires approval (standard for critical systems — user directive: "final binary must be used for testing")
```

---

## Resilience rules (combined best practices + Quanta directives)

1. **No external AI dependency** — brain runs as Quanta binary (`qc` compiled `.quanta` source, GPU-resident via PTX embedded in `.o`, or CPU-resident x86 ELF). No DeepSeek API, no Anthropic Claude, no OpenAI. Confirmed: `docs/SELF_IMPROVEMENT.md` prerequisites (spec parser, code synthesizer, Quanta emitter, test generator, merge automation) are all Quanta modules (`std/io`, `std/ir`, `std/patterns`, `compiler`, `std/git`, `std/ci`) — no external dependency listed.

2. **No Python in loop** — Anthropic uses Python (`python tools/validate-skill.py`, `python process.py`). DeepSeek uses TypeScript/Node (`pnpm`, `node ^22.19`). Quanta loop uses `.quanta` source compiled by `qc`. User directive confirmed: "SI must be pure Quanta, no Python".

3. **Version pointer = single source of truth** — `VERSION` (currently 0.0.166) points to latest stable. All artifacts reference it: `docs/GPU_ROADMAP.md` (milestones GPU_0.0.001–020), `docs/SKILLS_DESIGN.md`, skill SKILL.md frontmatter (`version: 0.0.166`), session projection records. When `VERSION` bumps → all artifacts become visibly stale (not hidden) — forced rebuild is the resilience mechanism.

4. **Static files only as build artifacts** — `skills/` contents are not in `git` source; they are rebuilt by `qc --build-skills`. Source is `docs/roadmap/domains/*.md` + `lib/std/` + `compiler/0.0.166/src/`. Same mechanism as `compiler/${VERSION}/bin/` binary (rebuild from source, verify fixpoint).

5. **Differential verification** — same gate as `fuzz_differential.sh`: for every new brain module (new `skills/DOMAIN.FEATURE/` or updated framework mapping), compile with `qc`, compile reference with previous `VERSION`, compare stdout + exit codes (`N=120` clean). Only if bit-exact: merge.

6. **Stale memory detection automatic** — DeepSeek's session architecture (`packages/session/` persistence + projection) + Quanta SI Phase 1 (gap detection scanning source vs skill registry). If a skill's `references/standards.md` framework version != current framework STIX version, or `SKILL.md` version != `VERSION`, session projection flags it stale. No hidden decay.

---

## Brain evolution pathway (from 0.0.166 to self-evolving)

Current state (`docs/SELF_IMPROVEMENT.md` verified):
- Prerequisites ✅ (Spec Parser, Spec-to-IR mapper, Code synthesizer, Quanta emitter, Test generator, Merge automation) — all at 0.0.166, pure Quanta
- Phase 1 🔲 (gap detection: needs Quanta-native scan of `docs/roadmap/domains/*.md` + `lib/std/` — no Python bootstrap)
- Phase 2 🔲 (code generation: spec-to-IR + pattern lib + synthesizer — prerequisites exist but not fully linked)
- Phase 3 🔲 (testing: `EXPECTED_STDLIB.tsv` exists but brain-specific tests not generated)
- Phase 4 🔲 (merge: `std/git` + `VERSION` bump mechanism exists, brain-specific merge gate not implemented)

Path to brain (GPU_0.0.020 final = brain substrate running on GPU-resident Quanta binary):

```
GPU_0.0.001-003: thin FFI (CUDA lifecycle stub)
GPU_0.0.004-007: emitter + build script (target-independent IR + GPU_BACKEND bit in globals.quanta)
GPU_0.0.008-011: memory model + VRAM safety + differential fuzz (Valgrind-equivalent for GPU)
GPU_0.0.012-016: ai_llm core (RoPE/RMSNorm/SwiGLU/GQA + KV cache + FlashAttn + NF4 dequant — Soup's use case)
GPU_0.0.017-020: SI loop runs on GPU-resident binary → brain evolves itself (pure Quanta, no Python, no external LLM)
```

Each milestone verified by same quality gates as x86 core: `fuzz_differential.sh` clean (`N=120`), `EXPECTED_STDLIB.tsv` 7/7 green, Valgrind-equivalent GPU memory clean (`cuMemRangeIsValid`), VERSION pointer consistent (`0.0.166` → `0.0.169` → `0.1.0` STABLE → `GPU_0.0.020` brain complete).
