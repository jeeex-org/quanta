# 0.0.129 — `fs` missing ops (stat/unlink/mkdir/chdir/rename/rmdir)

**Status:** ✅ DONE — self-hosting, gate-green, all 11 layers GREEN.

## What landed

Closed the `fs` ops gap: previously only `open`/`read`/`write`/`close` existed.
Added six missing filesystem builtins (low-level `file_*` syscall shims in
`emitter.quanta`) plus their `lib/std/fs.quanta` wrappers:

| Builtin | Syscall | Purpose |
|---|---|---|
| `file_stat(path, buf)` | `stat` (sc 4) | file metadata |
| `file_unlink(path)` | `unlink` (sc 87) | delete file |
| `file_mkdir(path, mode)` | `mkdir` (sc 83) | create dir |
| `file_chdir(path)` | `chdir` (sc 80) | change cwd |
| `file_rename(old, new)` | `rename` (sc 82) | move/rename |
| `file_rmdir(path)` | `rmdir` (sc 84) | remove empty dir |

Each wrapper null-terminates the path(s) (same pattern as the existing `open`
wrapper in `fs.quanta`) and returns the raw syscall result (0 = ok, `-errno` =
failure).

## Critical fix: dispatch collision

The `file_` builtin block dispatches on the **6th character** of the name
(`nm+5`). For `file_chdir`/`file_rename`/`file_rmdir` that 6th char is `c`/`r`/`r`
— which **collide** with `file_close` (`c`) and `file_read` (`r`). A naive single
char check (`c5=='d'/'n'/'i'`) would have silently routed `rmdir`→`read`,
`chdir`→`close`, returning garbage (`-90` / ENAMETOOLONG during testing). Fixed
by doing **full-name matching** for those three BEFORE the single-char branches.

## Verification

- **Fixpoint:** gen1==gen2==gen3 byte-identical, md5
  `463c47c91485efb3cc6623f103b0f3fc`.
- **Gate:** functional **162/162** (incl. new `fs_ops_test.quanta` rc=0),
  stdlib 7/7, multi-TU 3/3, all 11 layers GREEN.
- **End-to-end** (`fs_ops_test.quanta` rc=0): mkdir → open+write+close →
  stat → rename → unlink → rmdir → chdir, all returning success; temp dir
  fully cleaned up.
- Pre-existing `std_fs_test.quanta` (rc=9) still passes.

## Scope note

Compiler-core change (emitter `file_*` dispatch) + stdlib wrapper addition. The
compiler's self-compilation is unaffected, so the fixpoint md5 differs only by
the new code (not a regression).

## Next

0.0.130 — extern-C variadic (`printf(fmt, ...)` modeling).
