# 0.0.243: two defects fixed, one report not reproduced, one new finding

Status: measured on `0.0.241` (the shipping compiler, md5 `02b15543…`) and `0.0.243`
(md5 `26430066a4e04f61a687ccf6291b61d7`). Environment for every timing below:
governor `powersave`, 20 cores, ambient load 10-16, top CPU consumer `Hermes`
(Electron) at 700-750 % CPU for the whole session. Nothing here is a throughput
claim, so the load only matters for the note at the end.

This records the two defects the batched-prefill work hit (ordered item 1), the
*negative* result on one of them, and one new compiler defect found while building a
test for the other.

---

## A11 (FIXED): an integer `const` >= 2^60 crashed the COMPILER

### Minimal repro (0.0.241 golden)

```quanta
const V = 2305843009213693952          // 2^61
fn main() { print(V); return 0 }
```

```
compiler/0.0.241/bin/x86/qc V.quanta V.bin
-> Segmentation fault (core dumped), rc=139
```

No diagnostic, on a well-formed program, in **23 bytes of source**.

### Threshold, measured

| value | | |
|---|---:|---|
| 2^60 = 1152921504606846976 | ok | bei = 0, bvidx = 0 -- lands on a real entry |
| 2^60 + 1 | ok | bei = 0, bvidx = 1 |
| 1179675606577200000 | **CRASH** | bei != 0 |
| 2^61 = 2305843009213693952 | **CRASH** | |
| 2^62 = 4611686018427387904 | **CRASH** | == `f64bits(2.0)` |
| 2^60, **unused** | ok | it must be USED to be decoded |
| `let V = <2^60>` (global or local) | ok | only the const TABLE is marked |

### Root cause (read, then confirmed by the threshold)

A bare enum-variant name is registered in the const table as a **marked** value,
`bvmark() + ei*1048576 + vidx` with `bvmark() == 2^60` (`globals.quanta:636`), and the
const-use site decided "this is a marker" by **VALUE RANGE**:

```quanta
// method.quanta (0.0.241)
if cvi>=0 { cv0 = cval(cvi) }
if cv0>=0 {
    let cvr=nv()
    if cv0 >= bvmark() {                 // <-- ANY const >= 2^60 is "a variant mark"
        let packed = cv0 - bvmark()
        let bei = packed / 1048576
        let bvidx = packed - bei*1048576
        ... iremit(IR_CONST,ti,evariant_tag(bei,bvidx),0,0) ...
```

For `V = 2^61`: `bei = (2^61 - 2^60) / 2^20 = 2^40`, and `evariant_tag` is
`r64(evartab + (r64(enums + ei*96 + 24) + vidx)*40 + 16)` -- so it reads
`enums + 2^40*96`, tens of gigabytes past the table. `2^60` and `2^60+1` survive only
because `bei == 0` happens to land inside it, which is exactly why the boundary is
irregular rather than a round power of two.

### Why it matters more than one const

**This tree writes f64 BIT PATTERNS as integer constants constantly.** `f64bits(1.5)`
is `4609434218613702656`; `f64bits(2.0)` is `4611686018427387904`; the 0.0.241 WIP
quotes `2.5 -> 4612811918334230528` as the reason the FLOAT-const path had to be
moved above the `bvmark()` test. Every one of those is >= 2^60. The idiom is one
keystroke from crashing the compiler, and the crash is in the compiler, not in the
program -- so it reads as "my source is fine but qc died".

It was found by accident: `tests/f64of_mem_load_shape_test.quanta` used
`const VA = 4609434218613702656   // f64bits(1.5)` and qc segfaulted. The test itself
was innocent.

### The fix (0.0.243)

The marker is keyed on the const's **KIND**, not on its value:

* `globals.quanta` writes **kind 3** for a bare variant (was 0);
* `method.quanta` tests **`ckind(cvi)==3`** (was `cv0 >= bvmark()`).

`ckind` already existed with 0 = integer, 1 = string, 2 = float, so this adds a value
in a space nothing else used; the ambiguous range is returned to the user -- an
integer const >= 2^60 is now an integer. `bvmark()` survives as the *encoding* of the
mark (`packed = cv0 - bvmark()`), which is now unambiguous because only kind-3 entries
reach it.

**Two other const-use sites were left alone on purpose** (`method.quanta` ~1899 and
~2068): they have no `bvmark()` branch and emit `IR_CONST` with the raw mark value for
anything that is not kind 1 or 2. That is a *pre-existing* wrong-value path for a bare
variant reaching them, and it is unchanged by this fix (before: same, after: same).
Making kind 3 coherent at those sites too is a follow-up, not part of a crash fix.

