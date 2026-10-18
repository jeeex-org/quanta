#!/usr/bin/env bash
# tests/lfm2_f32_correctness.sh
#
# The two CORRECTNESS rows for the f32 kernel route, run in sequence because this
# box is shared and only one 20-worker model process should be alive at a time.
# Neither is a timing measurement, so the ambient load only affects how long they
# take; every absolute number is still printed with its load.
#
#   1. tests/lfm2_f32_logits_test   -- the f32 path's OWN bar: 4 arms in one
#      process (f64, f64+FMA, f32, f32+FMA), argmax + ids identical, and the
#      logit excursion REPORTED.
#   2. tests/lfm2_fused_logits_test -- the EXISTING flags' bit-exact gate, which
#      must still read logit_mism=0 / max_abs_diff_bits=0 on all 128,000 logits
#      with mm_fused_f32 off. This is the proof that adding the flag changed
#      nothing for the flags that were already there.
#
# Usage: bash tests/lfm2_f32_correctness.sh
set -u
cd "$(dirname "$0")/.." || exit 1
QC=${QC:-$PWD/compiler/0.0.252/bin/x86/qc}
VP="ulimit -c 0 -v 32000000;"

echo "=== f32 correctness rows ==="
echo "compiler: $QC"; md5sum "$QC"

echo "--- build ---"
"$QC" -O tests/lfm2_f32_logits_test.quanta /tmp/f32_logits || exit 1
"$QC" -O tests/lfm2_fused_logits_test.quanta /tmp/fused_logits || exit 1

echo "--- 1. the f32 path's own bar (load $(cut -d' ' -f1 /proc/loadavg)) ---"
( eval "$VP" nice -n 0 /tmp/f32_logits </dev/null )
echo "f32_logits_exit=$?"

echo "--- 2. the EXISTING flags' bit-exact gate (load $(cut -d' ' -f1 /proc/loadavg)) ---"
( eval "$VP" nice -n 0 /tmp/fused_logits </dev/null )
echo "fused_logits_exit=$?"
echo "load at end: $(cat /proc/loadavg)"
