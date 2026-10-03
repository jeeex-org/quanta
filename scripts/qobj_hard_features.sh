#!/bin/bash
# Harder feature probe: extern calls, generics, multi-module, and the real
# stdlib. These are where a cache is most likely to be an incomplete
# representation of a module rather than a faithful one.
# Bounded: at most 16 lines.
ulimit -c 0
REPO=$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)
# Read VERSION rather than hardcoding a tree: a pinned old compiler makes a gate
# report about a compiler nobody is shipping. Same bug as build_one.sh.
V=$(cat "$REPO/VERSION")
Q=${QC:-$REPO/compiler/$V/bin/x86/qc}
case $Q in /*) ;; *) Q=$(cd "$(dirname "$Q")" 2>/dev/null && pwd)/$(basename "$Q") ;; esac
W=/tmp/qobjhard
PASS=0; GAP=0; SKIP=0
rm -rf $W; mkdir -p $W/lib/std; cd $W || exit 1

# probe <name> <modfiles...> then main; compares source build vs cache-only
probe() {
  local name="$1"; shift
  rm -f s1; $Q main.quanta s1 >/dev/null 2>&1
  local src_rc=127; [ -f s1 ] && { ./s1 >/dev/null 2>&1; src_rc=$?; }
  [ $src_rc = 127 ] && { echo "  SKIP $name (source build failed)"; SKIP=$((SKIP+1)); return; }
  for f in $mods; do $Q --emit-qobj lib/std/$f.quanta lib/std/$f.qobj >/dev/null 2>&1; done
  local nc=0; for f in $mods; do [ -f lib/std/$f.qobj ] && nc=$((nc+1)); done
  [ $nc -lt $(echo $mods | wc -w) ] && { echo "  SKIP $name (only $nc/$(echo $mods|wc -w) caches emitted)"; SKIP=$((SKIP+1)); return; }
  mkdir -p held; for f in $mods; do mv lib/std/$f.quanta held/ 2>/dev/null; done
  rm -f s2; $Q main.quanta s2 >/dev/null 2>&1
  local co_rc=127; [ -f s2 ] && { ./s2 >/dev/null 2>&1; co_rc=$?; }
  for f in $mods; do mv held/$f.quanta lib/std/ 2>/dev/null; done
  if [ $co_rc = $src_rc ]; then echo "  PASS $name (=$src_rc)"; PASS=$((PASS+1));
  else echo "  GAP  $name (src=$src_rc, CACHE-ONLY=$co_rc)"; GAP=$((GAP+1)); fi
}

# --- multi-module chain, 3 deep, each importing the previous ---
printf 'fn a(x) { return x + 1 }\n'      > lib/std/a.quanta
printf 'import std/a\nfn b(x) { return a(x) * 2 }\n' > lib/std/b.quanta
printf 'import std/b\nfn c(x) { return b(x) + a(x) }\n' > lib/std/c.quanta
printf 'import std/c\nfn main() { return c(3) }\n' > main.quanta
mods="a b c"; probe "3-module dependency chain"

# --- diamond: two modules importing the same one ---
printf 'fn sh(x) { return x + 10 }\n'     > lib/std/sh.quanta
printf 'import std/sh\nfn L(x) { return sh(x) * 2 }\n' > lib/std/L.quanta
printf 'import std/sh\nfn R(x) { return sh(x) * 3 }\n' > lib/std/R.quanta
printf 'import std/L\nimport std/R\nfn main() { return L(1) + R(1) }\n' > main.quanta
mods="sh L R"; probe "diamond import (shared dep)"

# --- generics ---
printf 'fn idg(x) { return x }\n' > lib/std/idg.quanta
printf 'import std/idg\nfn main() { return idg(41) + 1 }\n' > main.quanta
mods="idg"; probe "generic-typed function"

# --- extern C call inside a cached module ---
cat > lib/std/xc.quanta <<'EOF'
extern "C" fn abs(x);
fn useabs(x) { return abs(x) }
EOF
printf 'import std/xc\nfn main() { return useabs(0 - 5) }\n' > main.quanta
mods="xc"; probe "extern C call in cached module"

# --- a REAL stdlib module, cached and consumed ---
rm -rf lib/std/*.quanta lib/std/*.qobj held
REAL=$(ls $REPO/lib/std/*.quanta | head -1)
cp "$REAL" lib/std/realmod.quanta
if grep -q '^fn ' lib/std/realmod.quanta; then
  printf 'import std/realmod\nfn main() { return 0 }\n' > main.quanta
  mods="realmod"; probe "real stdlib module"
else
  echo "  SKIP real stdlib module (no plain fn)"; SKIP=$((SKIP+1))
fi

echo "  QOBJHARD: $PASS full, $GAP gaps, $SKIP skipped"
exit 0
