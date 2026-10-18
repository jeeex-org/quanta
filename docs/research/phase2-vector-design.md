# Phase 2 — width: explicit vector types, their ABI, and the ISA contract (design)

Design only. **Not implemented** in 0.0.249. Recorded so the next run starts from a
decided design, per the author's directive ("if scalar can't win why not change
it?") and the ordering he fixed: **marshalling levers first, then vector TYPES as
their own version, then a targeted auto-vectorizer as a separate version.**

Backlog: `docs/plans/language-capabilities.md` **#21**.

Every count below is MEASURED in this session against
`compiler/0.0.249/src/x86/` and `lib/std/`.

---

## 1. Why width, and why after the marshalling levers

Measured, after the twin-width fix (§ `phase2-arith-baseline-0.0.248.md`): **9 of
38 C twins still use `%ymm`** — `big_array fileio heavy_mem heavy_recursion mem
mem_ops q4k q4k_heavy q4k_matmul` — and disassembly shows they are **4-wide i64**
(`vpaddq`, `vpsllq`, `vpsubq`, `vpbroadcastq`). On a throughput-bound loop nothing
in scalar codegen closes a 4x lane deficit: the same instruction budget does 4
elements per tick against our 1.

But the home-slot traffic is paid **per operation**, so it eats the lane gain
before it can show, and would be misattributed to vectorisation. The ordering is
therefore not a preference: **F1/F2/F3 … first, then width.** (F1 landed as 0.0.249;
`phase2-f1-adistinct-0.0.249.md`.)

## 2. What already exists, and what does not (measured)

| | measured in 0.0.249 |
|---|---|
| packed-instruction EMISSION in the code generator | **yes** — `emitter.quanta`: `vmovupd` x22, `vmulpd` x12, `vcvtdq2pd` x9, `vsubpd` x7, `vpslld` x7, `vaddpd` x4, `vpbroadcast` x3, `vpaddd` x2 |
| a vector TYPE in the lexer/parser | **no** — 0 occurrences of `i64x4`/`i32x8`/`f32x8`/`f64x4`/`vec` anywhere in `src/x86/`; `xmm`/`ymm` appear only in comments |
| an auto-vectorizer | **no** — `opt_func()` is constant-folding and small rewrites only |
| FMA | **no** — 0 occurrences of `vfmadd`/`vfmsub` in `src/x86/` (F5, opt-in) |
| packed emission already exercised in production | **yes** — the JIT kernels (`lib/std/jit_x86.quanta` 15, `jit_x86_fused.quanta` 30 packed-instruction sites) emit raw encodings through `mmap`+`closure_call` |

So the capability is **half-present**: emission exists and is proven by the JIT;
the *type*, the *ABI*, and the *pass* do not. That is why step 2 is cheap relative
to its value — the encodings are already written down in this tree, just not
reachable from the language.

(Discrepancy recorded for the record: the directive says `vmulpd` x13; a
case-insensitive count in `emitter.quanta` gives **x12**. Everything else matches
exactly. The count does not change the conclusion.)

## 3. Step 2 — vector TYPES (their own version)

### 3.1 Syntax and semantics

```
let a: i64x4 = [1, 2, 3, 4]          // literal constructor, lanes low -> high
let b = vload_i64x4(p)               // unaligned 32-byte load
let c = vloada_i64x4(p)              // aligned, 32-byte alignment REQUIRED (trap otherwise)
vstore_i64x4(p, b)
let s = a + b                        // whole-vector arithmetic, element-wise
let m = a * b
let x = a & b ; let y = a ^ b ; let z = ~a
let e = a[i]                         // lane extract, i must be a compile-time constant
let f = with_lane(a, 2, v)           // lane insert
let g = splat_i64x4(v)               // broadcast a scalar to all lanes
```

Type set for v1, chosen to be exactly the AVX2 shapes that pay: **`i64x4`, `i32x8`,
`f64x4`, `f32x8`**. (32-byte types only. 16-byte `*x2` types add a second
alignment class for no measured win; 8-lane f32 is the one gcc actually uses on
these twins.)

Semantics are **fully specified and total**, no undefined results:

