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
3. **roadmap/quanta.md "Current compiler:" header MUST equal `cat VERSION`** after every
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
9. **All docs in sync after EVERY version.** roadmap/quanta.md, SPEC,
   WIP.md, and this checklist must agree on version numbers, status,
   feature claims. ("roadmap/quanta.md and SPEC in sync. All docs must be in sync
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
    - All scratch/work goes in `/tmp` and is **deleted after the problem is solved**
      (never leave `compiler/<VER>/debug/` in the repo — that folder must not exist).
      Remove debug artifacts as soon as the issue is closed.

15. **Every version gets its own `compiler/<VER>/` folder — ALWAYS, even gate-only.**
    Copy the previous stable (`cp -r compiler/<PREV> compiler/<VER>`) and bump `VERSION`
    for EVERY released version, regardless of whether there is a source change. A
    gate-only version (no `src/` change) is still a real release: it exists so its
    ROADMAP ✅ maps to a verifiable on-disk artifact (roadmap/quanta.md
    or docs/roadmap/domains/*.md). **Never mark a version ✅ in
    ROADMAP/docs unless a `compiler/<VER>/` folder exists on disk.** No folder = no
    release = the ✅ is a lie.
16. **A gate stage must be able to FAIL for the reason it exists.** A golden value
    captured from a broken compiler turns the test into a bug shield — the golden
    and the defect agree, so it reports GREEN indefinitely. This is not
    hypothetical: `break_continue.quanta` asserted `s==36` while `continue` was a
    no-op, and 36 *was* the broken output, so the test passed while the feature it
    names did nothing. When fixing a defect, re-derive every affected golden by
    hand from the specification, assert the answer you computed, and prove the test
    fails against the pre-fix binary (`git show <old>:path/to/qc`).
    A test that cannot fail is worse than no test.
17. **Never weaken a golden to make a failing test pass.** If a test disagrees with
    your expectation, first decide which one is wrong by working the arithmetic —
    do not assume the test is stale. Two of the four `continue` cases in
    `break_continue.quanta` "looked wrong" and were not; only one golden was
    actually wrong, and the others were arithmetic I had skipped. Prove the value
    before changing it.
18. **Know where the work is, from tools — never from memory or prose.** On arrival:
    ```bash
    cat VERSION && git log --oneline -3 && git status --porcelain
    ```
    Then read `compiler/<VER>/WIP.md` **and verify its claims by running them** —
    WIP files go stale and mislead. `0.0.225/WIP.md` was titled `0.0.224 — WIP`,
    which is worse than no information. A finished result that lives only in an
    untracked scratch file is not a result: put the test in `test_suites/codes/`
    with a row in `EXPECTED.tsv`, where the gate runs it. Re-derive state at check
    time; do not trust what was written down earlier.
19. **Before editing any file, check whether it is finished work.**
    ```bash
    git log -1 --format=%s -- path/to/file
    ```
    If the last commit touching it describes a completed fix or a GREEN stage, you
    are about to regress it — stop and confirm. Do not go looking for work in
    infrastructure (`qobj_gate`, `g6_selfcache`, bisect scripts) when a functional
    task is already verified and in progress.

---

## Terminology (derive from `VERSION`, never hardcode)
- `<VER>`   = released/live stable   -> `cat VERSION`        (currently **0.0.225**; never type a literal — read it)
- `<NEXT>`  = the version being built -> exactly ONE patch above `<VER>`
- `<PRIOR>` = `<VER>` itself; its committed golden `compiler/<VER>/bin/x86/qc`
  is the seed for `<NEXT>`. There is NO separate `bootstrap/` directory.
- Golden binary: `compiler/<X>/bin/x86/qc` (committed). NEVER in `/tmp`.
- **FROZEN BASELINE = `<VER>`, the release one behind stable.** After promoting
  `<NEXT>`, `<VER>` is the baseline: its `src` is never modified again, and the
  release after that opens as a copy of it. A baseline qualifies only if its
  source rebuilds to its own committed md5 BIT-FOR-BIT (step 5) — otherwise it
  is not a usable fallback and the promotion is not done.

## LIVE STATE (advance this on every promotion)
- Current stable compiler: **0.0.225** — see `cat VERSION`, this literal goes stale.
- Golden binary: `compiler/$(cat VERSION)/bin/x86/qc`
- Gate: 813/813, 19/19 stages GREEN. Self-host behaviour: SELFHOST 7/7.
- Per-version state is recorded in `compiler/<VER>/WIP.md` and MUST be updated
  each promotion — and its title must match its directory. `0.0.225/WIP.md` was
  headed `0.0.224 — WIP`, which misinforms a reader who trusts it (rule #18).

> Never write the compiler's own binary in place: `qc -O src/x86/main.quanta
> bin/x86/qc` truncates the file it is executing and leaves 0 bytes. Always
> build to a separate output path, then install.

---

## 0. Ground truth
- [ ] `cat VERSION` -> <VER>; work tree `compiler/<NEXT>/` exists; <NEXT> == <VER>+1 patch.
- [ ] roadmap/quanta.md header `Current compiler: <VER>` == `cat VERSION` (no stale value).

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

## 2b. Source-vs-binary behaviour — the check §2/§3 cannot make
```bash
cd /opt/tali/quanta
bash scripts/selfhost_consistency.sh          # want SELFHOST: 7/7, rc 0
```
- [ ] 7/7. Every other stage compiles with the **shipped** `qc`, so if source has
      drifted from that binary they all still pass — they use the correct binary.
      Only a rebuild from source sees the drift. That is how a broken
      `parse_while()` shipped with the whole gate GREEN.
- [ ] Compare BEHAVIOUR, not bytes. A self-rebuild embeds absolute build-time
      addresses in 32-byte stack-slot initialisers, so the binaries never match
      byte-for-byte even when correct (~44 bytes differ). Byte comparison against
      a freshly built binary will report a permanent false failure — §2/§3 compare
      against the *committed* binary of the same build, which is a different test.
- [ ] After ANY `src/x86/` change, before any test change: run this first. If it
      reports a disagreement, the compiler is what is wrong — fix forward from
      there. Do not adjust a golden to silence it (rule #17).

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
      `compiler/<NEXT>/WIP.md`. Each version has its OWN fixpoint md5 — what
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
- [ ] roadmap/quanta.md header `Current compiler: <VER>` == `cat VERSION`; the version's
      row is marked done with what was ACTUALLY verified (no stale "BLOCKED").
- [ ] roadmap/quanta.md, SPEC.md, and `compiler/<VER>/WIP.md` agree on
      version numbers, status, and feature claims.
- [ ] No dangling references to removed paths (old `bootstrap/`, root `bin/`,
      stale `qc-bootstrap-*` seeds).
- [ ] No hardcoded version literal in any committed script/path (rule #1).

## 9. Promote <NEXT> (only after 0–8 all pass) — then KEEP GOING (rule #7)
- [ ] `compiler/<NEXT>/bin/x86/qc` is the promoted golden (committed).
- [ ] Bump `VERSION` to <NEXT> via `echo "<NEXT>" > VERSION`.
- [ ] Write/update `compiler/<NEXT>/WIP.md` (fixpoint md5, gate status, what landed).
- [ ] Re-run §2 drift check against the new seed before declaring done.
- [ ] Commit (only `src/`, `WIP.md`, docs, `test_suites/` tests, `EXPECTED.tsv`,
      `VERSION` — NEVER `bin/`, `debug/`, or scratch). Push. Verify remote CI uses
      the new pin.
- [ ] **If all green, do NOT stop — proceed to the next core** (rule #7).

---

## Failure protocol
On ANY non-pass: ROLL BACK to last known-good source and re-promote from the
seed. Do NOT debug a broken gen2 binary by hand. Never declare "done"/"fixed"
without §0–§8 green. Never present options or ask permission while a known
defect remains (rule #11).
