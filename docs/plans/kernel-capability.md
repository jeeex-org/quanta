# Kernel-Capability Plan: Operand ASM, Naked Functions, Section/Symbol Control

**Status:** Phases A and A2 complete — B onward open
**Date:** 2026-10-11 (updated 2026-10-12)
**Target:** Quanta 0.0.226+
**Stable at time of writing:** 0.0.225

**Progress:** A ✅ · A2 ✅ · B ⬜ · B2 ⬜ · C1 ⬜ · C2 ⬜ · D ⬜

---

## 1. Goal

Close the verified gaps that block Quanta from expressing a kernel's machine-specific layer. Each gap was confirmed by reading current source (`compiler/0.0.225/src/x86/`) and by executing test programs, not by inference from docs.

**Outcome:** Quanta can express a bootable bare-metal x86-64 program — its own IDT, its own interrupt handlers, its own atomics, its own MMIO.

**Non-goal:** Rewriting Linux. This plan builds the *language capability*. What gets written with it is a separate decision.

---

## 2. Verified Current State

### 2.1 What already works (tested this session)

| Capability | Evidence |
|---|---|
| `atomic_add(ptr,val)` | emits `lock xadd [rdi],rsi`; tested 10+5=15 |
| `atomic_cmpxchg(ptr,exp,new)` | tested: old=5, new=99 |
| `atomic_swap` / `atomic_load` / `atomic_store` | present in `features.quanta:657+` |
| `fence()` / `mfence()` / `lfence()` / `sfence()` | `features.quanta:688-690` |
| `volatile *p` load / `volatile *p = v` store | `parse.quanta:2240-2266`; tested, returns 42 |
| `bitfield(x, off, wid)` | `features.quanta:509` |
| `syscall(n,...)` arity 1..7 | `features.quanta:526-527` |
| `mem_load8` / `mem_store8` | true 8-bit widths |
| `mmap`, raw pointers, `*T`, `*mut T` | tested |

**This corrects an earlier claim of mine.** I previously told the user atomics were "single-threaded only" and that operand asm was the *sole* blocker. The atomic and barrier primitives are in fact present and working. The real remaining set is below.

### 2.2 The four gaps

**Gap 1 — Operand-bearing `asm!`**
`asm!` accepts only a string template. Parser at `method.quanta:629-650` requires `TT_STR` immediately after `(` and `)` immediately after; there is no operand, constraint, or clobber parsing anywhere in the file (verified: 0 matches for `operand|constraint|clobber` in that block). Result convention is RAX only (`codegen.quanta:2679-2700`).

Confirmed by execution: emitting `lock xadd [rax],rcx` segfaults, because there is no syntax to say RAX holds the pointer.

**Gap 2 — 16/32-bit memory access (defect, not a missing feature)**
`mem_load16` / `mem_store16` / `mem_load32` / `mem_store32` **do not exist** in the compiler. Only `mem_load`, `mem_load8`, `mem_store`, `mem_store8` are real (`emitter.quanta:2203-2222`).

They do not error — they fall through to the 64-bit path. Confirmed by execution:

```
mem_store(p+4, 999)      // sentinel
mem_store32(p, 1)        // "32-bit" store
mem_load(p+4)  →  0      // clobbered. A real 32-bit store leaves 999.
```

A 32-bit device register write corrupts its neighbour. This is a correctness bug independent of the kernel work.

**Gap 3 — `naked fn`, `section`, `no_mangle`**
- `naked`: 0 references in source. No way to write a function whose prologue/epilogue the compiler does not emit.
- `section`: 26 references, all internal ELF section handling. No user-facing way to place a function in `.text.startup` or a data object in a named section.
- `no_mangle` / `export_name`: 0 references. No way to give a function an exact symbol name.

An interrupt handler must be a naked function at a known symbol, in a known section. None of the three is expressible today.

**Gap 4 — Ring-0 entry (IDT/GDT, privilege transition)**
0 references to `interrupt|naked|isr|idt|gdt|ring0`. Quanta emits `_start` → `__init` → `main` → `exit` for a userspace process. There is no mechanism to install a trap gate and return via `iretq`.

This is an emitter feature, not a language feature, and it depends on Gap 3.

**Gap 5 — `asm!` silently emits garbage for non-hex input (defect)**
The `IR_ASM` handler (`codegen.quanta:2904-2930`) walks the template collecting *hex digit pairs* and emits each as one byte. Any character that is not `[0-9a-fA-F]` is skipped silently, and the emitter never errors. Confirmed by execution:

