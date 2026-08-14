# BUG: QC compiler Invalid write of size 8 (memory unsafety)

**Severity:** High (compiler memory corruption; latent SIGSEGV under Valgrind)
**Found by:** `tools/symbolize.py` + Valgrind scan (security layer, 0.0.46)
**Status:** OPEN — candidate for 0.0.47 robustness debt
**Component:** Quanta x86 self-hosting compiler (`compiler/0.0.46/src/x86/`)

## Symptom

Running the QC compiler under Valgrind on a *trivial valid* program
(`fn main() { return 42 }`) produces:

```
== Invalid write of size 8
==    at 0x4A390D: ??? (in .../compiler/0.0.46/bin/x86/qc)
==    by 0x53B46B: ??? (in .../compiler/0.0.46/bin/x86/qc)
==    by 0x400131: ??? (in .../compiler/0.0.46/bin/x86/qc)
== Address 0xffffffffffffffea is not stack'd, malloc'd or (recently) free'd
== Process terminating with default action of signal 11 (SIGSEGV)
```

(On bare metal the program still compiles & runs — the crash only manifests
under Valgrind instrumentation — but the write is genuinely out-of-bounds and
is undefined behavior regardless.)

## Crash attribution (via `qc --debug` + `tools/symbolize.py`)

| Frame | Virtual PC | Offset | Function |
|-------|-----------|--------|----------|
| invalid-write site | 0x4A390D | 669965 | **`init_regs`** |
| caller | 0x53B46B | 1291371 | `main` |
| (earlier standalone run, PC 0x416765) | 0x416765 | 92005 | `mem_load` (read primitive, called everywhere) |

The deepest app frame is **`init_regs`** (offset 669521..671551). The write
targets address `0xffffffffffffffea` = -22 as a pointer — a classic
"index -22 into a base" out-of-bounds pattern, consistent with a register/
global-table index that went negative or was never initialized.

## Likely root cause

`init_regs` initializes the register allocator / virtual-register table at
compiler startup. The `-22` (0xffffffffffffffea) write target strongly
suggests an `r64(vreg_table + idx*8)` style store where `idx` is negative or
out of range — i.e. a bounds-check gap in the allocator init. This is the
same class of bug that previously caused self-host segfaults around
`vreg_type`/`w64` writes (see 0.0.46 debt history); the fix there was to
bounds-check all emit arenas. `init_regs` init likely needs the same guard.

## Reproduction

```bash
# build a debug qc (emits <out>.sym)
qc -O compiler/0.0.46/src/x86/main.quanta /tmp/qc --debug
# run under valgrind
valgrind --leak-check=full /tmp/qc -O test_suites/codes/simple.quanta /tmp/out.bin
# attribute the crash PC
python3 tools/symbolize.py /tmp/qc.sym <crash_pc_from_valgrind>
```

Also reproducible: the valgrind CI workflow (`.github/workflows/valgrind.yml`)
runs this exact scan and fails on `ERROR SUMMARY > 0`.

## Acceptance / fix criteria

- [ ] Valgrind reports `ERROR SUMMARY: 0 errors` for the smoke program
      (and a broader set of test programs).
- [ ] `init_regs` writes are bounds-checked against the vreg/global table size.
- [ ] Add a regression test to `test_suites/scripts/security_tests.sh`
      that runs QC under Valgrind and asserts zero errors (the CI already
      enforces this; a fast local check is desirable too).

## Also tracked (separate, pre-existing) compiler-crash bugs (0.0.47):

1. **Compiler SIGILL on extreme literal `MININT-1`** (`let a: i64 = -9223372036854775808; let b = a - 1`) — the QC compiler itself crashes compiling it.
2. **Compiler SIGILL on garbage input** (e.g. `0xZZZ 0b222`) — malformed source crashes the compiler instead of rejecting it.

These three are the known compiler-robustness debt for 0.0.47.
