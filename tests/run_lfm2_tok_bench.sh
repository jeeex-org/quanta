#!/usr/bin/env bash
# tests/run_lfm2_tok_bench.sh -- build and run the tokenizer-only benchmark.
#
# Not a gate row for the same reason tests/lfm2_prefill_bench.quanta is not: it
# needs the 1.67 GB model (mmap'd, so VSZ must exceed it) and the special path's
# PRE-FIX cost is ~32 ms per input byte, far past any gate budget.
#
# Guards: core dumps off, address space capped at 8 GB, wall timeout, nice -19.
#
# Usage:  bash tests/run_lfm2_tok_bench.sh [bin_cap_bytes] [timeout_s]
# Conf:   tests/lfm2_tok_bench.conf   "<space-separated byte lengths>"
# Input:  tests/lfm2_tok_bench_input.txt  (prefixes are handed to the tokenizer)
#
# ALWAYS record the load average next to the numbers: this is a throughput
# measurement, and a number taken under a peer's load measures the peer.
set -u
cd "$(dirname "$0")/.." || exit 2
REPO="$PWD"
QC="${QC:-$REPO/compiler/$(cat "$REPO/VERSION")/bin/x86/qc}"
SRC="$REPO/tests/lfm2_tok_bench.quanta"
BIN="${TMPDIR:-/tmp}/lfm2_tok_bench.bin"
CAP="${1:-8000000}"
TMO="${2:-3600}"

if [ ! -f /opt/ai/models/quanta/QUANTA-LFM2.5-2.6Bv1-Q4_K_M.gguf ]; then
    echo "SKIP: model /opt/ai/models/quanta/QUANTA-LFM2.5-2.6Bv1-Q4_K_M.gguf absent"
    exit 3
fi

echo "conf: $(cat tests/lfm2_tok_bench.conf)"
echo "load_before: $(cat /proc/loadavg)"
echo "compile: $QC tests/lfm2_tok_bench.quanta"
( ulimit -c 0 -v 8000000; "$QC" "$SRC" "$BIN" ) || { echo "COMPILE FAIL rc=$?"; exit 2; }

echo "run: ulimit -v $CAP ; timeout $TMO nice -n 19 $BIN   (from $REPO)"
( ulimit -c 0 -v "$CAP"; timeout "$TMO" nice -n 19 "$BIN" </dev/null )
rc=$?
echo "load_after: $(cat /proc/loadavg)"
echo "run_rc=$rc"
exit $rc
