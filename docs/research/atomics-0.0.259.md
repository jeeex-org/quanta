# 0.0.259 — ATOMICS: the ordering model, a sound `&global`, and the optimiser barrier

This is the second lever in the `0.0.259` tree. The first is the `phase6` VA
reclaim (`docs/research/phase6-arena-reclaim-0.0.259.md`); the two are independent
and were developed concurrently in the same tree.

## 0. The one-line finding

**The atomic INSTRUCTIONS already existed and were already correct. What did not
exist was anything that made them usable, and the language was silently wrong in
two places at once.** So this version is not "add atomics": it is *make the
existing atomics sound, give them an ordering model, and give the optimiser the
barrier notion it needs to leave them alone*.

Measured on `0.0.258` (golden `e7fc8cd4`), all three of these are silent:

| # | defect | measured evidence |
|---|---|---|
| 1 | `&global` returned the address of a **temporary**, not the global's storage | `&g` gave `140450126102408` then `140450126102344` (two uses, two addresses); `atomic_add(&g,1)` returned `0` on every call and left `g` at `0`; a work-stealing loop `i = atomic_add(&next,1); while i<n` **never terminated** (rc 124 under the harness cap) |
| 2 | `atomic_store()` was a plain `mov`, i.e. **RELEASE**, while every call site and comment called it `seq_cst` | the store-buffering outcome a `seq_cst` store must forbid (`r1==0 && r2==0`) is architecturally permitted by a plain store on x86-64 (TSO store buffer). objdump of the emitted code: `48 89 37` = `mov [rdi],rsi`, with no locked or fence instruction anywhere in the program |
| 3 | no pass could even ASK whether a record was an atomic access | `DCE` exempted `IR_CALL` by opcode, not by any atomic-aware property -- an accident, not a rule |

Root cause of #1, quoted from the source that shipped it
(`compiler/0.0.258/src/x86/codegen.quanta`):

```
// address-of LOCAL: lea rd, [rbp + spill_home(a0)] gives the
// stack address of the local's home slot. (Globals: the a0
// vreg is an IR_LOADG temp, so &global is not yet supported ?
// same limitation as before, but locals now work.)
```

That is the defect written down as a limitation. `atomic_add(&global, 1)` -- the
natural spelling of a work-stealing counter -- incremented a private scratch cell
nobody else read. That is the `931 of 2048 rows wrong` measurement: not a race, a
**miscompile**, and it is why `lib/std/gguf_mm.quanta` reaches its protocol cells
through *global variables holding heap pointers* (`atomic_store(pl_genp, 0)`)
rather than `&global`. Those worked, which is what made the pool function while a
stolen counter could not.

`docs/plans/language-capabilities.md` item #2 said "the language has **no
atomics**". The source says otherwise: `atomic_load/store/add/swap/cmpxchg` and
`fence/lfence/sfence/pause` have existed since `0.0.105` (`features.quanta`,
`emit_bltn2`). Both statements are about the same tree, and the doc was the one
that was wrong -- but it was wrong in the direction that hid a *measured*
miscompile. `atomic_test.quanta` and `thread_concurrent_test.quanta` were sitting
in `test_suites/codes/` referenced by **no** row, which is how a broken `&global`
survived 154 versions.

## 1. The operations, and why exactly these five

| op | returns | consumer it is justified against |
|---|---|---|
| `atomic_load(ptr [,ord])` | the value | the pool's `done[t]`/generation check and every flag a worker polls |
| `atomic_store(ptr, v [,ord])` | `v` | publishing a job (`pl_submit`), clearing a stop flag |
| `atomic_add(ptr, v [,ord])` | the **previous** value | **the work-stealing claim**: `i = atomic_add(&next,1)` -- the loader's failing pattern |
| `atomic_swap(ptr, v [,ord])` | the previous value | a spin lock / a one-shot handoff where the old value is not needed for a decision |
| `atomic_cmpxchg(ptr, exp, new [,ord])` | the previous value | **claim-if-unchanged**: a deque steal that must fail rather than duplicate when the head moved |

