# 0.0.233 — WIP (Phase D: ring-0 entry, bare metal)

## What this release adds

**Kernel Phase D: a Quanta binary boots under QEMU and prints from an interrupt
handler in ring 0.** Measured serial output of
`test_suites/codes/baremetal_idt_test.quanta`:

```
Quanta ring0: IDT demo
triggering int3
Hello from Quanta            <- printed from INSIDE the #BP handler
returned from int3           <- iretq restored the interrupted context
```

The program zeroes a 256-gate IDT, installs gate 3 with a 16/16/32-bit split
handler address and `type_attr = 0x8E`, `lidts` it, executes `int3`; a `naked`
trampoline saves the caller-saved registers, calls a Quanta handler through a
fixed slot, restores them and `iretq`s. Everything above the boot stub is
Quanta — `lidt`, the handler and the UART writes included.

## The boot path: `--bare` (PVH), and why multiboot is gone

`--multiboot` (the 12-byte 0x1BADB002 header) never worked and has been
**removed**: QEMU's `-kernel` multiboot loader refuses a 64-bit image —

```
qemu-system-x86_64: Cannot load x86-64 image, give a 32bit one.
```

`--bare` uses the PVH path QEMU does support for ELF64: a `PT_NOTE` carrying the
Xen `XEN_ELFNOTE_PHYS32_ENTRY` note (type 18) whose descriptor is a 32-bit
physical entry. QEMU loads the ELF64 normally (segments at their real paddr),
enters that address in 32-bit protected mode with paging off; the stub builds
page tables, enables PAE + long mode, and jumps to the 64-bit entry the compiler
emits immediately after it (`e_entry` shifts past the prefix).

`--bare` also skips the mmap'd stack relocation (no syscalls in ring 0), uses a
fixed stack (top `0x2FF000`), and ends `_start` with a hlt loop instead of
`exit(2)`.

## The 32-bit stub (the only non-Quanta bytes in the image)

