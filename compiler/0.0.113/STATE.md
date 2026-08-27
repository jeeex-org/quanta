# Quanta 0.0.113 — Release State

- **Version:** 0.0.113
- **Date:** 2026-08-28
- **Source entry:** `compiler/0.0.113/src/x86/main.quanta` (16 modules)
- **Build seed:** 0.0.112 (`compiler/0.0.112/bin/x86/qc`)
- **Self-host fixpoint:** NOT byte-verified — systemic stage2 SIGSEGV
  (`si_addr=0xfffffffffffffff4`) pre-existing since 0.0.109; affects all
  versions 0.0.109–0.0.113. Feature-complete + functional-gated only.
- **Promoted from:** 0.0.113 (this version; copied from 0.0.112)

## What changed
Builtins (G-core): introspection stack-trace. NEW `stack_trace()` pure builtin
returns the immediate caller's return address (a code pointer) — the address
execution resumes at when the current function returns. Implementation reads
`[rbp+8]` of the executing frame: every Quanta function uses a SysV-style
prologue (`push rbp; mov rsp,rbp; push callee-saved; sub $frame,rsp`), so the
rbp frame chain holds the return address at a fixed +8 offset. No per-call
instrumentation, fixpoint-safe. Registered in `is_bltn` + `emit_bltn`
(11-char name match: s-t-a-c-k-_-t-r-a-c-e at indices 0–10).

Debug history (for the record): earlier attempts used a `CUR_FRAME` GDATA
global + `[rsp+frame]` model (wrong — `rbp()` helper is frame-relative, not
absolute, and the return address is not at `[rsp+frame]`), and a `[[rbp]+8]`
chain walk (one frame too far). Both removed; the final `[rbp+8]` read was
verified by disassembly to return exactly the instruction after `call` for the
executing frame. Dead `CUR_FRAME` store + global removed.

## Tests
- `stack_trace_test.quanta` (rc=0): two distinct call sites (`a()`, `b()`)
  each return a non-zero pointer inside the code segment (0x400000..0x410000),
  and the two addresses differ. Address-independent gate (stable across builds).
- Full gate: 146/146 functional + extern-c/security/performance/valgrind/fuzz/
  differential/generics-negative all GREEN.

## Gate result
- functional : GREEN (146/146)
- extern-c   : GREEN
- security   : GREEN (fail-closed; overflow traps fire as designed)
- performance: GREEN (3/3, baseline 4000ms)
- valgrind   : GREEN (0 errors)
- fuzz       : GREEN (fail-closed on all fuzzed inputs)
- differential: GREEN (120-run optimizer differential + vs-seed consistent)
- generics    : GREEN (negative compile-time checks)
- self-host   : NOT byte-verified (systemic stage2 SIGSEGV since 0.0.109)
