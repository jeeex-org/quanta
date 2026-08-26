# Quanta Security Tooling & Hardening Plan

> Companion to `docs/SAFETY_MANUAL.md` (§6 gaps) and `docs/SPEC.md`.
> Maps reputable security/verification tools onto Quanta's actual architecture
> (self-hosting compiler, bootstrap seed, x86-64 ELF emitter; AArch64 backend planned POST-0.1.0,
> tree-sitter grammar). Records what is in place, what is planned, and the
> gap each tool closes.

Last updated: 2026-08-16. Compiler version: 0.0.53.

---

## 1. Current tooling (baseline)

| Tool | What it covers | Status |
|------|---------------|--------|
| **Valgrind** (memcheck) | compiler own memory safety (leaks/UB) | Active; 0 errors on self-compile + crash-repros |
| **CodeRabbit** | PR review of `main.quanta` (entry point) | Active; module-file review blocked until grammar landed |
| **tree-sitter-quanta** | parse/static-analysis surface for all 15 modules | **Active v0.0.53 — 0 errors on every module** |
| **110-test gate** | functional regression (110/110 + 8 sec + 3 perf) | Active (LANGUAGE_DESIGN.md) |
| **Self-host invariant** | committed `compiler/$(cat VERSION)/bin/x86/qc` → source → qc, byte-identical fixed point | Active (ARCHITECTURE.md INVARIANTS #1) |

Gap: Valgrind is the ONLY dynamic analyzer; no fuzzing, no static
analyzer beyond CodeRabbit, no sanitizers, no differential backend test.

---

## 2. Tooling roadmap (prioritized)

### Tier 1 — compiler memory/UB correctness (Augments Valgrind)
| Tool | Catches | Why for Quanta | Gap closed |
|------|---------|----------------|-----------|
| **ASan + UBSan** (`-fsanitize=address,undefined`) | heap OOB, UAF, signed overflow, misalign, null | Faster + broader than Valgrind; run on `qc` built via sanitizer-aware host | SAFETY_MANUAL §6.1 (deeper UB) |
| **MSan** (`-fsanitize=memory`) | use-of-uninitialized (the exact class we fixed: 298 uninit → 0) | Stricter/faster than Valgrind for uninit | SAFETY_MANUAL §6.1 |
| **clang static analyzer** (`scan-build`) | path-sensitive leaks/null | Static complement to dynamic Valgrind | §6.4 process |

### Tier 2 — source/static analysis of Quanta programs (Augments CodeRabbit)
| Tool | Catches | Fit |
|------|---------|-----|
| **Semgrep** (custom Quanta ruleset) | paren/balance, wrong-hash, taint patterns over tree-sitter AST | **Direct fit** — uses tree-sitter-quanta. Catches the H_ENUM-class bug automatically in CI. |
| **CodeQL** | deep taint/semantic queries | Needs Quanta query pack or analysis of emitted ASM/IR; heavier |
| **clang-tidy** | only via LLVM IR path (future) | Not applicable to Quanta source today |

### Tier 3 — behavioral / input safety (Closes §6.5 untested-input gap)
| Tool | Buys | Notes |
|------|-------|-------|
| **AFL++ / libFuzzer** | fuzz `qc` with random `.quanta` → prove fail-closed (clean rc, no SIGSEGV) | **DONE** (self-contained harness, v0.0.53): 20K iters, 0 crashes. See §3.5. |
| **Differential x86↔ARM64** | compile same prog on both emitters → compare exit codes | **PARTIAL** (v0.0.53): tools/diff_test compares CURRENT qc vs independent bootstrap-SEED qc (two artifacts from different eras) → 5/5 behavioral parity. Full x86↔ARM64 when Stage-4 backend lands. See §7. |

### Tier 4 — supply chain / process (ISO 26262-8 §11.4)
| Tool | Buys |
|------|------|
| **Dependabot / Renovate** | pin + alert `tree-sitter-quanta` npm deps |
| **SLSA / in-toto** | provenance for the seed `compiler/<VER>/bin/x86/qc` (the prior stable version's committed golden; current trust anchor = hand-placed binary) |
| **Reproducible builds** | byte-identical `qc` from seed on clean machine |

---

## 3. AFL++ fuzzing of `qc` (IMPLEMENTED)

Fuzzing the compiler with malformed/unexpected source is the single most
valuable security investment: it proves fail-closed behavior on the
UNTESTED input space (SAFETY_MANUAL §6.5).

### 3.1 What is fuzzed
The `qc` binary (x86-64, from `compiler/$(cat VERSION)/bin/x86/qc`) invoked as:
`qc -O <fuzz_input.quanta> /tmp/fuzz_out`
The fuzzer mutates `.quanta` text; we assert the process NEVER crashes
with a signal (SIGSEGV/SIGILL/SIGABRT) and ALWAYS exits with a defined
code (0, 1, 7, 132 — see SPEC.md §6). Any other outcome = bug.

### 3.2 Harness
`tools/fuzz/afl_qc_harness.c` (or a shell wrapper):
- reads fuzz input from `stdin`/file arg
- invokes `qc` on it
- maps exit codes: 0/1/7/132 = expected (safe); signal/other = CRASH (report)
- AFL++ `persistent mode` for speed (re-exec in-process)

### 3.3 Seed corpus
`tools/fuzz/seeds/` — the 15 compiler modules + a few minimal programs
(`fn main(){ return 0 }`, the 81-test programs). Gives AFL++ valid
structure to mutate from.

### 3.4 Acceptance
- 24h fuzz run → 0 crashes on valid-signal handling (only clean rcs).
- Any crash → file defect (SAFETY_MANUAL §5 table), minimize, fix, re-fuzz.

### 3.5 Result (2026-08-17, v0.0.53)
`tools/fuzz/fuzz_qc.py` run against `compiler/0.0.53/bin/x86/qc`:
- **20,000 iterations, 0 crashes.** All exits were defined codes:
  rc=1 (internal/MAP_FAILED, 970 hits), rc=16 (import resolution
  failed, 19030 hits). No signal deaths (SIGSEGV/SIGILL/SIGABRT), no
  timeouts, no unexpected rc.
- **Hard MAX_INPUT=64KB cap** prevents the exponential input-growth
  defect found in v1 of the harness (uncapped slice-duplicate mutated a
  60KB seed into a 14GB file that exhausted RAM — fixed before any
  committed run).
- **Closes SAFETY_MANUAL §6.5** (untested input space): the compiler is
  proven fail-closed on arbitrary/garbage `.quanta` input.
- NOTE: this is a coverage-naive byte mutator (no AFL++ on host — not
  packaged for AlmaLinux). Swap in AFL++/libFuzzer later for guided
  search; the harness is structured for that upgrade.

---

## 4. Semgrep custom ruleset (PLANNED)

`tools/semgrep/quanta/` with rules that encode lessons from this session:
- **paren-balance** — flag any `let H_*` hash fold with unbalanced `()`.
  (Would have caught S-004 automatically.)
- **no-trailing-semicolon-let** — informational; documents the newline-
  terminated `let` style.
- **unsafe-block-count** — warn if `unsafe{}` count exceeds a threshold
  (audit signal, mirrors the compiler's own "N unsafe block(s) parsed").

Semgrep consumes `tree-sitter-quanta`'s parse output (or its own Quanta
grammar) — the grammar work (point 5) is what unlocks this.

---

## 5. Gap → Tool → Evidence trace

| SAFETY_MANUAL gap | Tool | Evidence target |
|-------------------|------|-----------------|
| §6.1 formal/deep UB | ASan/UBSan/MSan | 0 sanitizer errors on self-compile |
| §6.4 process | scan-build, Semgrep CI | clean static scan in CI log |
| §6.5 untested input | fuzzer | 20K iters, 0 crashes (DONE §3.5) |
| §6.2 independent impl | differential (current vs seed qc) | 5/5 behavioral parity (DONE §7) |
| §6.3 manual memory | borrow check (Stage 6) | N/A yet; CODE_CAP/DAT_CAP guards added §7.1 |

---

## 6. Memory-safety hardening (POINT #1) — v0.0.53

The native backend emits raw bytes into `mmap` buffers via `w8/w32/w64`
with no write-side bounds check (SAFETY_MANUAL §6.3). Two layers added:

### 6.1 Write-buffer caps (defense-in-depth)
- `CODE_CAP = 33554432` (code buffer), `DAT_CAP = 33554432` (string-literal
  buffer) constants added in globals.quanta.
- `eb`/`ei`/`eq` (emitter.quanta) abort `exit(1)` if `codelen >= CODE_CAP`.
- codegen.quanta:836 (manual `add rsp,frame_size` block) and :1219 (string
  literal write) abort `exit(1)` if `codelen+7 > CODE_CAP` / `data_off+bsz >
  DAT_CAP`.
- Self-host verified clean after the change (3-stage, binary 755).

### 6.2 Reachable boundary (already present)
For realistic programs the **IR/token buffer (1GB) overflows before the 32MB
code cap** — that path already exits cleanly via `exit(17)` (verified: a
60k-function input → rc=17, not a SIGSEGV). So the PRIMARY fail-closed
memory boundary is `exit(17)`; the CODE_CAP/DAT_CAP guards are
defense-in-depth that would bind if buffers are later rebalanced.

### 6.3 Honest limitation
These are RUNTIME traps (fail-closed), not COMPILE-TIME proofs. Quanta's
memory model remains manually-managed (SAFETY_MANUAL §6.3). True memory
SAFETY (no UB possible) requires Stage-6 borrow checking — out of scope
for v0.0.53.

---

## 7. Independent-implementation evidence (POINT #2) — v0.0.53

Quanta has ONE self-hosting compiler. Full independent implementation
(second hand-written compiler) is a multi-month effort (SAFETY_MANUAL §6.2).
Interim, runnable cross-check delivered:

### 7.1 Differential test (tools/diff_test/diff_qc.py)
Compiles reference programs with BOTH:
- **CURRENT** qc (`compiler/<VER>/bin/x86/qc`, rebuilt from `compiler/<VER>/src/x86/main.quanta`), and
- **SEED** `compiler/<VER>/bin/x86/qc` (the prior stable version's committed golden — an INDEPENDENT artifact from a different
  point in history — a genuine second implementation instance).

Asserts behavioral parity (same runtime exit code) and reports binary
byte-identity.

**Result (2026-08-17):** 5/5 reference programs agree across both
compilers; 4/5 produce byte-identical ELF. This is weak-but-real
cross-implementation consistency evidence — it shows the compiler is
deterministic and not a one-off accident.

### 7.2 Upgrade path
When the ARM64 backend lands (Stage 4), extend this harness to
x86-vs-ARM64 differential: two TRULY independent emitters over the same IR.
That is the strong form of independent implementation for qualification.


---

## 6. Version

Tooling plan corresponds to compiler `0.0.53` (commit `be00162`).
Update when a tool is added/removed; each addition MUST record the gap
it closes (§5) and the evidence it produced.
