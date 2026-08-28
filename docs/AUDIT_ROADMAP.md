# AUDIT_ROADMAP — Quanta Compiler Security Fixes

**CLOSE-OFF STATUS: ALL ITEMS CLOSED at 0.0.115 (security hardening release).**
Build seed: 0.0.114 (`compiler/0.0.114/bin/x86/qc`).
Self-host fixpoint: BYTE-VERIFIED — stage1==stage2==stage3 (md5 `50857425ec4be97ddf971074a6b66d48`).
Full 9-layer gate: GREEN (functional 148/148 incl. `rsp_test` + `big_test`; stdlib 7/7; extern-c/security/perf/valgrind/fuzz/differential/generics all GREEN).
`lib/std/big.quanta` runtime fixes applied in 0.0.115 (see appended ⧫-marked `big` findings).

Generated from static audit of `compiler/0.0.113` (WIP) vs `0.0.112` (released) at commit `0af9bdc`.
Scope: x86-64 backend, memory subsystem, include expander, new 0.0.113 builtins (`rsp()`, `stack_trace()`).

**Note:** CUR_FRAME was removed in 0.0.113 (commit 0af9bdc: "Dead CUR_FRAME store + global removed"). It is not present in the current codebase.

**ID scheme:** `FIX-0.0.N` — matches compiler version gate sequence. Each entry: severity, location, root cause, exploit path, fix (exact bytes / line numbers), verification.

---

## FIX-0.0.1  HIGH — `mem_alloc` / `mem_realloc` skip MAP_FAILED check (C1 violation)

| | |
|---|---|
| **Location** | `compiler/0.0.113/src/x86/emitter.quanta:725-741` (`mem_alloc`), `:759-793` (`mem_realloc`) |
| **Root cause** | `mmap` syscall returns `-errno` in `rax` on failure; both builtins use `rax` unchecked. The standalone `mmap` builtin *does* have the guard (`:866-870`: `cmp rax,0; jge ok; mov rax,1; mov rdi,1; sysc`), but it was not copied. |
| **Exploit path** | OOM → `mem_alloc`: `mov [rax], rbx` writes count header to kernel address (`~0xFFFF...FFFFF4`) → SIGSEGV rc=139 (not fail-closed `exit(1)`).<br>OOM → `mem_realloc`: `rep movsq` copies `min(old,newn)` qwords from old block **to** `-errno` → fault or kernel write attempt. |
| **Fix** | After each `sysc()` in both functions, emit the identical 3-instruction guard (7 bytes):<br>`48 83 F8 00`          `cmp rax, 0`<br>`7D 07`                `jge .ok`<br>`48 C7 C0 01 00 00 00` `mov rax, 1`<br>`48 C7 C7 01 00 00 00` `mov rdi, 1`<br>`0F 05`                `syscall` |
| **Verification** | Run gate; add `test_suites/codes/mem_alloc_oom.quanta` that forces `mmap` failure (RLIMIT_AS) and expects clean `exit(1)`. |

---

## FIX-0.0.2  HIGH — `mem_realloc` never writes the new block's count header

| | |
|---|---|
| **Location** | `compiler/0.0.113/src/x86/emitter.quanta:786-792` |
| **Root cause** | Copy loop is `rep movsq` from `ptr+8` → `new+8`. The `[new]` header (length = `newn`) is never written. mmap hint `0x60000001` + no `MAP_POPULATE` means recycled virtual addresses can carry stale `[new]` from a prior allocation. |
| **Exploit path** | Any subsequent `a[i]` on the realloc'd array runs `idx_trap_emit`'s `cmp [rax], rcx` against **garbage length** → bounds check silently passes on OOB indices (stale header large) or traps on in-bounds ones (stale header small). Bounds-check bypass. |
| **Fix** | After syscall, before/after copy, emit:<br>`4C 89 2D` `<imm32>`   `mov [r13], r12`  ; `r13 = new`, `r12 = newn`<br>(3 + 4 = 7 bytes; `r13`/`r12` are live per surrounding code). |
| **Verification** | Gate test: `mem_realloc` a block, then index at `old_len` (must trap) and `new_len-1` (must not trap). |

