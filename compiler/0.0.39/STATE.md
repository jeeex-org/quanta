# Quanta 0.0.39 — generic syscall family

## What
Added a GENERIC raw-syscall builtin:
- `syscall(num, a, b, c, d, e, f)` — any arity 1..7.
- Reloads each arg vreg from its spill home directly into the exact
  syscall-ABI register (rax=num, rdi=a, rsi=b, rdx=c, r10=d, r8=e, r9=f).
  Correctly uses r10 (not rcx) as the 4th syscall arg, and pulls arg6 from
  its home (IR_CALL places it on the stack).
- `syscall3` retained for back-compat (std/crypto uses it).

## Why the spill-home loader (not a register shuffle)
syscall ABI: 4th arg = r10, 6th = r9. IR_CALL loads args into
rdi/rsi/rdx/rcx/r8/r9 + stack. A pure shuffle can't reach r10 (it's rcx in
IR_CALL's layout) and can't recover arg6 (on the stack). Reloading from spill
homes sidesteps both. Does NOT call flush_all() again (IR_CALL already did).

## Test
- test_suites/codes/syscall_test.quanta: 1-arg getpid(39), 3-arg write(1),
  4-arg getrandom(318). exit(3). Added to EXPECTED.tsv.

## Gate
77/77 PASS, 0 fail (was 76/76). Self-host fixed point 1200128 (3-stage).
Bootstrap saved: bootstrap/qc-bootstrap-0.0.39.
