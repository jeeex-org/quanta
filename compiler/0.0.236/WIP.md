# 0.0.235 — WIP

**Lever: A2 — a float reaching a text/int builtin wrote its raw bit pattern.**

## What landed

- `src/x86/emitter.quanta`: the tag dispatch in `print`, `echo`, `println`, `printi`, `printsp` and `exit` now
  **refuses** a float-tagged argument at compile time (including through an `IR_MOV`, mirroring the string
  auto-detect). Before, `print(5.0)` wrote `4617315517961601024` and `exit(5.0)` exited **0** — the bit
  pattern's low byte — both with no diagnostic.
- `src/x86/helpers.quanta`: `chk_float_print()` / `chk_float_exit()`, the two refusals, each naming the
  correct routes (`print_f(x)` for a decimal value, `f64bits(x)` for the exact bits, `f2i(x)` for `exit`).
  Both routes were verified working first: `print_f` -> `5.000000`, `f64bits` -> `4617315517961601024`.
- Sweep: every float-printing site in the tree (27 files across `tests/`, `benchmarks/`, `test_suites/codes`)
  rewritten mechanically to `printi(f64bits(x))` — byte-identical output to before — with the compiler used as
  the oracle for each rewrite (applied, recompiled, reverted if the diagnostic survived).
- `test_suites/scripts/run_tests.sh`: new gate stage **`float-print`** — negative probes for `print(f64)` and
  `exit(f64)` (must be rejected, with the message checked) plus a positive control that `print_f` and
  `f64bits` agree on the same value.

## Verification

| check | result |
|---|---|
| `print(f64)` | rejected, rc=1, `line N:` + the offending source text, naming print_f/f64bits |
| `exit(f64)` | rejected, rc=1, same form, naming f2i |
| sanctioned routes | `5.000000 4617315517961601024`, exit code from `f2i` |
| tree sweep | **all 28 files compile; 27 verified byte-identical** output vs the originals under 0.0.234 (the 28th prints a timing; its result line matches) |
| §2 self-host consistency | **7/7** |
| §3 fixpoint (3 generations) | `md5 7e48d93cfaa822c0eb9bde9565b1cda3`, distinct = **1** |
| §4 smoke (`exit(f2i(p))`) | rc **20** |
| §5 full gate | `rc=0`, **820/820 pass, 0 fail, 0 compile-fail**, **STDLIB 108/108**, **24/24 layers GREEN**, 0 RED |
| §6 verify-release | **14 passed, 0 failed** (0.0.234 rebuilds bit-for-bit; 0.0.235 src/bin in lockstep) |

## Not in this version

A1b (block scoping — a language decision, `docs/research/let-scope-inventory.md`), A3–A7, the Severity B
accuracy tier, and one deliberate omission: `print(x)` does **not** auto-format a float as a decimal. That is
an ergonomics upgrade with a format to choose, not a defect fix, and it is recorded in `docs/plans/bugs.md`
rather than smuggled into this version.
