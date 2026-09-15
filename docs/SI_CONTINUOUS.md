# Continuous SI Pipeline — Architecture & Design

## Overview

The Continuous SI (Self-Improvement) Pipeline is an autonomous loop that systematically
implements gap specifications from `gap_specs.json`. Each iteration reads the current
state of unimplemented specs, attempts implementation, validates results, and updates
status — ensuring forward progress without human intervention.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Cron / systemd timer (every 15 min)                            │
│                         │                                       │
│                         ▼                                       │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  si_continuous.sh  (one iteration)                       │   │
│  │                                                          │   │
│  │  1. Acquire lock (prevent concurrent runs)               │   │
│  │  2. Read gap_specs.json                                  │   │
│  │  3. Filter unimplemented specs (status = planned)        │   │
│  │  4. For each spec (up to BATCH_SIZE):                    │   │
│  │     a. Generate IR + implementation                      │   │
│  │     b. Compile & test                                    │   │
│  │     c. On success → mark implemented, bump version      │   │
│  │     d. On failure  → mark failed, log, skip              │   │
│  │  5. Write updated gap_specs.json                         │   │
│  │  6. Release lock                                         │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## State Tracking

### Status Values in `gap_specs.json`

| Status       | Meaning                                          |
|--------------|--------------------------------------------------|
| `planned`    | Not yet attempted — eligible for processing      |
| `in_progress`| Currently being worked (lock held)               |
| `implemented`| Implementation passed tests, merged              |
| `failed`     | Implementation attempted but tests failed        |
| `blocked`    | Manual intervention required (e.g. dependency)   |

### State File: `si_state.json`

Tracks pipeline-level metadata (separate from per-spec status):

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

## Iteration Loop

```
START
  │
  ├─ Acquire flock on /tmp/si_continuous.lock
  │  └─ If locked: another instance is running → exit 0
  │
  ├─ Load gap_specs.json (validate JSON)
  │  └─ Invalid → exit 1 (CI should catch this)
  │
  ├─ Select candidate specs:
  │  status == "planned" AND
  │  (failed_count < MAX_RETRIES OR retry_after < now)
  │
  ├─ Sort candidates by priority (lower failed_count first)
  │
  ├─ For each candidate (max BATCH_SIZE per run):
  │  │
  │  ├─ Mark as "in_progress" (atomic)
  │  │
  │  ├─ Generate implementation:
  │  │  └─ Call implementation engine with spec fields
  │  │
  │  ├─ Test:
  │  │  a. Compile with Quanta compiler
  │  │  b. Run auto-generated test suite
  │  │  c. Run integration tests if present
  │  │
  │  ├─ On SUCCESS:
  │  │  ├─ Update status → "implemented"
  │  │  ├─ Set version = current compiler version
  │  │  ├─ Set stdlib = generated file path
  │  │  └─ Log success
  │  │
  │  └─ On FAILURE:
  │     ├─ Increment failed_count
  │     ├─ If failed_count >= MAX_RETRIES → "blocked"
  │     ├─ Else → "failed" (retry next eligible window)
  │     └─ Log failure with stderr capture
  │
  ├─ Write updated gap_specs.json (atomic: write-then-rename)
  │
  ├─ Update si_state.json with run metrics
  │
  └─ Release lock
```

## Success Criteria

A spec is marked `implemented` when ALL of the following hold:

1. **Generation**: `.quanta` file written to `lib/std/` with valid module header
2. **Compilation**: File compiles with `quanta` compiler (exit code 0)
3. **Unit Tests**: Auto-generated const test passes (`return 0`)
4. **Integration**: If `test_suites/codes/` has additional tests, those pass
5. **Idempotency**: Re-running generation produces identical output

## Failure Handling