- integer lanes: two's-complement wraparound, exactly like scalar `i64`/`i32`. The
  overflow trap does **not** apply to vector lanes (there is no per-lane trap
  instruction); this must be stated in `docs/SPEC.md`, and it is a second reason
  backlog #20's `unchecked` region is a prerequisite — a vector type is *always*
  unchecked arithmetic and the language should not have two contradictory stories
  about that.
- float lanes: the same IEEE-754 semantics as the scalar type, with the same
  rounding mode, and **no implicit f32->f64 promotion** — mixing `f32x8` and `f64x4`
  in one expression is a compile error, not a conversion.
- lane index: `a[i]` and `with_lane(a,i,v)` take a **compile-time constant** only in
  v1. A dynamic lane index lowers to a 32-byte stack round trip; that is an
  explicit non-goal for v1 (it can be added later without breaking anything).

### 3.2 Memory: alignment is a type-independent property of the operation

Two load/store families, no implicit choice:

- `vload_*` / `vstore_*` — unaligned (`vmovupd`). Always correct, any address.
- `vloada_*` / `vstorea_*` — aligned (`vmovapd`), and the **alignment is checked at
  the point of use**: reuse the existing bounds/`ud2` trap machinery
  (`idx_trap_emit`, `shl_trap_emit` are the precedents) so a misaligned address
  SIGILLs rather than faulting with a confusing SIGSEGV. Suppressed inside
  `unsafe{}`, exactly like the other traps.

### 3.3 ABI for a vector value

A vector value is 32 bytes and is a **first-class value**, so the ABI has to say
three things. Proposed, deterministic, minimal:

1. **Quanta-to-Quanta calls**: one `ymm` register per vector argument, in argument
   order, taking slots after the eight integer/SIMD-class argument registers are
   assigned (i.e. the standard SysV allocator extended with 4 vector registers
   `ymm0-ymm3` for vector-typed args). A vector RETURN value comes back in `ymm0`.
   More than 4 vector args -> the remainder are passed **by value on the stack,
   32-byte aligned**, in declaration order.
2. **`extern "C"` calls**: a vector argument is passed **by hidden pointer** (32-byte
   aligned, caller-owned), never in a register. Rationale: we cannot assume the C
   callee's vector ABI, and a wrong assumption here is silent corruption. A hidden
   pointer is always correct and is what a C compiler does for an over-aligned
   struct. This must be documented as the *definition* of vector FFI, not a
   limitation.
3. **Spills**: 32-byte-aligned slots in a **separate** spill region, indexed by
   vreg, exactly as `spill_home`/`fspill_home` are today.

   **Hard prerequisite, and it is A32.** `fspill_home` already writes ~8 KB below
   `%rbp` while the frame formula reserves 1120 bytes, and `fphys()` has 0 call
   sites, which is the only reason it has never faulted. Vector spills multiply the
   exposure. **The frame formula must be fixed before any vector home slot is
   allocated** — either grow the frame by the region size for functions that have
   vector vregs, or re-base every home (int, float, vector) into one region at
   disjoint index ranges. This is the same prerequisite the audit recorded for F4.

### 3.4 The ISA CONTRACT (required — this is the part that must not repeat F16C)

AVX2 is not universal: this box has it, a 2011 Core i5 does not, and a container
under an emulator may not. 0.0.248 spent real effort removing a *silent* F16C
dependency, proven by scanning emitted bytes (58 F16C opcodes -> 0). The vector
feature is the same class of risk at a larger scale, so the contract is:

**A vector type is only usable in a unit that explicitly declares the ISA it
needs, and the requirement is enforced at compile time.**

Concretely:

1. **Declared baseline.** The compiler has a named baseline (proposal:
   `x86-64-v2`, i.e. SSE4.2 + POPCNT) that is always available and never emits
   vector opcodes.
2. **Per-function / per-module declaration.** `@isa(avx2)` on a function (or
   `//! isa: avx2` on a module) states the requirement. Every function that uses a
   32-byte vector type, or that the vectorizer vectorises, must be inside such a
   declaration.
3. **Hard error, not a silent assumption.** Using `i64x4` in a unit without the
   declaration is a **compile error** naming the type, the required feature, and
   the missing declaration. This is the whole point: the requirement becomes
   visible in the source and impossible to satisfy by accident. There is
   deliberately **no** "just emit it and hope" mode.
