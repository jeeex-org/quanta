#!/bin/bash
# scripts/qcrun.sh -- the ONLY sanctioned way to run a Quanta compiler or a
# compiled Quanta binary from a shell or agent.
#
# RELEASE_CHECKLIST rule #14. A raw run of an untrusted/unverified .bin has
# produced 13-21 TB VSZ runaways and taken down the host (OOM-killed Hermes).
# This wrapper makes the cap structural instead of a thing to remember:
#
#   ulimit -c 0   no core dumps (a single c1.core here was 1.0 GB)
#   ulimit -v     address-space ceiling; an oversized alloc now fails fast
#                 instead of thrashing
#   nice -n 19    cannot starve interactive work / the agent backend
#   timeout       a hang costs seconds, not a wedged session
#
# Caps are hard: QUANTA_MEM_MB is clamped, so raising the env var past the
# ceiling is ignored by design rather than by trust.
#
# Usage:
#   scripts/qcrun.sh <program> [args...]      run one compiled binary
#   scripts/qcrun.sh --qc <src> <out>         compile with the VERSION compiler
#
# Never gdb a compiled binary (~1.5 GB, disrupts the backend). Disassemble
# statically instead:
#   objdump -D -b binary -m i386:x86-64 --start-address=0x400120 FILE

set -u

# hard ceilings -- an env var may lower these, never raise them
MEM_LIMIT_MB="${QUANTA_MEM_MB:-1024}"
[ "$MEM_LIMIT_MB" -gt 1536 ] && MEM_LIMIT_MB=1536

# The COMPILER needs its own ceiling: it mmaps arenas and dies SILENTLY below ~6 GB
# (no output, no binary, exit 0). Measured 0.0.225: fails at 1536 MB and 3072 MB,
# succeeds at 6144 MB. 0.0.259 reclaim reduced the minimum VA to 1,006,640 KB; the
# ceiling is now 1536 MiB (1,572,864 KB) with 56% margin. Do not reuse MEM_LIMIT_MB
# here -- that is the ceiling for compiled BINs, which need about 1 GB.
COMPILER_MEM_MB="${QUANTA_CC_MEM_MB:-1536}"
TIME_LIMIT_S="${QUANTA_TIME_S:-15}"
NICE=19

REPO="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"

# no core dumps under any circumstance (some sandboxes deny this; not fatal)
ulimit -c 0 2>/dev/null || true

apply_cap() {
  ulimit -v $((MEM_LIMIT_MB * 1024)) 2>/dev/null || true
}

if [ "${1:-}" = "--qc" ]; then
  # compile mode: cap the COMPILER too (it reads the 1.6 GB GGUF)
  shift
  [ $# -lt 2 ] && { echo "usage: qcrun.sh --qc <src> <out>" >&2; exit 2; }
  src="$1"; out="$2"
  QC="${QC:-$REPO/compiler/$(cat "$REPO/VERSION")/bin/x86/qc}"
  [ -x "$QC" ] || { echo "no compiler at $QC" >&2; exit 1; }
  ulimit -v $((COMPILER_MEM_MB * 1024)) 2>/dev/null || true
  exec timeout "${QUANTA_COMPILE_S:-300}" "$QC" "$src" "$out"
fi

# =====================================================================
# --ccrun <src> [args...] : COMPILE *AND* RUN, as one atomic step.
#
# WHY THIS EXISTS (do not remove -- it closes a real defect, twice hit):
# invoked separately, `qc src out` COMPILES and exits 0; it does not run the
# program. Both times the compile step's exit 0 was read as "the test passed",
# and two genuine defects were reported as "mutation survives / already fixed"
# off evidence that never executed a byte. This mode makes that unreachable:
# there is no code path here that reports success without the binary having run.
#
# It also enforces the invariants that a hand-rolled invocation drops:
#   * the compiler gets COMPILER_MEM_MB (below ~6 GB it dies SILENTLY: no
#     output, no binary, exit 0)
#   * the compiled binary gets the much lower MEM_LIMIT_MB
#   * a missing binary, or a compile failure, is a non-zero exit -- never a pass
# =====================================================================
if [ "${1:-}" = "--ccrun" ]; then
  shift
  [ $# -lt 1 ] && { echo "usage: qcrun.sh --ccrun <src> [args...]" >&2; exit 2; }
  src="$1"; shift
  QC="${QC:-$REPO/compiler/$(cat "$REPO/VERSION")/bin/x86/qc}"
  [ -x "$QC" ] || { echo "no compiler at $QC" >&2; exit 1; }
  td="$(mktemp -d "${TMPDIR:-/tmp}/ccrun.XXXXXX")" || exit 1
  bin="$td/prog"
  ( ulimit -v $((COMPILER_MEM_MB * 1024)) 2>/dev/null
    timeout "${QUANTA_COMPILE_S:-300}" "$QC" "$src" "$bin" "$@" )
  crc=$?
  if [ $crc -ne 0 ]; then
    echo "[ccrun] COMPILE FAILED rc=$crc (NOT a pass)" >&2; rm -rf "$td"; exit $crc
  fi
  if [ ! -x "$bin" ]; then
    echo "[ccrun] NO BINARY PRODUCED (NOT a pass)" >&2; rm -rf "$td"; exit 1
  fi
  ( ulimit -v $((MEM_LIMIT_MB * 1024)) 2>/dev/null
    timeout -k 5 "$TIME_LIMIT_S" nice -n "$NICE" "$bin" )
  rrc=$?
  rm -rf "$td"
  case $rrc in
    124) echo "[ccrun] TIMEOUT killed (>${TIME_LIMIT_S}s)" >&2;;
    137) echo "[ccrun] OOM/address-space limit hit (SIGKILL)" >&2;;
  esac
  exit $rrc
fi

PROG="${1:-}"
[ -n "$PROG" ] || { echo "usage: qcrun.sh <program> [args...]" >&2; exit 2; }
shift

if [ ! -x "$PROG" ]; then
  echo "not executable: $PROG" >&2
  exit 126
fi

apply_cap
# nice may be denied in some containers; the caps above still apply.
exec timeout "$TIME_LIMIT_S" nice -n "$NICE" "$PROG" "$@"