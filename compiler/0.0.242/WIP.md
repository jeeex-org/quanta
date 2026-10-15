# 0.0.242 — WIP · **A5: the P2 RAII auto-free detector fixed — and NOT PROMOTED (gate RED)**

## DO NOT PROMOTE

`VERSION` stays **0.0.241**. This tree is committed as a WIP with the detector
fixed and *proven*, because **enabling the auto-free breaks 26
`test_suites/EXPECTED.tsv` rows** (measured, this environment, below). The
detector fix is correct; the *ownership rule it turns on* is unsound without
escape detection. Details in §5.

```
HEAD at start         167531c2966a805176733b172e1de1d59390d200
0.0.241 golden md5    02b155430d10661b17645680b4092987   (untouched)
0.0.242 self-host      g1 ade2305af419d25f0081aafee62d51e3   (0.0.241 golden builds src)
                       g2 36c735cb6f7f8ced55926d324954b5a4   (g1 builds src)
                       g3 36c735cb6f7f8ced55926d324954b5a4   (g2 builds src == fixpoint)
```

`compiler/0.0.242/bin/x86/qc` = the fixpoint (g2==g3). The compiler **self-hosts
stably** even with the auto-free enabled (its own source is not broken by it);
what breaks is other code.

`compiler/0.0.242/src` vs `0.0.241/src` is **three files**: `parse.quanta`
(detector + `parse_ret` ordering), `codegen.quanta` (IR_FREE handler),
`emitter.quanta` (mem_free/drop). `lib/**` and `test_suites/**` are the 0.0.241
snapshot; this tree's `test_suites/EXPECTED.tsv` is the 0.0.241 copy (no new row
— see §6).

---

## 1. The detector was dead code — TWO record-read defects, not one

`docs/plans/bugs.md` A5 recorded a field-offset bug. Execution shows **three**
defects; all three had to be fixed for `vreg_owned` to be set:

**(a) RECORD INDEX.** `parse_let` emits `IR_MOV vr <- v` for *every* initialised
binding (`parse.quanta:1315`), so the record that produced the RHS is **not**
`irc-1`. Measured with an instrumented compiler on `let p = mem_alloc(8)`:

| probe | value |
|---|---|
| `irop(irc-1)` | `1` = **IR_MOV** (the binding MOV) |
| `irop(irc-2)` | `17` = **IR_CALL** |
| `irop(irc-3)` | `1` = IR_MOV (the arg record) |

The old code peeked `irc-1`, saw `IR_MOV`, and never entered `if lop==IR_CALL`.

**(b) FIELD OFFSETS.** The `IR_CALL` layout is `iremit(IR_CALL, res, a0=NAME
OFFSET, a1=nargs, a2=arg-start)` (`method.quanta:387`; accessors
`helpers.quanta:396-398`; codegen reads `nm=a0`, `arg_cnt=a1`, `arg_start=a2`).
Measured on the same probe at `irc-2`: `ira0=22` and `src+22=="mem_alloc(8)"`;
`ira1=1` (nargs); `ira2=1` (arg-start). The old code read `ira1` (arg COUNT) as
the name offset and `ira2` (arg-start IR INDEX) as the name length, so `cnl==9`
compared an IR index and `src+cnm` dereferenced a byte at the arg count.

**(c) NO LENGTH FIELD.** The record carries no name length, so the fix scans it
from the source bytes, exactly as codegen's IR_CALL handler does
(`codegen.quanta:2657-2664`).

### Proof the fix works (0.0.242 build)

```
# disassembly of the emitted free, 0.0.242 -- was 0 refs to HEAP_CTRL, now 2
346: push %rdi
347: pop  %rbx                     ; rbx = ptr
348: mov  0x42200408,%rax          ; rax = [HEAP_CTRL]  (old head)
350: mov  %rax,0x8(%rbx)           ; [ptr+8] = old head
354: mov  %rbx,0x42200408          ; [HEAP_CTRL] = ptr
```

`objdump -d` of `let p = mem_alloc(8)` in function / if / while / loop-escape
probes: `0x42200408` = 0 on the 0.0.241 golden, **2** on the 0.0.242 build;
byte pattern `48 89 1c 25` (`mov %rbx,HEAP_CTRL`) = 0 -> **1** per free site.

---

## 2. The IR_FREE handler was mis-encoded (found by disassembling the emitted free)