### Red-first

`tests/const_large_int_test.quanta`:

```
0.0.241 golden : qc dies with SIGSEGV (rc=139) -- the file does not compile at all
0.0.243        : CONST_BIG PASS, rc=0
```

It covers: large integer consts, the f64-bit-pattern idiom round-tripped through
`f64of`, arithmetic on them (`BIG/2`, `BIG - BIG2/2`), and -- as the regression the fix
could have caused -- bare enum-variant names still resolving to the right variant
through the now-kind-3 marked const.

**Proposed as an EXPECTED.tsv row** (`const_large_int_test.quanta<TAB>0`, no model, no
skip dependency). The manifest is owned by another unit, so it is proposed here and
not added.

---

## A12 (FIXED in c77d06db; pinned here): `mm_workers = 0` was a division by zero

### The defect

`mm_workers` / `mm_embed_workers` default to 0 and `mm_set_workers(0)` is documented as
*"the serial path, so nothing changes for callers that do not opt in"*
(`lib/std/lfm2_mm.quanta:258-265`). `mm_matvec` and `mm_embed_logits` guard **before**
dividing:

    if mm_workers > 1 { if rows / mm_workers >= 1 { return mm_matvec_par(...) } }

The new `mm_matmul` and `mm_embed_logits_batch` computed

    let per = rows / mm_workers          // rcx = 0  ->  idiv %rcx  ->  SIGFPE

**before** testing `<= 1`. `tests/lfm2_op_profile.quanta` runs with `mm_workers = 0`, so
the first batched probe died at `idiv %rcx` with `rcx = 0`. The benchmark path never
saw it because the bench's serial runs pass `workers = 1`, not 0.

### Fix and red-first

Guard first, divide second, at both sites (`c77d06db`):

    if mm_workers <= 1 { return mm_matmul_ser(idx, x, rows, cols, B, y) }
    let per = rows / mm_workers
    if per < 1 { return mm_matmul_ser(idx, x, rows, cols, B, y) }

`tests/lfm2_mm_workers_zero_test.quanta` pins it. Reverting the guard so the division
runs first makes it die **exactly as documented**:

```
$ <0.0.243 qc> tests/lfm2_mm_workers_zero_test.quanta /tmp/w0_red.bin   # guard reverted
$ ( ulimit -c 0 -v 8000000; /tmp/w0_red.bin </dev/null )
=== mm_workers = 0 (documented serial) ===
Floating point exception (core dumped)                 RED_RC=136
```

with the guard in place:

```
ffn_gate(Q4_K) workers=0 rc=0 mismatch=0/43008
ffn_down(Q6_K) workers=0 rc=0 mismatch=0/8192
conv_out(Q4_K) workers=0 rc=0 mismatch=0/8192
ffn_gate(-1)   workers=0 rc=0 mismatch=0/43008
ffn_gate(pool4) workers=4 rc=0 mismatch=0/43008
embed_batch workers=0 rc=0 mismatch=0/32
TOTAL_MISMATCH=0
WORKERS0 PASS
```

It asserts more than "does not trap": the `workers=0` output is **bit-identical** to
`workers=1`, a negative worker count **clamps to 0** and takes the same path, the
pool path at 4 workers still agrees bit for bit, and `mm_embed_logits_batch` gets the
same treatment on its own sentinel (`mm_set_workers` does not touch
`mm_embed_workers`).

Model-bearing, so it is a `tests/` driver and **not** proposed as a gate row -- the
gate's 15 s / 1536 MB ceiling is below the model mapping alone.

---

## The `f64of(mem_load(...))` report: NOT REPRODUCED

`docs/research/prefill-batching.md` §3 records that

    mem_store(p, f64of(mem_load(a + t*8)) * f64of(mem_load(b + (k+t)*8)))

SIGSEGV'd at address 0 in four sites of the new batched conv code ("the second
operand's address comes out 0"), and that the workaround is one `mem_load` per `let`.

**That does not reproduce on this tree, and it did not when the sites were put back.**
Two independent attempts:

1. **1920 generated programs.** 8 index forms x 8 x 5 contexts (let-bound, stored to a
   constant destination, stored to a computed destination, accumulated in a loop,
   three loads in one expression) x 3 pointer kinds (local `mem_alloc`, module global,
   function parameter) x 2 operators (`*`, `+`), each compiled and run under a 4 GB cap:
   **0 crashes, 0 wrong values.** The first harness flagged 384 lines; every one was
   the harness comparing `P[0]` after storing to `P[i*8]` -- an artefact, and it is
   recorded because "384 flags" would otherwise read as a finding.
