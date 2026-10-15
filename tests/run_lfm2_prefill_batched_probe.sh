#!/usr/bin/env bash
# tests/run_lfm2_prefill_batched_probe.sh -- build + run the BATCHED prefill dump,
# then check it two ways:
#   1. tests/diff_lfm2_probe.py    -- batched dump vs the one-forward-per-token
#      dump, element-wise, bit for bit. Batching claims IDENTITY, so any non-zero
#      differing-bit count is a fail.
#   2. tests/verify_lfm2_state_ref.py -- the batched dump against the llama.cpp
#      oracle (correlation + argmax + top-10 overlap, per position). This is the
#      independent check: agreeing with the other native path is not evidence
#      that the shared computation is right.
#
# Needs the 1.67 GB model and a 23-position prefill with the full 128000-way
# output projection at every position, so it is not a gate row (same reason
# tests/lfm2_prefill_probe.quanta is not).
#
# The reference dump (probe.bin) must already exist -- it is produced by
# tests/run_lfm2_prefill_probe.sh. Run that first, or point A at an existing dump.
#
# Usage:  bash tests/run_lfm2_prefill_batched_probe.sh [dump_a] [dump_b]
#         PY=python3.12   (llama_cpp/gguf/numpy are installed for 3.12 only)
set -u
cd "$(dirname "$0")/.." || exit 2
REPO="$PWD"
QC="${QC:-$REPO/compiler/$(cat "$REPO/VERSION")/bin/x86/qc}"
PY="${PY:-python3.12}"
OUTBIN="${TMPDIR:-/tmp}/lfm2_batched_probe.bin"
DUMP_A="${1:-/home/tali/.hermes/cache/scratch/lfm2probe/probe.bin}"
DUMP_B="${2:-/home/tali/.hermes/cache/scratch/lfm2probe/probe_batched.bin}"

if [ ! -f /opt/ai/models/quanta/QUANTA-LFM2.5-2.6Bv1-Q4_K_M.gguf ]; then
    echo "SKIP: model /opt/ai/models/quanta/QUANTA-LFM2.5-2.6Bv1-Q4_K_M.gguf absent"
    exit 3
fi

echo "load: $(cat /proc/loadavg)"
echo "compile: $QC tests/lfm2_prefill_batched_probe.quanta"
( ulimit -c 0 -v 8000000; "$QC" tests/lfm2_prefill_batched_probe.quanta "$OUTBIN" ) \
    || { echo "COMPILE FAIL rc=$?"; exit 2; }

# NO `nice -n 19` HERE ON PURPOSE. This measures and dumps a 23-position prefill;
# with an ambient load at nice 0 the measurement gets starved to ~1 core and
# never finishes inside the timeout. The sanctioned runners use nice -n 19 for
# the GATE, where politeness matters more than the number.
echo "run: ulimit -v 8000000 ; $OUTBIN"
( ulimit -c 0 -v 8000000; timeout 2400 "$OUTBIN" </dev/null ) \
    || { echo "RUN FAIL rc=$?"; exit 2; }

echo
echo "=== 1. diff vs $DUMP_A ==="
"$PY" tests/diff_lfm2_probe.py "$DUMP_A" "$DUMP_B"
drc=$?

echo
echo "=== 2. llama.cpp oracle on the BATCHED dump ==="
"$PY" tests/verify_lfm2_state_ref.py "$DUMP_B"
vrc=$?

echo "diff_rc=$drc verify_rc=$vrc"
[ "$drc" = 0 ] && [ "$vrc" = 0 ] || exit 1
echo "BATCHED PROBE PASS"