```
asm!("lock cmpxchg [rdi], rsi")   // textual mnemonics
→ COMPILES CLEAN. Emits a few stray bytes. Program traps (SIGTRAP).
```

The characters `l`, `o`, `c`, `k`, `c`, `m`, `p`, `x`, `g`, `h` are all valid hex digits, so the template is misparsed into nonsense bytes rather than rejected. `asm!("mov eax, 42")` likewise compiles and produces an executable that does not do what it says.

This matters for Phase C: the failure mode is silent, so any operand work built on this path inherits it. **Phase C must add validation that rejects non-hex input**, or replace the hex path entirely.

---

## 3. Proposed Approach

Four independent workstreams, ordered by dependency and risk.

| Phase | Work | Risk | Status |
|---|---|---|---|
| **A** | 16/32-bit memory widths | Low | ✅ **DONE** — commit `452e5285` |
| **A2** | `asm!` rejects non-hex input | Low | ✅ **DONE** — commit `452e5285` |
| **B** | `naked fn` + `section` + `no_mangle` | Low | ⬜ open |
| **B2** | `packed` structs / explicit field offsets | Medium | ⬜ open |
| **C1** | Minimal x86 assembler | High | ⬜ open |
| **C2** | Operands + constraints | **High** | ⬜ open |
| **D** | Ring-0 entry (IDT/GDT) | Medium | ⬜ open |

**Order rationale:** A and A2 were bug fixes with a small blast radius — done first to get a clean baseline. B and B2 are additive syntax with no interaction with the register allocator — do them second. C1/C2 are the hard ones and want a stable base. D is last because it consumes B, B2 and C.

**Versioning** (one per phase, per convention — new feature → next sequential number):

| Phase | Version | Status |
|---|---|---|
| A | 0.0.225 (folded in) | ✅ done |
| A2 | 0.0.225 (folded in) | ✅ done |
| B | 0.0.226 | ⬜ |
| B2 | 0.0.227 | ⬜ |
| C1 (assembler) | 0.0.228 | ⬜ |
| C2 (operands) | 0.0.229 | ⬜ |
| D | 0.0.230 | ⬜ |

A and A2 landed inside 0.0.225 rather than as separate versions — both were defect fixes, not features, so they did not take a version number. Subsequent phases start at 0.0.226.

Phase C is deliberately split: the assembler and the operand/constraint machinery are separable and the assembler is independently testable.

---

## 3a. Completed: Phases A and A2 ✅

**Commit:** `452e5285` — *"fix: mem_store16/32 silent clobber + asm! silent garbage"*, 2026-10-12.

### A — 16/32-bit memory widths

Implemented in `compiler/0.0.225/src/x86/emitter.quanta`:

| Builtin | Encoding |
|---|---|
| `mem_load16` | `movzx rax, word[rdi]` |
| `mem_load32` | `mov eax, [rdi]` (zero-extends) |
| `mem_store16` | `mov [rdi], si` |
| `mem_store32` | `mov [rdi], esi` |

**Verified by execution** against `compiler/0.0.225/bin/x86/qc` — 7/7 checks pass:

| Check | Result |
|---|---|
| 8-bit store/load round-trip | ✅ |
| 8-bit no-clobber (neighbour intact) | ✅ |
| 16-bit round-trip (40000) | ✅ |
| 16-bit no-clobber | ✅ |
| 32-bit round-trip (3000000000) | ✅ |
| 32-bit no-clobber | ✅ |
| 16-bit zero-extension of 65535 | ✅ |

The original defect is gone: `mem_store(p+4,999); mem_store32(p,1); mem_load(p+4)` now returns **999**, not 0.

### A2 — `asm!` input validation

Implemented in `compiler/0.0.225/src/x86/codegen.quanta` (the `IR_ASM` handler). Added compile-time rejection:

| Template | Result |
|---|---|
| `asm!("zz")` | ✅ rejected — `invalid hex char in asm! template` |
| `asm!("abc")` | ✅ rejected — `odd number of hex digits in asm! template` |
| `asm!("b8 2a")` | ✅ accepted (valid) |
| `asm!("b8 2a 00 00 00")` | ✅ accepted (valid) |

Whitespace (spaces, tabs, newlines) is allowed between byte pairs.

### Gate

