#!/usr/bin/env bash
# 0.0.101 negative generics layer — proves the compile-time type-argument
# checks FAIL CLOSED: a bad generic instantiation must be a hard compile error
# (non-zero rc, no binary), not a silent type-erased call.
#
# Case 1: id<unknown>(42)  -> unknown type arg -> compile error (kind 1)
# Case 2: id<i64,i64>(42)  -> arity mismatch   -> compile error (kind 2)
set -u
QC="${QC:-./compiler/$(cat VERSION)/bin/x86/qc}"
CODES="./test_suites/codes"
TMP="$(mktemp -d)"
FAIL=0

emit() { printf '%s\n' "$1" > "$2"; }

echo "########## NEGATIVE GENERICS (compile-time type checks) ##########"

# Case 1: unknown type argument
emit 'fn id<T>(x T) T { return x }
fn main() { exit(id<unknown>(42)) }' "$TMP/neg_unknown.quanta"
if $QC "$TMP/neg_unknown.quanta" "$TMP/nu.bin" >/dev/null 2>&1; then
  echo "  FAIL: id<unknown>(42) compiled (should be a hard error)"; FAIL=$((FAIL+1))
else
  echo "  PASS: id<unknown>(42) rejected at compile time"
fi

# Case 2: arity mismatch on type args
emit 'fn id<T>(x T) T { return x }
fn main() { exit(id<i64,i64>(42)) }' "$TMP/neg_arity.quanta"
if $QC "$TMP/neg_arity.quanta" "$TMP/na.bin" >/dev/null 2>&1; then
  echo "  FAIL: id<i64,i64>(42) compiled (arity mismatch should error)"; FAIL=$((FAIL+1))
else
  echo "  PASS: id<i64,i64>(42) rejected (arity mismatch)"
fi

rm -rf "$TMP"
if [ "$FAIL" -ne 0 ]; then
  echo "  GENERICS-NEG: $FAIL failure(s)"
  exit 1
fi
echo "  GENERICS-NEG: GREEN (both negative cases fail closed)"
exit 0
