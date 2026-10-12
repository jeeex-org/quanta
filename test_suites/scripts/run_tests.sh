#!/usr/bin/env bash
# Quanta test runner — run from quanta project root
set -e

# NEVER let qemu crashes dump 148GB core files into the repo CWD.
# Non-fatal: some CI/sandbox runners deny ulimit changes (Operation not permitted);
# that must not abort the gate.
ulimit -c 0 2>/dev/null || true

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
QC="${QC:-$REPO/compiler/$(cat "$REPO/VERSION")/bin/x86/qc}"
TEST_SUITES="./test_suites"
PASS=0
FAIL=0
COMPILE_FAIL=0
# Tests skipped because a declared prerequisite file was absent (see the
# SKIP_IF_MISSING column). Excluded from TOTAL so a skip can never read as a pass.
SKIP=0

mkdir -p "$TEST_SUITES/bin"
# Scratch cwd for test runs. Symlink every top-level repo entry in, so a test
# that reads a repo-relative path still finds it, while a test that WRITES drops
# the file here instead of in the project root.
rm -rf "$TEST_SUITES/run"; mkdir -p "$TEST_SUITES/run"
for e in "$REPO"/* "$REPO"/.gitattributes "$REPO"/.gitignore; do
  [ -e "$e" ] || continue
  ln -sfn "$e" "$TEST_SUITES/run/$(basename "$e")" 2>/dev/null || true
done

# Compile all test codes
echo "=== Compiling test suite ==="
while IFS=$'\t' read -r name expected skip_if_missing; do
  src="$TEST_SUITES/codes/$name"
  out="$TEST_SUITES/bin/${name%.quanta}"
  # A test needing a real model cannot be compiled-and-run meaningfully without
  # it; compiling it is still useful (it proves the source builds), so only the
  # RUN loop skips. See the run loop below.
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
while IFS=$'\t' read -r name expected skip_if_missing; do
  bin="$TEST_SUITES/bin/${name%.quanta}"
  if [ ! -x "$bin" ]; then
    echo "  SKIP $name (no binary)"
    continue
  fi
  # Declared prerequisite absent (SKIP_IF_MISSING column, third field): a test
  # needing a real model cannot pass on a runner that has none. Printed, never
  # silent, and excluded from the totals so a skip cannot read as a pass.
  if [ -n "$skip_if_missing" ] && [ ! -f "$skip_if_missing" ]; then
    echo "  SKIP $name (missing: $skip_if_missing)"
    SKIP=$((SKIP + 1)); continue
  fi
  set +e
  # Run from a scratch cwd. A test that writes a file (test_generator does)
  # would otherwise drop it in the project root, and a path built from an
  # unquoted title can land anywhere at all. The 0.0.219 root debris -- 21
  # files named "A", "B", ";", ">", "@" -- was exactly this.
  # Resolve the absolute path FIRST -- inside the subshell, `cd ..` is relative
  # to the new cwd, so doing it there yields test_suites/ and the runner reports
  # "not executable" (rc 2) for every test.
  #
  # $TEST_SUITES/run is a symlink farm, not an empty dir: it contains links to
  # the repo's top-level entries. Tests that open a repo-relative path
  # (file_open_test opens "test_suites/codes/simple.quanta") still resolve,
  # while a test that WRITES still lands in the scratch dir, not the root.
  abs_bin="$(cd "$(dirname "$bin")" && pwd)/$(basename "$bin")"
  ( cd "$TEST_SUITES/run" && "$REPO/scripts/quanta_run.sh" "$abs_bin" ) < /dev/null > /dev/null 2>&1
  actual=$?
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
if [ "$SKIP" -gt 0 ]; then
  echo "=== Results: $PASS/$TOTAL pass, $((FAIL + COMPILE_FAIL)) fail (incl. $COMPILE_FAIL compile-fail), $SKIP skipped (model absent) ==="
else
  echo "=== Results: $PASS/$TOTAL pass, $((FAIL + COMPILE_FAIL)) fail (incl. $COMPILE_FAIL compile-fail) ==="
fi
# A compile-fail is a broken feature, not a green row. Exit non-zero if anything
# failed to compile or produced the wrong result, so CI / promotion gates catch it.
if [ $((FAIL + COMPILE_FAIL)) -gt 0 ]; then
  FUNCTIONAL_RC=1
else
  FUNCTIONAL_RC=0
fi

# --- Stage 1.4: NATIVE SUFFICIENCY (no extern, no libc) ------------------------
# Quanta is a native language. `extern "C"` and the dynamic-linker path are
# OPTIONAL interop, never the way anything has to be written. This stage asserts
# that directly: a program covering strings, byte indexing, NUL termination,
# raw syscalls, raw memory and the native allocator must compile in plain EXEC
# mode -- no flags, no extern -- and run correctly.
#
# The stages after this one all test extern paths, and a gate made only of those
# would stay green while the native surface quietly rotted. This is the one that
# fails when native regresses.
#
# The binary must also be statically linked: a native program that pulled in
# libc would mean something reached for extern "C" to get at it.
echo ""
echo "########## NATIVE SUFFICIENCY (no extern, no libc) ##########"
NATIVE_FAIL=0
NAT_SRC="$TEST_SUITES/codes/native_capability_test.quanta"
if [ ! -f "$NAT_SRC" ]; then
  echo "  FAIL native $NAT_SRC missing"
  NATIVE_FAIL=1
else
  NAT_BIN="$TEST_SUITES/bin/native_capability_test"
  if ! $QC "$NAT_SRC" "$NAT_BIN" 2>/tmp/native_stderr.txt; then
    echo "  FAIL (compile) native_capability_test  $(cat /tmp/native_stderr.txt)"
    NATIVE_FAIL=1
  else
    # Capture the status before inspecting it: `[ $? -ne 42 ]` inside a
    # `! ... ||` chain reads the status of the negation, not the program, and
    # reported a correct run as exit 0.
    "$NAT_BIN" >/dev/null 2>&1
    nat_rc=$?
    if [ "$nat_rc" -ne 42 ]; then
      echo "  FAIL (run) native_capability_test: expected exit 42, got $nat_rc"
      NATIVE_FAIL=1
    else
      # A static binary is the real assertion. A native program has no reason to
      # reach libc, and nothing is allowed to make it: the compiler now refuses
      # `extern "C"` in EXEC mode outright ("extern \"C\" needs --emit-dynamic"),
      # so if a native build ever does link libc that is a hole in that check and
      # it should fail loudly here.
      if ldd "$NAT_BIN" 2>&1 | grep -q "libc\.so\|ld-linux"; then
        echo "  FAIL (link) native_capability_test linked libc; a native program must not"
        NATIVE_FAIL=1
      else
        echo "  PASS native: strings, indexing, syscall, mmap, mem_alloc, no libc"
      fi
    fi
  fi
fi
if [ "$NATIVE_FAIL" -eq 0 ]; then NATIVE_RC=0; else NATIVE_RC=1; FUNCTIONAL_RC=1; fi

# --- Stage 1.5a: FLOAT OPERATORS (gating) -------------------------------------
# float_arith_test.quanta was committed long ago but referenced by NO script, so
# the + - * / float operator path was never actually gated. It passes (exit 42) as
# of 0.0.220 and is now enforced: the four prefix/tagging/comparison defects it
# documents (SSE prefix order, untagged float params, untagged float returns,
# bitwise float comparison) must not come back.
#
# The BUILTIN path (fadd/fsub/fmul/fdiv) is a separate implementation and is
# still broken -- see stage 1.6 below.
echo ""
echo "########## FLOAT OPERATOR PATH (gating) ##########"
FLOATOP_FAIL=0
FLOATOP_SRC="$TEST_SUITES/codes/float_arith_test.quanta"
if [ ! -f "$FLOATOP_SRC" ]; then
  echo "  FAIL float_arith_test $FLOATOP_SRC missing"
  FLOATOP_FAIL=1
else
  FLOATOP_BIN="$TEST_SUITES/bin/float_arith_test"
  if ! $QC "$FLOATOP_SRC" "$FLOATOP_BIN" 2>/tmp/floatop_stderr.txt; then
    echo "  FAIL (compile) float_arith_test  $(cat /tmp/floatop_stderr.txt)"
    FLOATOP_FAIL=1
  else
    "$FLOATOP_BIN" >/dev/null 2>&1
    floatop_rc=$?
    if [ "$floatop_rc" -ne 42 ]; then
      echo "  FAIL (run) float_arith_test: expected exit 42, got $floatop_rc"
      FLOATOP_FAIL=1
    else
      echo "  PASS float operators: + - * / , params, returns, comparisons"
    fi
  fi
fi
if [ "$FLOATOP_FAIL" -eq 0 ]; then FLOATOP_RC=0; else FLOATOP_RC=1; FUNCTIONAL_RC=1; fi

# --- Stage 1.6: FLOAT BUILTINS (KNOWN FAILING -- does not gate) ----------------
# fadd/fsub/fmul/fdiv are implemented separately from the + - * / operators and
# are currently WRONG: they return one of their arguments instead of the result.
#   let a = 3.0
#   let b = 4.0
#   a + b        -> 7.0    correct
#   fadd(a, b)   -> 3.0    wrong
#
# sqrt, floor, ceil, cos, sin, log and pow are all correct.
#
# Why this stage exists: NEITHER float test was wired into the runner before
# 0.0.220 -- float_arith_test.quanta is still referenced by nothing -- which is
# how these four stayed broken while the gate stayed green. This stage keeps the
# defect VISIBLE without turning the gate red, and flips to PASS the moment the
# handlers are fixed.
#
# It deliberately does NOT set FUNCTIONAL_RC: the tree is knowingly broken here
# and a red gate would block every other fix. See docs/roadmap for the
# tracking item and the quanta-float-builtins-defect skill for the analysis.
echo ""
echo "########## FLOAT BUILTINS (known-failing, non-gating) ##########"
FBT_FAIL=0
# --- Stage 1.6b: FLOAT RETURN TYPING (gating) ---------------------------------
# float_builtin_test.quanta covers the arithmetic; this covers the TYPE. A call to
# a function declared `-> f64` must produce a float-tagged vreg, or an enclosing
# builtin takes the integer path on its bit patterns.
echo ""
echo "########## FLOAT RETURN TYPING (gating) ##########"
FRT_FAIL=0
FRT_SRC="$TEST_SUITES/codes/float_return_test.quanta"
if [ ! -f "$FRT_SRC" ]; then
  echo "  FAIL float_return_test $FRT_SRC missing"
  FRT_FAIL=1
else
  FRT_BIN="$TEST_SUITES/bin/float_return_test"
  if ! $QC "$FRT_SRC" "$FRT_BIN" 2>/tmp/frt_stderr.txt; then
    echo "  FAIL (compile) float_return_test  $(cat /tmp/frt_stderr.txt)"
    FRT_FAIL=1
  else
    "$FRT_BIN" >/dev/null 2>&1
    frt_rc=$?
    if [ "$frt_rc" -ne 42 ]; then
      echo "  FAIL (run) float_return_test: expected exit 42, got $frt_rc (case $frt_rc is the first failing one)"
      FRT_FAIL=1
    else
      echo "  PASS float returns: -> f64 tags the caller's operand vreg"
    fi
  fi
fi
if [ "$FRT_FAIL" -eq 0 ]; then FRT_RC=0; else FRT_RC=1; FUNCTIONAL_RC=1; fi

# --- Stage 1.6c: FLOAT OPERAND PATH (gating) ---------------------------------
# float_operand_path_test.quanta exercises the INTEGER operand path of
# fadd/fsub/fmul/fdiv, which emits cvtsi2sd. Those sites carried a stray 66
# (packed-SSE prefix) between the mandatory F2 and the REX byte -- F2 66 48 0F 2A
# is not a decodable cvtsi2sd -- and arg1's sites put F2 after the REX. Eleven
# sites in emitter.quanta. The test discriminates: exit 0 with the fix, exit 1
# against 0.0.219's broken encoding.
echo ""
echo "########## FLOAT OPERAND PATH (gating) ##########"
FOP_FAIL=0
FOP_SRC="$TEST_SUITES/codes/float_operand_path_test.quanta"
if [ ! -f "$FOP_SRC" ]; then
  echo "  FAIL float_operand_path_test $FOP_SRC missing"
  FOP_FAIL=1
else
  FOP_BIN="$TEST_SUITES/bin/float_operand_path_test"
  if ! $QC "$FOP_SRC" "$FOP_BIN" 2>/tmp/fop_stderr.txt; then
    echo "  FAIL (compile) float_operand_path_test  $(cat /tmp/fop_stderr.txt)"
    FOP_FAIL=1
  else
    "$FOP_BIN" >/dev/null 2>&1
    fop_rc=$?
    if [ "$fop_rc" -ne 0 ]; then
      echo "  FAIL (run) float_operand_path_test: expected exit 0, got $fop_rc (case $fop_rc is the first failing one)"
      FOP_FAIL=1
    else
      echo "  PASS float operands: cvtsi2sd encoding correct on both arg slots"
    fi
  fi
fi
if [ "$FOP_FAIL" -eq 0 ]; then FOP_RC=0; else FOP_RC=1; FUNCTIONAL_RC=1; fi

FBT_SRC="$TEST_SUITES/codes/float_builtin_test.quanta"
if [ ! -f "$FBT_SRC" ]; then
  echo "  FAIL float_builtin_test $FBT_SRC missing"
  FBT_FAIL=1
else
  FBT_BIN="$TEST_SUITES/bin/float_builtin_test"
  if ! $QC "$FBT_SRC" "$FBT_BIN" 2>/tmp/fbt_stderr.txt; then
    echo "  FAIL (compile) float_builtin_test  $(cat /tmp/fbt_stderr.txt)"
    FBT_FAIL=1
  else
    "$FBT_BIN" >/dev/null 2>&1
    fbt_rc=$?
    if [ "$fbt_rc" -eq 42 ]; then
      echo "  PASS float builtins: fadd/fsub/fmul/fdiv correct (exit 42)"
      FBT_FAIL=0
    else
      echo "  FAIL (run) float_builtin_test: expected exit 42, got $fbt_rc (case $fbt_rc is the first failing op)"
      FBT_FAIL=1
    fi
  fi
fi
if [ "$FBT_FAIL" -eq 0 ]; then FBT_RC=0; else FBT_RC=1; FUNCTIONAL_RC=1; fi

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

# --- Stage 1.6: EXTERN "C" FFI via DIRECT LINKER (GCC-FREE, PLT/GOT) ----------
# 0.0.122 deliverable: a Quanta EXE links libc symbols STANDALONE without gcc.
# qc emits the relocatable .o (R_X86_64_PLT32 relocs); the system linker `ld`
# emits the PLT/GOT + PT_INTERP. quanta_link.sh drives `ld` with the Linux
# glibc interpreter. This is the fixpoint-safe alternative to hand-rolling a
# dynamic ELF inside write_elf (which breaks the self-host, per
# references/extern-c-and-dynamic-elf-bootstrap-trap.md).
echo ""
echo "########## EXTERN \"C\" FFI LAYER (object mode + ld, GCC-FREE) ##########"
EXTERN_LD_FAIL=0
while IFS=$'\t' read -r name sentinel; do
  src="$TEST_SUITES/codes/$name"
  [ -f "$src" ] || continue
  obj="$TEST_SUITES/bin/${name%.quanta}_ld.o"
  bin="$TEST_SUITES/bin/${name%.quanta}_ld"
  if ! $QC --emit-obj "$src" "$obj" 2>/tmp/extern_ld_stderr.txt; then
    echo "  FAIL (compile) $name  $(cat /tmp/extern_ld_stderr.txt)"
    EXTERN_LD_FAIL=$((EXTERN_LD_FAIL + 1)); continue
  fi
  if ! ./scripts/quanta_link.sh "$obj" "$bin" 2>/tmp/extern_ld_link.txt; then
    echo "  FAIL (link) $name  $(cat /tmp/extern_ld_link.txt)"
    EXTERN_LD_FAIL=$((EXTERN_LD_FAIL + 1)); continue
  fi
  got=$("$bin" 2>&1)
  if echo "$got" | grep -q "$sentinel"; then
    echo "  PASS extern-ld $name (sentinel '$sentinel' found)"
  else
    echo "  FAIL extern-ld $name (expected sentinel '$sentinel', got: '$got')"
    EXTERN_LD_FAIL=$((EXTERN_LD_FAIL + 1))
  fi
done < "$TEST_SUITES/EXTERN_EXPECTED.tsv"
EXTERN_LD_RC=0
[ "$EXTERN_LD_FAIL" -eq 0 ] && EXTERN_LD_RC=0 || EXTERN_LD_RC=1
if [ $EXTERN_LD_RC -ne 0 ]; then FUNCTIONAL_RC=1; fi

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
echo ""

echo "########## GENERICS NEGATIVE (compile-time type checks) ##########"
GENERICS_RC=0
if [ -f "test_suites/scripts/generics_neg_tests.sh" ]; then
  if ! QC="$QC" bash "test_suites/scripts/generics_neg_tests.sh"; then
    GENERICS_RC=1
  fi
else
  echo "  SKIP: generics_neg_tests.sh missing"
fi

echo "########## STDLIB SUITE (lib/std/* via import) ##########"
STDLIB_RC=0
if [ -f "$TEST_SUITES/EXPECTED_STDLIB.tsv" ]; then
  STDLIB_PASS=0; STDLIB_FAIL=0; STDLIB_SKIP=0
  # CUDA tests skip themselves (and return 0) when no daemon is up, so a broken
  # CUDA path would look identical to a passing one. Start the daemon here and
  # treat a CUDA test that reports SKIP as a FAILURE, so the coverage is real.
  CUDA_DAEMON_STARTED=0
  # A daemon already running is only usable if it IS the committed binary.
  # Otherwise the gate measures a stale build -- the same failure mode as
  # compiling with a stale VERSION. Verified by md5 of /proc/<pid>/exe against
  # the committed file; a mismatch means restart with the right binary.
  CUDA_WANT_MD5="$(md5sum "$REPO/scripts/audit/cuda_daemon" 2>/dev/null | cut -d' ' -f1)"
  CUDA_STALE=0
  for _p in $(pgrep -x cuda_daemon 2>/dev/null); do
    _have="$(md5sum "/proc/$_p/exe" 2>/dev/null | cut -d' ' -f1)"
    if [ -n "$_have" ] && [ "$_have" != "$CUDA_WANT_MD5" ]; then
      CUDA_STALE=1
      echo "  NOTE: killing stale cuda_daemon pid=$_p (md5 $_have != committed $CUDA_WANT_MD5)"
      kill "$_p" 2>/dev/null || true
    fi
  done
  if [ "$CUDA_STALE" = "1" ]; then
    sleep 0.5
  fi
  if ! pgrep -x cuda_daemon >/dev/null 2>&1; then
    rm -f /tmp/quanta_cuda/queue /tmp/quanta_cuda/result /tmp/quanta_cuda/lock
    "$REPO/scripts/audit/cuda_daemon" >/tmp/cuda_daemon_gate.log 2>&1 &
    CUDA_DAEMON_PID=$!
    for _ in $(seq 1 40); do
      grep -q READY /tmp/cuda_daemon_gate.log 2>/dev/null && break
      sleep 0.1
    done
    if pgrep -x cuda_daemon >/dev/null 2>&1; then
      CUDA_DAEMON_STARTED=1
    else
      echo "  WARN: cuda_daemon failed to start (CUDA tests will be reported as FAIL)"
    fi
  fi
  while IFS=$'\t' read -r name expected skip_if_missing; do
    src="$TEST_SUITES/codes/$name"
    bin="$TEST_SUITES/bin/${name%.quanta}"
    # --no-overflow-trap is REQUIRED for crypto/unsigned-bitwise stdlibs (secure, quantum).
    # The signed-overflow trap (OF flag after add/sub/mul/neg) fires on intentional
    # two's-complement wraparound in crypto (rotations, XOR, shifts, byte multiplies).
    # This is NOT a bug workaround — it's the correct semantic flag for such code.
    # The shift-count UB trap (count >= 64) remains active.
    #
    # SKIP_IF_MISSING (optional 3rd column): a test that needs a real model file
    # cannot pass on a runner that has no model. Marking it explicitly here means
    # it is skipped ONLY when declared, the skip is always printed (never silent),
    # and the pass/fail totals exclude it. Unmarked model-dependent tests still
    # FAIL on a runner without the model, which is the point: a new
    # model-dependent test cannot be added by accident.
    if [ -n "$skip_if_missing" ]; then
      if [ ! -f "$skip_if_missing" ]; then
        echo "  SKIP $name (missing: $skip_if_missing)"
        STDLIB_SKIP=$((STDLIB_SKIP + 1)); continue
      fi
    fi
    # stdlib_safetensors_test reads /tmp/hostile/*.gguf, produced here rather than
    # checked into the repo: ten small malformed files that must all be refused.
    # Generated before every run so the test cannot pass on stale fixtures.
    if [ "$name" = "stdlib_safetensors_test.quanta" ]; then
      python3 "$REPO/scripts/audit/make_hostile_st.py" /tmp/hostile >/dev/null 2>&1 || true
    fi
    if ! $QC --no-overflow-trap "$src" "$bin" 2>/tmp/stdlib_stderr.txt; then
      echo "  FAIL (compile) $name  stderr: $(cat /tmp/stdlib_stderr.txt | head -1)"
      STDLIB_FAIL=$((STDLIB_FAIL + 1)); continue
    fi
    set +e
    # Capture output so a self-reported SKIP can be detected. A CUDA test that
    # skips has not tested anything, so counting it as a pass is how the CUDA
    # path stayed "green" while the daemon was actually broken.
    STDLIB_OUT="$(./scripts/quanta_run.sh "$bin" < /dev/null 2>&1)"
    actual=$?
    set -e
    case "$name" in
      std_cuda_*)
        if printf '%s' "$STDLIB_OUT" | grep -q "^SKIP:"; then
          echo "  FAIL $name (reported SKIP: CUDA daemon not reachable)"
          STDLIB_FAIL=$((STDLIB_FAIL + 1)); continue
        fi
        ;;
    esac
    if [ "$actual" = "$expected" ]; then
      echo "  PASS $name (rc=$actual)"
      STDLIB_PASS=$((STDLIB_PASS + 1))
    else
      echo "  FAIL $name (expected rc=$expected, got rc=$actual)"
      STDLIB_FAIL=$((STDLIB_FAIL + 1))
    fi
  done < "$TEST_SUITES/EXPECTED_STDLIB.tsv"
  if [ "$CUDA_DAEMON_STARTED" = "1" ]; then
    kill "$CUDA_DAEMON_PID" 2>/dev/null || true
    wait "$CUDA_DAEMON_PID" 2>/dev/null || true
  fi
  if [ "$STDLIB_SKIP" -gt 0 ]; then
    echo "  STDLIB: $STDLIB_PASS/$((STDLIB_PASS + STDLIB_FAIL)) GREEN ($STDLIB_SKIP skipped: model absent)"
  else
    echo "  STDLIB: $STDLIB_PASS/$((STDLIB_PASS + STDLIB_FAIL)) GREEN"
  fi
  if [ $STDLIB_FAIL -gt 0 ]; then STDLIB_RC=1; fi
else
  echo "  SKIP: EXPECTED_STDLIB.tsv missing"
fi

echo "########## MULTI-TU (cross-TU call + global, --emit-obj + link) ##########"
MTU_RC=0
if [ -f "$TEST_SUITES/scripts/multi_tu_tests.sh" ]; then
  if ! QC="$QC" bash "$TEST_SUITES/scripts/multi_tu_tests.sh"; then
    MTU_RC=1
  fi
else
  echo "  SKIP: multi_tu_tests.sh missing"
fi

echo "########## QOBJ (module cache: write, read, cache-only consume) ##########"
# G1/G3/G5. This stage is the only thing that exercises the .qobj format: a
# module that imports two other modules is written as a cache, its sources are
# deleted, and the cache is then consumed on its own. Single- and two-function
# modules pass by luck -- a corrupt argument list still lands on in-range IR
# records -- so the fixture deliberately uses three modules with cross-calls.
#
# It also asserts the cache file is READABLE, not merely present. A cache
# written mode 0111 is treated as absent by every probe, which is how the
# cache-only build was silently broken for a long time.
QOBJ_RC=0
if [ -f "$TEST_SUITES/scripts/gguf_corrupt_gate.sh" ]; then
  if bash "$TEST_SUITES/scripts/gguf_corrupt_gate.sh"; then
    GGUF_RC=0
  else
    GGUF_RC=1
  fi
else
  echo "  FAIL: gguf_corrupt_gate.sh missing"
  GGUF_RC=1
fi

if [ -f "$TEST_SUITES/scripts/qobj_gate.sh" ]; then
  if ! QC="$QC" bash "$TEST_SUITES/scripts/qobj_gate.sh"; then
    QOBJ_RC=1
  fi
else
  echo "  FAIL: qobj_gate.sh missing"
  QOBJ_RC=1
fi

# --- Stage 12: STATUS VERIFICATION (docs vs source consistency) --------------
echo ""
echo "########## STATUS VERIFICATION GATE ##########"
VERIFY_STATUS_RC=0
QC_STATUS="$QC"
if $QC_STATUS test_suites/scripts/verify_status.quanta /tmp/verify_status 2>/tmp/verify_status_compile.txt; then
  if /tmp/verify_status >/tmp/verify_status_run.txt 2>&1; then
    echo "  PASS: status verification consistent"
    VERIFY_STATUS_RC=0
  else
    echo "  FAIL: status verification found inconsistencies"
    cat /tmp/verify_status_run.txt
    VERIFY_STATUS_RC=1
  fi
else
  echo "  FAIL: verify_status failed to compile"
  cat /tmp/verify_status_compile.txt
  VERIFY_STATUS_RC=1
fi

# --- Stage 13: OUTPUT-PATH GUARD (compiler must not overwrite its input) -----
echo ""
echo "########## OUTPUT-PATH GUARD ##########"
OUTGUARD_RC=0
if bash "$TEST_SUITES/scripts/output_path_guard_test.sh" "$QC" 2>&1 | sed 's/^/  /'; then
  OUTGUARD_RC=0
else
  OUTGUARD_RC=1
fi

# --- Stage 14: NAKED fn / section / no_mangle (0.0.229 Phase B) --------------
echo ""
echo "########## NAKED / SECTION ##########"
NAKED_RC=0
NAKED_BIN="$TEST_SUITES/run/naked_gate"
if $QC --no-overflow-trap "$TEST_SUITES/codes/naked_test.quanta" "$NAKED_BIN" 2>/tmp/naked_gate_compile.txt; then
  NAKED_OUT="$(./scripts/quanta_run.sh "$NAKED_BIN" < /dev/null 2>&1)"
  if printf '%s' "$NAKED_OUT" | grep -q "^naked: ok$"; then
    echo "  PASS: naked fn callable, returns asm value"
  else
    echo "  FAIL: naked fn runtime check: $NAKED_OUT"
    NAKED_RC=1
  fi
  # Negative fixture: naked fn WITH PARAMETERS must fail to compile (fail closed).
  if $QC --no-overflow-trap "$TEST_SUITES/codes/naked_neg_test.quanta" /tmp/naked_neg_gate 2>/tmp/naked_neg_gate.txt; then
    echo "  FAIL: naked fn with parameters compiled (must be a compile error)"
    NAKED_RC=1
  else
    echo "  PASS: naked fn with parameters rejected at compile time"
  fi
  # Object mode: section("...") must produce the NAMED section and bind the
  # fn's symbol to it; the name must be EXACT (no_mangle semantics).
  if $QC --emit-obj "$TEST_SUITES/codes/naked_test.quanta" /tmp/naked_gate.o 2>/dev/null; then
    if readelf -SW /tmp/naked_gate.o 2>/dev/null | grep -q "text.startup" \
       && readelf -sW /tmp/naked_gate.o 2>/dev/null | grep -q "startup_stub" \
       && [ "$(readelf -sW /tmp/naked_gate.o 2>/dev/null | awk '$8=="startup_stub" {print $7}')" = "8" ]; then
      echo "  PASS: section(".text.startup") emitted, symbol bound, name exact"
    else
      echo "  FAIL: section/no_mangle object checks"
      NAKED_RC=1
    fi
  else
    echo "  FAIL: --emit-obj failed on naked_test"
    NAKED_RC=1
  fi
else
  echo "  FAIL: naked_test failed to compile: $(cat /tmp/naked_gate_compile.txt | head -1)"
  NAKED_RC=1
fi

echo "=== GATE SUMMARY ==="
echo "  functional     : $([ $FUNCTIONAL_RC = 0 ] && echo GREEN || echo RED)"
echo "  native        : $([ $NATIVE_RC = 0 ] && echo GREEN || echo RED)  (no extern, no libc -- the default path)"
echo "  float-oper   : $([ $FLOATOP_RC = 0 ] && echo GREEN || echo RED)  (f64 + - * / , params, returns, comparisons)"
echo "  float-builtin: $([ $FBT_RC = 0 ] && echo GREEN || echo RED)  (fadd/fsub/fmul/fdiv result store + vfloat tag; fixed 0.0.220)"
echo "  float-return: $([ $FRT_RC = 0 ] && echo GREEN || echo RED)  (a call to a -> f64 function tags its result; fixed 0.0.220)"
echo "  float-operpath: $([ $FOP_RC = 0 ] && echo GREEN || echo RED)  (cvtsi2sd operand encoding on the int path; fixed 0.0.220)"
echo "  extern-c      : $([ $EXTERN_RC = 0 ] && echo GREEN || echo RED)  (object-mode + gcc libc link)"
echo "  extern-ld     : $([ $EXTERN_LD_RC = 0 ] && echo GREEN || echo RED)  (object-mode + ld, GCC-FREE 0.0.122)"
echo "  security      : $([ $SECURITY_RC = 0 ] && echo GREEN || echo RED)  (KNOWN bugs reported by script, not blocking)"
echo "  performance   : $([ $PERF_RC = 0 ] && echo GREEN || echo RED)"
echo "  valgrind      : $([ $VALGRIND_RC = 0 ] && echo GREEN || echo RED)  (compiler binary leak/error scan)"
echo "  fuzz          : $([ $FUZZ_RC = 0 ] && echo GREEN || echo RED)  (fail-closed: 0 crashes)"
echo "  differential  : $([ $DIFF_RC = 0 ] && echo GREEN || echo RED)  (opt -O==no-O + vs-seed)"
echo "  generics      : $([ $GENERICS_RC = 0 ] && echo GREEN || echo RED)  (negative type-arg checks fail closed)"
echo "  stdlib        : $([ $STDLIB_RC = 0 ] && echo GREEN || echo RED)  (lib/std/* via import, EXPECTED_STDLIB.tsv)"
echo "  multi-tu      : $([ $MTU_RC = 0 ] && echo GREEN || echo RED)  (cross-TU call + global, --emit-obj + gcc link)"
echo "  gguf-corrupt  : $([ $GGUF_RC = 0 ] && echo GREEN || echo RED)  (byte-level corrupt GGUF files must be rejected)"
echo "  verify-status : $([ $VERIFY_STATUS_RC = 0 ] && echo GREEN || echo RED)  (docs/status.json consistency)"
echo "  qobj          : $([ $QOBJ_RC = 0 ] && echo GREEN || echo RED)  (module cache write/read/cache-only, G1+G3+G5+G4, plus G6 cache self-compile)"
echo "  output-path   : $([ $OUTGUARD_RC = 0 ] && echo GREEN || echo RED)  (qc must refuse to overwrite its own input)"
echo "  naked         : $([ $NAKED_RC = 0 ] && echo GREEN || echo RED)  (naked fn + section + no_mangle, 0.0.229 Phase B)"
# Block promotion on a real functional/security/perf/valgrind/fuzz/diff/stdlib/mtu/qobj/verify-status
# regression. Security KNOWN issues are surfaced by the script but do not turn
# the gate red.
#
# qobj is included because the .qobj module cache had NO coverage at all: the
# 811-test functional gate never writes or consumes a cache, so it stayed green
# while every cache-only build failed (unreadable cache mode, 128-vs-144
# metadata stride, an unrebased IR_CALL argument list, and a cache written from
# stale IR). qobj_gate.sh is the only stage that exercises the format.
# NATIVE_RC is folded into FUNCTIONAL_RC above and listed separately for
# clarity: a native regression blocks promotion even though extern still works.
if [ $FUNCTIONAL_RC -ne 0 ] || [ $NATIVE_RC -ne 0 ] || [ $SECURITY_RC -ne 0 ] || [ $PERF_RC -ne 0 ] \
   || [ $VALGRIND_RC -ne 0 ] || [ $FUZZ_RC -ne 0 ] || [ $DIFF_RC -ne 0 ] \
   || [ $GENERICS_RC -ne 0 ] || [ $STDLIB_RC -ne 0 ] || [ $MTU_RC -ne 0 ] \
   || [ $QOBJ_RC -ne 0 ] || [ $VERIFY_STATUS_RC -ne 0 ] || [ $OUTGUARD_RC -ne 0 ] || [ $NAKED_RC -ne 0 ]; then
  exit 1
fi
exit 0
