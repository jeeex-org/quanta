#!/bin/bash
# scripts/bench_instr.sh — LOAD-INDEPENDENT codegen metrics for the benchmarks/ suite.
#
# WHY THIS EXISTS
# ---------------
# This box is throttled (governor `powersave`) and contended (the `Hermes` backend
# holds several cores all day), so wall-clock ratios swing +-17 % on rows that
# produce BYTE-IDENTICAL machine code (`benchmarks/BENCHMARK.md` table 3). For
# codegen work that is the wrong instrument. This script measures what does not
# move with load:
#   * instruction count per function (emitted, not executed)
#   * HOT-LOOP body size: the innermost backward branch and its target, which is
#     the number that actually decides a loop benchmark's runtime
#   * frame bytes (`sub $0xNNN,%rsp` in the prologue)
#   * frame-relative memory operations per function (`(%rbp`) — spill/reload traffic
#   * call count per function
# It compiles each Quanta twin with `--emit-obj` (which carries a symbol table)
# and each C twin with `gcc -O2`, then disassembles both with
# `objdump -d --no-show-raw-insn`.
#
# Usage: scripts/bench_instr.sh <qc> [--only a,b,c] [--fn name] [--tsv FILE]
#   <qc>        path to a Quanta compiler binary (golden or a WIP tree's qc)
#   --fn name   function to summarise (default: main)
#   --tsv FILE  append rows as TSV for before/after diffs
#
# TSV columns:
# case q_fn q_instr q_loop q_frame q_mem q_calls q_text c_instr c_loop c_frame c_mem c_calls
set -u
REPO=/opt/tali/quanta
cd "$REPO" || exit 1
QC="${1:-}"; shift 2>/dev/null || true
ONLY=""; FN="main"; TSV=""
while [ $# -gt 0 ]; do
  case "$1" in
    --only) ONLY="$2"; shift 2 ;;
    --fn)   FN="$2"; shift 2 ;;
    --tsv)  TSV="$2"; shift 2 ;;
    *) echo "usage: scripts/bench_instr.sh <qc> [--only a,b] [--fn name] [--tsv FILE]" >&2; exit 2 ;;
  esac
done
[ -x "$QC" ] || { echo "bench_instr.sh: no compiler at '$QC'" >&2; exit 1; }

OUT="${BENCH_INSTR_DIR:-/tmp/bench_instr}"; rm -rf "$OUT"; mkdir -p "$OUT"
# The compiler needs its own address-space ceiling (dies silently below ~6 GB).
ulimit -c 0
ulimit -v 8000000 2>/dev/null || true

