# Phase 4 — F6 (0.0.255): a constant multiplier uses the 3-operand `imul`

Lever: **F6** — `i*8` was emitted as `mov $0x8,%eax` + `mov %rcx,%rdx` +
`imul %rax,%rdx`; the 3-operand form removes the multiplicand copy.
Golden `2fe5e2844b9c3a74cf7922152a69ea46`.

Measured in this run against `compiler/0.25{4,5}/`.

---

## 1. The copy, and why it exists

```
0.0.254, `i * 8` in a loop:          0.0.255:
  mov    $0x8,%eax                     mov    $0x8,%eax          (unchanged)
  mov    -0x50(%rbp),%rcx              mov    -0x50(%rbp),%rcx
  mov    %rcx,%rdx        <-- copy     imul   $0x8,%rcx,%rdx    (3-operand)
  imul   %rax,%rdx                     jno; ud2
  jno; ud2
```

The 2-operand `imul rd, rsrc` reads AND writes `rsrc`, so with `i` (`rcx`) still
live the codegen had to copy it first. `imul rd, rsrc, imm32` reads `rsrc`
directly, so the copy is gone — once per constant multiply, and the constant no
longer needs a register either (its register is freed).

## 2. Why NOT `shl`/`lea` — the semantics constraint that shaped the version

The campaign note for F6 says `i*8` → `shl $3` / `lea`. **Neither is usable**, and
this is the substantive finding of the version:

- `imul` sets OF on signed overflow of the product, and `ovf_trap_emit(ii)`
  (`jno +2; ud2`) fires on it. The trap is a language feature (integer overflow
  detection), and 0.0.251/A33 spent a whole version making sure it is only
  removed where the author said so (`unsafe{}`).
- `lea` affects no flags at all.
- `shl` sets OF only for a **1-bit** shift; for a multi-bit shift it is
  undefined/unchanged.

So either substitution silently disables (or randomises) the overflow trap on
every constant multiply. The 3-operand `imul` is the form that keeps the trap
bit-for-bit AND removes the copy. The full `shl` win needs the language to state
the product cannot overflow — which is exactly `unsafe{}` — so a follow-up lever
can lower to `shl`/`lea` where `ir_unsafe[ii]==1` (no trap is emitted there, so no
OF contract exists to honour) and measure that separately.

## 3. Measured effect — 15/38 rows, pure instruction removal, zero memory change

| case | Δq_instr | Δq_loop |
|---|---|---|
| q4k / q4k_heavy | -5 each | -1 each |
| big_array / mem / mem_ops | -4 each | -1 / -2 / -2 |
| heavy_mem | -3 | -1 |
| match / q4k_matmul | -2 each | -1 / 0 |
| arith / div_const / heavy_div / heavy_div2 / heavy_int / heavy_int2 / higher_order | -1 each | -1 each (0 for higher_order) |

Suite totals (all 38 rows):

| metric | 0.0.254 | 0.0.255 | delta |
|---|---|---|---|
| `q_instr` | 8273 | **8237** | **-36 (-0.4 %)** |
| `q_loop` | 1864 | **1849** | **-15 (-0.8 %)** |
| `q_hst` | 1360 | 1360 | **0** |
| `q_hld` | 694 | 694 | **0** |
| `q_lst` | 427 | 427 | **0** |
| `q_lld` | 242 | 242 | **0** |

`Δhome-stores == Δhome-loads == 0` across the suite is the signature that this is
a pure ALU-instruction removal, not a reallocation: nothing moved to or from the
frame.

**Honest scope.** The constant's OWN materialisation (`mov $0x8,%eax`, an
`IR_CONST` record) survives and is now unused. Removing it is a DEAD-CONST lever
(it needs a liveness argument that no later op reads that const vreg), a different
version. So this lever's win is the copy and only the copy — which is why the
suite delta is -0.4 % and not the -25 % a full `shl` substitution would suggest.

## 4. Red-first row

`constmul-guard` reads the hot-loop body size of
`arith_constmul_probe.quanta` (FOUR constant multiplies in the body) from the
`--emit-obj` object. Exact bytes, load-independent, no tolerance.

