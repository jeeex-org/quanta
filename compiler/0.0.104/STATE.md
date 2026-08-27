# Quanta 0.0.104 — Release State

- **Version:** 0.0.104
- **Date:** 2026-08-27
- **Source entry:** `compiler/0.0.104/src/x86/main.quanta` (16 modules)
- **Build seed:** 0.0.103 (`compiler/0.0.103/bin/x86/qc`)
- **Compiler binary:** `compiler/0.0.104/bin/x86/qc`
- **Self-host fixpoint:** byte-identical `qc_self == qc`, md5 `dc18d73e1a5218d05f80a13fb9ae8d50` (3-stage boot→self→qc verified 2026-08-27).

## What landed in 0.0.104

`str_split(s, sep)` builtin — added to `emit_bltn` (emitter.quanta). Splits a
string on a single-byte separator into a qword array of N independent
string-header pointers (each segment is its own mmap with `[hdr]=len`, bytes at
`hdr+8`, NUL-terminated). Edge cases: no separator → single part = whole
string; empty string → single empty part.

Key typing fix: added a `vreg_str_arr` flag (globals.quanta) so the `str_split`
result is tagged as "array of strings". In IR_IDX (codegen.quanta), indexing a
str-array reads each element (a string pointer) with a **string tag** — so
`parts[i]` is treated as a byte-stride string, enabling `len(parts[i])` and
segment byte access. Without this, `parts[i]` was an untagged qword and
`len(parts[i])` / byte indexing read the wrong field.

Root-cause bug fixed: the `mmap` syscall clobbers `r11`, but the original code
stored `[sub]=r11` (the segment length header) *before* popping the saved
`seg_len` back into `r11` — so every segment header held the syscall's
leftover garbage instead of the real length. Fixed by restoring `r11` before the
store.

## Gate status (verified, all GREEN)
- functional: 136/136 core (EXPECTED.tsv) + str_split_test (rc=0) added → 137 codes, 137 expected
- valgrind: clean (0 errors, 0 leaks) on a str_split program
- fuzz: 30 deterministic comma-placement patterns + reassembly-invariant check → 0 crashes, total≤len
- self-host fixpoint: B==C byte-identical (md5 `dc18d73e1a5218d05f80a13fb9ae8d50`)

## ROADMAP / FEATURES sync
ROADMAP 0.0.104 → 🟡 partial: `str_split` GREEN; `utf8` remains deferred.
FEATURES §string ops: strcat/substr/str_split ✅ gate.
