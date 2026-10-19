#!/usr/bin/env bash
# gate_fsize_guard.sh -- the documented entry point (scripts/run_gate.sh) must
# permit copying the largest gate fixture byte-complete.
#
# RED-FIRST: on 0.0.260, run_gate.sh sets ulimit -f 1048576 (1 GiB), which
# truncates the 1.67 GB gguf model copy at exactly 1,073,741,824 bytes. This
# stage copies the model under the inherited limit and asserts byte-identity.
# PASS = copy size == source size AND cmp succeeds AND gguf walk verifies.
# This proves the DOCUMENTED path (scripts/run_gate.sh -> run_tests.sh) passes.
#
# Usage: sourced by run_tests.sh (runs in same shell, inherits ulimit -f).

set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MODEL="/opt/ai/models/quanta/QUANTA-LFM2.5-2.6Bv1-Q4_K_M.gguf"
OUT=/tmp/gate_fsize
GEN="$REPO/scripts/audit/gen_corrupt_gguf.py"
VERIFY_WALK="$REPO/scripts/audit/verify_corrupt_walk.py"

# The constants from gguf_corrupt_gate.sh (must match or the walk won't verify).
TINFO_START=8222781
N_TENSORS=266
T0REL=0
T5REL=245506048

mkdir -p "$OUT"
A41_RC=0

# 1. Print the inherited file-size limit (blocks of 1024 bytes in bash).
limit_blocks=$(ulimit -f)
if [ "$limit_blocks" = "unlimited" ]; then
  echo "  gate-fsize: inherited ulimit -f = unlimited (no file-size cap)"
  limit_ok=1
else
  echo "  gate-fsize: inherited ulimit -f = $limit_blocks blocks (x1024 = $((limit_blocks * 1024)) bytes)"
  limit_ok=0
fi

# If the limit is "unlimited" (no cap), that's fine -- the fixture copies will work.
if [ "$limit_ok" -eq 1 ]; then
  echo "  PASS gate-fsize: ulimit -f is unlimited (no file-size cap)"
fi

# 2. Copy the model under that limit, verify byte-identity.
src_sz=$(stat -c%s "$MODEL" 2>/dev/null || echo 0)
if [ "$src_sz" -eq 0 ]; then
  echo "  FAIL gate-fsize: model not found or empty at $MODEL"
  A41_RC=1
else
  dst="$OUT/model_copy.gguf"
  ( cp "$MODEL" "$dst" 2>/dev/null )
  cp_rc=$?
  dst_sz=$(stat -c%s "$dst" 2>/dev/null || echo 0)

  if [ "$cp_rc" -ne 0 ] || [ "$dst_sz" -ne "$src_sz" ]; then
    echo "  FAIL gate-fsize: copy truncated (cp_rc=$cp_rc, src=$src_sz, dst=$dst_sz) -- ulimit -f too low"
    A41_RC=1
  else
    # Byte-identity via cmp (reads both from page cache, fast).
    if cmp -s "$MODEL" "$dst"; then
      echo "  PASS gate-fsize: copy byte-identical (${src_sz} B)"
    else
      echo "  FAIL gate-fsize: copy size matches but content differs"
      A41_RC=1
    fi
  fi
fi

# 3. Verify the gguf-corrupt generator's walk on the copy (proves the stage can work).
if [ "$A41_RC" -eq 0 ]; then
  dst="$OUT/model_copy.gguf"
  if python3 "$VERIFY_WALK" "$dst" "$TINFO_START" "$N_TENSORS" "$T0REL" "$T5REL" > "$OUT/walk.log" 2>&1; then
    echo "  PASS gate-fsize: gguf walk verifies on the copy"
  else
    echo "  FAIL gate-fsize: gguf walk failed on the copy (cannot generate corrupt files)"
    cat "$OUT/walk.log"
    A41_RC=1
  fi
fi

if [ "$A41_RC" -eq 0 ]; then
  echo "  gate-fsize: GREEN"
else
  echo "  gate-fsize: RED"
fi

exit "$A41_RC"