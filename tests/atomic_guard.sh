#!/usr/bin/env bash
# tests/atomic_guard.sh — the 0.0.259 ATOMICS guard, standalone.
#
# WHY THIS IS A SCRIPT AND NOT A STAGE INSIDE test_suites/scripts/run_tests.sh.
# run_tests.sh is the compiler peer's path (shared, and being edited in the same
# tree). This check belongs to the atomics lever, so it lives in its own file and
# can be wired in with ONE line from the gate, or run by hand:
#
#     QC=/opt/tali/quanta/compiler/0.0.259/bin/x86/qc bash tests/atomic_guard.sh
#     bash tests/atomic_guard.sh                       # uses compiler/$(cat VERSION)/bin/x86/qc
#
# TO WIRE IT INTO THE GATE (one line, plus ATOM_RC in the exit condition — the
# same shape as marshal-guard / deadstore-guard / csave-guard):
#     ATOM_RC=0
#     if ! QC="$QC" bash tests/atomic_guard.sh; then ATOM_RC=1; fi
#     ... | [ "${ATOM_RC:-1}" -ne 0 ] || ...
#
# WHAT IT MEASURES, AND WHY IT IS A BYTE SCAN.
# Neither the ordering model nor the optimiser barrier has a FUNCTIONAL symptom:
# an ordering is a choice of instruction, and a barrier is a promise that no pass
# moved, merged or deleted an access. So, exactly like the marshal / deadstore /
# terminator / constmul guards, this reads the EMITTED OBJECT of one tiny fixed
# probe, restricted to `main`:
#
#   xchg %rsi,(%rdi)   a SEQ_CST store: implicitly locked
#   mov  %rsi,(%rdi)   a RELAXED / RELEASE store: deliberately unlocked
#   lock xadd          an atomic read-modify-write that SURVIVED THE OPTIMISER
#
# Counts are emitted bytes: exact, load-independent, no wall clock, no tolerance.
#
# MEASURED (main, --emit-obj + objdump, this box):
#   0.0.258:  mov 3   xchg 0   lock xadd 3   -> RED   (a seq_cst atomic_store was
#                                                     a plain mov, i.e. release)
#   0.0.259:  mov 2   xchg 1   lock xadd 3   -> GREEN
#
# Order matters. `xchg >= 1` is the ordering-model row and it is the one RED on
# the predecessor. `mov <= 2` pins that the order is HONOURED -- the seq_cst
# default must not have made every store locked, and an acquire/acq_rel store must
# not masquerade as a relaxed one. `lock xadd == 3` is the BARRIER row: it fails
# the moment a pass deletes, merges or CSEs an atomic access.
#
# Plus a negative that must FAIL to compile: an ordering argument that is a
# runtime value. A check that cannot fail for the reason it exists is worse than
# no check.
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
QC="${QC:-$REPO/compiler/$(cat "$REPO/VERSION")/bin/x86/qc}"
SRC="$REPO/test_suites/codes/atomic_ord_probe.quanta"
NEG="$REPO/test_suites/codes/atomic_order_neg_test.quanta"
OBJ=/tmp/atomic_guard.o
DIS=/tmp/atomic_guard.dis
RC=0
rm -f "$OBJ" "$DIS" "$DIS.main"

if [ ! -x "$QC" ]; then
    echo "atomics-guard: FAIL  no compiler at $QC"
    exit 1
fi
if [ ! -f "$SRC" ]; then
    echo "atomics-guard: FAIL  $SRC missing (the ordering/barrier probe)"
    exit 1
fi
if ! "$QC" --emit-obj "$SRC" "$OBJ" >/dev/null 2>&1; then
    echo "atomics-guard: FAIL  the ordering probe did not compile with --emit-obj"
    exit 1
fi

objdump -d --no-show-raw-insn "$OBJ" > "$DIS" 2>/dev/null
awk '/<main>:/{f=1;next} f&&/^$/{exit} f' "$DIS" > "$DIS.main"
# `|| true`: grep -c exits 1 when the count is 0, and under `set -e` a failing
# command substitution aborts the caller -- which would turn this guard's RED
# into a silent abort with no verdict at all.
atom_mov=$(grep -cE 'mov[a-z]*[[:space:]]+%rsi,\(%rdi\)' "$DIS.main" || true)
atom_xchg=$(grep -cE 'xchg[a-z]*[[:space:]]+%rsi,\(%rdi\)' "$DIS.main" || true)
atom_xadd=$(grep -c 'lock xadd' "$DIS.main" || true)

