#!/usr/bin/env bash
# quanta_run.sh — MANDATORY guardrail for EVERY compiled Quanta program.
# ANY binary run without this cap can OOM the host (13-21TB runaways observed)
# and take down Hermes. This is the only sanctioned way to run test binaries.
#
# Hard caps (cannot be raised above safe ceiling via env to avoid foot-shooting):
#   - virtual address space (ulimit -v)  -> kills alloc-runaways before host OOM
#   - wall-clock time      (timeout)     -> kills hangs
#   - low CPU priority     (nice -n 19)  -> can't starve interactive/Hermes
# Runs ONE instance. Never loops.
set -u
# Safe ceiling: a single tiny test must never touch more than 1 GB VSZ.
# Keep this LOW — the runaway t3.bin hit 15 TB; 1 GB is 15000x headroom we don't need.
MEM_LIMIT_MB="${QUANTA_MEM_MB:-768}"
# never allow > 1536 MB regardless of env (foot-gun guard)
[ "$MEM_LIMIT_MB" -gt 1536 ] && MEM_LIMIT_MB=1536
TIME_LIMIT_S="${QUANTA_TIME_S:-15}"
NICE=19
PROG="${1:-}"
[ -n "$PROG" ] || { echo "usage: quanta_run.sh <prog> [args...]" >&2; exit 2; }
[ -x "$PROG" ] || { echo "not executable: $PROG" >&2; exit 2; }
shift
# GitHub Actions checks out the workspace on a filesystem some runners mount
# noexec, so execve() of a test binary living under test_suites/bin/ fails with
# EACCES -> the shell reports rc=127 ("command not found"). The golden `qc` lives
# under compiler/ (exec) so it works; copied test binaries do not. Copy the
# binary to a temp dir that is always exec-capable ($RUNNER_TEMP / /tmp) and run
# from there. This keeps ALL guardrails (ulimit/timeout/nice) intact.
TD="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/quanta_run"
mkdir -p "$TD" 2>/dev/null
EXEC="$(mktemp "$TD/qr.XXXXXX")"
cat "$PROG" > "$EXEC" 2>/dev/null && chmod +x "$EXEC" || EXEC="$PROG"
ulimit -v $((MEM_LIMIT_MB * 1024)) 2>/dev/null   # address-space cap (effective OOM guard)
timeout -k 5 "$TIME_LIMIT_S" nice -n "$NICE" "$EXEC" "$@"
ec=$?
rm -f "$EXEC" 2>/dev/null
case $ec in
  124) echo "[quanta_run] TIMEOUT killed (>${TIME_LIMIT_S}s) — possible hang" >&2;;
  137) echo "[quanta_run] OOM/address-space limit hit (SIGKILL) — runaway contained" >&2;;
esac
exit $ec
