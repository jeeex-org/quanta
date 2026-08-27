# Quanta 0.0.40 — time builtins

## What
Added 4 time builtins:
- `clock_gettime(clk_id, ts_ptr)`: sc 228
- `gettimeofday(tv_ptr, tz_ptr)`: sc 96
- `nanosleep(req_ptr, rem_ptr)`: sc 35
- `sleep(sec)`: internal mmap(16) -> fill {sec,0} -> nanosleep -> munmap.

## Bugs hit & fixed (this version)
1. Name-length checks in is_bltn/emitter: clock_gettime is 13 chars (not 12),
   gettimeofday is 12 (not 13). Miscounted byte positions in the r8(src+nm+N)
   chain caused "undeclared function". Fixed by checking key positions only.
2. Store encoding: `mov [rax], rdx` needs `eb(16)` (48 89 10), not `eb(1)`
   (which emits mov [rcx], rax). `mov [rax+8], rcx` needs `eb(8)` (1-byte
   disp8), NOT `ei(8)` (which writes a 4-byte imm32, corrupting the byte
   stream and masking the following nanosleep).
3. sleep's internal mmap result kept in rbx across the nanosleep syscall
   (kernel preserves rbx; no live vregs in it after IR_CALL flush_all).

## Test
- test_suites/codes/time_test.quanta: clock_gettime/gettimeofday return 0,
  gettimeofday tv_sec nonzero, sleep(1) returns 0, nanosleep(0.2s) returns 0.
  exit(6). Registered in EXPECTED.tsv.

## Gate
78/78 PASS (was 77/77). Self-host fixed point 1216512. Bootstrap saved.
