# 0.0.249 — WIP · **LEVER: F1 — `adistinct` stops evicting live operands (A31)**

```
0.0.248 golden  md5 b9e36271373d108eb52989f08d841365   (frozen baseline, untouched)
0.0.249 g1      md5 e2769a4374b472abf7d1f14b2ba98084   (0.0.248 golden compiling the edited source)
0.0.249 g2      md5 14fd1086617bb1b37a502a33c624c802   (COMMITTED GOLDEN, = fixpoint)
0.0.249 g3      md5 14fd1086617bb1b37a502a33c624c802
0.0.249 g4      md5 14fd1086617bb1b37a502a33c624c802   (distinct(g2,g3,g4) == 1)
```

Two files changed, everything else the 0.0.248 snapshot copied verbatim:

| file | change |
|---|---|
| `src/x86/emitter.quanta` | `adistinct()`'s operand-eviction loop deleted; new `apick_free` / `aevict_nop` / `aremap` / `aunmap`; the `f2i` builtin gets `flush_clob(0,1,2)` + an explicit operand un-map + REX.B on its staging `movq` |
| `src/x86/codegen.quanta` | `width_mask()` no longer reads register 0 (RAX) as "no register was supplied" |

Gate-side, in the same commit: `test_suites/codes/arith_marshalling_probe.quanta`
(new row; `EXPECTED.tsv` 238 -> 239) and the new `marshal-guard` stage in
`test_suites/scripts/run_tests.sh` (+ its summary line, folded into the exit
status).

---

## 1. What landed

`adistinct(res, a1, a2)` used to un-map and **store the home slot of both live
operands on every binary op**, then reload the result from a slot it had just
overwritten. The operands are still live, nothing clobbers their registers, and
nothing reads those slots before the next write, so the stores were dead — and the
operand's next use reloaded what had just been stored. The register map was
emptied on every op, which is why residency never accumulated in a 13-register pool.

0.0.249 deletes the eviction. The non-aliasing guarantee is unchanged (the
free-register scan excluded a1/a2 before too, and `apick_free` is now the only
mechanism, excluding them by construction). When `res` is already mapped to an
operand register — `x = x + y` in place, common now that values stay reserved — the
value is moved with a register-to-register `rr`, never through the frame, because
under the 0.0.245 invariant a **mapped** vreg's home may be stale. `aevict_nop`'s
fallback eviction is bounded (`allocfc>0`); the old degenerate loop read `alloc-16`
when it reached zero.

## 2. Measured effect (instrument of record: `scripts/bench_instr.sh`)

`q_loop` = hot-loop body; `q_lst`/`q_lld` = frame stores/loads inside it.
**30 of 38 benchmark rows changed codegen.**

| metric | 0.0.248 | 0.0.249 | delta |
|---|---|---|---|
| `q_instr` (whole `main`) | 9031 | 8825 | **-2.3 %** |
| `q_loop` (hot-loop body) | 2257 | 2101 | **-6.9 %** |
| `q_mem` (frame ops in `main`) | 2856 | 2645 | **-7.4 %** |
| `q_lst` (home stores in the loop) | 712 | 633 | **-11.1 %** |
| `q_lld` (home loads in the loop) | 352 | 273 | **-22.4 %** |

Largest single row: `regpressure` loop 310 -> 268, loop stores 102 -> 81, loop
loads 33 -> 12. `arith` 98 -> 92, `div_const` 84 -> 76, `loop_sum` 38 -> 32,
`heavy_int`/`heavy_int2` 65 -> 59. Loop-home share median 49.2 % -> 45.6 %.

**The audit's PROJECTED -33 % is REFUTED by this measurement.** A31 was real and is
-6.9 % of the loop body, not half of it: the eviction could only store operands that
were *mapped* when the op ran, and `flush_all()` already spills everything at block
boundaries. Full per-case table and the corrected rank of what remains:
`docs/research/phase2-f1-adistinct-0.0.249.md`.

## 3. Two latent miscompiles F1 exposed, fixed HERE (not worked around)

Removing the eviction removed an accidental side effect that two sites had been
relying on. Both were already wrong in 0.0.248; they were unreachable only because
the old `adistinct` emptied the map on every op.

1. **`width_mask` read RAX (register 0) as "no register"** (`... && rd != 0`). With
   residency, `adistinct` returns RAX and the width truncation was **silently
   dropped**. MEASURED: `mixed_width_mask_test.quanta` exited 103 instead of 7
   (u8 255+1 stopped wrapping to 0).