Fixing only the detector was **worse**: the pre-fix IR_FREE handler emitted

```
350: mov  %rbx,0x8(%rbx)     ; 48 89 5b 08  -- wrote ptr into [ptr+8]  (should be old head)
354: mov  %rbx,(%rbx)        ; 48 89 1b     -- wrote ptr into [ptr]   (should be [HEAP_CTRL])
25 08 04 20 42              ; the leftover 0x25+imm mis-decoded as `and eax,0x42200408`
```

i.e. it **clobbered the block's own length header `[p]`** and **never wrote
`HEAP_CTRL`**. Correct ModRM: `48 89 43 08` (0x43, not 0x5b) and `48 89 1C 25`
(0x1c, not 0x1b) — the same idiom the compiler already uses at
`codegen.quanta:2551` (`// 48 89 43 08 = mov [rbx+8], rax`). Fixed in the
IR_FREE handler (codegen.quanta).

Demonstrated: a detector-only build (handler left as-is) turns a correct program
into corruption — `tests/raii_autofree_test.quanta` prints
`139773645234176 139773645234176 ...` (both the header and the first data qword
are the pointer) and exits 1.

---

## 3. `mem_free` / `drop` carry the SAME mis-encoding

`lib/std` uses `mem_free` in **13 files**. The builtins at
`emitter.quanta:1995-1996` (mem_free) and `2056-2057` (drop) emit the identical
wrong bytes, so `mem_free(p)` has **never** pushed to the free list either — it
has been corrupting `[p]` and `[p+8]`. Fixed to match §2. This is why `87`
corpus units show the buggy `48 89 5b 08` store disappearing. `mem_free_test`
passes rc=0 on both compilers because it never inspects the free list.

---

## 4. `parse_ret` freed owned bindings BEFORE evaluating the return expression

`parse_ret` called `owned_pop_all()` **before** `parse_expr()`
(`parse.quanta:490-491`). So `return file_open(cp + 8, flags, mode)` — the body
of `lib/std/fs`'s `open()` — emitted `IR_FREE(cp)` **before the call read
`cp+8`**, and the free writes `[cp+8] = old head`, destroying the first path
byte. Measured, minimal:

```
import std/fs
fn main() {
  let fd = open("/opt/ai/models/quanta/QUANTA-LFM2.5-2.6Bv1-Q4_K_M.gguf", 0, 0)
  if fd < 0 { print("open failed\n"); return 1 }
  let buf = mem_alloc(8); read_raw(fd, buf, 8); print(mem_load(buf)); print("\n"); return 0
}
0.0.241 golden : rc=0  "14064895815"
0.0.242 build  : rc=1  "open failed"          <- the free ran before the syscall
```

