# Quanta — Release & Seed Verification Checklist (SINGLE SOURCE OF TRUTH)

Run EVERY session that touches the compiler (`compiler/<VER>/src/`). Any
"NO"/"DIVERGED"/non-1/FAIL is a HARD GATE FAILURE — fix before any new work.

> Companion audit procedure: skill `quanta-checklist-audit`
> (`references/audit-procedure.md`). If this file and the skill disagree,
> THIS FILE WINS (it is the consolidated single source of truth).

---

## TRIGGER KEYWORDS (when to run / what they mean)
- **"CHECKLIST AUDIT"** → run the FULL audit for the current `<VER>` (all steps below).
- **"checklist" / "CHECKLIST"** → **ALL** gated tests must pass. NO partial. Every
  GREEN claim must be backed by a test exercised THIS session.
- **terse status ("synced? committed? next? checklist?")** → RE-RUN the gate and
  SHOW the output, then START the next task WITHOUT asking. Do not present
  options or ask permission when the rules are clear. ("You know the rules, stop asking.")
- **"continue" / "why stop?" / "done? why keep stopping?"** → if every check is
  GREEN, do NOT stop between versions — keep going until ALL scheduled cores are done.

---

## HARD RULES (baked in — user has corrected these repeatedly; NEVER violate)
These are non-negotiable. Violating any of them is a gate failure by itself.

1. **NEVER hardcode the version.** The only source of truth is the `VERSION`
   file. Use `cat VERSION` / `$(cat VERSION)` everywhere — in the gate command,
   in scripts, in docs paths, in commit messages. No literal `0.0.10x` in any
   committed file path or gate logic. ("Why the fuck do you still hard code?
   VERSION file -- mother fucker.") Comment-only historical references (e.g.
   `// 0.0.101: ...`) are allowed, but executable paths and the gate MUST derive
   from `VERSION`.
2. **`VERSION` is the pointer to the latest stable.** `compiler/$(cat VERSION)/`
   is the live compiler. Never refer to a stale version as "current".
