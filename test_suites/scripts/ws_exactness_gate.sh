#!/bin/bash
# --- Stage 1.6p: WORK-STEALING EXACTNESS GUARD --------------------------------
# The loader's decode pool partitions rows across workers. Before 0.0.259 the
# only safe spelling was a STATIC row slice; an attempt at a stolen (dynamic)
# claim measured **931 of 2048 rows silently wrong**, and another shape hung
# (rc 124).
#
# That was NOT a race and NOT a missing capability. It was A39, a `&global`
# MISCOMPILE: `&global` returned the address of an IR_LOADG TEMPORARY, so
# `atomic_add(&g, 1)` returned 0 on EVERY call and left `g` at 0 -- a claimed
# row was never written, and a claim loop could not terminate. 0.0.259 fixed
# address-of resolution in the parser (`gfind` -> `IR_PTR_CAST.a1`), and the
# static slice turned out to be a workaround for that miscompile rather than a
# property of the atomics.
#
# RED-FIRST: on 0.0.258 / any pre-A39 spelling, Part A reports rows claimed 0
# times or twice, and Part B's diff_bits are non-zero. On 0.0.259+ every row is
# claimed exactly once, and the stolen partition is BIT-IDENTICAL to the static
# one and to the reference.
#
# These are hard assertions, not ratios. For every arm: 2048 rows, diff_bits all
# zero between reference/static/stolen in raw u64, and a claim counter that
# advances by exactly the number of rows claimed.
#
# Usage: bash test_suites/scripts/ws_exactness_gate.sh
#   QC=<path to qc> to pin a compiler; otherwise VERSION selects the tree.
set -u

REPO=$(cd "$(dirname "$(readlink -f "$0")")/../.." && pwd)
QC=${QC:-"$REPO/compiler/$(cat "$REPO/VERSION" 2>/dev/null)/bin/x86/qc"}
SRC="$REPO/tests/lfm2_worksteal_test.quanta"
W=/tmp/ws_exactness_gate

rm -rf "$W"; mkdir -p "$W"

if [ ! -x "$QC" ]; then
  echo "  FAIL ws-exactness: no compiler at $QC"
  exit 1
fi
if [ ! -f "$SRC" ]; then
  echo "  FAIL ws-exactness: $SRC missing"
  exit 1
fi

# Compile under the SHIPPING ceiling (scripts/qcrun.sh COMPILER_MEM_MB=1536).
# A compiler that runs out of address space dies SILENTLY: exit 0, no binary,
# no diagnostic -- so the binary's existence is the assertion, not the exit code.
( cd "$REPO" || exit 1
  ulimit -c 0; ulimit -v 1572864 2>/dev/null || true
  timeout 600 "$QC" -O "$SRC" "$W/ws" >"$W/cc.log" 2>&1 )
if [ ! -s "$W/ws" ]; then
  echo "  FAIL ws-exactness: compile produced no binary under the 1,572,864 KB shipping cap (see $W/cc.log)"
  exit 1
fi

# The pool is 20 workers wide; give the run room.
( cd "$REPO" || exit 1
  ulimit -c 0; ulimit -v 32000000 2>/dev/null || true
  timeout 900 "$W/ws" </dev/null >"$W/run.log" 2>&1 )
runrc=$?

fail=0
fail_why=""

# 1. The test must reach its own PASS verdict.
if ! grep -qE '^PASS' "$W/run.log"; then
  fail=1; fail_why="no PASS verdict (rc=$runrc); tail: $(tail -3 "$W/run.log" | tr '\n' ' ')"
fi

# 2. Every arm must have bit-identical results between reference, static and stolen.
n_arms=$(grep -c 'diff_bits' "$W/run.log" 2>/dev/null || echo 0)
if [ "$n_arms" -lt 4 ]; then
  fail=1; fail_why="only $n_arms arms reported (expected >=4: fused and no-fused, chunk=16 and chunk=1)"
fi
bad_diff=$(grep 'diff_bits' "$W/run.log" 2>/dev/null | grep -v 'ref_vs_st=0 ref_vs_sw=0 st_vs_sw=0' | head -1)
if [ -n "$bad_diff" ]; then
  fail=1; fail_why="non-zero diff_bits: $bad_diff"
fi

# 3. Every arm must cover the full row count -- a partition that drops rows
#    entirely would otherwise pass assertion 2 by agreeing on nothing.
bad_rows=$(grep 'nrows=2048' "$W/run.log" 2>/dev/null | wc -l)
if [ "$bad_rows" -ne "$n_arms" ]; then
  fail=1; fail_why="$bad_rows of $n_arms arms report nrows=2048"
fi

# 4. Every claim counter must advance by exactly the rows it claimed:
#    `next` is what the pool actually consumed, `want_next` the closed form.
bad_claim=$(grep '^ *claim: ' "$W/run.log" 2>/dev/null | awk '
  { for (i = 1; i <= NF; i++) { if ($i ~ /^next=/) { split($i, a, "="); n = a[2] } if ($i ~ /^want_next=/) { split($i, b, "="); w = b[2] } }
    if (n != w || n == "") { print; c++ } }
  END { exit (c > 0) ? 1 : 0 }') || { fail=1; fail_why="claim counter mismatch: $(grep '^ *claim: ' "$W/run.log" | head -1)"; }

# 5. Every arm's own return code line must be 0/0/0.
bad_rc=$(grep 'rc ref/st/sw=' "$W/run.log" 2>/dev/null | grep -v 'rc ref/st/sw=0/0/0' | head -1)
if [ -n "$bad_rc" ]; then
  fail=1; fail_why="arm returned non-zero: $bad_rc"
fi

if [ "$fail" -eq 0 ]; then
  echo "  PASS ws-exactness: $n_arms arms, 2048 rows each, stolen == static == reference in raw u64 bits, claim counters exact (0 of 2048 rows wrong)"
  exit 0
else
  echo "  FAIL ws-exactness: $fail_why"
  echo "        (0.0.259 fixed A39: &global returned an IR_LOADG temporary's address, so atomic_add(&g,1) always returned 0. Log: $W/run.log)"
  exit 1
fi
