#!/usr/bin/env bash
# tests/run_lfm2_polite_pool_test.sh -- build and run the resource-politeness
# unit test (defect A16) under three environments and check the ceiling each way.
#
#   default               -> ceiling == min(nproc/2, 8)
#   QUANTA_MM_ALL_CORES=1 -> ceiling == nproc
#   QUANTA_MM_WORKERS=13  -> ceiling == 13
#
# Model-free, so it is cheap; still capped like every Quanta run (core dumps off,
# 8 GB address space, 15 s, nice -n 19).
set -u
cd "$(dirname "$0")/.." || exit 2
REPO="$PWD"
QC="${QC:-$REPO/compiler/$(cat "$REPO/VERSION")/bin/x86/qc}"
SRC="$REPO/tests/lfm2_polite_pool_test.quanta"
BIN="${TMPDIR:-/tmp}/lfm2_polite_pool.bin"

NC=$(nproc)
DEF=$(( NC / 2 )); [ "$DEF" -gt 8 ] && DEF=8; [ "$DEF" -lt 1 ] && DEF=1

echo "nproc=$NC expected_ceiling_default=$DEF"
echo "compile: $QC tests/lfm2_polite_pool_test.quanta"
( ulimit -c 0 -v 8000000; "$QC" "$SRC" "$BIN" ) || { echo "COMPILE FAIL rc=$?"; exit 2; }

run_case() {
    local label="$1" want="$2"; shift 2
    echo "--- case: $label (want ceiling=$want) ---"
    local out
    out=$( ( ulimit -c 0 -v 8000000; env "$@" timeout 60 nice -n 19 "$BIN" </dev/null ) ) || {
        echo "$out"; echo "CASE FAIL ($label) rc=$?"; return 1; }
    echo "$out"
    local got bad
    got=$(echo "$out" | awk '/^CEILING /{print $2}')
    bad=$(echo "$out" | awk '/^BAD_TOTAL /{print $2}')
    if [ "$got" != "$want" ]; then echo "CASE FAIL ($label): ceiling got=$got want=$want"; return 1; fi
    if [ "$bad" != "0" ]; then echo "CASE FAIL ($label): BAD_TOTAL=$bad"; return 1; fi
    echo "CASE PASS ($label)"
    return 0
}

fail=0
run_case default "$DEF" DUMMY=1 || fail=1
run_case all_cores "$NC" QUANTA_MM_ALL_CORES=1 || fail=1
run_case workers_13 13 QUANTA_MM_WORKERS=13 || fail=1

if [ "$fail" = "0" ]; then echo "POLITE POOL TEST: PASS"; exit 0; fi
echo "POLITE POOL TEST: FAIL"; exit 1
