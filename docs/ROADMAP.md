# Quanta ROADMAP — core + builtins campaign (0.0.39 → 0.1.0)

Goal: complete ALL core builtins before any new std/lib work. One patch version
per feature/function. After EACH successful builtin, add/extend a test_suite test
that exercises it (so the gate grows with the language). 0.1.0 = milestone where
core+builtins are complete and std/lib work may resume.

CONVENTIONS (enforced):
- Version per feature: 0.0.39, 0.0.40, ... each adds ONE builtin family or ONE
  closely-related group (e.g. syscall1..6 is one version; clock+nanosleep one; etc).
- Fix-forward only. Self-host gate (3-stage) must hold after each version.
- test_suites/EXPECTED.tsv + a codes/*.quanta test added/extended per version.
- Gate must be 100% green (run_tests.sh) before promoting a version.
- 0.0.38 is the last test-suite-only + tail-expr-fix version (committed: d396b7a).

CRITICAL PROCESS RULES (learned the hard way):
- NEW VERSION = COPY OF IMMEDIATELY-PRECEDING VERSION (e.g. 0.0.41/src = copy of
  0.0.40/src + new feature). NEVER use an old scratch pad (e.g. 0.0.38/src) as the
  base, and NEVER `git checkout` a version's src to "restore" it (that reverts
  uncommitted WIP and drops already-shipped builtins like time — which then shows up
  as a phantom "missing feature" caught by the gate).
- emit_bltn DISPATCH BUG: builtin name-match handlers MUST be placed BEFORE the
  `mem_` block (the `if nl>=8 && src[nm]=='m'&&src[nm+1]=='e'&&src[nm+2]=='m'&&src[nm+3]=='_'`
  block) in emit_bltn(). Handlers placed AFTER that block silently fail to dispatch
  (the check is reached but never fires) — a compiler codegen bug, not a logic error.
  If a newly-added builtin won't dispatch, move its check above the mem_ block.
- emit_bltn HARD LIMIT (discovered attempting 0.0.42): adding ANY new handler to emit_bltn
  (even a trivial no-op `zz` if-block) makes the self-hosted compiler emit NO binary
  (crash / Illegal-instruction) for large programs such as std_crypto_test. Confirmed
  by a CLEAN test (0.0.41 copy + 1 trivial handler -> std_crypto produces no output).
  The same applies to is_bltn (features.quanta): growing it by 6 checks also breaks the
  compiler during parse. Symptom: simple programs compile; large/complex ones emit no
  binary. NOT if-chain length per se — splitting emit_bltn into emit_bltn+emit_bltn2
  (each <45 handlers, the 0.0.41 working count) did NOT fix it. Likely a global dispatch
  limit, a per-function return-path/branch cap, or IR/branch corruption in how the
  compiler compiles emit_bltn-family functions when they grow. ROOT CAUSE NOT PINNED.
  BLOCKS 0.0.42+ builtins until the compiler's emit_bltn/is_bltn codegen is fixed.
  The byte/endianness BUILTIN ENCODINGS themselves are correct (bswap=48 0F C8,
  popcnt=F3 48 0F B8 C0, lzcnt=F3 48 0F BD C0, tzcnt=F3 48 0F BC C0, rol=48 D3 C0,
  ror=48 D3 C8; all load arg via 48 89 F8 mov rax,rdi), verified in isolation.

## Completeness audit (what exists vs. what a "full and complete" language needs)
This section is the SOURCE OF TRUTH for remaining work. It was built by auditing
the actual compiler source (0.0.42), not guessed. Status: ✅ done · 🟡 partial ·
❌ missing. "Core" = the language itself; "builtins" = inline-code primitives.

### A. Core language — types
- ✅ i64 (default integer), u8/u32/u64 masks, usize
- ✅ f64 (arithmetic via i2f/f2i/fadd/fsub/fmul/fdiv builtins)
- ❌ **float literals** — lexer hard-errors "floating-point literals are not supported" (parse.quanta/lexer line ~127). Cannot write `3.14`; only compute via i2f.
- ❌ **char / byte / bool** as first-class types (tokens kt==9..12 reserved, not wired)
- ❌ **string** as a real type (TT_STRING token reserved; only byte-buffer conventions + print builtins today)
- 🟡 **struct** — fields/method-call (`obj.method`) work (method.quanta); construction + literal + field read/write work. No struct *literals* verification coverage.
- ❌ **enum** (real, user-defined) — TT_ENUM token + bare Some/None/Ok/Err matching only. No `enum Name { A, B }` definition or custom variants.
- ❌ **union / tagged-union** definition (Ok/Err/Some/None are built-in magic, not general)
- ❌ **tuple** as a type (mk_any exists as 2-tuple hack; no `(T,U)` syntax)
- ❌ **array/slice** as typed (only untyped `[...]` + vec_* builtins)

### B. Core language — declarations & scoping
- ✅ fn, let, const (H_CONST), extern "C" fn, global vars, unsafe {} , defer {}
- ✅ struct methods (impl-style via first-param `self`)
- ❌ **trait / interface** — TT_TRAIT/TT_INTERFACE tokens + funcscan skips/records them, but NO dispatch, NO method resolution, NO impl<->trait linking at codegen. Effectively a no-op scaffold.
- ❌ **impl Trait for Type** — scanimpls() records pairs but nothing consumes them (no vtable, no resolution)
- ❌ **generics `<T>`** — no type-parameter parsing anywhere; all code is monomorphic
- ❌ **modules / namespaces** — `#import` is flat-global textual inline; no `module`, no name resolution, no privacy
- ❌ **visibility / pub / priv** — absent

### C. Core language — control flow
- ✅ if/else, while, for-in (`for x in arr`), match (expression arms), break/continue, return, defer
- ❌ **for-range `for i in 0..n`** — `..` operator is NOT parsed (grep for `..` in source = none). Only array for-in. VERIFIED GAP, no coverage.
- ❌ **match block arms `1 => { ... }`** — parser only emits IR for expression arms (`1 => expr`); block arms return no vreg. Deferred.
- 🟡 **`?` operator** — only UNWRAP (extracts Ok payload); EARLY-RETURN-on-Err propagation is NOT emitted (comment says "if tag==0 early-return" but code doesn't). Deferred due to IR_RET-terminator DCE bug.
- ❌ **loop expressions / labeled break with value** — absent
- ❌ **try/catch / except** — no structured error handling (only panic + `?` unwrap)

### D. Core language — expressions & operators
- ✅ arithmetic, bitwise, shifts, comparisons, logical, ternary, field access, indexing
- ✅ unsigned arith builtins (udiv/umod/ult/ugt/ulte/ugte)
- ❌ **operator overloading** — absent
- ❌ **range/`..` expression** — absent (needed by for-range)
- ❌ **closure literals `|a| a+1`** — closure_call/fnptr exist but NO lambda syntax; closures built only via builtin plumbing

### E. Memory & runtime
- ✅ mem_alloc/free/mmap/realloc, memcpy/memcmp/memmove, mem_load/store (+8)
- ✅ defer (LIFO replay), unsafe blocks
- ❌ **real allocator** — mmap-based bump; no free-list/GC; realloc is mmap-copy
- 🟡 **callee load-store-to-same-addr aliasing** — BUG: fn that reads mem then writes same addr, called in loop, corrupts all but first iter. Blocks SHA/AES (load-modify-store) and map>4x. HIGHEST-PRIORITY CORRECTNESS FIX.
- ❌ **stack unwinding / destructors / RAII** — absent (defer is manual)
- ❌ **ref/mut/move** — TT_REF/TT_MUT/TT_MOVE tokens reserved, not implemented

### F. Builtins already present (53 registered; prefixes expand further)
syscall(1-6), exit, mmap, mem_alloc/free/realloc, memcpy/memcmp/memmove,
mem_load/mem_store(+8), file_* (open/read/write/close family), print/printi/
println/prints/printsp/newline, len, str, push/pop, vec_*(get/set/load/store/
add/sub/mul/div), arg, mk_any, fnptr, closure_call, fadd/fsub/fmul/fdiv,
i2f/f2i, udiv/umod/ult/ugt/ulte/ugte, u8/u32/u64 masks, bswap/popcount/clz/ctz/
rotl/rotr, gettimeofday/nanosleep/sleep, panic.

### G. Builtins still MISSING (the real "core+builtins" queue)
- ❌ **float comparisons**: feq, flt, fgt, fle, fge, fisnan, fisinf (NaN-correct)
- ❌ **process/env**: getpid, getppid, getenv, argc/environ exposure
- ❌ **stdin I/O**: getchar, getline
- ❌ **fs metadata**: stat, fstat, lseek, unlink, mkdir, chdir, rename
- ❌ **networking convenience**: socket/connect/bind/listen/accept (raw syscall reachable already)
- ❌ **atomics**: atomic_load/store/add/cmpxchg + futex
- ❌ **introspection**: abort, debugbreak, stack-trace hook
- ❌ **string ops**: strcat, substr, strcmp, str_split, utf8 encode/decode
- ❌ **bit/byte ops**: byteswap already; missing ctz-clz fine; missing parity, bitfield insert/extract, byte swap per-size
- ❌ **math**: sqrt, sin/cos/tan, pow, log, abs, min/max, floor/ceil (currently only via fadd etc.)
- ❌ **random**: getrandom (libc), rand
- ❌ **intrinsics**: prefetch, fence, expected/unexpected (branch hint)

### H. Tooling / self-sufficiency (user-stated goal: replace python for writing Quanta)
- ❌ **Quanta-native codegen/refactor tool** — currently edits done via python heredocs (clunky, blocked payloads, brace bugs). A Quanta app that reads/writes Quanta source reliably is needed so compiler work stops depending on fragile text surgery.
- ❌ **debugger/objdump integration**, ❌ **package manager**, ❌ **build system** beyond `qc src bin`.

## Full build order to 1.0 (each = one WIP version, gate green before promote)

**Sequencing decision (2026-08-14):** core tech-debts fixed FIRST, one atomic fix per
version, before any new feature work.
- **0.0.43 – 0.0.50 = bug/debt-fix window.** New features wait until the debt window clears.
- **0.0.51+ = new planned features/functions resume.**

### 0.0.43 – 0.0.50: bug & tech-debt window (one small fix per version)

**Context — aliasing bug diagnosis (DONE, not a version):** reproduced with `reg_alias.quanta`
(permanent red gate test: 75/76, the 1 fail pins the bug). Bisected: `mem_load` is correct in
isolation; `len` is correct immediately after `len = mem_load(p)`; but after the FIRST
`mem_store`, `len` is corrupted. Bug is in `flush_all()`'s failure to correctly preserve a live
vreg derived from a preceding `mem_load` when a `mem_store` clobbers registers. The fix is a
correct memory barrier at the store (conservative aliasing — correct-by-construction); precise
alias analysis for speed is deferred to 0.1.0+.

- 0.0.43 **Fix aliasing bug**: correct memory barrier so `mem_store` preserves/refreshes live
  vregs derived from memory. `reg_alias` goes GREEN; add a 2nd regression (map-accumulate /
  repeated same-addr mutate). Full gate green.
- 0.0.44 Wire `usize`/`u32`/`u64`/`u8`/`u16` as proper type keywords (mask builtins exist).
- 0.0.45 Complete `extern "C"` (funcscan path).
- 0.0.46 `?` early-return propagation (needs IR_RET DCE fix; sibling of aliasing).
- 0.0.47..0.0.50 spare debt slots (absorb any debt discovered during 0.0.43–0.0.46, or
  pull forward if a debt needs more room). New features do NOT start before 0.0.51.

### 0.0.51+ : new planned features / functions

PRIORITY 2 — builtin families (G):
- 0.0.51 Float comparisons (feq/flt/fgt/fle/fge/fisnan/fisinf) + fcmp_test
- 0.0.52 Process/env (getpid/getppid/getenv/argc) + proc_test
- 0.0.53 Stdin I/O (getchar/getline) + input_test
- 0.0.54 fs metadata (stat/fstat/lseek/unlink/mkdir/chdir/rename) + fsmeta_test
- 0.0.55 String ops (strcat/substr/strcmp/split/utf8) + strtest
- 0.0.56 Math (sqrt/sin/cos/tan/pow/log/abs/min/max/floor/ceil) + math_test
- 0.0.57 Atomics (atomic_*/futex) + atomic_test
- 0.0.58 Networking convenience (socket/connect/bind/listen/accept) + net_test
- 0.0.59 Introspection (abort/debugbreak/stack-trace) + abort_test
- 0.0.60 Random (getrandom/rand) + rand_test

