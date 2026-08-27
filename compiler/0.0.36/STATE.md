# Quanta compiler 0.0.36 — STATE

## What this version is
Continuous from 0.0.35 (split monolith). Source is identical modules to 0.0.35
EXCEPT the documented #1 bug fix below. Single x86-only self-hosting file set
(src/x86/*.quanta, no ARM emitter).

## 0.0.36 scope: fix bugs (part 1)
- #1 FIXED (verified): `lib/std/vec.quanta` defined `vec_set`/`vec_get`, but the
  compiler reserves those exact names as SIMD f64-lane builtins
  (features.quanta:403-404, emitter.quanta:556-567). The SIMD `vec_set(ptr,lane,val)`
  writes to `ptr + lane*8`, dropping the `+16` header offset, so lib calls were
  intercepted and stored elements at v+0,v+8,... overwriting capacity/length
  header words -> vec_push silently no-opped. Renamed to `vec_put`/`vec_at`.
  Verified: vec_new/push/get/len all correct (len 8->9->10, get(8)=99, get(9)=100).
- #2 OPEN (deferred to 0.0.37): register-allocator / comparison-under-pressure
  bug. `if <call-return> == <imm>` fails when preceded by >=8 calls of the same
  pattern. The call-return VALUE is correct but the `==` comparison reads a
  clobbered operand (home/spill slot). Localized to allocator spill/live-range
  handling (emitter.quanta:aphys/afree/adistinct/flush_all). Frame is correctly
  sized for spill slots, so root cause is subtle. std_vec_test exits 8 (expect 9).
- printi/println length bug OPEN (deferred to 0.0.38): strace shows
  `write(1,"7",17)` — correct string, garbage rdx length. Lives in
  emitter.quanta:673-758 (rr(2,8) length handling). Does not affect exit-code gate.

## Gate status (0.0.36)
71/74 (unchanged from 0.0.35). The 3 "failures" are: std_vec_test (rc 8, expects
9 — #2 allocator bug), std_fs_test (rc 9, expects 10 — test asserts 10 checks but
only 9 exist; lib is correct), and 2 pre-existing SIGILL tests (rc 132, in
EXPECTED.tsv). None are regressions from 0.0.35.

## Build
bootstrap/qc-bootstrap-0.0.35 -> qc_boot -> qc_self -> qc (fixed point: 1183744 bytes).
## Next
0.0.37 = bug #2 (allocator comparison-under-pressure).
0.0.38 = printi length bug.
0.0.39 = test_suite.
