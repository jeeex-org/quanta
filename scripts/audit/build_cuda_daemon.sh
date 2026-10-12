#!/usr/bin/env bash
# build_cuda_daemon.sh — build the Phase 6.2 CUDA daemon.
#
# The daemon is plain C and links cudart, so it stays a gcc build. The kernels
# need nvcc, so they are a separate translation unit (quanta_gpu_kernels.cu) that
# is compiled first and linked in. Splitting them means a change to the queue or
# protocol logic does not need the CUDA compiler, and the kernel file is the only
# thing that carries device code.
#
# Usage: scripts/audit/build_cuda_daemon.sh [output-path]
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="${1:-$REPO/scripts/audit/cuda_daemon}"

# Locate the toolkit rather than assuming it is on PATH: nvcc is not on this
# box's PATH, and a hardcoded /usr/local/cuda works only while that symlink is
# the right version.
CUDA_ROOT="${CUDA_ROOT:-}"
if [ -z "$CUDA_ROOT" ]; then
    for c in /usr/local/cuda /usr/local/cuda-13.3 /usr/local/cuda-13; do
        if [ -x "$c/bin/nvcc" ]; then CUDA_ROOT="$c"; break; fi
    done
fi
if [ -z "$CUDA_ROOT" ] || [ ! -x "$CUDA_ROOT/bin/nvcc" ]; then
    echo "build_cuda_daemon: no nvcc found (set CUDA_ROOT)" >&2
    exit 1
fi

# Compute capability of the installed GPU, so the kernels are built for the
# hardware that will run them. Falls back to 89 (this box's 4070) when
# nvidia-smi is unavailable.
CC="$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>/dev/null | head -1 | tr -d ' .' || true)"
[ -n "$CC" ] || CC=89
ARCH="sm_${CC}"

echo "build_cuda_daemon: CUDA_ROOT=$CUDA_ROOT arch=$ARCH -> $OUT"
"$CUDA_ROOT/bin/nvcc" -O2 -arch="$ARCH" -c "$REPO/scripts/audit/quanta_gpu_kernels.cu" \
    -o /tmp/qg_kernels_$$.o
gcc -O2 -Wall -I"$CUDA_ROOT/targets/x86_64-linux/include" \
    -o "$OUT" "$REPO/scripts/audit/cuda_daemon.c" /tmp/qg_kernels_$$.o \
    -L"$CUDA_ROOT/targets/x86_64-linux/lib" -lcudart -lstdc++ -lm
rm -f /tmp/qg_kernels_$$.o
echo "build_cuda_daemon: built $(stat -c%s "$OUT") bytes md5=$(md5sum "$OUT" | cut -d' ' -f1)"
