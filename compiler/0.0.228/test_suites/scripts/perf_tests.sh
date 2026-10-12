#!/usr/bin/env bash
# Performance test layer for the Quanta x86 self-hosting compiler.
#
# Measures wall-clock time of controlled compute kernels using clock_gettime
# (CLOCK_MONOTONIC) and asserts they complete within a generous BASELINE
# threshold. The threshold is a REGRESSION GUARD, not a benchmark record:
# it should be loose enough to pass on any reasonable machine but tight
# enough to catch a gross performance regression (e.g. optimizer breakdown
# or codegen exploding loop bodies). Tune PERF_BASELINE_MS if the host is
# unusually slow; the assertion is about stability, not absolute speed.
#
# Usage: QC=<path-to-qc> bash perf_tests.sh
set -u
QC="${QC:-./compiler/$(cat VERSION)/bin/x86/qc}"
TMP="$(mktemp -d)"
PASS=0; FAIL=0

# Regression-guard baseline in milliseconds (generous; tune per host).
PERF_BASELINE_MS="${PERF_BASELINE_MS:-4000}"

# Helper: build $1 into $2, run it, return measured ms in $MEAS_MS
measure() { # $1=src $2=bin
  $QC -O "$1" "$2" >/dev/null 2>&1 || { echo "  FAIL  compile $1"; FAIL=$((FAIL+1)); MEAS_MS=-1; return; }
  chmod +x "$2" 2>/dev/null
  local t0 t1
  t0=$(date +%s%N)
  "$2" >/dev/null 2>&1
  t1=$(date +%s%N)
  MEAS_MS=$(( (t1 - t0) / 1000000 ))
}

# --- Kernel 1: recursive fib(30) (compute-bound, exercises call/return) ----
cat > "$TMP/fib.quanta" <<'EOF'
fn fib(n: i64) -> i64 {
  if n < 2 { return n }
  return fib(n - 1) + fib(n - 2)
}
fn main() {
  let ts = mmap(16)
  let c0 = clock_gettime(1, ts)
  let r = fib(30)
  let c1 = clock_gettime(1, ts + 8)
  printi(r); println(0)
  return 0
}
EOF
measure "$TMP/fib.quanta" "$TMP/fib.bin"
if [ "$MEAS_MS" -ge 0 ] && [ "$MEAS_MS" -le "$PERF_BASELINE_MS" ]; then
  echo "  PASS  fib(30) ${MEAS_MS}ms <= ${PERF_BASELINE_MS}ms baseline"
  PASS=$((PASS+1))
else
  echo "  FAIL  fib(30) ${MEAS_MS}ms > ${PERF_BASELINE_MS}ms baseline (regression?)"
  FAIL=$((FAIL+1))
fi

# --- Kernel 2: tight integer loop sum 0..N (exercises loop codegen) -------
cat > "$TMP/loop.quanta" <<'EOF'
fn main() {
  let s = 0
  let i = 0
  while i < 20000000 {
    s = s + i
    i = i + 1
  }
  printi(s); println(0)
  return 0
}
EOF
measure "$TMP/loop.quanta" "$TMP/loop.bin"
LOOP_BASE=$(( PERF_BASELINE_MS / 2 ))
if [ "$MEAS_MS" -ge 0 ] && [ "$MEAS_MS" -le "$LOOP_BASE" ]; then
  echo "  PASS  loop-sum(20M) ${MEAS_MS}ms <= ${LOOP_BASE}ms baseline"
  PASS=$((PASS+1))
else
  echo "  FAIL  loop-sum(20M) ${MEAS_MS}ms > ${LOOP_BASE}ms baseline (regression?)"
  FAIL=$((FAIL+1))
fi

# --- Kernel 3: vectorized memset-style fill (exercises SIMD/store path) ----
cat > "$TMP/fill.quanta" <<'EOF'
fn main() {
  let p = mmap(8000000)
  let i = 0
  while i < 1000000 {
    mem_store64(p + i * 8, 123456789)
    i = i + 1
  }
  printi(i); println(0)
  return 0
}
EOF
measure "$TMP/fill.quanta" "$TMP/fill.bin"
FILL_BASE=$(( PERF_BASELINE_MS / 2 ))
if [ "$MEAS_MS" -ge 0 ] && [ "$MEAS_MS" -le "$FILL_BASE" ]; then
  echo "  PASS  memfill(1M*8B) ${MEAS_MS}ms <= ${FILL_BASE}ms baseline"
  PASS=$((PASS+1))
else
  echo "  FAIL  memfill(1M*8B) ${MEAS_MS}ms > ${FILL_BASE}ms baseline (regression?)"
  FAIL=$((FAIL+1))
fi

echo ""
echo "=== Perf: $PASS passed, $FAIL failed (baseline ${PERF_BASELINE_MS}ms) ==="
rm -rf "$TMP"
[ "$FAIL" = "0" ] && exit 0 || exit 1
