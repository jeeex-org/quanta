# Quanta 0.0.105 — Release State

- **Version:** 0.0.105
- **Date:** 2026-08-27
- **Source entry:** `compiler/0.0.105/src/x86/main.quanta` (16 modules)
- **Build seed:** 0.0.104 (`compiler/0.0.104/bin/x86/qc`)
- **Compiler binary:** `compiler/0.0.105/bin/x86/qc`
- **Self-host fixpoint:** byte-identical stage1 (seed-built) == stage2 (self-built), md5 `4699f31355d7feba866abc7644df808b` (verified 2026-08-27).

## What landed in 0.0.105

Five lock-based x86 atomic builtins, added to `is_bltn` (features.quanta) and
`emit_bltn` (emitter.quanta):

- `atomic_load(ptr)`   → `*ptr`                       (plain MOV; x86 loads are not reordered)
- `atomic_store(ptr,v)` → stores v, returns v          (`mov [rdi], rsi`)
- `atomic_add(ptr,v)`   → old value                    (`lock xadd [rdi], rsi`)
- `atomic_swap(ptr,v)`  → old value                    (`xchg [rdi], rsi`)
- `atomic_cmpxchg(ptr,oldv,newv)` → old mem value     (`lock cmpxchg [rdi], rdx`; rax=oldv compare)

All take a *pointer* (use `&var`) and an `i64` value, per the by-value
argument convention of Quanta builtins. Return value is the prior memory
value (cmpxchg returns the old mem value so callers can detect mismatch).

Bugs fixed during bring-up (all real, caught by isolated tests):
1. Name-match off-by-one: every `atomic_*` length was counted +1 with a
   phantom trailing `'_'`, so `is_bltn` and `emit_bltn` never matched. Fixed
   `nl` and dropped the extra char in both tables.
2. `atomic_add` ModRM byte `3E` → `37` (`xadd [rsi], rdi` was reading a bad
   address; should be `xadd [rdi], rsi`).
3. `atomic_swap` ModRM byte `3E` → `37` (same class of bug).
4. `atomic_cmpxchg` used `ira2(ii)` for the ptr arg while the other four use
   `irres(...)`; made it consistent (`irres(ira2(ii))`) to avoid allocator
   interference across consecutive cmpxchg calls.

## Gate status (verified, all GREEN)
- functional: 138/138 core (EXPECTED.tsv) — `atomic_test` added (rc=11) → 138 codes, 138 expected
- extern-c: GREEN (object-mode + gcc libc link)
- security: GREEN (KNOWN bugs reported by script, not blocking)
- performance: GREEN (fib/loop/memfill baselines)
- valgrind: GREEN (compiler binary leak/error scan, 0 errors)
- fuzz: GREEN (fail-closed, 0 crashes)
- differential: GREEN (opt -O == no-O + vs-seed)
- generics-negative: GREEN
- self-host fixpoint: stage1 == stage2 byte-identical (md5 `4699f31355d7feba866abc7644df808b`)

## ROADMAP / FEATURES sync
ROADMAP 0.0.105 → ✅: lock-based atomics (5/5 builtins) GREEN, gated by `atomic_test`.
Futex deferred to a later core (it is an OS-syscall primitive, not a plain
lock instruction).
FEATURES §atomics: atomic_load/store/add/swap/cmpxchg ✅ 5/5 gated.

## Repo hygiene
- `bin/qc` does not exist in project root (per rule).
- Each version lives in its own `compiler/<VER>/` folder, copied from the
  previous stable seed.
- `src/` contains source only; `bin/` holds the promoted seed (tracked).
- All test binaries run via `scripts/quanta_run.sh` (address-space + time caps)
  to prevent OOM runaways; `run_tests.sh` patched to use it.
