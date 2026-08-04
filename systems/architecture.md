## 6. Architecture

### 6.1 Pipeline

```
Source (.quanta) → Tokenizer → Scanner (fns/structs/enums/traits/impls/globals) →
Parser (recursive descent → flat per-function IR) → Optimizer (const-fold, DCE,
tail-call, loop strength) → Register allocator (linear, home-slot spill) →
Code generator (ci_func x86-64 / arm_ci_func ARM64) → ELF writer → Binary
```

Single-file compiler source (`src/qc-0.0.14-wip.quanta`, ~7,700 lines). Both
backends live in one file; `target_arch` (set by `--target=arm64`) selects
`arm_ci_func`/ARM ELF at emit time.

### 6.2 IR ops (actual values from source)

Each instruction is a 5-word slot (40 B): `op, result-vreg, arg0, arg1, arg2`.

| Op | # | Description | Op | # | Description |
|----|---|-------------|----|---|-------------|
| IR_CONST | 0 | Load constant | IR_BR | 20 | Branch (cond) |
| IR_MOV | 1 | Move vreg | IR_RET | 21 | Return |
| IR_ADD | 2 | Add | IR_PARAM | 22 | Param binding |
| IR_SUB | 3 | Subtract | IR_STR | 23 | String const |
| IR_MUL | 4 | Multiply | IR_BAND | 24 | AND |
| IR_DIV | 5 | Divide | IR_BOR | 25 | OR |
| IR_MOD | 6 | Modulo | IR_BXOR | 26 | XOR |
| IR_EQ | 7 | Equal | IR_BNOT | 27 | Bitwise NOT |
| IR_NE | 8 | Not equal | IR_SHL | 28 | Shift left |
| IR_LT | 9 | Less than | IR_SHR | 29 | Shift right |
| IR_GT | 10 | Greater than | IR_LOADG | 30 | Load global |
| IR_LE | 11 | ≤ | IR_STOREG | 31 | Store global |
| IR_GE | 12 | ≥ | IR_ISTORE | 33 | Field/array write |
| IR_AND | 13 | Logical AND | IR_TALLOC | 34 | Tuple/array alloc |
| IR_OR | 14 | Logical OR | IR_FNPTR | 35 | Function pointer |
| IR_NEG | 15 | Negate | IR_CLOSURE_CALL | 36 | Indirect closure |
| IR_NOT | 16 | Logical NOT | IR_FREE | 37 | Ownership free |
| IR_CALL | 17 | Function call | IR_FCONST | 38 | Float const |
| IR_LABEL | 18 | Label | IR_FADD/FSUB/FMUL/FDIV | 39-42 | Float arith |
| IR_JMP | 19 | Jump | IR_ENUM | 45 | Enum variant create |
| IR_MATCH | 46 | Match | IR_SOME/NONE/OK/ERR | 47-50 | Option/Result ctor |
| IR_UNWRAP | 51 | Unwrap | IR_VTABLE | 52 | Vtable |
| IR_DYN | 53 | Dyn trait | IR_RAW_PTR | 54 | Raw ptr type |
| IR_MUT_PTR | 55 | Mut ptr type | IR_DEREF | 56 | Ptr deref |
| IR_DEREF_MUT | 57 | Mut deref | IR_PTR_ADD/SUB/DIFF | 58-60 | Ptr arith |
| IR_PTR_CAST | 61 | Ptr cast | IR_IS_NULL | 62 | Null check |
| IR_VOLATILE_LOAD/STORE | 63-64 | Volatile | IR_ASM | 65 | Inline asm |
| IR_FFI_CALL | 66 | FFI call | IR_UNSAFE_BLOCK | 68 | Unsafe marker |
| IR_ARRAY_LEN | 69 | Array len `[base]` | | | |

> Note: op 32 (IR_IDX, field/array read) is used in parser code as `iremit(32, ...)`; op 44/67 are unassigned. IR_ARRAY_LEN (69) has an **x86 handler only** — see known_warts_bugs.md §10.2 for the ARM64 gap.

### 6.3 Optimizer

| Pass | Function | Description |
|------|----------|-------------|
| A | Const-fold | Constant expression evaluation; algebraic id (`x*1`, `x+0`, `x&-1`); **refuses to fold comparison ops** (loop-liveness safety, 2026-08-03) |
| B | Tail-call | Call → jmp for tail position |
| C | DCE | Dead code elimination (unreachable branches, dead stores) |
| D | Loop strength | Closed-form sum reduction |

Default ON. Verified large speedup on arithmetic-progression loop.

### 6.4 Code generation — x86-64

- ABI: args RDI, RSI, RDX, RCX, R8, R9; return RAX; callee-saved RBX, RBP, R12–R15
- vregs → scratch regs (RAX, RCX, RDX, RSI, RDI, R8–R11); spill to `[rbp - offset]` (home slots)
- Prologue: `push rbp; mov rbp, rsp; sub rsp, <frame_size>`
- Epilogue: `mov rsp, rbp; pop rbp; ret`
- Overflow/shift/bounds traps ON by default (`jo`/`ud2`), suppressed inside `unsafe {}`

### 6.5 Code generation — ARM64

- ABI: args X0–X5; return X0; callee-saved X19–X30
- Frame: X29, link register X30
- Prologue: `stp x29, x30, [sp, #-16]!; mov x29, sp; sub sp, sp, <frame_size>`
- Epilogue: `ldp x29, x30, [sp], #16; ret`
- Static PIE ELF output (ET_DYN, ASLR-safe — only PC-relative addressing survives); `.o` object emission supported
- ⚠️ Not all x86 IR ops are ported (IR_ARRAY_LEN etc.) — see known_warts_bugs.md §10.2

### 6.6 Binary format

**x86-64:** Standard ELF64 ET_EXEC — `\x7fELF` class 2, one PT_LOAD at vaddr
`0x400000` (R+X), code+data appended, RW LOAD at `0x42200000` with BSS
(MemSiz ≥ FileSiz). Mode 0755.

**ARM64:** Static PIE ELF (ET_DYN, position-independent). Tested on real
Android devices (Termux SSH port 8022) + qemu-aarch64.

### 6.7 Syscalls (Linux)

| Op | x86-64 | ARM64 |
|----|--------|-------|
| read | 0 | 63 |
| write | 1 | 64 |
| open | 2 | 56 |
| close | 3 | 57 |
| exit | 60 | 93 |
| mmap | 9 | 222 |
| munmap | 11 | 215 |

---