#!/bin/bash
# Run the 12-gate suite with all output captured, and print ONLY the summary.
# Prevents megabytes of test chatter from reaching the agent context.
ulimit -c 0
ulimit -v 68719476736
ulimit -t 3000
# The gguf-corrupt stage copies a 1.67 GB fixture 7 times; the guard stage
# verifies the documented entry point's file-size limit permits that. The
# bisected minimum VA for the compiler is 1,006,640 KB; the model is 1,674,455,072 B.
# 8,388,608 blocks * 1024 = 8,589,934,592 B = 8 GiB (5.1x the largest fixture).
ulimit -f 8388608
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