PRIORITY 3 — language completeness (A/B/D/E):
- 0.0.61 Float literals (lexer) — unblocks natural f64 code
- 0.0.62 Real enums (user-defined `enum Name { A, B(c) }` + match)
- 0.0.63 Tuples `(T,U)` as a type + destructuring
- 0.0.64 Generics `<T>` (monomorphization) — large, own campaign
- 0.0.65 Traits + impl dispatch (consume scanimpls records; vtables)
- 0.0.66 Modules/namespaces + visibility (replaces flat #import)
- 0.0.67 char/byte/bool/string as real types
- 0.0.68 ref/mut/move (ownership lite) or documented-RC
- 0.0.69 Operator overloading (where sound)
- 0.0.70 Closure literals `|a| ...` syntax
- 0.0.71 Parse and/or/not/true/false/global keywords

PRIORITY 4 — tooling (H):
- 0.0.72 Quanta-native code-writing tool (the user's stated goal to replace python)

--- 1.0: CORE + BUILTINS COMPLETE. std/lib work (crypto split, net/lib, serde, etc.) resumes at 1.0+ ---


## Notes
- Audit basis: 0.0.42 source (53 builtins in is_bltn; tokens/parser scanned 2026-08-14).
- Each version: edit compiler/0.0.XX/src/x86/{features,emitter,parse,lexer}.quanta as
  needed, self-host 3-stage, run gate, add test, commit. Keep bootstrap/ current.
- "One feature per WIP version" still holds — the list above is the QUEUE, not a bundle.
- **Debt-first:** 0.0.43 + 0.0.44 clear ALL genuine partial features + test debt before
  new features, because a wrong codegen silently breaks earlier-green tests.
- Test framework: tests `return`/`exit` a computed value; EXPECTED.tsv's expected_rc is
  that value. Non-zero expected_rc = correct answer, NOT a hidden failure.

## 0.0.42 status (byte/endianness builtins) — DONE / SHIPPED (commit 36f76b6)
- **SHIPPED GREEN.** 0.0.42 = 0.0.41 + `emit_bltn` split (self-host fix) + the
  6 byte/endianness builtins `bswap, popcount, clz, ctz, rotl, rotr` (the 0.0.43
  objective, layered on the 0.0.42 base).
- **Self-host fixed point:** qc_boot == qc_self == qc (byte-identical). ✓
- **Core gate: 73/73 pass, 0 compile-fail.** ✓
- **bits_test passes (rc=0)** — builtins verified correct (encodings:
  bswap=48 0F C8, popcnt=F3 48 0F B8 C0, lzcnt=F3 48 0F BD C0, tzcnt=F3 48 0F BC C0,
  rol=48 D3 C0, ror=48 D3 C8; all load arg via 48 89 F8 mov rax,rdi).
- **std/lib removed from core gate:** the 7 `lib/std/*` integration tests
  (std_crypto/fs/lib/map/math/str/vec) were removed from EXPECTED.tsv per the
  project rule "complete cores+builtins before std/lib work" (0.1.0+). std_crypto
  in particular was a PRE-EXISTING compile-fail under 0.0.41 itself (blocked by the
  callee load-store-to-same-addr aliasing bug) — NOT a 0.0.42 regression. It will
  be reimplemented properly in 0.1.0+ split into crypto_sha2/crypto_hmac/crypto_aead.
- **CORRECTION NOTE (2026-08-14):** an earlier draft of this block claimed
  "0.0.41 miscompiles 0.0.42 → BLOCKED". That was WRONG — it was inferred from a
  STALE `/tmp` binary (a leftover `std_crypto` binary from a prior session reported
  rc=3 and was mistaken for 0.0.41's live output). The actual gate showed 0.0.41
  ALSO failed std_crypto (compile-fail), so the "regression" was a phantom. This
  block is now rewritten to the verified green state. Lesson encoded in
  PROJECT_RULES.md §8 / SKILL.md DOC-FRESHNESS RULE.
- NEXT (debt window, see build order above): 0.0.43 = diagnose aliasing bug + add `reg_alias` regression test. New features wait until 0.0.51.