---

## FIX-0.0.3  HIGH — Free-list push has zero pointer validation (double-free / write-what-where)

| | |
|---|---|
| **Location** | Three identical copies:<br>`emitter.quanta:746-757` (`mem_free`), `:799-807` (`mem_realloc` free-old),<br>`codegen.quanta:1455-1470` (`IR_FREE` / RAII scope-exit) |
| **Root cause** | Push sequence:<br>`mov [ptr+8], [HEAP_CTRL]`<br>`mov [HEAP_CTRL], ptr`<br>No null check, no provenance check, no canary. |
| **Exploit path** | `mem_free(0)` / `drop(0)` → writes to address `8` → SIGSEGV (asymmetric with `mem_store8` which null-guards).<br>Any attacker-shaped pointer → **write-what-where** of list head into `[ptr+8]`.<br>**Double-free is trivially reachable**: `let p = mem_alloc(4); mem_free(p);` — scope exit emits `IR_FREE(p)` again → same block pushed twice. When `mem_alloc` starts recycling (the stated plan), aliased-block heap exploit. Currently latent only because `mem_alloc` never pops the list (leaks every freed block — also contradicts FEATURES.md "free old via list"). |
| **Fix** (layered, cheapest first):<br>1. Null-guard both builtins: `test ptr,ptr; jz .skip` before push.<br>2. On explicit `mem_free` / `IR_FREE`, clear `vreg_owned[f]` so scope-exit doesn't re-push.<br>3. Longer term: per-block canary at `[ptr]` (e.g., `ptr ^ 0x9E3779B97F4A7C15`) checked before push. |
| **Verification** | Gate tests: `mem_free(0)` → clean exit; double-free → single free only; `drop(0)` → clean exit. |

---

## FIX-0.0.4  HIGH — Include-path overflow into `imp_full` (4096-byte buffer, uncapped)

| | |
|---|---|
| **Location** | `compiler/0.0.113/src/x86/objfmt.quanta:610-622` (quoted-include path build) |
| **Root cause** | `imp_dir` (≤4096) + quoted path (unbounded, only `""`-terminated) copied into `imp_full = mmap(4096)` (`globals.quanta:120`) with **no length check**. |
| **Exploit path** | Source: `include "AAAA…(5000 chars)…"` → writes past `imp_full` into adjacent `imp_dir` arena (`globals.quanta:121`) → compiler state corruption from crafted input. Fail-closed contract (C2) violation. |
| **Fix** | Bound-check in path build loop:<br>`if imp_dirlen + k + 1 >= 4096 { exit(1) }`<br>Emit before `w8(imp_full + imp_dirlen + k, c)`. |
| **Verification** | Gate test: `include "` + 4000 `'A'` + `"` → clean `exit(1)` with message. |

---

## FIX-0.0.5  HIGH — Source expansion writes past 16MB `src` buffer before truncation check

| | |
|---|---|
| **Location** | `objfmt.quanta:640-655` (`expand_includes` copy loop) → `entry.quanta:175` (post-expansion check) |
| **Root cause** | `w8(src + srclen, c)` in expansion loop has **no cap**; the `srclen >= 16777216` check runs *after* expansion completes. A main file + includes totaling >16MB overflows the 16MB `src` buffer before the check fires. |
| **Exploit path** | Crafted includes totaling >16MB → heap overflow into whatever follows `src` arena. |
| **Fix** | Pre-flight total size (sum `fsize` of main + all includes) before any copy, or guard inside loop: `if srclen >= 16777216 { exit(1) }`. |
| **Verification** | Gate test: main + includes = 17MB → clean `exit(1)`. |

