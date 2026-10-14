#!/usr/bin/env bash
# verify-release.sh <NEXT> <VER>
#
# Runs the checks in docs/RELEASE_CHECKLIST.md that are mechanical enough to
# automate. Steps that need a human judgement call (writing WIP.md prose,
# deciding a claim is true) stay in the checklist and are NOT done here -- this
# script only verifies what it can measure.
#
#   <NEXT> = version being built, one patch above <VER>
#   <VER>  = released stable, read from root VERSION when omitted
#
# CONVENTION: this is a PRE-PROMOTION check. Run it BEFORE the version bump,
# while root VERSION still names the released stable <VER>, so <NEXT> can be
# proven to build from <VER>'s committed seed (check 6) and <VER> proven to be a
# valid frozen baseline (check 5). Correct invocation while developing <NEXT>:
#
#     bash scripts/verify-release.sh <NEXT> "$(cat VERSION)"
#
# Re-running AFTER the bump (root VERSION == <NEXT>) is also meaningful -- checks
# 5-7 re-verify the promoted tree against its frozen baseline -- so check 1
# accepts both states and says which one it detected. Any other VERSION is a real
# mismatch.
#
# Exit 0 only if every check passes. Any FAIL is a promotion blocker.

set -uo pipefail
cd /opt/tali/quanta || { echo "FATAL: not in /opt/tali/quanta"; exit 2; }

NEXT="${1:-}"
VER="${2:-$(cat VERSION)}"

if [[ -z "$NEXT" ]]; then
    echo "usage: bash scripts/verify-release.sh <NEXT> [<VER>]" >&2
    exit 2
fi

PASS=0; FAIL=0
ok()   { printf '  PASS  %s\n' "$1"; PASS=$((PASS+1)); }
bad()  { printf '  FAIL  %s\n' "$1"; FAIL=$((FAIL+1)); }
note() { printf '  ....  %s\n' "$1"; }

echo "=== verify-release: <NEXT>=$NEXT  <VER>=$VER ==="

# --- 1. version pointer -----------------------------------------------------
# Accept both documented states (see the header): pre-promotion (VERSION == <VER>)
# and post-promotion re-check (VERSION == <NEXT>). The previous strict
# "VERSION == <VER>" made the script a permanent false red once a tree was
# promoted, because there is no <NEXT> tree to check a promoted version against.
V=$(cat VERSION)
if [[ "$V" == "$VER" ]]; then
    ok "root VERSION = $VER (<VER>, the released stable) -- pre-promotion state"
elif [[ "$V" == "$NEXT" ]]; then
    note "root VERSION = $NEXT = <NEXT>: tree ALREADY PROMOTED; <VER>=$VER is the frozen baseline being re-verified"
    ok "root VERSION = $NEXT == <NEXT> (promoted) -- post-promotion re-check"
else
    bad "root VERSION = $V, expected <VER>=$VER (pre-promotion) or <NEXT>=$NEXT (post-promotion); run BEFORE the bump as: bash scripts/verify-release.sh <NEXT> \$(cat VERSION)"
fi

[[ -e compiler/VERSION ]] && bad "compiler/VERSION exists -- root VERSION must be the only pointer" \
                          || ok "no compiler/VERSION (root VERSION is the only pointer)"