Fix: emit the scope-exit frees **after** the return expression is evaluated,
immediately before `IR_RET` (IR_FREE's `flush_all()` spills the return value to
its home first, so the frees' register use does not destroy it). This defect was
invisible while IR_FREE was dead code; it is a latent ordering bug, not a
consequence of the detector change.

---

## 5. BLAST RADIUS — the reason this does NOT promote

### 5a. Codegen changes, object level (0.0.241 golden vs the 0.0.242 build)

| corpus | files | both-compile | object changed | new free-store |
|---|---|---|---|---|
| test_suites/codes | 637 |  | 187 | 187 |
| tests | 143 |  | 134 | 134 |
| benchmarks | 37 |  | 10 | 10 |
| lib/std | 165 |  | 10 | 10 |
| **total** | **983** | **821** | **341** | **340** |

`--emit-obj` byte-compare over the whole tree. **0 units fail to compile**; 341
of 821 comparable units (**42 %**) change their emitted code, 340 gain a
free-list push. (`lib/std` modules without a `main` are the 162 non-compiling
rows; the 821 are the comparable ones.)

### 5b. Runtime / gate — 26 EXPECTED rows break

`QC=<0.0.242 build> bash test_suites/scripts/run_tests.sh`:
`=== Results: 219/229 pass, 10 fail (incl. 0 compile-fail) ===`, plus extern and
stdlib stage failures:

```
functional : big_divzero_test(1->132) big_ops_test(0->132) big_test(0->132)
             config_test(42->11) linalg_test(0->139) quantum_test(0->1)
             std_spec_parser_const_test(0->1) std_spec_to_ir_const_test(0->1)
             std_test_generator_const_test(0->1) lfm2_threaded_pool_test(7->3)
extern-c   : extern_var_test (sentinel EXTERN_VAR_OK missing)
extern-ld  : extern_var_test
stdlib     : stdlib_lfm2_mm/conv/rope/attn_test(0->1) embedding_test(0->1)
             stdlib_gguf_validate/truncated_test(0->1) stdlib_safetensors_test(0->1)
             std_light_mode_test(0->139) std_proof_record_test(0->139)
             std_matvec_par_test(0->1) stdlib_loader_multi_test(0->1)
             std_qmodel_dtype_test(0->1) std_tokenizer_trait_special_test(0->1)
             stdlib_rag_search_gate_test(0->2)
```

**Not the peer unit's doing:** every functional row above was re-run with the
**0.0.241 golden compiler on the same working tree** and passes with the
expected rc (`config_test` 42, `big_test` 0, `big_ops_test` 0, `linalg_test` 0,
…). The functional failure set is a clean A/B against this change. (The tree
also contains an uncommitted peer edit to `lib/std/lfm2_forward.quanta`; the lfm2
stdlib rows are listed because they fail under the 0.0.242 build, but only the
functional set is proven an A/B.)

### 5c. Why — the ownership rule is unsound without escape detection

`lib/std/fmt.quanta:7-15` is the canonical casualty:

```
fn fmt_print_char(c: i64): i64 {
    let buf = mem_alloc(3)   // owned -> auto-freed at scope exit
    mem_store(buf, 1); mem_store8(buf + 8, c)
    prints(buf)
    free(buf)                // explicit free; `free` is not mem_free/drop -> double free
    return 1
}
```

and functions that **return** a `mem_alloc` buffer (formatted strings) hand the
caller a block the RAII pass frees. A block-scoped `mem_alloc` is owned only if
the pointer cannot escape; deciding that needs escape/alias analysis, which does
not exist. A5's own note already required it ("a pointer escaping a loop body
that owns it is then silent, data-dependent aliasing corruption").

### 5d. The memory claim does NOT hold — measured

A loop that allocates 20 000 × `mem_alloc(64)`:

| | peak RSS (VmHWM) | free-store in object |
|---|---|---|
| 0.0.241 golden | 79 840 kB | 0 |
| 0.0.242 build | 82 064 kB | 1 |

Peak RSS is **unchanged** (within noise): free-list **reuse is deferred**
(`mem_alloc` ignores the list, `emitter.quanta:1980`), so the free only pushes
onto a list nobody consumes — it reclaims nothing. A "peak RSS stops growing"
assertion cannot detect the free; it passes on both compilers. The runtime proof
used instead is the free-list-chain test, §6.

---

## 6. The red-first test — `tests/raii_autofree_test.quanta`, NOT in EXPECTED.tsv

`tests/raii_autofree_test.quanta` asserts the **free-list chain**: two sequential
block-scoped `mem_alloc` blocks must leave `[p2+8]==p1`, `[p1+8]==0`, and both
length headers `[p]==4` (so it also rejects the §2 mis-encoding).

```
0.0.241 golden   : rc=3   (blocks never freed — red, as required)
0.0.242 build    : rc=0   (5/5 runs, deterministic; ASLR-invariant: relative ptrs only)
detector-only    : rc=1   (header clobbered by the mis-encoded handler)
```

It is **deliberately NOT added to `test_suites/EXPECTED.tsv`**: the shipping
compiler is 0.0.241 and this row fails on it (rc=3), so a manifest entry would
turn the gate RED (rule #16). It lives in `tests/` with a `known-fail:` header
(the A1 precedent) and becomes an EXPECTED row when escape detection lands.

---

## 7. Not verified / open

- **Escape / alias detection is the blocker.** Until a `mem_alloc` pointer that
  escapes its scope (returned, stored, captured, passed to a retainer) is *not*
  marked owned, the auto-free cannot ship.
- The stdlib rows that fail are not bisected to a single root cause; only the
  functional set is proven a clean A/B against the golden on the same tree.
- The multi-value `return a, b, c` branch is untested by any corpus program.
- `lib/std/**` was not edited (peer-owned); the fmt/fs casualties are reported,
  not fixed.
- `docs/research/lfm2-perlayer-norm-defect.md` (the peer unit's logits-divergence
  write-up) is referenced from `docs/plans/bugs.md`, not edited.
