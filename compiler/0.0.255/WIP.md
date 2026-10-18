# 0.0.255 — WIP · **LEVER: F6 — a constant multiplier uses the 3-operand `imul`**

```
0.0.254 golden  md5 5c23efdd1e0550af170dee95f1fbabec   (frozen baseline, untouched)
0.0.255 g1      md5 9a91af735a9a4f07bd8bad9a565e985e   (0.0.254 golden compiling the edited source)
0.0.255 g2      md5 2fe5e2844b9c3a74cf7922152a69ea46   (COMMITTED GOLDEN, = fixpoint)
0.0.255 g3      md5 2fe5e2844b9c3a74cf7922152a69ea46
0.0.255 g4      md5 2fe5e2844b9c3a74cf7922152a69ea46   (distinct(g2,g3,g4) == 1)
```

One file changed, everything else the 0.0.254 snapshot copied verbatim:

| file | change |
|---|---|
| `src/x86/codegen.quanta` | `IR_MUL`'s integer path: a CONSTANT multiplier (either operand) emits the 3-operand `imul rd, rsrc, imm32` instead of allocating a register for the constant, copying the multiplicand and running the 2-operand `imul` |

Gate-side, in the same commit: the new `constmul-guard` stage in
`test_suites/scripts/run_tests.sh` (+ summary line, folded into the exit status)
and the new probes `test_suites/codes/arith_constmul_probe.quanta` (the guard's
kernel, `EXPECTED.tsv` rc=216) and `test_suites/codes/constmul_reuse_test.quanta`
(the vreg-reuse companion, rc=224), so the row count moves **244 -> 246**.

---

## 1. What was emitted, and why it was one instruction too many

`i * 8` inside a loop, on 0.0.254:

```
mov    $0x8,%eax        the constant materialised (IR_CONST)
mov    -0x50(%rbp),%rcx i, from its home slot
mov    %rcx,%rdx        a COPY of the multiplicand ...
imul   %rax,%rdx        ... because the 2-operand imul writes its own source
```

The copy exists only because the 2-operand form READS AND WRITES its source
register, and `i` (`rcx`) is still live. A 3-operand `imul rd, rsrc, imm32` reads
`rsrc` directly and writes `rd`, so the copy disappears — once per constant
multiply. On 0.0.255:

```
mov    $0x8,%eax        (unchanged -- see the honest scope below)
mov    -0x50(%rbp),%rcx
imul   $0x8,%rcx,%rdx   the copy is GONE
```

## 2. WHY NOT `shl` / `lea` — the semantics decision this lever had to respect

`shl $3` and `lea 0x0(,%rcx,8)` are cheaper than `imul`, and the campaign note for
F6 says "`i*8` → `shl $3` (or `lea`)". **Neither can be used here**, and this is
the constraint that shaped the version:

- `imul` sets OF on signed overflow of the product, and `ovf_trap_emit(ii)`
  (`jno +2; ud2`) fires on it. That trap is a language feature.
- `lea` does NOT affect the flags at all.
- `shl` sets OF only for a **1-bit** shift; for a multi-bit shift OF is
  UNDEFINED/unchanged.

Either substitution would therefore silently DISABLE (or randomise) the integer
overflow trap on every constant multiply. That is a semantics change, so the
multiply is **not** strength-reduced to a shift here. The 3-operand `imul` is the
form that keeps the trap bit-for-bit and still removes the copy.

Recorded as the reason F6 is smaller than it looks: the full "shift instead of
multiply" win needs the language to be able to say the product cannot overflow —
which is exactly what `unsafe{}` already expresses (A33). A follow-up lever can
lower to `shl`/`lea` where `ir_unsafe[ii]==1` (no trap is emitted there, so no OF
contract to honour) and measure that separately.

## 3. Measured effect (instrument of record: `scripts/bench_instr.sh`)

**15 of 38 rows changed; every change is instruction REMOVAL with zero memory
traffic change** — the signature of a removed copy, not of a reallocation:

| case | Δq_instr | Δq_loop | Δq_hst | Δq_hld | Δq_lst | Δq_lld |
|---|---|---|---|---|---|---|
| big_array | -4 | -1 | 0 | 0 | 0 | 0 |
| mem | -4 | -2 | 0 | 0 | 0 | 0 |
| mem_ops | -4 | -2 | 0 | 0 | 0 | 0 |
| q4k | -5 | -1 | 0 | 0 | 0 | 0 |
| q4k_heavy | -5 | -1 | 0 | 0 | 0 | 0 |
| heavy_mem | -3 | -1 | 0 | 0 | 0 | 0 |
| match | -2 | -1 | 0 | 0 | 0 | 0 |
| q4k_matmul | -2 | 0 | 0 | 0 | 0 | 0 |
| arith / div_const / heavy_div / heavy_div2 / heavy_int / heavy_int2 / higher_order | -1 each | -1 each (0 for higher_order) | 0 | 0 | 0 | 0 |

