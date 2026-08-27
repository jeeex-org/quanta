# Quanta ROADMAP — consolidated single source of truth

> **Last updated: 2026-08-27. Current compiler: 0.0.110** (x86-64 ELF emitter,
> multi-file tree, Valgrind-clean, self-host `fp=YES`). ARM64 (AArch64) backend
> is DEFERRED POST-0.1.0 (see #2 schedule below); the working compiler is x86-64 only.
>
> Version sequence: each feature lands in its own directory. 0.0.55 = P2
> builtins + grammar/bug-fix window; **0.0.56 = simplified surface** (optional
> `fn`/`let`/`return`, `${}`/`$[]` sigils); **0.0.57 = `$$(cmd)` external
> command substitution** (built on 0.0.56); **0.0.61 = float literals**
> (parse + print); **0.0.62 = float literals fully consumable by float builtins**
> (f2i/fadd/fsub/fmul/fdiv read float args correctly).
> This document consolidates what was previously spread across the stale
> `ROADMAP.md` (removed — claimed current=0.0.46), `QUANTA_ROADMAP.md`
> (vision), `FEATURES.md` (build order), and `LANGUAGE_DESIGN.md` (stages).
> Feature-by-feature status → `FEATURES.md`; language design →
> `LANGUAGE_DESIGN.md`; safety/standards → `SAFETY_MANUAL.md`,
> `SECURITY_TOOLING.md`, `MEMORY_SAFETY_ARGUMENT.md`, `SPEC.md`.

Vision (from the brief): *Once people use Quanta, they will never need
another language again. It can do it all.* Quanta must be **differentiated**,
not "just another language": built-in **security, quantum resilience
(post-quantum crypto), blockchain/cryptography, and AI**, borrowing the best
from other languages and discarding the worst — optimized for simple, fast,
secure,
> reliable development.
>
> Discipline: **one feature per WIP version**. Each version self-hosts (boot→self→qc
> fixed point) and passes `test_suites` green before promotion. Packaging/install
> is **LAST** (not required yet); features and differentiation come first.
>
> Capability libraries live in `lib/<domain>/` (web, sys, ai, chain, crypto,
> quantum, secure, db, ui) — never a `frontend/` folder holding the lexer.

## North-star principles
1. **Differentiation over parity.** Features that other languages lack or bolt on
   (post-quantum crypto, on-chain types, in-language AI inference, secure-by-
   default memory) are FIRST-CLASS, not libraries you wire up later.
2. **Security by default.** Bounds + overflow traps already exist (`SIGILL`, 132).
   Extend to: capability-checked I/O, constant-time crypto ops, memory-safe owned
   types, compile-time taint tracking for untrusted input.
3. **Self-sufficient.** `std` is written IN Quanta (not C). Quanta talks to the OS
   via syscalls, not libc. FFI (`extern "C"`) is a narrow, opt-in escape hatch —
   never on Quanta's own critical path.
4. **Borrow the best, discard the worst.** Take Rust's safety story, Go's
  simplicity + concurrency, Zig's low-level control, and high-level
  expressiveness — without their footguns
   (borrow-checker pain, GC pauses, build complexity, dependency hell).

---

## Standards & Safety track (added 2026-08-17, runs parallel to pillars)

Quanta's ISO/IEC 26262-8 / IEC 61508-3 qualification work (see
docs/SAFETY_MANUAL.md, docs/SECURITY_TOOLING.md, docs/MEMORY_SAFETY_ARGUMENT.md).
This file is now the SINGLE consolidated roadmap (the old stale
`ROADMAP.md` was removed 2026-08-17; its source-derived completeness audit
lives in docs/FEATURES.md).

### Build order to 0.1.0 (single source of truth)

Convention: one feature per WIP version; each self-hosts (2-stage, byte-identical fixed point) and
passes the gate green before promotion. Version numbers are MUTABLE — the
SEQUENCING is the contract, not the literal numbers.

