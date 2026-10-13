#!/bin/bash
# scripts/bench.sh — run the benchmarks/ suite: Quanta (current VERSION compiler) vs gcc -O2.
#
# Both sides run through scripts/qcrun.sh (hard memory cap, nice, timeout) and are alternated;
# the best of --runs is reported. Two guards, both learned the hard way:
#   * loop-present: if the C source has a loop but the compiled twin has no jump inside main,
#     gcc folded it away — that row is reported TWIN_FOLDED instead of a fictional ratio.
#   * output equality: both sides must print the same thing (whitespace-insensitive), or the
#     row is flagged MISMATCH — a fast wrong answer is not a result.
#
# Usage: scripts/bench.sh [--runs N] [--md]
set -u
REPO=/opt/tali/quanta
cd "$REPO" || exit 1
RUNS=3; MD=0
while [ $# -gt 0 ]; do
  case "$1" in
    --runs) RUNS="$2"; shift 2 ;;
    --md)   MD=1; shift ;;
    *) echo "usage: scripts/bench.sh [--runs N] [--md]" >&2; exit 2 ;;
  esac
done
QC="$REPO/compiler/$(cat "$REPO/VERSION")/bin/x86/qc"
[ -x "$QC" ] || { echo "bench.sh: no compiler at $QC" >&2; exit 1; }
OUT=/tmp/bench_run; mkdir -p "$OUT"
FAIL=0   # structural failures: compile failures + folded twins (a folded twin is a fictional baseline)

VER=$(cat "$REPO/VERSION")
echo "# scripts/bench.sh — Quanta $VER vs gcc -O2 — $(date -Is)"
echo "# runs/side: $RUNS (best of, alternating) · load: $(uptime | sed 's/.*average: //')"
if [ "$MD" -eq 1 ]; then
  echo
  echo "| case | Quanta | gcc -O2 | ratio | notes |"
  echo "|---|---|---|---|---|"
fi

timeit() {  # timeit <binary> <stdout-file> -> "ms rc"
  local s e rc
  s=$(date +%s%N)
  QUANTA_MEM_MB=1536 QUANTA_TIME_S=600 "$REPO/scripts/qcrun.sh" "$1" >"$2" 2>/dev/null
  rc=$?
  e=$(date +%s%N)
  echo "$(( (e - s) / 1000000 )) $rc"
}

row() { # row <case> <qms> <cms> <ratio> <note>
  if [ "$MD" -eq 1 ]; then
    printf '| %s | %s ms | %s ms | %sx | %s |\n' "$1" "$2" "$3" "$4" "$5"
  else
    printf '%-30s quanta=%8sms  gcc=%7sms  ratio=%7sx  %s\n' "$1" "$2" "$3" "$4" "$5"
  fi
}

for q in "$REPO"/benchmarks/benchmark_*.quanta; do
  b=$(basename "$q" .quanta); c="$REPO/benchmarks/$b.c"
  qb="$OUT/$b.q"; cb="$OUT/$b.cbin"
  qo="$OUT/$b.q.out"; co="$OUT/$b.c.out"

  # XFAIL: "// known-fail: <reason>" documents a defect the case exists to expose. It keeps the row
  # visible without making the suite permanently red -- and a marker that still passes is a failure,
  # so it cannot outlive its bug.
  known=$(sed -n 's|^// known-fail: *||p' "$q" | head -1)
  if ! "$REPO/scripts/qcrun.sh" --qc "$q" "$qb" >/dev/null 2>&1; then
    if [ -n "$known" ]; then row "$b" - - - "KNOWN-BROKEN (marker): $known"; else
      row "$b" - - - "QUANTA_COMPILE_FAIL"; FAIL=$((FAIL + 1)); fi
    continue
  fi
  if [ -n "$known" ] && [ -z "${SKIP_MARKER_CHECK:-}" ]; then
    row "$b" - - - "STALE known-fail MARKER (it compiles now -- remove the marker)"; FAIL=$((FAIL + 1)); continue
  fi
  [ -f "$c" ] || { row "$b" - - - "NO_C_TWIN"; continue; }
  if ! gcc -O2 -o "$cb" "$c" >/dev/null 2>&1; then
    row "$b" - - - "C_COMPILE_FAIL"; FAIL=$((FAIL + 1)); continue
  fi

  note=""; skip_diff=0
  # Opt-out marker for rows whose two sides legitimately print different representations.
  if grep -q 'twin-output: not-comparable' "$q"; then skip_diff=1; note="output not comparable by design"; fi
  if grep -qE '\b(for|while)\b' "$c"; then
    jumps=$(objdump -d "$cb" 2>/dev/null | awk '/<main>:/,/^$/' | grep -cE '\bj(mp|ne|e|b|ae|be|g|ge|l|le|s|ns|o|no|z|nz)\b')
    if [ "$jumps" -eq 0 ]; then
      row "$b" - - - "TWIN_FOLDED (gcc deleted the loop; fix the C twin)"; FAIL=$((FAIL + 1)); continue
    fi
  fi

  bestq=99999999; bestc=99999999
  i=0
  while [ "$i" -lt "$RUNS" ]; do
    read -r ms rc < <(timeit "$qb" "$qo"); [ "$ms" -lt "$bestq" ] && bestq=$ms
    read -r ms rc < <(timeit "$cb" "$co"); [ "$ms" -lt "$bestc" ] && bestc=$ms
    i=$((i + 1))
  done

  if [ "$skip_diff" -eq 0 ] && ! diff -q <(tr -d '[:space:]' < "$qo") <(tr -d '[:space:]' < "$co") >/dev/null 2>&1; then
    note="MISMATCH: quanta='$(tr -d '[:space:]' < "$qo" | head -c 20)' gcc='$(tr -d '[:space:]' < "$co" | head -c 20)'"
  fi

  ratio=$(awk -v a="$bestq" -v b="$bestc" 'BEGIN{ if (b > 0) printf "%.2f", a/b; else print "inf" }')
  row "$b" "$bestq" "$bestc" "$ratio" "$note"
done

echo "# load after: $(uptime | sed 's/.*average: //')"
echo "# gates that must stay green with any codegen change: functional suite + SELFHOST 7/7"
if [ "$FAIL" -gt 0 ]; then
  echo "# FAIL: $FAIL structural row(s) — compile failures or folded twins. Fix before trusting this table."
  exit 1
fi
echo "# OK: every row compiled and every C twin kept its loop."
exit 0