* source: `scripts/boot/boot32.S` (gas, 208 bytes)
* generator: `scripts/boot/gen_boot32.py` → `src/x86/boot32_bytes.quanta`
  (one line per instruction, with the assembler's own disassembly as comment)
* verifier: `scripts/boot/verify_boot32.py <bare-elf> <verdir>` — re-derives the
  prefix from a built image, validates the note, and compares the stub bytes and
  instruction stream against a fresh assembly of the `.S`

Layout: `[note 20][pad 4][stub]` at `ht = 64 + 56*5 = 344`, so
`STUB_BASE = 0x400170` (16-byte aligned: the section must not need linker
padding) and the 64-bit entry is `0x400240`. The compiler asserts this layout
and fails closed on drift.

## Defects found and fixed here

1. **`patch_globals()` hardcoded the code base** (`BASE + 288 + gp + 4`, 288 =
   `ht` for the 4-phdr layout). In `--bare` (`ht` = 344) every RIP-relative
   global access landed **56 bytes late** — the startup stub's argc/environ
   stores overwrote a string literal and the banner printed shifted garbage.
   Fixed by `code_vbase()` (288/344/400 by layout) in `globals.quanta`, now used
   by the global-patch path, `g_code_end` and the try/catch `catch_ip` patch.
2. **The fixed BSS base (`GDATA = 0x42200000`, ~1.03 GiB) is outside a 1 GiB
   identity map and beyond a 256 MiB guest** — the first global store took a
   `#PF` (`CR2 = 0x42200168`, error 0x2) and the guest triple-faulted. The stub
   now identity-maps the low 4 GiB with 1 GiB pages; a bare guest needs
   **≥ 1.06 GiB of RAM** until `GDATA` becomes relocatable (open follow-up).
3. **`fnptr()` was unusable in ring 0** (its tuple path `mmap`s). Under `--bare`
   it now yields the raw code address — the same PIC lea object mode emits —
   which is what IDT/ISR tables need.
4. **`asm!` hex has no operand checking**: `BA imm16` desynced the stream
   (`BA` is `mov r32, imm32` in 64-bit mode), so the exit-port write never
   reached QEMU's `isa-debug-exit` and the harness hung until timeout. Use
   `asm!` with operands where possible.

## Test coverage

* gate count 817 → **819** (`argconv_test` pins the argument convention bare code
  depends on — args arrive in RDI; `strlayout_test` pins the string layout:
  `[len:8][payload at s+8]`).
* new **`bare-metal` stage**: compiles both demos with `--bare`, runs them under
  QEMU, checks the serial stream, that QEMU exits via `isa-debug-exit`, and that
  the shipped PVH prefix matches `boot32.S`. The guests exit in ~0.3 s, not by
  timeout.

## Still open

* **D4 ring 3 → ring 0 and back**: needs a TSS descriptor in the stub's GDT, a
  TSS with a valid `rsp0`, `ltr`, a DPL-3 gate, and an `iretq` to CPL 3.
* **Relocatable `GDATA`** to drop the 1.06 GiB RAM requirement.
* **ARM64 convergence** (`docs/plans/arm64-backend.md`), unchanged.

---

# 0.0.224 — WIP (stale: this file has been a verbatim copy in every version
# directory since 0.0.229; the notes above are the current release's)

## What this release fixes

The four red trait tests (`trait_min`, `trait_only`, `trait_test`, `trait_test2`)
had ONE root cause, not four. They all failed at the same line with the same
diagnostic:

    line 14: error: call to undeclared function: radius

### Root cause

`rewrite_struct_literals()` (`compiler/0.0.224/src/x86/funcscan.quanta`) rewrites
`Name { f: v }` into `Name(v)` in the token stream, so the parser -- which only
understands a constructor *call* -- never meets the new syntax.

It must skip DECLARATION positions. The guard that did this required the
preceding token to be `TT_ID`:

    if p>=1 && tokt(p-1)==TT_ID {

and one of its cases was meant to skip the brace of `impl Trait for Struct {`:

    // for (impl Trait for Struct)
    if pl==3 && ...=='f'&&=='o'&&=='r' { prev_ok = 0 }

But `for` lexes as a **TT_KEY**, not a TT_ID. The guard was therefore false at
every impl header, the `for` case was unreachable, and the impl header's `{` was
rewritten to `(`.

Downstream, `scanimpls()` looked for the impl body brace starting after
`for <Struct>`, skipped the already-converted `(`, and landed on the METHOD's
body brace instead. `bp+1` was then `return`, not `fn`, so the method was never
recognised:

    MATCH ti=1 si=1 bp=30
    LOOP bp= 30 bp_t=5 bp_v=123        <- '{' of the method body, not the impl
    CP=31 t=6 v=120 kw=16              <- 'return'; kw!=1 so not the `fn` branch

With no method recognised, `imethods` stayed empty and the intended receiver
tag never executed:

    w64(fn_partype + (fi*200 + 0)*8, si)

so the `self` parameter had no struct type. `self.radius` then parsed as a call
to a global named `radius`, which is the reported error.

The same defect broke non-trait inherent impls too -- `impl C { fn d(self)
-> int { return self.r } }` failed identically. Trait dispatch was never the
problem; `self` was simply untyped.

### Fix

One line in `funcscan.quanta`:

    - if p>=1 && tokt(p-1)==TT_ID {
    + if p>=1 && (tokt(p-1)==TT_ID || tokt(p-1)==TT_KEY) {

`self` typing, `imethods`, and point-of-use trait dispatch needed no change: they
were correct and had simply never been reached.

## Measured result

    compiler/0.0.224/bin/x86/qc
    size=2978568
    md5=d0aaa549c11361d27f7c9b91ffdc7dff

    official gate:  813/813 pass, 0 fail   (was 813/817)
    every stage GREEN, including `functional` and `qobj`
    self-host:      gen0 == gen1 == gen2 == the released binary (fixed point)

All four trait tests compile AND return the correct value (exit 10).

## Baseline

`0.0.224` was opened as a copy of `0.0.223`, which is now the frozen baseline —
one behind stable. Measured before the copy:

    compiler/0.0.223/src rebuilt -> md5=ff78dcbbb0cbfb94a1127c7813595f83
    i.e. the frozen baseline reproduces its own committed binary BIT-FOR-BIT.

`0.0.223/src` is frozen and never modified after promotion. `0.0.222`
(`md5=650f03c6d6ce13bb6f575b5056e07d3d`) is one behind the baseline and is kept
only because it also reproduces bit-for-bit.

Exactly one source file differs from the baseline: `src/x86/funcscan.quanta`.

---

## Inherited record (from 0.0.223)

Promoted from `0.0.222` by copy. `0.0.222/src` is frozen and never modified; it
is the stable fallback. Verified before the copy:

    compiler/0.0.222/src rebuilt -> size=2974472 md5=650f03c6d6ce13bb6f575b5056e07d3d
    i.e. the frozen source reproduces its own committed binary BIT-FOR-BIT.

`0.0.223` opened clean from that baseline — no carried-over dirty edits.

The body below the "Done in 0.0.222" heading is inherited history and remains
accurate as history. Everything it says about the CURRENT tree has been
re-measured; see below.

## Current state (measured, not asserted)

    compiler/0.0.223/bin/x86/qc
    size=2978568
    md5=ff78dcbbb0cbfb94a1127c7813595f83
    source rebuilds to the same md5 (SRC and BIN in lockstep)

    official gate:  813/817 pass, 4 fail (all 4 are COMPILE failures)
    self-host:      gen0 == gen1 == gen2 == gen3  (fixed point holds)
    SELFH: 4/8      — fails only because the gate demands 0 RED and
                     `functional` is still red from the 4 trait tests below.

18 gate stages logged, every stage covered by the summary, RED only on
`functional`. GREEN: native, extern-c, extern-ld, float-oper, float-builtin,
float-return, float-operpath, generics, stdlib, multi-tu, qobj, valgrind, fuzz,
differential, verify-status, performance, security.

Note: the header this file inherited from 0.0.222 asserted three things that
were false — a `compiler/VERSION` that did not exist as described, a stale
binary md5, and "129 tests, each compiled AND run individually -> all pass".
It also claimed `dequant_diff.py` covered "all 256 elements of Q4_K/Q5_K/Q6_K";
that harness actually covers Q5_K, Q6_K, Q8_0 and F16 only (0 mismatches of 32)
and does NOT exercise Q4_K. Nothing below is claimed unless a command in this
session produced it.

## What is in THIS increment

Two files, 88 insertions. Both extend fixes already proven in earlier versions.

1. `src/x86/parse.quanta` — the nested-function skip consumed `(` and stopped at
   `)`, which made its own signature-skipping branch unreachable. The corrected
   skip consumes the nested `fn`'s name, balanced parameters, body, return type
   and optional semicolon. This removed the compiler SIGILL cluster.

2. `src/x86/helpers.quanta` — `vclr()` now also clears the four per-vreg side
   tables `vreg_struct`, `vreg_is_str`, `vreg_str_arr`, `vreg_is_big` to the
   same `-1` sentinel used by the initialisation loop in `entry.quanta`.
   This is the identical fix already shipped for `vfloat` in `e3f6af85`:
   `vclr()` resets `vreg_n` to 0, so every vreg index is immediately reusable,
   but the previous function's tags were still in those tables.
   `vreg_struct` is what `method.quanta` reads to resolve `x.field`, so a stale
   struct index made a field lookup miss and the name fall through to a call.

Gate result: 813/817, matching the measured prediction for this change set
exactly. No regression, no unexpected movement.

## Deliberately EXCLUDED from this increment

**`funcscan.quanta` — held back, not carried forward.**

The dirty tree carried an 83-line `funcscan.quanta` change with two unrelated
parts:

- `w64(imethods + slot + 8, fi)` was suspected of storing one-past-end.
  Investigated and REJECTED as a fix: the search loop `break`s with `fi` already
  at the matched index, so on a match the original line is correct. It is only
  wrong on the no-match path, which nothing reads.
- `found_f` was changed from a boolean into an index. Built and measured: an
  ordinary top-level method then returned 176 instead of 10. A regression.

Decisive finding: **`imethods` is written in two places and read nowhere.**
`grep -rn imethods *.quanta` returns two writes in `funcscan.quanta`, one
allocation in `globals.quanta`, and no consumer in the whole compiler. The
dispatch table is dead code today. Neither change is observable, and a change
no test can detect is not evidence of anything.

`compiler/0.0.223/src/x86/funcscan.quanta` is byte-identical to 0.0.222.

## What is still broken (measured)

    FAIL (compile) trait_min.quanta   rc=7
    FAIL (compile) trait_only.quanta  rc=7
    FAIL (compile) trait_test.quanta  rc=7
    FAIL (compile) trait_test2.quanta rc=7

Root cause, from direct source inspection rather than behaviour bisection:

    lexer.quanta       `impl` lexes as TT_IMPL; `self` is an ordinary identifier
    parse.quanta       no dedicated TT_IMPL branch exists anywhere
    entry.quanta:749   tokp = fn_btok(fi) + 1  — the body brace
    funcscan.quanta    fn_btok can be the signature's `)` rather than the body `{`

so an impl-contained method's body can begin parsing in the wrong place and
function identity is unreliable.

For `trait_test.quanta` / `trait_test2.quanta` this is not a parser bug at all:
they need trait-typed parameters and dynamic dispatch. CORRECTION — an earlier
note here claimed no writer of a negative trait encoding into `fn_partype`
exists anywhere in the compiler. That was WRONG and was repeated without
re-reading the source. `globals.quanta:849` writes `ptyp = 0 - (ti + 2)` and
`entry.quanta:770` consumes it into `vreg_trait`. Both ends exist.

The actual missing link is narrower: `method.quanta:1699-1707`, the
trait-tagged-receiver branch, resolves the method by NAME rather than by trait
(its own comment says "a real vtable dispatch can replace this later"), and
`imethods` — the (impl, trait-method) -> fn-index table — is written at
`funcscan.quanta:574,586` and read NOWHERE. So the dispatch data is all recorded
and then never consulted. This is why no parser work can supply it.

Plan for the fix: docs/research/trait-dispatch-increment-plan.md

## Native inference status

Loader (verified):

    dequant_diff.py  0 mismatches of 32 vs compiled ggml-quants.c
      Q6_K (block 256), Q5_K (256), Q8_0 (32), F16 (10)
    dequant_q4k      verified separately against a pure-Python oracle
    absent: Q2_K, Q3_K, IQ variants — unused by this model

`read_tensor_f64()` dtype dispatch — F32, F16, Q4_K, Q6_K (verified 2026-10-05):

    tests/test_read_formats.quanta   rc=0, 0 failures, memory-bounded run
    scripts/audit/read_formats_oracle.py   independent stdlib+mmap oracle

Every probed tensor agrees with the oracle on first-6, sum, sumsq, min AND max,
to every displayed digit:

    blk.0.ffn_gate.weight      Q4_K  sum=-1.766741 sumsq=1.957209
                                      min=-0.062004 max=0.054209
    blk.0.ffn_gate.weight      F16   sum=-1.692625 sumsq=1.958057
    blk.0.ffn_down.weight      Q6_K  sum= 0.707707 sumsq=0.975708
                                      min=-0.056152 max=0.058891
    blk.0.ffn_norm.weight      F32   sum=197.648681 sumsq=26.413435
    token_embd_norm.weight     F32   sum=4512.754822 sumsq=10095.453304

Three loader defects were fixed to get here, each found by that comparison and
each invisible to a first-values-only check:

1. `read_tensor_f64()` dispatched on `gguf_type_size()`, which returns 1 for
   BOTH F32 and F16, so neither branch was ever selected and those two dtypes
   silently loaded nothing. It now dispatches on `gguf_tensor_dtype()`.
2. The seek added `gguf_data_offset()` to `gguf_tensor_offset()`, which already
   returns an ABSOLUTE offset — double-adding 8239136 produced pure garbage.
   It now seeks to `offset` directly.
3. Q4_K/Q6_K reads must use `gguf_tensor_nbytes()`, not an inline
   `nelem*144/256`, which cannot express a partial trailing block.

`pf64()` dropped the sign of any value with |v| < 1 (fixed 0.0.224):

    It printed the sign by negating only the integer part (`printi(0 - ip)`) and
    then printing the six fraction digits unsigned. For |v| >= 1 that looks
    correct; for |v| < 1 the integer part is 0, so `0 - ip` is also 0 and the
    '-' vanished. pf64(-0.023193359375) printed "0.023193". This corrupted every
    min/max diagnostic and made every F16 weight LOOK unsigned. The sign is now
    emitted once, before the digits.

Measured lesson: three of the four "loader is wrong" conclusions in this
increment were wrong, and in each case the *oracle* was the broken side — a
shifted GGUF metadata type table, interleaved Q4_K nibbles, and a Q6_K scale
index that treated `is` as an absolute byte offset while the reference advances
the scale POINTER by 8 per 128-element pass. `dequant_q6k`'s `is = l / 16` is
correct and must not be "simplified". Always settle native-vs-oracle by
correlating against the F16 twin before changing either side.

Inference engine: still non-operational. Tokenizer, 30-layer forward pass,
short-conv cache, KV cache, logits/sampling and the generation loop are all
missing. `native_inference.quanta` lines 537-551 are comments where execution
belongs. `q4k_dot` / `q4k_matvec` emitter builtins are unsafe stubs; use
`lib/std/matmul_q4k.quanta`, which is oracle-verified.

## Working method notes

- Generated and freshly built binaries MUST run under
  `systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0`.
  `ulimit -v` and `prlimit` were both tried on this host and returned rc=1
  without taking effect — a capped-looking command is not a bounded run.
  A 4,816-byte binary once reached 50.7 GB anon-rss and OOM-killed the host.

## Done in 0.0.221 (inherited, for reference)

- `expf` in lib/std/math.quanta; three overflow/underflow defects fixed; 278 of 278
  finite audit cases within 1e-12 relative, median 3.8e-15.
- `pow` renamed `ipow` in std/math: a user function SHADOWS a same-named builtin
  in every importing scope.
- Float literals with >17 significant digits were silently wrong, ~10x per extra
  digit, because the lexer froze the mantissa while still counting fraction
  digits. Now within 2 ULP.
- 26 broken GGUF reader tests replaced by one asserting test (16/16 mutations
  detected). They all skipped a string array as `alen * 4`; the format is
  `u32 elem_type, u64 count, (u64 len, bytes)*` -- length-prefixed.
- Six float kernels in lib/std/gguf did INTEGER arithmetic on float buffers:
  matvec, softmax_arr, vec_add, vec_mul, rms_norm, swiglu all read with mem_load()
  and no f64of(). rms_norm also divided by sqrt(1+mean) rather than sqrt(mean),
  swiglu used 1/(1+2^-x), and softmax_arr computed 1+e^x, which sums to n+1.
  RFAIL reached 0 here.
- String parameters print as text for all three spellings (str/string/String).
  Three causes: `w8` where `w64` was required (nv() initialises cells to -1);
  `: string` lexes as TT_STRING, which funcscan's type-annotation guard excluded;
  and `String` missed a case-sensitive compare.
- std/math's abs/min/max no longer shadow the f64 builtins. Importing std/math
  turned `abs(-5.0) / 2.0` from 2.5 into 9223372036854.775808. Integer forms are
  iabs/imin/imax; float min/max needed adding as fmin/fmax because the untyped
  `fn min` was the only implementation in the language.
- pow honoured an integer exponent, and then six more builtins with the same
  omission: sqrt, log, sin, cos, tan, abs.
- dequant_f32() added to lib/std/gguf.quanta. 99 of the reference model's 266
  tensors are F32 -- 37% -- and it was the only dtype with no decoder. They went
  unnoticed because they are the SMALL per-layer vectors, 1/260th the size of the
  weight matrices, so a run that only ever touched the k-quants looked complete:

      token_embd_norm.weight   [2048]     x61
      ...                      [3, 2048]  x22
      ...                      [64]       x16

  F32 has no quantisation, so the decoder is a widening over the existing
  (already exact) f32_to_f64. Decoder coverage is now 266 of 266.

## OPEN DEFECTS

### No decoder for F16, Q5_K, Q8_0 or any IQ type

`std/gguf.quanta` now covers every dtype THIS model uses (F32, Q4_K, Q6_K =
266/266), but the other families are absent. `gguf_type_size` returns a byte size
for types 0..13 plus 30, and a caller can therefore size a buffer it has no way to
decode -- the same shape of defect F32 had, one step further out:

    Q8_0  (type 8)   32 values / 34 B     -- the standard KV-cache quant
    Q5_K  (type 13) 256 values / 176 B
    F16   (type 1)    1 value  / 2 B
    IQ2_XXS .. IQ4_XS (16..23)

Nothing in the reference model needs them, so this is not blocking today. It is
recorded because `gguf_type_size` succeeding where no decoder exists is the exact
trap that hid the F32 gap: a caller allocates correctly and then reads garbage.

### RESOLVED: a nested index / a non-name base CRASHED THE COMPILER

    print(m[1][0])            SIGILL while COMPILING
    print(len(m[1][0]))       SIGILL while COMPILING
    print([70,80][0])         SIGILL while COMPILING
    print(g()[0])             SIGILL while COMPILING
    print(len([1,2,3][1:3]))  SIGILL while COMPILING

Two independent defects, both in parse_primary's postfix handling.

1. The `[` arm resolved its base with vfind(nm,nl)/gfind(nm,nl) and RETURNED
   after the first `[...]`. So a base that is not a name -- an array literal, a
   call result, a parenthesised expression -- had nothing to resolve, and
   `n[1][0]` left the `[0]` in the token stream.

2. That leftover token was harmless in a `let` and fatal as a CALL argument.
   parse_call_impl:101 saw `[` where it expected `,` or `)`, and mpnct() is
   lenient -- parse.quanta:13 returns 0 on a mismatch and every caller ignores the
   result. The argument count silently over-counted, the permutation at 139-146
   read an arg_tgt slot that was never written, and that garbage index reached
   `ir + idx*IRS + field`. The multiply overflowed and the COMPILER's own
   checked-arithmetic trap (jno/ud2, confirmed at 0x42fd9a) fired.

The worst part is the failure SHAPE: a caller-side mistake reported as an
illegal instruction inside the compiler, with no diagnostic and no line number.
The traceback points at the compiler, not at the code that caused it.

Fix: `parse_index_on(base_vr)` consumes one `[...]` against an already-produced
VREG and returns the result VREG; `parse_postfix_expr(vr)` loops it. The named-base
path resolves nm/nl once and then chains; the non-name primaries -- array literal,
call result, parenthesised expression, numeric literal -- return through
parse_postfix_expr.

`n[1][0]` on a FLAT array is not valid Quanta and is not tested: n[1] is the
integer 80, and indexing an integer reads a header off whatever 80 points at.
tests/test_postfix_index.quanta uses real nested arrays. That mis-designed probe
was mine, and it is worth naming -- `n[1][0]` looks like the obvious test and it
is not one.

tests/test_postfix_index.quanta: 38 checks over nested arrays, three-deep,
runtime indices at every level, literal/call/paren bases, string arrays, slicing a
non-name base, the named forms that had to keep working, and a nested index passed
straight to a user function with other arguments. Verified to crash the pre-fix
compiler and pass on this one.

### RESOLVED: a slice did not clamp its HIGH bound

    let b = [10, 20, 30, 40, 50]
    b[0:99]        SIGILL
    b[3:99]        SIGILL
    [1,2,3][0:99]  SIGILL
    g()[0:99]      SIGILL

Every in-range slice was already correct; only `hi > len` trapped. method.quanta's
lowering clamped ONE side:

    nraw = hi - lo
    neg  = nraw < 0
    n    = neg ? 0 : nraw        // clamps nraw < 0 only

`hi` was never bounded by the length, so the copy loop ran n iterations reading
base[lo+idx], the IR_IDX bounds trap fired once lo+idx reached len, and the whole
program died -- for what is an entirely ordinary slice expression. Python, Rust
and Go all clamp the high bound.

Fixed to `lo = max(lo,0); hi = min(hi,len); n = max(0, hi-lo)`.

The clamp is BRANCHLESS on purpose:

    oc  = hi < len
    om  = 1 - oc
    hic = hi*oc + len*om          // min(hi, len)

The obvious branch form

    BR(oc, l_hi); MOV(hic, len); LABEL(l_hi)

compiled and was WRONG: it broke even the slices that used to work
(`b[3:3]` returned 2 instead of 0, `b[4:2]` returned 1 instead of 0). A value
defined before a branch and used after it does not survive here -- codegen's
dead-definition pass rewrites a def whose result is not read back along the same
path, so `hic` came back as garbage. Empirically confirmed: the same code with a
branch is wrong, the same code branchless is right.

That is a second-order trap worth remembering: a value live ACROSS an IR_BR or
IR_LABEL in parser-emitted IR is not reliably live. Prefer arithmetic selection
in generated IR.

### CORRECTION: array indexing IS bounds-checked


## Verified pitfalls for this tree

- `mem_load` always reads 8 bytes. Reading a u32 field into a 4-byte buffer
  overreads the allocation; read 8 wide and mask.
- `mem_store` takes a VALUE, not a bit pattern. `mem_store(p, 4607182418800017408)`
  stores the float 4.6e18, and a round-trip returns that same wrong value, so a
  store/load test passes while asserting nothing.
- An UNTYPED `fn` returning `f64of(...)` returns the integer bit pattern. Needs an
  explicit `-> f64`.
- `mem_alloc` inside a loop body is unsafe -- the next iteration clobbers it.
  Allocate up front, as lib/std/gguf.quanta does.
- `lseek` returns the resulting ABSOLUTE offset, not a 0-on-success status.
- A user `fn` shadows a same-named builtin in every importing scope.
- `print`/`println` and indexing of a string PARAMETER give a pointer / garbage;
  locals and array literals are fine. Pass flat integer arrays instead.
- x87/SSE byte encodings: the direction of `0F 7E` vs `0F 6E` is fixed by the
  opcode, not by the ModRM fields. `fld_x` is the load, `fst_x` the store.
  `66 48 0F 7E` is movq; `66 0F 7E` is movd and truncates.
- `is_float_vr` must be read BEFORE `flush_all()`, which spills live vregs and
  makes the float tag unreliable.

## Rules for anything added here

- Assert. A test that prints an expectation next to a result is not a test.
  test_full_final printed `Matvec: 0, 0 (expect 17, 39)` and then `SUCCESS`.
- Compare on raw bits or a ULP tolerance, never on formatted output. Print rounds,
  so `1/3` and `0.3333333333` are indistinguishable.
- Take every expected value from the real data, not from a plausible guess. Five
  values in the GGUF tests were wrong that way, and the file was right each time.
- Prove a branch fires before debugging what it writes: set a value that is
  consumed downstream and produces a loud failure.
- Verify a new test fails on the pre-fix binary. Otherwise it is a false pass.

## Done in 0.0.222

### Postfix index chaining (`1f21f927` and earlier in this tree)

- `parse_index_on`/`parse_postfix_expr` chain trailing `[...]`, so `n[1][0]`,
  three-level indexing, string-array elements and nested expressions used as
  call arguments all parse. Before, the second `[` was left in the token stream
  and `parse_call_impl` consumed the commas and the `)`.
- Slice high bounds clamp to the array length. `b[0:99]` on a 5-element array
  entered the copy loop with an out-of-range bound and trapped. Branchless
  arithmetic, because parser-emitted values live across IR_BR/IR_LABEL are not
  reliably preserved by codegen's dead-definition pass -- the branch version
  broke `b[3:3]` and `b[4:2]`.
- `scripts/audit/run_gguf_tests.py` reads VERSION; it had defaulted to 0.0.221
  and silently tested the previous stable after promotion.

### GGUF decoders, verified against the compiled C (`4352c9e2`)

The reference is not hand-written: `scripts/audit/dequant_oracle.py` extracts
`dequantize_row_q8_0`, `_q4_K`, `_q5_K` and `_q6_K` verbatim out of
ggml-quants.c, links them against a driver, and dumps raw f64 bit patterns.
`dequant_diff.py` runs the Quanta decoders on the same synthetic blocks and
compares. Every value is bit-exact: these decoders only widen, multiply and
subtract, so anything short of exact is a defect.

Seven library defects, all of which returned plausible floats rather than
crashing:

- `dequant_q6k` was not Q6_K at all -- a 2-byte scale at offset 0 and 3-byte
  quant groups from offset 2, which is no GGML layout. It decoded 19 of the
  reference model's 266 tensors including `token_embd.weight`.
- and, once the layout was right, it ran one pass of 128 per 256-element block
  instead of the C's two, leaving elements 128..255 as zero. Every Q6_K tensor
  was half garbage; the first eight values matched the oracle.
- `std/fs.f16_to_f64` never masked the exponent, so the sign bit leaked into it:
  every negative half was wrong by a power of two (0xC000, -2.0, came back as
  -8589934592.0). Inf was faked as 1e308 and NaN as 0.0, so `Inf - Inf` did not
  produce NaN; subnormals used the decimal literal 1e-27 where 2^-24 belongs.
  std/gguf imports std/fs, so this shadowed gguf's correct copy.
- int8 conversion subtracted 128 AND 256, so 0xF0 became -144. Every negative
  quant in every decoder was off by 128.
- Q5_K's high-bit masks are 4^n (the C does `u1 <<= 2`), not 2^n. Group 0 agrees
  either way, so 192 of 256 elements disagreed.
- the mask test `qh & u1` was implemented as `qh % u1`; modulo is 0 for every
  u1 == 1, so bit 0 was never set.
- NaN came from `Inf - Inf`, which on x87 is a NEGATIVE quiet NaN, so a positive
  input NaN came out with its sign flipped.

Three more defects were in the audit itself and are fixed in the same commit:
the C driver's Q6_K block wrote `d` at offset 192 on top of `scales[0..1]`; its
Q5_K block used Q4_K's field layout; and its F16 subnormal conversion was off by
one exponent (it now uses the host's exact `_Float16`).

`tests/test_dequant_k.quanta` asserts every element of every block -- 800 exact
comparisons -- plus a three-block Q8_0 decode, because a one-block test cannot
see the block stride. Every expected value is generated by
`scripts/audit/dequant_k_expect.py`; none is typed by hand, because hand-typed
ones were how three of them came to be wrong. Twelve negative controls confirm
each defect is caught.

### Still open

- **A `-> f64` call's result depends on what the program called before it.**
  Found while implementing fdlibm argument reduction for `sinf`. A `-> f64`
  function returns the right bits in some programs and a constant wrong value in
  others, with no difference in its own source: `reduce(0.5)` is correct only if
  `qmult` is called somewhere in the program BEFORE it, and `reduce` calls
  `qmult` itself, so an extra earlier call appears to fix it. Only `qmult`
  matters -- it is the one callee whose body holds the 2^52 magic constant and a
  pair of guarded early returns. The argument-passing ABI, untyped-float-return,
  callee call-site count, module definition order, stack depth and `mem_alloc`
  inside the callee are all ruled out by direct test; each individual step is
  correct when executed alone. Full diagnosis, the ruled-out list, and where to
  look next are in `docs/research/call-order-f64-defect.md`. A `-> f64` call to a
  USER function is a different path from the builtin path that 0d7950b6's
  `as_f64_rdi()` fixed, and nothing equivalent exists there.

  The fdlibm reduction itself is done and every step of it is verified correct
  in isolation; it is held back at /tmp/negctl/math.sin-attempt rather than
  shipped, because a transcendental that is right only in some programs is worse
  than one with a known 57-ULP worst case. Re-applying that file is the whole
  change once the defect is fixed.

- `sin` near roots: x87 gives 73/88 bit-exact with a worst case of 57 ULP.
  Common arguments are exact; relative error near a root is not. Measured
  against the host: sin(pi + 1e-9) is 19558 ULP out, sin(1e15) is 7.7e-7 relative
  out. x87's FSIN does no accurate reduction above about 2^20.
- Long decimal literals: 160/222 exact, 58 at 1 ULP, 4 at 2 ULP, none worse.
- `mem_alloc` inside a loop body is unsafe; the next iteration can clobber it.
- Raw-pointer vs Quanta-string separation is still unresolved, so `print` on a
  string PARAMETER emits text but other string paths can still emit a pointer.
- Q8_0 exists and is now exact, but the full model has not been run end to end:
  KV cache, sampling, vector store and RAG ingestion are still to build.


## 0.0.225 -- string consts and variadic print

## Loader: corrected `gguf_tensor_nbytes()` block-size table

Derived every quantised block size from the `static_assert(sizeof(block_x) == ...)`
lines in `/opt/ai/llama.cpp/ggml/src/ggml-common.h` and diffed against the loader.

Six IQ types and BF16 were wrong:

```
IQ4_NL  18 vs 110   used a 256-element block for a 32-element type
IQ3_S  110 vs  82
IQ2_S   82 vs 136   swapped with IQ4_XS
IQ4_XS 136 vs 186
IQ1_M   56 vs  54
BF16     2 vs  56   treated 2 bytes/elem as a 256-element block
```

`gguf_tensor_nbytes()` drives the read length, so a wrong value silently read
past or short of a tensor and returned plausible weights -- the same failure
mode as the Q4_K/Q6_K bugs fixed earlier. Summing the wrong table over the
real models proved it:

```
                        old sum_nbytes      new sum_nbytes     filesize
GG4-26B4-IQ4        11,093,359,736      13,581,352,056   13,597,177,568
GW38-27B-IQ4        16,777,233,024      13,894,652,544   13,905,647,712
GG4-E4B              4,912,314,536       4,961,343,656    4,977,171,584
```

Two of the three missed by >2.5 GB; every other model on the box was already
within ~15 MB. That gap is how the bug was isolated without needing a
reference dequantizer.

Also corrected the comment block above the function, which mislabelled dtype 30
as `IQ4_NL_4_4` (removed upstream); it is **BF16**. Added the six newer types
that were absent entirely: TQ1_0(34), TQ2_0(35), MXFP4(39), NVFP4(40),
Q1_0(41), Q2_0(42).

Pinned by `tests/test_nbytes_table.quanta` -- 3,496 tensors across 6 real
models, checked against the upstream (bytes, elems_per_block) pairs, plus the
invariant that the sum of all nbytes must not exceed the file size.

Verification (compiler `0.0.225`, md5 f6e7e40d735b953babebb53f16862c27):

```
test_nbytes_table  RC=0   wrong=0 across all 6 models
test_read_formats  RC=0   F32/F16/Q4_K/Q6_K oracle agreement intact
gate               rc=0   green=19 red=0
official suite     RC=0   813/813 pass, 0 fail
```

## GGML format coverage decision

Full taxonomy (43 types) recorded in
`docs/plans/lfm2-native-inference-spec.md`. Coverage directed for **everything,
including the IQ codebook and FP4 types (~26 formats)**.

The split that matters: ~17 uniform-scale types (F32/F16/BF16, Q4_0-Q8_1,
Q2_K-Q8_K, TQ1_0/TQ2_0) are self-contained dequantizers, each verifiable
against a real tensor. The ~11 IQ + FP4 types are **codebook lookups** -- each
index selects from a learned codebook shipped in the GGUF as its own tensor --
so they need the codebook plus a `ggml_vec_dot` variant, and cannot be written
or tested in isolation.

Q2_K and Q3_K are present in **no** model on this box, and neither `gguf` nor
`numpy` is installed, so an independent oracle for those two would have to be
built from llama.cpp itself.

## Stage 1 (post-0.0.225) -- LFM2 descriptor table

- Removed `lib/std/native_inference.quanta`: dead, unimported, and did not
  compile (`cannot resolve imported module 'std/mem'`). Its fixed 128-entry
  tensor table and placeholder tokenizer were never production facts. The
  earlier "fixed 128-entry table" blocker in `docs/NATIVE_INFERENCE.md` was a
  description of this dead file, not of the loader. The real loader at
  `lib/std/gguf.quanta:96` already allocates descriptors dynamically.
- Added `docs/plans/lfm2-native-inference-spec.md`: the reviewed design.
- Added `lib/std/lfm2_model.quanta`: descriptor-only role table. Maps
  `(layer, role)` to GGUF tensor indices. Reads NO tensor data and materializes
  NO weights (full f64 materialization is ~20.1 GB).
- Added `tests/test_lfm2_table.quanta`: verifies all 266 descriptors classify,
  the 8 attention layers are exactly [2,5,9,13,17,21,24,27], absent roles
  return -1 rather than a stale 0, and out-of-range layers are rejected.

### Three defects found and fixed while building Stage 1

1. `name_ends_with()` used a literal `"blk.N."` prefix, which can never match a
   real `"blk.12."`. Now matches role SUFFIXES only, with the length taken from
   `len(suffix)` rather than a hardcoded constant.
2. String PARAMETERS are length-prefixed: `len(s)` is correct and the body
   starts at `s+8`. Reading `s+0` returns the length byte, not `'a'`.
3. A string parameter cannot be printed -- `print(name)` emits its raw pointer
   address. A first pass passed role names as parameters and every failure line
   printed `1109395432` instead of a role name. Test helpers now take integer
   role codes.

### Measured per-layer dtype map

`ffn_down` and `attn_v` are NOT the same dtype on every layer, so a global
per-role dtype assumption is wrong (it caused 20 spurious failures):

```
ffn_down Q6_K: [0,1,2,5,8,11,14,17,20,23,26,27,28,29]   Q4_K: the other 16
attn_v   Q6_K: [2,13,24,27]                            Q4_K: [5,9,17,21]
```

A matvec kernel must dispatch on `gguf_tensor_dtype(idx)` per tensor.

### Still absent (no forward pass exists yet)

Tokenizer, embeddings, short-conv + cache, attention + RoPE + KV cache, logits,
sampling, stopping, generation loop.

## 0.0.225 -- string consts and variadic print

Two compiler defects fixed, both silent-data-corruption class.

### String constants

The const table stored 24-byte untyped entries and the const evaluator was
numeric-only, so a string `const` evaluated to the integer 0:

    const S = "/abc/def"    print(S)      -> 0
    len(S)                                -> SIGSEGV

Passing such a const to any function that reads its bytes segfaulted, which is
what crashed gguf_load() when handed a const path.

The table is now 32-byte typed entries:

    +0   name offset/pointer
    +8   name length
    +16  value
    +24  kind  (0 = integer, 1 = string)

Both writers (scan-time in features.quanta, parse-time in parse.quanta) were
updated, plus a third enum-variant writer in globals.quanta that still used the
old 24-byte stride. `cfind()` now returns an INDEX rather than a value, so every
consumer dereferences through cval()/ckind() with a negative-index guard;
missed consumers were silently using the index as the value.

The actual defect was in the CONSUMER, not the table. method.quanta's
general-identifier path emitted IR_CONST unconditionally, putting a raw source
offset into a vreg where a char* was required. String consts now emit IR_STR
and set vreg_is_str.

Verified: const path prints in full, integer consts unaffected, len() on a
string const returns the correct length, top-level and function-local both.

### Variadic print

The emitter consumed only argument 0; all others were dropped with no
diagnostic:

    print("a=", 12, "
")   ->  "a="

A 2-arg call was always treated as the print(buf,len) alias, so
print("a=", 12) wrote 12 bytes of the literal.

Fixed by lowering at PARSE time, not in the emitter. The emitter only sees
already-lowered IR, and a literal argument has no live vreg to spill, so reading
a spill home returns unrelated stack bytes (an emitter-side attempt printed
"n=201122", the bytes of the caller's own format string, then SIGSEGV). Each
argument is copied into its own fresh vreg and emitted as an ordinary
single-argument print, reusing the existing working builtin.

Two arguments are NOT treated as variadic: test_suites/codes/prints_family.quanta
documents print(buf, len) as a defined form and existing callers rely on it.
Disambiguating by argument type instead broke print("ABCDEFGH", 8). argc decides:
2 == alias, 3+ == variadic.

Verified: argc 3..7 print every argument correctly, mixed string/int sequences,
expressions as arguments, printi/printsp/println unchanged, prints_family
output byte-identical to its documented golden output.

### Gates

    gate:  gate_rc=0 green=19 red=0
    suite: 813/813 pass, 0 fail

Binary: compiler/0.0.225/bin/x86/qc md5=f6e7e40d735b953babebb53f16862c27
Built from source with compiler/0.0.224/bin/x86/qc as the seed.

## Q5_K and Q8_0 wired and verified against upstream C

### Changes

`read_tensor_f64()` now dispatches dtype 13 (Q5_K) and dtype 8 (Q8_0) through
`gguf_tensor_nbytes()`, absolute `lseek()`, raw allocate/read, native
dequantization and `mem_free()`. Removed a duplicated pair of `q5_scale()` /
`q5_min()` definitions that existed twice, byte-identical.

Added `gguf_dtype_supported(dtype)` and `gguf_tensor_supported(idx)`. This is
not a convenience wrapper: `read_tensor_f64()` signals failure by returning 0,
but the buffer is sized by the caller from `gguf_tensor_nelements()`, so an
unimplemented dtype still demanded the FULL allocation before the refusal was
discovered. `token_embd.weight` at 1,271,398,400 elements is 10.2 GB of f64 for
a tensor that cannot be read at all, which exceeds the 6 GB inference scope
before any error surfaces. Callers must be able to ask first.

### Why a compiled oracle was added

Two independent Python transcriptions of `dequantize_row_q5_K` disagreed on
sum and sumsq while AGREEING on min and max, so neither could be trusted. All
three candidate values (two Python, one native) were plausible; only one was
right. `scripts/audit/c_oracle.c` resolves this by calling the real
`dequantize_row_q5_K` / `dequantize_row_q8_0` and `ggml_fp16_to_fp32` out of
the prebuilt `libggml-base.so`.

It is TEST SCAFFOLDING ONLY. It is not in `lib/`, the native inference path
never calls it, and Quanta does not link C.

Two traps hit while building it, both of which the native code does NOT have:

1. `ldexpf(1.0f, mant) * 2^-149` is wrong for subnormal halves. The ldexpf
   argument is the UNSHIFTED mantissa (0..1023), so a subnormal half asks for
   2^914, which overflows to inf, and inf * tiny stays inf. Both `d` and `dmin`
   of the Q5_K blocks here are subnormal (0x0392, 0x1375), so every weight came
   out inf. Fixed by calling `ggml_fp16_to_fp32` instead of hand-rolling.
2. Computing the data section offset in a single pass -- stopping at the
   matching tensor name -- lands short by the size of all remaining tensor-info
   records. That reads garbage which still looks like plausible weights. The
   walk must cover every record.

The Q5_K `ql` pointer DOES advance 32 bytes per group while `qh` does not; only
the u1/u2 masks move. Holding `ql` fixed as well reproduces a plausible wrong
sum, which is exactly what both Python transcriptions did.

### Verification

`tests/test_read_formats.quanta` extended with a `check_oracle()` that asserts
sum, sumsq, min and max rather than merely that values are finite, so a
dequantizer returning the right SHAPE of wrong numbers cannot pass.

Real fixture `QUANTA-GW38-27B-IQ4.gguf` (866 tensors) is used because no LFM2
tensor is Q5_K or Q8_0. Its dtype histogram is F32 408, IQ4_XS 293, IQ3_S 75,
Q6_K 59, Q5_K 21, Q8_0 5, Q4_K 5 -- one file, five dtypes, four wired, which
also proves dispatch is per-tensor dtype and not per-model.

Native vs compiled upstream, all four fields within 1e-6:

| tensor | dtype | sum | sumsq | min | max |
|---|---|---|---|---|---|
| blk.3.attn_k.weight | Q5_K | 0.615401 | 0.932176 | -0.068733 | 0.079718 |
| blk.11.attn_k.weight | Q5_K | -0.303321 | 0.725723 | -0.056386 | 0.066370 |
| blk.1.ssm_beta.weight | Q8_0 | 0.816602 | 0.580516 | -0.064434 | 0.044934 |
| blk.16.ssm_beta.weight | Q8_0 | -1.099899 | 0.334722 | -0.076667 | 0.061769 |

IQ3_S and IQ4_XS are confirmed refused by `gguf_tensor_supported()` before
any allocation, and Q5_K in the same file still reads 5242880 elements, so the
new guard is not over-broad.

Results:
- `tests/test_read_formats.quanta` -- all pass
- `tests/test_nbytes_table.quanta` -- all pass, 0 mismatches
- gate -- green=19 red=0
- official suite -- 813/813 pass, 0 fail

### Still missing

Q2_K, Q3_K, Q4_0, Q4_1, Q5_0, Q5_1, Q8_1, Q8_K, BF16, TQ1_0, TQ2_0, MXFP4,
NVFP4, Q1_0, Q2_0 and the remaining IQ types have no native dequantizer.
`scripts/audit/c_oracle.c` is the reference to extend as each is added.

## 0.0.225 — Q4_0 + BF16, and two loader-path defects found by them

Q4_0 (dtype 2) and BF16 (dtype 30) are wired into `lib/std/gguf.quanta`
(support table + dispatch + `dequant_q4_0` / `dequant_bf16`) and verified
against the compiled C oracle in `scripts/audit/c_oracle.c`:

    Q4_0  QUANTA-GG4-30B-Q4KXL.gguf  blk.5.attn_k.weight      n=11010048
          sum   = -781.592564  sumsq = 1960.441500
          min   =   -0.135376  max   =   0.134583

    BF16  QUANTA-GG4-E4B-Q4_K_M.gguf  per_layer_model_proj.weight  n=27525120
          sum   =   -0.511763  sumsq =    6.810468
          min   =   -0.121582  max   =    0.100586

### FIX 1 — the `f64of` leak (one 72-byte mmap per call)

`lib/std/math.quanta:285` re-declared `f64of` as a USER function:

    fn f64of(bits: i64) -> f64 {
        let b = mem_alloc(8)
        mem_store(b, bits)
        return f64_load(b)
    }

A user function shadows a same-named builtin in EVERY importing scope, so any
file importing `std/math` (directly, or transitively via `std/gguf`) turned every
`f64of()` into that call: `mem_alloc(8)` with no matching `mem_free`. One 72-byte
mmap per call, ~4KB effective RSS per call. The 11,010,048-element Q4_0 reduction
grew to ~16GB RSS and was OOM-killed (RC=137) under `MemoryMax=6G`.

The builtin is inlined by `emit_bltn` (features.quanta:598) and allocates nothing.
Measured on a 200k-iteration loop: 200,001 mmaps with the import, 1 without. The
shadow was numerically correct, so nothing failed loudly — it only leaked.

Removed from BOTH `lib/std/math.quanta` and `lib/std/transformer.quanta:12`
(identical copy). Verified the builtin gives identical results:
`f64of(4612811918334230528)` = 2.5, `f64of(f64bits(2.5))*2.0` = 5.0, sum of five
`f64of(f64bits(1.0))` = 5.0.

### FIX 2 — BF16 endianness and header offset

`dequant_bf16` went through three wrong forms before the oracle agreed. Each was
wrong in a way that returned plausible-looking numbers or exact zeros:

1. `f32_to_f64(raw + i*2)` reads 4 bytes, so the NEXT element's two bytes landed
   in the mantissa's low half. Sum off by 0.033, every min/max wrong.
2. Shifting into an f64 directly (`f64of(bits << 48)`) is not a widening: an f64
   pattern of `bf16<<48` has bias 1023 where fp32 has 127, so it is off by a
   factor of 2^896. 16561 became 4352.0 instead of 1.0. The exponent must be
   REBASED, which is exactly what `f32_to_f64` does.
3. Placing the bf16 bytes at scratch offsets +0/+1 built the pattern `0x00003f80`
   — a subnormal ~1.7e-38, so every element printed 0.000000. Little-endian fp32
   puts sign+exponent in b3 and the top mantissa byte in b2, so `bf16<<16` lands
   in offsets +2/+3.

Also note `mem_load8`/`mem_store8` are RAW (no header skip) while `mem_load`/
`mem_store` skip the 8-byte alloc header — measured directly, not assumed. The
working dequantizers are unaffected because they go through `f16_to_f64`/`i8_at`.

Verified in isolation first: bf16 [1.0, -2.0, 0.5, 3.0] round-trips exactly.

### Verification

    tests/test_read_formats      all pass (RC=0, MemoryMax=6G)
    tests/test_nbytes_table      all pass (6 models, 0 wrong)
    scripts/run_gate.sh          green=19 red=0
    test_suites/scripts/run_tests.sh   813/813 pass, 0 fail

Still zero local fixtures, so still unverified natively: Q2_K, Q3_K, Q4_1, Q5_0,
Q5_1, Q8_1, Q8_K. Upstream exports dequantizers for all of those except Q8_1.

## 0.0.225 — uniform-scale GGUF formats: Q2_K, Q3_K, Q4_1, Q5_0, Q5_1, Q8_K

The remaining legacy row-storage formats are now natively supported. Supported
dtype IDs in `lib/std/gguf.quanta` are now:

    0 F32   1 F16   2 Q4_0   3 Q4_1   6 Q5_0   7 Q5_1   8 Q8_0
   10 Q2_K 11 Q3_K 12 Q4_K 13 Q5_K 14 Q6_K 15 Q8_K  30 BF16

**Q8_1 (9) is deliberately still unsupported and must stay that way at the
dequantizer level.** It is not a row-storage format: upstream exports no
`dequantize_row_q8_1` because its `qs[]` bytes have no per-element meaning on
their own. They are consumed as int8 multipliers inside `vec_dot`, paired with a
matching weight block. Supporting Q8_1 means writing that paired matvec kernel,
not adding a dequant function. An earlier hand-written `deq_q8_1` invented
semantics and is discredited.

### Verification boundary

None of these six formats appears in any local GGUF, so they cannot be verified
against a real model. They are verified against committed block fixtures:

- `tests/fixtures/blocks_<fmt>.bin` — raw quantized blocks, produced ONCE by
  `scripts/audit/gen_fixtures.py` calling upstream `quantize_row_*_ref` and
  `dequantize_row_*` out of `/opt/ai/llama.cpp/bin/libggml-base.so`.
- The expected reductions are baked into `tests/test_read_formats.quanta` as
  literals. The test never invokes the generator or the shared library.
- Reading the block, dequantizing it, and computing sum/sumsq/min/max all happen
  in Quanta. Only the one-time quantization is foreign — a native Quanta
  quantizer would share any layout or arithmetic mistake with the native
  dequantizer and would happily agree with itself.

Expected values are the ROUND-TRIPPED ones, not the original f32 input. A 2-bit
quantizer discards most of its input, so comparing against the input would demand
an exact dequantizer for a format defined by being inexact.

### Defects found and fixed while bringing these up

1. **`read_block_f64()` added.** `read_tensor_f64()` dispatched off a GGUF file
   on disk. Fixture tests (and any future direct kernel caller) have raw bytes
   and no file, so the dispatch table is now factored out and shared. A dtype can
   no longer be supported in one entry point and missing in the other.

2. **Q2_K field order.** `scales[16]` is at block offset **0**, `qs[64]` at 16,
   `d` at 80, `dmin` at 82. Reading `d` at +64 returns a garbage half
   (`d = -0.000195` instead of ~0.0018) and inflates every element by 4e5. The
   scales come FIRST in `block_q2_K`, unlike most other K formats.

3. **Q2_K/Q3_K pass offset.** The output index must advance by 128 per
   128-element pass. Without `pass * 128` every pass overwrote pass 0, which
   looks like a plausible tensor rather than an error.

4. **Q3_K hmask polarity inverted.** Upstream is
   `low2 - ((hm & m) ? 0 : 4)`: the bit being SET means the high bit was NOT
   consumed, so subtract 0. Written as `(hi << 2)` it compiles, runs, and yields
   values wrong by exactly the 4-offset — the failure mode is silently plausible
   output, not a crash. The parser also rejects `!=` inside that expression form,
   so the correction is an explicit `sub` branch.

5. **Q3_K SWAR mask constants were mistyped.** `km1` was written as `75796967`,
   which is `0x48491e7` — not `0x03030303` (`50529027`). This is the single
   worst defect in the batch: a garbage mask still compiles and still produces
   plausible-looking scale bytes. Worth noting that the initial suspicion landed
   on the compiler's `&` operator, and an exhaustive runtime-operand sweep of
   `&` came back clean — the constant, not the codegen, was wrong. Both masks are
   now decimal literals with a comment giving the hex.

6. **Q8_K int8 sign extension.** `mem_load8()` returns 0..255 **unsigned**
   (measured, not assumed). A bare `q - 256` maps 0..127 to -256..-129 and
   inflates every magnitude. Correct form branches on bit 7.

### Not attempted

IQ, MXFP4, NVFP4, Q1_0 and Q2_0 families. These need codebooks and
format-specific unpacking plus their own matvec paths; they are not reachable
from the uniform-scale dequantizer dispatch.

### Still open

The LFM2 forward path remains unimplemented: tokenizer/detokenizer with
`pre='lfm2'`, embedding wiring, short-convolution execution and cache,
attention with RoPE and KV cache, logits, sampling, stopping, generation. Full
f64 materialization is ~20.1 GB against a verified 6 GB scope, so bounded or
quantized in-place weight access stays mandatory.
