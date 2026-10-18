# A33 (`loop_depth`) — the capability already exists; the guard is the defect

Answer to the phase-2 brief's question: *"the design you propose for the `unchecked`
region (backlog #20) instead of deleting the trap."* Design + measurement only; no
compiler change in 0.0.249.

Measured on `compiler/0.0.249` (`VERSION` 0.0.249), instrument
`scripts/bench_instr.sh` / `objdump` on `--emit-obj` output.

---

## 1. The finding: Quanta already has the escape hatch, and it is per-operation

`docs/plans/language-capabilities.md` #20 reads *"None: the only ways to avoid the
trap today are to not use integers or to accept the cost."* **That is wrong.**
Every trap emitter is already gated on `ir_unsafe`:

```
emitter.quanta:250  fn ovf_trap_emit(ii) { if ovf_trap==1 && r8(ir_unsafe+ii)==0 { ... jno; ud2 } }
emitter.quanta:256  fn shl_trap_emit(ii) { if ovf_trap==1 && r8(ir_unsafe+ii)==0 { ... cmp; jb; ud2 } }
emitter.quanta:322  fn idx_trap_emit(ii) { if ovf_trap==1 && r8(ir_unsafe+ii)==0 { ... cmp; jb; ud2 } }
```

`helpers.quanta:420` writes `ir_unsafe + i = unsafe_depth` for **every IR op emitted
inside a `unsafe { }` block** (the `unsafe_depth` counter is maintained by
`parse.quanta:569`). So `unsafe { }` suppresses the integer overflow trap, the
shift-count trap **and** the index trap, at *operation* granularity — not
block-of-loop granularity. It is not hypothetical: the compiler's own
`compute_magic()` is wrapped in `unsafe { }` precisely because its signed-division
magic-number recovery does deliberate 64-bit wraparound.

## 2. Measured: what the escape hatch buys

Same probe, one line of source different (`unsafe { s = s + i * 7 }` instead of
`s = s + i * 7`), loop `while i < 100 { ...; i = i + 1 }`:

| | loop body | `ud2` in `main` | exit |
|---|---|---|---|
| without `unsafe{}` | **39** | **3** | 0 (34650 correct) |
| with `unsafe{}` on the arithmetic statement | **35** | **1** | 0 (34650 correct) |

**-4 instructions (-10.3 %) of the loop body, and 2 of the 3 traps gone.** The one
remaining trap is `i = i + 1`, which is outside the `unsafe` block — i.e. the
suppression is correctly scoped to exactly the operations the author wrapped, which
is the whole point of doing it per-operation rather than per-loop.

The audit's `regpressure` figure (66 of 310 loop instructions, 21 %) is the size of
the prize when the *whole* loop body is wrapped, and it is available today.

## 3. So what is actually wrong

1. **`loop_depth` is dead code that lies.** `codegen.quanta:1446` declares
   `let loop_depth = 0`; nothing ever increments it; four sites read
   `if loop_depth == 0 { ovf_trap_emit(ii) }`, so the condition is always true and
   the guard can never suppress anything. It reads as "traps are skipped in loops",
   which is not a behaviour the compiler has. **Delete the four guard conditions
   and the declaration** — that is honest cleanup, not an optimisation, and it
   changes no emitted byte (the condition is constant-true, so removing it is a
   no-op on codegen — verify that with the byte-identity check).
2. **Nothing tests the escape hatch.** There is no gate row asserting that
   `unsafe { }` actually removes the trap for `add`/`sub`/`mul`/`neg`, so the
   capability can regress silently — and it is load-bearing (the compiler's own
   `compute_magic` depends on it; if the gate flipped, the self-host would trap
   during its bootstrap). This is the *real* A33 defect: a capability with no test
   is a capability that is not known to exist.
3. **The name.** The entry proposes an "`unchecked` region". The existing construct
   is `unsafe { }`, which is a stronger word for a narrower claim. Two options, and
   the owner should choose deliberately:
   - keep `unsafe { }` as the only spelling (simplest; it is already in the spec,
     the parser, the IR and the compiler's own source); or
   - add `unchecked { }` as a **second spelling of the same IR flag**, for the
     narrow arithmetic case, so "this arithmetic cannot overflow" does not have to
     be spelled with a word that also covers raw syscalls and `$$(cmd)`. This is a
     lexer + parser change and **no codegen change at all** if it reuses
     `unsafe_depth`.

## 4. Proposed order of work (its own version, per the standing policy)

1. **Test the capability first** — that is the policy's "capability ships first"
   applied honestly, because the capability is already shipped with no proof.
   Red-first row: a loop whose arithmetic overflows inside `unsafe { }` must NOT
   raise SIGILL (exit 0), and the same loop outside `unsafe { }` MUST raise SIGILL
   (exit 132). Both directions are needed; a one-sided test passes if the trap is
   removed globally, which is the failure mode being guarded against. Plus a
   byte-scanning stage asserting the `ud2` count inside `main` drops when the
   `unsafe { }` is added (the `marshal-guard` pattern from 0.0.249).
2. **Delete the dead `loop_depth` guard** in the same version, with the byte
   identity of all 239 gate rows re-checked (it must be **239/239 identical** —
   a constant-true condition cannot change codegen; if any row differs, the guard
   was not constant-true and the change is not the cleanup it claims to be).
3. Only then consider whether `unchecked { }` earns a second spelling.

**What must NOT happen** (and is why A33 stayed open through this phase): wiring
`loop_depth` up so the trap is skipped inside loops. That silently removes overflow
detection from every loop in every program — the class of change this campaign
forbids, and the opposite of what the guard's author intended. The trap stays on by
default; the author opts out per operation, as `compute_magic` already does.
