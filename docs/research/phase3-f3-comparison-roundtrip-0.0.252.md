# 0.0.252 — F3: the comparison round trip at the block terminator

Phase 3, lever three. `VERSION` 0.0.251 -> **0.0.252**. Source changed:
`src/x86/codegen.quanta` (the `IR_BR` and `IR_RET` handlers), `src/x86/emitter.quanta`
(`f2_live_q` stops force-marking the terminator's own operand live).

```
0.0.251 golden  md5 cd0fc7bf61e066b731a533c1bd3589ea   (frozen baseline, untouched)
0.0.252 g1      md5 f357252469fdf4dd0e974a9867675655   (0.0.251 golden building the edited source)
0.0.252 g2      md5 1d1e2d04a2acc5cdaabcd23e26fdf354   (g1 building the edited source = COMMITTED GOLDEN)
0.0.252 g3      md5 1d1e2d04a2acc5cdaabcd23e26fdf354
0.0.252 g4      md5 1d1e2d04a2acc5cdaabcd23e26fdf354   (distinct(g2,g3,g4) == 1)
```

Instrument of record: `scripts/bench_instr.sh`. Every pre/post pair is MEASURED in this
session, 0.0.251 golden vs the 0.0.252 fixed point.

---

## 1. The defect

A loop test in 0.0.251, from the emitted object of `benchmark_arith.quanta`:

```
 f3: mov -0x50(%rbp),%rcx     ; i
 fa: xor %rdx,%rdx
 fd: cmp %rax,%rcx            ; i < N
100: setl %dl
103: movzbq %dl,%rdx          ; the comparison result, in rdx
107: mov %rcx,-0x50(%rbp,%riz,1)
10f: mov %rdx,-0x70(%rbp,%riz,1)   <-- STORE to the condition's home
117: mov -0x70(%rbp),%rax          <-- RELOAD of the value just stored
11e: test %rax,%rax
121: je 26c
```

The store and the reload exist only because of the ORDER of two statements in the `IR_BR`
handler: `flush_all()` ran first and stored every mapped vreg — including the condition,
which is live at that moment *only because the branch is about to read it* — and then
`aphys(a0)` found the vreg un-mapped and read it back out of the frame. The value never
needed to leave the register file. A block terminator's operand is the classic case of a
value that is used and then dies, so this round trip is paid on **every** loop test and
every `return`.

## 2. The lever

`flush_all()` is a **store-only** pass — `mov [rbp+disp], reg`, nothing else — so it
cannot disturb a physical register. (The `IR_PARAM` widening path has relied on exactly
this property since 0.0.245.) So the fix is to reverse the order *inside the terminator's
handler*:

```
let cv=aphys(a0)     // materialise the condition into a register FIRST
flush_all()          // may store it, may not; either way cv is still live
rtest(cv,cv)         // the test reads the REGISTER
```

and, since the terminator's home slot is no longer read after the flush, `f2_live_q` no
longer special-cases `ira0(p)` at `IR_BR`/`IR_RET`. That special case existed only to
compensate for the old order; with the order fixed it would keep the store alive for
nothing. The store is now decided purely by `live_out(block)`, which is the correct
question: *does a successor read this?* For a `let c = a < b; if c { print(c) }` the
value really is live-out and is still stored.

Same change at `IR_RET`, where the return value was likewise stored and reloaded. A block
ending in `IR_RET` has **no successors**, so with the terminator operand no longer
force-marked live the `RET` flush now stores nothing at all — which is correct: no code
runs after a `ret`. (Functions containing `IR_TRY`, whose early-return target does read
state, are excluded from the filter entirely by `f2_analyze`.)

The same emitted loop test now:

```
 fd: cmp %rax,%rcx
100: setl %dl
103: movzbq %dl,%rdx
107: mov %rcx,-0x50(%rbp,%riz,1)
10f: test %rdx,%rdx          <-- the register, directly
112: je 25d
```

## 3. Measured effect — the instrument of record

38 rows. **All 38 rows changed codegen** (every row has at least one branch or return).

| metric | 0.0.251 | 0.0.252 | delta |
|---|---|---|---|
| `q_instr` (whole `main`) | 8420 | 8273 | **-1.7 %** |
| `q_loop` (hot-loop body) | 1926 | 1864 | **-3.2 %** |
| `q_mem` (frame ops in `main`) | 2240 | 2055 | **-8.3 %** |
| `q_hst` (home stores, `main`) | 1454 | 1360 | **-6.5 %** |
| `q_hld` (home loads, `main`) | 785 | 694 | **-11.6 %** |
| `q_lst` (home stores in the loop) | 458 | 427 | **-6.8 %** |
| `q_lld` (home loads in the loop) | 273 | 242 | **-11.4 %** |

Every row with a loop shows the same signature — **loop body -2, loop stores -1, loop
loads -1** — because every row has exactly one loop test:

| case | loop | loop st | loop ld | | case | loop | loop st | loop ld |
|---|---|---|---|---|---|---|---|---|
| match | 141 -> **139** | 28 -> 27 | 14 -> 13 | | heavy_int/_int2 | 52 -> **50** | 9 -> 8 | 6 -> 5 |
| float | 120 -> **118** | 38 -> 37 | 29 -> 28 | | q4k/_heavy | 53 -> **51** | 12 -> 11 | 9 -> 8 |
| fileio | 83 -> **79** | 19 -> 17 | 18 -> 16 | | mem / mem_ops | 50 -> **48** | 13 -> 12 | 7 -> 6 |
| arith | 82 -> **80** | 13 -> 12 | 9 -> 8 | | big_array | 50 -> **48** | 13 -> 12 | 7 -> 6 |
| div_const | 66 -> **64** | 16 -> 15 | 10 -> 9 | | loop_sum | 27 -> **25** | 5 -> 4 | 4 -> 3 |
| heavy_float/_2 | 58 -> **56** | 16 -> 15 | 12 -> 11 | | regpressure | 254 -> **252** | 67 -> 66 | 12 -> 11 |

`q_hld` falls further than `q_lst` (-96 vs -31) because the `RET` round trip is removed
too, and those are non-loop loads; `fnptr_indirect` and `match` (many returns) contribute
most of that.

### The campaign total, 0.0.248 -> 0.0.252

| metric | 0.0.248 (fair baseline) | 0.0.252 | delta |
|---|---|---|---|
| `q_instr` | 9031 | 8273 | **-8.4 %** |
| `q_loop` | 2257 | 1864 | **-17.4 %** |
| `q_mem` | 2856 | 2055 | **-28.0 %** |
| `q_lst` | 712 | 427 | **-40.0 %** |
| `q_lld` | 352 | 242 | **-31.2 %** |

## 3b. A latent invariant this lever exposes — and the first build of it broke

The first build of F3 reordered `IR_RET` **unconditionally**, and the gate caught it:
`test_suites/codes/question_mark.quanta` printed the right numbers (`7`, `0`) and then
**exited 173 instead of 0**.

Cause, and it is a real finding: the `?`-on-Err unwind jumps to `early_ret_lbl` with
`rax` ALREADY holding the whole `Option`/`Result` base pointer, and it was relying on a
side effect of the old statement ORDER — `flush_all()` emptied the register map, so the
following `aphys(a0)` got `RAX` back from `afree()` (first entry of `REGS`) and loaded the
return value straight into it, making the subsequent `if rv!=0 { rr(0,rv) }` a no-op.
Materialising the value first allocates a *different* register, and the `rr(0,rvz)` then
overwrites the early-returned pointer.

The fix is a guard, not a revert: the reorder is taken only when `f2_ok == 1`, which —
because `f2_analyze` refuses any function containing `IR_TRY` — is exactly the predicate
"this function has no early-return label". Functions with `?` keep the 0.0.251 order
verbatim. The `IR_BR` half needs no such guard: nothing jumps into the middle of its
handler.

This is the second time in the campaign that the allocator's flush was silently
providing an invariant (0.0.249 exposed two the same way). Both times the fix was to make
the requirement explicit rather than to keep the accidental behaviour.

## 3c. Red-first row, registered in this commit

New stage `terminator-guard`, using the same probe and the same byte metric as
`deadstore-guard` (emitted bytes, exact, load-independent):

| compiler | loop | loop stores | loop loads | verdict |
|---|---|---|---|---|
| 0.0.251 golden | 52 | 7 | 4 | **FAIL** (`52 > 51`, `4 > 3`) |
| 0.0.252 golden | 50 | 6 | 3 | PASS |

Thresholds 51 / 7 / 3. The round trip coming back costs exactly +1 loop instruction and
+1 loop load, so the stage fails for the reason it exists. No new gate *row* is needed —
the probe row already exists — so `EXPECTED.tsv` stays at 242.

## 4. What F3 does NOT close

The loop test is now 5 instructions (`cmp; setl; movzbq; test; je`), not gcc's 2
(`cmp; jl`). The remaining three are the **materialisation of the comparison as a boolean
value** — `setl` + `movzbq` and the redundant `xor %rdx,%rdx` that clears the register
before `setl` writes its low byte. Those are only needed because the IR represents a
comparison as a first-class i64 the branch consumes. Closing that gap is a *peephole over
two IR ops* (`IR_LT` immediately followed by `IR_BR` on its result, nothing else reading
it: emit `cmp; jcc` from the flags and skip the materialisation), which is a different
lever from the round trip this version removes — and it must be its own version with its
own red-first row, because it changes the comparison's *result register* and therefore
the register allocation of the loop.

## 5. Verification

- Gate / fixpoint / verify-release / bench.sh: see `compiler/0.0.252/WIP.md`.
- Byte-identity: wide by construction (the reorder changes where a value is read from on
  every branch and return), so equivalence rests on the behavioural oracles: the gate's
  exit-code match on every row, all 38 benchmark outputs against their C twins, the
  `differential` stage (`-O` == no-`-O` and vs-seed), `fuzz` fail-closed, `valgrind`, and
  the 4-generation self-host fixpoint.
