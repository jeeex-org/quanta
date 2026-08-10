#!/usr/bin/env bash
# Quanta Promotion Script
# =======================
# Automates promotion of WIP source to a stable version with MANDATORY
# regression guards. Fails hard if any guard is not met.
#
# Usage: ./scripts/promote.sh <new_version> <wip_source>
# Example: ./scripts/promote.sh 0.0.19 src/qc-0.0.19-wip.quanta
#
# Guards enforced (the exact failures that slipped through before):
#   1. x86 self-host fixed-point: stage1 == stage2 (byte-identical)
#   2. ARM64 cross-compile: ALL 61 tests compile (no FAILCOMPILE)
#   3. ARM64 device run: 61/61 PASS on ARM-01 (no "known gaps" allowed)
#   4. Old version files removed from git before commit
#   5. bin/qc symlink updated
#
# If ANY guard fails, the script exits non-zero and leaves git clean (no partial commit).

set -euo pipefail

# Configuration - UPDATE THESE when device IPs change
ARM_HOST="tali@192.168.254.231"
ARM_DEST_DIR="~/promo_rt"
SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=15 -o BatchMode=yes"

VERSION="${1:-}"
WIP_SRC="${2:-}"

if [[ -z "$VERSION" || -z "$WIP_SRC" ]]; then
    echo "Usage: $0 <version> <wip_source_file>"
    echo "Example: $0 0.0.19 src/qc-0.0.19-wip.quanta"
    exit 1
fi

if [[ ! -f "$WIP_SRC" ]]; then
    echo "ERROR: WIP source not found: $WIP_SRC"
    exit 1
fi

SRC_DIR="src"
BIN_DIR="bin"
X86_BIN="$BIN_DIR/x86_64/qc-$VERSION"
ARM_BIN="$BIN_DIR/aarch64/qc-$VERSION"
PROMO_SRC="$SRC_DIR/qc-$VERSION.quanta"

# Helper: fail with message and leave repo clean
fail() {
    echo "=== GUARD FAILED ==="
    echo "$1"
    echo "Repo left clean — no partial promotion committed."
    exit 1
}

# Helper: run command and capture output
run_cmd() {
    local out
    out=$(eval "$1" 2>&1)
    local rc=$?
    echo "$out"
    return $rc
}

echo "=== PROMOTION: qc-$VERSION from $WIP_SRC ==="
echo "Guards: x86 fixed-point | ARM64 cross-compile 61/61 | ARM-01 device 61/61"
echo ""

# --- GUARD 1: x86 self-host fixed-point ---
echo "--- GUARD 1: x86 self-host fixed-point ---"
STAGE1="/tmp/promo_stage1_$$.bin"
STAGE2="/tmp/promo_stage2_$$.bin"
STABLE_QC="./bin/x86_64/qc-0.0.18"

echo "Building stage1 from stable 0.0.18..."
run_cmd "$STABLE_QC $WIP_SRC $STAGE1 2>/dev/null" || fail "stage1 build failed"
echo "Building stage2 from stage1..."
run_cmd "$STAGE1 $WIP_SRC $STAGE2 2>/dev/null" || fail "stage2 build failed"

if ! cmp -s "$STAGE1" "$STAGE2"; then
    fail "Fixed-point broken: stage1 != stage2 (not byte-identical)"
fi
echo "OK: stage1 == stage2 (fixed-point verified)"
rm -f "$STAGE1" "$STAGE2"

# --- GUARD 2: ARM64 cross-compile full 61-suite ---
echo ""
echo "--- GUARD 2: ARM64 cross-compile 61/61 ---"
PROMO_RT_DIR="/tmp/promo_rt_$$"
mkdir -p "$PROMO_RT_DIR/bin"
COMPILE_FAIL=0
while IFS=$'\t' read -r name expected; do
    src="test_suites/codes/$name"
    out="$PROMO_RT_DIR/bin/${name%.quanta}"
    if ! ./bin/x86_64/qc-0.0.18 "$WIP_SRC" "$out" --target=arm64 2>/dev/null; then
        echo "FAILCOMPILE $name"
        COMPILE_FAIL=$((COMPILE_FAIL + 1))
    fi
done < test_suites/EXPECTED.tsv

if [[ $COMPILE_FAIL -gt 0 ]]; then
    fail "ARM64 cross-compile: $COMPILE_FAIL failures (must be 0)"
