#!/usr/bin/env bash
# tests/lfm2_f32_ab.sh
#
# The END-TO-END paired A/B for mm_set_fused_f32 (decode bench conf field 17),
# with the four arms in a PALINDROME: off, f64+fma, f32, f32+fma, f32+fma, f32,
# f64+fma, off. Every arm therefore has a near-load neighbour on both sides,
# which is the only way an effect of this size is resolvable on a box whose
# ambient load moved the SAME tree between 1.85 and 3.148 tok/s.
#
# The attributable ratio lives in the KERNEL-level A/B
# (tests/lfm2_f32_kernel_ab_test.quanta); this driver exists to show whether the
# end-to-end number moves at all and to report the absolute tok/s of each
# configuration labelled with its own load.
#
# Usage: bash tests/lfm2_f32_ab.sh
set -u
cd "$(dirname "$0")/.." || exit 1

QC=${QC:-$PWD/compiler/0.0.255/bin/x86/qc}
BIN=${BIN:-/tmp/lfm2_f32_ab_bench}
CONF=tests/lfm2_decode_bench.conf
LOG="${PROF_SCRATCH:-/tmp}/lfm2_f32_ab"
mkdir -p "$LOG"

# lens 64/64/64 keeps one invocation ~1.5 min so eight arms fit in a session and
# every arm sees a comparable load band. All other flags at the SHIPPED settings.
# LENS is a parameter because the arms must be SHORT enough to interleave: an
# arm whose own three runs take 2.5 minutes cannot resolve an effect on a box
# whose available core count swings by 2.5x inside one arm. Measured: the same
# eight-arm palindrome at LENS=64 produced arm means spread 1.93-4.96 tok/s
# that did NOT track loadavg at all.
LENS=${LENS:-64}
COMMON="20 $LENS $LENS $LENS 1 1 1 1 1 0 0 1 1 1 1"

echo "=== lfm2 f32 end-to-end A/B (palindrome off,f64fma,f32,f32fma,f32fma,f32,f64fma,off) LENS=$LENS ==="
echo "NOTE: read the PALINDROME PAIRS and the MIN over each arm's runs, not one"
echo "      number: this box's available cores swing inside a single arm."
echo "compiler: $QC"
md5sum "$QC"
echo "common conf: $COMMON <fma> <f32>"
echo "load at start: $(cat /proc/loadavg)"

"$QC" -O tests/lfm2_decode_bench.quanta "$BIN" || { echo "COMPILE FAILED"; exit 1; }

run_arm () {
  local tag="$1" fma="$2" f32="$3"
  local l0 l1
  l0=$(cut -d' ' -f1 /proc/loadavg)
  printf '%s %s %s\n' "$COMMON" "$fma" "$f32" > "$CONF"
  echo "--- arm $tag  fma=$fma f32=$f32  load_before=$l0  $(date +%H:%M:%S) ---"
  ( ulimit -c 0 -v 32000000 2>/dev/null; nice -n 0 "$BIN" </dev/null ) \
      > "$LOG/arm_$tag.log" 2>&1
  grep -E '^conf:|fused_fma_active|fused_fma_used|fused_f32_active|fused_f32_used|fused_f32_drop|xf32_allocs|xf32_elems|fused_q4k_active|fused_q6k_active|first_argmax_id|VmPeak' "$LOG/arm_$tag.log" | head -20
  echo " arm $tag results:"
  grep -E 'tok/s|ms/token' "$LOG/arm_$tag.log" | head -12
  l1=$(cut -d' ' -f1 /proc/loadavg)
  echo " arm $tag done, load_after=$l1"
}

# Restore the COMMITTED conf, not "whatever was there when this started": the
# latter propagates a dirty value from a previous manual edit (it did exactly
# that here -- an A/B left the bench conf at the last arm's flags for the next
# reader). A driver must not leave the tree dirtier than it found it, and the
# committed file is the only unambiguous definition of "clean".
cp "$CONF" "$LOG/conf.before"
trap 'git checkout -- "$CONF" 2>/dev/null || cp "$LOG/conf.before" "$CONF"' EXIT

run_arm off1    0 0
run_arm f64fma  1 0
run_arm f32     0 1
run_arm f32fma  1 1
run_arm f32fma2 1 1
run_arm f322    0 1
run_arm f64fma2 1 0
run_arm off2    0 0

echo "=== summary ==="
for t in off1 f64fma f32 f32fma f32fma2 f322 f64fma2 off2; do
  echo "--- $t ---"
  grep -E 'tok/s|ms/token|first_argmax_id' "$LOG/arm_$t.log" | head -10
done
echo "load at end: $(cat /proc/loadavg)"
echo "logs: $LOG"
