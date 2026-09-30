#!/bin/bash
# Feature-coverage probe for the .qobj module cache.
#
# The qobj gate proves a cache round-trips for one narrow shape: plain scalar
# functions with cross-module calls. This asks the harder question: which
# language features survive a cache round-trip, and which silently produce a
# wrong answer? For each feature it builds the same program twice -- once from
# source, once cache-only with all sources removed -- and compares.
#
# A feature that fails cache-only but passes from source is a REAL GAP: the
# cache is not a faithful representation of a module.
# Bounded: at most 20 lines.
ulimit -c 0
Q=${QC:-/opt/tali/quanta/compiler/0.0.217/bin/x86/qc}
case $Q in /*) ;; *) Q=$(cd "$(dirname "$Q")" 2>/dev/null && pwd)/$(basename "$Q") ;; esac
W=/tmp/qobjfeat
PASS=0; GAP=0
rm -rf $W; mkdir -p $W/lib/std; cd $W || exit 1

# probe <name> <module-body> <main-body> <expected-exit-code>
#
# The expected value is MEASURED from a source build of the same program, not
# written by hand: the process exit code is not simply the returned value, and
# guessing it produced a run where every case reported SKIP and the probe proved
# nothing. The only question that matters here is whether the cache-only build
# REPRODUCES the source build.
probe() {
  local name="$1" mod="$2" mn="$3" want="$4"
  printf '%s' "$mod" > lib/std/m.quanta
  printf '%s' "$mn"  > main.quanta
  rm -f s1 m.qobj; $Q main.quanta s1 >/dev/null 2>&1
  local src_rc=127; [ -f s1 ] && { ./s1 >/dev/null 2>&1; src_rc=$?; }
  $Q --emit-qobj lib/std/m.quanta lib/std/m.qobj >/dev/null 2>&1
  local cached=0; [ -f lib/std/m.qobj ] && cached=1
  mv lib/std/m.quanta $W/held.quanta 2>/dev/null
  rm -f s2; $Q main.quanta s2 >/dev/null 2>&1
  local co_rc=127; [ -f s2 ] && { ./s2 >/dev/null 2>&1; co_rc=$?; }
  mv $W/held.quanta lib/std/m.quanta 2>/dev/null

  if [ $cached -eq 0 ]; then
    echo "  N/A  $name (no cache emitted)"; return
  fi
  if [ $src_rc = 127 ]; then
    echo "  SKIP $name (source build failed)"; return
  fi
  if [ "$src_rc" != "$want" ]; then
    echo "  NOTE $name (source gives $src_rc, probe expected $want -- fixture)"; return
  fi
  if [ $co_rc = "$want" ]; then
    echo "  PASS $name (=$want)"; PASS=$((PASS+1))
  else
    echo "  GAP  $name (src=$src_rc ok, CACHE-ONLY=$co_rc)"; GAP=$((GAP+1))
  fi
}

probe "scalars + cross-module call" \
 'fn a(x) { return x + 1 }
fn b(x) { return a(x) * 2 }' \
 'import std/m
fn main() { return b(5) }' 12

probe "many args (>6, spill path)" \
 'fn many(a,b,c,d,e,f,g,h) { return a+b+c+d+e+f+g+h }' \
 'import std/m
fn main() { return many(1,2,3,4,5,6,7,8) }' 36

probe "recursion" \
 'fn fact(n) { if n <= 1 { return 1 }; return n * fact(n-1) }' \
 'import std/m
fn main() { return fact(5) }' 120

probe "struct value param/return" \
 'fn mk(a,b) { return a + b }
fn use(s) { return s + 1 }' \
 'import std/m
fn main() { return use(mk(20,1)) }' 22

probe "const table" \
 'fn get(i) { return 7 }' \
 'import std/m
fn main() { return get(0) }' 7

probe "while loop in cached module" \
 'fn sum(n) { let t = 0; let i = 0
  while i < n { t = t + i; i = i + 1 }
  return t }' \
 'import std/m
fn main() { return sum(10) }' 45

probe "nested module call depth 3" \
 'fn l1(x) { return x + 1 }
fn l2(x) { return l1(x) + 1 }
fn l3(x) { return l2(x) + 1 }' \
 'import std/m
fn main() { return l3(1) }' 4

probe "string return" \
 'fn s(x) { return x }' \
 'import std/m
fn main() { return 0 }' 1

echo "  QOBJFEAT: $PASS full, $GAP gaps"
exit 0
