# Quanta Memory-Safety Argument (v0.0.53)

> Companion to `docs/SAFETY_MANUAL.md` (§6.3) and `docs/SECURITY_TOOLING.md`
> (§6). This document states, rigorously and honestly, what memory-safety
> property Quanta's native compiler currently HAS, HOW it is enforced, and
> what remains to reach a qualification-grade (ISO 26262 / IEC 61508) claim.
>
> Standard: this follows the shape of a **software safety argument** (a
> structured claim → evidence → assumption chain), not a formal proof.

Last updated: 2026-08-17. Compiler: 0.0.53.

---

## 1. Claim

**C1 (enforced, fail-closed):** The Quanta native compiler, and the
binaries it emits, do not fail silently on out-of-contract memory
operations. On overflow, out-of-bounds access, OOM, or buffer exhaustion,
the relevant process TERMINATES with a defined status — it does not
corrupt memory and continue.

**C2 (enforced, bounded):** The compiler's own working buffers are
size-capped; an over-large input or program triggers a clean error exit
(`exit(1)` / `exit(17)`), not an out-of-bounds write.

**C3 (NOT claimed):** Quanta does NOT offer *compile-time* memory safety.
A program can still request an operation the runtime trap will reject; the
language provides no static proof that such operations are absent. This is
the gap that Stage-6 borrow checking would close (SAFETY_MANUAL §6.3).

---

## 2. Evidence (what was actually run, this session)

| ID | Test | Result | Interpretation |
|----|------|--------|----------------|
| E1 | Valgrind `--leak-check=full` on `qc` self-compile | **0 errors, 0 leaks** | Compiler's own memory use is clean (no UB in the compiler). |
| E2 | Valgrind on emitted array program (`[1..5]` sum) | **0 errors, 0 leaks** | Quanta-emitted code is memory-safe under Valgrind. |
| E3 | Emitted OOB access `a[99]` on 3-elem array | **rc=132 (SIGILL trap)**, Valgrind **0 errors** | Bounds trap fires; no corruption. Fail-closed. |
| E4 | 15,000-iter fuzz of `qc` with garbage input | **0 crashes** (rc∈{1,16,17}) | Compiler is fail-closed on arbitrary input. |
| E5 | `eb`/`ei`/`eq` guarded by `CODE_CAP` (exit(1)) | self-host clean; guards unreachable for normal input (IR_CAP binds first at exit(17)) | Defense-in-depth; primary boundary is E6. |
| E6 | 60k-function input → `exit(17)` (IR/token overflow) | clean exit, no SIGSEGV | Primary reachable memory boundary is fail-closed. |

E1–E3 were run 2026-08-17 against `compiler/0.0.53/bin/x86/qc`.

---

## 3. Mechanism → Claim trace

| Mechanism | Enforces | Claim |
|-----------|----------|-------|
| Integer overflow → `ud2` (SIGILL rc=132) | C1 | Verified E3 (via overflow/bounds trap) |
| Array OOB → bounds-trap `ud2` (SIGILL rc=132) | C1 | Verified E3 |
| `mmap` failure → `exit(1)` (was SIGSEGV 139) | C1 | Verified 0.0.49 (ulimit -v → rc=1) |
| `CODE_CAP`/`DAT_CAP` write guards → `exit(1)` | C2 | Verified E5 (self-host clean) |
| IR/token buffer cap → `exit(17)` | C2 | Verified E6 |
| `unsafe{}` opts OUT of traps (audit-counted) | C3 context | Parity with Rust unsafe; documented |

---

## 4. Assumptions (must hold for C1/C2 to be true)

**A1.** The hand-written emit paths (`emitter.quanta`, `codegen.quanta`,
`elf.quanta`, `objfmt.quanta`) write only within their `mmap` regions for
all *valid* inputs. For *invalid* inputs, the parse/scan/funcscan phases
reject before emission (error rc=7) or the buffer caps (E5/E6) abort.

**A2.** The `mem_store`/`mem_load` host intrinsics (the only raw-pointer
writes) are correct. These are the single trusted computing base for all
emission; a bug here would undermine C1/C2. (No sanitizer currently
instruments them — see §6.)

**A3.** The golden `bin/x86/qc` is trusted. The
self-host fixed-point (committed bin/x86/qc → 0.0.69 source → qc, byte-identical,
and to a 2nd-stage rebuild) shows the CURRENT compiler
reproduces itself; it does not independently prove A2 (that needs #2).

---

## 5. What is OUT OF SCOPE (the orange, not green)

- **Compile-time memory safety** (C3 not claimed). Requires Stage-6 IR-level
  borrow checking (unique/borrow per vreg) — NOT built.
- **ASan / UBSan / MSan instrumentation of `qc` itself.** These require a
  C/Clang compilation path for the compiler. Quanta is self-hosted (no C
  source), so sanitizers cannot instrument `qc` today. Deferred until a
  C/LLVM emit path exists (which is itself a #2-adjacent capability: it
  would provide a *second* implementation to cross-check against).
- **Formal proof of A1/A2.** The emit paths are correct by construction +
  Valgrind + fuzz, not by proof.

---

## 6. Path to GREEN (what would make #1 a qualification-grade claim)

1. **Stage-6 borrow checking** (IR-level ownership) → closes C3; makes
   memory safety a compile-time guarantee, not a runtime trap.
2. **Second implementation / C backend** (#2) → provides independent
   cross-check of A2; also unlocks ASan/UBSan/MSan on the compiler.
3. **Sanitizer CI** (once #2 lands) → `qc` built under ASan+UBSan+MSan,
   0 errors required for promotion.

Until 1–3, #1 is **HARDENED (fail-closed, Valgrind-clean, fuzz-proven) but
NOT PROVEN.** This is the honest basis for the 🟡 status in the standards
scorecard.

---

## 7. Version

Argument corresponds to compiler `0.0.53` (commit `dd79554`).
Update on any memory-safety-relevant change; re-run E1–E6 and record
results.
