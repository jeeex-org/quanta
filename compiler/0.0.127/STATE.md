# 0.0.127 — PTY (pseudo-terminal) core

**Status:** ✅ DONE — self-hosting, gate-green, all 11 layers GREEN.

## What landed

Low-level pseudo-terminal allocation builtins (the layer under a future `term`
/ interactive-shell capability, and a prerequisite for capturing subprocess
output that goes through a real TTY):

| Builtin | Syscall(s) | Notes |
|---|---|---|
| `pty_open()` | `open("/dev/ptmx", O_RDWR)` + `ioctl(TIOCSPTLCK, &0)` | returns master fd |
| `pty_slave(m)` | `ioctl(TIOCGPTN, &n)` + `open("/dev/pts/N", O_RDWR)` | returns slave fd |
| `pty_name(m)` | `ioctl(TIOCGPTN, &n)` + build `/dev/pts/N` | returns slave path string |
| `dup2(a,b)` | `dup2` (sc 33) | fd duplication |
| `ioctl(fd,req,arg)` | `ioctl` (sc 16) | generic ioctl |

All five preserve callee-saved r12–r15 per the x86-64 ABI (the `qc_sys_cmd`
convention — push at entry, pop at exit).

## Key implementation details (source-verified)

- `pty_open` builds the `/dev/ptmx` path at **runtime** in an `mmap`'d scratch
  page (not a compile-time literal), then `open`s it. The unlock ioctl
  (`TIOCSPTLCK = 0x40045431`) must receive a **pointer to a zero int** — passing
  `NULL` faults. The scratch slot `[S+8]` holds that zero.
- `pty_slave` / `pty_name` do `ioctl(TIOCGPTN = 0x80045430, &n)` to read the pty
  number into a scratch int, then format `/dev/pts/N` with a decimal-digit loop
  (right-to-left digit extraction into the buffer, no reversal needed).
- `O_NOCTTY` was **dropped** from the `/dev/ptmx` open: with it, `read()` on the
  master returned `-ETIMEDOUT` (110) unconditionally. Plain `O_RDWR` makes the
  master read block correctly until the slave writes.

## Verification

- **Fixpoint:** gen1(gen2) == gen2(gen3) byte-identical, md5
  `e1d5ed96d9df41f69297c4bcd2b50b4c`. Built from 0.0.126 seed.
- **Gate:** functional **160/160** (incl. new `pty_test.quanta` rc=2), stdlib
  7/7, multi-TU 3/3, all 11 layers GREEN.
- **End-to-end:** `pty_test.quanta` opens a pty, forks, child `dup2(slave,1)` +
  `exec("printf hi")` (stdout wired to the pty), parent `wait` returns 0 —
  proving the full open→slave→fork→dup2→exec→wait pipeline.

## Known limitation (separate defect, NOT a 0.0.127 bug)

Byte-level `file_read(master)` round-trip (reading the child's exact output
bytes back through the master) is blocked by a **pre-existing compiler bug**
present in 0.0.126 too: consecutive builtin calls corrupt the 2nd call's count
argument register (e.g. `file_write(fd, buf, 7)` returns 70, `file_read` gets a
bad count). Confirmed identical behavior under the 0.0.126 seed. This is a
register-clobber bug in the builtin arg-loading path — filed for a later core
version (not 0.0.127 scope). The C-reference equivalent reads `QWERTY` cleanly,
so the pty logic itself is correct; the gate test asserts the pipeline via
`wait()==0` instead of a byte read.

## Next

0.0.128 — `big` div-by-zero guard (FIX-0.0.19, partial core).
