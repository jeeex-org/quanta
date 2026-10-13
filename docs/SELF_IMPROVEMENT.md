# Quanta Self-Improvement (SI) — measured state

**This document is derived from `docs/status.json`.** Do not hand-edit the numbers
below; regenerate with:

    bash scripts/regen_status.sh          # writes docs/status.json + docs/status.md

Freshness is enforced by the gate: stage 12 (`test_suites/scripts/verify_status.quanta`)
fails closed if `docs/status.json` is missing, malformed, or older than 30 days.
(An older revision of this file pointed at `scripts/verify_status.quanta`; the
canonical, CI-tracked path is `test_suites/scripts/verify_status.quanta`.)

---

## Delivery ratio (derived)

| metric | value |
|---|---|
| gap_specs specs | 9026 |
| distinct domains | 97 |
| distinct categories | 2163 |
| distinct modules named | **5505** |
| modules with a real implementation in `lib/std` | **22** |
| **delivery ratio** | **0.4 %** (22 / 5505) |
| `lib/std` real modules (no stubs) | 165 |
| `test_suites/codes` tests | 619 |
| planned stubs — `planned/lib_std` | 9237 |
| planned tests — `planned/tests` | 16861 |
| `planned/INDEX.tsv` manifest rows | 26098 |

"A module is delivered" = its slug is literally a file in `lib/std`
(e.g. spec module `QUIC` → `lib/std/quic.quanta`). This is the convention the 22
delivered modules actually use; the generated `domain_category_module` form was
never the delivered shape. Full per-domain table: `docs/status.md`.

## Immediate next steps (corrected)

Items 2–4 below were listed as TODO in an earlier revision although the modules
have existed since 0.0.178. Marked done, with paths:

1. ~~Implement real `spec_parser`~~ — **DONE**: `lib/std/spec_parser.quanta` (187 lines).
2. ~~Implement real `spec_to_ir`~~ — **DONE**: `lib/std/spec_to_ir.quanta` (193 lines).
3. ~~Flesh out `test_generator`~~ — **DONE**: `lib/std/test_generator.quanta` (262 lines).
4. **`std/json` / `std/vec` array cap — the real blocker.** `std/vec.vec_new()`
   allocates a **fixed 64-slot** vector and `vec_push()` *silently drops* pushes
   past capacity (`if len < cap`). `std/json` parses arrays with it, so
   `json_array_len(gap_specs.json.specs)` returns **64**, not 9026 — every
   json-based SI stage can only ever see the first 64 specs. The earlier note
   ("mem_alloc size calc / OOM") was wrong; there is no OOM. Fixing this (a
   growable vector, or driving `json` with `vec_set` + an explicit counter) is the
   single change that unblocks the json paths.
5. **Implement `std/net/http`** — MISSING. Unblocks flintai-cli + Soup.
6. **Implement `std/html_parser`** — MISSING. Soup equivalent.
7. **Implement `std/jsonrpc` + `std/lsp`** — MISSING. Flint LSP.
8. **Implement `std/graphics`** — MISSING. flint-chart (CPU canvas first).
9. **GPU_0.0.001** — start CUDA target selection (parallel track).
10. **SI codegen loop** — wire the CPU path end to end. What runs today:
    `lib/std/code_synthesizer.quanta` (286 lines) does **not** use `std/json`; it
    scans `gap_specs.json` byte-by-byte and generates all **9026** module stubs
    into the CWD-relative staging dir `synth_out/` (never a tracked tree — see
    `SYNTH_OUT_ROOT`). The json-based stages (`spec_parser` → `spec_to_ir` →
    `test_generator` → `si_main`) stop at the 64-spec cap above. `si_main.quanta`
    claims to "run until all planned specs implemented, compiles generated code,
    runs tests, auto-updates status"; it does none of those yet (see the header
    note in that file).

---

# Appended 2026-10-05 — consolidated from three overlapping design docs

`docs/SI_CONTINUOUS.md`, `docs/SKILLS_DESIGN.md` and `docs/BRAIN_DESIGN.md`
all described the same subsystem and were removed to stop three docs drifting
apart. Their unique content is preserved below. **These are designs, not
implemented features** — measured against the tree:

