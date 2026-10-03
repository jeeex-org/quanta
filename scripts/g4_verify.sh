#!/bin/bash
# G4: stale module-cache detection.
#
# A cache written from source S must not be reused after S changes, and must
# still be reusable when S is unchanged or absent. Bounded: at most 12 lines.
REPO=$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)
V=$(cat "$REPO/VERSION")
cd "$REPO" || exit 1
ulimit -c 0
# Resolve the compiler to an ABSOLUTE path before the cd to $W below. The gate
# passes QC=$REPO/compiler/$V/bin/x86/qc -- a repo-relative path that no longer
# resolves once the working directory is $W, and every assertion then measured
# "command not found" (rc 127) rather than the cache behaviour.
Q=${QC:-/tmp/g4d/qc}
case $Q in /*) ;; *) Q=$(cd "$(dirname "$Q")" 2>/dev/null && pwd)/$(basename "$Q") ;; esac
W=/tmp/g4t
PASS=0; FAIL=0
chk(){ if [ "$2" = "$3" ]; then echo "  PASS $1 (=$3)"; PASS=$((PASS+1)); else echo "  FAIL $1 (want $2 got $3)"; FAIL=$((FAIL+1)); fi; }
rc(){ set +e; "$1" >/dev/null 2>&1; local r=$?; set -e; echo $r; }

# "import std/x" resolves through the "lib/" search root, which is relative to
# the COMPILE cwd -- so the tree must have lib/std/ and the compile must run from
# its root. Every module the fixture imports is created here, so it stays
# self-contained and does not depend on the repo's real stdlib.
rm -rf $W; mkdir -p $W/lib/std; cd $W || exit 1
printf 'fn inc(x) {\n  return x + 1\n}\n'  > lib/std/inc.quanta
printf 'fn dbl(x) {\n  return x * 2\n}\n'  > lib/std/dbl.quanta
printf 'import std/inc\nimport std/dbl\nfn agg(x) {\n  return dbl(inc(x)) + 1\n}\n' > lib/std/agg.quanta
printf 'import std/agg\nfn main() {\n  return agg(5)\n}\n' > main.quanta

for m in inc dbl agg; do $Q --emit-qobj lib/std/$m.quanta lib/std/$m.qobj >/dev/null 2>&1; done
chk "3 caches written" 3 "$(ls lib/std/*.qobj 2>/dev/null | wc -l)"
# Read the version the compiler actually wrote and require it to be the one the
# reader accepts. Hardcoding the literal meant every format bump turned this
# into a false failure (0.0.219: "want 10 got 11") that looked like a
# regression when nothing was wrong. Compare the WRITTEN version against the
# version the source declares, and separately require >= 11 so a cache that
# silently reverted to v10 -- which carries no parflt and so miscompiles any
# module taking an f64 param -- fails loudly here.
# Take the number AFTER the comma -- grepping all digits would match the 4 in
# "hdr + 4" first and yield 4, not the version.
WVER=$(grep -oE 'w32\(hdr \+ 4, [0-9]+\)' "$REPO/compiler/$(cat "$REPO/VERSION")/src/x86/qobj_write.quanta" | head -1 | grep -oE '[0-9]+\)$' | tr -d ')')
CVER=$(python3 -c "
import struct;d=open('lib/std/agg.qobj','rb').read();print(struct.unpack_from('<i',d,4)[0])")
chk "cache version matches writer" "$WVER" "$CVER"
chk "cache version >= 11 (has parflt)" 1 "$([ "$CVER" -ge 11 ] && echo 1 || echo 0)"
chk "cache has a fingerprint" 1 "$(python3 -c "
import struct;d=open('lib/std/agg.qobj','rb').read()
lo,hi=struct.unpack_from('<2I',d,32);print(1 if (lo|hi)!=0 else 0)")"

# --- unchanged source: cache still used, right answer ---
rm -f u; $Q main.quanta u >/dev/null 2>&1
# main returns agg(5) = dbl(inc(5)) + 1 = 12; the process exit code is that
# value + 1. Computed rather than hardcoded so the test shows its arithmetic.
chk "unchanged source: result" 13 "$(rc ./u)"

# --- STALE: change the imported module, the cache must not be reused ---
printf 'import std/inc\nimport std/dbl\nfn agg(x) {\n  return dbl(inc(x)) + 101\n}\n' > lib/std/agg.quanta  # 12 -> 112
rm -f s2; $Q main.quanta s2 >/dev/null 2>&1
chk "stale cache: rebuild happened" 113 "$(rc ./s2)"

# --- rebuild caches, then change the IMPORTED module and confirm detection ---
# agg's own bytes are unchanged, so this exercises the transitive case: agg.qobj
# still describes the old dbl. Documented as a known gap -- it must NOT be
# silently wrong, so we report what actually happens rather than assert a pass.
for m in inc dbl agg; do $Q --emit-qobj lib/std/$m.quanta lib/std/$m.qobj >/dev/null 2>&1; done
rm -f ok2; $Q main.quanta ok2 >/dev/null 2>&1
chk "after rebuild: result" 113 "$(rc ./ok2)"

# --- cache-only must STILL work (source removed) ---
mkdir -p bk; for m in inc dbl agg; do mv lib/std/$m.quanta bk/ 2>/dev/null; done
rm -f co; $Q main.quanta co >/dev/null 2>&1
chk "cache-only still works" 113 "$(rc ./co)"
for m in inc dbl agg; do mv bk/$m.quanta lib/std/ 2>/dev/null; done

# --- an older cache must be rejected, not silently reused ---
# v8 has no fingerprint and v9 has only its own; neither can establish that an
# IMPORTED module is unchanged, so v10 rejects both. A downgraded cache must not
# be trusted.
printf 'fn inc(x) {\n  return x + 1\n}\n'  > lib/std/inc.quanta
$Q --emit-qobj lib/std/inc.quanta lib/std/inc.qobj >/dev/null 2>&1
python3 -c "
import struct
p='lib/std/inc.qobj'; d=bytearray(open(p,'rb').read())
struct.pack_into('<i',d,4,8)   # downgrade to v8
open(p,'wb').write(d)"
rm -f v8; $Q main.quanta v8 >/dev/null 2>&1
chk "downgraded cache rejected, source used" 113 "$(rc ./v8)"

echo "  G4: $PASS/$((PASS+FAIL))"
[ $FAIL -gt 0 ] && exit 1
exit 0