Full suite re-run after both fixes: **20/20 gates GREEN** — functional, native, float-oper, float-builtin, float-return, float-operpath, extern-c, extern-ld, security, performance, valgrind, fuzz, differential, generics, stdlib, multi-tu, gguf-corrupt, verify-status, qobj — plus G4 9/9, G4TRANS 8/8, QOBJ 17/17, G6 5/5.

### Scope note

A2 made `asm!` **safe** (invalid input is rejected rather than silently miscompiled) but did **not** add an assembler. `asm!` still takes hex bytes only. Phase C1 remains the work that turns mnemonics into encodings, and C2 remains the operand/constraint machinery.

---

## 4. Phase A — 16/32-bit memory widths ✅ COMPLETED

> **Status: DONE (commit `452e5285`).** Kept below for the record — the task text describes the work as planned, and the verification steps were run and passed. Do not re-implement.

**Goal:** `mem_load16/32`, `mem_store16/32` do real width-limited access.

### Task A1: Write the failing test

**Files:**
- Create: `test_suites/codes/mem_width_test.quanta`
- Modify: `test_suites/EXPECTED.tsv`

```quanta
// Each width must touch exactly its own bytes. A 32-bit store that is
// silently 64-bit clobbers the neighbouring word -- see A1's sentinel check.
fn main() {
  let ok = 0

  // 8-bit
  let p = mmap(32)
  mem_store(p + 8, 999)
  mem_store8(p, 200)
  if mem_load8(p) == 200 { ok = ok + 1 }
  if mem_load(p + 8) == 999 { ok = ok + 1 }   // 8-bit store did not clobber

  // 16-bit
  mem_store(p + 8, 999)
  mem_store16(p, 40000)
  if mem_load16(p) == 40000 { ok = ok + 1 }
  if mem_load(p + 8) == 999 { ok = ok + 1 }   // 16-bit store did not clobber

  // 32-bit
  mem_store(p + 8, 999)
  mem_store32(p, 3000000000)
  if mem_load32(p) == 3000000000 { ok = ok + 1 }
  if mem_load(p + 8) == 999 { ok = ok + 1 }   // 32-bit store did not clobber

  // zero-extension: a 16-bit load of 0xFFFF must be 65535, not 18446744073709551615
  mem_store32(p, 65535)
  if mem_load16(p) == 65535 { ok = ok + 1 }

  exit(ok)   // expect 8
}
```

Append to `test_suites/EXPECTED.tsv`:
```
mem_width_test.quanta	8
```

**Step 1: Run and verify failure**

```bash
cd /opt/tali/quanta
QC=compiler/0.0.225/bin/x86/qc
$QC test_suites/codes/mem_width_test.quanta /tmp/mw && /tmp/mw; echo "rc=$?"
```
Expected: `rc` is **not** 8 — the clobber checks fail because `mem_store16/32` currently emit 64-bit stores.

**Step 2: Implement**

**Files:**
- Modify: `compiler/0.0.226/src/x86/emitter.quanta:2203-2222`
- Modify: `compiler/0.0.226/src/x86/features.quanta` (builtin recognition)

The current matcher dispatches on `nl` (name length) and `r8(nm+4)`. It needs to distinguish the digit suffix. Replace the `mem_` block with explicit length checks:

```quanta
// mem_load / mem_load8 / mem_load16 / mem_load32
// mem_store / mem_store8 / mem_store16 / mem_store32
if nl>=8&&r8(nm)=='m'&&r8(nm+1)=='e'&&r8(nm+2)=='m'&&r8(nm+3)=='_' {
    flush_all()
    if r8(nm+4)=='l' {
        if nl==12 {                                    // mem_load16
            eb(72); eb(15); eb(183); eb(7); return 1   // movzx rax,word[rdi]
        }
        if nl==12&&r8(nm+10)=='3' {                    // mem_load32
            eb(139); eb(7); return 1                   // mov eax,[rdi]  (zero-extends)
        }
        if nl==9 { eb(72); eb(15); eb(182); eb(7); return 1 }  // mem_load8
        eb(72); eb(139); eb(7); return 1               // mem_load
    }
    if r8(nm+4)=='s' {
        if nl==12 {                                    // mem_store16
            eb(102); eb(137); eb(55); return 1         // mov [rdi],si
        }
        if nl==12&&r8(nm+10)=='3' {                    // mem_store32
            eb(137); eb(55); return 1                  // mov [rdi],esi
        }
        if nl==10 { /* existing mem_store8 null-guarded path */ }
        eb(72); eb(137); eb(55); return 1              // mem_store
    }
}
```

