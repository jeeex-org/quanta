# ARM64 Backend Plan

**Status:** Draft for review  
**Date:** 2026-10-06  
**Author:** Hermes Agent  
**Target:** Quanta 0.0.226+

---

## 1. Executive Summary

Quanta 0.0.225 has a working x86-64 backend (16 files, ~21,000 lines). This plan scopes the work to add an ARM64 (AArch64) backend so Quanta can target the architectures that matter for kernel work: OpenHarmony LiteOS-A (Cortex-A), Android GKI (aarch64-only), and LiteOS-M (Cortex-M, ARM32 — future).

**Recommendation:** Path B — arch-abstracted backend. The frontend is not fully arch-independent (lexer, features, method, parse, funcscan all contain x86-specific patterns), so a parallel backend would require duplicating and maintaining two copies of the frontend. A shared IR with arch-dispatched backend is the correct long-term architecture.

---

## 2. Current State Analysis

### 2.1 File inventory

| File | Lines | x86-specific patterns | Role |
|---|---|---|---|
| `emitter.quanta` | 4,297 | 1,459 | Instruction encoding (biggest file) |
| `codegen.quanta` | 2,771 | 374 | Register allocation + IR dispatch |
| `parse.quanta` | 2,296 | 7 | Parser (mostly arch-independent) |
| `method.quanta` | 1,894 | 33 | Method/struct dispatch |
| `globals.quanta` | 1,570 | 46 | Global state + IR opcodes |
| `objfmt.quanta` | 1,413 | 74 | Object file format |
| `funcscan.quanta` | 1,296 | 41 | Function scanning |
| `entry.quanta` | 1,161 | 95 | `_start` + `__init` + `main` |
| `elf.quanta` | 983 | 7 | ELF header/section emission |
| `features.quanta` | 662 | 192 | Builtin function recognition |
| `lexer.quanta` | 549 | 46 | Tokenizer |
| `helpers.quanta` | 532 | 69 | Utility functions |
| `qobj_write.quanta` | 417 | 11 | Object cache serialization |
| `fconst.quanta` | 375 | 0 | Float constants (arch-independent) |

**Total:** 16 files, ~20,948 lines, ~2,492 x86-specific patterns.

### 2.2 What is arch-independent

- **IR opcodes** (`globals.quanta:1-71`): All 70+ opcodes are arch-neutral. `IR_ADD`, `IR_LOAD`, `IR_CALL`, etc. have no register or encoding assumptions.
- **Float constants** (`fconst.quanta`): 0 x86-specific patterns. Pure IEEE-754 bit manipulation.
- **Parser** (`parse.quanta`): Only 7 x86-specific patterns. The grammar is arch-neutral.
- **Type system, structs, enums, traits, generics**: All in the frontend, all arch-independent.

### 2.3 What is arch-specific

- **Instruction encoding** (`emitter.quanta`): 1,459 patterns. Every `eb()`, `ei()`, `eq()` call emits x86-64 bytes. The `mr()`, `ri()`, `rr()`, `ra()`, `rs()`, `rm()`, `rxor()`, `rand()`, `ror()`, `rcmp()`, `rtest()` helpers are all x86 ModR/M + opcode encoding.
- **Register allocation** (`codegen.quanta`): 374 patterns. `aphys()`, `rr()`, `flush_all()`, spill logic — all assume 16 GPRs with x86 names and the x86-64 calling convention (rdi, rsi, rdx, rcx, r8, r9 for args).
- **Syscall convention** (`entry.quanta`, `features.quanta`): x86-64 `syscall` instruction, nr in rax, args in rdi/rsi/rdx/r10/r8/r9.
- **ELF machine type** (`objfmt.quanta:398`, `elf.quanta:116,404`): Hardcoded `EM_X86_64` (62).
- **Builtin recognition** (`features.quanta`): 192 patterns. Syscall numbers, x86-64-specific builtins.
- **Entry stub** (`entry.quanta`): 95 patterns. `_start` reads argc/argv from the stack per x86-64 System V ABI.

### 2.4 The frontend is NOT fully arch-independent

This is the critical finding. The frontend files contain x86-specific patterns:

