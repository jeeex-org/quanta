# Quanta 0.0.109 — Release State

- **Version:** 0.0.109
- **Date:** 2026-08-27
- **Source entry:** `compiler/0.0.109/src/x86/main.quanta` (16 modules)
- **Build seed:** 0.0.106 (`compiler/0.0.106/bin/x86/qc`)
- **Self-host fixpoint:** stage2 == stage3, md5 `814a2724eca60ffa0a6b51f5cb279db8` (byte-identical)
- **Promoted from:** 0.0.109 (this version; copied from 0.0.106)

## What changed
F core (Built-ins) fs-metadata partial fix. The F-core row in FEATURES/ROADMAP was
🟡 PARTIAL because `stat/unlink/mkdir/chdir/rename` returned -ENOENT. Root causes:

1. **unlink / chdir** did `ri(3,8); ra(7,3)` (rdi += 8) — but IR_CALL already loads
   string args as `header+8`, so this applied +8 **twice** → garbage path (-ENOENT).
2. **rename** used the old-path +8 (double, see #1) and the new-path via `rbp` (the
   header pointer, **no** +8) → wrong new path.
3. **stat** loaded rsi (path) from IR_CALL rdi and overwrote rdi with AT_FDCWD,
   destroying the path; also its rsi remap was wrong.
4. **file_open** relied on IR_CALL's rdi for the path, which for Quanta string literals
   is the **header** (length prefix), not the bytes → it created files at mangled paths
   (e.g. `/tmp/qu_rt` was empty; stray NUL/control-char files appeared in cwd). The
   compiler itself reads its source via `file_open(argv_ptr, 0)` where `argv_ptr` is a
   **raw C-string pointer** (no length prefix) — so file_open must accept BOTH.

## Fix
- unlink / chdir / rename / stat: use `argp8(reg, ira2(ii), k)` which loads the arg's
  spill-home header and adds exactly one +8 (header → bytes). This is the same helper
  `mkdir` already used correctly.
- file_open(path, flags, mode): detect whether arg0 is a Quanta string via the
  `vreg_is_str` tag (mirroring print()/echo()). If string → `argp8` (+8). If raw
  pointer (argv) → use IR_CALL's rdi directly (no +8). This makes both
  `file_open("/path", ...)` (string literal) and `file_open(argv_ptr, ...)` (raw)
  correct — and restores a byte-identical self-host fixpoint.

## Tests
- `fs_meta_test.quanta` (rc=11): mkdir → file_open(create) → stat → rename → unlink →
  chdir, all on real `/tmp` paths; verifies no stray/mangled files.
- `file_open_test.quanta` (rc=11): file_open on an existing source file returns a valid
  fd (>=3). Updated because the old test manually did `f+8` (now redundant).
- `net_test.quanta` (rc=11) carried over from 0.0.106.
- Full gate: 140/140 functional + extern-c/security/performance/valgrind/fuzz/
  differential/generics-negative all GREEN.

## Gate result
- functional : GREEN (140/140)
- extern-c   : GREEN
- security   : GREEN (fail-closed)
- performance: GREEN
- valgrind   : GREEN
- fuzz       : GREEN
- differential: GREEN
- generics    : GREEN
- self-host   : byte-identical (stage2 == stage3)
