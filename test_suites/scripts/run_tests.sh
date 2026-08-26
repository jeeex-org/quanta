#!/usr/bin/env bash
# Quanta test runner — run from quanta project root
set -e

# NEVER let qemu crashes dump 148GB core files into the repo CWD.
# Non-fatal: some CI/sandbox runners deny ulimit changes (Operation not permitted);
# that must not abort the gate.
ulimit -c 0 2>/dev/null || true

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
  if $QC -O "$src" "$out" 2>/tmp/compile_stderr.txt; then
    echo "  OK  $name"
  else
    rc=$?
    echo "  FAIL (compile) $name  rc=$rc"
    echo "    stderr: $(cat /tmp/compile_stderr.txt)"
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
  "$bin" < /dev/null > /dev/null 2>&1
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
  FUNCTIONAL_RC=1
else
  FUNCTIONAL_RC=0
fi

# --- Stage 1.5: EXTERN "C" FFI (object mode + gcc link) ----------------------
# The main loop above compiles in EXEC mode only ($QC -O), where extern "C"
# cannot resolve libc. This stage actually links a real libc FFI test so the
# string-header skip, 16B stack alignment, and libc-exit stdout flush paths are
# exercised by the gate (not just by ad-hoc manual checks).
echo ""
echo "########## EXTERN \"C\" FFI LAYER (object mode + gcc) ##########"
EXTERN_FAIL=0
while IFS=$'\t' read -r name sentinel; do
  src="$TEST_SUITES/codes/$name"
  [ -f "$src" ] || continue
  obj="$TEST_SUITES/bin/${name%.quanta}.o"
  bin="$TEST_SUITES/bin/${name%.quanta}_ext"
  if ! $QC --emit-obj "$src" "$obj" 2>/tmp/extern_stderr.txt; then
    echo "  FAIL (compile) $name  $(cat /tmp/extern_stderr.txt)"
    EXTERN_FAIL=$((EXTERN_FAIL + 1)); continue
  fi
  if ! gcc -nostartfiles "$obj" -o "$bin" 2>/tmp/extern_ld.txt; then
    echo "  FAIL (link) $name  $(cat /tmp/extern_ld.txt)"
    EXTERN_FAIL=$((EXTERN_FAIL + 1)); continue
  fi
  got=$("$bin" 2>&1)
  if echo "$got" | grep -q "$sentinel"; then
    echo "  PASS extern $name (sentinel '$sentinel' found)"
  else
    echo "  FAIL extern $name (expected sentinel '$sentinel', got: '$got')"
    EXTERN_FAIL=$((EXTERN_FAIL + 1))
  fi
done < "$TEST_SUITES/EXTERN_EXPECTED.tsv"
EXTERN_RC=${EXTERN_RC:-0}
[ "$EXTERN_FAIL" -eq 0 ] && EXTERN_RC=0 || EXTERN_RC=1
if [ $EXTERN_RC -ne 0 ]; then FUNCTIONAL_RC=1; fi

# --- Stage 2: SECURITY layer (overflow traps, OOB, malformed/garbage input) ---
echo ""
echo "########## SECURITY TEST LAYER ##########"
QC="$QC" bash "$TEST_SUITES/scripts/security_tests.sh" || SECURITY_RC=1
SECURITY_RC=${SECURITY_RC:-0}

# --- Stage 3: PERFORMANCE layer (timed kernels vs regression baseline) ------
echo ""
echo "########## PERFORMANCE TEST LAYER ##########"
QC="$QC" bash "$TEST_SUITES/scripts/perf_tests.sh" || PERF_RC=1
PERF_RC=${PERF_RC:-0}

echo ""
echo "=== GATE SUMMARY ==="
echo "  functional : $([ $FUNCTIONAL_RC = 0 ] && echo GREEN || echo RED)"
echo "  extern-c  : $([ $EXTERN_RC = 0 ] && echo GREEN || echo RED)  (object-mode + gcc libc link)"
echo "  security   : $([ $SECURITY_RC = 0 ] && echo GREEN || echo RED)  (KNOWN bugs reported by script, not blocking)"
echo "  performance: $([ $PERF_RC = 0 ] && echo GREEN || echo RED)"
# Block promotion on a real functional/security/perf regression. Security
# KNOWN issues are surfaced by the script but do not turn the gate red.
if [ $FUNCTIONAL_RC -ne 0 ] || [ $SECURITY_RC -ne 0 ] || [ $PERF_RC -ne 0 ]; then
  exit 1
fi
exit 0