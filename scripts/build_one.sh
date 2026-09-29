#!/bin/bash
# Build the compiler from source with the INSTALLED qc, one generation, bounded.
# Deletes outputs first and verifies the binary really was produced.
ulimit -c 0
REPO=/opt/tali/quanta
V=0.0.217
SRC=$REPO/compiler/$V/src/x86
OUT=${1:-/tmp/g9/b1}
Q=${QC:-$REPO/compiler/$V/bin/x86/qc}
mkdir -p $OUT
rm -f $OUT/qc
cd $SRC || exit 1
timeout 900 $Q main.quanta $OUT/qc > $OUT/build.log 2>&1
rc=$?
echo "build_rc=$rc"
if [ -f $OUT/qc ]; then
  echo "size=$(stat -c%s $OUT/qc) md5=$(md5sum $OUT/qc | cut -c1-32)"
  chmod +x $OUT/qc
else
  echo "NO BINARY"; tail -5 $OUT/build.log
fi