| Scenario | Action | Retry? |
|----------|--------|--------|
| `gap_specs.json` malformed | Exit 1, alert | No |
| Lock held by another run | Exit 0, next cron tick | Yes |
| Generation produces empty file | Mark failed, log | Yes |
| Compilation fails | Mark failed, capture stderr | Yes (up to MAX_RETRIES) |
| Test assertion fails | Mark failed, capture stdout/stderr | Yes (up to MAX_RETRIES) |
| Disk full / I/O error | Exit 1, abort run | Next tick |
| Max retries exceeded | Mark `blocked`, skip permanently | No |

### Retry Policy

- `MAX_RETRIES = 3` per spec
- Exponential backoff: retry after `2^failed_count` iterations
- `blocked` specs require manual intervention to reset to `planned`

## Rate Limiting

### Per-Run Batch Limit

- `BATCH_SIZE = 5` specs per cron invocation
- Prevents runaway resource consumption
- Allows progress across many cron ticks without blocking

### Global Rate Limiting

- Lock file prevents concurrent execution
- `MAX_RUNTIME_SECONDS = 840` (14 min — less than 15-min cron interval)
  - Hard timeout kills the script if it hangs
  - `trap 'cleanup' EXIT` ensures lock release on timeout

### API / External Call Rate (if applicable)

If the implementation engine calls external APIs:
- `API_RATE_LIMIT = 60` calls per minute
- `API_RETRY_BACKOFF = 5s` initial, doubling up to 60s
- `API_MAX_RETRIES = 3`

## Idempotency

- Re-running on an already-implemented spec: **skip** (file exists)
- Re-running on a `failed` spec: **retry** (under MAX_RETRIES)
- Atomic updates via write-then-rename for both `gap_specs.json` and `si_state.json`
- Each spec processed independently — partial failures don't block others

## Observability

### Log Format

```
[ISO8601] [LEVEL] [RUN_ID] [SPEC] message
```

Example:
```
[2026-09-15T10:30:00Z] [INFO] [run-abc123] [accounting/GAAP/Revenue Recognition] Generated module
[2026-09-15T10:30:02Z] [INFO] [run-abc123] [accounting/GAAP/Revenue Recognition] Compiled OK
[2026-09-15T10:30:03Z] [ERROR] [run-abc123] [accounting/GAAP/Revenue Recognition] Test failed: expected 0 got 1
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success (or idle: no work to do) |
| 1 | Fatal error (config, JSON parse, missing tools) |
| 2 | Partial success (some specs failed but run completed) |

## Wiring: Cron Configuration

```bash
# /etc/cron.d/si_continuous  (run every 15 min)
*/15 * * * * tali /opt/tali/quanta/scripts/si_continuous.sh >> /opt/tali/quanta/logs/si_continuous.log 2>&1
```

## Wiring: systemd Timer (Preferred)

### `/etc/systemd/system/si-continuous.service`
```ini
[Unit]
Description=Continuous SI Pipeline
After=network.target

[Service]
Type=oneshot
ExecStart=/opt/tali/quanta/scripts/si_continuous.sh
User=tali
WorkingDirectory=/opt/tali/quanta
StandardOutput=append:/opt/tali/quanta/logs/si_continuous.log
StandardError=append:/opt/tali/quanta/logs/si_continuous_error.log
TimeoutStartSec=840
```

### `/etc/systemd/system/si-continuous.timer`
```ini
[Unit]
Description=Run SI Pipeline every 15 minutes

[Timer]
OnCalendar=*:0/15
Persistent=true

[Install]
WantedBy=timers.target
```

### Enable:
```bash
systemctl daemon-reload
systemctl enable --now si-continuous.timer
systemctl list-timers si-continuous.timer  # verify
```

## Future Enhancements

- **Priority queue**: Process high-value specs first based on a `priority` field
- **Dependency graph**: Respect inter-spec dependencies before implementation
- **Metrics**: Prometheus endpoint tracking `specs_implemented_total`, `specs_failed_total`, `iteration_duration_seconds`
- **Slack/alert notification** on `blocked` status or consecutive failure threshold
- **Git integration**: Auto-commit successful implementations with spec metadata
