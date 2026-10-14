#!/bin/bash
# scripts/si_generate.sh - Self-Improvement Code & Test Generator
# Parses gap_specs.json and generates Quanta module + test stubs

set -e

SPECS_FILE="gap_specs.json"
# Staging ONLY -- never a tracked tree (lib/std, test_suites/codes). See
# SYNTH_OUT_ROOT in lib/std/code_synthesizer.quanta.
STDLIB_DIR="synth_out"
TEST_DIR="synth_out/tests"
GENERATED=0

# Check if jq is available
if command -v jq &> /dev/null; then
    # Use jq for proper JSON parsing
    SPECS=$(jq -r '.specs[] | "\(.domain)|\(.category)|\(.module)"' "$SPECS_FILE" 2>/dev/null || echo "")
else
    # Fallback: use grep/sed to extract domain/category/module triplets
    # This is fragile but works for our known JSON format
    SPECS=$(grep -oP '"domain":\s*"\K[^"]+' "$SPECS_FILE" | while read domain; do
        echo "placeholder"
    done)
    echo "Warning: jq not found, using limited fallback parsing" >&2
    SPECS=""
fi

if [ -z "$SPECS" ]; then
    echo "No specs found or jq not available."
    echo "Install jq for full functionality: sudo apt-get install jq"
    exit 0
fi

# Process each spec
echo "$SPECS" | while IFS='|' read -r domain category module; do
    if [ -z "$domain" ] || [ -z "$category" ] || [ -z "$module" ]; then
        continue
    fi
    
    # Sanitize identifiers (replace non-alphanumeric with underscore)
    clean_domain=$(echo "$domain" | sed 's/[^a-zA-Z0-9]/_/g' | tr '[:upper:]' '[:lower:]')
    clean_category=$(echo "$category" | sed 's/[^a-zA-Z0-9]/_/g' | tr '[:upper:]' '[:lower:]')
    clean_module=$(echo "$module" | sed 's/[^a-zA-Z0-9]/_/g' | tr '[:upper:]' '[:lower:]')
    
    # Generate filename
    FILENAME="${clean_domain}_${clean_category}_${clean_module}.quanta"
    
    # Skip if file already exists
    if [ -f "$STDLIB_DIR/$FILENAME" ]; then
        continue
    fi
    
    # Generate module stub
    cat > "$STDLIB_DIR/$FILENAME" << EOF
// std/${clean_domain}_${clean_category}_${clean_module} - SI-generated stub
// Domain: ${domain} | Category: ${category} | Module: ${module}
// Status: planned

module std_${clean_domain}_${clean_category}_${clean_module};

import std/types;

// TODO: Implement based on gap spec
fn init() -> i64 {
    return 0;
}

fn main() -> i64 {
    return init();
}
EOF
    
    # Generate test stub
    TEST_FILENAME="std_${clean_domain}_${clean_category}_${clean_module}_const_test.quanta"
    cat > "$TEST_DIR/$TEST_FILENAME" << EOF
// SI-generated const test for std/${clean_domain}_${clean_category}_${clean_module}
import std/${clean_domain}_${clean_category}_${clean_module}

fn main() {
    return 0
}
EOF
    
    GENERATED=$((GENERATED + 1))
done

echo "SI generation complete: $GENERATED modules + tests created"
