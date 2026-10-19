# 0.0.258 — CS1: callee-saved elision, and why round 2's blocker was not this lever

Baseline `b72f3c3d` / golden `f047748f7eddb3991b7b5306656ceae4` (0.0.257). Every
number below is MEASURED on this box. Status: **LANDED** — gate 249/249, `QOBJ
17/17`, `verify-release` 14/14, fixpoint `e7fc8cd4`.

This closes the record opened by `docs/research/phase5-cs1-callee-saved-BLOCKED.md`
(round 2's revert). The lever is unchanged from round 2's implementation,
recovered from its apply script and reproduced byte-for-byte (CS1-only g1 md5
`1bd406dd8b03b8b8f0f2d196b9066dee` = round 2's value).

## 1. The defect

`codegen.quanta:1917` pushed all five ABI callee-saved registers (RBX, R12-R15)
and `:3285` popped all five in every epilogue, unconditionally. In `is_odd` —
the hot function of the author's row #1, `mutual_recursion` — none of the five is
written. Measured, whole function:

```
0.0.257 is_odd  md5 f047748f         0.0.258 is_odd  md5 e7fc8cd4
  push %rbp                            push %rbp
  mov  %rsp,%rbp                       mov  %rsp,%rbp
  push %rbx                            sub  $0x478,%rsp      <-- 0x450 + 8*5
  push %r12
  push %r13
  push %r14
  push %r15
  sub  $0x450,%rsp
  ...                                  ...
  pop %r15 ... pop %rbx                (no pops)
  pop %rbp                             pop %rbp
  ret                                  ret
```

`is_odd`: **64 -> 44 instructions (-20, -31.25%)**, frame 1104 -> 1144.
0.0.257 emits 64 too, which is the independent confirmation that the address-space
reclaim is codegen-inert.

## 2. Implementation (unchanged from round 2, recovered not rewritten)

* `cs_mask`, a 5-bit scalar; `cs_mark(pr)` from every allocator entry point that
  hands out a destination (`aset`, `aremap`, `afree`, `afree_x`, `apick_free`,
  `ascratch`, `aevict_*`). That is the only way a callee-saved register enters
  use on the paths codegen emits normally.
* `cs_risky(op)`, a **fail-closed** guard for the six ops whose emitted body
  writes a callee-saved register by hand with no allocator involvement:
  `IR_ARRNEW`, `IR_APUSH`, `IR_CLOSURE`, `IR_FREE`, `IR_THROW`, `IR_ASM`. A
  builtin `IR_CALL` (inline emit succeeded) also sets `cs_hard`, because builtins
  such as `str_split` clobber RBX deliberately and rely on the caller's prologue.
* **Removal, not padding.** The bytes of the unused pushes (prologue) and pops
  (every epilogue, recorded per `IR_RET`) are DELETED and the buffer is compacted
  in `cs_finish`. The frame's rsp adjustment grows by 8 per elided register so
  the body's rsp is byte-for-byte where it was, and every epilogue's `add rsp`
  cancels it. Compaction shifts every offset after a removed range, so the three
  tables that can hold an absolute code offset for the function are fixed up: its
  own `patches` entries, its `lblmap` label positions, its `gpatches` data
  patches. Function-start offsets need no fixup: removal begins at
  `func_start+4`, and later functions read `codelen` after this one returns.
* **Scalars, not arenas.** The bookkeeping is 1-16-entry scalars; six 200 KB
  arenas originally tripped `qcrun.sh`'s ceiling. 0.0.257's reclaim bought
  1.47 GB, so this constraint is no longer binding — but the scalars stand.

## 3. The blocker: measured, and it is not this lever

`scripts/g6_selfcache.sh` caches the 327-function compiler, deletes every
`.quanta`, and rebuilds from the cache alone. Round 2 saw a **segfault** ->
`QOBJ 16/17` -> unpromotable, with these isolations: disabling `cs_finish` made
G6 pass 5/5; excluding cache-imported functions did not help; a paranoid build
that marked every callee-saved operand mattered not at all.

Re-measured now (0.0.258 binary unless stated):

| configuration | G6 |
|---|---|
| shipped script, pinned source (`V=0.0.217`), x3 | 5/5, 5/5, 5/5 |
| CS1-only tree (no reclaim), rebuilt from round 2's apply script, x3 | 5/5 x3 |
| CS1-only, own source | 5/5 |
| CS1-only as writer / 0.0.256 as consumer | 5/5 |
| CS1-only as consumer / 0.0.256 as writer | 5/5 |
| reclaim-only g1/g2, pinned source x4 | 5/5 x4 |
| reclaim x writer/consumer/source matrix | 5/5 in every cell |
| gate `QOBJ` stage | **17/17 GREEN** |

**No segfault was observed in any cell, including elision+reclaim combined —
which is what round 2's failing gate actually ran.** Two structural facts also
argue against the ceiling as a *segfault* explanation, and they are stated here
because they bound what can honestly be concluded: (a) the gate's G6 path sets
**no `ulimit -v`** at all, and (b) a failed `mmap` **cannot** segfault — the guard
at `emitter.quanta:2744` is `cmp rax,0; jge +12; mov edi,1; mov eax,60; syscall`,
i.e. `exit(1)`.
So: the offset-accounting class was never demonstrated, and **the G6 segfault
remains unreproduced**. What *is* reproducible on this path is the ceiling plus
the two silent-success defects fixed in 0.0.257. That is the honest limit of this
investigation.

## 4. Accounting and the mechanical cross-check (249 rows)

| check | result |
|---|---|
| counts SHRANK / GREW / identical | **247 / 0 / 2** |
| total emitted instructions | 680,211 -> 659,069 (**-21,142, -3.11%**) |
| byte-identity over the same 249 rows | identical **2**, differing **247**, compile-fail 0 |

count-identical set == byte-identical set == `{mmap1.quanta, test_many_globals.quanta}`.
Both genuinely write RBX (`mov %rdi,%rbx` in the emitted object), so keeping every
save for them is correct — a positive result, not a null one.

## 5. Red-first row

`test_suites/codes/csave_probe.quanta` + Stage 1.6m `csave-guard` (+ `EXPECTED.tsv`
row, same commit). `probe_fn` writes none of the five:

| compiler | `probe_fn` instr | callee-saved push/pop | verdict |
|---|---|---|---|
| 0.0.257 | 86 | 15 | **FAIL** (>80) |
| 0.0.258 | 74 | 3 | **PASS** (<=80) |

## 6. The nine rows after 0.0.258 — none at parity

`scripts/bench_instr.sh`, hot-loop body (`q_loop` = innermost backward branch and
its target) vs `gcc -O2`:

| # | row | q_loop | c_loop | ratio | <=1.00x |
|---|---|---|---|---|---|
| 1 | `mutual_recursion` (`is_odd`, whole fn) | 44 | 12 | 3.67x | no |
| 2 | `heavy_float2` | 54 | 6 | 9.00x | no |
| 3 | `heavy_int2` | 45 | 7 | 6.43x | no |
| 4 | `float` | 116 | 8 | **14.50x** | no |
| 5 | `heavy_float` | 54 | 6 | 9.00x | no |
| 6 | `heavy_int` | 45 | 7 | 6.43x | no |
| 7 | `heavy_div2` | 31 | 7 | 4.43x | no |
| 8 | `arith` | 73 | 20 | 3.65x | no |
| 9 | `div_const` | 55 | 15 | 3.67x | no |

Not reached, in the order they should be attacked next: comparison/jcc fusion
(4 instructions per loop test, every looped row at once), then F4 xmm-resident FP
for the three float rows — `float` at 14.50x is the worst row in the campaign.
Wall-clock is deliberately not quoted: load average ran 10-18 here and within-arm
spread has been measured at 1.24-1.54x, so an absolute ms figure would not travel
across versions.
