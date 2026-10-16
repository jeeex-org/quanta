#!/usr/bin/env bash
# tests/run_lfm2_decode_bench.sh -- build and run the large-scale decode bench.
#
# Unlike tests/run_lfm2_generate.sh this does NOT use nice -n 19: measured on
# this box (docs/research/q6k-simd-dequant.md section 0) nice -n 19 starves a
# throughput measurement to ~1 core. The bench is an ATTENDED throughput run,
# so it runs at nice 0 and REFUSES to start while a peer model-heavy process is
# alive (pgrep gate below) -- concurrent runs contaminate each other's numbers.
#
# Usage: bash tests/run_lfm2_decode_bench.sh [bin_cap_bytes] [timeout_s]
# Conf:  tests/lfm2_decode_bench.conf
#         "<workers> <len1> <len2> <len3> <use_mmap> <cache_norms> <dot_multi>"
set -u
cd "$(dirname "$0")/.." || exit 2
REPO="$PWD"
QC="${QC:-$REPO/compiler/$(cat "$REPO/VERSION")/bin/x86/qc}"
SRC="$REPO/tests/lfm2_decode_bench.quanta"
BIN="${TMPDIR:-/tmp}/lfm2_decode_bench.bin"
CAP="${1:-8000000}"
TMO="${2:-14400}"

if [ ! -f /opt/ai/models/quanta/QUANTA-LFM2.5-2.6Bv1-Q4_K_M.gguf ]; then
    echo "SKIP: model /opt/ai/models/quanta/QUANTA-LFM2.5-2.6Bv1-Q4_K_M.gguf absent"
    exit 3
fi

# Environment discipline: refuse to measure under a peer model-heavy run.
PEERS=$(pgrep -af 'lfm2_gen_driver|lfm2_generate\.bin|wire\.py' | grep -v pgrep | grep -v 'defunct' || true)
if [ -n "$PEERS" ]; then
    echo "REFUSING: model-heavy peer process alive (measurement discipline):"
    echo "$PEERS"
    exit 4
fi

echo "env: $(date '+%F %T %Z') governor=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo '?') load=$(cut -d' ' -f1-3 /proc/loadavg)"
echo "top_cpu: $(ps -eo pcpu,comm --sort=-pcpu | sed -n '2p')"

echo "compile: $QC $SRC"
( ulimit -c 0 -v 8000000; "$QC" "$SRC" "$BIN" ) || { echo "COMPILE FAIL rc=$?"; exit 2; }

echo "run: ulimit -v $CAP ; nice 0 $BIN (timeout ${TMO}s)"
echo "run_start: $(date '+%F %T')"
( ulimit -c 0 -v "$CAP"; timeout "$TMO" nice 0 "$BIN" </dev/null )
rc=$?
echo "run_end: $(date '+%F %T')"
echo "env_after: load=$(cut -d' ' -f1-3 /proc/loadavg)"
echo "run_rc=$rc"
exit $rc