**Pitfall to avoid:** `nl==12` matches both `mem_load16` and `mem_load32` (both 11 chars → nl 11; verify exact lengths with a probe before writing the branch). Disambiguate on the suffix character, as above, and **verify the lengths empirically** — do not trust the count in this document.

**Step 3: Verify**

```bash
$QC test_suites/codes/mem_width_test.quanta /tmp/mw && /tmp/mw; echo "rc=$?"
```
Expected: `rc=8`.

**Step 4: Full gate**

```bash
QC=compiler/0.0.226/bin/x86/qc bash test_suites/scripts/run_tests.sh
```
Expected: all gates GREEN, no regression.

**Step 5: Commit**

```bash
git add test_suites/codes/mem_width_test.quanta test_suites/EXPECTED.tsv \
        compiler/0.0.226/src/x86/emitter.quanta compiler/0.0.226/src/x86/features.quanta
git commit -m "fix: mem_load16/32 + mem_store16/32 emit true-width accesses"
```

---

## 5. Phase B — `naked fn`, `section`, `no_mangle`

**Goal:** A function can be declared without prologue/epilogue, placed in a named section, and given an exact symbol.

### Task B1: Lexer keywords

**Files:** Modify `compiler/0.0.227/src/x86/lexer.quanta:430-440`, `compiler/0.0.227/src/x86/helpers.quanta:255-280`

Add three keywords following the existing char-code pattern (e.g. `naked` = n-a-k-e-d). Register `TT_NAKED`, `TT_SECTION`, `TT_NOMANGLE`. Follow the existing convention exactly — `helpers.quanta:261` shows the pattern, and `:273` warns about duplicate keyword codes (a past bug: `asm` was assigned 53 then corrected to 40). **Check for collisions before assigning.**

### Task B2: Parser — `naked fn`

**Files:** Modify `compiler/0.0.227/src/x86/method.quanta` (fn parsing), `compiler/0.0.227/src/x86/parse.quanta`

Accept `naked fn name(...) { ... }` before the existing `fn` handling. Set a per-function flag.

### Task B3: Codegen — suppress prologue/epilogue

**Files:** Modify `compiler/0.0.227/src/x86/codegen.quanta` (the `ci_func` frame setup, around `:1079-1150`)

When the naked flag is set, skip the frame allocation, the register saves, and the `ret`. The body is emitted verbatim.

**Critical:** a naked function cannot use the normal vreg spill machinery, because there is no frame. Document this constraint and fail closed — a compile error is correct, silent corruption is not.

### Task B4: `section` and `no_mangle`

**Files:** Modify `compiler/0.0.227/src/x86/objfmt.quanta`, `compiler/0.0.227/src/x86/elf.quanta`

`section("...")` on a function or global routes it to a named ELF section. `no_mangle` suppresses name mangling so the symbol is exactly as written.

### Task B5: Test

**Files:** Create `test_suites/codes/naked_test.quanta`, modify `test_suites/EXPECTED.tsv`

Test that a naked function is reachable and that `readelf` shows the symbol unmangled in the named section:

```bash
readelf -sW /tmp/naked | grep my_handler
readelf -SW /tmp/naked | grep .text.startup
```

---

## 6. Phase C — Operand-bearing `asm!`

**This is the hard phase. It touches the register allocator.**

**Split into two versions:** C1 (0.0.230) adds a minimal x86 assembler; C2 (0.0.231) adds operand/constraint machinery on top. C1 is independently testable and has no regalloc interaction.

### 6.0 Phase C1 — Minimal x86 assembler (0.0.230)

**Why required:** `asm!` currently takes a hex byte string (`"b8 2a 00 00 00"`) and the handler at `codegen.quanta:2904-2930` collects hex pairs, silently skipping everything else. Operands cannot be substituted into this form because the ModR/M byte depends on the register chosen.

**Scope — the minimum that covers kernel needs:**

| Instruction class | Examples | Why |
|---|---|---|
| mov r/m, r/m/imm | `mov rax, rdi` | universal |
| mov to/from control reg | `mov cr3, rax` | paging |
| mov to/from segment | `mov ds, ax` | GDT load |
| lgdt / lidt | `lgdt [rax]` | descriptor tables |
| rdmsr / wrmsr | | CPU config |
| invlpg | | TLB |
| iretq | | trap return |
| cli / sti / hlt | | interrupt control |
| cpuid | | feature detection |
| in / out | | port I/O |
| push / pop | | handler save/restore |
| lock-prefixed forms | `lock cmpxchg` | already builtin, but asm needs it |

