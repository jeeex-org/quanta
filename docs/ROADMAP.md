# Quanta ROADMAP — consolidated single source of truth

> **Last updated: 2026-08-25. Current compiler: 0.0.86** (x86-64 ELF emitter,
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
| **P4 tooling** | **0.114** | **Quanta-native code-writing tool** (edit Quanta source reliably without external scripting — the user's stated goal; last core item, sequenced immediately before 0.1.0) |
| **0.1.0** | 0.1.0 | Core + builtins complete → std/lib resumes; borrow-checking target for #1 green; **PTY layer for interactive `$$()` (vi/ssh/top)** |

### Outstanding cores — per-version sequencing (0.0.87 → 0.1.0+)

Every item below is one WIP version: self-hosts (2-stage byte-identical fixed point) and gate-green before promotion. Sequence is lowest-risk-first; the code-writing tool is placed last, after all language cores are closed.

| Version | Core | Item | Status today | Work |
|---------|------|------|--------------|------|
| 0.0.87 | Lang | Gate the std libs | ✅ done | Add `std_crypto_test`, `std_quantum_test`, `std_linalg_test`, `std_vec_test`, `std_fs_test`, `std_math_test` to EXPECTED.tsv; verify green. |
| 0.0.88 | Lang | `u8`/`u16` type keywords | ✅ done | `let x: u8`/`u16` parsed + width_mask codegen. Fixed silent-wrong mask bug: REX.B for r8-r15 result regs + const-fold wrap. mixed_width_mask_test.quanta gates it. |
| 0.0.89 | Lang | `bool`/`char`/`byte` as types | ❌ (keyword+values done) | Parse `let x: bool`/`char`/`byte` as type annotation. |
| 0.0.90 | Lang | `as` cast | ❌ lexed-only | Parse `x as T`; emit width conversion. |
| 0.0.91 | Lang | `raw` / `volatile` | ❌ lexed-only | Parse pointer/volatile qualifiers; codegen. |
| 0.0.92 | Lang | typed array/slice `T[]` | ❌ untyped only | Parse `let a: i64[]`; bound-checked access. |
| 0.0.93 | Lang | range `..` expression | ❌ | Standalone `a..b` range value; feed `for-range`. |
| 0.0.94 | Lang | `where` clause | ❌ lexed-only | Parse `fn f<T>(x:T) where T: Num`; elide today, hook for 0.1.0. |
| 0.0.95 | Lang | `move` / `ref` / `mut` | ❌ tokens reserved | Parse ownership sigils; track in symbol table (enforce at 0.1.0 borrow-check). |
| 0.0.96 | Lang | `String` real type | ❌ byte-buffer only | Promote `string` to first-class type with length-aware ops. |
| 0.0.97 | Lang | try/catch | ❌ panic+`?` only | Parse `try/catch`; unwind to handler. |
| 0.0.98 | Lang | operator overloading | ❌ | Trait-vtable dispatch for `op` fns (needs trait dispatch from P3). |
| 0.0.99 | Lang | generics monomorphisation | 🟡 type-erased | Instantiate `map<T,U>` per type-args; compile-time checks. |
| 0.100 | Builtins | float math (sin/cos/tan/pow/log/min/max) | ❌ | Add builtins; gate `std_math_test`. |
| 0.101 | Builtins | string ops (strcat/substr/strcmp/str_split/utf8) | ❌ | Add builtins; gate `std_str_test`. |
| 0.102 | Builtins | atomics (load/store/add/cmpxchg+futex) | ❌ | Add builtins; gate `atomic_test`. |
| 0.103 | Builtins | networking (socket/connect/bind/listen/accept) | ❌ | Add builtins; gate `net_test`. |
| 0.104 | Builtins | random `rand` | ❌ getrandom only | Add `rand` builtin; gate `rand_test`. |
| 0.105 | Builtins | bit/byte extras (parity/bitfield/per-size swap) | ❌ | Add builtins. |
| 0.106 | Builtins | intrinsics (prefetch/fence/branch hints) | ❌ | Add builtins. |
| 0.107 | Builtins | fs metadata fix (stat/unlink/mkdir/chdir/rename) | 🟡 BROKEN | Fix path-string remap; gate. |
| 0.108 | Builtins | introspection stack-trace | ❌ | Add `abort_test` stack trace. |
| 0.109 | Memory | stack unwind / destructors / RAII | ❌ defer manual | Scope-exit cleanup. |
| 0.110 | Memory | real allocator (free-list/GC) | ❌ bump mmap only | Free-list allocator replacing raw mmap. |
| 0.111 | FFI | extern "C" PLT/GOT | 🟡 partial | Full dynamic-link symbol resolution. |
| 0.112 | Lang | trait/impl dispatch completion | 🟡 partial | Complete vtable dispatch for interface/impl/trait. |
| 0.113 | Lang | `big` keyword/type | 🟡 lib convention | `TT_BIG` + op-overload routing `a+b`→`big_add`; gate `big_test`. |
| 0.114 | P4 tooling | **Quanta-native code-writing tool** | ❌ | LAST core item — sequenced right before 0.1.0 (where std/libs resume). Edit Quanta source reliably without external scripting. |
| — | POST-0.1.0 | borrow-checking (ref/mut/move enforce) | ❌ | Compile-time memory safety (#1 green). |
| — | POST-0.1.0 | `chain` lib (Merkle/signed-tx/UTXO/Block) | ❌ not in code | Differentiation mandate. |
| — | POST-0.1.0 | `secure` lib (capability I/O, constant-time) | ❌ not in code | Differentiation mandate. |
| — | POST-0.1.0 | `ai` lib (tensor ops + inference) | ❌ not in code | Differentiation mandate. |
| — | POST-0.1.0 | `physics` lib (ODE/PDE solvers) | ❌ not in code | Differentiation mandate. |
| — | POST-0.1.0 | ARM64 (AArch64) backend | ❌ x86 only | Second backend (independent impl route). |

**Version-number rule:** literal numbers above are the plan; the SEQUENCING (order + one-feature-per-version + fixpoint-verified) is the contract. If a version needs splitting, the number increments — never skipped, never reused. 0.0.90 is **not reserved**; it is simply the `as`/`raw`/`volatile` cluster above. The code-writing tool is **0.114 — the last core item, sequenced immediately before 0.1.0** (where std/libs resume); ARM64 and the deep-systems items remain POST-0.1.0.

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

### Current status (0.0.87)

**0.0.87 (promoted stable seed):** std-lib gating — the 7 existing `std_*` test files
(`std_crypto_test`, `std_fs_test`, `std_lib_test`, `std_map_test`,
`std_math_test`, `std_str_test`, `std_vec_test`) are now in the gate
(EXPECTED.tsv), raising the suite from 117 → 124 tests, all GREEN (0 compile-fail;
security + performance GREEN). Compiler source unchanged — the 0.0.87 golden is
the byte-identical 0.0.86 binary (`a85aeacb…`), self-host fixpoint preserved.
FEATURES.md §J markers updated (crypto/math/vec/fs/map/str → ✅ gate; quantum/
linalg remain ❌ none — no test file on disk). This closes the "file-only" gap
for shipped std libs; it is doc/test work, NOT a core-feature implementation.

**0.0.88 (promoted stable seed):** first real core-feature — `u8`/`u16` as width-tagged
type keywords (`let x: u8`/`u16` parsed in parse_let, width mask in width_mask).
Found and FIXED a silent-wrong-answer bug: when a width-typed ADD/SUB/MUL result
lands in an extended register (r8–r15, which happens once low registers are
occupied by preceding vars), the mask emit omitted REX.B and silently masked the
wrong register; const-folded width arithmetic also dropped the wrap. Both fixed;
`mixed_width_mask_test.quanta` (rc=7) gates it. Suite 124 → 125, all GREEN.
Self-host fixpoint preserved (B==C byte-identical, A==C drift-identical).

**0.0.86 (prior stable seed):** self-hosting native compiler (byte-identical
fixpoint), intent-level syntax, primitive layer (syscalls, mmap, file I/O, floats,
closures, generics, big-int), stdlib seeds for crypto/quantum/linalg/math. Verified
stable seed for all subsequent work; the prior seed (0.0.85) remains one patch
behind per §9.

**Next:** 0.0.89 continues Core B (`bool`/`char`/`byte` as type annotations).
See "Outstanding cores — per-version sequencing" below.

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

### Current status (0.0.86) — verified stable seed

0.0.86 is the **promoted stable version** (replaces 0.0.85 as the seed for all
future work). Its feature content is the int→big auto-promotion from 0.0.85 plus
full release-gate verification: 117/117 suite green, self-host fixpoint
byte-identical (`a85aeacb…`), valgrind 0, fuzz clean, CI pinned (derived from
`cat VERSION`).

Over-sized decimal literals (those exceeding i64 range) are auto-promoted to
`big` at compile time — no `big_from_*` call needed. A 30- or 250-digit literal
like `123456789012345678901234567890` parses directly into a `big`.

- **Lexer** (`lexer.quanta`): the i64-overflow guard no longer rejects the
  literal; instead it emits a new `TT_BIGNUM` token carrying the source offset
  (`val`) and digit count (`len`). The digit text is left in `src` untouched.
- **Parser** (`method.quanta parse_primary`): on `TT_BIGNUM` it builds a runtime
  string from the digit bytes (writing `"digits"` into the source buffer at
  `srclen`, reusing the proven `IR_STR` path), registers `big_from_dec` in the
  global call table (`resolve_fn(..., FI_GLOBAL)`), loads the string into the
  call-arg stack, and lowers to `big_from_dec(str)`. The result vreg flows as a
  `big` like any other.
- **stdlib** (`big.quanta`): `big_from_dec(s)` parses an ASCII decimal string →
  `big` (corrected the runtime-string layout: length lives at `s+0`, packed
  bytes at `s+8+i` read via `mem_load8`, NOT 8-byte limb slots — a layout
  mismatch that previously crashed on print).
- **Verified**: 250-digit literal round-trips (`a*a/a == a`); `big_eq` matches
  `big_from_i64`; doubles match Python exactly. Normal i64 literals (`42`,
  `999999999999`) unaffected. Self-host fixpoint **byte-identical** (lex/parse
  edits are never taken on the compiler's own i64-only source).

### Current status (0.0.84) — 24-bit limbs + decimal printing + Karatsuba shipped


Performance + usability pass on `lib/std/big.quanta` (pure stdlib, zero codegen
changes, self-host fixpoint **byte-identical and verified**: bin==sh2==sh3).

- **24-bit limbs** (was 16-bit): every `a[i]*b[j] < 2^48 < 2^63`, so the signed
  `*` with `ovf_trap=1` never trips, and carry = `prod >> 24` / `prod & 16777215`
  is exact. 4096-bit = 171 limbs; 1M bits = 41,667 limbs (vs 62,500 at 16-bit
  → ~1.5× less RAM and ~1.5× fewer loop iterations). Sign lives in a dedicated
  slot (a[1]); limbs are 0..16777215.
- **Karatsuba multiply** (`big_mul` dispatches to `big_mul_base` schoolbook for
  ≤32-limb operands, Karatsuba above → O(n^1.585)). Two bugs found and fixed
  during bring-up: (1) midpoint was `half=(na+nb)/2`, which equals `na` when
  `na==nb` and made `big_hi(a, lo)` empty → **infinite recursion / stack
  overflow** at ~220 digits; now `half = min(na,nb)/2` so the split is always
  strictly below both lengths. (2) `big_mul_kara` allocated `nr = na+nb` limbs
  but placed `z2` at offset `2*lo = na+nb`, writing **past the end of `r`**
  (heap corruption / segfault); allocation is now `2*(na+nb)`.
- **Decimal printing** (`big_print` / `big_println`, signed-aware): iterative
  divide-by-10 building digits into a buffer, emitted via a `putc` byte writer
  (`write(1,&b,1)` syscall) — no per-digit recursion (which overflowed the
  runtime stack at scale) and no `print(n)` integer-formatter misuse (which
  emitted the digit *value* rather than an ASCII byte). Verified exact vs Python
  for 252-digit numbers.
- **Verified vs Python** (all reconstruct / match): mul, div (reconstruction
  `p/a==b`), mod (`p mod a == 0`), sub, signed div, shl/shr round-trips, and
  decimal rendering at 150–400-digit and 252-digit scale. 256-bit mul/div,
  2^80/2^64, and signed edge cases (`-17//5==-4`, `-17%5==3`) all exact.

### Current status (0.0.83) — big-int Stage 3 (SHIFTS) shipped

Arbitrary-count magnitude shifts `big_shl(x, n)` / `big_shr(x, n)` added to
lib/std/big.quanta (pure stdlib, zero codegen changes, self-host fixpoint
untouched). Split n into a whole-limb shift (n/16) plus a sub-limb bit shift
(n%16); spill bits handled via shift+mask only, so it never trips ovf_trap.
Negative n shifts the opposite direction. Verified against Python for n in
{0,1,7,10,32,50,64} on 128-bit operands, plus round-trip identities
shr(shl(x,n),n)==x.

### Current status (0.0.82) — big-int Stage 2 (DIV/MOD) shipped

Big-int DIV/MOD landed in `lib/std/big.quanta` (pure stdlib, zero codegen
changes, self-host fixpoint untouched). Signed floor division + modulo with
Python semantics (mod takes the sign of the divisor), binary restoring division
(shift-subtract, ovf_trap-safe) over 16-bit limbs. Verified against Python for:
all 16 signed sign-combos of small operands, and 128/256-bit operands
(incl. `(2^128-1)/7`, `2^128-1 mod 13`, `(2^128-1)*(2^64-1)/(2^128-1)`).

Root-cause bugs fixed during Stage 2 (all in `lib/std/big.quanta`):
- `big_add` carry detection was dead (`if s < x`, always false) -> carries
  never propagated; rewrote to `carry = s >> 16` with masked store.
- `big_mul` old split low/high form double-counted the carry into one limb;
  rewrote in standard schoolbook form (single 32-bit cell product).
- Sign stored in a dedicated slot (a[1]), not bit 63 of the header, because the
  compiler cannot represent the INT64_MIN literal (0x8000000000000000).

### Current status (0.0.81) — big-int Stage 1 (ADD/SUB/MUL) shipped

Big-int landed as a **pure-Quanta stdlib** (`lib/std/big.quanta`) — no compiler
codegen changes, so the self-host fixpoint is completely untouched (the compiler
never imports `std/big`). Import with `import std/big`.

**Design (pointer-in-vreg, fixpoint-safe):** a `big` is a header-pointer to a
little-endian limb array (`[base]=nlimbs`, limbs at `base+8+i*8`), exactly like
the existing `mem_alloc` array model. The vreg holds an 8-byte pointer, so spill
slots, call ABI, and frame layout are unchanged.

**Limb width = 16 bits.** This is deliberate: Quanta's `*` is a signed 64-bit
multiply with `ovf_trap=1`; a 32-bit limb squared (~1.8e19) overflows i64 and
trips the trap, and a 64-bit limb loses the high half of the 128-bit product
entirely. 16-bit limbs keep every `a[i]*b[j]` < 2^32 (never traps), and the
split `low=prod&0xFFFF; high=prod>>16` is exact. 4096-bit numbers = 256 limbs.

**Verified against Python** (all match):
- `123456789+987654321=1111111110`, `|123456789−987654321|=864197532`,
  `123456789×987654321=121932631112635269`
- `(2^64−1)² = 0xfffffffffffffffe0000000000000001` (128-bit, exact hex)
- `(10^12+7)×(10^12+13) = 0xd3c21bcedf1e3de5405b` (large, exact hex)
- Schoolbook ADD (carry), SUB (borrow + magnitude-swap), MUL (two-column carry).

**Self-host verified:** `bin/qc` compiled by itself reproduces itself
byte-identical (`bin==sh2==sh3`); a normal `import std/big` program compiles and
runs; a non-big program is unaffected.

**Not in 0.0.81 (deferred to 0.0.82):** DIV/MOD (Stage 2 per ROADMAP), SHL/SHR,
sign/magnitude (signed arithmetic), decimal printing, `>64-bit` literals +
auto-promotion, and a `big` *keyword/type* (currently `big` is a library
convention, not a language type). **STILL OUTSTANDING** — never landed in
0.0.82; tracked in the live "remaining to 0.1.0" list below and in
FEATURES.md §J. Implemented as a 0.1.0 type-system item (needs `TT_BIG` type
token + operator-overload dispatch so `a + b` routes to `big_add`).

### Current status (0.0.78)

Shipped + verified (x86-64 only; ARM64 deferred POST-0.1.0): **true 2-stage self-host** —
the committed `bin/x86/qc` compiles the 0.0.74 source to a faithful `qc`, verified
byte-identical to the golden binary (and to a 2nd-stage rebuild); fail-closed memory
model (overflow/bounds→SIGILL 132, MAP_FAILED→rc=1, undeclared/cyclic→rc=7);
grammar 0 errors on all 15 modules; Valgrind-clean; differential vs seed.
Standards docs: SPEC/SAFETY_MANUAL/SECURITY_TOOLING/MEMORY_SAFETY_ARGUMENT.

P2 builtins landed through 0.0.57 (gate green, 91/91): float comparisons
(`feq/flt/fgt/fle/fge/fisnan/fisinf`), float math (`sqrt/floor/ceil/abs`),
float arith (`fadd/fsub/fmul/fdiv`), process/env (`getpid/getppid/arg_count/environ`;
`getenv` is a stub returning 0), stdin (`getc`), random (`getrandom`),
introspection (`abort`/`debugbreak`). Simplified surface: `fn`/`let`/`return`
optional, no-parens conditions, `${name}`/`$[]` global/local sigils.

**0.0.61** float literals: `3.14`/`-0.5`/`123.456` parse and `println(3.14)`
prints `3.140000`.
**0.0.62** float-arg fix: the float builtins (`f2i`, `fadd`, `fsub`, `fmul`,
`fdiv`) now read float-literal / float-vreg arguments correctly (was a known gap
in 0.0.61). Verified: `f2i(3.14)`→3, `fadd(1.5,2.5)`→4, `fmul(2.5,4.0)`→10,
`fdiv(10.0,4.0)`→2, `fsub(5.0,2.0)`→3; int args still work (`fadd(3,4)`→7).
**0.0.63** user enums: `enum Name { A, B, C }` and explicit tags
(`enum Pri { Low=1, Mid=5, High=9 }`); qualified (`Color.Red`) and bare (`Green`)
variant resolution; both usable in `match` arms (integer-tag comparison). Variants
are heap-allocated tagged values (Rust-style sum types) — use `match` for value
comparison, not `==`. Gate: 93/93 functional, 8/8 security, 3/3 performance.
**0.0.64** modules: `mod Name { fn ... }` registers functions with `Name.fn` names;
qualified calls `Mod.fn()` resolve via a module registry. Nested modules
supported. Basic trait/struct/impl compatibility verified. Gate: 93/93 functional,
8/8 security, 3/3 performance. Bootstrap: **true 2-stage self-host** — the
committed `bin/x86/qc` compiles the 0.0.64 source to a faithful `qc` (verified
byte-identical to a 2nd-stage rebuild, 93/93 gate). Previously the self-host was
broken by two parameter/global name collisions in `emitter.quanta`
(`mr(mod,…)` vs global `IR_MOD`; `stx(base,disp,src)` vs global `src`), which
corrupted `mr`'s modrm byte ordering and made every emitted program segfault.
Both renamed (`mod`→`mmod`, `src`→`sreg`) — self-host is now faithful.
**0.0.65** closure literals: `|x, y| { expr }` parses as an anonymous function
value and lowers to a 16-byte `[codeptr, env]` tuple (the same layout `IR_FNVAL` /
`mk_any` use), emitted by the new `IR_CLOSURE` opcode. The body is registered as a
synthetic top-level function (`reg_closure`) so the main compile loop emits it with
its own parameters bound; calls route through the existing `IR_CLOSURE_CALL` ABI
(args in the standard SysV registers, env in `r10`). Both direct invocation
(`let f = |x| { x + 1 }` then `f(5)`) and passing a closure to an fn-typed
parameter (`fn apply(f: fn(i64) i64, x) { return f(x) }`) work.
Lexer note: single `|` is emitted as `TT_OP` value 124 for closure syntax while
`||` remains a distinct multi-char token (31868), so logical-OR is unaffected.
Gate: 96/96 functional (3 new closure tests), 8/8 security, 3/3 performance,
optimizer differential fuzz 120/120 clean. Bootstrap: **true 2-stage self-host** —
golden `0.0.64/bin/x86/qc` → 0.0.65 source → `qc`, and a 3rd stage rebuild is
byte-identical (fixed point, md5 `feca334f…`).
Known gap: closures do NOT yet capture enclosing locals (`env` is 0); a free
variable in a closure body is an "undeclared variable" error. Captures are the
next increment.
**0.0.66** array-push correctness fix (**regression introduced by 0.0.65**).
`IR_CLOSURE` was assigned opcode **72**, which was already `IR_APUSH`. Because
`parse_let` tags a fn-value RHS by checking `irop(lr)==IR_CLOSURE`, every array
push matched that test, so the push result vreg was tagged as a closure/fn value
and corrupted: the array header grew (`len` reported the new length) but the
appended element read back as **0**. Symptom was silent wrong data, not an error.
Fixed by moving `IR_CLOSURE` to the next free opcode (**76**).
Impact: `a.push(v)` returned 0 for every array; the `[U]()` + `push` idiom used
by the generic `map<T,U>` example returned 0 instead of 12, which had been
mis-attributed to generics being unimplemented — generics were fine.
Caught by no gated test: nothing in the suite pushed onto an array (`reg_alias`
defines its own `push`, `std_vec_test` uses `vec_push`, `stdlib_test` pushes onto
a *string*). Three regression tests added that PASS on 0.0.66 and FAIL on 0.0.65:
`array_push_method` (7), `array_push_empty_annot` (7), `array_push_closure_mix`
(35 — push and a closure literal in one program, so a future collision fails
loudly). Gate: 99/99 functional, 8/8 security, 3/3 performance, differential fuzz
120/120, compiler fuzz 5000/0 crashes, Valgrind 0 errors. Self-host fixed point
md5 `543d5c4e…` across stages 1/2/3.
Lesson recorded: adding an IR opcode MUST check for collisions — `grep -oE '^let
IR_[A-Z_0-9]+ = [0-9]+' globals.quanta | awk '{print $4}' | sort -n | uniq -d`
must print nothing. **CI now enforces this** as a build step ("IR opcode
uniqueness"), verified to pass on 0.0.66 and fail on 0.0.65's collision.
**0.0.67** closure captures — completes the closure feature started at 0.0.65
(where `env` was hardcoded 0 and a free variable was a hard error).
A closure body may now reference locals of the enclosing function; they are
captured **by value**, snapshotted at construction time:
`let y=10; let f=|x| { x+y }; f(5)` → 15, and reassigning `y` afterwards does not
change what the closure sees (`y=99` then `f(1)` → 11, not 100).
Implementation: new `IR_CAPREAD` opcode (**77**, uniqueness-checked) reads the
k'th captured value as `mov rax,[r10+k*8]`, since `IR_CLOSURE_CALL` already
passed `env` in `r10`; `IR_CLOSURE` now mmaps an `ncap*8` env array and copies
each captured value in from the enclosing frame's home slot (`env=0` fast path
preserved when a closure captures nothing).
Key ordering constraint: the env array's size must be known when `IR_CLOSURE` is
emitted, but a body is not parsed until its own turn in the per-function compile
loop — by which point the enclosing scope is gone. First attempt resolved
captures during body parse and produced `env=0` + a segfault. Captures are
therefore discovered in `parse_primary`'s closure branch by scanning the body's
tokens while the enclosing `vars` table is still live, skipping `name(` calls and
`.field` accesses and the closure's own params. Repeat references share one slot;
cap is 32 captures. By value only — no by-reference capture, so a closure cannot
mutate an enclosing local.
Gate: 102/102 functional (3 new capture tests, each failing on 0.0.66), 8/8
security, 3/3 performance, differential fuzz 120/120, compiler fuzz 5000/0
crashes, Valgrind 0 errors, differential 5/5 vs 0.0.66. Self-host fixed point
md5 `62b2e0cd…` across stages 1/2/3.
**0.0.68** user functions win over builtins (silent-hijack fix).
The documented rule "a user-defined fn MUST win over this builtin" was enforced
in exactly **2** of **86** builtin branches (`push`/`pop`). Every other builtin
silently hijacked a same-named user function, with no diagnostic:
`fn abs(x){ if x<0 { return 0-x }; return x }` then `abs(-42)` returned **0**,
because the FPU builtin `abs` read the integer bits as a double. `pow` likewise
(it is `exp(b·ln a)`), and `gcd`/`lcm` cascaded because they call `abs`.
Fixed with ONE guard at the top of `emit_bltn`/`emit_bltn2` instead of 86 ad-hoc
checks; the two per-branch checks are now redundant. Returning 0 makes codegen
emit a normal patched call to the user's function.
**Deliberate exception — primitive intrinsics are NOT overridable:**
`mem_load`/`mem_store`/`mem_load8`/`mem_store8` and `fadd`/`fsub`/`fmul`/`fdiv`
(`is_prim_intrin`). A blanket guard **broke the self-host**: the compiler defines
its own same-named wrappers in `helpers.quanta` (`fn w64(p,v) { mem_store(p,v) }`
alongside `fn mem_store(p,v) { … w64(p,v) }` — mutually recursive, with the
builtin breaking the cycle), so honouring user-wins there is infinite recursion.
Observed failure was itself silent: stage 2 exited rc=0 while writing NO output
file, and stage1 ≠ stage2. Caught only by the fixpoint check, which is exactly
why that gate exists.
Gate: 105/105 functional (3 new tests), 8/8 security, 3/3 performance,
differential fuzz 120/120, compiler fuzz 5000/0 crashes, Valgrind 0 errors,
differential 5/5 vs 0.0.67, 0 duplicate opcodes. Self-host fixed point md5
`308cf0c0…` across stages 1/2/3.
New tests, each wrong on 0.0.67: `user_fn_beats_builtin` (42, was 0),
`user_fn_beats_builtin_chain` (38, was a SIGILL trap 132),
`builtin_still_inline` (3 — proves un-shadowed builtins and the primitive
intrinsics still work inline).
NOTE: `lib/std/*` is deferred POST-0.1.0 and is deliberately NOT in the gate,
but this core fix repaired it as a side effect: `std_math_test` self-reports
"expect 19" and returned **9** on 0.0.67 — it returns **19** on 0.0.68, because
all four of its failures (`abs`, `pow`, `gcd`, `lcm`) were this same builtin
hijack, not library bugs (`lib/std/math.quanta` was always correct). Verified
against their self-reported expectations on 0.0.68: std_math 19, std_str 13,
std_fs 9, std_vec 8, std_map 6 — all matching. They stay ungated until after
0.1.0 per the release plan.
**0.0.69** match guards — the last known silent-wrong-answer in core.
`match x { n if n > 3 => 111, _ => 222 }` compiled clean and returned **0**,
taking NO arm. Root cause: the identifier-binding arm consumed the binder `n` and
then called `mop('=>')`, but `mop` returns 0 **without advancing** when the token
does not match — so the `if` was never consumed, the arm's IR came out malformed,
and the whole match produced 0 with no diagnostic.
Fix (parse.quanta, identifier-binding arm): after binding the pattern name,
accept an optional `if <cond>` and emit `IR_BR cond -> arm_skip`. `IR_BR` lowers
to `je`, i.e. it branches when the condition is FALSE, which is exactly
skip-this-arm-on-guard-false. The binder is `vadd`-ed before the guard is parsed,
so the condition may use it (`n if n > 3 => n * 2` works).
Semantics verified: guard true takes the arm; guard false falls through to the
next arm; multiple guarded arms are tried in order (first match wins); the
wildcard runs when no guard matches; unguarded arms are unaffected.
Gate: 108/108 functional (3 new tests), 8/8 security, 3/3 performance,
differential fuzz 120/120, compiler fuzz 5000/0 crashes, Valgrind 0 errors,
differential 5/5 vs 0.0.68, 0 duplicate opcodes. Self-host fixed point md5
`5f23f927…` across stages 1/2/3.
New tests, each returning 0 on 0.0.68: `match_guard` (111),
`match_guard_false` (222), `match_guard_order` (4 — ordering, fallthrough, and a guard body using the bound name).
**0.0.74** `$$(identifier)` shorthand — a single bare identifier inside `$$()` is stringified, so `$$(ls)` == `$$("ls")`. Multi-token commands still require quotes: `$$(echo hello)` is a parse error (the shorthand only fires for `TT_ID` immediately followed by `)`).
**0.0.75** const redefinition fix — `const x = 5; const x = 10;` silently took the second value (10) before; now the first value wins (5) and the duplicate is skipped. The scanner phase (`features.quanta:scan_globals`) registers consts before the parser runs, so the dup check had to go there.
Also: coverage audit of all documented-but-untested surface. Findings:
- `a[-2]` traps (SIGILL) — **intentional**, SYNTAX.md documents this
- Closure mutating captured var — **intentional**, by-value capture semantics
- `isnan`/`isinf` — missing (not yet built)
- All P2 float builtins verified working: sin, cos, tan, pow, log (roadmap was stale)
- `std/net` and atomics — never built
**0.0.72** fnptr/closure_call segfault fix — `fnptr(FNAME)` now returns a [codeptr, env=0] tuple (same layout as IR_FNVAL), so it can be passed directly to `closure_call`. Before 0.0.72, `fnptr` emitted a raw code pointer (`lea rax,[rip+disp]`), but `closure_call` expects a tuple and dereferences its argument as `mov rdx,[rax]` then `call r11`. Feeding it a raw pointer read garbage and jumped to a bogus address → SEGFAULT (rc=139). No gated test covered `fnptr`, so the crash survived since 0.0.67. The `fnptr_test.quanta` test was rewritten: it previously wrapped the result in `mk_any(p,0)` as a workaround for the raw-pointer behavior, which is no longer needed.
Gate: 110/110 functional (rewritten fnptr_test), 8/8 security, 3/3 performance,
differential fuzz 120/120, compiler fuzz 5000/0 crashes, Valgrind 0 errors,
differential 5/5 vs 0.0.71, 0 duplicate opcodes. Self-host fixed point md5
`e622a3a0…` across stages 1/2/3.
**0.0.70** `and` / `or` keyword operators (silent-discard fix), plus two
roadmap corrections found by auditing the "remaining" list instead of trusting it.
The keywords were tokenized as `TT_KEY` but never consumed by `parse_and` /
`parse_or`, so only the FIRST operand was evaluated and the rest was silently
discarded: `1==1 and 2==3` wrongly took the true branch, `1==2 or 2==2` returned
0. Fixed by accepting the keyword alongside the symbolic form at the same
precedence level, reusing the existing short-circuit lowering — so `and`/`or` are
exact aliases of `&&`/`||`, including short-circuit.
**Roadmap corrections (the list was stale, not the compiler):**
1. **tuples were already DONE** — 13/13 probes passed on 0.0.69 (literals, 3-tuples,
   nested `t.0.1`, tuple-valued returns, element reassign, tuple in array,
   destructuring, swap), and they are already gated (`tuple_test` 40,
   `option_tuple` 42). Removed from "remaining"; no version was spent on it.
2. **`not` / `true` / `false` / `global` were already DONE** — only `and`/`or`
   were actually broken, so this entry replaces the whole
   `and/or/not/true/false/global` line item.
**Rejected change, recorded so it is not retried:** while probing `not` I read
`!1 == -2` as a bug and "fixed" the constant folder to make `IR_NOT` logical
(0/1). That turned the gate RED at `bitwise_not.quanta`, which asserts
`!0 == -1`, `!1 == -2`, `!!7 == 7`, and the compiler's own sources depend on the
bitwise reading. Change reverted; `codegen.quanta` now carries a comment saying
IR_NOT and IR_BNOT fold identically on purpose. The gated test caught what my
reasoning got wrong.
**NEW DEFECT FOUND, deferred to its own version:** `!` / `not` is **inconsistent
between the constant and runtime paths**. Constant operands fold BITWISE
(`!0` → -1) while runtime operands emit LOGICAL code (`let a=0; !a` → **1**). Same
expression, two different meanings depending on whether the operand folds.
Pre-existing — reproduced on 0.0.69, so not introduced here. NOT fixed in 0.0.70
because it is a semantic decision, not a mechanical bug: either the folder is
wrong (make it logical, and rewrite `bitwise_not.quanta` plus the compiler
sources that rely on `!`), or the runtime lowering is wrong (make it bitwise), or
the two readings should be split into separate operators. Recorded in FEATURES.md
as ⚠️ INCONSISTENT and flagged in SYNTAX.md as avoid-in-new-code rather than
documented as a feature.
**0.0.71** `!` / `not` is now LOGICAL not (0/1) on BOTH the constant and runtime
paths -- the inconsistency is fixed. Before 0.0.71 `!` meant two different things
depending on whether its operand was a constant:
    println(!0)            -> -1    (constant path: bitwise)
    let a=0; println(!a)   ->  1    (runtime path: logical)
The runtime lowering was the correct one: all 36 unary-`!` sites in the
compiler's own sources are boolean tests (`if !(tokt(p)==X)`, `while !(...)`,
`if !is_novf && !is_arm`) and NONE uses `!` for bitwise arithmetic. So the
constant folder was changed to match: `IR_NOT` now folds to 0/1, while `IR_BNOT`
(`~`) still folds to `~x`. They are different operators and fold differently.
`bitwise_not.quanta` was rewritten to pin both paths so they can never drift
again: logical `!`/`not` return 0/1 on both const and runtime operands, bitwise
`~` returns `~x` on both, and the double-negation identities hold for each.
Gate: 110/110 functional (rewritten test), 8/8 security, 3/3 performance,
differential fuzz 120/120, compiler fuzz 5000/0 crashes, Valgrind 0 errors,
differential 5/5 vs 0.0.70 (consistent -- the change is self-consistent), 0
duplicate opcodes. Self-host fixed point md5 `7466753b…` across stages 1/2/3.
New tests, both returning 0 on 0.0.69: `logical_keywords` (4 — full truth table
for `and`/`or` plus mixed precedence), `logical_keywords_shortcircuit` (2 — the
right operand is a trapping call that must never be evaluated).

Known gap: `getenv` is a stub; string ops (concat via `..` and `${}`/`$[]`
interpolation) work. See FEATURES.md §I.

