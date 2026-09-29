#!/bin/bash
# Bounded G5 diagnostic: MEASURE stack depth and whether rsp lands inside an
# arena mapping. Prints at most 20 lines. No unbounded dumps.
ulimit -c 0
REPO=/opt/tali/quanta
Q=${QC:-$REPO/compiler/0.0.217/bin/x86/qc}
P=/tmp/g9/stk
D=/tmp/g9/stk
rm -rf $P; mkdir -p $P/lib/std
printf 'fn helper(x) {\n  return x + 1\n}\n' > $P/lib/std/one.quanta
printf 'import std/one\nfn main() {\n  printi(helper(41))\n  return 0\n}\n' > $P/main.quanta
(cd $P && timeout 30 $Q --emit-qobj lib/std/one.quanta lib/std/one.qobj >/dev/null 2>&1)
echo "cache: $([ -f $P/lib/std/one.qobj ] && stat -c%s $P/lib/std/one.qobj || echo NONE)"
rm -f $P/lib/std/one.quanta

cat > $D/g.cmds <<'EOF'
set pagination off
set confirm off
run
echo \n====FAULT====\n
info registers rip rsp rbp rbx
echo \n====MAPS_NEAR_RSP====\n
info proc mappings
echo \n====END====\n
quit
EOF

(cd $P && timeout 90 gdb -batch -x $D/g.cmds "$Q" 2>&1) > $D/out.txt 2>&1
echo "gdb_rc=$?"
grep -E '====|^(rip|rsp|rbp|rbx) ' $D/out.txt | head -8
echo "--- mapping containing rsp / program header ---"
python3 - "$D/out.txt" <<'PY'
import re,sys
txt=open(sys.argv[1],errors='replace').read()
regs=dict(re.findall(r'^(rip|rsp|rbp|rbx)\s+(0x[0-9a-f]+)',txt,re.M))
maps=[]
for a,b in re.findall(r'^\s*(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s',txt,re.M):
    maps.append((int(a,16),int(b,16)))
rsp=int(regs.get('rsp','0'),16)
print("rsp = 0x%x" % rsp)
for a,b in maps:
    if a<=rsp<b:
        print("RSP IN MAPPING 0x%x-0x%x  size=%.1fMB  rsp_ofs=0x%x"%(a,b,(b-a)/1e6,rsp-a))
        break
else:
    print("rsp not in any listed mapping (stack guard/unmapped)")
# find the 8MB-ish stack window: the mapping that ends highest near rsp
cand=[(a,b) for a,b in maps if b>a and (b-a)<=0x2000000 and b>rsp]
if cand:
    a,b=max(cand,key=lambda t:t[1])
    print("stack window 0x%x-0x%x size=%.1fMB"%(a,b,(b-a)/1e6))
    print("depth below top = %.1f MB"%(((b)-rsp)/1e6))
PY