**Explicitly out of scope:** full x86 encoding. Anything not in the table above can use the existing hex-byte escape hatch, which stays supported.

**Tasks:**

**C1-T1: Test — assembler correctness**
**Files:** Create `test_suites/codes/asm_asmblr_test.quanta`, modify `test_suites/EXPECTED.tsv`

Each test assembles an instruction, executes it, and asserts the observed machine state. Example:

```quanta
// `mov rax, 42` via asm must leave 42 in the result register.
fn main() {
  let ok = 0
  let v = asm!("mov rax, 42")
  if v == 42 { ok = ok + 1 }
  exit(ok)   // expect 1
}
```

**C1-T2: Reject non-hex, non-mnemonic input**
**Files:** Modify `compiler/0.0.230/src/x86/codegen.quanta:2904-2930`

Before Phase C1's assembler accepts a template, the *existing* hex path must fail closed. Add: if a character is neither a hex digit nor whitespace, and the template does not parse as a known mnemonic, emit `error: unrecognized asm template` and exit non-zero. **This alone closes Gap 5.**

**C1-T3: Encoding table**
**Files:** Create `compiler/0.0.230/src/x86/asm_x86.quanta`

Opcode table keyed by mnemonic, with operand-form dispatch (reg/reg, reg/imm, reg/mem). Reuse the existing emitter primitives (`rr`, `ri`, `mr`, `eb` — see `emitter.quanta:18-52`) rather than hand-rolling bytes.

**C1-T4: Test the rejection path**
Assert that `asm!("not an instruction")` now fails to compile with a clear message, where today it compiles silently.

**Milestone C1:** `asm!("mov rax, 42")` produces a working `mov`; `asm!("garbage")` is a compile error.

---

### 6.1 Phase C2 — Operands and constraints (0.0.231)

Target syntax (Rust-like, adapted to Quanta):

```quanta
asm!("lock cmpxchg %1, %0"
     : "+m"(*p), "+r"(expected)     // outputs
     : "r"(desired)                 // inputs
     : "memory", "cc")              // clobbers
```

Three operand kinds to support, minimum viable:

| Constraint | Meaning | x86-64 |
|---|---|---|
| `"r"` | general register, input | any free GPR |
| `"=r"` / `"+r"` | output / read-write register | any free GPR |
| `"m"` | memory operand | addressed through the vreg's spill home |
| `"i"` | immediate | constant-folded |

Clobbers: `"memory"` (barrier — already emitted for volatile), `"cc"` (flags).

**Explicitly out of scope for the first cut:** specific-register constraints (`"a"`, `"d"`), multi-alternative constraints (`"rm"`), and `%k`-style size modifiers. Add them only if a real target needs them (YAGNI).

### 6.2 Tasks

**Task C1: Parser**
**Files:** Modify `compiler/0.0.228/src/x86/method.quanta:629-650`

After the string template, accept an optional `: outputs : inputs : clobbers` sequence. Each operand is `"<constraint>" ( <expr> )`. Produce an operand descriptor array; do not resolve registers here.

**Task C2: IR representation**
**Files:** Modify `compiler/0.0.228/src/x86/globals.quanta`

Extend `IR_ASM` (op 65). Today: `iremit(IR_ASM, vr, sv, 0, 0)` — `sv` is the source offset of the template. Add parallel arrays for operand vregs and constraint codes, indexed by an operand count. Keep the existing no-operand path working unchanged (it is used by current tests).

**Task C3: Codegen — constraint → register binding**
**Files:** Modify `compiler/0.0.228/src/x86/codegen.quanta:2679-2700`

This is the real work. For each operand:
1. Call `aphys(vreg)` to get a physical register (`emitter.quanta:303`).
2. Register the constraint so `aphys` does not hand the same register to two operands.
3. Substitute the physical register name into the template at `%0`, `%1`, … before byte emission.
4. For `"m"`, substitute the vreg's spill-home address (`spill_home(vr)`, see `sdef` at `emitter.quanta:987`).
5. After emission, `sdef()` each output vreg so the allocator knows its home.

