# Quanta — Seed & Version-Divergence Checklist

Run this EVERY session that touches the compiler (`compiler/<VER>/src/`).
Any "NO"/"DIVERGED"/non-1 result is a HARD GATE FAILURE — fix before any new work.
Rules of record: PROJECT_RULES §3 (green-state invariant), §9 (seed tracks latest
stable, never a patch behind), §10 (seed in project folder, never /tmp).

## 0. Establish ground truth
- `cat VERSION`                         → current released version, e.g. `0.0.85`
- Active work tree is `compiler/<NEXT>/` (e.g. `0.0.86`); its `PRIOR` seed is
  `bootstrap/qc-bootstrap-<VER>` (e.g. `qc-bootstrap-0.0.85`).
- `<NEXT>` must be exactly ONE patch above `<VER>`. Never skip a version.

## 1. Seed location (§10) — must be a PROJECT folder, never /tmp
- [ ] `bootstrap/qc-bootstrap-<VER>` exists on disk (not in /tmp).
- [ ] `compiler/<NEXT>/bin/x86/qc` exists on disk (not in /tmp).
- [ ] Neither is a `/tmp/qc_new.bin`-style throwaway. If a working qc exists only
      in /tmp: `cp` it into both paths FIRST, then continue.
- [ ] `bootstrap/qc-bootstrap-<VER>` is the promoted qc of the immediately
      preceding version — NOT a historical/old seed. (It must NOT lag by ≥1 patch.)

## 2. Drift check (§9) — seed must reproduce the stored qc from current source
```
cd /opt/tali/quanta
bootstrap/qc-bootstrap-<VER> compiler/<NEXT>/src/x86/main.quanta /tmp/_drift.bin
cmp -s /tmp/_drift.bin compiler/<NEXT>/bin/x86/qc && echo IDENTICAL || echo DIVERGED
rm -f /tmp/_drift.bin
```
- [ ] Result is `IDENTICAL`. If `DIVERGED`: the seed is stale → re-promote `<VER>`
      as `bootstrap/qc-bootstrap-<VER>` (rebuild from `<VER>` source, save, re-run
      this check) BEFORE any new work.

## 3. Self-host fixpoint (§3) — 3-step chain, byte-identical gen2
```
cd /opt/tali/quanta
Q=compiler/<NEXT>/bin/x86/qc
$Q compiler/<NEXT>/src/x86/main.quanta /tmp/f1.bin
/tmp/f1.bin compiler/<NEXT>/src/x86/main.quanta /tmp/f2.bin
/tmp/f2.bin compiler/<NEXT>/src/x86/main.quanta /tmp/f3.bin
md5sum /tmp/f1.bin /tmp/f2.bin /tmp/f3.bin | awk '{print $1}' | uniq | wc -l   # want 1
rm -f /tmp/f1.bin /tmp/f2.bin /tmp/f3.bin
```
- [ ] distinct md5 == 1 (all three stages byte-identical).

## 4. Functional smoke (proves the binary actually works, not just self-hosts)
```
# big-int literal auto-promotion (0.0.85 feature)
printf 'import std/big\nfn main(){ let a = 123456789012345678901234567890\n big_println(a) }\n' > /tmp/sm.quanta
$Q /tmp/sm.quanta /tmp/sm.bin && /tmp/sm.bin   # want 123456789012345678901234567890
```
- [ ] Output matches expected (cross-check vs Python for numerics).

## 5. Gate (§3 step 4) — full suite on gen2 qc, compile-fail folded in
```
QC=compiler/<NEXT>/bin/x86/qc bash test_suites/scripts/run_tests.sh   # want 62/62, 0 fail
```
- [ ] 62/62, 0 fail. Compile-fail counts as fail (never a green row).

## 6. Promote <NEXT> → new stable seed (only after 2–5 all pass)
```
cp compiler/<NEXT>/bin/x86/qc bootstrap/qc-bootstrap-<NEXT>      # seed for <NEXT+1>
# scaffold <NEXT+1>: cp source from <NEXT> into compiler/<NEXT+1>/, keep its qc
# bump VERSION to <NEXT>; rewrite ROADMAP/docs status blocks (§8)
```
- [ ] New `bootstrap/qc-bootstrap-<NEXT>` written; <NEXT+1> tree scaffolds; VERSION bumped.
- [ ] Re-run §2 drift check against the NEW seed before declaring done.

## 8. Doc/rule sync (§8)
- [ ] Every status/root-cause/known-issue block the green gate disproves is deleted
      or rewritten. No stale "BLOCKED" notes.
- [ ] PROJECT_RULES §9/§10 reflect the promotion just performed.
- [ ] **CI pin**: `.github/workflows/ci.yml` golden must be `compiler/<RELEASED>/bin/x86/qc`
      where `<RELEASED>` == `cat VERSION`. A stale CI pin (e.g. 0.0.76 while released
      is 0.0.85) is a divergence-in-waiting — fix it on every release.
- [ ] **Golden layout**: the committed golden is `compiler/<VER>/bin/x86/qc` (a binary).
      There is NEVER a `qc` inside `src/` (that path is gitignored). NOTE: the
      skill's `verify-release.sh` stage-4 checks `src/x86/qc` — that is a broken
      assumption for this repo's layout; ignore its "binary drift" FAIL when
      `bin/x86/qc` matches the fixpoint md5. The real identity check is
      `bin/x86/qc` == 3-stage fixpoint (§3), which is what matters.

---
Failure protocol: on ANY non-pass, ROLL BACK to the last known-good source and
re-promote from the seed (revert is per-file for split libs, rule §6). Do NOT debug
a broken gen2 binary by hand. Never declare "done"/"fixed" without §2–§5 green.
