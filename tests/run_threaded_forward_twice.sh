#!/usr/bin/env bash
# tests/run_threaded_forward_twice.sh -- run the A9 red-first repro and report
# BOTH the process exit code and the two marker files.
#
# WHY A WRAPPER: the defect is silent. The pre-fix engine dies inside the first
# forward and the process is still reported as exited 0 (the emitter's
# mmap-failure guard exits(1) on the main thread while the group's worker
# threads keep running, so the group's final status is 0). Checking rc alone
# would call a dead run a pass -- so the assertion is "the second-forward marker
# exists", plus rc == 7.
#
# The VSZ cap is the second argument (default 8 GB, the sanctioned ceiling). The
# recorded defect reproduces at 4 GB, where the pre-fix leak (~2.3 GB per
# forward) exhausts the space inside forward 1.
set -u
cd "$(dirname "$0")/.." || exit 2
REPO="$PWD"
QC="$REPO/compiler/0.0.236/bin/x86/qc"
SRC="$REPO/tests/threaded_forward_twice.quanta"
BIN="${TMPDIR:-/tmp}/qrw_tft.bin"
CAP="${1:-8000000}"
W1="$REPO/stage1/logs/tft_forward1.bin"
W2="$REPO/stage1/logs/tft_forward2.bin"

rm -f "$W1" "$W2"
echo "compile: $QC (implicit lib/std) ..."
( ulimit -c 0 -v 8000000; "$QC" "$SRC" "$BIN" ) || { echo "COMPILE FAIL rc=$?"; exit 2; }

echo "run: ulimit -v $CAP ; nice -n 19 $BIN"
( ulimit -c 0 -v "$CAP"; timeout 300 nice -n 19 "$BIN" </dev/null )
rc=$?
w1=MISSING; w2=MISSING
[ -f "$W1" ] && w1=ok
[ -f "$W2" ] && w2=ok
echo "run_rc=$rc  forward1_marker=$w1  forward2_marker=$w2"
if [ "$rc" = "7" ] && [ "$w2" = "ok" ]; then
  echo "PASS: both threaded forwards completed"
  exit 0
fi
echo "FAIL: the second threaded forward did not complete (rc=$rc, marker2=$w2)"
exit 1