echo "atomics-guard: counts (main): mov=$atom_mov xchg=$atom_xchg lock-xadd=$atom_xadd  [compiler $QC]"

if [ "${atom_xchg:-0}" -lt 1 ]; then
    echo "atomics-guard: FAIL  no locked store (xchg=$atom_xchg): a seq_cst atomic_store is a plain mov, i.e. release-only (0.0.258 behaviour). See docs/research/atomics-0.0.259.md"
    RC=1
elif [ "${atom_mov:-0}" -gt 2 ]; then
    echo "atomics-guard: FAIL  $atom_mov unlocked atomic stores > 2: an order stronger than relaxed/release is emitted as an unlocked mov (see at_emit, emitter.quanta)"
    RC=1
elif [ "${atom_xadd:-0}" -ne 3 ]; then
    echo "atomics-guard: FAIL  $atom_xadd 'lock xadd', expected exactly 3: an atomic read-modify-write was deleted or MERGED by the optimiser (the memory-clobber barrier; see ir_isbar, codegen.quanta)"
    RC=1
elif [ ! -f "$NEG" ]; then
    echo "atomics-guard: FAIL  $NEG missing (the runtime-order negative fixture)"
    RC=1
elif "$QC" --no-overflow-trap "$NEG" /tmp/atomic_guard_neg >/dev/null 2>/tmp/atomic_guard_neg.err; then
    echo "atomics-guard: FAIL  a runtime-valued atomic ordering COMPILED; an order must be a compile-time literal, not a silent demotion"
    RC=1
elif ! grep -q "ordering argument" /tmp/atomic_guard_neg.err; then
    echo "atomics-guard: FAIL  runtime order rejected, but the message does not name the ordering: $(head -1 /tmp/atomic_guard_neg.err)"
    RC=1
else
    echo "atomics-guard: PASS  seq_cst store locked, relaxed/release store unlocked, 3/3 atomic RMWs survived the optimiser, runtime ordering rejected by name"
fi

# ---------------------------------------------------------------------------
# THE ACCEPTANCE ROWS, run from HERE as well as from the shared manifest.
#
# test_suites/EXPECTED.tsv is shared with the compiler peer, which is appending
# its own rows to it; carrying the acceptance in this script as well means it can
# be verified WITHOUT the shared manifest and without depending on root VERSION
# already naming the promoted tree. Two of the five rows are RED-FIRST, so until
# the version is promoted they would make the official gate red if they were only
# in EXPECTED.tsv -- which is precisely why the acceptance lives here too.
#
# rc expected per row, and the rc measured on 0.0.258 (the red-first evidence):
#   atomic_ws_test         0    <- 11 on 0.0.258  (the 2048-row claim loop)
#   atomic_addrglobal_test 0    <-  1 on 0.0.258  (&global was a temp address)
#   atomic_ord_test        0      0
#   atomic_ord_probe       30    30
#   atomic_test            11    11
ROWS="atomic_ws_test:0:11 atomic_addrglobal_test:0:1 atomic_ord_test:0:0 atomic_ord_probe:30:30 atomic_test:11:11"
for row in $ROWS; do
    name="${row%%:*}"; rest="${row#*:}"; want="${rest%%:*}"; old="${rest##*:}"
    src="$REPO/test_suites/codes/$name.quanta"
    bin="/tmp/atomic_guard_row"
    rm -f "$bin"
    if [ ! -f "$src" ]; then
        echo "atomics-guard: FAIL  row $name missing ($src)"
        RC=1; continue
    fi
    if ! "$QC" --no-overflow-trap "$src" "$bin" >/dev/null 2>/tmp/atomic_guard_row.err; then
        echo "atomics-guard: FAIL  row $name did not compile: $(head -1 /tmp/atomic_guard_row.err)"
        RC=1; continue
    fi
    "$REPO/scripts/quanta_run.sh" "$bin" >/dev/null 2>&1
    got=$?
    if [ "$got" = "$want" ]; then
        echo "atomics-guard: PASS  row $name rc=$got  (on 0.0.258: rc=$old)"
    else
        echo "atomics-guard: FAIL  row $name expected rc=$want, got rc=$got  (on 0.0.258: rc=$old)"
        RC=1
    fi
    rm -f "$bin"
done

rm -f "$OBJ" "$DIS" "$DIS.main" /tmp/atomic_guard_neg /tmp/atomic_guard_neg.err /tmp/atomic_guard_row.err
if [ "$RC" -eq 0 ]; then
    echo "atomics-guard: ALL GREEN (ordering model, optimiser barrier, negative, and the acceptance rows)"
fi
exit $RC
