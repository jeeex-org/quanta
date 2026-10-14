#!/usr/bin/env bash
# tests/run_lfm2_generate.sh -- build and run the native LFM2 generation driver.
#
# WHY A WRAPPER SCRIPT: this needs the 1.67 GB model, and one decode token costs
# tens of seconds, so it cannot live in test_suites/EXPECTED.tsv (15 s cap,
# 1536 MB cap -- quanta_run.sh's ceiling is BELOW the model's mapping). The
# guards are therefore explicit and the same ones the native-inference work
# agreed on: core dumps off, an explicit address-space cap at the sanctioned
# 8 GB ceiling, a wall-clock timeout, and nice -n 19.
#
# Usage:  bash tests/run_lfm2_generate.sh [bin_cap_bytes]
# Conf:   tests/lfm2_gen.conf   "<workers> <max_new_tokens> <temp_milli> <top_k>"
# Prompt: tests/lfm2_prompt.txt (the user turn)
set -u
cd "$(dirname "$0")/.." || exit 2
REPO="$PWD"
QC="${QC:-$REPO/compiler/$(cat "$REPO/VERSION")/bin/x86/qc}"
SRC="$REPO/tests/lfm2_generate.quanta"
BIN="${TMPDIR:-/tmp}/lfm2_generate.bin"
CAP="${1:-8000000}"

if [ ! -f /opt/ai/models/quanta/QUANTA-LFM2.5-2.6Bv1-Q4_K_M.gguf ]; then
    echo "SKIP: model /opt/ai/models/quanta/QUANTA-LFM2.5-2.6Bv1-Q4_K_M.gguf absent"
    exit 3
fi

echo "compile: $QC tests/lfm2_generate.quanta"
( ulimit -c 0 -v 8000000; "$QC" "$SRC" "$BIN" ) || { echo "COMPILE FAIL rc=$?"; exit 2; }

echo "run: ulimit -v $CAP ; nice -n 19 $BIN   (from $REPO)"
( ulimit -c 0 -v "$CAP"; timeout 1800 nice -n 19 "$BIN" </dev/null )
rc=$?
echo "run_rc=$rc"
exit $rc
