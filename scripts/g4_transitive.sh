#!/bin/bash
# G4 transitive: a cache must be rejected when an IMPORTED module changes, even
# though the cached module's own source is untouched.
# Bounded: at most 12 lines.
REPO=$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)
V=$(cat "$REPO/VERSION")
ulimit -c 0
Q=${QC:-}
case $Q in /*) ;; *) Q=$(cd "$(dirname "$Q")" 2>/dev/null && pwd)/$(basename "$Q") ;; esac
# Same rule as g4_verify.sh: read the qobj writer's declared version from the
# SOURCE TREE OF THE COMPILER UNDER TEST (QC), not from `cat VERSION` -- a WIP
# gate hands a compiler that VERSION does not name yet.
QROOT="${Q%/bin/x86/qc}"
[ -f "$QROOT/src/x86/qobj_write.quanta" ] || QROOT="$REPO/compiler/$(cat "$REPO/VERSION")"
W=/tmp/g4trans
PASS=0; FAIL=0
chk(){ if [ "$2" = "$3" ]; then echo "  PASS $1 (=$3)"; PASS=$((PASS+1)); else echo "  FAIL $1 (want $2 got $3)"; FAIL=$((FAIL+1)); fi; }
rc(){ set +e; "$1" >/dev/null 2>&1; local r=$?; set -e; echo $r; }

rm -rf $W; mkdir -p $W/lib/std; cd $W || exit 1
printf 'fn leaf(x) {\n  return x + 1\n}\n'                              > lib/std/leaf.quanta
printf 'import std/leaf\nfn mid(x) {\n  return leaf(x) * 2\n}\n'       > lib/std/mid.quanta
printf 'import std/mid\nfn top(x) {\n  return mid(x) + 1\n}\n'        > lib/std/top.quanta
printf 'import std/top\nfn main() {\n  return top(1)\n}\n'            > main.quanta

# top's cache embeds mid AND leaf (it is self-contained), so it must list both.
$Q --emit-qobj lib/std/top.quanta lib/std/top.qobj >/dev/null 2>&1
chk "cache written" 0 "$([ -f lib/std/top.qobj ] && echo 0 || echo 1)"
# Same rule as g4_verify.sh: compare against the writer's declared version
# rather than a literal, so a format bump is not a false failure.
# Take the number AFTER the comma -- grepping all digits would match the 4 in
# "hdr + 4" first and yield 4, not the version.
WVER=$(grep -oE 'w32\(hdr \+ 4, [0-9]+\)' "$QROOT/src/x86/qobj_write.quanta" | head -1 | grep -oE '[0-9]+\)$' | tr -d ')')
CVER=$(python3 -c "
import struct;print(struct.unpack_from('<i',open('lib/std/top.qobj','rb').read(),4)[0])")
chk "version matches writer" "$WVER" "$CVER"
chk "dep_count >= 2 (mid+leaf)" 1 "$(python3 -c "
import struct
d=open('lib/std/top.qobj','rb').read()
print(1 if struct.unpack_from('<I',d,40)[0]>=2 else 0)")"

rm -f a; $Q main.quanta a >/dev/null 2>&1
chk "fresh cache: top(1)=(2*2)+1" 5 "$(rc ./a)"

# THE GAP: change LEAF, an indirect dependency. top.quanta and mid.quanta are
# both untouched, so a cache fingerprinting only its own module would still
# match and the stale result would be reused.
printf 'fn leaf(x) {\n  return x + 100\n}\n' > lib/std/leaf.quanta
rm -f b; $Q main.quanta b >/dev/null 2>&1
chk "TRANSITIVE: leaf(x)=x+100 -> (101*2)+1" 203 "$(rc ./b)"

# one level deeper: change mid, also untouched by top
printf 'fn leaf(x) {\n  return x + 1\n}\n'   > lib/std/leaf.quanta
printf 'import std/leaf\nfn mid(x) {\n  return leaf(x) * 3\n}\n' > lib/std/mid.quanta
$Q --emit-qobj lib/std/top.quanta lib/std/top.qobj >/dev/null 2>&1
rm -f c; $Q main.quanta c >/dev/null 2>&1
chk "baseline: leaf(x)=x+1, mid*3 -> (2*3)+1" 7 "$(rc ./c)"
printf 'import std/leaf\nfn mid(x) {\n  return leaf(x) * 5\n}\n' > lib/std/mid.quanta
rm -f d; $Q main.quanta d >/dev/null 2>&1
chk "mid*5 -> (2*5)+1" 11 "$(rc ./d)"

# cache-only must still work: sources removed, dependencies unreadable.
# Rebuild top's cache FIRST: a dependency that is ABSENT is not treated as
# changed (the G3/G5 contract), so a cache written before the last edit would
# still be served -- correctly, since there is nothing left to compare against.
# The point of this case is that consumption still WORKS with no sources, not
# that a stale cache self-heals.
$Q --emit-qobj lib/std/top.quanta lib/std/top.qobj >/dev/null 2>&1
mkdir -p bk; for m in leaf mid top; do mv lib/std/$m.quanta bk/ 2>/dev/null; done
rm -f co; $Q main.quanta co >/dev/null 2>&1
chk "cache-only still consumes" 11 "$(rc ./co)"
for m in leaf mid top; do mv bk/$m.quanta lib/std/ 2>/dev/null; done

echo "  G4TRANS: $PASS/$((PASS+FAIL))"
[ $FAIL -gt 0 ] && exit 1
exit 0