**Interaction with regalloc — the hazard:** `flush_all()` (`emitter.quanta:574`) currently spills everything before a builtin. For asm with operands this is wrong — it would clobber the registers just bound. The operand bindings must be established *after* the flush, and the flush must not spill the operand registers. This is the single most likely place for a subtle bug.

**Task C4: Template substitution**
**Files:** Create `compiler/0.0.228/src/x86/asm_template.quanta`

Walk the template string; on `%` followed by a digit, emit the operand's register name (or address form). Everything else is passed through to the existing hex-byte path.

**Note:** the existing `asm!` takes a *hex byte string* (`"b8 2a 00 00 00"`), not textual assembly — see `codegen.quanta:2679-2700`. The plan must decide: either (a) keep hex bytes and have `%N` substitute register *numbers* into a hex encoding (very awkward), or (b) accept textual mnemonics and add a minimal assembler. **(b) is almost certainly required** and is a significant addition not yet scoped. **This is the largest open question in the plan — see §9.**

**Task C5: Test**
**Files:** Create `test_suites/codes/asm_operand_test.quanta`, modify `test_suites/EXPECTED.tsv`

Must exercise: register input, register output, read-write operand, memory operand, and the memory clobber barrier. Each test asserts an observed value, not merely that it compiled.

---

## 7. Phase D — Ring-0 entry

**Depends on B (naked, section, no_mangle), B2 (packed), and C (asm + operands).**

### Tasks

**D1: `packed` structs** — **CONFIRMED REQUIRED.** Verified: Quanta structs use 8-byte stride with no sub-word packing. An x86-64 IDT gate is 16 bytes with fields at offsets 0, 2, 4, 5, 6, 8, 12 — not expressible with 8-byte stride. Add `packed` (or explicit field offsets). This is its own version (0.0.229) and blocks D.

**D2: `lgdt`/`lidt`** — expressible via operand asm once C lands, or as dedicated builtins. Prefer asm; it is the point of C.

**D3: Trap entry emitter** — a naked function that saves registers, calls a handler, and `iretq`s. Needs `naked` (B) and `iretq` encoding (C1).

**D4: Privilege transition** — ring-3 → ring-0 and back. Needs `mov cr3`/`mov ds` forms from C1.

**D5: Test** — a bare-metal binary under QEMU that installs an IDT, triggers `int3`, and prints from the handler.

**Milestone:** QEMU boots a Quanta binary that prints `"Hello from Quanta"` via UART from an interrupt handler.

---

## 8. Validation

**Per phase:**
```bash
cd /opt/tali/quanta
QC=compiler/<VER>/bin/x86/qc bash test_suites/scripts/run_tests.sh
```
All gates must stay GREEN. The suite is currently 813 tests in `EXPECTED.tsv` plus the named gates (functional, native, float-*, extern-*, security, performance, valgrind, fuzz, differential, generics, stdlib, multi-tu, verify-status, qobj).

**Per phase, additionally:**
- Self-host check: the new compiler must build itself byte-identically (`scripts/build_wip.sh` does this).
- **Final test must use the promoted `qc` binary**, not a temp build (user convention).

**Phase A specifically:** run the existing suite before and after — the width change touches a shared dispatch path and could regress `mem_load`/`mem_store`.

---

## 9. Risks and Open Questions

### Risks

| Risk | Severity | Mitigation |
|---|---|---|
| `asm!` currently takes hex bytes, not mnemonics — operands may require a real assembler | **High** | Scope §6.2 Task C4 explicitly before starting Phase C; this may be its own phase |
| Regalloc interaction: `flush_all()` clobbering bound operand registers | **High** | Bind after flush; add a targeted test for a read-write operand across a call |
| Keyword code collision (three new keywords) | Medium | Check `helpers.quanta` codes first; the `asm`=53→40 bug is precedent |
| Naked functions bypass spill machinery | Medium | Fail closed with a compile error, never silently |
| Width fix regresses `mem_load`/`mem_store` | Medium | Run full suite; A1 test has explicit non-clobber checks |
| Function size ceiling — emitter dispatch is already split (`emit_bltn`/`emit_bltn2`) | Low | Follow the existing split pattern |

### Open questions — RESOLVED by source inspection and execution

**Q1: Textual mnemonics vs hex bytes — RESOLVED. It is hex bytes, and the path is silent about wrong input.**