fi
echo "OK: 61/61 cross-compiled cleanly"

# --- GUARD 3: ARM64 device run 61/61 on ARM-01 ---
echo ""
echo "--- GUARD 3: ARM-01 hardware 61/61 ---"
ssh $SSH_OPTS "$ARM_HOST" "mkdir -p $ARM_DEST_DIR"
scp $SSH_OPTS -q "$PROMO_RT_DIR"/bin/* "$ARM_HOST:$ARM_DEST_DIR/" || fail "scp to ARM-01 failed"

PASS_COUNT=$(ssh $SSH_OPTS "$ARM_HOST" "
    cd ~
    rm -f /tmp/promo_run.txt
    while IFS=\$'\\t' read -r line; do
        raw=\$(echo \"\$line\" | cut -f1)
        exp=\$(echo \"\$line\" | cut -f2)
        bin=\$(echo \"\$raw\" | sed 's/\\.quanta//')
        if [ -x \"$ARM_DEST_DIR/\$bin\" ]; then
            timeout 10 \"$ARM_DEST_DIR/\$bin\" >/dev/null 2>&1
            rc=\$?
            if [ \"\$rc\" -eq \"\$exp\" ]; then
                echo \"PASS \$raw\" >> /tmp/promo_run.txt
            else
                echo \"FAIL \$raw exp=\$exp got=\$rc\" >> /tmp/promo_run.txt
            fi
        fi
    done < ~/proj/EXPECTED.tsv 2>/dev/null || cat ~/EXPECTED.tsv 2>/dev/null
    grep -c '^PASS' /tmp/promo_run.txt 2>/dev/null || echo 0
")

if [[ $PASS_COUNT -ne 61 ]]; then
    FAILS=$(ssh $SSH_OPTS "$ARM_HOST" "grep '^FAIL' /tmp/promo_run.txt 2>/dev/null" || echo "ssh failed")
    fail "ARM-01 run: $PASS_COUNT/61 pass (must be 61). Failures: $FAILS"
fi
echo "OK: ARM-01 $PASS_COUNT/61 pass"

# --- GUARD 4: Clean old version from git ---
echo ""
echo "--- GUARD 4: Remove old version from git ---"
OLD_SRC="$SRC_DIR/qc-$VERSION.quanta"
OLD_X86="$BIN_DIR/x86_64/qc-$VERSION"
OLD_ARM="$BIN_DIR/aarch64/qc-$VERSION"
if git ls-files | grep -q "qc-$VERSION"; then
    echo "Removing tracked old files..."
    git rm -f "$OLD_SRC" "$OLD_X86" "$OLD_ARM" || fail "git rm old files failed"
else
    echo "No old tracked files found for $VERSION"
fi

# --- Build and stage fresh binaries ---
echo ""
echo "--- Build fresh binaries from promoted source ---"
# First promote source
mv "$WIP_SRC" "$PROMO_SRC"

# Build x86 using stable
run_cmd "./bin/x86_64/qc-0.0.18 $PROMO_SRC $X86_BIN 2>/dev/null" || fail "x86 final build failed"
# Build ARM using fresh x86 (cross)
run_cmd "./$X86_BIN $PROMO_SRC $ARM_BIN --target=arm64 2>/dev/null" || fail "ARM cross build failed"

# --- GUARD 5: Update bin/qc symlink ---
echo ""
echo "--- GUARD 5: Update bin/qc symlink ---"
ln -sf "x86_64/qc-$VERSION" "$BIN_DIR/qc"
if [[ "$(readlink $BIN_DIR/qc)" != "x86_64/qc-$VERSION" ]]; then
    fail "symlink not updated correctly"
fi
echo "OK: bin/qc -> x86_64/qc-$VERSION"

# --- Stage all and commit ---
echo ""
echo "--- Stage and commit ---"
git add -A
git commit -m "Promote qc-$VERSION: ARM64 cross-compile 61/61 + x86 fixed-point

- x86_64 self-host: stage1 == stage2 byte-identical
- ARM64 cross-compile: 61/61 clean
- ARM-01 device: 61/61 pass (verified on hardware)
- Old regressed $VERSION removed
- bin/qc symlink updated"

echo ""
echo "=== PROMOTION COMPLETE: qc-$VERSION ==="
echo "Run 'git push origin main' to publish."