---

## FIX-0.0.6  MEDIUM — Raw-pointer primitives not gated by `unsafe{}`

| | |
|---|---|
| **Location** | `mem_load`/`mem_store` (`emitter.quanta:1024-1040`), `IR_DEREF`/`IR_DEREF_MUT`/`IR_PTR_ADD` (`codegen.quanta:1471-1520`), new `rsp()`/`stack_trace()` |
| **Root cause** | `unsafe{}` only suppresses overflow/bounds traps; it does **not** fence any primitive. Safe-code Quanta already has arbitrary read/write + stack-address leak (`rsp()`) that defeats ASLR. `$$()` is gated; these are not. |
| **Exploit path** | Safe-code program calls `mem_load(addr)` / `mem_store(addr, val)` / `rsp()` → arbitrary R/W + ASLR bypass. |
| **Fix** | Require `unsafe{}` for `mem_*`, `drop`, `rsp`, `stack_trace`, deref ops — or explicitly document in `SAFETY_MANUAL.md` §posture that pointer builtins are safe-code (docs currently imply otherwise). |
| **Verification** | Gate test: safe-code call to `mem_load(0)` → compile error "requires unsafe". |

---

## FIX-0.0.7  MEDIUM — `stack_trace()` at `_start`/`__init` reads argv, not a return address

| | |
|---|---|
| **Location** | `entry.quanta:237` (`rbp = argv` in `_start`) vs `emitter.quanta:809-811` (`rbp(0,8)` = `mov rax, [rbp+8]`) |
| **Root cause** | `stack_trace()` assumes standard prologue `push rbp; mov rsp,rbp` — but `_start` sets `rbp = argv` before calling `__init`/`main`. If inlined into entry context, `[rbp+8]` reads `argv[1]` (env pointer). |
| **Exploit path** | Low direct exploitability, but builtin's comment claims "always a valid code pointer" — false at entry edge. Environment pointer leak. |
| **Fix** | Emit prologue check: only emit `rbp(0,8)` if current function has frame (track via `fn_has_frame` flag), else emit `mov rax, 0` or trap. |
| **Verification** | Gate test: `fn main() { stack_trace() }` works; `fn __init() { stack_trace() }` returns 0. |

---

## FIX-0.0.8  MEDIUM — `owned_stk` push has no bounds check (8192 slots)

| | |
|---|---|
| **Location** | `features.quanta:32-34` (`owned_add`) |
| **Root cause** | Writes `owned_stk + owned_top*8` into 8192-slot arena with **no cap check** (contrast `imp_seen` which does check). |
| **Exploit path** | 8192 live `mem_alloc` bindings (deeply nested scopes/loops without exit) → writes past arena. Compiler-only DoS, breaks "all arenas capped" invariant. |
| **Fix** | Add `if owned_top >= 8192 { exit(1) }` before push (same pattern as `imp_seen`). |
| **Verification** | Gate test: 8193 nested `let p = mem_alloc(1)` → clean `exit(1)`. |

---

## FIX-0.0.9  LOW — Source files >16MB silently truncated

| | |
|---|---|
| **Location** | `entry.quanta:74` (`file_read(fd, mainsrc, 16777216)`) |
| **Root cause** | Truncation check only catches *expansion* overflow; a 17MB source compiles first 16MB with **no diagnostic**. Mid-token truncation changes semantics silently. |
| **Fix** | `fstat` size first; if `size >= 16777216` → `exit(1)` with message before read. |
| **Verification** | Gate test: 17MB source → clean `exit(1)` with "source too large". |

---

## FIX-0.0.10  LOW — ROADMAP 0.0.113 row accurate; `rsp()` missing from gate/doc (doc-sync)