| compiler | loop body | rc |
|---|---|---|
| 0.0.254 (pre-F6) | **69** | 216 |
| 0.0.255 (F6) | **65** | 216 |

Threshold 66. The identical rc on both is the point: instructions removed, no
value changed.

### 4.1 The vreg-reuse risk, and the row that pins it

F6 decides "is this operand a constant" with `op_is_iconst(vr)`, which scans the
function's IR for an `IR_CONST` whose result vreg is `vr`. Sound only if a vreg is
defined once per function. If `x = 7` reused x's vreg, F6 would fold the stale
constant. `constmul_reuse_test.quanta` (rc=224 on BOTH compilers) exercises it:
`let x = 5` then `x*3`=15, `x = 7` then `x*3`=21, `let k = 9` then `3*k`=27,
`k = 2` then `3*k`=6 — both operand orders and a reassigned constant. Measured
identical, so the reuse does not occur and F6 is value-preserving there.

### 4.2 A VACUOUS FIRST DRAFT OF THE GUARD STAGE, caught and fixed

The first version of the stage printed TWO fields from awk (`%d %d`, loop and
loop-span) into `read -r f6c_loop` — which, with a single variable, assigns the
WHOLE line (`"65 275"`). The comparison then became
`[ "65 275" -gt 66 ]`, which bash rejects with "integer expression expected" and
returns non-zero, so the `elif` never fired and the stage PASSED
**unconditionally** — a check that cannot fail. It was caught in the gate's own
output (`PASS constmul-guard: loop=65 275 (<=66)`) because the extra field printed.
Fixed by printing one field. This is the same class the campaign has already paid
for twice (the withdrawn `objdump` multiset oracle; the rule "an oracle must
refuse to report when its input is empty"). Recorded because the tell was the
extra token in the PASS line, not a failure.

## 5. Verification

| check | result |
|---|---|
| gate (0.0.255) | **245/245 pass, 0 fail, 0 compile-fail**, 0 RED stages, `GATE_RC=0` — `PASS constmul-guard: loop=65 (<=66)` |
| gate (0.0.254, red-first) | **`constmul-guard` RED — `FAIL constmul-guard: loop body 69 > 66`** -> `GATE_RC=1`. (`spillframe-guard` is correctly GREEN there: A32 is already in 0.0.254; A32's own red-first compiler is 0.0.252.) |
| fixpoint (from 0.0.254 golden) | `5c23efdd -> 9a91af73 -> 2fe5e284 -> 2fe5e284 -> 2fe5e284`; distinct(g2,g3,g4)==1 |
| `bench.sh` | 38/38 compiled, 0 MISMATCH, `BENCH_RC=0` |
| `verify-release.sh 0.0.255 0.0.254` | 14 passed, 0 failed |

Equivalence rests on the behavioural oracles: gate exit codes, all 38 benchmark
outputs equal to their C twins, `differential` (`-O` == no-`-O` + vs-seed), `fuzz`
fail-closed, `valgrind` clean, and the self-host fixpoint. Byte-identity is not the
right oracle for this lever — removing a copy changes register allocation
downstream, so rows that do a constant multiply legitimately move.

## 6. F8 measured ZERO on this suite (so it was not taken)

`F8` is "the constant shift-range check" (`shl_trap_emit` emits
`cmp rcx,0x40; jb +2; ud2` and the check is provably unnecessary when the shift
amount is a compile-time constant `< 64`). Measured before implementing:

```
$ grep -hoE '<< *[0-9]+|>> *[0-9]+' benchmarks/*.quanta
   (nothing)
```

No benchmark row has a CONSTANT shift; `benchmark_q4k` / `benchmark_q4k_heavy`
shift by a variable. So F8 would have **zero suite-level effect** and could only be
justified by a dedicated probe — a weaker lever than the ones taken, so it was
deliberately deferred rather than landed as a formality. Constant MULTIPLIES, by
contrast, appear 37 times (`* 8`) plus `* 256` x7, `* 144` x7, which is why F6
went first.
