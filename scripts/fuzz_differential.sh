#!/usr/bin/env bash
# Differential fuzz gate: compile each generated small program WITH and WITHOUT
# -O and assert identical stdout. Any divergence is a real optimizer/correctness
# bug. This locks in the optimizer's correctness so future versions can't silently
# regress it. Exits non-zero on divergence.
set -u
QC="${QC:-./compiler/$(cat VERSION)/bin/x86/qc}"
OUT_DIR="$(mktemp -d)"
N=120
SEED=$$
div=0
# tiny program templates (ints/loops/mem/calls) excluding Options/structs which
# the fuzzer doesn't model
PROGS=(
'fn f(a){return a+1} fn main(){let i=0 let s=0 while i<10 {s=s+f(i) i=i+1} printi(s) println(0) return 0}'
'fn main(){let a=mem_alloc(64) let i=0 while i<8 {mem_store(a+i*8,i) i=i+1} let j=0 let t=0 while j<8 {t=t+mem_load(a+j*8) j=j+1} printi(t) println(0) return 0}'
'fn fib(n){if n<2 {return n} return fib(n-1)+fib(n-2)} fn main(){printi(fib(12)) println(0) return 0}'
'fn main(){let x=7 let y=3 printi(x*y-x/y) println(0) return 0}'
'fn g(a,b){return a*b+b} fn main(){let i=0 let r=1 while i<5 {r=g(r,i) i=i+1} printi(r) println(0) return 0}'
'fn main(){let a=mem_alloc(32) mem_store(a,100) mem_store(a+8,200) let s=mem_load(a)+mem_load(a+8) printi(s) println(0) return 0}'
'fn sq(n){return n*n} fn main(){let i=0 while i<6 {printi(sq(i)) println(0) i=i+1} return 0}'
'fn main(){let x=1 let i=0 while i<16 {x=x*2 i=i+1} printi(x) println(0) return 0}'
)
np=${#PROGS[@]}
for ((k=0;k<N;k++)); do
  src="$OUT_DIR/p$k.quanta"
  idx=$(( (SEED + k) % np ))
  echo "${PROGS[$idx]}" > "$src"
  a="$OUT_DIR/a$k"; b="$OUT_DIR/b$k"
  $QC -O  "$src" "$a" >/dev/null 2>&1
  $QC     "$src" "$b" >/dev/null 2>&1
  chmod +x "$a" "$b" 2>/dev/null
  oa=$("$a" 2>/dev/null); ob=$("$b" 2>/dev/null)
  if [ "$oa" != "$ob" ]; then
    echo "DIVERGE at seed $k (template $idx):"
    echo "  -O : [$oa]"
    echo "  noO: [$ob]"
    echo "  src: ${PROGS[$idx]}"
    div=1
  fi
done
rm -rf "$OUT_DIR"
if [ "$div" = "1" ]; then echo "FAIL: optimizer differential fuzz found divergences"; exit 1; fi
echo "OK: optimizer differential fuzz ($N runs) clean"
exit 0
