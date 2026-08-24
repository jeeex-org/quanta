# Big-Int (big) Design — Quanta x86-64

Last updated: 2026-08-24. Status: IMPLEMENTED. Landed: ADD/SUB/MUL (0.0.81),
DIV/MOD (0.0.82), SHL/SHR (0.0.83), decimal printing + 24-bit limbs +
Karatsuba multiply (0.0.84). See `lib/std/big.quanta`.

## Goal
Support arbitrarily large integers so 250-digit literals and PQC/Kademlia key
arithmetic are representable without overflow. `int` stays 64-bit (fast default,
self-host path untouched). `big` is the arbitrary-precision type.

## Hard constraint
The x86-64 backend MUST remain a **byte-identical self-host fixpoint** (`qc`
compiled by itself reproduces itself). The compiler's own source uses only 64-bit
`int`, so the `big` path must be a **separate, never-taken** branch during
bootstrap. That is the guiding principle of this design.

## Architecture (grounded in 0.0.80 source)

### Value model — pointer-in-vreg (matches strings/arrays)
- A `big` value is a **heap-allocated limb array**. The vreg holds a 64-bit
  pointer (8 bytes) — exactly like strings (`vreg_is_str`) and arrays
  (`IR_APUSH`/`IR_IDX` use `[base]=len, [base+8..]=qwords`).
- Consequence: vreg spill slots stay 8 bytes, frame layout, call ABI, and
  global layout are UNCHANGED. `big` values flow through `IR_CALL` like any
  pointer (rdi/rsi/.../rax, result in rax) — see `IR_CALL` arg load at
  codegen ~line 1142. **Self-host fixpoint preserved.**

### Representation
- Heap layout: `[ptr] = nlimbs (i64)`, `[ptr+8 .. +8+nlimbs*8] = limbs, little-
  endian, limb = u64. Sign stored in a separate tag word or as limb[0] sign +
  a magnitude convention. Chosen: **sign-magnitude**, `ptr+8+nlimbs*8` = 1-byte
  sign (0=+,1=-). Simple, correct, easy compare.
- i4096 target = 64 limbs × 64 bits = 4096 bits. Allocation size = 8 + 64*8 + 1.

### Vreg type tagging
- Extend `vreg_type[vr]` with a new vtype (e.g. `10 = big`). `width_mask`
  already special-cases unsigned widths 1..5; `big` falls through to "no mask"
  (it's not a 64-bit value — the vreg holds a pointer).
- Parser: add `big` keyword (new ktext id) → vtype 10 on `let x: big` and on
  literals too large for i64 (auto-promote `int` literal > 2^63 to `big`).

### Multi-precision IR + emit
New IR ops (numeric, appended to globals.quanta IR_ enum):
- `IR_BADD`, `IR_BSUB`, `IR_BMUL`, `IR_BDIV`, `IR_BMOD`, `IR_BNEG`,
  `IR_BCMP`, `IR_BSHL`, `IR_BSHR`.
- Each has a `big`-specific emit that:
  1. loads the two operand pointers (rbp from spill_home),
  2. ensures result buffer allocated (mmap if needed; reuse res home slot as
     the pointer),
  3. emits a **loop over limbs** using `adc`/`sbb`/`mulx`+`adc`/`divq`-free
     schoolbook (x86 `div` is 128/64; multi-limb div uses the standard
     restore-and-subtract algorithm),
  4. stores result pointer to res home, `sdef(res, rd)` (rd holds the pointer).
- Bootstrapping multi-precision in Quanta: the loops are written as IR or
  emitted inline via `eb(...)`. Early stage can emit a **helper call** to a
  runtime `big_*` routine (linked in the ELF runtime stub) to avoid hand-writing
  limb loops in the compiler — cleaner and keeps self-host simpler. Decision:
  **runtime helpers** (`big_add`, `big_sub`, `big_mul`, `big_divmod`,
  `big_neg`, `big_cmp`, `big_from_i64`, `big_to_i64`) in the runtime, called via
  `IR_CALL`. The compiler emits `IR_BADD → call big_add(a.ptr, b.ptr) → res.ptr`.

### Literals & conversions
- `big` literal: parser emits `IR_CALL big_from_i64(const)` or, for >64-bit
  literals, a bytes→big constructor (`big_from_bytes`).
- `int`→`big`: `IR_CALL big_from_i64`. `big`→`int` (truncating): `big_to_i64`
  (traps if out of range, fail-closed per the memory model).

### Optimizer / constfold
- `constfold` does NOT fold `big` ops (no constant `big` values in IR; they are
  runtime pointers). Leave `big` ops for the emit/CALL path. This matches how
  float ops are skipped in constfold (line 74: `if float operand, return 0`).

## Staged plan (each stage keeps the fixpoint green)

**Stage 0 — scaffolding (no behavior change).**
- Add `big` keyword + vtype 10; `let x: big` tags the vreg. No arithmetic yet.
- Add IR_B* enum constants. No emit (unreached). Self-host must stay green.

**Stage 1 — heap + helpers + assignment.**
- Runtime: `big_alloc(n)`, `big_free`, `big_from_i64`, `big_neg`, `big_cmp`,
  `big_to_i64`. ELF runtime stub gets these symbols.
- Emit `IR_BMOV`/`IR_BNEG`/`IR_BCMP` via calls. Test: `let x: big = 5; let y = -x;`
- Verify self-host + a `big` test program runs.

**Stage 2 — add/sub/mul.**
- Runtime `big_add`, `big_sub`, `big_mul`. Emit IR_BADD/IR_BSUB/IR_BMUL.
- Test: 250-digit add/mul against Python reference.

**Stage 3 — div/mod.**
- Runtime `big_divmod` (schoolbook / Knuth Algorithm D). Emit IR_BDIV/IR_BMOD.
- Test against Python.

**Stage 4 — shifts + literals > 64-bit + auto-promotion.**
- `big_shl`/`big_shr`; `big_from_bytes` for huge literals; auto-promote
  overflowing `int` literals to `big`.

## Risks / open questions
- **Cycles:** `big` arithmetic in the runtime helpers is written in asm/C-like,
  not Quanta, so it does not affect the Quanta self-host fixpoint. The compiler
  source never uses `big`, so stages never re-exercise the new path during
  bootstrap. Good.
- **ABI for >6 limb returns:** result is always a pointer (8 bytes) — fits rax.
  No issue.
- **Garbage collection:** none planned; `big_free` is manual or leaked (fine
  for now). Note in docs.
- **i4096 vs unbounded:** target 64 limbs (4096 bits). Larger values overflow
  the fixed buffer → trap (fail-closed). `big` (unbounded heap) can be a later
  opt-in; for 0.0.81 the fixed 4096-bit buffer matches the stated goal.

## What is explicitly NOT done in this design pass
- Unbounded bignum (`big` heap growable) — fixed 4096-bit buffer for now.
- ARM64 backend big-int — deferred with ARM64 (POST-0.1.0).
- Operator overloading so `int`/`big` mix transparently — explicit conversion
  calls for 0.0.81.