# One awk program, used for both sides. Per function `want`:
#   instr  instructions in the function
#   loop   instructions in the innermost backward-branch loop (0 = none)
#   frame  the FIRST `sub $0x..,%rsp` imm (the prologue; later ones are inline)
#   mem    instructions with a (%rbp frame operand — spill/reload traffic
#   calls  call instructions
#   hst    home STORES function-wide  (mov %rXX,-N(%rbp...) — register -> frame)
#   hld    home LOADS  function-wide  (mov -N(%rbp...),%rXX — frame -> register)
#   lst    home STORES inside the hot-loop body
#   lld    home LOADS  inside the hot-loop body
# A home op must be a mov-family instruction with an (%rbp memory operand;
# `lea` is an address computation, not a memory access, and is excluded.
# Both SIB spellings objdump emits are matched: `-0x78(%rbp,%riz,1)` (the
# store emitter's encoding) and plain `-0x50(%rbp)` (loads).
AWKPROG='
  /^[0-9a-f]+ <.*>:/ { name=$2; gsub(/[<>:]/,"",name); infn=(name==want); seenfrm=0; next }
  infn && /^[[:space:]]*[0-9a-f]+:/ {
    n=split($0,a,"\t"); txt=(n>=2?a[2]:$0)
    addr=$1; sub(/:$/,"",addr); ia=strtonum("0x" addr)
    ord[ic]=ia; ic++
    instr++
    if (txt ~ /\(%rbp/) mem++
    if (txt ~ /^call/) calls++
    ismov=(txt ~ /^(mov|movz|movs)/)
    hs=0; hl=0
    if (ismov && txt ~ /\(%rbp/) {
      if (txt ~ /\(%rbp[^)]*\),%/) hl=1
      else if (txt ~ /%[a-z0-9]+,-[x0-9a-f]*\(%rbp/) hs=1
    }
    hst+=hs; hld+=hl
    hst_at[ic]=hs; hld_at[ic]=hl
    if (seenfrm==0 && txt ~ /sub[[:space:]]+\$0x[0-9a-f]+,%rsp/) {
      f=txt; sub(/.*sub[[:space:]]+\$/,"",f); sub(/,%rsp.*/,"",f); frame=strtonum(f); seenfrm=1
    }
    # backward branch -> candidate loop. Keep the LARGEST span: in these
    # benchmarks the hot while-loop dwarfs the inlined print/itoa helpers, and
    # `small` would pick the helper. The count is printed so the choice is visible.
    if (txt ~ /^j/) {
      w=split(txt, b, /[[:space:]]+/)
      if (w>=2 && b[2] ~ /^[0-9a-f]+$/) {
        ta=strtonum("0x" b[2])
        if (ta < ia) { nback++; span=ia-ta; if (span>loopspan) { loopspan=span; lo=ta; hi=ia } }
      }
    }
  }
  END {
    if (loopspan>0) for (k=0;k<ic;k++) if (ord[k]>=lo && ord[k]<=hi) { loop++; lst+=hst_at[k]; lld+=hld_at[k] }
    printf "%d %d %d %d %d %d %d %d %d %d", instr+0, loop+0, frame+0, mem+0, calls+0, nback+0, hst+0, hld+0, lst+0, lld+0
  }'

echo "# scripts/bench_instr.sh — load-independent codegen metrics"
echo "# qc=$QC  fn=$FN  load: $(uptime | sed 's/.*average: //')  governor: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null)"
echo "# resp: $(top -bn1 2>/dev/null | awk 'NR>7 && $9+0>50 {printf "%s(%s%%) ",$12,$9}' | head -c 200)"
printf '%-24s %7s %6s %7s %5s %5s %5s %5s | %7s %6s %7s %5s %5s %5s %5s\n' case q_instr q_loop q_frame q_st q_ld q_l_st q_l_ld c_instr c_loop c_frame c_st c_ld c_l_st c_l_ld
[ -n "$TSV" ] && printf 'case\tq_instr\tq_loop\tq_frame\tq_mem\tq_calls\tq_text\tq_brs\tq_hst\tq_hld\tq_lst\tq_lld\tc_instr\tc_loop\tc_frame\tc_mem\tc_calls\tc_brs\tc_hst\tc_hld\tc_lst\tc_lld\n' >> "$TSV"

for q in "$REPO"/benchmarks/benchmark_*.quanta; do
  b=$(basename "$q" .quanta); short="${b#benchmark_}"
  if [ -n "$ONLY" ] && ! printf '%s' ",$ONLY," | grep -q ",$short,"; then continue; fi
  c="$REPO/benchmarks/$b.c"
  qo="$OUT/$short.o"; co="$OUT/${short}_c.o"
  if ! "$QC" "$q" "$qo" --emit-obj >/dev/null 2>&1; then
    printf '%-24s %s\n' "$short" COMPILE_FAIL; continue
  fi
  qd="$OUT/$short.qd"; objdump -d --no-show-raw-insn "$qo" > "$qd" 2>/dev/null
  read -r qi ql qf qm qc qb qhst qhld qlst qlld <<<"$(awk -v want="$FN" "$AWKPROG" "$qd")"
  qt=$(awk '/^[[:space:]]*[0-9a-f]+:/{n++} END{print n+0}' "$qd")
  if [ -f "$c" ] && gcc -O2 -c "$c" -o "$co" 2>/dev/null; then
    cd="$OUT/$short.cd"; objdump -d --no-show-raw-insn "$co" > "$cd" 2>/dev/null
    read -r ci cl cf cm cc cb chst chld clst clld <<<"$(awk -v want="$FN" "$AWKPROG" "$cd")"
  else read -r ci cl cf cm cc cb chst chld clst clld <<<"- - - - - - - - - -"; fi

  printf '%-24s %7s %6s %7s %5s %5s %5s %5s | %7s %6s %7s %5s %5s %5s %5s\n' \
    "$short" "$qi" "$ql" "$qf" "$qhst" "$qhld" "$qlst" "$qlld" "$ci" "$cl" "$cf" "$chst" "$chld" "$clst" "$clld"
  [ -n "$TSV" ] && printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$short" "$qi" "$ql" "$qf" "$qm" "$qc" "$qt" "$qb" "$qhst" "$qhld" "$qlst" "$qlld" "$ci" "$cl" "$cf" "$cm" "$cc" "$cb" "$chst" "$chld" "$clst" "$clld" >> "$TSV"
done
echo "# load after: $(uptime | sed 's/.*average: //')"