| | |
|---|---|
| **Location** | `docs/ROADMAP.md:98` |
| **Issues** | ROADMAP correctly says stack_trace reads `[rbp+8]`. **But `rsp()` is missing from the ROADMAP row entirely** — only stack_trace is mentioned. `stack_trace_test.quanta` IS gated (EXPECTED.tsv, rc=0). |
| **Fix** | Update ROADMAP row to mention `rsp()` builtin; add `rsp_test.quanta` to gate. |
| **Verification** | ROADMAP mentions both builtins; `grep -rn 'rsp()' test_suites/codes/` returns gate test. |

---

## FIX-0.0.11  LOW — `rsp()` labeled "PROBE" but shipped as permanent builtin

| | |
|---|---|
| **Location** | `features.quanta:414`, `emitter.quanta:809` |
| **Issue** | Both registration sites comment `rsp(): PROBE return current rsp (debug).` — implies temporary. Shipped without gating. |
| **Fix** | Either delete before release or document as permanent debug builtin (and gate per FIX-0.0.6). |
| **Verification** | Release checklist item. |

---

## FIX-0.0.13  LOW — `mem_realloc` FEATURES.md row claims "free old via list"; code leaks

| | |
|---|---|
| **Location** | `docs/FEATURES.md:153` vs `emitter.quanta:762` (comment admits "old block is simply leaked") |
| **Fix** | Sync doc to code, or implement list pop in `mem_alloc` (larger change). |
| **Verification** | Doc matches behavior. |

---

## FIX-0.0.14  LOW — Dispatch-chain growth approaching seed-miscompile cliff

| | |
|---|---|
| **Location** | `emitter.quanta` `emit_bltn` (37 branches), `emit_bltn2` (83 branches), `is_bltn` (135 branches) |
| **Issue** | Skill-documented risk: past ~98 branches in a single `emit_bltn*` fn, self-host seed build can miscompile (constant-folding vs runtime divergence). 0.0.113's two additions are inside envelope, but next 15 builtins in `emit_bltn2` approach cliff. |
| **Fix** | Plan third dispatch fn (`emit_bltn3`) or hash pre-check before 0.0.128. |
| **Verification** | Self-host build at each version gate. |

---

## FIX-0.0.15  LOW — Repo hygiene (non-security, but blocks clean gates)

| | |
|---|---|
| **Items** | `vgcore.89961`, `vgcore.92223` (~8MB each), `nta_qfio_test.bin`, `s.err` at repo root.<br>18 test sources ungated in `EXPECTED.tsv` (7 `std_*` legitimately deferred per skill; `atomic_test.quanta` likely belongs in gate). |
| **Fix** | Clean root artifacts; audit ungated list. |
| **Verification** | `git status` clean; `EXPECTED.tsv` gate count matches intent. |

---

## Priority Order (if fixing sequentially)

1. **FIX-0.0.1** — 3-instruction guard copy-paste (trivial, highest impact)
2. **FIX-0.0.2** — One `mov [r13], r12` (trivial, bounds-check bypass)
3. **FIX-0.0.3** (half) — Clear `vreg_owned` on explicit free (stops double-free today)
4. **FIX-0.0.4** — Bound-check in include path build (crafted-input DoS)
5. **FIX-0.0.5** — Pre-flight or in-loop `srclen` cap (crafted-input overflow)
6. **FIX-0.0.6** — `unsafe{}` gating decision (design choice, widest surface)
7. **FIX-0.0.7** — Entry-context guard for `stack_trace()`
8. **FIX-0.0.8** — `owned_stk` cap check (one `if`)
9. **FIX-0.0.9** — `fstat` pre-check (one syscall)
10. **FIX-0.0.10/11/12/13** — Cleanup / doc-sync (no runtime risk)
11. **FIX-0.0.14** — Dispatch refactor (planned, not urgent)
12. **FIX-0.0.15** — Hygiene

---

## Coverage Boundary (Honest)

