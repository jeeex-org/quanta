#!/bin/bash
# G5 verification: cache CONTENT correctness + cache-only consumption, with
# controls that must never regress. Bounded: prints at most 18 lines.
ulimit -c 0
Q=${QC:-/opt/tali/quanta/compiler/0.0.217/bin/x86/qc}
W=/tmp/g5fix
PASS=0; FAIL=0
chk(){ if [ "$2" = "$3" ]; then echo "  PASS $1 (=$3)"; PASS=$((PASS+1)); else echo "  FAIL $1 (want $2 got $3)"; FAIL=$((FAIL+1)); fi; }
rc(){ set +e; "$1" >/dev/null 2>&1; local r=$?; set -e; echo $r; }

# Report which functions in a cache wrongly contain IR_CALL (op 17). Only a
# function that actually calls something may.
audit(){ python3 - "$1" "$2" <<'PY'
import struct,sys
f,expect=sys.argv[1],sys.argv[2]
d=open(f,'rb').read()
m,v,nf,irn,nb,mb,pb,prb=struct.unpack_from('<8I',d,0)
if m!=0x514F424A: print("BADMAGIC"); raise SystemExit
no=32+nf*32; names=d[no:no+nb]
o=no+nb+mb+prb+pb; irb=d[o:o+irn*40]
ents=[struct.unpack_from('<5I',d,32+i*32) for i in range(nf)]
s=0; bad=[]
for i,(so,nl,pc,firn,mo) in enumerate(ents):
    nm=names[so:so+nl].decode()
    ops=[struct.unpack_from('<q',irb,(s+k)*40)[0] for k in range(firn)]
    if (nm!=expect)==(17 in ops): bad.append(nm)
    s+=firn
print("OK" if not bad else ",".join(bad))
PY
}

rm -rf $W; mkdir -p $W/lib/std; cd $W || exit 1
printf 'fn inc(x) {\n  return x + 1\n}\n'  > lib/std/inc.quanta
printf 'fn dbl(x) {\n  return x * 2\n}\n'  > lib/std/dbl.quanta
printf 'import std/inc\nimport std/dbl\nfn agg(x) {\n  return dbl(inc(x)) - 1\n}\n' > lib/std/agg.quanta
printf 'fn sol(x) {\n  return x * 3\n}\n'  > lib/std/sol.quanta
printf 'import std/agg\nfn main() {\n  return agg(5)\n}\n' > main.quanta
printf 'import std/sol\nfn main() {\n  return sol(5)\n}\n' > msol.quanta

rm -f s; $Q main.quanta s >/dev/null 2>&1
chk "control: program w/ imports" 11 "$(rc ./s)"

for m in inc dbl agg sol; do $Q --emit-qobj lib/std/$m.quanta lib/std/$m.qobj >/dev/null 2>&1; done
chk "4 caches written" 4 "$(ls lib/std/*.qobj 2>/dev/null | wc -l)"

rm -f so; $Q msol.quanta so >/dev/null 2>&1
chk "control: single-module cache" 15 "$(rc ./so)"

chk "agg.qobj: only agg has IR_CALL" "OK" "$(audit lib/std/agg.qobj agg)"

mkdir -p $W/bk
for m in inc dbl agg sol; do mv lib/std/$m.quanta $W/bk/ 2>/dev/null; done
chk "all sources removed" 0 "$(ls lib/std/*.quanta 2>/dev/null | wc -l)"
rm -f co; $Q main.quanta co >/dev/null 2>&1
chk "cache-only result agg(5)==11" 11 "$(rc ./co)"

h=""; same=1
for i in 1 2 3; do
  rm -f d; $Q main.quanta d >/dev/null 2>&1
  t=$(md5sum d 2>/dev/null|cut -c1-12); [ -z "$h" ] && h=$t; [ "$t" != "$h" ] && same=0
done
if [ $same -eq 1 ]; then echo "  PASS determinism x3 (md5 $h)"; PASS=$((PASS+1));
else echo "  FAIL determinism x3"; FAIL=$((FAIL+1)); fi
for m in inc dbl agg sol; do mv $W/bk/$m.quanta lib/std/ 2>/dev/null; done

echo "  G5FIX: $PASS/$((PASS+FAIL))"
[ $FAIL -gt 0 ] && exit 1
exit 0
