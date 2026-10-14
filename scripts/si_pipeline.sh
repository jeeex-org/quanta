#!/bin/bash
# scripts/si_pipeline.sh - Self-Improvement Pipeline
# Orchestrates: gap detection → IR mapping → code synthesis → test generation

set -e

SPECS_FILE="gap_specs.json"
# Staging ONLY -- these MUST NOT point at a tracked tree. See SYNTH_OUT_ROOT in
# lib/std/code_synthesizer.quanta: the generator used to rewrite lib/std and
# test_suites/codes directly on every run (9,026 files).
STDLIB_DIR="synth_out"
TEST_DIR="synth_out/tests"
TMP_DIR="/tmp/si_pipeline"
mkdir -p "$TMP_DIR"

echo "╔══════════════════════════════════════════════════╗"
echo "║  Quanta Self-Improvement Pipeline v1.0           ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# Phase 1: Gap Detection
echo "=== SI Phase 1: Gap Detection ==="
if [ ! -f "$SPECS_FILE" ]; then
    echo "Error: $SPECS_FILE not found"
    exit 1
fi

# Count specs using jq
TOTAL_SPECS=$(jq '.specs | length' "$SPECS_FILE" 2>/dev/null || echo "0")
PLANNED_SPECS=$(jq '[.specs[] | select(.status | contains("planned"))] | length' "$SPECS_FILE" 2>/dev/null || echo "0")
echo "Total specs: $TOTAL_SPECS"
echo "Planned specs needing implementation: $PLANNED_SPECS"
echo "$PLANNED_SPECS gaps detected"

# Phase 2: Generate IR
echo ""
echo "=== SI Phase 2: Generate IR ==="
# Export specs to a simple format for processing
jq -r '.specs[] | "\(.domain)|\(.category)|\(.module)|\(.status)"' "$SPECS_FILE" 2>/dev/null > "$TMP_DIR/ir_specs.txt" || true
IR_COUNT=$(wc -l < "$TMP_DIR/ir_specs.txt" 2>/dev/null || echo "0")
echo "$IR_COUNT specs mapped to IR"

# Phase 3: Code Synthesis
echo ""
echo "=== SI Phase 3: Code Synthesis ==="
SYNTH_COUNT=0

while IFS='|' read -r domain category module status; do
    # Skip if not planned
    if [[ ! "$status" =~ planned ]]; then
        continue
    fi
    
    # Sanitize identifiers
    clean_domain=$(echo "$domain" | sed 's/[^a-zA-Z0-9]/_/g' | tr '[:upper:]' '[:lower:]')
    clean_category=$(echo "$category" | sed 's/[^a-zA-Z0-9]/_/g' | tr '[:upper:]' '[:lower:]')
    clean_module=$(echo "$module" | sed 's/[^a-zA-Z0-9]/_/g' | tr '[:upper:]' '[:lower:]')
    
    FILENAME="${clean_domain}_${clean_category}_${clean_module}.quanta"
    FILEPATH="$STDLIB_DIR/$FILENAME"
    
    # Skip if file already exists
    if [ -f "$FILEPATH" ]; then
        SYNTH_COUNT=$((SYNTH_COUNT + 1))
        continue
    fi
    
    # Generate module stub
    cat > "$FILEPATH" << EOF
// std/${clean_domain}_${clean_category}_${clean_module} - SI-generated
// Domain: ${domain} | Category: ${category} | Module: ${module}
// Source: gap_specs.json

module std_${clean_domain}_${clean_category}_${clean_module};

import std/types;

// Core operations for ${module}
fn init() -> i64 {
    return 0;
}

fn main() -> i64 {
    return init();
}
EOF
    
    SYNTH_COUNT=$((SYNTH_COUNT + 1))
done < "$TMP_DIR/ir_specs.txt"

echo "$SYNTH_COUNT modules synthesized"

# Phase 4: Test Generation
echo ""
echo "=== SI Phase 4: Test Generation ==="
TEST_COUNT=0

while IFS='|' read -r domain category module status; do
    # Skip if not planned
    if [[ ! "$status" =~ planned ]]; then
        continue
    fi
    
    # Sanitize identifiers
    clean_domain=$(echo "$domain" | sed 's/[^a-zA-Z0-9]/_/g' | tr '[:upper:]' '[:lower:]')
    clean_category=$(echo "$category" | sed 's/[^a-zA-Z0-9]/_/g' | tr '[:upper:]' '[:lower:]')
    clean_module=$(echo "$module" | sed 's/[^a-zA-Z0-9]/_/g' | tr '[:upper:]' '[:lower:]')
    
    MODULE_FILE="$STDLIB_DIR/${clean_domain}_${clean_category}_${clean_module}.quanta"
    TEST_FILE="$TEST_DIR/std_${clean_domain}_${clean_category}_${clean_module}_const_test.quanta"
    
    # Skip if module doesn't exist or test already exists
    if [ ! -f "$MODULE_FILE" ] || [ -f "$TEST_FILE" ]; then
        continue
    fi
    
    # Generate test stub
    cat > "$TEST_FILE" << EOF
// SI-generated const test for std/${clean_domain}_${clean_category}_${clean_module}
// Domain: ${domain} | Category: ${category} | Module: ${module}

import std/${clean_domain}_${clean_category}_${clean_module}

fn main() {
    // TODO: Add test assertions
    return 0
}
EOF
    
    TEST_COUNT=$((TEST_COUNT + 1))
done < "$TMP_DIR/ir_specs.txt"

echo "$TEST_COUNT tests generated"

# Phase 5: Run Tests
echo ""
echo "=== SI Phase 5: Run Tests ==="
echo "Tests are run by CI gate (./test_suites/scripts/run_tests.sh)"

# Phase 6: Merge
echo ""
echo "=== SI Phase 6: Merge ==="
echo "Merge requires human review gate"

# Summary
echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║  SI Pipeline Summary                             ║"
echo "╠══════════════════════════════════════════════════╣"
echo "║  Gaps detected:       $PLANNED_SPECS"
echo "║  IR specs mapped:     $IR_COUNT"
echo "║  Modules synthesized: $SYNTH_COUNT"
echo "║  Tests generated:     $TEST_COUNT"
echo "╚══════════════════════════════════════════════════╝"

echo ""
echo "SI pipeline complete."