| Frontend file | x86 patterns | What they are |
|---|---|---|
| `features.quanta` | 192 | Syscall numbers, x86-64 builtin recognition |
| `funcscan.quanta` | 41 | Function scanning with x86 assumptions |
| `lexer.quanta` | 46 | Tokenizer with x86 keywords |
| `method.quanta` | 33 | Method dispatch with x86 patterns |
| `parse.quanta` | 7 | Minor x86 references |

This means **Path A (parallel backend) would require maintaining two copies of the frontend**, not just two backends. Path B is the only viable option.

---

## 3. Architecture Options

### Path A — Parallel Backend (rejected)

Write `src/arm64/` as a second independent backend, sharing only the IR opcodes.

**Pros:**
- Faster to start (no refactoring of existing code)
- x86-64 backend stays untouched

**Cons:**
- Frontend is not arch-independent — `features.quanta`, `funcscan.quanta`, `lexer.quanta`, `method.quanta` all need ARM variants
- Two copies of 21,000 lines to maintain
- Every new feature must be implemented twice
- The two backends will diverge over time

**Verdict:** Rejected. The frontend coupling makes this a maintenance nightmare.

### Path B — Arch-Abstracted Backend (recommended)

Introduce an arch abstraction layer between the IR and the backend. The frontend emits arch-neutral IR; a backend trait/vtable dispatches to x86-64 or ARM64 codegen.

**Pros:**
- Single frontend, single IR
- New backends (RISC-V, ARM32) become additive
- The abstraction forces clean separation of concerns
- Self-hosting: the compiler can compile itself for ARM64

**Cons:**
- Requires refactoring `emitter.quanta` (1,459 patterns) and `codegen.quanta` (374 patterns)
- The register allocator needs a register-description abstraction
- Upfront work before any ARM64 code is emitted

**Verdict:** Recommended. This is the correct architecture for a multi-target compiler.

---

## 4. Detailed Design

### 4.1 Register Description Table

Introduce a register description that both backends consume:

```quanta
struct RegDesc {
    count: i64          // number of GPRs (16 for x86-64, 31 for ARM64)
    arg_regs: [i64]     // argument registers (rdi..r9 / x0..x7)
    arg_count: i64      // number of arg regs (6 / 8)
    ret_reg: i64        // return value register (rax / x0)
    sp_reg: i64         // stack pointer (rsp / sp)
    fp_reg: i64         // frame pointer (rbp / x29)
    scratch: [i64]      // scratch registers for codegen
    name_prefix: string // "r" for x86, "x" for ARM64
    reg_size: i64       // 8 for both
}
```

The register allocator reads from this table instead of hardcoding x86 register names.

### 4.2 Instruction Emitter Abstraction

The emitter is the biggest challenge. Two sub-approaches:

**Sub-approach 1 — Arch-specific emitter files:**
- `emitter_x86.quanta` — current x86-64 encoding
- `emitter_arm64.quanta` — new ARM64 encoding
- A shared `emitter.quanta` that dispatches based on `target_arch`

**Sub-approach 2 — Instruction builder API:**
- Define arch-neutral "instruction descriptors" (e.g., `AddRegReg(dst, src)`, `LoadReg(dst, base, off)`, `Call(func)`)
- Each backend implements the descriptor → bytes lowering

**Recommendation:** Sub-approach 1 for the initial port. It's simpler and the x86-64 emitter is already working. Sub-approach 2 can be a later refactor if a third backend is added.

### 4.3 Syscall Convention Abstraction

| | x86-64 | ARM64 |
|---|---|---|
| Instruction | `syscall` | `svc #0` |
| Syscall nr | rax | x8 |
| Arg 1 | rdi | x0 |
| Arg 2 | rsi | x1 |
| Arg 3 | rdx | x2 |
| Arg 4 | r10 | x3 |
| Arg 5 | r8 | x4 |
| Arg 6 | r9 | x5 |
| Return | rax | x0 |
| Error | rax (negative) | x0 (negative) |

The `syscall` builtin in `features.quanta` needs to emit the correct instruction based on `target_arch`.

### 4.4 ELF Differences