| Artifact | State |
|---|---|
| `gap_specs.json` | exists (repo root; `test_suites/run/gap_specs.json` is a symlink) |
| `planned/INDEX.tsv` | exists (26098 rows; the moved planning tree) |
| `lib/std/spec_parser.quanta` | exists (187 lines) |
| `lib/std/spec_to_ir.quanta` | exists (193 lines) |
| `lib/std/pattern_library.quanta` | exists (105 lines) |
| `lib/std/code_synthesizer.quanta` | exists (286 lines; stages to `synth_out/`) |
| `lib/std/test_generator.quanta` | exists (262 lines; stages to `synth_out/tests/`) |
| `lib/std/si_main.quanta` | exists (109 lines; header claims corrected) |
| `scripts/si_generate.sh` | exists (stages to `synth_out/`) |
| `scripts/si_pipeline.sh` | exists (stages to `synth_out/`) |
| `scripts/si_continuous.sh` | exists (stages to `synth_out/`) |
| `scripts/regen_status.sh` | exists (regenerates `docs/status.json`) |
| `test_suites/scripts/verify_status.quanta` | exists (gate freshness check) |
| `si_state.json` | **does not exist** |
| `si/retriever.quanta` | **does not exist** |
| `si/prompt.quanta` | **does not exist** |
| `si/gate.quanta` | **does not exist** |
| `si/merge.quanta` | **does not exist** |

The pipeline below is specified but not built. Treat it as a target, not a
description of current behaviour.

## Continuous iteration loop (from SI_CONTINUOUS.md)

### Gap-spec status values

| Status | Meaning |
|---|---|
| `planned` | Not yet attempted — eligible for processing |
| `in_progress` | Currently being worked (lock held) |
| `implemented` | Implementation passed tests, merged |
| `failed` | Attempted but tests failed |
| `blocked` | Manual intervention required (e.g. dependency) |

### Pipeline state file: `si_state.json` (not yet created)

Tracks pipeline-level metadata, separate from per-spec status:

```json
{
  "last_run": "2026-09-15T10:30:00Z",
  "last_run_status": "ok",
  "total_iterations": 42,
  "specs_implemented_this_run": 3,
  "consecutive_failures": 0,
  "lock_held_by": null
}
```

### Loop

```
START
  ├─ flock /tmp/si_continuous.lock
  │    └─ already locked → another instance runs → exit 0
  ├─ Load gap_specs.json (validate JSON) — invalid → exit 1
  ├─ Select candidates: status == "planned"
  │    AND (failed_count < MAX_RETRIES OR retry_after < now)
  ├─ Sort by priority (lower failed_count first)
  ├─ For each candidate (max BATCH_SIZE per run):
  │    ├─ Mark "in_progress" (atomic)
  │    ├─ Generate implementation via the implementation engine
  │    ├─ Test
  │    ├─ On pass → "implemented"; on fail → "failed" + failed_count++
  └─ Write back atomically (write-then-rename)
```

## Resilience rules (from SKILLS_DESIGN.md + BRAIN_DESIGN.md)

Combined, and explicitly *not* copied from any external system — designed for
Quanta's constraints:

- **Fail closed, never fail open.** A missing, malformed or stale artifact stops
  the pipeline. It does not get a default that looks like success. (The gate's
  status stage now enforces this for `docs/status.json`.)
- **Every generated change is gated.** Compile gate, then test gate, then a
  human merge gate. No path writes to `compiler/<VER>/src` directly.
- **Generated stubs never live in a source tree.** The generator's output root is
  the one named constant `SYNTH_OUT_ROOT` ("synth_out", git-ignored); the planned
  population is under `planned/` with `planned/INDEX.tsv`. `lib/std` and
  `test_suites/codes` hold only real implementations and tests.
- **Skills are data, not code.** A skill is a spec plus its tests; the runner is
  fixed. This is what makes the self-improvement loop auditable.
- **No external LLM required.** The self-sufficiency path must run without one.
  An external model is an accelerator, never a dependency.
- **Bounded and observable.** Every iteration records what it did and why, so a
  failing run is diagnosable rather than merely detectable.

## Independence principle

The AI brain is derived from Quanta's own verified source state and the
requirements of self-hosting, not copied from another project's architecture.
Where a practice was adopted, the doc said so; where it was rejected, it said
why.