2. **`f2i` left live vregs mapped across registers it destroys.** It stages through
   `xmm0`, and `cvttsd2si` writes RAX; the old `adistinct(res, rs, -1)` un-mapped
   the operand incidentally. Now explicit: `flush_clob(0,1,2)`, `aunmap(srcv)`, and
   `aunmap(res)` before the RAX result binding (new helper: drop a mapping, storing
   first, so nothing is lost). Also fixed on the same line: the staging `movq`
   emitted a fixed REX byte, so it encoded the wrong register for rd >= 8.
   MEASURED: `sampling_test.quanta`'s argmax loop silently stopped updating its
   running maximum, and `std_vfloat_result_test` failed likewise. Both green now.

## 4. Gate, fixpoint, verification

- **Fixpoint** from the frozen 0.0.248 golden: `b9e36271 -> e2769a43 -> 14fd1086 ->
  14fd1086 -> 14fd1086`; `distinct(g2,g3,g4) == 1`; the committed golden is g2.
- **Drift check** (`0.0.249` golden building `0.0.249/src/x86/main.quanta`):
  **IDENTICAL** (re-run after promotion, §9).
- **Self-host consistency** on the pre-change 0.0.248 tree: **SELFHOST 7/7** (rc 0).
- **Full gate** on the committed golden
  (`QC=./compiler/0.0.249/bin/x86/qc bash test_suites/scripts/run_tests.sh`):
  **`=== Results: 239/239 pass, 0 fail (incl. 0 compile-fail) [rows: EXPECTED.tsv] ===`**
  with every stage GREEN — including the new `marshal-guard`, plus `valgrind`,
  `fuzz` fail-closed (0 crashes), `differential`, `stdlib`, `security` 8/8,
  `performance` 3/3, `qobj`, `verify-status`, `f16c-indep`.
- **`scripts/bench.sh`** (0.0.249 golden): `# OK: every row compiled and every C
  twin kept its loop.` — 0 `MISMATCH`, 0 compile failures; all 38 benchmark
  outputs still equal their C twins.

## 5. Red-first row — proven RED on the previous version

New stage `marshal-guard`: compile `arith_marshalling_probe.quanta` with
`--emit-obj` and count frame-relative stores/loads in the hot loop using the same
AWK metric definition as `bench_instr.sh`. Emitted bytes — exact, load-independent,
no tolerance.

| compiler | loop | loop stores | loop loads | verdict |
|---|---|---|---|---|
| 0.0.248 golden (pre-F1) | 79 | 26 | 10 | **FAIL** (`26 home stores > 23`) |
| 0.0.249 golden (F1) | 67 | 20 | 4 | PASS |

Thresholds 73 / 23 / 7 lie between the two on all three counts, so re-instating the
eviction turns the gate RED for the reason the stage exists.

## 6. Byte-identity across the gate rows

All 239 `EXPECTED.tsv` rows compiled with both compilers, `-O`, byte compare:

| | count |
|---|---|
| **byte-identical** | **33 / 239** |
| differing | **206 / 239** |
| compile-fail | 0 |

Wider than the 0.0.248 unit's 232/238-with-6-differing, and structurally expected:
that lever was a flag/type change, F1 changes the operand/allocation path of every
binary op. A row differs because (1) the operand marshalling of a binary op no
longer stores/reloads, and (2) residency now accumulates, so later `afree`/`aphys`
hand out different registers — pure renaming, which is why rows with no arithmetic
operator at all still differ. Opcode-sequence identity was measured too and is the
same 33/206 set (the removed marshalling *is* a sequence of `mov` opcodes), so it
is not a finer discriminator here.

Equivalence therefore rests on the behavioural oracles, all measured this run:
gate 239/239, 38/38 benchmark outputs matching their C twins, `differential` GREEN,
and the self-host fixpoint.

## 7. What is still open

F2 (dead-store elimination over the provably-dead 30-67 % that remain), F3 (the
comparison round trip: an 8-instruction loop test), F4 (xmm-resident FP; still gated
on the A32 frame/offset mismatch — `fspill_home` writes ~8 KB below `%rbp` while the
frame reserves 1120 bytes), F5 (opt-in FMA), F6 (constant multiply as `lea`/`shl` —
`i*8` is still `imul $0x8`), F7 (LICM), F8 (the constant shift-range check). A33
(`loop_depth`, 21 % of `regpressure`'s loop) is a semantics decision and needs the
language capability (backlog #20) first.

The measured rank has moved: the **block-boundary `flush_all()`** is now the largest
remaining in-loop term, ahead of A31's residue — which is what
`docs/plans/performance.md` predicted as "the next lever after 0.0.245: cross-block
liveness". Next lever after that, per the author's directive: **width** (backlog
#21, explicit vector types), for which the design is proposed in
`docs/research/phase2-vector-design.md`.
