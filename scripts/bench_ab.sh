#!/bin/bash
# scripts/bench_ab.sh — A/B two QUANTA compilers on the benchmarks/ suite.
#
# WHY THIS EXISTS
# ---------------
# `scripts/bench.sh` reports quanta_time / gcc_time. The gcc twin is the SAME
# source and the SAME binary in both runs, yet its best-of-3 swings by up to 40%
# on short rows (measured 10ms -> 6ms, 8ms -> 6ms, 5ms -> 8ms on identical C
# binaries). On a row that takes 6-25 ms that denominator noise is larger than
# the effect being measured, so a ratio table alone cannot say whether a codegen
# change helped or hurt.
#
# This script removes BOTH sources of confusion:
#   * the gcc denominator (it compares two Quanta binaries, same source);
#   * cross-run load drift (the two binaries are run INTERLEAVED in one process
#     loop, best-of-N and median-of-N both reported).
#
# It also reports whether the two compilers even produced the same machine code.
# If the binaries are byte-identical the delta is noise BY DEFINITION, which is
# the cheapest possible explanation to test and the one most often ignored.
#
# Usage: scripts/bench_ab.sh <qcA> <qcB> [--runs N] [--only a,b,c]
set -u
REPO=/opt/tali/quanta
cd "$REPO" || exit 1
RUNS=15; ONLY=""
A="${1:-}"; B="${2:-}"; shift 2 2>/dev/null || true
while [ $# -gt 0 ]; do
  case "$1" in
    --runs) RUNS="$2"; shift 2 ;;
    --only) ONLY="$2"; shift 2 ;;
    *) echo "usage: scripts/bench_ab.sh <qcA> <qcB> [--runs N] [--only a,b,c]" >&2; exit 2 ;;
  esac
done
[ -x "$A" ] && [ -x "$B" ] || { echo "bench_ab.sh: need two executable compilers" >&2; exit 1; }
OUT=/tmp/bench_ab; rm -rf "$OUT"; mkdir -p "$OUT"

echo "# scripts/bench_ab.sh — QUANTA A/B (same source, no gcc denominator)"
echo "# A = $A"
echo "# B = $B"
echo "# runs/side: $RUNS interleaved (best-of and median-of reported) · load: $(uptime | sed 's/.*average: //')"
printf '%-30s %8s %8s %8s %8s %8s %8s  %s\n' case A_best B_best A_med B_med best_d% med_d% verdict

timeit() { # timeit <binary> -> ms
  local s e
  s=$(date +%s%N)
  QUANTA_MEM_MB=1536 QUANTA_TIME_S=600 "$REPO/scripts/qcrun.sh" "$1" >/dev/null 2>&1
  e=$(date +%s%N)
  echo $(( (e - s) / 1000000 ))
}

for q in "$REPO"/benchmarks/benchmark_*.quanta; do
  b=$(basename "$q" .quanta); short="${b#benchmark_}"
  if [ -n "$ONLY" ] && ! printf '%s' ",$ONLY," | grep -q ",$short,"; then continue; fi
  "$A" "$q" "$OUT/$short.A" >/dev/null 2>&1 || { printf '%-30s %s\n' "$short" COMPILE_FAIL_A; continue; }
  "$B" "$q" "$OUT/$short.B" >/dev/null 2>&1 || { printf '%-30s %s\n' "$short" COMPILE_FAIL_B; continue; }
  ident=no; cmp -s "$OUT/$short.A" "$OUT/$short.B" && ident=yes

  at=(); bt=()
  i=0
  while [ "$i" -lt "$RUNS" ]; do
    at+=("$(timeit "$OUT/$short.A")")
    bt+=("$(timeit "$OUT/$short.B")")
    i=$((i + 1))
  done
  stats() { printf '%s\n' "$@" | sort -n | awk '{v[NR]=$1} END{printf "%d %d", v[1], v[int((NR+1)/2)]}'; }
  read -r ab am <<< "$(stats "${at[@]}")"
  read -r bb bm <<< "$(stats "${bt[@]}")"
  bd=$(awk -v x="$ab" -v y="$bb" 'BEGIN{printf "%+.1f", (y-x)*100/x}')
  md=$(awk -v x="$am" -v y="$bm" 'BEGIN{printf "%+.1f", (y-x)*100/x}')
  if [ "$ident" = yes ]; then verdict="IDENTICAL-CODE (delta is noise)"; else verdict="code differs"; fi
  printf '%-30s %8s %8s %8s %8s %8s %8s  %s\n' "$short" "$ab" "$bb" "$am" "$bm" "$bd" "$md" "$verdict"
done
echo "# load after: $(uptime | sed 's/.*average: //')"