| | x86-64 | ARM64 |
|---|---|---|
| `e_machine` | 62 (`EM_X86_64`) | 183 (`EM_AARCH64`) |
| Relocation types | `R_X86_64_*` | `R_AARCH64_*` |
| Calling convention | System V AMD64 ABI | AAPCS64 |
| Stack alignment | 16-byte | 16-byte |
| Instruction size | Variable (1-15 bytes) | Fixed 4 bytes |
| Endianness | Little | Little |

### 4.5 Calling Convention Differences

| | x86-64 (System V AMD64) | ARM64 (AAPCS64) |
|---|---|---|
| Arg registers | rdi, rsi, rdx, rcx, r8, r9 | x0, x1, x2, x3, x4, x5, x6, x7 |
| Return value | rax | x0 |
| Stack alignment | 16-byte at call | 16-byte at call |
| Varargs | al = vector reg count | No equivalent (different mechanism) |
| Red zone | 128 bytes below rsp | None |
| Callee-saved | rbx, rbp, r12-r15 | x19-x28, x29 (fp), x30 (lr) |

### 4.6 Memory Model

x86-64 has a strong memory model (TSO). ARM64 has a weak memory model. This affects:
- `IR_VOLATILE_LOAD` / `IR_VOLATILE_STORE` — need explicit barriers on ARM64
- `atomic_add` and other atomics — need `ldadd`/`ldxr`+`stxr` on ARM64 vs `lock xadd` on x86-64
- Fence builtins — `mfence`/`sfence`/`lfence` on x86-64 vs `dmb`/`dsb`/`isb` on ARM64

---

## 5. Implementation Plan

### Phase 1: Arch Abstraction Layer (foundation)

**Goal:** Introduce `target_arch` and the register description table without breaking x86-64.

1. Add `target_arch` global (0 = x86-64, 1 = ARM64) to `globals.quanta`
2. Add `RegDesc` struct and two instances (`regdesc_x86`, `regdesc_arm64`)
3. Refactor `codegen.quanta` to read register properties from `RegDesc` instead of hardcoding
4. Add `EM_AARCH64 = 183` and `R_AARCH64_*` relocation constants to `elf.quanta`
5. Gate all existing x86-64 code behind `if target_arch == 0`

**Deliverable:** x86-64 backend still passes all 19 gates. No ARM64 code yet.

### Phase 2: ARM64 Emitter

**Goal:** Write `emitter_arm64.quanta` with the full ARM64 instruction encoding.

1. Implement ARM64 instruction encoding helpers:
   - `a64_mov_reg(dst, src)` — `mov xD, xS` (ORR xD, xZR, xS)
   - `a64_mov_imm(dst, imm)` — `movz`/`movk` sequence
   - `a64_add_reg(dst, src1, src2)` — `add xD, xS1, xS2`
   - `a64_sub_reg`, `a64_mul_reg`, `a64_div_reg`
   - `a64_ldp`/`a64_stp` — load/store pair
   - `a64_ldr`/`a64_str` — load/store with immediate offset
   - `a64_b`/`a64_bl` — branch/branch-with-link
   - `a64_ret` — `ret`
   - `a64_svc` — `svc #0` (syscall)
   - `a64_cmp`/`a64_b_cond` — compare and conditional branch
2. Implement condition codes (eq, ne, lt, gt, le, ge, etc.)
3. Implement shift operations (lsl, lsr, asr, ror)
4. Implement bitwise operations (and, orr, eor, mvn)

**Deliverable:** `emitter_arm64.quanta` compiles as a module. No integration yet.

### Phase 3: ARM64 Codegen

**Goal:** Wire ARM64 emitter into the IR dispatch.