2. **The real thing.** All FIVE reported sites (conv gate, conv kernel, conv output,
   both residuals) were **re-inlined into `lib/std/lfm2_forward.quanta`** -- replacing
   the `let`-per-load workaround with the original single-expression form -- and run
   through `tests/lfm2_batch_layer_unit.quanta`:

       T1 L=0 ... mismatch=0/8192
       T2 L=2 ... mismatch=0/8192
       T3 L=5 ... mismatch=0/8192
       T4 L=0 workers=4 ... mismatch=0/8192
       T5 L=2 workers=4 ... mismatch=0/8192
       TOTAL_MISMATCH=0    UNIT PASS    rc=0

   The file was restored with `git checkout --` afterwards.

**Why it is safe here, mechanically.** An `IR_CALL` begins with `flush_all()`
(`codegen.quanta:2634`), which spills every register-resident vreg to its home slot
and clears the register map, so no operand of the enclosing expression is still
resident when the operands are evaluated; and `spill_home(v) = -(SPILL_BASE + (v+1)*8)`
(`emitter.quanta:316`) is **unique per vreg index**, so two live operands cannot share
a home slot. Both `mem_load` and `f64of` read the marshalled `%rdi`, which the arg
loader writes from the home slot immediately before the call.

**This is a negative result, stated as one.** It does not prove the original
observation was wrong: the reporting unit's compiler, tree and call site may have
differed in a way not preserved in the commit (the final commit was insertions-only,
so the failing text no longer exists anywhere -- a filesystem-wide grep for it found
nothing). What it establishes is that on 0.0.241 and 0.0.243 the idiom is correct for
a wide class of shapes, and `tests/f64of_mem_load_shape_test.quanta` now **pins** that
so a future compiler change cannot break it silently. That file is GREEN on both
versions; it is a regression pin, not a red-first test, and it is labelled as such in
its own header.

---

## NEW FINDING (NOT fixed): a parameter named `ref`, used, makes the compiler SIGILL

Found while writing the A12 test, whose helper had `fn mismatch(dst, ref, n)`.

```quanta
fn mismatch(dst, ref, n) {
    let i = 0
    let bad = 0
    while i < n { if mem_load(dst + i * 8) != mem_load(ref + i * 8) { bad = bad + 1 }
    i = i + 1 }
    return bad
}
fn main() { return 0 }
```

```
$ <0.0.243 qc> n1.quanta n1.bin
line 3: error: reserved type keyword used as a variable name:
Illegal instruction (core dumped)                                   rc=132
```

Measured variants:

| case | rc |
|---|---|
| `fn f(ref)` **unused** | 0 |
| `fn f(ref) { return ref + 1 }` | 7 (clean diagnostic) |
| `fn f(mut) { return mut + 1 }` | 7 (clean) |
| `let ref = 5` + `print(ref)` | 7 (clean) |
| `let u32 = 0` + use | 7 (clean) |
| the `while` + `mem_load` shape above | **132 (SIGILL)** |

Three separate problems, all in one place:

1. **The diagnostic names nothing.** `compile_error(8, pval(), plen())` passes a
   KEYWORD ID where a source offset is expected, so both the "line NNN" and the name
   are garbage (the name prints empty; the line was 3, 15 and 44 for the same
   construct in different files). The 0.0.221 note in `parse.quanta:719-727`
   acknowledges the id/offset mix-up and then prints the offset-derived line anyway.
2. **The error fires at the USE, not the DECLARATION.** An unused `ref` parameter
   compiles; the same parameter crashes when read. A binding the language accepts and
   then cannot read is the 0.0.221 defect class again, one level up -- the 0.0.221 fix
   covers `parse_let`, not the parameter list.
3. **The error path can SIGILL.** rc=132 instead of rc=7 means execution reached
   something that is not code after reporting the error (the parser continues past
   `compile_error(8, ...)` -- there is no recovery).

**Not fixed here**, deliberately: whether `ref` is a legitimate ownership marker
(`parse.quanta:715-716` has `is_ref` / `is_mut` handling) is a language-semantics
question, and validating parameter names is a change to what the language ACCEPTS, not
a crash fix. The honest state is: minimal repro recorded, threshold table measured,
root cause located to two functions, fix not attempted. The test that found it was
renamed (`ref` -> `rf`) and is unaffected.

---

## Cross-check on the timestamped claim

Every number here was taken in this session. The op-profile pair in
`docs/research/q6k-simd-dequant.md` was taken back to back; the A/B binaries differ
only by one `return` statement. The load line for each is recorded beside it.
