#!/bin/bash
# QOBJ GATE (G1-G5): module cache write, read, and cache-only consumption.
#
# Multi-file by nature, so it lives here rather than in EXPECTED.tsv. The cases
# below are the ones that actually discriminate: a single-function module with
# no calls passes even when the cache is broken, so the cache cases use
# MULTIPLE functions and CROSS-MODULE calls.
#
# The expected value is validated against a source build of the SAME program
# first. That is deliberate: a fixture that also trips an unrelated compiler
# bug would report as a qobj failure and send the next person chasing the
# wrong thing. (A caller defined in an importing file currently returns a wrong
# value -- pre-existing, reproducible on aed9d194 -- so callers stay in their
# own module and only MAIN crosses a module boundary.)
#
# Prints at most 20 lines.
ulimit -c 0
QC="${QC:?QC must be set}"
W=/tmp/qobj_gate
PASS=0; FAIL=0

rm -rf $W; mkdir -p $W/lib/std
cd $W || exit 1

chk() { # name expected actual
  if [ "$2" = "$3" ]; then echo "  PASS $1 (=$3)"; PASS=$((PASS+1));
  else echo "  FAIL $1 (expected $2, got $3)"; FAIL=$((FAIL+1)); fi
}
runrc() { set +e; "$1" >/dev/null 2>&1; local r=$?; set -e; echo $r; }

# ---- fixtures: main -> agg -> {inc, dbl} is a real cross-module chain --------
printf 'fn inc(x) {\n  return x + 1\n}\n' > lib/std/inc.quanta
printf 'fn dbl(x) {\n  return x * 2\n}\n' > lib/std/dbl.quanta
printf 'import std/inc\nimport std/dbl\nfn agg(x) {\n  return dbl(inc(x)) - 1\n}\n' > lib/std/agg.quanta
printf 'import std/agg\nfn main() {\n  return agg(5)\n}\n' > main.quanta

# ---- control: source build, and pin the expected value ---------------------
rm -f out_src
$QC main.quanta out_src >/dev/null 2>&1; chk "control source compile" 0 $?
want=$(runrc ./out_src)
if [ "$want" = 11 ]; then echo "  PASS control source result agg(5)==11"; PASS=$((PASS+1));
else echo "  FAIL control source result is $want, want 11 (fixture broken)"; FAIL=$((FAIL+1)); fi

# ---- G1: --emit-qobj writes a READABLE cache --------------------------------
for m in inc dbl agg; do $QC --emit-qobj lib/std/$m.quanta lib/std/$m.qobj >/dev/null 2>&1; done
chk "G1 three caches written" 3 "$(ls lib/std/*.qobj 2>/dev/null | wc -l)"
allread=1; for f in lib/std/*.qobj; do [ -r "$f" ] || allread=0; done
if [ $allread = 1 ]; then echo "  PASS G1 caches readable (mode $(stat -c%a lib/std/inc.qobj))"; PASS=$((PASS+1));
else echo "  FAIL G1 a cache is NOT readable (mode $(stat -c%a lib/std/inc.qobj 2>/dev/null))"; FAIL=$((FAIL+1)); fi

# ---- G3: cache preferred when source is also present ------------------------
rm -f out_both; $QC main.quanta out_both >/dev/null 2>&1; chk "G3 src+cache compile" 0 $?
chk "  G3 src+cache result" "$want" "$(runrc ./out_both)"

# ---- G5: CACHE ONLY, every imported source removed --------------------------
mkdir -p $W/bak
for m in inc dbl agg; do mv lib/std/$m.quanta $W/bak/ 2>/dev/null; done
chk "G5 all imported sources removed" 0 "$(ls lib/std/*.quanta 2>/dev/null | wc -l)"
rm -f out_co
$QC main.quanta out_co >/dev/null 2>&1; chk "G5 cache-only compile" 0 $?
chk "  G5 cache-only result" "$want" "$(runrc ./out_co)"
mv $W/bak/*.quanta lib/std/ 2>/dev/null

# ---- G5: determinism (byte-identity) ---------------------------------------
h=""; same=1
for i in 1 2 3; do
  for m in inc dbl agg; do mv lib/std/$m.quanta $W/bak/ 2>/dev/null; done
  rm -f out_d; $QC main.quanta out_d >/dev/null 2>&1
  t=$(md5sum out_d 2>/dev/null | cut -c1-12)
  [ -z "$h" ] && h=$t
  [ "$t" != "$h" ] && same=0
  for m in inc dbl agg; do mv $W/bak/$m.quanta lib/std/ 2>/dev/null; done
done
if [ $same = 1 ] && [ -n "$h" ]; then echo "  PASS G5 cache-only deterministic (md5 $h)"; PASS=$((PASS+1));
else echo "  FAIL G5 cache-only NOT deterministic ($h)"; FAIL=$((FAIL+1)); fi

echo "  QOBJ: $PASS/$((PASS+FAIL)) GREEN"
[ $FAIL -gt 0 ] && exit 1
exit 0
