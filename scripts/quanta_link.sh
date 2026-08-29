#!/usr/bin/env bash
# quanta_link.sh — link a Quanta --emit-obj object into a standalone executable
# WITHOUT gcc. Uses the system linker `ld` directly, which emits the PLT/GOT and
# resolves libc UNDEF symbols. This satisfies ROADMAP 0.0.122: "standalone EXE
# links libc symbols without gcc."
#
# Usage:
#   qc prog.quanta prog.o --emit-obj
#   quanta_link.sh prog.o prog          # -> prog (standalone ELF, runs with ld.so + libc)
#   quanta_link.sh prog.o               # -> prog.o.exe
#
# Fixpoint note: this is a standalone script, NOT inlined into compiler source, so
# the qc self-host (qc building qc) is unaffected — write_elf stays static.
set -euo pipefail

OBJ="${1:-}"
OUT="${2:-}"
if [ -z "$OBJ" ]; then
  echo "usage: $0 <input.o> [output]" >&2
  exit 2
fi
[ -f "$OBJ" ] || { echo "error: '$OBJ' not found" >&2; exit 2; }
[ -z "$OUT" ] && OUT="${OBJ%.o}.exe"

# Locate the glibc dynamic linker (PT_INTERP). ld's built-in default is the
# *BSD* name (/lib/ld64.so.1) which does not exist on Linux glibc, so we must
# pass the Linux interpreter explicitly. Probe a few well-known locations.
INTERP=""
for c in /lib64/ld-linux-x86-64.so.2 \
         /lib/ld-linux-x86-64.so.2 \
         /usr/lib64/ld-linux-x86-64.so.2 \
         /usr/lib/ld-linux-x86-64.so.2; do
  if [ -e "$c" ]; then INTERP="$c"; break; fi
done
if [ -z "$INTERP" ]; then
  echo "error: glibc dynamic linker (ld-linux) not found" >&2
  exit 3
fi

# Link: -lc pulls libc.so.6; --dynamic-linker sets PT_INTERP; qc emits _start so
# the default entry works. No gcc, no crt objects (Quanta provides _start/__init).
ld "$OBJ" -o "$OUT" -lc --dynamic-linker "$INTERP"
echo "linked: $OUT (interp=$INTERP, libc via ld)"