`add` is the minimum for the loader. `cmpxchg` is the minimum for a *sound* steal
(a failed steal must be distinguishable from a successful one, and `old == exp`
is that test on the returned value, so no second builtin is needed).
`swap` earns its place as the one RMW that is correct without a retry loop.

**Deliberately NOT added**, each with the consumer that would justify it:

* no `atomic_and`/`or`/`xor`/`sub` -- no call site in the tree or in the loader's
  plan needs them; a flag can be published with `store` and a counter with `add`.
  Adding four ops "for completeness" would be four untested names.
* no `atomic_cas` returning a **bool**. The natural spelling already exists
  (`cmpxchg` returns the old value; `== expected` is the success test) and reading
  ZF instead would be *wrong* here, because these builtins are inlined into
  arbitrary expressions whose surrounding flags are not the compiler's to read.
* no atomic float ops (no `atomic_add` on an f64). The loader accumulates into a
  per-worker private cell and combines once; a shared f64 accumulator would be a
  design error, not a missing instruction.
* no wide ops (`atomic_load128`) -- there is no consumer and `cmpxchg16b` needs a
  different register convention.

## 2. The ordering model, and what it is expressed as

```
0 relaxed   1 acquire   2 release   3 acq_rel   4 seq_cst   (the default)
```

The order is the **last argument**, and **only when the call has more arguments
than the operation's minimum arity** (`at_minargs()`, `features.quanta`). So every
existing call site keeps working and keeps its meaning:

```
atomic_add(&next, 1)        // seq_cst -- unchanged, and now true
atomic_store(pl_genp, 0)    // seq_cst -- was a plain mov, now xchg
atomic_add(nextp, 1, 0)     // relaxed
atomic_cmpxchg(nextp, e, n, 3)   // acq_rel
```

**It must be a compile-time LITERAL.** `at_ord()` resolves the argument through
its IR def chain (following the `IR_MOV` copies the parser puts in front of every
argument record -- measured, see §5) and rejects anything that does not resolve.
A runtime-valued order is a compile error that names the operation:

```
error: the atomic ordering argument must be an integer literal in 0..4
       (0 relaxed, 1 acquire, 2 release, 3 acq_rel, 4 seq_cst)
```

Failing closed is the point: an order is a property of the program text, and the
alternative -- emit the strongest form and say nothing -- is the `seq_cst` lie
this version exists to remove.

`lib/std/atomic.quanta` ships the five names as **`const`**, not `let`. That is
measured, not stylistic: the order must resolve to a literal, and a top-level
`let` cannot, because reading a global emits an `IR_LOADG` whose value is not a
compile-time literal. Written with `let` the module would have shipped five names
the compiler refuses.

### 2.1 What was deliberately left out of the model, and why

* **No `consume` order.** No mainstream implementation maps it to anything other
  than `acquire`. Shipping it would be a synonym wearing a model's name.
