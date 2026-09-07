# Quanta Self-Improvement

## How Quanta reads its own gaps, generates code, tests, and merges.

---

## Prerequisites (build before SI runs) — ✅ ALL DONE

Quanta can only self-improve when its core subsystems are in place. These are the **hard prerequisites** before the self-improvement loop can run:

| SI Component | Prerequisite | Quanta Module | Status |
|---|---|---|---|
| Spec Parser | stdlib I/O + markdown parser | `std/io` + `std/regex` | ✅ |
| Spec-to-IR mapper | IR + type system stable | `std/ir` + `std/types` | ✅ |
| Code synthesizer | Pattern library + codegen | `std/patterns` + `std/codegen` | ✅ |
| Quanta emitter | Compiler + AST + printer | `compiler` + `std/ast` + `std/fmt_ir` | ✅ |
| Test generator | Test harness + EXPECTED.tsv | `std/testing` + `test/` | ✅ |
| Merge automation | Git integration + CI | `std/git` + `std/ci` | ✅ |

All prerequisites completed at 0.0.166.

---

## Phase 1: Gap Detection — TODO

Quanta reads its own source code and roadmap to identify what's missing.

### Input Sources
- `docs/roadmap/quanta.md` — what Quanta itself must implement
- `docs/roadmap/domains/` — what Quanta must support
- `compiler/0.0.166/src/` — current compiler source
- `lib/std/` — current stdlib implementations
- `test/` — existing test coverage

### Process
1. Parse roadmap markdown tables → extract all 🔲 planned modules
2. Scan `lib/std/` for existing implementations → mark ✅ done
3. Scan compiler source for keyword/builtin support → mark ✅ done
4. Cross-reference test files → identify untested modules
5. Output: gap list sorted by priority (core first, then domains)

### Output Format
```
GAP: std/math/statistics/bayesian
  Roadmap: mathematics.md → stats/bayesian → 🔲 planned
  Source: lib/std/math.quanta → no bayesian functions
  Tests: test/expect_math.tsv → no bayesian rows
  Priority: HIGH (core math, blocks many domains)
```

---

## Phase 2: Code Generation — TODO

Quanta generates code for identified gaps.

### Required Components
1. **spec-to-IR mapper** — converts roadmap module spec → Quanta IR
2. **pattern library** — known implementations for similar modules
3. **code synthesizer** — generates IR from pattern + spec
4. **Quanta emitter** — emits IR → `.quanta` source
5. **test generator** — generates test cases from spec

### Generation Flow
```
Roadmap spec → spec-to-IR mapper → IR
IR + pattern library → code synthesizer → synthesized IR
Synthesized IR → Quanta emitter → .quanta source
Roadmap spec → test generator → test cases
```

### Quality Gates
- Generated code must pass existing tests
- Generated code must compile with `qc`
- Generated code must match roadmap spec
- No regressions in existing modules

---

## Phase 3: Testing — TODO

Quanta tests its own generated code.

### Test Levels
1. **Unit tests** — per-module, from test generator
2. **Integration tests** — module interactions
3. **Regression tests** — existing test suite
4. **Roadmap coverage** — every 🔲 module has tests

### Pass Criteria
- All existing tests pass (no regressions)
- New module tests pass
- Coverage ≥ 80% for new code
- Roadmap 🔲 count decreases

---

## Phase 4: Merge — TODO

Quanta merges generated code into the main codebase.

### Merge Checklist
- [ ] Code compiles with `qc`
- [ ] All tests pass
- [ ] Roadmap status updated (🔲 → ✅)
- [ ] Version bumped in `VERSION`
- [ ] No regressions

---

## Self-Improvement Loop

```
Detect Gaps → Generate Code → Test → Merge → Detect Gaps → ...
```

### Stopping Conditions
- No 🔲 modules remain in roadmap
- User intervenes
- Quality gate fails (regression detected)

### Human Oversight
- Phase 1 (gap detection) — automatic
- Phase 2 (code generation) — human reviews before merge
- Phase 3 (testing) — automatic
- Phase 4 (merge) — human approves

---

## Current Status

| Phase | Status |
|-------|--------|
| Phase 1: Gap Detection | 🔲 Not implemented in Quanta — pure Quanta implementation required, no Python |
| Phase 2: Code Generation | 🔲 Not implemented in Quanta |
| Phase 3: Testing | 🔲 Not implemented in Quanta |
| Phase 4: Merge | 🔲 Not implemented in Quanta |

### Immediate Next Steps
1. Port gap detector to Quanta — pure Quanta, no Python bootstrap
2. Build pattern library from existing stdlib
3. Create spec-to-IR mapper for simple modules
4. Implement test generator in Quanta
5. Build Quanta emitter (IR → .quanta source)

---

## Architecture Notes

- Quanta compiler at `compiler/0.0.166/`
- Stdlib at `lib/std/`
- Roadmap at `docs/roadmap/`
- Tests at `test_suites/`
- VERSION at `VERSION` (0.0.166)

### Key Files
- `compiler/0.0.166/src/x86/` — 16 .quanta source files
- `lib/std/` — stdlib implementations
- `test_suites/EXPECTED_STDLIB.tsv` — 9026 expected test results
- `docs/roadmap/quanta.md` — 97 domain roadmaps
- `docs/roadmap/domains/*.md` — 97 domain files with module tables