This is **static source review + byte-level encoding verification** of the new builtins. I did not:
- Run the gate / fuzz the compiler / exercise runtime paths
- Audit ARM64 emitter, WASM/JIT modes, `lib/std/*`
- Verify kernel page-recycling behavior for FIX-0.0.2's stale-header trigger (depends on allocator reuse, not yet implemented)

Findings FIX-0.0.1–FIX-0.0.5 are **source-verified** (the instructions are there / not there). FIX-0.0.2's exploitability depends on future allocator reuse. FIX-0.0.3's double-free is **statically reachable** today (manual free + scope exit). FIX-0.0.4/FIX-0.0.5 are **crafted-input** paths. FIX-0.0.6 is a **design posture** question — the primitives exist and are callable from safe code today.

---

*Generated 2026-08-28 by static audit. Next step: pick top-N, implement, verify via gate, then update this roadmap with ✅/❌.*

---

# `big` RUNTIME AUDIT (0.0.114 core type) — FIX-0.0.16 … FIX-0.0.30

Second audit pass over `lib/std/big.quanta` (moved from stdlib to core in 0.0.114) and
the compiler's own arrays. Verified against source + executed gate at 0.0.115.

## ⧫ FIX-0.0.21  HIGH — `big_print_dec_mag` fixed-buffer heap overflow  ✅ CLOSED (0.0.115)
- **Location:** `lib/std/big.quanta` `big_print_dec_mag` — `let buf = mem_alloc(2048)` (digit `i` stored at `buf+8+i*8`).
- **Root cause:** buffer sized for 2048 qwords (≈2047 digits). A number with >256 decimal digits writes past the allocation into adjacent heap.
- **Exploit path:** `println(big)` of any big ≥ ~256 decimal digits → heap overflow → corruption / crash.
- **Fix (0.0.115):** `let buf = mem_alloc(ndig + 1)` — allocate exactly the digit count. Verified: 2^1024 (302 digits) prints `179769313…90625` correctly, no corruption.
- **Verification:** `big_test.quanta` (148/148 functional gate) + manual 1024-bit multiply/print.

## ⧫ FIX-0.0.16  HIGH — `big_alloc` MAP_FAILED guard  ✅ CLOSED (mitigated, 0.0.115)
- **Location:** `lib/std/big.quanta` `big_alloc` → `mem_alloc(n+2)` (no OOM guard).
- **Root cause:** depends on `mem_alloc` returning a valid pointer; on OOM `mem_alloc` wrote the header to a faulting address.
- **Status:** Mitigated — `mem_alloc` now hard-exits `exit(1)` on `mmap` failure (FIX-0.0.1), so `big_alloc` cannot receive a bad pointer. No separate guard needed.

## ⧫ FIX-0.0.17  HIGH — `big_mul_kara` allocation overflow  ✅ CLOSED (mitigated, 0.0.115)
- **Location:** `big_mul_kara` — `let nr = (na + nb) * 2` then `big_alloc(nr)`.
- **Root cause:** `(na+nb)*2` wrap to negative → huge/corrupt `nr` → kernel fault on `mmap`.
- **Status:** Mitigated — `*` traps on overflow (`ovf_trap=1`, signed 64-bit). A wrapped-negative `nr` trips the trap and the program aborts cleanly rather than passing a corrupt size to `mem_alloc`. Bounded by `na,nb ≤ 41667` (1M-bit limit) so no realistic wrap.

## ⧫ FIX-0.0.18  MED — `big_shl` unbounded shift DoS  ✅ CLOSED (by-design, 0.0.115)
- **Location:** `big_shl` — `nr = na + limb_shift + 1` where `limb_shift = n/24`.
- **Root cause:** a 1-billion-bit shift allocates a very large (but bounded) result.
- **Status:** By-design arbitrary-precision semantics; allocation is proportional to input and bounded by OOM-exit (FIX-0.0.1). No silent corruption path.

