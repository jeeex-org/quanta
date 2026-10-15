#!/usr/bin/env bash
# tests/run_lfm2_prefill_probe.sh -- build + run the native prefill dump and verify
# its carried state against a reference.
#
# Not a gate row: it needs the 1.67 GB model and a 23-position prefill with the
# full 128000-way output projection at every position (~3 min), far past the
# gate's 15 s / 1536 MB caps -- the same reason tests/lfm2_generate.quanta and
# tests/threaded_forward_twice.quanta live in tests/.
#
# The dump is written to the path baked into tests/lfm2_prefill_probe.quanta
# (OUTF), because a Quanta program cannot read argv for a path here.
#
# Usage:  bash tests/run_lfm2_prefill_probe.sh
#         PY=python3.12   (llama_cpp/gguf/numpy are installed for 3.12 only)
set -u
cd "$(dirname "$0")/.." || exit 2
REPO="$PWD"
QC="${QC:-$REPO/compiler/$(cat "$REPO/VERSION")/bin/x86/qc}"
PY="${PY:-python3.12}"
OUTBIN="${TMPDIR:-/tmp}/lfm2_prefill_probe.bin"
PROBE_OUT="/home/tali/.hermes/cache/scratch/lfm2probe/probe.bin"

if [ ! -f /opt/ai/models/quanta/QUANTA-LFM2.5-2.6Bv1-Q4_K_M.gguf ]; then
    echo "SKIP: model /opt/ai/models/quanta/QUANTA-LFM2.5-2.6Bv1-Q4_K_M.gguf absent"
    exit 3
fi

echo "compile: $QC tests/lfm2_prefill_probe.quanta"
( ulimit -c 0 -v 8000000; "$QC" tests/lfm2_prefill_probe.quanta "$OUTBIN" ) \
    || { echo "COMPILE FAIL rc=$?"; exit 2; }

echo "run: ulimit -v 8000000 ; nice -n 19 $OUTBIN"
( ulimit -c 0 -v 8000000; timeout 1200 nice -n 19 "$OUTBIN" </dev/null ) \
    || { echo "RUN FAIL rc=$?"; exit 2; }

echo
echo "verify: $PY tests/verify_lfm2_state_ref.py $PROBE_OUT"
"$PY" tests/verify_lfm2_state_ref.py "$PROBE_OUT"
