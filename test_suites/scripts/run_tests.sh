#!/usr/bin/env bash
# Quanta test runner — run from quanta project root
set -e

# NEVER let qemu crashes dump 148GB core files into the repo CWD
ulimit -c 0

QC="${QC:-./bin/qc}"
TEST_SUITES="./test_suites"
PASS=0
FAIL=0
COMPILE_FAIL=0

mkdir -p "$TEST_SUITES/bin"

# Compile all test codes
echo "=== Compiling test suite ==="
while IFS=$'\t' read -r name expected; do
  src="$TEST_SUITES/codes/$name"
  out="$TEST_SUITES/bin/${name%.quanta}"
  if $QC -O "$src" "$out" 2>/dev/null; then
    echo "  OK  $name"
  else
    echo "  FAIL (compile) $name"
    COMPILE_FAIL=$((COMPILE_FAIL + 1))
  fi
done < "$TEST_SUITES/EXPECTED.tsv"

echo ""
echo "=== Running test suite ==="
while IFS=$'\t' read -r name expected; do
  bin="$TEST_SUITES/bin/${name%.quanta}"
  if [ ! -x "$bin" ]; then
    echo "  SKIP $name (no binary)"
    continue
  fi
  set +e
  "$bin" > /dev/null 2>&1
  actual=$?
  set -e
  if [ "$actual" = "$expected" ]; then
    echo "  PASS $name (rc=$actual)"
    PASS=$((PASS + 1))
  else
    echo "  FAIL $name (expected rc=$expected, got rc=$actual)"
    FAIL=$((FAIL + 1))
  fi
done < "$TEST_SUITES/EXPECTED.tsv"

TOTAL=$((PASS + FAIL + COMPILE_FAIL))
echo ""
echo "=== Results: $PASS/$TOTAL pass, $((FAIL + COMPILE_FAIL)) fail (incl. $COMPILE_FAIL compile-fail) ==="
# A compile-fail is a broken feature, not a green row. Exit non-zero if anything
# failed to compile or produced the wrong result, so CI / promotion gates catch it.
if [ $((FAIL + COMPILE_FAIL)) -gt 0 ]; then
  exit 1
fi