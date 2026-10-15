#!/usr/bin/env bash
# gguf_corrupt_gate.sh -- byte-level corrupt GGUF files must all be rejected.
#
# WHY THIS IS A SCRIPT AND NOT A QUANTA TEST
# ------------------------------------------
# Producing a corrupt file means copying a 1.6 GB model and patching one 8-byte
# field at a known offset. Doing that from inside a Quanta test would need a
# GGUF *writer*, and two hand-rolled Python GGUF readers failed earlier in this
# project (both desynced on general.base_model.0.name). So the generator takes
# the tensor-table offset FROM QUANTA's verified parser and never parses the KV
# block itself; the Quanta side then just loads each file and reports rc.
#
# The generator's walk is verified against Quanta's own parsed tensor offsets
# before anything is written, and it refuses on mismatch -- so a bug here cannot
# silently corrupt an unrelated region of the model.
#
# PASS = every corrupt file is rejected AND the real model still loads.
set -u

# scripts/ lives two levels below the repo root, not one.
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
QC="$REPO/compiler/$(cat "$REPO/VERSION")/bin/x86/qc"
MODEL="/opt/ai/models/quanta/QUANTA-LFM2.5-2.6Bv1-Q4_K_M.gguf"
OUT=/tmp/quanta_corrupt
GEN="$REPO/scripts/audit/gen_corrupt_gguf.py"

# Measured by Quanta, not assumed. If the loader's layout ever changes these
# change too, and verify_walk below will refuse rather than corrupt the wrong
# bytes.
TINFO_START=8222781
N_TENSORS=266
T0REL=0
T5REL=245506048

KINDS="gap overlap tail dim_overflow dim_mismatch huge_dtype neg_offset"

mkdir -p "$OUT"

if [ ! -f "$MODEL" ]; then
  echo "SKIP gguf-corrupt: model not present"
  exit 0
fi

# --- 1. the walk must be verified before anything is written ---
if ! python3 "$REPO/scripts/audit/verify_corrupt_walk.py" > "$OUT/walk.log" 2>&1; then
  echo "FAIL gguf-corrupt: offset walk verification failed"
  cat "$OUT/walk.log"
  exit 1
fi

# --- 2. the real model must load ---
cat > "$OUT/real.quanta" <<'EOF'
import std/fs
import std/gguf
import std/math
fn main() {
    print(gguf_load("/opt/ai/models/quanta/QUANTA-LFM2.5-2.6Bv1-Q4_K_M.gguf"))
    return 0
}
EOF
rm -f "$OUT/real.bin"
if ! "$QC" --no-overflow-trap "$OUT/real.quanta" "$OUT/real.bin" 2>"$OUT/real.err"; then
  echo "FAIL gguf-corrupt: real probe did not compile: $(head -1 "$OUT/real.err")"
  exit 1
fi
set +e
real_rc=$("$REPO/scripts/quanta_run.sh" "$OUT/real.bin" 2>/dev/null | tail -1)
set -e
if [ "$real_rc" != "0" ]; then
  echo "FAIL gguf-corrupt: the REAL model failed to load (rc=$real_rc)"
  exit 1
fi

# --- 3. each corruption must be rejected ---
fail=0
rejected=0
total=0
for kind in $KINDS; do
  total=$((total + 1))
  dst="$OUT/$kind.gguf"
  if ! python3 "$GEN" "$MODEL" "$dst" "$TINFO_START" "$kind" "$N_TENSORS" "$T0REL" "$T5REL" > "$OUT/$kind.gen" 2>&1; then
    echo "  FAIL (generate) $kind: $(head -1 "$OUT/$kind.gen")"
    fail=$((fail + 1)); continue
  fi
  cat > "$OUT/$kind.quanta" <<EOF
import std/fs
import std/gguf
import std/math
fn main() {
    print(gguf_load("$dst"))
    return 0
}
EOF
  rm -f "$OUT/$kind.bin"
  if ! "$QC" --no-overflow-trap "$OUT/$kind.quanta" "$OUT/$kind.bin" 2>"$OUT/$kind.err"; then
    echo "  FAIL (compile) $kind: $(head -1 "$OUT/$kind.err")"
    fail=$((fail + 1)); continue
  fi
  set +e
  rc=$("$REPO/scripts/quanta_run.sh" "$OUT/$kind.bin" 2>/dev/null | tail -1)
  set -e
  if [ "$rc" = "0" ]; then
    echo "  FAIL $kind: corrupt file was ACCEPTED (rc=0)"
    fail=$((fail + 1))
  else
    echo "  PASS $kind rejected (rc=$rc)"
    rejected=$((rejected + 1))
  fi
  rm -f "$dst" "$OUT/$kind.bin" "$OUT/$kind.quanta"
done

echo "  gguf-corrupt: $rejected/$total rejected, real model rc=0"
if [ "$fail" -ne 0 ]; then
  echo "  gguf-corrupt: FAILED ($fail)"
  exit 1
fi
echo "  gguf-corrupt: GREEN"
exit 0