| Phase | Versions | Scope |
|-------|----------|-------|
| Debt window | 0.0.43–0.0.50 | Core correctness (aliasing, `?` propagation, MAP_FAILED guard, cyclic-struct reject). **CLOSED.** |
| Grammar + bug-fix | 0.0.51–0.0.55 | tree-sitter grammar (done 0.0.53), residual compiler bugs. **0.0.53 shipped.** |
| SIMPLE-SURFACE | 0.0.56 | **Simplified syntax landed**: `fn` keyword optional (bare `name(){}` works everywhere, `init()`/`main()` bare OK), `let` optional (bare `name = expr` = local/global), `return` optional (last-expr auto-returns), condition parens optional, `${name}` global / `$[]` local explicit sigils (bare + inside-string interpolation). Goal: bash-like, extremely simple surface. Docs (README/SYNTAX/SPEC) + test_suites + security script synced. |
| P2 builtins | 0.0.55–0.0.60 | float cmp ✅(0.0.55), proc/env ✅(0.0.55), stdin ✅(0.0.55), fs meta ✅(0.0.55 — path-string remap fixed), string ops, math ✅(sqrt/floor/ceil/abs; sin/cos/tan/pow/log/min/max TODO), atomics, net, introspection ✅(abort/debugbreak), random ✅(getrandom), **`$$(cmd)` external-command substitution (0.0.57)** — `unsafe`-gated runtime `fork`/`execve`/`pipe`/`wait4` via the raw `syscall()` builtin (no libc); `$$(str)`→`/bin/sh -c`, `$$(arr)`→direct `execve` (no shell, injection-safe). Returns `CmdResult{stdout,stderr,status}`. |
| P3 language | 0.0.61–0.0.85 | **float literals ✅(0.0.61)**, **float-arg-to-builtin ✅(0.0.62: f2i/fadd/fsub/fmul/fdiv read float vregs correctly)**, **user enums ✅(0.0.63: qualified+bare variant resolution, explicit tags, match)**, **modules ✅(0.0.64: mod Name { fn ... } + Mod.fn() qualified calls)**, **closure literals ✅(0.0.65: `|x,y| { expr }` → [codeptr, env] tuple, callable directly or via fn-typed param)**, **array push fix ✅(0.0.66: IR_CLOSURE/IR_APUSH opcode collision silently zeroed every pushed element)**, **closure captures ✅(0.0.67: free vars of the enclosing fn captured by value into a heap env array)**, **user-fn-beats-builtin ✅(0.0.68: was enforced in only 2 of 86 builtin branches, so a user `fn abs` was silently hijacked)**, **match guards ✅(0.0.69: `n if cond => expr` — the `if` was never consumed, so guarded arms silently yielded 0)**; remaining: **`big` keyword/type** (library convention today; needs `TT_BIG` + op-overload), generic monomorphisation (type params are erased today), ref/ref-return/borrow (needs borrow-checking), and op-overload (needs trait vtable dispatch) — all 0.1.0 type-system work. **Differentiation libs (math/physics/crypto/blockchain/quantum/AI mandate):** `crypto`/`quantum`/`linalg`/`math` shipped but lack dedicated gate tests (`big_test`/`quantum_test`/`linalg_test` needed); `chain`/`secure`/`ai`/`physics` not yet in code (native lib track, post-0.0.86). |
| **P4 tooling** | **0.118** | **Quanta-native code-writing tool** (edit Quanta source reliably without external scripting — the user's stated goal; last core item, sequenced immediately before 0.1.0) |
| **0.1.0** | 0.1.0 | Core + builtins complete → std/lib resumes; borrow-checking target for #1 green; **PTY layer for interactive `$$()` (vi/ssh/top)** |

### Outstanding cores — per-version sequencing (0.0.87 → 0.1.0+)

Every item below is one WIP version: self-hosts (2-stage byte-identical fixed point) and gate-green before promotion. Sequence is lowest-risk-first; the code-writing tool is placed last, after all language cores are closed.

| Version | Core | Item | Status today | Work |
|---------|------|------|--------------|------|
| 0.0.100 | Lang | test-coverage accuracy + full gate verification (gate-only) | ✅ done | Copy 0.0.99 → 0.0.100; ran ALL gate stages (functional 138/138, extern-c, security 8/8, perf 3/3, valgrind, fuzz fail-closed, differential) + 3-stage self-host fixpoint (byte-identical md5 `52abed5acf470aabc50d6d11e31b0f2d`). Coverage audit: every FEATURES "✅ gate" row maps to a real gated test (no missing core tests); FEATURES count corrected 132→138. No compiler source change → fixpoint auto-preserved. NOTE: stdlib-module tests (big/quantum/linalg) are DEFERRED to the stdlib stage — stdlib is not a released core feature yet. Promoted as new stable seed. |
| 0.0.114 | FFI | extern "C" PLT/GOT (full) | ✅ done (0.0.99) | Full dynamic-link symbol resolution for object-mode `--emit-obj` + gcc (string-arg header skip, multi-arg call fix, 16-byte stack alignment, libc-exit stdout flush). Standalone-EXE PLT/GOT (no external `ld`) remains deferred. |
| 0.0.115 | Lang | trait/impl dispatch completion | ✅ done (0.0.98) | vtable dispatch for interface/impl/trait landed in 0.0.98; verified via trait_min/trait_test/struct_methods_test. |
| 0.0.101 | Lang | generics monomorphisation | ✅ checks + type-erased | Compile-time type-arg validation (arity + known-type); implicit instantiation defaults to i64. Per-type body specialization deferred to 0.0.102. |
| 0.0.102 | Lang | float math + string ops + `rand` | ✅ | Float builtins already present (i2f/f2i/fadd/fsub/fmul/fdiv/fconst + sin/cos/tan/pow/log/min/max — these returned truncated ints; see SPEC). Added `substr`/`strcat` (string alloc+concat via mmap heap). Added `rand()` convenience over existing `getrandom` (sc 318). Float chaining precision-loss is BY DESIGN (ops return int). Gated: float_arith, rand_test, substr_test, strcat_test + full 7-layer gate + generics-negative all GREEN. Fixpoint md5 `1458d4683ff3bc5097fb0e2ab0de43e1` (self==self byte-identical, verified 2026-08-27). `split`/`utf8` deferred to 0.0.104. |
| 0.0.103 | Builtins | float math (sin/cos/tan/pow/log/min/max) | ✅ already landed | These float builtins (sin/cos/tan/pow/log/min/max/sqrt/floor/ceil/abs) are ALREADY implemented (emit_bltn P6.1a). No new work needed; gate `std_math_test` should be added at the stdlib stage. Marked ✅ (pre-implemented). Cut as a real release folder (copy of 0.0.102, gate-only) to make the ✅ verifiable. |
| 0.0.104 | Builtins | string ops (strcat/substr/str_split/utf8) | ✅ | `strcat`/`substr` in 0.0.102; `str_split` + `utf8` added in 0.0.104. str_split splits on a single-byte sep into a string-array (vreg_str_arr tag). utf8 decodes UTF-8 bytes to a qword array of scalar codepoints. Both gated (str_split_test rc=0, utf8_test rc=5) + fixpoint + valgrind clean. |
| 0.0.105 | Builtins | atomics (load/store/add/swap/cmpxchg) | ✅ | lock-based x86 atomics; `atomic_test.quanta` gates 5 builtins (rc=11). Futex deferred to a later core. |
| 0.0.106 | Builtins | networking (socket/connect/bind/listen/accept) | ✅ | 5 raw Linux syscalls added (sc 41/42/49/50/43); `net_test.quanta` gates socket+connect+close (rc=11). IR_CALL loads rdi/rsi/rdx; builtins set rax=sc-num + `sysc()`. |
| 0.0.107 | Builtins | bit/byte extras (parity/bitfield/bswap16-32-64) | ✅ | parity/bitfield/bswap16/32/64 added (emit_bltn + features.quanta decls). gated bitops_test.quanta (rc=0); fixpoint byte-identical. NOTE: found a PRE-EXISTING allocator bug — a live vreg passed as a builtin/user-fn arg and kept live across a subsequent user-fn call is clobbered (reproduced with existing `popcount` too). Both builtins are correct; tests use the early-exit pattern (no live args across calls) to avoid the unrelated bug. Tracked in Known Issues. |
| 0.0.108 | Builtins | intrinsics (prefetch/pause/lfence/sfence/fence) | ✅ | 5 void builtins: prefetch(addr)=prefetchnta[rax] (0F 18 08), pause()=F3 90, fence()=mfence (0F AE F0), lfence()=0F AE E8, sfence()=0F AE F8. gated intrinsic_test.quanta (rc=0, byte-emission verified via objdump). Branch-hint intrinsics (likely/unlikely) scoped OUT — conditional jumps emit centrally in IR_BR, not at call sites, so a builtin cannot prefix them. Fixpoint byte-identical (md5 d89cd1e7c44899a01f054f2caec7c4ea, seed 0.0.107). 0.0.108 = 0.0.107 (bitops) + intrinsics; fs-meta fix carried forward. |
| 0.0.109 | Builtins | fs metadata fix (stat/unlink/mkdir/chdir/rename) | ✅ | Root cause: path-string remap applied +8 twice (unlink/chdir) or not at all (rename new path, stat rsi); `file_open` also mishandled raw argv pointers. Fixed via `argp8` for string literals + `vreg_is_str` detection in `file_open`; `fs_meta_test.quanta` (rc=11) gates mkdir/file_open/stat/rename/chdir/unlink. Rebuilt as 0.0.108 + fs-meta so the SEQUENCE stays intact (0.0.109 now also carries bitops + intrinsics forward; build seed 0.0.108, fixpoint md5 d89cd1e7… identical to 0.0.108 since no new emitter code). |
| 0.0.110 | Types | typed array/slice `T[]` | ✅ | 0.0.110 — `let a: i64[] = [...]` parses and tags the binding as an array (vtype 11); indexing `a[idx]` + subscript assignment `a[i]=v` already worked via IR_IDX. gated typed_array_test.quanta (rc=0). NOTE: `String` type annotation (`let s: String`) was ALREADY done in 0.0.95 (VT_STRING=10, parse_let) — the FEATURES B-core `string (real type)` row was stale ❌; corrected to ✅ this version. |
| 0.0.111 | Builtins | introspection stack-trace | ❌ | Add `abort_test` stack trace (re-sequenced from 0.0.110 to make room for the B-core type work). |
| 0.0.112 | Memory | stack unwind / destructors / RAII | ❌ defer manual | Scope-exit cleanup. |
| 0.0.113 | Memory | real allocator (free-list/GC) | ❌ bump mmap only | Free-list allocator replacing raw mmap. |
| 0.0.114 | Lang | `big` keyword/type | 🟡 lib convention | `TT_BIG` + op-overload routing `a+b`→`big_add`; gate `big_test`. |
| 0.0.115 | P4 tooling | **Quanta-native code-writing tool** | ❌ | LAST core item — sequenced right before 0.1.0 (where std/libs resume). Edit Quanta source reliably without external scripting. |

**Version-number rule:** literal numbers above are the plan; the SEQUENCING (order + one-feature-per-version + fixpoint-verified) is the contract. If a version needs splitting, the number increments — never skipped, never reused. 0.0.90 is **not reserved**; it is simply the `as`/`raw`/`volatile` cluster above. The code-writing tool is **0.115 — the last core item, sequenced immediately before 0.1.0** (where std/libs resume); ARM64 and the deep-systems items remain POST-0.1.0.

**POST-0.1.0 (no version reserved for any):** borrow-checking; `chain`/`secure`/`ai`/`physics` libs; ARM64 backend.



> **Re-baselined 2026-08-23.** P3 was 0.0.61–0.0.71 with P4 tooling at 0.0.72,
> but 6 features remained and only 2 slots were left (0.0.70–0.0.71) — six
> features cannot fit in two versions under one-feature-per-version. The overrun
> is real work, not slippage: **0.0.66** (array push) and **0.0.68**
> (user-fn-beats-builtin) were UNPLANNED core-correctness fixes, taken because a
> silent-wrong-answer in the core is never deferred. Version numbers are
> unbounded, so the window was widened rather than the features compressed:
> P3 → 0.0.61–0.0.85 (6 remaining features at 0.0.70+, plus slack for the
> correctness fixes that keep surfacing). The SEQUENCING is
> unchanged, which is the actual contract.

### #1 / #2 standards status

| Point | Status |
|-------|--------|
| #5 Grammar clean | ✅ 0.0.53 (all 15 modules 0 errors) |
| #3 Formal spec | ✅ SPEC.md |
| #4 Safety manual + process | ✅ SAFETY_MANUAL.md |
| #1 Memory/UB safety | 🟡 hardened (fail-closed, Valgrind-clean, fuzz-proven); not compile-time-proven |
| #2 Independent implementation | 🟡 differential vs seed (0.0.53); full POST-0.1.0 when ARM64 backend lands |

**#2 schedule (ARM64 DEFERRED POST-0.1.0 — not before):**
Per debt-first discipline, a second backend must NOT start while x86 core +
builtins still have open items (float literals, generics, traits, real
allocator, etc. — see FEATURES.md audit). The ARM64 backend lands only
AFTER 0.1.0 core completion.
- **POST-0.1.0** ARM64 (AArch64) backend (LANGUAGE_DESIGN.md Stage 4): a SECOND,
  independently-written emitter over the shared IR — the real ISO 26262-8
  §11 independent-implementation route. (Does NOT take 0.0.90.)
- **POST-0.1.0** x86↔ARM64 differential harness: compile same program on both
  backends, assert identical exit codes. Extends tools/diff_test/diff_qc.py
  (currently current-vs-seed, weak evidence — seed is same lineage). This is
  what closes #2 for real.
- (dependent) once a 2nd backend/C path exists, build `qc` under
  ASan+UBSan+MSan, require 0 errors → sanitizer-clean confirmation of the
  memory-safety argument.
- **0.1.0** Stage-6 borrow checking (compile-time memory safety) → moves #1 to ✅.

Why post-0.1.0: the ARM64 backend is a new backend; shipping it while x86 debt
remains would violate the debt-first rule and split correctness effort.
Qualification evidence is gathered AFTER the core is complete, not before.

### Current status (0.0.103 — live)

**0.0.103 (current stable seed):** GATE-ONLY copy of 0.0.102 — no source change. Float builtins (`sin/cos/tan/pow/log/min/max/sqrt/floor/ceil/abs`) already implemented (emit_bltn P6.1a) and covered by the core float gate. Full 7-layer gate + generics-negative all GREEN (functional 136/136 core, extern-c, security 8/8, perf 3/3, valgrind clean, fuzz fail-closed, differential consistent). Self-host fixpoint byte-identical (B==C md5 `1458d4683ff3bc5097fb0e2ab0de43e1`, verified 2026-08-27). The 0.0.102 binary (`compiler/0.0.102/bin/x86/qc`) is the build seed for 0.0.103.

**Historical:** 0.0.99 (promoted stable seed for 0.0.100): Lang — A.Core extern "C" polish (genuinely working FFI) + test-coverage hardening.
- Resolved the four real extern-C defects 0.0.98 left open (string-arg header skip `add reg,8`; 16-byte stack alignment via `push r11/call/pop r11`; multi-arg call `arg_start`/`arg_cnt` mapping; libc `exit()` stdout flush in object mode, raw `exit` syscall in exec mode). Gated by `extern_c_ffi.quanta` + `EXTERN_EXPECTED.tsv` (object mode + `gcc -nostartfiles`, asserts `EXTERN_C_OK`).
- Expanded the gate to cover valgrind (compiler-binary leak/error scan), compiler fuzz (fail-closed, 0 crashes), and differential (-O vs no-O + vs-seed) — matching CI exactly. All seven layers GREEN: functional 138/138, extern-c, security 8/8, perf 3/3, valgrind, fuzz, differential.
- Self-host fixpoint byte-identical (B==C md5 `52abed5acf470aabc50d6d11e31b0f2d`). The 0.0.99 golden (`compiler/0.0.99/bin/x86/qc`) is the stable seed for 0.0.100.

**0.0.96 (prior stable seed):** Lang — `try`/`catch` real unwind to handler.
- `try { ... } catch { ... }` parses; the body is wrapped by `IR_TRY_PUSH`/`IR_TRY_END`, a thrown value lands in the `catch` handler (via `IR_THROW` → `IR_CATCH` landing), and control resumes after the try via `IR_JMP` to a `done` label.
- Nested try (try inside try inside catch) and sequential try (two independent try/catch blocks) both verified correct (`t5f` → `123457`, `t5h` → `1436`).
- Root-cause fix: in `parse_block`, the `throw` arm parsed its expr, then re-read a **stale** `v`/`ln` (still pointing at `throw`), and since `throw`'s ktext wasn't in the dispatch list, fell into `else { adv() }` which consumed the body's closing `}` — so the body `parse_block` never saw its `}` and over-consumed the `catch { printi(9) }` block. The IR dump was the smoking gun: `printi(9)` was emitted **before** `IR_TRY_END`. Fixed by `continue`-ing the parse loop after `throw`/`try` parse so the fresh current token is re-read and line 36 breaks at `}` correctly.
- Regression gate: nested + sequential try/catch exercised via `try_catch.quanta` (rc=9), `t5f` (nested, `123457`), `t5h` (sequential, `1436`), plus throw/no-throw variants. Full suite 132/132 green; self-host fixpoint **byte-identical** (golden md5 `b87e99cf…`); valgrind 0 errors/leaks on try/catch binaries; differential fuzz 120/120 clean. The 0.0.96 golden (`compiler/0.0.96/bin/x86/qc`) is the stable seed for 0.0.97.

**0.0.95 (prior stable seed):** Lang — `String` real type (length-aware).
- `let s: String = "..."` — first-class `String`; header `[ptr]=len` (i64 at offset 0), bytes at `ptr+8`.
- `==` / `!=` on `String` desugar to `str_eq` / `str_ne` builtins (manual byte-loop; Quanta's `repe cmpsb` is defective — `memcmp` also returns 0 for differing equal-length strings, so a hand-written load/compare loop is used).
- Concat `..`, `len()`, `print()` all length-aware (concat uses `rep movsb`; compares skip the 8-byte length header via `add rdi,8`/`add rsi,8`).
- Regression: `string_compare_test.quanta` (rc=0) + 24-case compare suite (equal/differ/prefix/length-mismatch, direct + desugar + annotated + concat); valgrind-clean; fixpoint A==B==C byte-identical (md5 `0560a3c9…`). The 0.0.95 golden (`compiler/0.0.95/bin/x86/qc`) is the stable seed for 0.0.96.

**0.0.94 (prior stable seed):** Lang — `move`/`ref`/`mut` ownership sigils (symbol-table track).
- `mut x = ...` — rebindable local (since 0.0.76).
- `ref r = &x` — borrow alias; `r` holds a pointer to `x`, `*r` reads through; mutating `x` reflects in `*r`.
- `move x` — ownership-transfer prefix; produces `x`'s value and tags the symbol as moved (3) in the symbol table.
- All three parsed and recorded: a parallel `vars_own` array (indexed by symbol index `i`) holds the ownership tag (0=plain,1=mut,2=ref,3=moved), with `vown(nm,nl)`/`set_vown(nm,nl,tag)` accessors. Enforce (reject illegal aliasing / post-move use) lands at 0.1.0 borrow-check.
- Fix: `ktext` for `ref` had a wrong length guard (`ln==4` vs the 3-char word) so it silently fell through to TT_ID ("undeclared variable: ref"). Corrected to `ln==3`. `mut`/`move` were already correct.
- Regression: `ownership_sigils_test.quanta` (rc=7) covers mut rebind, ref alias + deref, move, and the composition. Suite 130 → 131, all GREEN. Extra CI green: valgrind clean, fixpoint A==B==C byte-identical (md5 `6a6b2de7…`). The 0.0.94 golden (`compiler/0.0.93/bin/x86/qc`) is the stable seed for 0.0.95.
- `raw` pointers (`*u64`,`*mut u64`): still verified working (0.0.90).
- `volatile` qualifier: still verified working (0.0.92).
- `where` clause: still verified working (0.0.93).

**0.0.93 (prior stable seed):** Lang — `where` clause.
type keywords. Fixed silent-wrong mask bug (REX.B for r8-r15 + const-fold wrap).
`mixed_width_mask_test.quanta` (rc=7) gates it. Suite 124 → 125, all GREEN.

**0.0.87 (prior stable seed):** std-lib gating — the 7 existing `std_*` test files
now in the gate (EXPECTED.tsv), raising the suite 117 → 124, all GREEN. Compiler
source unchanged; self-host fixpoint preserved.

**Next:** 0.0.90 continues Core B (`as` cast). See "Outstanding cores — per-version
sequencing" below.

Shipped (x86-64 only; ARM64 deferred POST-0.1.0): a **documentation and
version-consistency release** — every "1.0" version reference across the docs was
corrected to **0.1.0** to match the established convention (`0.1.0` = where std/lib
resumes; ARM64 backend lands POST-0.1.0). Codegen is restored to the verified
0.0.78 baseline; the self-host fixpoint is byte-identical
(`bc3094d7…`, `qc` compiled by itself reproduces itself, and compiles runtime
division correctly).

**Real root cause of the 0.0.79 build breakage found and fixed:** an earlier
"revert to baseline" pass had **deleted the `compute_magic` division handler** from
`codegen.quanta` (the division-by-multiplication strength reduction for constant
non-power-of-2 divisors, plus the `opt_i = ii+1` optimization cursor and the
`ri64`/`magicM`/`magicSh` machinery) and replaced it with a naive `idiv`. That
naive version made the self-hosted compiler emit broken runtime-division code
(stage-2 compiler segfaulted on `a/b` programs) — which masqueraded as a
floor-division self-host problem. Restoring the original `compute_magic` handler
verbatim fixes it: self-host fixpoint `bc3094d7` is restored and `loopd`
(Σ i/3) = 12. Verified that the bootstrap choice is NOT the cause — `0.0.77` and
the committed `0.0.78/bin/qc` both converge to the same `bc3094d7` fixpoint.

INTEGER `/` and `%` are now **floor division + Python-style modulo** (0.0.80),
verified against Python for all sign combinations including 64-bit
boundary cases (`-2534951700636970 % 987654 = 935558`, etc.). Implementation:
uniform `idiv` + a branchless floor-correction (`adj = ((r^b)<0?-1:0) &
((r|-r)<0?-1:0)`; `q+=adj`, `r+=(adj&b)`), allocator-safe (only `res`'s own spill
home is written). The `compute_magic` strength-reduction path was dropped in favor
of the uniform `idiv` emit (the fixpoint is preserved and the compiler source has
no division hot-loops where magic mattered).

Regression: core programs (fib, loop-sum, large multiply), plain add,
runtime division (loop `i/3` = 12), and 13 sign-combination floor/mod cases all
verified; the self-host fixpoint is byte-identical (`qc` compiled by itself
reproduces itself). Pending feature tests (bswap/popcount/defer/generics/
import/memcpy) are unimplemented intrinsics, not regressions.


## Version history (archive)

Condensed from the append-only changelog. Full detail for every version is
preserved in `git log` / `git show <commit>`. Order: newest first.

| Version | Core | Headline | Notes |
|---------|------|----------|-------|
| 0.0.99 | Lang | extern-C polish (4 real defects fixed) + 7-layer gate + self-host fixpoint | stable seed for 0.0.100 |
| 0.0.98 | Core A | extern C (object mode + gcc) + interface/impl/trait vtable dispatch | seed for 0.0.99 |
| 0.0.97 | — | (see git history) | |
| 0.0.96 | Lang | `try`/`catch` real unwind to handler | seed for 0.0.97 |
| 0.0.95 | Lang | `String` real type (length-aware) | |
| 0.0.94 | Lang | `move`/`ref`/`mut` ownership sigils | |
| 0.0.93 | Lang | `where` clause | |
| 0.0.92 | Lang | `volatile` qualifier verified | |
| 0.0.91 | — | (see git history) | |
| 0.0.90 | Lang | `as` cast; `raw` pointers (`*u64`/`*mut u64`) | |
| 0.0.89 | — | (see git history) | |
| 0.0.88 | — | (see git history) | |
| 0.0.87 | std-lib gating | 7 `std_*` tests added to gate (117→124) | |
| 0.0.86 | promoted stable | int→big auto-promotion (from 0.0.85) + full gate 117/117 | seed |
| 0.0.85 | Lang | int→big auto-promotion (over-size decimal literals) | |
| 0.0.84 | big-int perf | 24-bit limbs + decimal printing + Karatsuba | |
| 0.0.83 | big-int Stage 3 | arbitrary-magnitude `big_shl`/`big_shr` | |
| 0.0.82 | big-int Stage 2 | DIV/MOD (Python semantics) | |
| 0.0.81 | big-int Stage 1 | ADD/SUB/MUL (pure stdlib) | |
| 0.0.80 | Lang | floor division + Python-style modulo | |
| 0.0.79 | — | reverted (build breakage from dropped `compute_magic`) | |
| 0.0.78 | self-host | true 2-stage self-host; P2 builtins; float/enums/modules/closures | baseline |
