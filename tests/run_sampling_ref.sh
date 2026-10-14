#!/usr/bin/env bash
# tests/run_sampling_ref.sh -- reference check of lib/std/sampling.quanta.
#
# Compiles tests/sampling_ref.quanta with the version's compiler, runs it (no
# model needed; the vectors are synthetic), and checks the result against an
# independent numpy reference plus a bit-exact Python replica of the RNG+draw.
#
#   bash tests/run_sampling_ref.sh          # prints the check table, exits 0/1
#
# Requires python3 WITH numpy: /usr/bin/python3 on this box (the Hermes python
# does not have numpy).
set -u
cd "$(dirname "$0")/.." || exit 2
REPO="$PWD"
QC="${QC:-$REPO/compiler/$(cat "$REPO/VERSION")/bin/x86/qc}"
PY="${PY:-/usr/bin/python3}"
OUT="${TMPDIR:-/tmp}/sampling_ref_out.txt"

( ulimit -c 0 -v 8000000; "$QC" "$REPO/tests/sampling_ref.quanta" "${TMPDIR:-/tmp}/sampling_ref.bin" ) \
    || { echo "COMPILE FAIL"; exit 2; }
./scripts/quanta_run.sh "${TMPDIR:-/tmp}/sampling_ref.bin" </dev/null > "$OUT" || { echo "RUN FAIL"; exit 2; }
"$PY" "$REPO/tests/verify_sampling_ref.py" "$OUT"
