#!/bin/bash
# Run the 12-gate suite with all output captured, and print ONLY the summary.
# Prevents megabytes of test chatter from reaching the agent context.
ulimit -c 0
ulimit -v 68719476736
ulimit -t 3000
ulimit -f 1048576
REPO=$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)
# Read VERSION rather than hardcoding a tree: a pinned old compiler makes a gate
# report about a compiler nobody is shipping. Same bug as build_one.sh.
V=$(cat "$REPO/VERSION")
cd "$REPO" || exit 1
LOG=${1:-/tmp/g9/gate.log}
QC="$REPO/compiler/$V/bin/x86/qc" FUZZ_ITER=200 timeout 1200 bash test_suites/scripts/run_tests.sh > "$LOG" 2>&1
rc=$?
green=$(grep -c ': GREEN' "$LOG")
red=$(grep -c ': RED' "$LOG")
echo "gate_rc=$rc green=$green red=$red"
sed -n '/=== GATE SUMMARY ===/,$p' "$LOG" | head -15