* **No failure-order argument on `cmpxchg`** (C++'s two-order form). The loader's
  claim-if-unchanged loop needs one order. A second order is a decision with no
  consumer today, and it can be added as its own version when one appears.
* **No ordered `fence()`.** `fence()`/`lfence()`/`sfence()` already exist
  (`0.0.108`) and are the standalone-barrier spellings. Ordering a standalone
  fence adds no capability the loader's pattern needs.
* **No acquire/release on a plain load or store beyond what the ISA gives free.**
  On x86-64 an aligned load IS at least acquire and a store IS at least release,
  so `ord 1` on a load and `ord 2` on a store select the same bytes as the
  default-stronger form. Saying this is the honest thing; pretending a `mov` has
  an order because we passed a 1 would be the same lie as #2.
* **AArch64 is not implemented.** Not for budget: **there is no AArch64 backend in
  this tree at all.** `grep -rn 'arm64\|aarch' compiler/0.0.258/src/x86/` is empty;
  `scripts/promote.sh` still mentions `--target=arm64` from the old `src`/`bin`
  layout, and nothing in `emitter.quanta`/`codegen.quanta` emits or targets arm64
  (`is_arm` has **zero** call sites). So "both backends" reduces to x86-64 for the
  same reason `atomic_load` was x86-64-only in `0.0.105`: there is one backend.
  The ldar/stlr/ldaxr-stlxr forms, and choosing between `dmb ish` and the
  acquire/release load-store forms, are what a second backend will need; none of
  it is faked here.
* **No typed atomic widths.** Everything is one aligned 64-bit word. A narrow
  atomic needs a decision about shadow `cmpxchg` loops that the loader does not
  need and that would be untested code.

## 3. Emission, x86-64

| access | relaxed / release | acquire / acq_rel / seq_cst |
|---|---|---|
| `atomic_load` | `48 8B 07` `mov rax,[rdi]` | *same* |
| `atomic_store` | `48 89 37` `mov [rdi],rsi` | `48 87 37` `xchg [rdi],rsi` |
| `atomic_add` | `F0 48 0F C1 37` `lock xadd [rdi],rsi` | *same* |
| `atomic_swap` | `48 87 37` `xchg [rdi],rsi` | *same* |
| `atomic_cmpxchg` | `F0 48 0F B1 17` `lock cmpxchg [rdi],rdx` | *same* |

Three things in that table are decisions, not accidents:

1. **The seq_cst store is `xchg`, not `mov`+`mfence`.** `xchg` with a memory
   operand is *implicitly locked*, so it is one instruction and gets the same
   total order. That is the change that makes defect #2 go away; it is also the
   only byte-level choice the order argument can make on this ISA.
2. **Every RMW is locked for every order, including `relaxed`.** x86-64 has no
   cheaper atomic read-modify-write; the emitted instruction already provides
   acq_rel, which is *stronger* than any order the argument can request. An
   argument that changes nothing must say why, in the source, next to the
   instruction -- so it does (`at_emit()`, `emitter.quanta`).
3. **A seq_cst load is a plain `mov`.** Under TSO loads are not reordered with
   older loads, so this is correct, and it is the same statement the `0.0.105`
   comment made -- the comment was right about loads and about nothing else,
   which is exactly how the store's `mov` survived review.
4. **`rax` is set from `rsi` BEFORE the `xchg`.** `xchg` swaps `rsi` and memory,
   so the stored value must be captured first; the call still returns the value it
   stored, which is what `atomic_store` documented and what `lib/std/gguf_mm`
   relies on.

## 4. The optimiser: the memory-clobber barrier, and the audit of every pass

### 4.1 The rule, and how it is expressed

An atomic access is a **memory-clobber barrier**: no pass may move, merge, delete
or reorder it, or reorder any memory access across it.

`ir_isbar(k)` (`codegen.quanta`) is the predicate, and it is **derived from the
record itself** -- an `IR_CALL` whose name is in the atomic registry -- rather
than stored in a side table. That is deliberate:

* a side table must be allocated, sized and kept in step with the IR arena, and
  this tree has already paid once for a side table sized against the wrong
  capacity (the 1.57 GB `ir_unsafe` that left the compiler 13 KB under its own
  memory ceiling, `0.0.257`). This tree shrank `ir` to 40 MB in the same version;
  a per-record table would be a second thing to get wrong for no benefit.
* a derived predicate cannot go stale and cannot be forgotten by a pass: a pass
  that never asks `ir_isbar()` is a pass with a bug, but a table a pass forgot to
  *set* silently disables its own protection.
* it is one fact: `at_isatomic()` (`features.quanta`) is asked by the front end
  (`is_bltn`), the backend (`emit_bltn2`) and the optimiser (`ir_isbar`), so the
  three cannot disagree about which call sites are atomic -- the "two divergent
  scans of one fact" defect this tree has paid for more than any other.

`bar_in_range(a,b)` is the span form.

### 4.2 The audit: for each optimisation, can it move/merge/delete an atomic?

| pass | what it does | can it touch an atomic? | what was done |
|---|---|---|---|
| `opt_func` A: constfold + algebraic identity | rewrites `IR_ADD`/`SUB`/`MUL`/`AND`/`OR`/`XOR`/cmp into `CONST`/`MOV`/`NEG` | **no** -- it only rewrites records whose opcode is an arithmetic op; an atomic is `IR_CALL` and its *name* is not an opcode it matches. `constfold()` is called only for those opcodes. | left as is |
| `opt_func` A: `x==x -> 1`, `x*0 -> 0` | same opcode set | **no** -- same reason | left as is |
| `opt_func` B: `opt_tailcall()` | detects `IR_RET` whose operand is a self-call, moves args into PARAM homes and jumps to the entry label; neutralises the call to `MOV res,res` | **could**, in principle: it rewrites a *span* of the function and jumps back to the prologue. A barrier inside the span must not be neutralised or skipped. Measured: it only fires on `IR_RET` of a self-call, and an atomic access is neither. No red-first row is constructible, so none is claimed. | guard NOT added; recorded here as audited-and-safe-for-this-pattern |
| `opt_func` D: `opt_loop_strength()` | matches a pinned 12-opcode loop (`LABEL CONST LT BR LABEL ADD MOV CONST ADD MOV JMP LABEL`) and **overwrites all eleven body records in place**, replacing the accumulator with a compile-time closed form | **could** -- this is the one pass in the tree that destroys records. It does not today: the pattern pins all twelve opcodes and an atomic is an `IR_CALL`. | **guard added**: `if bar_in_range(p, p + 12) != 0 { ok = 0 }`. It cannot fire on today's pattern (it fires the day the pattern is widened), and saying so is the honest form of the claim |
| `opt_func` C: DCE | marks live vregs, rewrites any non-live def into the no-op `MOV res,res` | **exempt by opcode today** (`op==IR_CALL` is skipped), i.e. by accident | **guard added**, explicitly: `if ir_isbar(k) != 0 { k=k+1; continue }` plus the rule written down. Cannot change today's output; exists so that a future call-folding arm cannot acquire the right to rewrite an atomic |
| `flush_all()` + `f2_live_q()` (emitter) | the block-boundary **dead-store** skip: a home-slot store whose vreg is dead at the boundary is not emitted | **no** -- it is HOME-SLOT only, so it cannot skip an access to a pointer's target, and it already returns "store it" for any vreg whose home address escaped (`vr_at`), which is exactly the `&local`-plus-atomic case | left as is; the reasoning is recorded next to the code |
| register allocation / `sdef` / `adistinct` | keeps values in registers across records | the atomic handlers run `flush_all()` first, so every live value is in its home and every read after an atomic reloads; and each atomic access is emitted in place with no reuse of a previous result | left as is |
| ordinary loads (`mem_load`, `atomic_load`) | could in principle be CSE'd with an earlier load | **no pass does**: each is its own `IR_CALL` and is re-emitted per source occurrence. Measured: a loop's three `atomic_add`s all survive (3 x `lock xadd` in the object) | left as is; `lock xadd == 3` is now a **gate row**, so the first pass that ever CSEs one turns the gate RED |

**No pass in `0.0.258` could be shown to move, merge or delete an atomic access**,
and the three `lock xadd`s in a loop surviving to the object is the measurement
that says so. Two of the guards above therefore change no output, and they are
written down anyway, because *"this pass happens to exempt `IR_CALL`"* is not a
property of an atomic access. The one guard that *could* have been red-first
(`opt_loop_strength`) is guarded and the reason it cannot fire is stated rather
than dressed up.

## 5. The capability gap that was closed, and how

### 5.1 `&global`

`codegen.quanta`'s address-of path emitted `lea rd, [rbp + spill_home(a0)]` for
everything. For a local that is correct *because a local's home slot is its
storage*. For a global it is wrong: the operand vreg is an `IR_LOADG` temporary,
so the LEA took the address of a scratch frame slot holding a copy.

**The fix records the fact once, in the parser, where the name is known.**
`parse_unary`'s `&` branch resolves the target with `gfind()` and stores its
global index (`g+1`; `0` = not a global) in the `IR_PTR_CAST` record's `a1` field,
which was unused on this path. `codegen` then emits `lea rd, [rip+disp32]` for the
global case and patches it exactly like an `IR_LOADG` (`patch_globals()` does not
branch on the mode field for the disp32, so no new patch kind was needed). The
local path is untouched.

**Why the parser, and not a backward IR scan at emit time.** Recovering the
`IR_LOADG` by scanning the IR for the operand's def is the "two divergent scans of
one fact" defect, and here it is *unsound as well*: the optimiser's dead-def pass
rewrites an unread `IR_LOADG` into `MOV res,res`, destroying the fact before
codegen could look for it. Resolve once, record it, read it back. (The
`0.0.248` f32 work learned the same lesson at the type level and wrote it into
`ft_isnew()`.)

### 5.2 What the compiler had to learn

* **A registry, asked by three consumers** (`at_isatomic`): the front end, the
  backend and the optimiser. Before this the same five names were spelled out as
  five hand-written character chains inside `is_bltn` *and* five more inside
  `emit_bltn2`.
* **A compile-time argument resolver** (`at_const_vreg`): the parser emits each
  call argument as an `IR_MOV` copy of its value, so reading the argument record
  and expecting `IR_CONST` rejects every legal literal. This was found on the
  first build of the feature, not by reasoning -- the error message named a
  literal argument as non-literal.
* **An address-of that distinguishes a name from a temporary** (§5.1).
* **An optimiser predicate for "this record is a synchronisation"** (§4).
* **A `lock`-ed store chosen by an argument** rather than one fixed instruction,
  with the argument validated before a byte is emitted (`at_ord` runs first, so a
  rejected program emits nothing for the access).

## 6. The rows, and the red-first evidence

Registered in `test_suites/EXPECTED.tsv` **in the same commit as their sources**:

| row | rc on 0.0.258 | rc on 0.0.259 | what it is |
|---|---|---|---|
| `atomic_test.quanta` | **11** | **11** | the `0.0.105` primitive test, which was in `codes/` and referenced by **no** row for 154 versions. Registered unchanged: it pins that the compatibility surface did not move |
| `atomic_addrglobal_test.quanta` | **1 (RED)** | **0** | `&global` is the global's storage address: stable across uses and frames, writes through it visible, `atomic_add(&g,1)` advances `g`. **Single-threaded on purpose** -- the defect is in address computation, so it must be observable with no race |
| `atomic_ord_test.quanta` | 0 | **0** | every order on every op, plus the no-argument default, plus the `import std/atomic` names, plus a `let`-bound literal |
| `atomic_ord_probe.quanta` | 30 | **30** | the objdump target for the gate stage |
| `atomic_ws_test.quanta` | **11 (RED)** | **0** | **THE ACCEPTANCE ROW** (below) |
| `thread_concurrent_test.quanta` | 0 | 0 | already registered in `EXPECTED_STDLIB.tsv`; unchanged |

### 6.1 The acceptance row: `atomic_ws_test.quanta`

A concurrent **claim/accumulate** loop over **2048 rows** with N workers, checked
**exactly**:

* every one of the 2048 rows is claimed and processed **exactly once** (a per-row
  write counter -- a duplicate claim is a *detected failure*, not a
  silently-overwritten cell),
* the accumulated total equals `0+1+...+2047 = 2096128` exactly,
* the claim counter ends at exactly `2048 + N` (each worker's terminating claim
  overshoots by one -- a fingerprint of the loop's shape, not a tolerance),
* at N = 1, 2, 4 and 8, checking **every row**, not a reduction.

The claim is `i = atomic_add(&next, 1)` -- a counter living in a **global**, which
is how the loader would naturally write it and exactly the shape that was
measured wrong. Measured result:

```
0.0.258:  rc=11      (case 1: a row was claimed != 1 time -- every worker
                      re-processed row 0 and rows 1..2047 were never touched)
0.0.259:  rc=0       at N = 1, 2, 4, 8
```

The loop carries a **step budget** on purpose. The unbounded form *hangs* on
`0.0.258` (measured: rc 124 against the 15 s harness cap), and a row that eats a
timeout on every red run is a row that trains people to ignore the gate. With the
budget the broken counter produces a **wrong answer immediately**, which is the
failure it actually is.

The same loop is then run again with the counter in a **heap cell reached through
a global pointer** -- the shape `lib/std/gguf_mm.quanta`'s pool protocol already
used, and which *worked* on `0.0.258`. That half pins that the fix did not break
the working usage, and it is why the row is not simply "the pool works".

### 6.2 The guard: `tests/atomic_guard.sh`

Neither the ordering model nor the barrier has a *functional* symptom -- an
ordering is a choice of instruction, and a barrier is a promise that nothing
moved -- so, like the `marshal`/`deadstore`/`terminator`/`constmul` guards, the
stage reads the **emitted object** of `atomic_ord_probe.quanta`, restricted to
`main`. Counts are emitted bytes: exact, load-independent, no wall clock, no
tolerance.


**Why it is a script and not a stage inside `test_suites/scripts/run_tests.sh`.** `run_tests.sh` is the compiler peer's path in the same tree, so this
check lives in its own file and is wired in with ONE line (the same shape as
`marshal-guard`/`deadstore-guard`/`csave-guard`):

```
ATOM_RC=0
if ! QC="$QC" bash tests/atomic_guard.sh; then ATOM_RC=1; fi
   || [ "${ATOM_RC:-1}" -ne 0 ] || ...     # in the exit condition
```

Run by hand: `QC=<qc> bash tests/atomic_guard.sh`. Measured verdicts:

```
0.0.258: counts mov=3 xchg=0 lock-xadd=3  -> FAIL (no locked store)  exit 1
0.0.259: counts mov=2 xchg=1 lock-xadd=3  -> PASS                     exit 0
```

```
                        mov %rsi,(%rdi)   xchg %rsi,(%rdi)   lock xadd
0.0.258                       3                  0               3     -> RED
0.0.259                       2                  1               3     -> GREEN
```

* `xchg >= 1` -- a `seq_cst` store is locked. **This is the row that is RED on the
  predecessor**, for the reason the stage exists.
* `mov <= 2` -- a relaxed/release store is **not** locked, so the order is
  honoured and the `seq_cst` default has not quietly made every store expensive.
* `lock xadd == 3` -- all three atomic RMWs survived the optimiser. **This is the
  barrier row**: the first pass that ever deletes or merges an atomic access turns
  the gate RED.
* plus a negative that must **fail to compile**: an ordering argument that is a
  runtime value, rejected *by name* (`grep -q "ordering argument"`), so the
  rejection cannot pass for the wrong reason.

## 7. Byte-identity accounting (the mechanical cross-check)

`test_suites/scripts/byte_identity.sh 0.0.258 0.0.259 <tsv>` over both tables,
plus an explicit run over the five rows added here (they were registered after the
sweep had read `EXPECTED.tsv`), and a transitive-import closure computed in Python:

```
EXPECTED.tsv         rows=249   identical=248   differing=1    compile-fail=0
EXPECTED_STDLIB.tsv  rows=114   identical=107   differing=7    compile-fail=0
added rows           rows=5     identical=0     differing=5    compile-fail=0
```

**The invariant, checked mechanically over all 368 rows:**

| set | rows | differing |
|---|---|---|
| closure contains an atomic access | 13 | **13** |
| closure contains none | 351 | **0** |

so *byte-identical ⇔ the row's transitively imported sources contain no atomic
access*, and the whole difference is confined to the 13 rows that reach
`lib/std/gguf_mm.quanta` (the only module in the tree that calls these builtins)
or that were written for this version.

**Instruction-level verification of the 21 differing bytes.** For
`stdlib_gguf_mm_test` the two objects differ by exactly **7 sites**, and each is
exactly this:

```
- 5c03e: mov  %rsi,(%rdi)      + 5c03e: mov  %rsi,%rax
- 5c041: mov  %rsi,%rax        + 5c041: xchg %rsi,(%rdi)
```

That is `at_emit`'s store: the value is captured into `rax` before the exchange,
and the default `seq_cst` store is now locked. 7 sites x 3 bytes = **21**, which
is the measured differing-byte count for **every one of the 8 stdlib rows** --
identical on all of them, because the change is local and nothing shifts.
`xchg` in the disassembly: 0 on the predecessor, 7 here.

**ON THE SIZE CROSS-CHECK, WHICH DOES NOT DETECT THIS.** The brief's mechanical
form is "counts shrank on N / grew on 0 / identical on M, and the count-identical
set == the byte-identical set". For this change **that equality is FALSE, and
knowing why matters**: the store swaps one 3-byte instruction for another 3-byte
instruction, so every binary is **byte-length-identical** (measured: `8552`,
`12704`, `435744`, `445000`, ... four examples checked, all equal) while 21 bytes
inside differ. So:

* size/count-identical set = **all 368 rows** (sizes never move),
* byte-identical set = **355 rows**,
* count-identical ⊋ byte-identical, and the difference is exactly the 13 atomic
  rows.

An instruction-count row would therefore report this version as a no-op. The
byte comparison is the instrument that sees it, which is why the gate stage for
the ordering model is a **byte scan** and not a count.

## 8. What was NOT reached

* **AArch64.** There is no AArch64 backend in this tree (§2.1). Nothing was faked.
* **A `relaxed` RMW that is actually cheap.** Impossible on x86-64; documented
  rather than pretended.
* **Two build/test iterations that had to be discarded.** The first build of the
  feature rejected every legal literal because `at_ord` read the argument *record*
  instead of resolving its def chain (`IR_MOV` copies). The first version of the
  `lib/std/atomic.quanta` ordinals used `let`, which cannot resolve to a literal
  through a global read; `const` is what makes the names usable. Both are recorded
  in the source next to the code that had to change, because both are the kind of
  thing that would otherwise be re-learned.
* **No attempt to make the seq_cst ordering assertion measurable at run time.**
  A store-buffering litmus (`r1==0 && r2==0`) is the *semantic* content of the
  store fix, and a probe for it was written; it was **not landed**, because on this
  box a hand-rolled rendezvous between a spinning worker and a spinning main
  thread **segfaults 10/10 times** (rc 139) on both `0.0.258` and `0.0.259`
  (passing under gdb, i.e. a timing-dependent crash), so it is not a stable
  instrument and it is not a property of the atomics: a 2048-row claim loop
  (`atomic_ws_test`) and the pool's own protocol are both stable. That crash is
  **filed, not explained** -- see §9.
* **`unsafe{}` interaction: nothing new was needed, and nothing was claimed.**
  `unsafe{}` already suppresses the overflow, shift-count and index traps per
  operation (`ir_unsafe`). Atomics do not trap, so they compose by doing
  nothing: an atomic access inside `unsafe{}` emits the same instruction, because
  the traps `unsafe{}` removes are not the ones an atomic access can raise. There
  is deliberately no `unsafe{}`-required rule for atomics -- requiring it would
  have been a ritual, and the *absence* of a rule is the decision, so it is stated
  here and pinned by `atomic_ws_test` running entirely outside `unsafe{}`.

## 9. Filed, not fixed

**A two-thread tight-spin rendezvous segfaults.** `main` spinning on
`atomic_load(done)` while a worker spins on `atomic_load(go)` crashes rc 139 in
10/10 runs outside gdb and 0/10 under gdb (i.e. timing-dependent), on **both**
`0.0.258` and `0.0.259`, at N as small as 200 iterations. It is not the atomics:
`atomic_ws_test`'s claim loop (2048 rows, 1/2/4/8 workers, 8 concurrent threads)
is stable and exact across 16+ runs, and `lib/std/gguf_mm.quanta`'s pool (which is
exactly this rendezvous shape via `futex_wait`) drives the whole model today. It is
not explained, and it is not claimed to be fixed by this version.





