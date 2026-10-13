#!/usr/bin/env bash
# Quanta MULTI-TU gate layer — 0.0.116 (FIX-0.0.36 wiring).
# Compiles the mtu_* fixtures as separate translation units (--emit-obj,
# --no-start for the callee TU), links them with gcc -nostartfiles, and
# checks the exit code. Run from the quanta project root.
set -e
QC="${QC:-./compiler/$(cat VERSION)/bin/x86/qc}"
TEST_SUITES="./test_suites"
BIN="$TEST_SUITES/bin"
mkdir -p "$BIN"

MTU_PASS=0
MTU_FAIL=0

# link_and_run <expected_rc> <label> <obj...>
link_and_run() {
  local expected="$1"; shift
  local label="$1"; shift
  local out="$BIN/mtu_${label}"
  if ! gcc -nostartfiles "$@" -o "$out" 2>/tmp/mtu_ld.txt; then
    echo "  FAIL (link) $label  $(cat /tmp/mtu_ld.txt | head -2)"
    MTU_FAIL=$((MTU_FAIL + 1)); return
  fi
  set +e
  "$out" >/dev/null 2>&1
  local actual=$?
  set -e
  if [ "$actual" = "$expected" ]; then
    echo "  PASS mtu $label (rc=$actual)"
    MTU_PASS=$((MTU_PASS + 1))
  else
    echo "  FAIL mtu $label (expected rc=$expected, got rc=$actual)"
    MTU_FAIL=$((MTU_FAIL + 1))
  fi
}

# --- Pair 1: cross-TU function call (mtu_main calls square() in mtu_helper) ---
if $QC --emit-obj --no-start "$TEST_SUITES/codes/mtu_helper.quanta" "$BIN/mtu_helper.o" 2>/tmp/mtu_c.txt \
   && $QC --emit-obj "$TEST_SUITES/codes/mtu_main.quanta" "$BIN/mtu_main.o" 2>>/tmp/mtu_c.txt; then
  link_and_run 49 "call" "$BIN/mtu_main.o" "$BIN/mtu_helper.o"
else
  echo "  FAIL (compile) mtu call pair  $(cat /tmp/mtu_c.txt | head -2)"
  MTU_FAIL=$((MTU_FAIL + 1))
fi

# --- Pair 2: cross-TU DATA global (def TU owns SHARED, use TU writes it) ---
if $QC --emit-obj --no-start "$TEST_SUITES/codes/mtu_glob_use.quanta" "$BIN/mtu_glob_use.o" 2>/tmp/mtu_c.txt \
   && $QC --emit-obj "$TEST_SUITES/codes/mtu_glob_def.quanta" "$BIN/mtu_glob_def.o" 2>>/tmp/mtu_c.txt; then
  link_and_run 25 "global" "$BIN/mtu_glob_def.o" "$BIN/mtu_glob_use.o"
else
  echo "  FAIL (compile) mtu global pair  $(cat /tmp/mtu_c.txt | head -2)"
  MTU_FAIL=$((MTU_FAIL + 1))
fi

# --- Single-TU named global (mtu_glob_hw, real-hardware codegen shape) ---
if $QC "$TEST_SUITES/codes/mtu_glob_hw.quanta" "$BIN/mtu_glob_hw" 2>/tmp/mtu_c.txt; then
  set +e
  ./scripts/quanta_run.sh "$BIN/mtu_glob_hw" >/dev/null 2>&1
  actual=$?
  set -e
  if [ "$actual" = "25" ]; then
    echo "  PASS mtu glob_hw single-TU (rc=$actual)"
    MTU_PASS=$((MTU_PASS + 1))
  else
    echo "  FAIL mtu glob_hw single-TU (expected rc=25, got rc=$actual)"
    MTU_FAIL=$((MTU_FAIL + 1))
  fi
else
  echo "  FAIL (compile) mtu_glob_hw  $(cat /tmp/mtu_c.txt | head -2)"
  MTU_FAIL=$((MTU_FAIL + 1))
fi

echo "  MULTI-TU: $MTU_PASS/$((MTU_PASS + MTU_FAIL)) GREEN"
[ "$MTU_FAIL" -eq 0 ]