Verified by reading `codegen.quanta:2904-2930` and by execution:
- `asm!("b8 2a 00 00 00")` → emits the 5 bytes, returns 42. This is the supported form.
- `asm!("mov eax, 42")` → **compiles clean**, emits garbage, program misbehaves.
- `asm!("lock cmpxchg [rdi], rsi")` → **compiles clean**, traps with SIGTRAP.

The handler collects hex digit pairs and silently skips everything else. So operand substitution into this representation is not merely awkward — the input format is a raw byte encoding, and there is no assembler to extend.

**Decision required:** Phase C needs either (a) a minimal x86 assembler that turns mnemonics into bytes, or (b) operand substitution expressed as hex *number* substitution into a byte template, which is unworkable for register operands because the ModR/M byte depends on the register. **(a) is the only viable path.** A minimal assembler is therefore in scope for Phase C and is likely the larger half of that phase. It should be planned as its own version.

**Immediate fix regardless:** `asm!` must reject non-hex input with a compile error. Today it fails silently, which makes the feature unsafe to use at all.

**Q2: Are structs bit-exact / packed? — PARTIALLY RESOLVED.**

Verified by execution: a 6-field struct `IdtEntry { off_lo sel ist_type off_mid off_hi zero }` constructs and reads back correctly, and field stride is 8 bytes (`P(11,22,33)` written to `p`, `p+8`, `p+16` reads back 11, 22, 33).

**This is the problem.** An x86-64 IDT gate descriptor is 16 bytes with non-8-byte field offsets:

| Field | Bits | Byte offset |
|---|---|---|
| offset_low | 16 | 0 |
| selector | 16 | 2 |
| ist | 3 | 4 |
| type_attr | 5 | 5 |
| offset_mid | 16 | 6 |
| offset_high | 32 | 8 |
| reserved | 32 | 12 |

With 8-byte stride and no sub-word packing, this layout is **not expressible**. `packed` structs (or explicit field offsets, or a byte-array encoding) are therefore **required for Phase D** — this is a confirmed gap, not an open question.

**Q3: Is a QEMU IDT demo required? — RESOLVED: yes.**

User direction: the demo is required. Phase D's milestone stands — QEMU boots a Quanta binary that prints from an interrupt handler.

**Q4: ARM64 convergence — open, unchanged.**

This plan is x86-64 only. Same four gaps exist for ARM64, addressed by `docs/plans/arm64-backend.md`. The two should converge on a shared operand-asm design; sequence them so whichever lands first defines the interface.

---

## 10. What This Plan Does Not Claim

- It does not claim Quanta can rewrite Linux. It closes specific, verified gaps.
- It does not claim the gaps are few because the kernel is small. The kernel is 96,080 files and 1.45 GB of C.
- It does not claim operand asm is a small change. It requires a minimal assembler, which is likely the larger half.

The honest framing: **atomics, fences, and volatile already work. Five items remain open (B, B2, C1, C2, D), and the assembler-plus-operands work (C1+C2) is substantially larger than everything else combined.**

### Defects found during plan review — ✅ BOTH FIXED

1. ~~**`mem_store16`/`mem_store32` silently emit 64-bit stores** — clobbers adjacent memory.~~ ✅ **Fixed** in commit `452e5285`. Re-verified: neighbour intact, 7/7 width checks pass.
2. ~~**`asm!` silently emits garbage for non-hex input** — compiles clean, traps at runtime.~~ ✅ **Fixed** in commit `452e5285`. Re-verified: invalid hex and odd-digit counts are now compile errors.

Both were correctness bugs with silent failure modes. They became Phases A and A2 and are now closed.

---

## 11. Remaining Work Summary

| Phase | Work | Version | Blocks | Effort |
|---|---|---|---|---|
| B | `naked fn` + `section` + `no_mangle` | 0.0.226 | D | Small — additive syntax, 3 keywords |
| B2 | `packed` structs / explicit field offsets | 0.0.227 | D | Medium — layout change, touches struct codegen |
| C1 | Minimal x86 assembler | 0.0.228 | C2, D | **Large** — new module `asm_x86.quanta` |
| C2 | Operands + constraints | 0.0.229 | D | **Large** — touches register allocator |
| D | Ring-0 entry (IDT/GDT) | 0.0.230 | — | Medium — consumes B, B2, C |

**The critical path is C1 → C2.** Everything else is either small (B, B2) or consumes what C produces (D). The assembler is the piece with no existing foundation in the compiler — `asm!` today is a hex-byte emitter with no mnemonic table.
