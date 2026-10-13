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
# Repo root, resolved now while $0 is still the path the caller used. The gate
# cd's into $W later and run_tests.sh invokes this with a relative path, so a
# $0-derived root would resolve against $W instead of the repo.
REPO=$(cd "$(dirname "$(readlink -f "$0")")/../.." && pwd)
# Absolute, because this script cd's to $W below and the nested harnesses need
# to exec the compiler from there. run_tests.sh passes a repo-relative QC.
case $QC in /*) ;; *) QC=$(cd "$(dirname "$QC")" 2>/dev/null && pwd)/$(basename "$QC") ;; esac
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

# ---- f64 PARAM through the cache (0.0.219) ----------------------------------
# fn_parflt records which params are declared `: f64`, and that flag has to
# survive a round trip through the cache. It did not: a cached module taking an
# f64 param reloaded with the float tag missing, so every float operation on
# that param took the integer path. The failure is SILENT -- no diagnostic, a
# wrong number -- so the integer-only fixtures above could not catch it.
#
# main -> fmath.q -> half(third(12.0)); expected 2.0.
printf 'fn half(x: f64) -> f64 {\n  return x / 2.0\n}\n' > lib/std/half.quanta
printf 'fn third(x: f64) -> f64 {\n  return x / 3.0\n}\n' > lib/std/third.quanta
printf 'import std/half\nimport std/third\nfn q(x: f64) -> f64 {\n  return half(third(x))\n}\n' > lib/std/fmath.quanta
printf 'import std/fmath\nfn main() -> i32 {\n  if q(12.0) != 2.0 { return 1; }\n  return 42\n}\n' > mainf.quanta

rm -f outf_src; $QC mainf.quanta outf_src >/dev/null 2>&1; chk "f64 param source compile" 0 $?
fwant=$(runrc ./outf_src)
if [ "$fwant" = 42 ]; then echo "  PASS f64 param source result (=42)"; PASS=$((PASS+1));
else echo "  FAIL f64 param source result is $fwant, want 42 (fixture broken)"; FAIL=$((FAIL+1)); fi

for m in half third fmath; do $QC --emit-qobj lib/std/$m.quanta lib/std/$m.qobj >/dev/null 2>&1; done
for m in half third fmath; do mv lib/std/$m.quanta $W/bak/ 2>/dev/null; done
rm -f outf_co
$QC mainf.quanta outf_co >/dev/null 2>&1; chk "f64 param cache-only compile" 0 $?
chk "  f64 param cache-only result" "$fwant" "$(runrc ./outf_co)"
for m in half third fmath; do mv $W/bak/$m.quanta lib/std/ 2>/dev/null; done
rm -f lib/std/half.qobj lib/std/third.qobj lib/std/fmath.qobj

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

# ---- G4: stale cache detection ---------------------------------------------
# A cache written from source S must not be reused after S changes. G4 added a
# content fingerprint to the header (v9); this confirms the writer records it and
# that a consume site actually rejects a stale cache.
#
# Checks the RESULT, not merely that a rebuild happened: a rebuild that still
# produced the old answer would satisfy the weaker test. Deliberately folded in
# here rather than made a 15th gate stage -- it is the same fixture and the same
# cache, and a separate stage would be a second place to forget to look.
# Both G4 harnesses: own-source staleness, and the transitive case where an
# IMPORTED module changes while the cached module's own bytes do not.
# G6: the compiler caches itself and builds from that cache with every source
# deleted. The longest case in the gate (~13s), and the only one that runs the
# cache format against the real 327-function compiler rather than a fixture.
if [ -f "$REPO/scripts/g6_selfcache.sh" ]; then
  if QC="$QC" bash "$REPO/scripts/g6_selfcache.sh" > "$W/g6.log" 2>&1; then
    echo "  PASS G6 compiler self-compiles from cache ($(grep -o 'G6: [0-9]*/[0-9]*' "$W/g6.log" | tail -1))"
    PASS=$((PASS+1))
  else
    echo "  FAIL G6 compiler self-compiles from cache:"
    grep FAIL "$W/g6.log" | sed 's/^/    /'
    FAIL=$((FAIL+1))
  fi
else
  echo "  FAIL g6_selfcache.sh missing"
  FAIL=$((FAIL+1))
fi

for g4v in g4_verify g4_transitive; do
  G4V=$REPO/scripts/$g4v.sh
  if [ -f "$G4V" ]; then
    if QC="$QC" bash "$G4V" > "$W/$g4v.log" 2>&1; then
      echo "  PASS G4 $g4v ($(grep -oE 'G4: [0-9]+/[0-9]+|G4TRANS: [0-9]+/[0-9]+' "$W/$g4v.log" | tail -1))"
      PASS=$((PASS+1))
    else
      echo "  FAIL G4 $g4v:"
      grep FAIL "$W/$g4v.log" | sed 's/^/    /'
      FAIL=$((FAIL+1))
    fi
  else
    echo "  FAIL $g4v.sh missing at $G4V"
    FAIL=$((FAIL+1))
  fi
done

echo "  QOBJ: $PASS/$((PASS+FAIL)) GREEN"
[ $FAIL -gt 0 ] && exit 1
exit 0
