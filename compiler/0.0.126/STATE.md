# Quanta 0.0.126 — Release State

- **Version:** 0.0.126
- **Date:** 2026-08-30
- **Source entry:** `compiler/0.0.126/src/x86/main.quanta` (16 modules)
- **Build seed:** 0.0.125 (`compiler/0.0.125/bin/x86/qc`)
- **Fixpoint:** gen1 → gen2 → gen3 byte-identical. md5 `2504e5b10d4fcbe812199b6f2e56679b` (qc_self == qc_gen3).
- **Gate:** functional 159/159 (incl. new `process_test.quanta` rc=4), stdlib 7/7, multi-TU 3/3, all 11 layers GREEN (valgrind/security/fuzz/differential/generics/stdlib/multi-tu).

## What changed (vs 0.0.125)
`process` core — low-level POSIX process builtins, emitted as raw Linux syscalls:

| Builtin | Syscall | Behavior |
|---|---|---|
| `fork()` | 57 | returns pid: 0 in child, child pid in parent, -errno on failure |
| `exec(cmd)` | 59 | replaces image with `/bin/sh -c <cmd>` (reuses `qc_sys_cmd` child marshaling: mmap scratch, build `"/bin/sh","-c",cmd` argv, execve). No return on success; `exit(127)` on failure |
| `wait(pid)` | 61 (wait4) | reaps child, returns `WEXITSTATUS = (status>>8)&0xff` (matches `qc_sys_cmd`); signaled child → 0 (signal is in low 7 bits) |
| `kill(pid,sig)` | 62 | sends signal; 0 ok, -errno on failure |

All four `push`/`pop` callee-saved r12–r15 (x86-64 ABI) — required because codegen can hold live values there across a builtin call (proven by `qc_sys_cmd`). The prior WIP left these OUT plus a `wait()` rax-clobber bug (trailing `munmap` zeroed rax) — both fixed.

## Critical encoding notes
- `exec` builds its argv in an mmap'd scratch page (4096 B): `"/bin/sh"` @ +16, `"-c"` @ +32, argv array `[S+16, S+32, cmd+8, 0]` @ +1024. `wmi` writes the 32-bit C-string literals; `stx` writes the 64-bit pointers.
- `wait` reads the 32-bit `wait4` status via `ldx(6,12,0)`, computes `WEXITSTATUS`, preserves it in r13 across the `munmap` of the status slot, then restores rax.
- `fork`/`kill` are thin syscall wrappers after the r12–r15 save/restore.

## Files touched
- `src/x86/features.quanta` — 4 new `is_bltn` recognizer entries (fork/exec/wait/kill).
- `src/x86/emitter.quanta` — 4 new `emit_bltn2` bodies (after the `now()` block, before `syscall3`).
- `test_suites/codes/process_test.quanta` — new gate test (rc=4).
- `test_suites/EXPECTED.tsv` — new row `process_test.quanta\t4`.

## Known constraints
- `exec` runs `/bin/sh`; does not take a raw argv array (QUANTA array-of-strings layout is not yet a first-class execve interface). This is the minimal, proven path; a typed `execv(path, [..])` can be added later.
- `wait` returns `WEXITSTATUS` only (not raw status); a `wait_raw` is not provided. Consistent with `qc_sys_cmd`'s contract.
- Process builtins are low-level; no stdio redirection (that requires the PTY layer at 0.0.127).

## Next
0.0.127 PTY layer (partial core) — needs 0.0.126 process + pty-alloc (posix_openpt/ioctl/grantpt/unlockpt).
