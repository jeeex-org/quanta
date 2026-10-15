#!/usr/bin/env bash
# tests/run_lfm2_prefill_bench.sh -- build and run the prefill throughput driver.
#
# Not a gate row for the same reason tests/lfm2_generate.quanta is not: it needs
# the 1.67 GB model and one prompt token costs seconds, far past the gate's
# 15 s / 1536 MB caps. The guards below are the sanctioned ones: core dumps off,
# address space capped at 8 GB, wall-clock timeout, nice -n 19.
#
# Usage:  bash tests/run_lfm2_prefill_bench.sh [bin_cap_bytes]
# Conf:   tests/lfm2_prefill_bench.conf  "<workers> <n_tokens> [batch]"
# Prompt: tests/lfm2_prefill_prompt.txt  (a copy of the real SI-loop prompt)
#
# ALWAYS record the load average next to the numbers. This measures throughput;
# under a peer's load it measures the peer.
set -u
cd "$(dirname "$0")/.." || exit 2
REPO="$PWD"
QC="${QC:-$REPO/compiler/$(cat "$REPO/VERSION")/bin/x86/qc}"
SRC="$REPO/tests/lfm2_prefill_bench.quanta"
BIN="${TMPDIR:-/tmp}/lfm2_prefill_bench.bin"
CAP="${1:-8000000}"

if [ ! -f /opt/ai/models/quanta/QUANTA-LFM2.5-2.6Bv1-Q4_K_M.gguf ]; then
    echo "SKIP: model /opt/ai/models/quanta/QUANTA-LFM2.5-2.6Bv1-Q4_K_M.gguf absent"
    exit 3
fi

echo "conf: $(cat tests/lfm2_prefill_bench.conf)"
echo "load: $(cat /proc/loadavg)"
echo "compile: $QC tests/lfm2_prefill_bench.quanta"
( ulimit -c 0 -v 8000000; "$QC" "$SRC" "$BIN" ) || { echo "COMPILE FAIL rc=$?"; exit 2; }

echo "run: ulimit -v $CAP ; nice -n 19 $BIN   (from $REPO)"
( ulimit -c 0 -v "$CAP"; timeout 3600 nice -n 19 "$BIN" </dev/null )
rc=$?
echo "load_after: $(cat /proc/loadavg)"
echo "run_rc=$rc"
exit $rc
