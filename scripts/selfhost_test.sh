#!/bin/bash
# SELF-HOSTING TEST: the compiler must compile itself to a fixed point.
#
# gen0 = the installed binary
# gen1 = gen0 compiling the compiler source
# gen2 = gen1 compiling the compiler source
# gen3 = gen2 compiling the compiler source
#
# A correct self-hosting compiler is a FIXED POINT: gen1, gen2 and gen3 must be
# byte-identical, and each must still run the suite. This is a much stronger
# statement than "the compiler builds" -- a compiler with a nondeterministic or
# unstable backend can build once and then drift, and that drift is exactly what
# makes a module cache (G4/G6) untrustworthy.
#
# Bounded: prints at most 16 lines.
ulimit -c 0
REPO=/opt/tali/quanta
# Read VERSION, and let QC= override the builder. This used to hardcode 0.0.217,
# so it silently tested the previous stable tree no matter what was installed --
# and a full-gate PASS against a binary that is not the one under test is not
# evidence for that source at all. SRC, QC0 and the gate binaries must all be
# the tree actually being verified.
V=$(cat $REPO/VERSION)
SRC=$REPO/compiler/$V/src/x86
QC0=${QC:-$REPO/compiler/$V/bin/x86/qc}
[ -f "$QC0" ] || { echo "  FAIL no builder at $QC0"; exit 1; }
WORK=${1:-/tmp/selfhost}
PASS=0; FAIL=0
chk(){ if [ "$2" = "$3" ]; then echo "  PASS $1 (=$3)"; PASS=$((PASS+1)); else echo "  FAIL $1 (want $2 got $3)"; FAIL=$((FAIL+1)); fi; }

rm -rf $WORK; mkdir -p $WORK

build() { # $1=builder binary  $2=out dir
  mkdir -p "$2"
  ( cd $SRC && timeout 900 "$1" main.quanta "$2/qc" > "$2/build.log" 2>&1 )
  if [ ! -f "$2/qc" ]; then
    echo "    build failed:"; tail -2 "$2/build.log" | sed 's/^/      /'; return 1
  fi
  chmod +x "$2/qc"
  return 0
}

echo "  gen0 (installed): $(md5sum $QC0 2>/dev/null | cut -c1-12)"
for g in 1 2 3; do
  prev=$QC0; [ $g -gt 1 ] && prev=$WORK/gen$((g-1))/qc
  if build "$prev" "$WORK/gen$g"; then
    echo "  gen$g built:      $(md5sum $WORK/gen$g/qc | cut -c1-12)"
  else
    echo "  FAIL gen$g did not build"; FAIL=$((FAIL+1)); break
  fi
done
[ $FAIL -eq 0 ] || { echo "  SELFH: $PASS/$((PASS+FAIL))"; exit 1; }

h1=$(md5sum $WORK/gen1/qc | cut -d' ' -f1)
h2=$(md5sum $WORK/gen2/qc | cut -d' ' -f1)
h3=$(md5sum $WORK/gen3/qc | cut -d' ' -f1)
chk "gen1 == gen2 (fixed point)" "$h1" "$h2"
chk "gen2 == gen3 (stable)"     "$h2" "$h3"

# Each generation must still run the whole suite. A compiler that self-hosts
# into something that no longer works is not a fixed point. run_tests.sh honours
# QC=..., so drive it directly rather than through run_gate.sh (which always uses
# the installed binary and would silently test gen0 instead).
gate_gen() { # $1=gen binary  $2=log
  ( cd $REPO && QC="$1" timeout 1800 bash test_suites/scripts/run_tests.sh > "$2" 2>&1 )
}
# Verify a gate run. Stage count is NOT hardcoded: it is counted from the log and
# cross-checked against the summary, so adding a stage does not turn this RED and
# a stage that is missing from the summary is caught. (Both a hardcoded 14 here
# and the hardcoded V= above were the same mistake: a constant that silently rots.)
#
# The one absolute is "at least 12": a truncated log must not pass by being small.
verify_gate() { # $1=binary  $2=log  $3=label
  gate_gen "$1" "$2"
  chk "$3 gate exit code" 0 "$?"

  local body summary red
  body=$(grep -cE '^##########' "$2")
  summary=$(sed -n '/GATE SUMMARY/,$p' "$2" | grep -cE ': (GREEN|RED)')
  red=$(grep ': RED' "$2" | wc -l)

  [ "$body" -ge 12 ] || { echo "  FAIL $3 gate: only $body stages logged (log truncated?)"; FAIL=$((FAIL+1)); }
  chk "$3 gate: summary covers every stage" "$body" "$summary"
  chk "$3 gate: 0 RED" 0 "$red"
}
verify_gate $WORK/gen1/qc $WORK/g1.log gen1
verify_gate $WORK/gen3/qc $WORK/g3.log gen3

echo "  SELFH: $PASS/$((PASS+FAIL))"
[ $FAIL -gt 0 ] && exit 1
exit 0
