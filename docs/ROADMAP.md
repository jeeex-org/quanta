# Quanta ROADMAP — consolidated single source of truth

> **Last updated: 2026-09-04. Current compiler: 0.0.135** (x86-64 ELF emitter,
> multi-file tree, Valgrind-clean; self-host fixpoint **BYTE-VERIFIED** —
> md5 `aabe3cafbca502cc6ce7bb8925f9b52c`; IR_CAP=1B/40GB, TOK_CAP=48M/1.92GB, CODE_CAP=512MB, fn_btok fix for bare function declarations. FIPS 202 SHA3 + AES-GCM complete. ARM64 (AArch64) backend is
> DEFERRED POST-0.1.0 (see #2 schedule below); the working compiler is x86-64 only.
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
| P3 language | 0.0.61–0.0.85 | **float literals ✅(0.0.61)**, **float-arg-to-builtin ✅(0.0.62: f2i/fadd/fsub/fmul/fdiv read float vregs correctly)**, **user enums ✅(0.0.63: qualified+bare variant resolution, explicit tags, match)**, **modules ✅(0.0.64: mod Name { fn ... } + Mod.fn() qualified calls)**, **closure literals ✅(0.0.65: `|x,y| { expr }` → [codeptr, env] tuple, callable directly or via fn-typed param)**, **array push fix ✅(0.0.66: IR_CLOSURE/IR_APUSH opcode collision silently zeroed every pushed element)**, **closure captures ✅(0.0.67: free vars of the enclosing fn captured by value into a heap env array)**, **user-fn-beats-builtin ✅(0.0.68: was enforced in only 2 of 86 builtin branches, so a user `fn abs` was silently hijacked)**, **match guards ✅(0.0.69: `n if cond => expr` — the `if` was never consumed, so guarded arms silently yielded 0)**; remaining: generic monomorphisation (type params are erased today), ref/ref-return/borrow (needs borrow-checking), and op-overload (needs trait vtable dispatch) — all 0.1.0 type-system work. **`big` keyword/type shipped in 0.0.114** (first-class `big` type: `: big`/`-> big` annotations, operator routing with int→big promotion, `big_test` gate). **Differentiation libs (math/physics/crypto/blockchain/quantum/AI mandate):** `crypto`/`quantum`/`linalg`/`math` shipped; `quantum_test`/`linalg_test` gate tests landed 0.0.116 (exposed + fixed 5 real stdlib bugs); `big_test` landed with 0.0.114; `chain`/`secure`/`ai`/`physics` not yet in code (native lib track, post-0.0.86). |
| **P4 tooling** | **0.1.x (first Quanta App)** | **`chain` package/build tool — the first Quanta App**, built ON 0.1.0 (not a compiler core). Per user directive 2026-08-30: tooling is dogfooded as an application on the stable release, not baked into the language. |
| **0.0.125+** | 0.0.125 → 0.0.138 | **Cores resume at 0.0.125** (one feature per version, fixpoint-verified, per 2026-08-30 directive — cores do NOT go into 0.1.0). **All PARTIAL cores first (right after `process`), then AI/QC-era, then classical/hardest.** `time` (0.0.125) → `process` fork/exec/waitpid (0.0.126, shell-free `$$()`) → **PTY layer (0.0.127, partial core, needs 0.0.126 process + pty-alloc)** → **`big` div-by-zero guard FIX-0.0.19 (0.0.128, partial core — `big` shipped 0.0.114, hole remains)** → **`fs` missing ops (0.0.129, partial core — stat/unlink/mkdir/chdir/rename/rmdir absent; `fs` shipped 0.0.87)** → **extern-C variadic (0.0.130, partial core — `printf(fmt,...)` not modeled; extern-C shipped 0.0.98/122)** → **closure self-recursion by name (0.0.131, partial core — `findfn` doesn't resolve name in closure body; closures shipped 0.0.65→123)** → `json` (0.0.132, AI/data interchange) → `secure` TLS 1.3 + hybrid X25519/ML-KEM (0.0.133, **PQC-ready QC-age**) → `quic` HTTP/3 UDP+TLS (0.0.134, modern transport, ahead of HTTP/2) → `http` HTTP/2-over-TLS (0.0.135, no plaintext) → `ai` tensor ops + inference (0.0.136, AI-age, promoted into core chain) → generics type constraints FIX-0.0.33 (0.0.137, classical type-system; `where` bounds enforced) → borrow-check (0.0.138, language safety pass, hardest). Each self-hosts + gate-green before promotion. |
| **0.1.0** | 0.1.0 (STABLE) | **Application-capable stable release — AFTER all cores (0.0.125–0.0.138) are done.** 0.1.0 is the post-core stable; it does not carry new cores. `chain` (first Quanta App) dogfooded on 0.1.0, lands 0.1.1+; `physics` optional 0.1.1+. |

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
| 0.0.111 | Memory (E) | real allocator (free-list) | ✅ | 0.0.111 — real heap allocator: `mem_alloc` left byte-identical (bump mmap) for fixpoint-safety; NEW builtins `mem_free(ptr)` (free-list push at `HEAP_CTRL=GDATA+1032`) and `mem_realloc(ptr,newn)` (mmap new + `rep movsq` copy min(old_count,newn) qwords, returns new) added in `is_bltn`+`emit_bltn`. gated `mem_free_test.quanta` (rc=0, verifies realloc preserves payload + mem_free no-crash). Full 8-layer gate GREEN. **FIXPOINT: NOT byte-verified at the time** — the self-host fixpoint chain was systemically broken (stage2 SIGSEGV `si_addr=0xfffffffffffffff4` in 0.0.109/0.0.110); affects ALL versions 0.0.109–0.0.113. Resolved at 0.0.114. |
| 0.0.112 | Memory (E) | stack unwind / destructors / RAII | ✅ | 0.0.112 — RAII complete: owned `mem_alloc` bindings are auto-recycled to the free-list at every scope exit (normal + early return) via compiler-inserted `drop()` (replaces the old `munmap` IR_FREE with the 0.0.111 free-list push). NEW user-facing `drop(ptr)` builtin (== mem_free) is the destructor hook and is also auto-invoked for owned bindings. `defer` LIFO replay unchanged. gated `raii_test.quanta` (rc=0: scope-exit recycle, early-return RAII, reusable-after-free, no UAF). Full 8-layer gate GREEN. **FIXPOINT: NOT byte-verified** (systemic stage2 SIGSEGV, same as 0.0.111 — pre-existing in 0.0.109/0.0.110). |
| 0.0.113 | Builtins (G) | introspection stack-trace | ✅ | 0.0.113 — `stack_trace()` pure builtin returns the immediate caller's return address (code pointer) read from the rbp frame chain (`[rbp+8]` under the SysV-style prologue; no per-call instrumentation, fixpoint-safe). Gated `stack_trace_test.quanta` (rc=0: non-zero result, inside code segment 0x400000..0x410000, distinct call sites yield distinct return addresses). Full 8-layer gate GREEN. **FIXPOINT: NOT byte-verified** (systemic stage2 SIGSEGV, same as 0.0.111/0.0.112 — pre-existing in 0.0.109/0.0.110). |
| 0.0.114 | Lang | `big` keyword/type | ✅ | 0.0.114 — `big` is a first-class type keyword (context-sensitive: `ktext` ID 62, stays `TT_ID` so `let big = 70000` still works). Compiler: `vreg_is_big` tag array; `: big` param annotations recorded in `fn_parbig`; `-> big` return annotations detected by `scan_retbig()` (explicit annotation supersedes the old return-name heuristic); big tag propagates through `let`, reassignment, and call results. Operators `+ - * / % == !=` route to `big_add/sub/mul/div/mod/eq` with automatic int→big promotion (operator operands AND call-site args to `: big` params, via a pre-pass that rewrites argstack before the contiguous `IR_MOV` arg records); ordering compares (`< > <= >=`) rejected at compile time (error kind 6). Overflowing decimal literals lex as `TT_BIGNUM` (single token — fixed a lexer double-emit) and lower through the resolved-callee call convention; `println(big)` rewrites to `big_println`. `lib/std/big.quanta` public API fully annotated (`: big` params, `-> big` returns) so raw-int args auto-promote and big-returning calls never double-wrap. Gated `big_test.quanta` (rc=0: 30-digit add/sub/mul/div/mod vs Python reference values, signed equality, println). Full 8-layer gate GREEN (147/147). **FIXPOINT: BYTE-VERIFIED** — the systemic stage2 SIGSEGV that broke the self-host chain in 0.0.109–0.0.113 is RESOLVED at 0.0.114: the promoted binary compiles its own source to a byte-identical binary (md5 `637c7c694f04a7579468715c1f0c8b97`, verified across multiple independent builds; promoted binary == self-fixpoint). |
| 0.0.115 | Security | AUDIT_ROADMAP close-off (hardening) | ✅ | All AUDIT_ROADMAP findings FIX-0.0.1–30 CLOSED. Heap: MAP_FAILED guards in mem_alloc/mem_realloc (fail-closed exit(1)); mem_realloc writes new block count header; free-list null-guards + vreg_owned cleared on explicit mem_free/drop (double-free). Include/source: path + 16MB expansion overflow caps. Stack: stack_trace() frame-context guard; rsp() PROBE→permanent builtin. Owned/entry: owned_stk cap (8192); fstat pre-check >16MB source. big runtime: big_print_dec_mag heap-overflow fix (allocates ndig+1 qwords, was fixed 2048). Hygiene: stdlib suite wired into gate (10th layer); pointer-builtin posture in SAFETY_MANUAL §3b. AUDIT_ROADMAP moved to docs/. Full 9-layer gate GREEN (148/148 + 7/7 stdlib). FIXPOINT BYTE-VERIFIED md5 `50857425ec4be97ddf971074a6b66d48`. Remote CI green. |
| 0.0.116 | Bugfix+Hygiene | AUDIT_ROADMAP close-off #2 | ✅ done | (1) FIX-0.0.31: `rsp()` emitted `mov rsp,rsp` (ModR/M 0xE4 no-op) instead of `mov rax,rsp` (0xE0) — any `rsp() <op> local` miscompiled to `local <op> local`. Fixed the byte. (2) FIX-0.0.40: hex literals ≥ 0x8000000000000000 rejected as i64 overflow — now full 64-bit two's-complement range (needed by Keccak round constants). (3) FIX-0.0.45: sin/cos/tan reloaded arg0 from wrong vreg → always 0 — now use rdi directly, bit-exact vs libm. (4) Stdlib bugs exposed by new gate tests: quantum Keccak rho+pi scrambled + sponge absorb/squeeze bugs (FIX-0.0.41/42, verified vs OpenSSL), linalg mat_from_flat off-by-8 + mat_det truncated-division (FIX-0.0.43/44, Bareiss rewrite). (5) New gate tests: quantum_test (5 NIST vectors), linalg_test, trig_test. (6) MULTI-TU gate layer (mtu_* fixtures, --emit-obj + link). Gate: 151/151 + 10 layers GREEN. Fixpoint md5 `662de43a69d848581774e81f01703456`. |
| 0.0.117 | Lang | `big` completion: ordering + bitwise ops + sign-correct arithmetic | ✅ done | Route `< > <= >=` on big to signed `big_cmp` (was rejected, error kind 6); route `& | ^ << >>` to `big_and`/`big_or`/`big_xor`/`big_shl_signed`/`big_shr_signed` (two's-complement, sign-aware). **Also fixed (discovered during 0.0.117): `big_add`/`big_sub`/`big_mul` were MAGNITUDE-ONLY** — negative operands silently miscomputed (e.g. `big_add(-5,3)`→8). Now `big_add_signed`/`big_sub_signed`/`big_mul_signed` are SIGN-AWARE and the `+ - *` operators route to them. `: big` annotation with an int literal RHS now PROMOTES via `big_from_i64` (previously tagged big but held a raw i64 → any big-op deref'd garbage). New gate test: `big_ops_test.quanta` (EXPECTED.tsv 152 rows). Compiler delta: operator routing only; arithmetic/compare/bitwise stay in lib/std (core-vs-stdlib line). |
| 0.0.118 | Builtins | net completion: `send`/`recv` | ✅ done | net (0.0.106) shipped socket/connect/bind/listen/accept (sc 41/42/49/50/43) but NO data transfer. Added `send(fd,buf,len,flags)` + `recv(fd,buf,len,flags)` builtins. **x86-64 ABI detail:** there is NO `send`/`recv` syscall — glibc implements them as `sendto(44)`/`recvfrom(45)` with NULL addr/addrlen. The builtin reloads the 4 named args (rdi=fd, rsi=buf, rdx=len, r10=flags) from their spill homes, then ZEROES r8/r9 (the 5th/6th args) so the kernel sees a connected SOCK_STREAM send (otherwise leftover r8/r9 = garbage sockaddr → EISCONN, and `recvfrom` blocks forever → hang). `net_test.quanta` now transfers 8 real bytes over a socketpair via the builtins (rc=0). Full gate GREEN (152/152 functional + extern-c/security/perf/valgrind/fuzz/differential/generics/stdlib/multi-tu). FIXPOINT BYTE-VERIFIED (md5 `a15551b66e157068420e3fd95262f08c`, seed 0.0.117, B==C byte-identical). |
| 0.0.119 | Builtins | concurrency completion: futex + threads | ✅ done | `futex_wait(addr,expected)`/`futex_wake(addr,n)` (sc 202) + `thread_create(fn,arg)`/`thread_join(tid)` (clone sc 56 + per-thread 1MB stack mmap + join-slot mmap). **x86-64 ABI detail:** `thread_create` runs the worker in a `CLONE_VM|CLONE_FS|CLONE_FILES|CLONE_SIGHAND|CLONE_THREAD|CLONE_PARENT_SETTID|CLONE_CHILD_CLEARTID` child that resumes at a trampoline (raw clone resumes child at the post-syscall instruction, parent gets tid). The worker fn index is resolved by codegen via `findfn(worker_name)` and linked (patch type 5 → `fn_symidx[idx]`, R_X86_64_PC32). Worker result is stored to `[r14+8]` (r14=join-slot, reloaded from `[rsp+8]` because the `call worker` clobbers callee-saved r14 as a leaf scratch) and the kernel clears `*slot` on child exit via CLONE_CHILD_CLEARTID, waking `thread_join`'s `futex_wait`. `thread_test.quanta` (worker(7)=107, join returns 107) + `futex_test.quanta` GREEN. Full gate GREEN (152/152 functional + extern-c/security/perf/valgrind/fuzz/differential/generics/stdlib/multi-tu). **Note:** a latent `lsp` helper bug (4-byte disp + wrong REX.R/B) was fixed during this work — it corrupted every `mov r64,[rsp+disp]`; no other call site depended on the broken form. FIXPOINT BYTE-VERIFIED (md5 `8c2ccfdb7388fda3f83ae1d1bd60474b`, seed 0.0.118, B==C byte-identical). |
| 0.0.120 | Builtins | `stack_frames` full unwind | ✅ done | `stack_frames()` (0.0.120) returns a qword-array of return addresses by walking the full rbp frame chain. Each frame's return address = `[rbp+8]`; saved caller rbp = `[rbp]`; following `[rbp]` walks to the caller. A candidate return address is accepted only if `CODE_VBASE(0x400000) <= rax < g_code_end` (g_code_end = CODE_VBASE+codelen, written into the internal-global data slot by write_elf); otherwise the walk terminates (defends against the entry stub's `rbp=argv` frame whose `[rbp+8]` is not a code pointer — the entry stack is relocated to a fresh 8MB mmap, so its rbp base is a low address like 0x202). Capacity capped at 64 frames. Array layout matches str_split: `[arr]=count`, element i at `[arr+8+i*8]`. Floor guard `cmp r11,0x1000; jb done` stops before dereferencing a non-frame rbp. No per-call instrumentation → fixpoint-safe. Gated `stack_frames_test.quanta` (deep chain deep1→deep2→deep3→stack_frames unwinds 4 real return addresses, all in code range; rc=0) GREEN. FIXPOINT BYTE-VERIFIED (md5 `07e58edb4d44a300166b2161533a1258`, self-host build == self-host rebuild byte-identical). `stack_trace()` (0.0.113) remains for single-frame use. |
| 0.0.121 | Lang | closures: by-ref capture | ✅ done | **By-ref closure capture (0.0.67 was by-value-only).** A closure can now mutate an enclosing local: captured vars are passed as `&enclosing_slot` pointers in the heap env, read via `IR_CAPREAD` (deref through env into the outer frame) and written via `IR_CAPWRITE` (store back through the pointer). Implemented `IR_CAPREAD=82`, `IR_CAPWRITE=83`, `IR_CLOSURE=81`. Prologue now saves the incoming env pointer (r10) to a reserved frame slot when `ncaps>0`; `nv()` clears the per-vreg capture tag; `parse_assign`/body reads route a captured var to CAPREAD/CAPWRITE via `cap_find`. **Escape hazard (0.0.121 safety gate):** returning or storing a closure that captures a *stack-local* of its defining function would dangle — `check_closure_escape_ci` (deferred until all bodies parsed, because captures register lazily) rejects it at compile time with `error: by-ref closure escapes a stack-local (dangling pointer)`. Capturing a *param* is safe (param lives in the caller's frame) and is allowed. Gated: ca1/ca2/ca3/clo_wr/clo1/clo2/clo3/closure_capture/cw1/closure_dbg/closure_byref_test (all PASS; ca2 `n=n+1`→1, clo1→102, clo_wr→8). **Fixpoint:** 0.0.121 source self-hosts stage1==stage2 byte-identical (md5 `d8a6d1333ee6ca0a7fb1ee21f83e9d98`, seed 0.0.120). Note: nested `fn name(){}` *returned/escaped* from a function still hits a pre-existing parser loop (unrelated to by-ref capture; \\|x\\| lambdas are the canonical escape syntax and work). |
|| 0.0.122 | Linker | extern "C" standalone EXE (PLT/GOT via `ld`) | ✅ done (workaround) | **Standalone extern-C EXE via external `ld` (not pure Quanta).** `qc --emit-obj` emits relocatable `.o` with `R_X86_64_PLT32` UNDEF relocs; `scripts/quanta_link.sh` drives `ld` (`-lc`, `--dynamic-linker /lib64/ld-linux-x86-64.so.2`). String-arg header skip works. Gated: `extern_c_ffi.quanta` links under both `gcc -nostartfiles` and `ld` → both GREEN. **Fixpoint trap:** hand-rolling dynamic ELF (PT_INTERP/PT_DYNAMIC/GOT/PLT) inside `write_elf` was attempted and REJECTED — breaks self-host fixpoint. **Pure Quanta dynamic ELF remains → 0.0.141.** |
| 0.0.123 | Lang | nested named-fn escape (closure fix) | ✅ done | **Closes the one verified gap left after the 0.0.122 gate (every verified gap gets a version):** nested *named* `fn name(){}` defined inside another fn and called/returned errors `undeclared function: name` (reproduced 0.0.122: `fn make(){ let f = fn helper():i64 { return 7 }; return f() }` → `error: undeclared function: helper`). Fixed in `method.quanta` `parse_primary`: a value-position `fn NAME(params){body}` (guarded so it never fires at statement start / tokp=0 pre-passes, and never touches the `fn func1(){}` definition form or the fn-less `func1(){}` SIMPLE-SURFACE shorthand) is now a named closure — routed through `reg_closure` (parent = enclosing fn), params bound into local scope, captures discovered, emits `IR_CLOSURE`. Gated by `closure_named_fn.quanta` (rc=0: single + double-nested + capture-outer-var cases). Does NOT break either definition syntax (verified regressions). **Known limitation (pre-existing, lambda-equivalent, NOT a 0.0.123 regression):** self-recursion *by name* inside the closure body (`fact(n-1)` calling `fact`) still errors `undeclared function: fact` — identical to lambda self-recursion (`f(n-1)`), a separate closure-self-call gap. NOTE: multi-arg extern-C (`strcmp(a,b)`, already gated) and the security KNOWN-issue items were investigated and found ALREADY WORKING — not gaps. **Fixpoint VERIFIED:** seed 0.0.122 builds 0.0.123 source → gen1==gen2 byte-identical (md5 `d9027d0504269e3a8deed5593115de51`). |
| 0.0.124 | Concurrency safety | thread_create/futex hardening (AUDIT_ROADMAP Part D) | ✅ done | **Closes verified security gaps from `AUDIT_ROADMAP.md` Part D (every verified gap gets a version):** FIX-0.0.35 (join-slot `mmap` MAP_FAILED guard), FIX-0.0.36 (child-stack `mmap` MAP_FAILED guard), FIX-0.0.37 (`futex_wait`/`futex_wake` negative-errno → 0 clamp, verified `futex_wake(0,1)` rc 242→0), FIX-0.0.38 (`clone` failure path: `munmap` both mappings + `exit(1)`), FIX-0.0.40 (child-stack `mprotect` guard page), FIX-0.0.47 (added `futex_wait_test.quanta`). Findings FIX-0.0.39 (join race) / 41 (futex timeout) / 42 (capture O(n²)) / 48 (64-frame cap) re-verified as STALE/not-defects/code-verified. Built from 0.0.123 seed; **gate 157/157 GREEN**; **self-host fixpoint BYTE-VERIFIED** (gen1==gen2==golden, md5 `2f579f42bd56995a822033a9baa8ed67`). |

**The final cores in the 0.0.x concurrency series (0.0.87→0.0.124):** 0.0.115 (security hardening, ✅), 0.0.116 (audit close-off #2), 0.0.117 (`big` completion), 0.0.118 (net send/recv), 0.0.119 (futex + threads), 0.0.120 (stack_trace full unwind), 0.0.121 (closures by-ref capture), 0.0.122 (extern "C" standalone EXE), 0.0.123 (nested named-fn escape fix), 0.0.124 (thread_create/futex concurrency hardening) — **no-deferral policy, every verified gap got a version.** **Cores RESUME at 0.0.125** (per 2026-08-30: cores do NOT go into 0.1.0; continue 0.0.125+ one feature per version until done). 0.1.0 = post-core STABLE. PTY (0.0.127, right after process) + borrow-check (0.0.138, hardest, last) are cores in this chain; `fs` ops (0.0.129), extern-C variadic (0.0.130), closure self-recursion (0.0.131) are partial-core completions.

**POST-0.1.0 (no version reserved):** ARM64 backend (new backend, POST-0.1.0). The Quanta-native code-writing tool is now the **first Quanta App** (`chain`), built ON 0.1.0 — not a compiler core (2026-08-30).



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
AFTER all 0.0.125–0.0.138 cores are done (0.1.0 = post-core STABLE).
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

### Current status (0.0.133 — live)

**0.0.133 (stable seed):** SHA3-256 foundation. IR_CAP=1B/40GB, TOK_CAP=48M/1.92GB, CODE_CAP=512MB, fn_btok fix for bare function declarations (`fn foo();` terminates at `;` without body). All 11 gate layers GREEN (functional 163/163, extern-c, extern-ld, security, performance, valgrind, fuzz, differential, generics, stdlib 8/8, multi-tu 3/3). Self-host fixpoint byte-verified. Built from 0.0.132 seed.

**0.0.134 (current stable, live):** `secure` — full FIPS 202: SHA3-224/256/384/512 + SHAKE128/256. Modular split: 6 modules (`sha3_constants`, `sha3_theta`, `sha3_rhopi` (fixed Pi perm), `sha3_chi`, `sha3_keccak_f`, `sha3_hash`) + re-export via `std/secure`. Compiler fixes: funcscan bare extern fn + builtin detection, entry.quanta ModR/M fix, lexer u8/u16/u32/u64 as TT_KEY, malloc builtin. All 11 gates GREEN (stdlib 9/9). Self-host fixpoint byte-verified. Built from 0.0.133 seed.

**0.0.135 (current stable, live):** `secure` — AES-GCM (TLS 1.3 AEAD) + full FIPS 202 SHA3/SHAKE. Modular: 7 modules (`sha3_constants`, `sha3_theta`, `sha3_rhopi` (fixed Pi perm), `sha3_chi`, `sha3_keccak_f`, `sha3_hash`, `aes_gcm`), re-exported via `std/secure`. AES-GCM test compiles via `--emit-obj + ld` (token limit for single-TU); SHA3 tests compile directly. Self-host fixpoint BYTE-VERIFIED (md5 `1641c0b7195969ce4026846bc94583bb`).

Next core = **0.0.136** (`self-sufficiency` — native `printf` / variadic formatting (FIX-0.0.50) — replace libc `printf`). 0.1.0 = **100% self-sufficient STABLE**.

### Historical stable seeds (completed):

**0.0.134 (stable seed):** `secure` — full FIPS 202: SHA3-224/256/384/512 + SHAKE128/256. Modular split: 6 modules + re-export via `std/secure`. Compiler fixes: funcscan bare extern fn + builtin detection, entry.quanta ModR/M fix, lexer u8/u16/u32/u64 as TT_KEY, malloc builtin. All 11 gates GREEN (stdlib 9/9). Self-host fixpoint byte-verified. Built from 0.0.133 seed.

**0.0.133 (stable seed):** SHA3-256 foundation. IR_CAP=1B/40GB, TOK_CAP=48M/1.92GB, CODE_CAP=512MB, fn_btok fix for bare function declarations. All 11 gate layers GREEN (functional 163/163, extern-c, extern-ld, security, performance, valgrind, fuzz, differential, generics, stdlib 8/8, multi-tu 3/3). Self-host fixpoint byte-verified. Built from 0.0.132 seed.

**0.0.132 (stable seed):** `json` stdlib (AI/data interchange). `import std/json` provides `json_parse(s)` → tagged heap-node tree and `json_stringify(j)` → Quanta string. Gate: functional 163/163, stdlib 8/8, multi-TU 3/3, all 11 layers GREEN. Fixpoint byte-verified (md5 `8e1bb23fc7e626ee4b8513dc690197c1`). Built from 0.0.131 seed.

**0.0.131 (stable seed):** closure self-recursion by name (partial core). Self-name bound as real enclosing local type-11 + captured into body; self-call routes via IR_CLOSURE_CALL. Gate: functional 163/163, stdlib 7/7, multi-TU 3/3, all 11 layers GREEN. Fixpoint byte-verified (md5 `8e1bb23fc7e626ee4b8513dc690197c1`). Built from 0.0.130 seed.

**0.0.130 (stable seed):** extern-C variadic (partial core). Variadic decl + args 0–5 in regs, 6+ spill after rsp-align. `extern_var_test.quanta` sentinel EXTERN_VAR_OK, both gcc + gcc-free ld. Fixpoint byte-verified (md5 `85f4122ae7b9626fe529d2b94eb79158`). Gate 162/162 GREEN. Built from 0.0.129 seed.

### 0.0.125→0.162 (core sequence — cores do NOT go into 0.1.0; ALL PARTIAL cores first after `process`, then AI/QC-era crypto foundations, then TLS/hybrid, then classical/hardest):

| Version | Domain | Core |
|---------|--------|------|
| 0.0.125 | `time` | clock/now/sleep/nanosleep |
| 0.0.126 | `process` | fork/exec/wait/kill |
| 0.0.127 | `pty` | open/slave/name/dup2/ioctl |
| 0.0.128 | `big` | div-by-zero guard (FIX-0.0.19) |
| 0.0.129 | `fs` | missing ops (stat/unlink/mkdir/chdir/rename/rmdir) |
| 0.0.130 | `lang` | extern-C variadic (partial core) |
| 0.0.131 | `lang` | closure self-recursion by name (partial core) |
| 0.0.132 | `lang` | `json` (data/AI interchange) |
| 0.0.133 | `lang` | SHA3-256 foundation (IR/TOK/CODE caps, fn_btok fix) |
| 0.0.134 | `secure` | full FIPS 202: SHA3-224/256/384/512 + SHAKE128/256 |
| 0.0.135 | `secure` | AES-GCM (TLS 1.3 AEAD) |
| 0.0.136 | `self-sufficiency` | Native `printf` / variadic formatting (FIX-0.0.50) |
| 0.0.137 | `self-sufficiency` | Quanta-native ELF linker (FIX-0.0.51) |
| 0.0.138 | `self-sufficiency` | Remove `gcc` from CI (FIX-0.0.53) |
| 0.0.139 | `self-sufficiency` | `qc --link` built-in replaces `quanta_link.sh` (FIX-0.0.54) |
| 0.0.140 | `self-sufficiency` | Static PIE option (FIX-0.0.55) |
| 0.0.141 | `secure` | X25519 (ECDH for TLS 1.3) |
| 0.0.142 | `secure` | ML-KEM (FIPS 203, Kyber) + hybrid X25519+ML-KEM KEM |
| 0.0.143 | `secure` | ML-DSA (FIPS 204, Dilithium) + hybrid X25519+ML-DSA sig |
| 0.0.144 | `secure` | SLH-DSA (FIPS 205, SPHINCS+) |
| 0.0.145 | `secure` | TLS 1.3 handshake (hybrid PQC) |
| 0.0.146 | `quic` | HTTP/3 (UDP+TLS 1.3, hybrid PQ) — modern transport, ahead of HTTP/2 |
| 0.0.147 | `http` | HTTP/2-over-TLS (no plaintext shipped) |
| 0.0.148 | `ai` | tensor ops + inference (AI-age, promoted into core chain) |
| 0.0.149 | `lang` | generics type constraints (FIX-0.0.33; `where` bounds enforced) |
| 0.0.150 | `lang` | borrow-check (language safety pass) — core, hardest |
| 0.0.151 | `secure` | X.509 / PKI — ASN.1 DER parser, cert chain validation, SAN/IP/CN, expiry, revocation (CRL/OCSP), trust store, cert/key PEM/DER load/save |
| 0.0.152 | `secure` | Certificate Transparency — SCT parsing/verification (RFC 6962), log list management, inclusion proof verification, stapled SCT validation |
| 0.0.153 | `secure` | OCSP Stapling — server-side OCSP response fetch, caching, stapling in TLS handshake, client-side verification |
| 0.0.154 | `secure` | TLS Resumption — session tickets (RFC 5077), PSK (RFC 8446), 0-RTT with replay protection |
| 0.0.155 | `secure` | mTLS / SPIFFE — X.509-SVID / JWT-SVID parsing, workload identity, trust domain federation, automatic rotation via SPIRE agent API |
| 0.0.156 | `secure` | Hardware Security Module — PKCS#11 (Cryptoki) interface, TPM 2.0 (ESAPI), secure enclave (SGX/SEV) attestation, key generation/storage/signing in HSM |
| 0.0.157 | `secure` | Key Derivation / Secrets at Rest — Argon2id (RFC 9106), Scrypt, PBKDF2, HKDF (RFC 5869), encrypted keystore (AES-256-GCM + Argon2id), key rotation policies |
| 0.0.158 | `secure` | Side-Channel Hardening — constant-time comparators (all PQC ops), masking/blinding for ML-KEM/ML-DSA/SLH-DSA, cache-line alignment, timing-safe memory access |
| 0.0.159 | `secure` | Audit & Tamper-Evident Logging — Merkle-tree log (RFC 6962), Trillian-compatible, signed checkpoints, inclusion/consistency proofs, sigstore/cosign integration |
| 0.0.160 | `secure` | Supply Chain Security — in-toto/SLSA provenance, sigstore/cosign signing & verification, reproducible build attestation, SBOM (SPDX/CycloneDX) generation |
| 0.0.161 | `secure` | Compliance Artifacts — FIPS 140-3 Level 1 module boundary, Common Criteria EAL4+ evidence, ISO 27001 control mapping, NIST 800-53 traceability |
| 0.0.162 | `secure` | Policy Engine — OPA/Rego-compatible policy language, runtime evaluation (TLS config, cert pinning, cipher suite enforcement, mTLS requirements), audit trail |
| 0.0.163 | `ai` | LLM Foundations — RoPE (rotary position embeddings), RMSNorm, SwiGLU/GeGLU, Grouped-Query Attention (GQA), Multi-Query Attention (MQA) |
| 0.0.164 | `ai` | Autoregressive Decoding — KV cache (paged/continuous), sliding window attention, speculative decoding (draft+verify), prefix caching |
| 0.0.165 | `ai` | Fused Kernels & Mixed Precision — FlashAttention-2/3 (tiling, online softmax), BF16/FP16 tensor cores (WMMA/PTX), quantization (GPTQ/AWQ/INT4/INT8 per-channel), kernel fusion (bias+act+dropout) |
| 0.0.166 | `ai` | Memory Optimization — Gradient checkpointing (activation recomputation), activation offloading (CPU/NVMe), ZeRO-1/2/3 (optimizer/grad/param sharding), pipeline parallelism |
| 0.0.167 | `ai` | Distributed Training — NCCL-compatible all-reduce/all-gather/reduce-scatter/broadcast, ring/tree/butterfly topologies, FSDP (fully sharded data parallel), tensor parallelism (column/row), sequence parallelism |
| 0.0.168 | `ai` | Tokenization — BPE (byte-pair encoding), WordPiece, Unigram, SentencePiece, TikToken-compatible, fast Rust-style tokenizer (SIMD), chat templates (HuggingFace/llama.cpp) |
| 0.0.169 | `ai` | Training Infrastructure — Cosine/warmup/linear/constant LR schedulers, gradient accumulation, gradient clipping (norm/value), EMA weights, mixed precision (AMP), loss scaling, checkpointing (sharded/distributed) |
| 0.0.170 | `ai` | Model Architecture Library — LLaMA/Gemma/Qwen/Mistral/Phi/GPT-2/3/NeoX/BERT/T5/Whisper configs, weight tying (embed↔output), RoPE scaling (NTK/YaRN/LongRoPE), sliding window (Mistral), ALiBi |
| 0.0.171 | `ai` | Inference Engine — Continuous batching, paged attention (vLLM-style), prefix caching, chunked prefill, structured output (JSON schema guided decoding), speculative decoding (EAGLE/Medusa), TensorRT-LLM compatible |
| 0.0.172 | `ai` | ONNX / Export — ONNX opset 18+ export/import, dynamic axes, quantization annotation (QDQ), TensorRT / CoreML / ORT / llama.cpp GGUF conversion |
| 0.0.173 | `chain` | Blockchain Core — UTXO model + account model, Merkle-Patricia Trie (MPT), RLP/SSZ serialization, Patricia proofs, state root computation, bloom filters |
| 0.0.174 | `chain` | Consensus — BFT (Tendermint/CometBFT), Nakamoto (PoW/PoS), Gasper (Ethereum PoS), Casper FFG, HotStuff, Narwhal/Tusk, consensus-critical types |
| 0.0.175 | `chain` | Smart Contract VM — EVM (EIP-1559, Shanghai, Cancun), WASM (Wasmi/Wasmtime-compatible), RISC-V (CKB-VM), FuelVM, MoveVM, gas metering, precompiles |
| 0.0.176 | `chain` | Cryptography — BLS12-381 (pairing, aggregation), BN254, secp256k1 (libsecp256k1-compatible), Ed25519, Poseidon hash, KZG commitments, Verkle trees |
| 0.0.177 | `chain` | Networking — libp2p (GossipSub, Kademlia, identify, ping), devp2p (RLPx), QUIC transport, peer scoring, NAT traversal (ICE/STUN/TURN), DHT |
| 0.0.178 | `chain` | Storage — LSM-tree (RocksDB-compatible), snapshots, pruning, archive nodes, state sync (fast/snap/warp), erasure coding, light client proofs |
| 0.0.179 | `chain` | Standards — ERC-20/721/1155/4337/4844, EIP-1559/2930/4844, CAIP-2/10/19, SLIP-44, BIP-32/39/44/85, multisig (Safe/Gnosis), account abstraction |
| 0.0.180 | `quantum` | Quantum Algorithms — QFT, Grover, Shor (factor/dlog), VQE, QAOA, Hamiltonian simulation, quantum error correction (surface code, Steane, color codes) |
| 0.0.181 | `quantum` | Quantum-Safe Standards — NIST PQC migration (hybrid KEM/sig), CNSA 2.0, RFC 9180 (HPKE), RFC 9380 (HPKE for PQC), IETF PQC transitions |
| 0.0.182 | `quantum` | Quantum Networking — BB84/QKD (E91, MDI-QKD), entanglement swapping, quantum repeaters, quantum internet protocols (CQC, SQNP) |
| 0.0.183 | `lang` | Effect System — algebraic effects/handlers, async/await as effect, linear types (affine/uniqueness), region-based memory, capability types |
| 0.0.184 | `lang` | Dependent Types — Pi/Σ types, type-level computation, proof terms, refinement types, SMT-backed verification (Z3/CVC5), liquid types |
| 0.0.185 | `lang` | Metaprogramming — compile-time reflection, AST macros, procedural macros, const eval (full interpreter), JIT (Cranelift/LLVM), incremental compilation |
| 0.0.186 | `lang` | Package Manager — `chain` (first Quanta App): dependency resolution (SAT solver), lockfiles, reproducible builds, workspace/monorepo, private registries, cargo-compatible |
| 0.0.187 | `math` | Linear Algebra (Full) — BLAS/LAPACK parity: LU/QR/Cholesky/SVD/Eig/Schur, sparse (CSR/CSC, ARPACK), iterative (CG/GMRES/BiCGSTAB), batched, GPU offload (CUDA/HIP) |
| 0.0.188 | `math` | Numerical Analysis — quadrature (Gauss-Legendre/Clenshaw-Curtis/adaptive), ODE (RK4/5, Dormand-Prince, Rosenbrock, BDF, symplectic), PDE (FDM/FEM/FVM, spectral), root-finding (Brent, Newton, homotopy), optimization (BFGS/L-BFGS, trust-region, SQP, interior-point, derivative-free) |
| 0.0.189 | `math` | Statistics & Probability — distributions (continuous/discrete/multivariate), MLE/MAP/Bayesian inference, MCMC (NUTS/HMC/Gibbs), variational inference, hypothesis testing, bootstrap, regression (OLS/GLM/quantile/robust), time series (ARIMA/state-space/GARCH) |
| 0.0.190 | `math` | Signal Processing — FFT (Cooley-Tukey/Bluestein/prime-factor, real/complex, NTT), filter design (FIR/IIR, Parks-McClellan, Butterworth/Chebyshev/Elliptic), wavelets (DWT/CWT, Daubechies/Coiflet/Symlet), spectrogram/STFT/mel, resampling |
| 0.0.191 | `math` | Computational Geometry — convex hull (QuickHull/Chan), Delaunay/Voronoi (CGAL-parity), polygon ops (Boolean, triangulation, offset), KD-tree/R-tree/quadtree, nearest neighbor, mesh generation (tetrahedral, surface) |
| 0.0.192 | `math` | Graph Algorithms — shortest path (Dijkstra/A*/Contraction Hierarchies), flow (Dinic/Push-Relabel), MST (Kruskal/Prim/Borůvka), matching (Hopcroft-Karp/Blossom), centrality (PageRank/betweenness/closeness), community (Louvain/Infomap), graph BLAS |
| 0.0.193 | `math` | Number Theory — primality (AKS/Miller-Rabin/BPSW), factorization (Pollard Rho/ECM/MPQS/GNFS), discrete log (index calculus), elliptic curves (Weierstrass/Edwards/Montgomery, pairings), modular forms, lattice basis reduction (LLL/BKZ) |
| 0.0.194 | `math` | Symbolic Math — expression trees, simplification, pattern matching, differentiation (forward/reverse auto-diff + symbolic), integration (Risch), equation solving (Groebner basis, cylindrical algebraic decomposition), term rewriting, MathML/LaTeX export |
| 0.0.195 | `math` | Special Functions — Gamma/Beta/Zeta/Polygamma, Bessel (J/Y/I/K), hypergeometric (1F1/2F1/pFq), orthogonal polynomials (Legendre/Chebyshev/Hermite/Laguerre), error functions, Airy, elliptic integrals, Lambert W |
| 0.0.196 | `math` | Interval & Verified Computing — interval arithmetic (IEEE 1788), affine arithmetic, Taylor models, validated ODE/PDE, global optimization (branch-and-bound), rigorous enclosures |
| 0.0.197 | `math` | Financial Mathematics — Black-Scholes/Merton/Heston, Greeks, binomial/trinomial trees, Monte Carlo (quasi-random, importance sampling), XVA (CVA/DVA/FVA), interest rate models (Hull-White/LMM/SABR), fixed income analytics |
|| 0.1.0 | STABLE | **100% self-sufficient, zero external dependencies** — `ldd qc` → `not a dynamic executable`; `readelf -d qc` → no `libc.so.6`; CI uses only `qc`. `chain` = first Quanta App (0.1.1+); `physics` optional 0.1.1+. |

**0.0.117 (prior stable seed):** `big` completion. Ordering (`< > <= >=`) + bitwise (`& | ^ << >>`) routed to sign-aware `big_cmp`/`big_and`/`big_or`/`big_xor`/`big_shl_signed`/`big_shr_signed`. **Also fixed: `big_add`/`big_sub`/`big_mul` were MAGNITUDE-ONLY** (negative operands silently miscomputed — e.g. `(-5)+3`→8) — now sign-aware via `big_add_signed`/`big_sub_signed`/`big_mul_signed`; `+ - *` operators route to them. `: big` annotation with int-literal RHS now promotes via `big_from_i64`. Gate: **152/152 functional + 7/7 stdlib + 3/3 multi-tu + extern-c/security/perf/valgrind/fuzz/differential/generics (all GREEN)**. **Self-host fixpoint BYTE-VERIFIED** (md5 `8b8a1e21573f12b5742a64f695a50b85`).

**0.0.103 (historical stable seed):** GATE-ONLY copy of 0.0.102 — no source change. Float builtins (`sin/cos/tan/pow/log/min/max/sqrt/floor/ceil/abs`) already implemented (emit_bltn P6.1a) and covered by the core float gate. Full 7-layer gate + generics-negative all GREEN (functional 136/136 core, extern-c, security 8/8, perf 3/3, valgrind clean, fuzz fail-closed, differential consistent). Self-host fixpoint byte-identical (B==C md5 `1458d4683ff3bc5097fb0e2ab0de43e1`, verified 2026-08-27). The 0.0.102 binary (`compiler/0.0.102/bin/x86/qc`) is the build seed for 0.0.103.

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