Suite totals:

| metric | 0.0.254 | 0.0.255 | delta |
|---|---|---|---|
| `q_instr` | 8273 | **8237** | **-36 (-0.4 %)** |
| `q_loop` | 1864 | **1849** | **-15 (-0.8 %)** |
| `q_hst` / `q_hld` / `q_lst` / `q_lld` | 1360 / 694 / 427 / 242 | identical | **0** |

**Honest scope.** The constant's own materialisation (`mov $0x8,%eax`, an
IR_CONST record) is NOT removed: it stays in the stream unused after this change.
Deleting it is a DEAD-CONST lever (it needs to know no later op reads the const
vreg), a different version. So the win measured here is the copy, and only the
copy.

## 4. Red-first row — proven RED on the previous version

New stage `constmul-guard`: reads the hot-loop body size of
`test_suites/codes/arith_constmul_probe.quanta` from the emitted object. That
probe's `main` holds FOUR constant multiplies, so the body moves by four. Same
instrument as `marshal-guard` / `deadstore-guard` / `terminator-guard`: exact
emitted bytes, load-independent, no tolerance.

| compiler | loop-body instructions | rc | verdict |
|---|---|---|---|
| 0.0.254 golden (pre-F6) | **69** | 216 | **FAIL** (`69 > 66`) |
| 0.0.255 golden (F6) | **65** | 216 | PASS |

The identical rc on both compilers is the point: the lever removes instructions
and changes no value.

### 4.1 The vreg-reuse risk, and the row that pins it

F6 decides "is this operand a constant" with `op_is_iconst(vr)`, which scans the
function's IR for an `IR_CONST` record whose result vreg is `vr`. That is only
sound if a vreg is DEFINED ONCE per function (SSA-like). If a reassignment
(`x = 7`) reused x's vreg, F6 would fold the STALE constant.

`constmul_reuse_test.quanta` (rc=224, both compilers) exercises exactly that:
`let x = 5` then `x * 3` (=15), `x = 7` then `x * 3` (=21), `let k = 9` then
`3 * k` (=27), `k = 2` then `3 * k` (=6) — both operand orders, a reassigned
constant on both sides. MEASURED: **224 on 0.0.254 and 224 on 0.0.255**, so the
reuse does not occur (vregs are per-definition here) and F6 is value-preserving on
the shape that would have exposed it.

## 5. Verification

- **Gate** on the committed golden: see §5.1.
- **Fixpoint** from the frozen 0.0.254 golden: `5c23efdd -> 9a91af73 -> 2fe5e284 ->
  2fe5e284 -> 2fe5e284`; `distinct(g2,g3,g4) == 1`; the committed golden is g2==g4.
- **`scripts/bench.sh`**: see §5.2.
- **`scripts/verify-release.sh 0.0.255 "$(cat VERSION)"`**: see §5.3.

### 5.1 gate

(recorded from the run)

### 5.2 bench.sh

(recorded from the run)

### 5.3 verify-release

(recorded from the run)

## 6. Byte-identity

A lever that changes operand placement is expected to move nearly every row that
does a constant multiply — the copy removal changes register allocation
downstream. Byte-identity is therefore NOT the right oracle; the equivalence rests
on the behavioural oracles: the gate's exit-code match, all 38 benchmark outputs
matching their C twins (`bench.sh`), `differential`, `fuzz` fail-closed,
`valgrind`, and the self-host fixpoint. Measured count is recorded in §5.

## 7. What is still open

- The dead constant materialisation left behind by this change (own version).
- `shl`/`lea` for a constant multiply inside `unsafe{}` (own version, §2).
- **F4** (xmm-resident FP) — still the largest remaining win and still the
  largest risk: wiring `fphys()` means float values leave the GPRs that
  `f64bits`/`f2i`/`fst_x` and the `printi`-on-float diagnostic currently read,
  so it is a cross-cutting change to every path that assumes "a float vreg's bits
  live in its INTEGER home". A32 (0.0.253) removed its prerequisite; the wiring
  itself was NOT reached in this run.
- **F5** (opt-in FMA), **F7** (LICM), **F8** (constant shift-range check —
  MEASURED ZERO on this suite: `grep -hoE '<< *[0-9]+|>> *[0-9]+' benchmarks/*.quanta`
  returns nothing, so no benchmark row has a constant shift and the lever would
  have no suite-level effect; it would need a dedicated probe only), and the
  **vector types**.