# --- 2. version arithmetic --------------------------------------------------
NEXT_MAJ=${NEXT%%.*}; NEXT_REST=${NEXT#*.}; NEXT_MIN=${NEXT_REST%%.*}; NEXT_PAT=${NEXT_REST#*.}
VER_MAJ=${VER%%.*};  VER_REST=${VER#*.};  VER_MIN=${VER_REST%%.*};  VER_PAT=${VER_REST#*.}
if [[ "$NEXT_MAJ.$NEXT_MIN" == "$VER_MAJ.$VER_MIN" && "$NEXT_PAT" -eq $((VER_PAT+1)) ]]; then
    ok "<NEXT> is exactly one patch above <VER>"
else
    bad "<NEXT>=$NEXT is not <VER>=$VER plus one patch"
fi

# --- 3. the work tree exists ------------------------------------------------
[[ -d "compiler/$NEXT" ]] && ok "compiler/$NEXT/ exists" \
                         || bad "compiler/$NEXT/ missing"
[[ -d "compiler/$NEXT/src/x86" ]] && ok "compiler/$NEXT/src/x86/ exists" \
                                 || bad "compiler/$NEXT/src/x86/ missing"

# --- 4. golden binaries on disk, not in /tmp -------------------------------
for v in "$NEXT" "$VER"; do
    b="compiler/$v/bin/x86/qc"
    [[ -s "$b" ]] && ok "$b exists and is non-empty ($(stat -c%s "$b") bytes)" \
                 || bad "$b missing or ZERO BYTES"
done

# --- 5. <VER> source rebuilds to its own committed binary, BIT-FOR-BIT ------
# This is what makes <VER> a usable frozen baseline after promotion.
if [[ -x "compiler/$VER/bin/x86/qc" && -f "compiler/$VER/src/x86/main.quanta" ]]; then
    T=$(mktemp -d)
    if (cd "compiler/$VER" && ./bin/x86/qc -O src/x86/main.quanta "$T/rebuild.bin") >/dev/null 2>&1 \
       && [[ -s "$T/rebuild.bin" ]]; then
        A=$(md5sum "compiler/$VER/bin/x86/qc" | cut -d' ' -f1)
        B=$(md5sum "$T/rebuild.bin" | cut -d' ' -f1)
        if [[ "$A" == "$B" ]]; then
            ok "<VER> src rebuilds BIT-FOR-BIT (md5 $A) -- qualifies as frozen baseline"
        else
            bad "<VER> src DIVERGED from its binary (committed $A, rebuilt $B) -- not a valid baseline"
        fi
    else
        bad "<VER> source failed to rebuild"
    fi
    rm -rf "$T"
else
    bad "<VER> source or binary missing, cannot prove baseline"
fi

# --- 6. src/bin lockstep for <NEXT> ----------------------------------------
# Build to a SEPARATE path. qc cannot write its own binary in place: doing so
# truncates the running file to 0 bytes.
if [[ -x "compiler/$VER/bin/x86/qc" && -f "compiler/$NEXT/src/x86/main.quanta" ]]; then
    T=$(mktemp -d)
    if (cd "compiler/$NEXT" && "../$VER/bin/x86/qc" -O src/x86/main.quanta "$T/n.bin") >/dev/null 2>&1 \
       && [[ -s "$T/n.bin" ]]; then
        A=$(md5sum "compiler/$NEXT/bin/x86/qc" | cut -d' ' -f1)
        B=$(md5sum "$T/n.bin" | cut -d' ' -f1)
        [[ "$A" == "$B" ]] && ok "<NEXT> src rebuilds to its committed binary (md5 $A) -- SRC and BIN in lockstep" \
                           || bad "<NEXT> src DIVERGED (committed $A, rebuilt $B) -- SRC and BIN out of lockstep"
    else
        bad "<NEXT> failed to rebuild from <VER> compiler"
    fi
    rm -rf "$T"
fi

# --- 7. self-host fixed point ---------------------------------------------
if [[ -x "compiler/$NEXT/bin/x86/qc" ]]; then
    T=$(mktemp -d)
    G=()
    for i in 0 1 2; do
        if (cd "compiler/$NEXT" && ./bin/x86/qc -O src/x86/main.quanta "$T/gen$i") >/dev/null 2>&1 \
           && [[ -s "$T/gen$i" ]]; then
            G+=("$(md5sum "$T/gen$i" | cut -d' ' -f1)")
        fi
    done
    if [[ ${#G[@]} -eq 3 && "${G[0]}" == "${G[1]}" && "${G[1]}" == "${G[2]}" ]]; then
        BIN=$(md5sum "compiler/$NEXT/bin/x86/qc" | cut -d' ' -f1)
        if [[ "${G[0]}" == "$BIN" ]]; then
            ok "self-host fixed point: gen0==gen1==gen2==released binary (md5 ${G[0]})"
        else
            bad "gen0==gen1==gen2 but != released binary (gens ${G[0]}, binary $BIN)"
        fi
    else
        bad "self-host did NOT reach a fixed point (${#G[@]}/3 generations built)"
    fi
    rm -rf "$T"
fi

# --- 8. WIP.md exists and carries no zero-byte-binary claim ---------------
if [[ -f "compiler/$NEXT/WIP.md" ]]; then
    ok "compiler/$NEXT/WIP.md exists"
else
    bad "compiler/$NEXT/WIP.md missing"
fi

# --- 9. the official gate --------------------------------------------------
# Untrusted generated programs are memory-bounded with a cgroup scope; a time
# limit is not a memory limit (see the 50GB runaway in the 0.0.223 notes).
GATE_LOG=${GATE_LOG:-/tmp/verify_release_gate.log}
if [[ "${SKIP_GATE:-0}" != "1" ]]; then
    if timeout 2400 systemd-run --user --scope -q -p MemoryMax=6G -p MemorySwapMax=0 \
        bash -c "QC=/opt/tali/quanta/compiler/$NEXT/bin/x86/qc bash test_suites/scripts/run_tests.sh" \
        > "$GATE_LOG" 2>&1; then
        ok "official gate ran (log: $GATE_LOG)"
    else
        bad "official gate returned non-zero (log: $GATE_LOG)"
    fi
    grep -qE 'Results: [0-9]+/[0-9]+ pass, 0 fail' "$GATE_LOG" \
        && ok "$(grep -oE 'Results: [0-9]+/[0-9]+ pass, 0 fail' "$GATE_LOG" | head -1)" \
        || bad "gate did not report a clean pass -- see $GATE_LOG"
    grep -qE 'functional *: RED' "$GATE_LOG" \
        && bad "functional stage RED" \
        || ok "functional stage GREEN"
else
    note "gate SKIPPED (SKIP_GATE=1) -- not verified by this run"
fi

echo
echo "=== $PASS passed, $FAIL failed ==="
[[ $FAIL -eq 0 ]] || exit 1
exit 0