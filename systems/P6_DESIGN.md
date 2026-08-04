# P6: Low-Level Features — Design & Implementation Plan

## Overview
P6 adds raw pointers, pointer arithmetic, inline assembly, volatile operations, and unsafe blocks. This enables FFI, OS kernels, MMIO drivers, and bare-metal programming.

## Syntax Design

### 1. Raw Pointer Types
```quanta
// Pointer type syntax (prefix *)
*T          // immutable raw pointer to T
*mut T      // mutable raw pointer to T

// Examples
let p: *i64 = 0x1000 as *i64
let q: *mut u8 = mmap(4096) as *mut u8
```

### 2. Pointer Operations
```quanta
// Dereference (raw, no bounds check)
let val = *p              // read through *T
*p = val                  // write through *mut T

// Pointer arithmetic (element-sized, like C)
let p2 = p + 4            // p + 4 * sizeof(T)
let p3 = p - 2            // p - 2 * sizeof(T)
let diff = p2 - p         // ptrdiff_t (elements)

// Pointer comparison
if p == q { ... }
if p < q { ... }

// Cast between pointer and integer
let addr = p as usize     // *T -> usize
let p = addr as *mut T    // usize -> *mut T

// Null pointer
let null: *mut T = 0 as *mut T
if p.is_null() { ... }
```

### 3. Unsafe Blocks
```quanta
// Existing unsafe block syntax (already in compiler)
unsafe {
    // Inside: overflow/shift traps disabled
    // Raw pointer ops allowed
    // Extern calls allowed
    let x = *raw_ptr
    asm!("mov rax, {}", in(reg) x)
}
```

### 4. Inline Assembly
```quanta
// Basic syntax
asm!("instruction", options...)

// With operands
asm!(
    "add {}, {}",
    in(reg) a,
    out(reg) result,
    clobbers("cc")
)

// Volatile asm (side effects, not optimized away)
asm!("mov {}, cr0", out(reg) val, options(volatile, nomem))

// Example: read/write CR0
fn read_cr0() -> u64 {
    let val: u64
    asm!("mov {}, cr0", out(reg) val, options(nomem, nostack))
    val
}

fn write_cr0(val: u64) {
    asm!("mov cr0, {}", in(reg) val, options(nostack))
}
```

### 5. Volatile Operations (MMIO)
```quanta
// Volatile read/write — never optimized away, ordered
let val = volatile_load(ptr as *const u32)
volatile_store(ptr as *mut u32, val)

// Shorthand for device registers
let uart_dr = 0x09000000 as *mut u32
volatile_store(uart_dr, b'A' as u32)
```

## IR Extensions

### New IR Opcodes
```c
// In IR enum
IR_RAW_PTR      // *T type
IR_MUT_PTR      // *mut T type
IR_DEREF        // *p (load through raw ptr)
IR_DEREF_MUT    // *p = v (store through raw ptr)
IR_PTR_ADD      // p + n (element-sized)
IR_PTR_SUB      // p - n
IR_PTR_DIFF     // p - q (elements)
IR_PTR_CAST     // p as usize / usize as *T
IR_IS_NULL      // p == 0
IR_VOLATILE_LOAD
IR_VOLATILE_STORE
IR_ASM          // inline assembly
```

### Type System
- Pointer types carry pointee type for arithmetic scaling
- `*T` and `*mut T` are distinct (like Rust)
- `usize` = pointer-sized integer (u64 on current targets)

## Backend Implementation

### x86_64 (sysv_amd64_abi)
| Operation | Instruction Sequence |
|-----------|---------------------|
| `*p` | `mov rax, [rdi]` |
| `*p = v` | `mov [rdi], rsi` |
| `p + n` | `lea rax, [rdi + rsi*8]` (scale by sizeof(T)) |
| `volatile_load` | `mov rax, [rdi]` + compiler barrier |
| `volatile_store` | `mov [rdi], rsi` + compiler barrier |
| `asm!` | Emit raw assembly with register allocation |

### ARM64 (aapcs64)
| Operation | Instruction Sequence |
|-----------|---------------------|
| `*p` | `ldr x0, [x0]` |
| `*p = v` | `str x1, [x0]` |
| `p + n` | `add x0, x0, x1, lsl #3` (scale by 8) |
| `volatile_load` | `ldr x0, [x0]` + `dmb ish` |
| `volatile_store` | `str x1, [x0]` + `dmb ish` |
| `asm!` | Emit raw assembly with register constraints |

## Test Fixtures Required (per P5 rule)

| Test | Description | Expected Exit |
|------|-------------|---------------|
| `ptr_basic.quanta` | Raw pointer deref read/write | 42 |
| `ptr_arith.quanta` | Pointer +/-, element scaling | 100 |
| `ptr_cast.quanta` | ptr↔usize cast, null check | 0 |
| `unsafe_basic.quanta` | Unsafe block disables traps | 0 |
| `asm_basic.quanta` | Inline asm with in/out operands | 7 |
| `asm_volatile.quanta` | Volatile asm not optimized away | 0 |
| `volatile_load_store.quanta` | MMIO-style volatile ops | 0 |
| `ptr_comparison.quanta` | ==, !=, <, > on pointers | 1 |

## Implementation Order

1. **Type system**: Add `*T` and `*mut T` to parser/typechecker
2. **IR**: Add opcodes, update IR builder
3. **x86_64 backend**: Implement codegen for all ops
4. **ARM64 backend**: Implement codegen for all ops
5. **Inline asm**: Parser → IR → both backends
6. **Volatile ops**: Compiler barriers + memory barriers
7. **Test fixtures**: Create all 8 test files
8. **Self-host**: Verify x86_64 fixed-point
9. **ARM64 cross-compile**: Verify on device
10. **Promote**: qc-0.0.4

## Open Decisions (from ROADMAP-2.0)

1. **Ownership vs GC**: P6 uses ownership (Rust-like). Raw pointers are non-owning, no borrow checking.
2. **Nominal vs structural interfaces**: Pointer types are structural (type = pointee type + mutability).
3. **ARM64 first**: Ensure ARM64 backend complete before x86_64 for P6 (test on device early).

## Files to Modify

- `src/qc-0.0.3-wip.quanta` — main compiler (parser, typechecker, IR, backends)
- `test_suites/codes/` — 8 new test fixtures
- `test_suites/EXPECTED.tsv` — add expected exit codes
- `docs/SYNTAX.md` — document P6 syntax