4. **Cross-declaration calls are checked.** Calling an `@isa(avx2)` function from a
   baseline function is an error too (a caller that cannot run the callee's
   instructions is a latent SIGILL); the opt-in runtime-dispatch form is a
   *separate*, later construct (`@isa_if(avx2)` + CPUID check, one branch), never
   automatic.
5. **Pinned by a gate stage that reads bytes, not intentions.** Two rows, both
   new, in the same commit as the feature:
   - `vec_isa_undeclared_negative` — a program using a vector type **without** the
     declaration: the gate asserts a **compile failure** with the expected message
     (a negative row, like `generics`; rule #16's "a test must be able to fail").
   - `vec_isa_avx2_bytes` — a program using it **with** the declaration: the stage
     scans the emitted object and asserts the AVX2 opcodes (`vpaddq`/`vmulpd`
     `c5`/`c4`-prefixed forms) are **present**, so the test cannot pass by the
     feature silently not lowering. This mirrors `f16c-indep` inverted, and is the
     same "scan emitted bytes" evidence standard.

No stage may depend on this host having AVX2 to *pass*: the byte scan is a static
property of the output.

## 4. Step 3 — a TARGETED auto-vectorizer (separate version)

Explicit vector types make the author think about lanes. gcc wins on the twins
because *scalar* source gets vectorised. So after step 2, a deliberate,
**narrow** pass:

- **Pattern recognised (v1, one shape):** `for i in 0..N { a[i] = f(b[i], c[i]) }`
  and its accumulation twin `s += f(b[i])`, where `i` is an independent induction
  variable with stride 1, the loop body is elementwise with **no** loop-carried
  dependence other than the accumulator, and the arrays are the same length.
- **Safety conditions, all required:** no aliasing between the written array and any
  read array (proved only for the cases we can name — distinct `let` bindings with
  no address-taken escape, reusing the existing `vr_at` "address escaped" flag);
  trip count ≥ one full vector, with a **scalar epilogue** for the remainder; no
  early exit, no carry, no call inside the body.
- **Scope discipline:** it vectorises or it emits the scalar loop unchanged. There
  is no partial/estimated path, and no speculative vectorisation of reduction chains
  whose order is observable (the JIT's serial accumulation exists for exactly that
  reason — do not vectorise it).
- **Proof:** integer vectorisation is **bit-exact against a scalar reference by
  construction**, so the oracle is the best one available in this project: a gate row
  that computes the same array twice, once with the vectorisable shape and once with
  a shape the pass refuses, and compares element-by-element, plus the existing
  `differential` stage (`-O` == no-`-O`) extended to the vectoriser. For floats the
  bar is the same as F5's: identical results, or an explicitly-flagged opt-in.

## 5. Sequencing, in dependency order

| step | version | prerequisite it needs first |
|---|---|---|
| marshalling levers (F1..F3, F6, F8) | 0.0.249+ | — (F1 landed) |
| frame/offset fix (A32) | its own version | — |
| `unchecked` region (backlog #20, A33) | its own version | — (also needed by vector lane arithmetic) |
| vector types + ABI + ISA contract | its own version | A32 frame fix |
| targeted auto-vectorizer | its own version | vector types |
| F4 (xmm-resident FP) | its own version | A32 frame fix |
| F5 (opt-in FMA) | its own version | — |

Each step keeps the campaign's invariants: one lever per version, a red-first row
that fails on the previous version, a 4-generation self-host fixpoint, `verify-release`
green, the full gate green with new rows registered in the same commit, and the
byte-identity report (compile every gate row with both compilers and account for
every differing row).

## 6. What would make this fail, stated up front

- The frame/offset fix (A32) is genuinely load-bearing, not a formality: without it
  a vector home slot writes into the caller's frame.
- The ABI decision for `extern "C"` (hidden pointer) must be made before the type
  ships, or the FFI path will silently pass garbage.
- The ISA contract is the difference between a feature and a repeat of the F16C
  incident. If it slips, the feature must not ship.
- The auto-vectorizer is where scope creep lives. v1's single recognised shape is
  deliberately one shape; measure it against the same 38-case suite and stop.
