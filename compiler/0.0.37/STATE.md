# Quanta 0.0.37 — bug fixes (crypto syscall3 + test-expectation corrections)

## Source vs 0.0.36
Identical EXCEPT the addition of the `syscall3(num, a, b, c)` builtin:
- `features.quanta` `is_bltn()`: registered `syscall3` as a known builtin (nl==8).
- `emitter.quanta` `emit_bltn()`: emits the raw 3-arg Linux syscall.
  IR_CALL arg load places rdi=num, rsi=a, rdx=b, rcx=c. The syscall
  instruction wants rax=num, rdi=a, rsi=b, rdx=c, so we shuffle via rr():
  rr(0,7) rax=rdi; rr(7,6) rdi=rsi; rr(6,2) rsi=rdx; rr(2,1) rdx=rcx; sysc().

## Why syscall3 was needed (REAL bug)
`lib/std/crypto.quanta` calls `syscall3(318, buf, n, 0)` for getrandom (CSPRNG).
The compiler had no `syscall3` builtin -> `std_crypto_test` failed to COMPILE
("call to undeclared function: syscall3"). This was a genuine missing builtin.
Now fixed: std_crypto_test compiles and passes (rc=3, matches EXPECTED).

## Test-expectation corrections (NOT compiler bugs)
Two gate "failures" were miscounts in the test source, not compiler defects:
- `std_vec_test.quanta`: source has 8 `ok = ok + 1` increments (program exits 8),
  but EXPECTED.tsv said 9. Corrected EXPECTED 9->8. (Investigated earlier as
  "bug #2"; proven to be a test miscount, not an allocator defect — 0.0.36
  already produced correct results on every allocator reproducer.)
- `std_fs_test.quanta`: source has 9 `ok = ok + 1` increments (program exits 9),
  but EXPECTED.tsv said 10 (author comment "3+3+4=10" but only 9 checks coded).
  Corrected EXPECTED 10->9. Verified via per-check trace (1 2 3 4 5 6 7 8 9).

## Gate result (0.0.37)
73 PASS / 0 FAIL. (0.0.36 baseline was 71/2: std_crypto_test COMPILE_FAIL +
std_fs_test rc=9/exp=10.) Both resolved.

## Self-host
3-stage fixed point: 1187840 / 1187840 / 1187840 (vs 0.0.36's 1183744; larger
only due to the added syscall3 builtin). bootstrap/qc-bootstrap-0.0.37 saved.

## Next
0.0.38: printi/println garbage write-length bug (strace: write(1,"7",17) —
content correct, rdx (length) garbage). Lives in emitter.quanta printi/println.
