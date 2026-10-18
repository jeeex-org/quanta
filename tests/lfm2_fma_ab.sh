#!/usr/bin/env bash
# tests/lfm2_fma_ab.sh
#
# The END-TO-END paired A/B for mm_set_fused_fma (decode bench conf field 16),
# with the arms INTERLEAVED in one session: off, on, on, off.
#
# WHY interleaved: this box's ambient load made the same tree measure 3.148 tok/s
# at loadavg 12 and 1.85 tok/s at 21. Two sequential arms cannot resolve an effect
# of the size being chased here, so the arms alternate and every run's own load is
# printed with its number. The kernel-level A/B (tests/lfm2_fma_kernel_ab_test)
# is where the attributable ratio lives; this driver exists to show whether the
# end-to-end number moves at all, and to report the absolute tok/s of the SHIPPED
# configuration labelled with its load.
#
# Usage: bash tests/lfm2_fma_ab.sh
set -u
cd "$(dirname "$0")/.." || exit 1

QC=${QC:-$PWD/compiler/0.0.249/bin/x86/qc}
BIN=${BIN:-/tmp/lfm2_fma_ab_bench}
CONF=tests/lfm2_decode_bench.conf
LOG="${PROF_SCRATCH:-/tmp}/lfm2_fma_ab"
mkdir -p "$LOG"

# lens 64/64/64 keeps one invocation ~1.5 min so four arms fit in a session and
# all four see the same load band. All other flags at the SHIPPED settings.
COMMON="20 64 64 64 1 1 1 1 1 0 0 1 1 1 1"

echo "=== lfm2 FMA end-to-end A/B (arms interleaved off,on,on,off) ==="
echo "compiler: $QC"
md5sum "$QC"
echo "conf: $COMMON <fused_fma>"
echo "load at start: $(cat /proc/loadavg)"

"$QC" -O tests/lfm2_decode_bench.quanta "$BIN" || { echo "COMPILE FAILED"; exit 1; }

run_arm () {
  local tag="$1" fma="$2"
  local l0 l1
  l0=$(cut -d' ' -f1 /proc/loadavg)
  printf '%s %s\n' "$COMMON" "$fma" > "$CONF"
  echo "--- arm $tag  fused_fma=$fma  load_before=$l0  $(date +%H:%M:%S) ---"
  ( ulimit -c 0 -v 32000000 2>/dev/null; nice -n 0 "$BIN" </dev/null ) \
      > "$LOG/arm_$tag.log" 2>&1
  grep -E '^conf:|fused_fma_active|fused_fma_used|fused_q4k_active|fused_q6k_active|^run |tok/s|first_argmax_id|VmPeak' "$LOG/arm_$tag.log" | head -40
  l1=$(cut -d' ' -f1 /proc/loadavg)
  echo " arm $tag done, load_after=$l1"
}

# copy the old conf so a peer can restore it, then restore at the end
cp "$CONF" "$LOG/conf.before"
trap 'cp "$LOG/conf.before" "$CONF"' EXIT

run_arm off1 0
run_arm on1  1
run_arm on2  1
run_arm off2 0

echo "=== summary (read the PAIRED arms, not one number) ==="
for t in off1 on1 on2 off2; do
  echo "--- $t ---"
  grep -E 'tok/s|ms/token' "$LOG/arm_$t.log" | head -12
done
echo "load at end: $(cat /proc/loadavg)"
echo "logs: $LOG"
