#!/usr/bin/env bash
# output_path_guard_test.sh <qc-binary>
#
# The compiler must refuse to overwrite its own input.
#
# `qc SRC SRC` used to read SRC and then open SRC for writing as the output,
# replacing the source with a compiled binary. lib/std/gguf.quanta (155 KB of
# source) was destroyed that way and had to be rebuilt from git.
#
# The check is on (st_dev, st_ino), not on the path text, so these cases all
# have to be caught even though only the first has identical argument strings.
#
# Exits 0 when every case behaves, 1 otherwise.
set -u

QC="${1:-}"
if [ -z "$QC" ] || [ ! -x "$QC" ]; then
    echo "usage: $0 <qc-binary>"
    exit 2
fi
QC="$(readlink -f "$QC")"

D="$(mktemp -d)"
trap 'rm -rf "$D"' EXIT
FAIL=0

SRC_BODY='fn main() -> i64 { return 42 }
'
mk_src() { printf '%s' "$SRC_BODY" > "$1"; }
sum()    { md5sum "$1" | cut -d' ' -f1; }

# refuse_case <label> <expected-rc-nonzero> <args...>
# Runs the compiler, then asserts the source is byte-identical afterwards.
refuse_case() {
    local label="$1"; shift
    local src="$1"; shift
    local before; before="$(sum "$src")"
    local rc=0
    "$QC" "$@" >/dev/null 2>&1 || rc=$?
    local after; after="$(sum "$src")"
    if [ "$rc" -eq 0 ]; then
        echo "  FAIL $label: compiler exited 0 (should have refused)"
        FAIL=1
        return
    fi
    if [ "$before" != "$after" ]; then
        echo "  FAIL $label: SOURCE WAS MODIFIED (rc=$rc)"
        FAIL=1
        return
    fi
    # and the refusal must say so, not fail for an unrelated reason
    local msg
    msg="$("$QC" "$@" 2>&1 >/dev/null | head -1)"
    case "$msg" in
        *"output path is the source path"*) : ;;
        *) echo "  FAIL $label: refused for the wrong reason: $msg"; FAIL=1; return ;;
    esac
    echo "  PASS $label (refused, source intact)"
}

# ok_case <label> <args...>
ok_case() {
    local label="$1"; shift
    local rc=0
    "$QC" "$@" >/dev/null 2>&1 || rc=$?
    if [ "$rc" -ne 0 ]; then
        echo "  FAIL $label: compiler exited $rc (should have succeeded)"
        FAIL=1
        return
    fi
    echo "  PASS $label"
}

# --- 1. the original destructive invocation ---------------------------------
mk_src "$D/a.quanta"
refuse_case "qc SRC SRC" "$D/a.quanta" "$D/a.quanta" "$D/a.quanta"

# --- 2. a different string for the same inode ------------------------------
mk_src "$D/b.quanta"
( cd "$D" && refuse_case "qc ./SRC SRC" "$D/b.quanta" "./b.quanta" "b.quanta" )

# --- 3. a symlink to the source -------------------------------------------
mk_src "$D/c.quanta"
ln -sf "$D/c.quanta" "$D/clink.quanta"
refuse_case "qc SRC symlink->SRC" "$D/c.quanta" "$D/c.quanta" "$D/clink.quanta"

# --- 4. a normal compile must still work ----------------------------------
mk_src "$D/d.quanta"
ok_case "qc SRC OUT (normal)" "$D/d.quanta" "$D/d.bin"
if [ ! -x "$D/d.bin" ]; then
    echo "  FAIL qc SRC OUT: no executable produced"; FAIL=1
else
    "$D/d.bin"; rc=$?
    if [ "$rc" -ne 42 ]; then
        echo "  FAIL qc SRC OUT: program returned $rc, expected 42"; FAIL=1
    else
        echo "  PASS qc SRC OUT: program runs (rc=42)"
    fi
fi

# --- 5. overwriting an unrelated existing output must still work ----------
ok_case "qc SRC EXISTING_OUT" "$D/d.quanta" "$D/d.bin"

# --- 6. an output that does not exist yet must still work ----------------
rm -f "$D/new.bin"
ok_case "qc SRC NEW_OUT" "$D/d.quanta" "$D/new.bin"

# --- 7. every output mode goes through the same check -------------------
mk_src "$D/e.quanta"
refuse_case "--emit-obj SRC SRC" "$D/e.quanta" --emit-obj "$D/e.quanta" "$D/e.quanta"

# --- 8. output elsewhere on disk ---------------------------------------
mkdir -p "$D/out"
ok_case "qc SRC other-dir/OUT" "$D/d.quanta" "$D/out/d"

# --- 9. an output path that cannot be CREATED must fail LOUDLY --------------
# 0.0.260. `write_elf` discarded BOTH `file_open`'s and `file_write`'s return
# values: a failed open left ofd negative, the `if ofd >= 0` guard skipped the
# write, and the compiler exited 0 having produced nothing. This is the same
# discarded-return class 0.0.257 opened one layer up (the --emit-qobj write), and
# it is what made "oversized alloc died silently (exit 0, no binary)" possible to
# mistake for success. Two independent unwritable shapes, because they fail for
# different reasons and one of them (a missing parent) is NOT a permission test:
#
#   measured 0.0.258 / 0.0.259:  rc=0, no binary, nothing on stderr -- for both.
#   measured 0.0.260:            rc=1, '"qc: error: cannot open the output file
#                                for writing"'.
unwritable_case() {
    local label="$1"; shift
    local out="$1"; shift
    rm -f "$out"
    local rc=0 msg
    msg="$("$QC" "$@" 2>&1 >/dev/null)" || rc=$?
    if [ "$rc" -eq 0 ]; then
        echo "  FAIL $label: compiler exited 0 with no output at all -- a silent success (0.0.258/0.0.259 behaviour)"
        FAIL=1
        return
    fi
    if [ -e "$out" ]; then
        echo "  FAIL $label: exited $rc but an output file exists anyway"
        FAIL=1
        return
    fi
    if [ -z "$msg" ]; then
        echo "  FAIL $label: exited $rc but said NOTHING -- a failure a caller cannot attribute"
        FAIL=1
        return
    fi
    echo "  PASS $label (exited $rc, '$(echo "$msg" | head -1)')"
}

mk_src "$D/f.quanta"
RO="$D/ro"
mkdir -p "$RO"; chmod 555 "$RO"
unwritable_case "unwritable dir" "$RO/f.bin" "$D/f.quanta" "$RO/f.bin"
# the same shape in the other output mode, which shares write_elf
unwritable_case "--emit-obj unwritable dir" "$RO/f.o" --emit-obj "$D/f.quanta" "$RO/f.o"
chmod 755 "$RO"
unwritable_case "missing parent" "$D/nodir/f.bin" "$D/f.quanta" "$D/nodir/f.bin"

if [ "$FAIL" -eq 0 ]; then
    echo "  OUTPUT-PATH GUARD: PASS"
    exit 0
fi
echo "  OUTPUT-PATH GUARD: FAIL"
exit 1