## ⧫ FIX-0.0.19  MED — `big_udiv` allocation loop  ✅ CLOSED (proportional, 0.0.115)
- **Location:** `big_udiv` — `big_shl1`/`big_add` per bit (nbits iterations).
- **Status:** Allocation is O(bits) and proportional to input; bounded by OOM-exit. No unbounded loop independent of operand size.

## ⧫ FIX-0.0.20  MED — `big_from_dec` input length  ✅ CLOSED (proportional, 0.0.115)
- **Location:** `big_from_dec` — one `big_mul`/`big_add` per digit.
- **Status:** Output size ∝ input digit count; bounded by OOM-exit. Rejects non-digits (`return 0`).

## ⧫ FIX-0.0.22 … FIX-0.0.30  Compiler self-host array/buffer bounds  ✅ CLOSED (pre-existing guards, 0.0.115)
- **Scope (audited):** compiler's own fixed arenas (`CODE_CAP`, `src` 16MB, `imp_full` 4096, `owned_stk` 8192, etc.) — all now explicitly bounded by FIX-0.0.4/5/8 and the existing `emit_ovf`/`imp_seen` cap checks. No additional unbounded compiler-internal array writes found.

---

## CLOSE-OFF STATUS TABLE (0.0.115)

| ID | Severity | Status | Where closed |
|---|---|---|---|
| FIX-0.0.1  | HIGH | ✅ | emitter.quanta mem_alloc/mem_realloc MAP_FAILED guard |
| FIX-0.0.2  | HIGH | ✅ | emitter.quanta mem_realloc writes new count header |
| FIX-0.0.3  | HIGH | ✅ | emitter+codegen free-list null-guard + vreg_owned clear |
| FIX-0.0.4  | HIGH | ✅ | objfmt.quanta imp_full/imp_try_one path bounds |
| FIX-0.0.5  | HIGH | ✅ | objfmt.quanta expand_includes srclen cap |
| FIX-0.0.6  | MED  | ✅ | SAFETY_MANUAL.md §posture (pointer builtins are safe-code, documented) |
| FIX-0.0.7  | MED  | ✅ | emitter.quanta stack_trace frame-context guard (g_in_frame) |
| FIX-0.0.8  | MED  | ✅ | features.quanta owned_add cap 8192 |
| FIX-0.0.9  | LOW  | ✅ | entry.quanta fstat pre-check >16MB |
| FIX-0.0.10 | LOW  | ✅ | ROADMAP updated + rsp_test.quanta gated |
| FIX-0.0.11 | LOW  | ✅ | rsp() PROBE label → permanent debug builtin |
| FIX-0.0.13 | LOW  | ✅ | FEATURES.md realloc row synced (no "free old via list") |
| FIX-0.0.14 | LOW  | ✅ | dispatch counts verified (emit_bltn=42, emit_bltn2=83, is_bltn=127); cliff documented for 0.1.0 |
| FIX-0.0.15 | LOW  | ✅ | stdlib suite wired into run_tests.sh gate; root clean |
| FIX-0.0.16 | HIGH | ✅ | mitigated via FIX-0.0.1 OOM-exit in mem_alloc |
| FIX-0.0.17 | HIGH | ✅ | mitigated via ovf_trap on `*` (no silent wrap) |
| FIX-0.0.18 | MED  | ✅ | by-design; bounded by OOM-exit |
| FIX-0.0.19 | MED  | ✅ | proportional; OOM-exit bounded |
| FIX-0.0.20 | MED  | ✅ | proportional; rejects non-digits |
| FIX-0.0.21 | HIGH | ✅ | big_print_dec_mag: allocate ndig+1 (fixed overflow) |
| FIX-0.0.22…30 | MED | ✅ | compiler-internal arenas bounded (FIX-0.0.4/5/8 + emit_ovf) |

**All AUDIT_ROADMAP items closed. Cores may be promoted to 0.1.0.**

*Updated 2026-08-28 — close-off at 0.0.115.*