3. **ROADMAP "Current compiler:" header MUST equal `cat VERSION`** after every
   version — and the on-disk value must be the live compiler, not a stale one.
   ("Current compiler: 0.0.100 -- why the fuck?" / "fuckhead know the fucking
   rules.") If you ever report or write "current compiler: X" where X != VERSION,
   that is a rule break — fix it immediately.
4. **Root of project contains ONLY `README.md`, `VERSION`, `.gitattributes`,
   `.gitignore`, and directories (`compiler/`, `docs/`, `scripts/`,
   `test_suites/`).** There is NO `bin/qc` at root. The golden binary lives at
   `compiler/<X>/bin/x86/qc`. ("bin/qc should never exist." / "apart from
   README.md and VERSION there should be no files in root of project.")
5. **ALL shell scripts live in `scripts/`** (and `test_suites/scripts/`). No
   loose `.sh` at project root. ("All shell script stay in scripts folder.")
6. **Green = actually exercised THIS session.** Never mark a core GREEN unless
   the gate ran it and it passed now. ("Why do you mark as green if not done?")
7. **Don't stop between versions.** If every check is GREEN, proceed to the next
   core immediately; do not pause for confirmation. ("Don't stop in between
   version if passed all checks keep going until all cores are done." /
   "why stop? why stop?")
8. **Fix forward — never revert to an older version** unless absolutely
   necessary. Keep the fix moving forward; a passed version is a stable seed, not
   a fallback to downgrade to. ("Make sure you keep fix forward... never revert
   to older version unless absolutely necessary.")
9. **All docs in sync after EVERY version.** ROADMAP, FEATURES, SPEC,
   STATE.md, and this checklist must agree on version numbers, status, and
   feature claims. ("ROADMAP and FEATURES in sync. All docs must be in sync
   after completing each version." / "every in sync?")
10. **Mandatory gate layers — never drop any.** functional, extern-c, security,
    performance, **valgrind**, **fuzz (fail-closed, 0 crashes)**,
    **differential (-O==no-O + vs-seed)**, and **generics-negative**. valgrind
    / fuzz / differential / CI are part of the gate; if any is missing, the gate
    did not run. ("valgrind, fuzz, ci and any other relevant security and
    performance testing may be added to the gate!" / "all the scan and ci passed
    too?")
11. **Fix it, no going on unless bug-free.** A known defect blocks promotion;
    do not present options or ask permission while a bug remains — fix it.
    ("fix it, no going on unless bug free." / "Always fix all the bugs.")
12. **Scope guard — stdlib is NOT a released core stage.** `lib/std/*` (big,
    quantum, linalg, crypto, …) is deferred to the stdlib stage. Do NOT add
    `std_*` tests to `EXPECTED.tsv` and do NOT patch `lib/std/*` under a core
    version. ("stdlibs are not implemented yet, so stdlib test should be done
    after stdlib stage.")
13. **Termux / ARM is not in play.** ARM64 (AArch64) backend is deferred
    POST-0.1.0. Termux is only for testing ARM, and there is no ARM now — do not
    waste cycles on it. ("Termux is only required for testing ARM, there is no
    ARM now.")
14. **Safety / execution guardrails (protect the host):**
    - Memory guard `ulimit -c 0 -v 6000000` BEFORE any run that executes a
      compiled binary (prevents core-dump pollution / OOM).
    - Execute compiled `.bin` ONLY through the gate (`run_tests.sh`) or
      `quanta_run.sh` (768MB VSZ, nice 19). **NEVER run a `.bin` raw** (a raw
      run once hit 13–21TB VSZ and OOM-killed Hermes).
    - **NEVER run `gdb` on a compiled `.bin`** (~1.5GB, disrupts the backend).
      Disassemble statically instead:
      `objdump -D -b binary -m i386:x86-64 --adjust-vma=0x400000 --start-address=0x400120 FILE`.
    - Compiler `src/` must stay `$$(...)`-free to preserve the bootstrap
      fixpoint.
    - All scratch/work stays INSIDE `/opt/tali/quanta` (use `compiler/<VER>/debug/`).
      Never use `/tmp` for compiler work. Delete scratch binaries after each session.

---

## Terminology (derive from `VERSION`, never hardcode)
- `<VER>`   = released/live stable   -> `cat VERSION`        (currently **0.0.102**)
- `<NEXT>`  = the version being built -> exactly ONE patch above `<VER>`
- `<PRIOR>` = `<VER>` itself; its committed golden `compiler/<VER>/bin/x86/qc`
  is the seed for `<NEXT>`. There is NO separate `bootstrap/` directory.
- Golden binary: `compiler/<X>/bin/x86/qc` (committed). NEVER in `/tmp`.

## LIVE STATE (advance this on every promotion)
- Current stable compiler: **0.0.102** (2026-08-27)
- Golden binary: `compiler/0.0.102/bin/x86/qc`
- Self-host fixpoint md5: `a4affa951d64304946862358316240c1` (B==C byte-identical)
- Per-version state is recorded in `compiler/<VER>/STATE.md` and MUST be updated
  each promotion.

---

## 0. Ground truth
- [ ] `cat VERSION` -> <VER>; work tree `compiler/<NEXT>/` exists; <NEXT> == <VER>+1 patch.
- [ ] ROADMAP.md header `Current compiler: <VER>` == `cat VERSION` (no stale value).

## 1. Seed location — project folder, never /tmp
- [ ] `compiler/<VER>/bin/x86/qc` exists on disk (this IS the seed for <NEXT>).
- [ ] `compiler/<NEXT>/bin/x86/qc` exists on disk.
- [ ] Neither is a `/tmp/qc_new.bin`-style throwaway. If a working qc is only in
      /tmp: `cp` it into `compiler/<X>/bin/x86/qc` FIRST.
- [ ] Seed is the immediately-preceding version's golden — NOT a historical/old
      seed, NOT ≥1 patch behind (rule #8: fix forward).

## 2. Drift check — seed must reproduce stored qc from current source
```bash
cd /opt/tali/quanta
compiler/$(cat VERSION)/bin/x86/qc compiler/<NEXT>/src/x86/main.quanta /tmp/_drift.bin
cmp -s /tmp/_drift.bin compiler/<NEXT>/bin/x86/qc && echo IDENTICAL || echo DIVERGED
rm -f /tmp/_drift.bin
```
- [ ] IDENTICAL. If DIVERGED: seed stale -> re-promote <VER> (rebuild from <VER>
      source, save to `compiler/<VER>/bin/x86/qc`), re-run before any new work.

## 3. Self-host fixpoint — 3-step chain, byte-identical gen2==gen3
```bash
cd /opt/tali/quanta
Q=compiler/<NEXT>/bin/x86/qc
$Q   compiler/<NEXT>/src/x86/main.quanta /tmp/f1.bin
/tmp/f1.bin compiler/<NEXT>/src/x86/main.quanta /tmp/f2.bin
/tmp/f2.bin compiler/<NEXT>/src/x86/main.quanta /tmp/f3.bin
md5sum /tmp/f1.bin /tmp/f2.bin /tmp/f3.bin | awk '{print $1}' | uniq | wc -l   # want 1
rm -f /tmp/f1.bin /tmp/f2.bin /tmp/f3.bin
```
- [ ] distinct md5 == 1 (all three stages byte-identical). Record the md5 in
      `compiler/<NEXT>/STATE.md`. Each version has its OWN fixpoint md5 — what
      matters is internal B==C, not matching any older golden.

## 4. Functional smoke (CORE language only — no stdlib; stdlib is deferred)
```bash
cd /opt/tali/quanta
printf 'fn main(){ let s = fadd(i2f(2), i2f(3)); let p = fmul(s, i2f(4)); exit(p) }\n' > /tmp/sm.quanta
Q=compiler/<NEXT>/bin/x86/qc
"$Q" /tmp/sm.quanta /tmp/sm.bin && /tmp/sm.bin < /dev/null >/dev/null 2>&1; echo "rc=$? (expect 20)"
rm -f /tmp/sm.quanta /tmp/sm.bin
```
- [ ] Output/exit matches expected (20). Pure core arithmetic — proves the
      binary works, relies on no stdlib.

## 5. Full gate (7 layers + generics) — EXACT command, uses VERSION
```bash
cd /opt/tali/quanta
ulimit -c 0 -v 6000000
QC=./compiler/$(cat VERSION)/bin/x86/qc bash test_suites/scripts/run_tests.sh
```
- [ ] All GREEN: functional (matches `EXPECTED.tsv` row count — **currently 143**,
      0 fail), extern-c, security 8/8, performance, **valgrind clean**,
      **fuzz fail-closed (0 crashes)**, **differential consistent**,
      **generics-negative GREEN**.
- [ ] Compile-fail counts as fail (never a green row).
- [ ] NEW feature tests for the version are added to `EXPECTED.tsv` and pass.

## 6. Release matrix (verify-release.sh — run `bash scripts/verify-release.sh <NEXT> <VER>`)
- [ ] cwd inside /opt/tali/quanta; no duplicate IR opcodes (collision grep empty).
- [ ] functional / security / performance all GREEN; no compile-fail present.
- [ ] self-host fixpoint md5 matches §3.
- [ ] valgrind 0 errors; optimizer differential fuzz clean; compiler fuzz
      fail-closed (0 crashes); differential vs prior golden PASS.
- NOTE: verify-release.sh stage-4 "binary drift" checks `src/x86/qc` which NEVER
  exists here (golden is `bin/x86/qc`, never in `src/`). Ignore that one FAIL when
  `bin/x86/qc` == fixpoint md5 (it does). The real identity is §3.

## 7. CI pin (must match released version)
- [ ] `.github/workflows/ci.yml` golden == `compiler/<VER>/bin/x86/qc` where
      <VER> == `cat VERSION`. A stale CI pin (golden points at an older version
      than `cat VERSION`) is a divergence-in-waiting — fix it on every release.

## 8. Doc/rule sync (after each version — rule #9)
- [ ] ROADMAP.md header `Current compiler: <VER>` == `cat VERSION`; the version's
      row is marked done with what was ACTUALLY verified (no stale "BLOCKED").
- [ ] FEATURES.md, SPEC.md, and `compiler/<VER>/STATE.md` agree with ROADMAP on
      version numbers, status, and feature claims.
- [ ] No dangling references to removed paths (old `bootstrap/`, root `bin/`,
      stale `qc-bootstrap-*` seeds).
- [ ] No hardcoded version literal in any committed script/path (rule #1).

## 9. Promote <NEXT> (only after 0–8 all pass) — then KEEP GOING (rule #7)
- [ ] `compiler/<NEXT>/bin/x86/qc` is the promoted golden (committed).
- [ ] Bump `VERSION` to <NEXT> via `echo "<NEXT>" > VERSION`.
- [ ] Write/update `compiler/<NEXT>/STATE.md` (fixpoint md5, gate status, what landed).
- [ ] Re-run §2 drift check against the new seed before declaring done.
- [ ] Commit (only `src/`, `STATE.md`, docs, `test_suites/` tests, `EXPECTED.tsv`,
      `VERSION` — NEVER `bin/`, `debug/`, or scratch). Push. Verify remote CI uses
      the new pin.
- [ ] **If all green, do NOT stop — proceed to the next core** (rule #7).

---

## Failure protocol
On ANY non-pass: ROLL BACK to last known-good source and re-promote from the
seed. Do NOT debug a broken gen2 binary by hand. Never declare "done"/"fixed"
without §0–§8 green. Never present options or ask permission while a known
defect remains (rule #11).
