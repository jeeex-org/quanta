#!/usr/bin/env bash
# tests/lfm2_f32_remeasure.sh
#
# EVERY f32 measurement, re-taken under ONE compiler pin. Written because the
# first pass pinned 0.0.252 and the author re-pinned to 0.0.255 mid-flight, and an
# A/B whose arms were built by different compilers is not an A/B: it measures the
# compilers, not the flag. The 0.0.252 arm data is DISCARDED, not spliced.
#
# Order matters. The end-to-end A/B needs the least contended box available, so it
# goes first; everything after it is either a within-process ratio (the kernel
# A/B), a microbenchmark, or a correctness row, none of which change their
# verdict with load.
#
# Usage: QC=$PWD/compiler/0.0.255/bin/x86/qc bash tests/lfm2_f32_remeasure.sh
set -u
cd "$(dirname "$0")/.." || exit 1

QC=${QC:-$PWD/compiler/0.0.255/bin/x86/qc}
LENS=${LENS:-32}
VP="ulimit -c 0 -v 32000000;"

echo "############ f32 re-measurement under a single pin ############"
echo "compiler: $QC"
md5sum "$QC"
echo "NOTE the pin is whatever QC names; the GOLDEN for 0.0.256 is"
echo "     21c868f418797c86d7db68728ed01917. Check the md5 against the version's"
echo "     documented golden before trusting any figure -- a moving VERSION is why"
echo "     the pin is explicit."
echo "VERSION (NOT used as the pin): $(cat VERSION)"
echo "load at start: $(cat /proc/loadavg)"
date

echo
echo "############ EMITTED-CODE CHECKS (fast, no model; run after touching any hex) ############"
python3 tests/lfm2_f32_enc_gen.py            # GNU as -> objdump -> table + prologue splice
gcc -O1 -o /tmp/f32enc tests/lfm2_f32_enc_verify.c && /tmp/f32enc
python3 tests/lfm2_f32_enc_negctl.py         # 5 negative controls: MUST all be caught
python3 tests/lfm2_f32_hexcheck.py
python3 tests/lfm2_jbytes_len_check.py

echo
echo "############ BUILD ############"
"$QC" -O tests/lfm2_f32_kernel_ab_test.quanta /tmp/f32ab || exit 1
"$QC" -O tests/lfm2_f32_fill_bench.quanta /tmp/f32fill || exit 1
"$QC" -O tests/lfm2_f32_logits_test.quanta /tmp/f32_logits || exit 1
"$QC" -O tests/lfm2_fused_logits_test.quanta /tmp/fused_logits || exit 1
echo "built OK"

echo
echo "############ 1. END-TO-END A/B, palindrome, LENS=$LENS (round 1) ############"
echo "load $(cut -d' ' -f1 /proc/loadavg)"
LENS=$LENS PROF_SCRATCH=/tmp/ab32 bash tests/lfm2_f32_ab.sh
echo "############ 1b. END-TO-END A/B, palindrome, LENS=$LENS (round 2) ############"
echo "load $(cut -d' ' -f1 /proc/loadavg)"
LENS=$LENS PROF_SCRATCH=/tmp/ab32b bash tests/lfm2_f32_ab.sh

echo
echo "############ 2. KERNEL A/B + f32 oracle reference (3 runs) ############"
for r in 1 2 3; do
  echo "## kernel run $r  load=$(cut -d' ' -f1 /proc/loadavg)"
  ( eval "$VP" /tmp/f32ab </dev/null )
done

echo
echo "############ 3. the f32 x-buffer fill, timed ############"
echo "load $(cut -d' ' -f1 /proc/loadavg)"
( eval "$VP" /tmp/f32fill </dev/null )

echo
echo "############ 4. the f32 path's own bar (3 runs, for the bound) ############"
for r in A B C; do
  echo "### bar run $r  load=$(cut -d' ' -f1 /proc/loadavg)"
  ( eval "$VP" nice -n 0 /tmp/f32_logits </dev/null )
  echo "bar_run_${r}_exit=$?"
done

echo
echo "############ 5. the EXISTING flags' bit-exact gate ############"
echo "load $(cut -d' ' -f1 /proc/loadavg)"
( eval "$VP" nice -n 0 /tmp/fused_logits </dev/null )
echo "fused_logits_exit=$?"

echo
echo "############ DONE ############"
echo "load at end: $(cat /proc/loadavg)"
date