1. Add ARM64 register allocator (31 GPRs, AAPCS64 calling convention)
2. Add ARM64 spill/reload logic
3. Add ARM64 function prologue/epilogue (stp x29, x30, [sp, #-16]! / ldp x29, x30, [sp], #16)
4. Add ARM64 syscall convention (nr in x8, args in x0-x5)
5. Add ARM64 `_start` stub (read argc/argv from sp per AAPCS64)
6. Add ARM64 ELF emission (e_machine = 183, R_AARCH64 relocations)

**Deliverable:** `qc --arch=arm64` produces a valid ARM64 ELF.

### Phase 4: Self-Hosting on ARM64

**Goal:** The Quanta compiler compiles itself for ARM64.

1. Build `qc` for ARM64: `qc --arch=arm64 src/compiler.quanta qc_arm64`
2. Run the ARM64 `qc` under QEMU user-mode emulation
3. Verify the ARM64 `qc` can compile a test program
4. Run the full test suite under QEMU

**Deliverable:** Self-hosting ARM64 compiler passes all gates under QEMU.

### Phase 5: Bare-Metal ARM64

**Goal:** Quanta can compile a bare-metal ARM64 kernel (no OS).

1. Add `--bare-metal` flag (no `_start`, no syscalls, no libc)
2. Implement ARM64 MMIO access (volatile load/store with barriers)
3. Implement ARM64 atomic operations (ldadd, ldxr/stxr)
4. Implement ARM64 interrupt handling (sti/cli equivalent — `msr daifset`/`msr daifclr`)
5. Test with a minimal bare-metal kernel that prints via UART

**Deliverable:** A bare-metal ARM64 kernel written in Quanta boots in QEMU and prints "Hello from Quanta" via UART.

---

## 6. Milestones

| Milestone | Deliverable | Gates |
|---|---|---|
| M1: Arch abstraction | x86-64 still green, `target_arch` global | 19/19 GREEN |
| M2: ARM64 emitter | `emitter_arm64.quanta` compiles | Module compiles |
| M3: ARM64 codegen | `qc --arch=arm64` produces valid ELF | `file` reports ARM64 |
| M4: Self-hosting | ARM64 qc compiles itself under QEMU | Self-host test passes |
| M5: Bare-metal | Quanta kernel boots on ARM64 QEMU | UART output |

---

## 7. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Emitter refactoring breaks x86-64 | High | Gate after every change; 19 gates must stay green |
| ARM64 instruction encoding errors | High | Differential testing: compile same program for both archs, compare behavior |
| Register allocator bugs | High | Start with a simple linear allocator; optimize later |
| Self-hosting fails | Medium | Fall back to cross-compilation (x86-64 qc → ARM64 binary) |
| Weak memory model bugs | Medium | Extensive volatile/atomic testing; compare with x86-64 behavior |
| Scope creep | Medium | Stick to the phases; no extra features until M5 |

---

## 8. Open Questions

1. **QEMU availability:** Is `qemu-user` and `qemu-system` available on this box for ARM64 testing?
2. **Cross-compilation vs self-hosting:** Should M4 use cross-compilation (x86-64 qc → ARM64) or full self-hosting (ARM64 qc → ARM64 qc)? Cross-compilation is easier but doesn't prove the backend works.
3. **ARM32 (Cortex-M):** Is ARM32 in scope for this plan, or only ARM64? ARM32 is a separate instruction set (Thumb-2) and would be a Phase 6+.
4. **RISC-V:** Is RISC-V a future target? If so, the emitter abstraction should be designed for three backends from the start.
5. **Float/SIMD:** ARM64 has NEON. Is NEON support in scope, or only scalar f64?

---

## 9. Estimate

This is a large piece of work. The x86-64 backend is ~21,000 lines. The ARM64 backend will be comparable in size, but the arch abstraction layer reduces the frontend duplication.

| Phase | Effort |
|---|---|
| M1: Arch abstraction | Medium (refactoring, no new code) |
| M2: ARM64 emitter | Large (new instruction encoding) |
| M3: ARM64 codegen | Large (register allocator, prologue/epilogue, ELF) |
| M4: Self-hosting | Medium (debugging, QEMU integration) |
| M5: Bare-metal | Medium (MMIO, atomics, interrupts) |

**Total:** Comparable to the original x86-64 backend development, but with the advantage of a working reference implementation to compare against.

---

## 10. Recommendation

Proceed with Path B (arch-abstracted backend). Start with M1 (arch abstraction layer) and verify all 19 gates stay green before writing any ARM64 code. The key insight is that the frontend is not arch-independent, so a parallel backend would require maintaining two copies of the frontend — Path B is the only sustainable option.

The first milestone (M1) is low-risk and high-value: it establishes the abstraction without changing any behavior. If M1 goes smoothly, M2-M5 are mechanical (if large) work.
