# Quanta Security Tooling & Hardening Plan

> Companion to `docs/SAFETY_MANUAL.md` (§6 gaps) and `docs/SPEC.md`.
> Maps reputable security/verification tools onto Quanta's actual architecture
> (self-hosting compiler, bootstrap seed, x86-64 + AArch64 ELF emitters,
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
| **81-test gate** | functional regression (81/81 + 6 sec + 3 perf) | Active (LANGUAGE_DESIGN.md) |
| **Self-host invariant** | qc_boot==qc_self==qc fixed-point | Active (INVARIANTS #1) |

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
| **AFL++ / libFuzzer** | fuzz `qc` with random `.quanta` → prove fail-closed (clean rc, no SIGSEGV) | **HIGHEST ROI for a compiler.** Stand up next (§3). |
| **Differential x86↔ARM64** | compile same prog on both emitters → compare exit codes | Catches backend divergence (two hand-written emitters). |

### Tier 4 — supply chain / process (ISO 26262-8 §11.4)
| Tool | Buys |
|------|------|
| **Dependabot / Renovate** | pin + alert `tree-sitter-quanta` npm deps |
| **SLSA / in-toto** | provenance for `qc-bootstrap-0.0.45` seed (current trust anchor = hand-placed binary) |
| **Reproducible builds** | byte-identical `qc` from seed on clean machine |

---

## 3. AFL++ fuzzing of `qc` (IMPLEMENTED)

Fuzzing the compiler with malformed/unexpected source is the single most
valuable security investment: it proves fail-closed behavior on the
UNTESTED input space (SAFETY_MANUAL §6.5).

### 3.1 What is fuzzed
The `qc` binary (x86-64, from `compiler/0.0.53/bin/x86/qc`) invoked as:
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
| §6.5 untested input | AFL++ | 24h fuzz, 0 crashes |
| §6.2 independent impl | differential x86/ARM64 | exit-code parity on 81-suite |
| §6.3 manual memory | borrow check (Stage 6) | N/A yet |

---

## 6. Version

Tooling plan corresponds to compiler `0.0.53` (commit `be00162`).
Update when a tool is added/removed; each addition MUST record the gap
it closes (§5) and the evidence it produced.
