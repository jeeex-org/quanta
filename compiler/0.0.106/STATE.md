# Quanta 0.0.106 — Release State

- **Version:** 0.0.106
- **Date:** 2026-08-27
- **Source entry:** `compiler/0.0.106/src/x86/main.quanta` (16 modules)
- **Build seed:** 0.0.105 (`compiler/0.0.105/bin/x86/qc`)
- **Compiler binary:** `compiler/0.0.106/bin/x86/qc`
- **Self-host fixpoint:** byte-identical stage1 (seed-built) == stage2 (self-built), md5 `a69a2d2702a401ceb17925abd3676090` (verified 2026-08-27).
- **Core letter (per user):** G core (networking).

## What landed in 0.0.106

Five networking builtins added to `is_bltn` (features.quanta) and `emit_bltn` (emitter.quanta), as raw Linux syscalls:

- `socket(domain, type, proto)` → fd        (sc 41)
- `connect(fd, sa_ptr, len)` → 0/-errno      (sc 42)
- `bind(fd, sa_ptr, len)` → 0/-errno         (sc 49)
- `listen(fd, backlog)` → 0/-errno           (sc 50)
- `accept(fd, sa_ptr, len_ptr)` → newfd       (sc 43)

Convention: `IR_CALL` already loads args 0/1/2 into rdi/rsi/rdx (same as the
existing `file_open` block). Each networking builtin does `flush_all()`,
`ri(0, <sc-num>)` (rax = syscall number), and `sysc()` (the `0F 05`
instruction). The kernel result lands in rax and is returned. No separate
syscall-register reload needed for the ≤3-arg forms.

`is_bltn` entries use exact name-length checks (socket=6, connect=7, bind=4,
listen=6, accept=6) — counted carefully (no phantom trailing chars, unlike the
0.0.105 atomic bring-up bug).

## Gate status (verified, all GREEN)
- functional: 139/139 core (EXPECTED.tsv) — `net_test` added (rc=11) → 139 codes, 139 expected
- extern-c: GREEN (object-mode + gcc libc link)
- security: GREEN (KNOWN bugs reported by script, not blocking)
- performance: GREEN
- valgrind: GREEN (compiler binary leak/error scan, 0 errors)
- fuzz: GREEN (fail-closed, 0 crashes)
- differential: GREEN (opt -O == no-O + vs-seed)
- generics-negative: GREEN
- self-host fixpoint: stage1 == stage2 byte-identical (md5 `a69a2d2702a401ceb17925abd3676090`)

## ROADMAP / FEATURES sync
ROADMAP 0.0.106 → ✅: networking (5/5 builtins) GREEN, gated by `net_test`.
FEATURES §networking: socket/connect/bind/listen/accept ✅ 5/5 gated.

## Repo hygiene
- `bin/qc` does not exist in project root (per rule).
- Each version in its own `compiler/<VER>/` folder, copied from previous stable seed.
- `src/` source-only; `bin/` holds the promoted seed (tracked).
- All test binaries run via `scripts/quanta_run.sh` (address-space + time caps).
