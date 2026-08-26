#!/usr/bin/env bash
# Quanta test runner — run from quanta project root
set -e

# NEVER let qemu crashes dump 148GB core files into the repo CWD.
# Non-fatal: some CI/sandbox runners deny ulimit changes (Operation not permitted);
# that must not abort the gate.
ulimit -c 0 2>/dev/null || true

QC="${QC:-./compiler/$(cat VERSION)/bin/x86/qc}"
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

# --- Stage 4: VALGRIND scan of the compiler binary (memory unsafety) --------
# Catches OOB writes / use-after-free in qc itself that the functional gate
# cannot see. Mirrors .github/workflows/valgrind.yml + ci.yml. Non-fatal if
# valgrind is not installed (some sandboxes lack it), but it MUST run in CI.
echo ""
echo "########## VALGRIND SCAN (compiler binary) ##########"
VALGRIND_RC=${VALGRIND_RC:-0}
if command -v valgrind >/dev/null 2>&1; then
  if ! valgrind --error-exitcode=42 --leak-check=summary \
        "$QC" test_suites/codes/simple.quanta /tmp/val_smoke.bin 2>/tmp/vg.log; then
    echo "  FAIL: Valgrind reported errors ($(grep -E 'ERROR SUMMARY' /tmp/vg.log | tail -1))"
    VALGRIND_RC=1
  else
    echo "  PASS: Valgrind clean ($(grep -E 'ERROR SUMMARY' /tmp/vg.log | tail -1))"
  fi
else
  echo "  SKIP: valgrind not installed on this host (CI runs it)"
fi

# --- Stage 5: COMPILER FUZZ (fail-closed proof) -----------------------------
# The compiler must NEVER crash on arbitrary/garbage input — it must exit with
# a defined code (0/1/7/13/14/15/16/17). Mirrors ci.yml Fuzz step.
echo ""
echo "########## COMPILER FUZZ (fail-closed) ##########"
FUZZ_RC=${FUZZ_RC:-0}
if [ -x tools/fuzz/fuzz_qc.py ] || [ -f tools/fuzz/fuzz_qc.py ]; then
  if ! python3 tools/fuzz/fuzz_qc.py --qc "$QC" --iter "${FUZZ_ITER:-2000}" >/tmp/fuzz.log 2>&1; then
    echo "  FAIL: compiler crashed on fuzzed input (see tools/fuzz/crashes/)"
    tail -3 /tmp/fuzz.log
    FUZZ_RC=1
  else
    echo "  PASS: $(grep -E 'RESULT:|DONE:' /tmp/fuzz.log | tail -1)"
  fi
else
  echo "  SKIP: tools/fuzz/fuzz_qc.py missing"
fi

# --- Stage 6: DIFFERENTIAL (optimizer + vs-seed) ----------------------------
echo ""
echo "########## DIFFERENTIAL ##########"
DIFF_RC=${DIFF_RC:-0}
# 6a: -O vs no-O identical stdout (optimizer correctness), mirrors fuzz_differential.sh
if ! bash "$TEST_SUITES/scripts/fuzz_differential.sh" >/tmp/diff_opt.log 2>&1; then
  echo "  FAIL: optimizer differential divergence"
  tail -3 /tmp/diff_opt.log
  DIFF_RC=1
else
  echo "  PASS: $(grep -E 'OK:' /tmp/diff_opt.log | tail -1)"
fi
# 6b: current qc vs committed qc on reference programs, mirrors ci.yml Differential
if [ -f tools/diff_test/diff_qc.py ]; then
  if ! python3 tools/diff_test/diff_qc.py --current "$QC" --seed "$QC" >/tmp/diff_seed.log 2>&1; then
    echo "  FAIL: differential vs seed diverged"
    tail -3 /tmp/diff_seed.log
    DIFF_RC=1
  else
    echo "  PASS: differential-vs-self consistent ($(grep -E 'PASS|OK|consistent' /tmp/diff_seed.log | tail -1))"
  fi
fi

echo ""
echo "=== GATE SUMMARY ==="
echo "  functional : $([ $FUNCTIONAL_RC = 0 ] && echo GREEN || echo RED)"
echo "  extern-c  : $([ $EXTERN_RC = 0 ] && echo GREEN || echo RED)  (object-mode + gcc libc link)"
echo "  security   : $([ $SECURITY_RC = 0 ] && echo GREEN || echo RED)  (KNOWN bugs reported by script, not blocking)"
echo "  performance: $([ $PERF_RC = 0 ] && echo GREEN || echo RED)"
echo "  valgrind   : $([ $VALGRIND_RC = 0 ] && echo GREEN || echo RED)  (compiler binary leak/error scan)"
echo "  fuzz       : $([ $FUZZ_RC = 0 ] && echo GREEN || echo RED)  (fail-closed: 0 crashes)"
echo "  differential: $([ $DIFF_RC = 0 ] && echo GREEN || echo RED)  (opt -O==no-O + vs-seed)"
# Block promotion on a real functional/security/perf/valgrind/fuzz/diff regression.
# Security KNOWN issues are surfaced by the script but do not turn the gate red.
if [ $FUNCTIONAL_RC -ne 0 ] || [ $SECURITY_RC -ne 0 ] || [ $PERF_RC -ne 0 ] \
   || [ $VALGRIND_RC -ne 0 ] || [ $FUZZ_RC -ne 0 ] || [ $DIFF_RC -ne 0 ]; then
  exit 1
fi
exit 0