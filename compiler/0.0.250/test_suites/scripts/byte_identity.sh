#!/bin/bash
# Phase-3 byte-identity accounting: compile every EXPECTED.tsv row with the
# predecessor golden and the new golden, and count byte-identical rows.
# Usage: byte_identity.sh <old_qc> <new_qc> [expected.tsv]
set -u
cd /opt/tali/quanta || exit 1
OLD="$1"; NEW="$2"; EXP="${3:-test_suites/EXPECTED.tsv}"
OUT=/tmp/ph3/bi
rm -rf "$OUT"; mkdir -p "$OUT"
ulimit -c 0
IDENT=0; DIFF=0; CFAIL=0
: > "$OUT/ident.txt"; : > "$OUT/diff.txt"; : > "$OUT/cfail.txt"
while IFS=$'\t' read -r name expect; do
  [ -n "$name" ] || continue
  src="test_suites/codes/$name"
  [ -f "$src" ] || continue
  a="$OUT/${name}.old"; b="$OUT/${name}.new"
  rm -f "$a" "$b"
  ( ulimit -v 7000000; timeout 120 "$OLD" -O "$src" "$a" >/dev/null 2>&1 )
  ( ulimit -v 7000000; timeout 120 "$NEW" -O "$src" "$b" >/dev/null 2>&1 )
  if [ ! -s "$a" ] || [ ! -s "$b" ]; then echo "$name" >> "$OUT/cfail.txt"; CFAIL=$((CFAIL+1)); continue; fi
  if cmp -s "$a" "$b"; then echo "$name" >> "$OUT/ident.txt"; IDENT=$((IDENT+1))
  else echo "$name" >> "$OUT/diff.txt"; DIFF=$((DIFF+1)); fi
done < "$EXP"
TOT=$((IDENT+DIFF+CFAIL))
echo "rows=$TOT identical=$IDENT differing=$DIFF compile-fail=$CFAIL"
