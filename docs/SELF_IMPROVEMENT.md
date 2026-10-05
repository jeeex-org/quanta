## Immediate Next Steps (from `status.json` gaps)

---

1. **Fix `std/json` allocation bug** (OOM on `mem_alloc` size calc) — `status.json`: partial
2. **Implement real `spec_parser`** — Phase 1 SI (read `gap_specs.json` + domain markdown)
3. **Implement real `spec_to_ir`** — map specs → Quanta IR
4. **Flesh out `test_generator`** — emit real const/integration tests
5. **Implement `std/net/http`** — unblocks flintai-cli + Soup
6. **Implement `std/html_parser`** — Soup equivalent
7. **Implement `std/jsonrpc` + `std/lsp`** — Flint LSP
8. **Implement `std/graphics`** — flint-chart (CPU canvas first)
9. **GPU_0.0.001** — Start CUDA target selection (parallel track)
10. **SI codegen loop** — wire E4B CPU path: retrieve from `lib/std/` → generate → `qc` compile gate → feed errors back on fail

Run `scripts/verify_status.quanta` after each implementation to update `status.json` and this document.



# Appended 2026-10-05 — consolidated from three overlapping design docs

`docs/SI_CONTINUOUS.md`, `docs/SKILLS_DESIGN.md` and `docs/BRAIN_DESIGN.md`
all described the same subsystem and were removed to stop three docs drifting
apart. Their unique content is preserved below. **These are designs, not
implemented features** — measured against the tree:

| Artifact | State |
|---|---|
| `gap_specs.json` | exists (repo root and `test_suites/run/`) |
| `lib/std/si_main.quanta` | exists |
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
  the pipeline. It does not get a default that looks like success.
- **Every generated change is gated.** Compile gate, then test gate, then a
  human merge gate. No path writes to `compiler/<VER>/src` directly.
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
