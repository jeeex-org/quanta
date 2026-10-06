#!/bin/bash
# Self-host consistency: the shipped compiler must behave the same as a
# compiler rebuilt from the shipped compiler's own source.
#
# WHY THIS EXISTS
# ---------------
# A gate that runs only against compiler/$V/bin/x86/qc cannot detect that the
# binary and the source disagree. Every other stage compiles fixtures with the
# SHIPPED binary; if source has drifted, they all still pass, because the correct
# binary is what they use. The drift is invisible until someone rebuilds, and
# then it looks like a random regression.
#
# That is not hypothetical. With the binary correct and parse_while() in the
# source disagreeing about `continue`, all 19 gate stages reported GREEN while
# the tree was broken; rebuilding from source turned `functional` RED with
# break_continue.quanta computing s=25 against a golden 36.
#
# The fix for that class is a byte-identity check too: the rebuild embeds
# absolute build-time addresses in 32-byte stack-slot initialisers, so the two
# binaries are never byte-identical even when correct. Byte comparison would
# report a permanent false failure. Hence the behavioural comparison below --
# same fixture set, both compilers, outputs must agree exactly.
#
# A compiler that cannot rebuild itself is not self-hosting regardless of what
# its own gate says.
#
# Read VERSION; never pin a tree here. A pinned old compiler makes this stage
# report about a compiler nobody ships.
ulimit -c 0 2>/dev/null || true

REPO=$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)
V=$(cat "$REPO/VERSION")
QC=${QC:-$REPO/compiler/$V/bin/x86/qc}
case $QC in /*) ;; *) QC=$(cd "$(dirname "$QC")" 2>/dev/null && pwd)/$(basename "$QC") ;; esac

W=/tmp/selfhost_consistency
PASS=0; FAIL=0
chk(){ if [ "$2" = "$3" ]; then echo "  PASS $1 (=$3)"; PASS=$((PASS+1)); else echo "  FAIL $1 (want $2 got $3)"; FAIL=$((FAIL+1)); fi; }

rm -rf $W; mkdir -p $W || exit 1

[ -x "$QC" ] || { echo "  FAIL no shipped compiler at $QC"; echo "  SELFHOST: 0/1"; exit 1; }
[ -f "$REPO/compiler/$V/src/x86/main.quanta" ] || { echo "  FAIL no source tree for $V"; echo "  SELFHOST: 0/1"; exit 1; }

# ---- 1. rebuild the compiler from its own source -----------------------------
if ! "$QC" "$REPO/compiler/$V/src/x86/main.quanta" "$W/qc_selfbuilt" >"$W/build.log" 2>&1; then
  echo "  FAIL could not rebuild $V from source"
  sed 's/^/    /' "$W/build.log" | head -20
  echo "  SELFHOST: 0/1"; exit 1
fi
chk "compiler rebuilds from source" 1 "$([ -x "$W/qc_selfbuilt" ] && echo 1 || echo 0)"

# ---- 2. the fixture set: one file per behaviour the rebuild could break ------
# Chosen for what drifted before, not for coverage theatre. break_continue is
# the continue-target case; the string cases are the string-literal-pointer
# case (a string expression is the [u64 len][chars][NUL] HEADER pointer, and
# pointing it at the characters instead shifts print/str/substr by 8).
mkdir -p $W/fix || exit 1
cat > $W/fix/continue_in_while.quanta <<'EOF'
fn main() {
  let s=0 let i=0
  while i<10 { i=i+1; if i%2==0 { continue }; s=s+i }
  if s!=25 { return 1 }
  let t=0 let j=0
  while j<10 { j=j+1; if j%3==0 { continue }; t=t+j }
  if t!=37 { return 2 }
  return 0
}
EOF
cat > $W/fix/break_nested.quanta <<'EOF'
fn main() {
  let c=0 let a=0
  while a<3 { a=a+1; let b=0; while b<10 { b=b+1; if b==2 { break }; c=c+1 } }
  if c!=3 { return 3 }
  let n=0 let x=0
  while x<99 { x=x+1; if x==1 { break }; n=n+1 }
  if n!=0 { return 4 }
  return 0
}
EOF
cat > $W/fix/string_literal.quanta <<'EOF'
fn main() {
  let s="hello"
  print(s)
  print(s.len())
  print(s+"!")
  let a=s[0]
  print(a)
  let n=0 let i=0
  while i<s.len() { n=n+s[i]; i=i+1 }
  print(n)
  return 0
}
EOF
cat > $W/fix/int_and_f64.quanta <<'EOF'
fn sq(x) { return x * x }
fn main() {
  print(42)
  print(-7)
  print(sq(3.5))
  return 0
}
EOF

# ---- 3. same fixtures, both compilers, identical behaviour -------------------
# Compares stdout AND exit status. Exit status alone is too weak: a compiler
# that printed garbage and returned 0 would pass.
SAME=1; TOTAL=0
for f in $W/fix/*.quanta; do
  base=$(basename "$f" .quanta)
  TOTAL=$((TOTAL+1))
  for who in shipped selfbuilt; do
    [ $who = shipped ] && bin="$QC" || bin="$W/qc_selfbuilt"
    out=$W/$base.$who
    if ! "$bin" "$f" "$out" >/dev/null 2>&1; then :; fi
  done
  a=$( { "$W/$base.shipped" 2>&1; echo "rc=$?"; } )
  b=$( { "$W/$base.selfbuilt" 2>&1; echo "rc=$?"; } )
  if [ "$a" != "$b" ]; then
    SAME=0
    echo "  FAIL $base: shipped and self-built disagree"
    echo "    shipped:   ${a}"
    echo "    selfbuilt: ${b}"
  else
    echo "  PASS $base agrees"
    PASS=$((PASS+1))
  fi
done
chk "all $TOTAL fixtures agree" 1 "$SAME"

# ---- 4. the rebuild is itself a working compiler -----------------------------
# A self-built compiler that agrees on these four fixtures but is broken
# elsewhere would still be a regression. Compile one real gate fixture with it
# and require the golden answer, so "agrees with shipped" cannot be satisfied by
# two equally broken compilers.
REAL=$REPO/test_suites/codes/break_continue.quanta
if [ -f "$REAL" ]; then
  if "$W/qc_selfbuilt" "$REAL" "$W/bc" >/dev/null 2>&1; then
    rc=$( { "$W/bc" >/dev/null 2>&1; echo $?; } )
    # break_continue returns 0 only when continue and break are both correct.
    chk "self-built passes break_continue golden" 0 "$rc"
  else
    echo "  FAIL self-built compiler could not compile break_continue.quanta"; FAIL=$((FAIL+1))
  fi
else
  echo "  SKIP break_continue golden (fixture absent)"
fi

echo "  SELFHOST: $PASS/$((PASS+FAIL))"
[ $FAIL -gt 0 ] && exit 1
exit 0