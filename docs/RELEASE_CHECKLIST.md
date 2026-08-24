# Quanta — Release & Seed Verification Checklist (SINGLE SOURCE OF TRUTH)

Run EVERY session that touches the compiler (`compiler/<VER>/src/`). Any
"NO"/"DIVERGED"/non-1/FAIL is a HARD GATE FAILURE — fix before any new work.
Rules of record: PROJECT_RULES §3 (green-state invariant), §9 (seed tracks latest
stable, never a patch behind), §10 (seed in project folder, never /tmp). The seed
IS the prior stable version's committed golden: `compiler/<PRIOR>/bin/x86/qc`.
There is NO separate `bootstrap/` directory.

Conventions:
- `<VER>`  = released version (e.g. 0.0.85)      -> `cat VERSION`
- `<NEXT>` = current work tree  (e.g. 0.0.86)    -> must be exactly ONE patch above `<VER>`
- `<PRIOR>`= `<VER>` itself (the seed for `<NEXT>` is `compiler/<VER>/bin/x86/qc`)
- Golden binary lives at `compiler/<X>/bin/x86/qc` (committed). NEVER in `/tmp`.

## 0. Ground truth
- [ ] `cat VERSION` -> <VER>; work tree `compiler/<NEXT>/` exists; <NEXT> == <VER>+1 patch.

## 1. Seed location (§10) — project folder, never /tmp
- [ ] `compiler/<VER>/bin/x86/qc` exists on disk (this IS the seed for <NEXT>).
- [ ] `compiler/<NEXT>/bin/x86/qc` exists on disk.
- [ ] Neither is a `/tmp/qc_new.bin`-style throwaway. If a working qc is only in
      /tmp: `cp` it into `compiler/<X>/bin/x86/qc` FIRST.
- [ ] Seed is the immediately-preceding version's golden — NOT a historical/old seed,
      NOT ≥1 patch behind.

## 2. Drift check (§9) — seed must reproduce stored qc from current source
```
cd /opt/tali/quanta
compiler/<VER>/bin/x86/qc compiler/<NEXT>/src/x86/main.quanta /tmp/_drift.bin
cmp -s /tmp/_drift.bin compiler/<NEXT>/bin/x86/qc && echo IDENTICAL || echo DIVERGED
rm -f /tmp/_drift.bin
```
- [ ] IDENTICAL. If DIVERGED: seed stale -> re-promote <VER> (rebuild from <VER>
      source, save to `compiler/<VER>/bin/x86/qc`), re-run before any new work.

## 3. Self-host fixpoint (§3) — 3-step chain, byte-identical gen2
```
Q=compiler/<NEXT>/bin/x86/qc
$Q compiler/<NEXT>/src/x86/main.quanta /tmp/f1.bin
/tmp/f1.bin compiler/<NEXT>/src/x86/main.quanta /tmp/f2.bin
/tmp/f2.bin compiler/<NEXT>/src/x86/main.quanta /tmp/f3.bin
md5sum /tmp/f1.bin /tmp/f2.bin /tmp/f3.bin | awk '{print $1}' | uniq | wc -l   # want 1
rm -f /tmp/f1.bin /tmp/f2.bin /tmp/f3.bin
```
- [ ] distinct md5 == 1 (all three stages byte-identical).

## 4. Functional smoke (proves the binary works, not just self-hosts)
```
printf 'import std/big\nfn main(){ let a = 123456789012345678901234567890\n big_println(a) }\n' > /tmp/sm.quanta
$Q /tmp/sm.quanta /tmp/sm.bin && /tmp/sm.bin   # want 123456789012345678901234567890
```
- [ ] Output matches expected (cross-check vs Python for numerics).

## 5. Suite gate (§3 step 4) — full suite on gen2 qc, compile-fail folded in
```
QC=compiler/<NEXT>/bin/x86/qc bash test_suites/scripts/run_tests.sh   # want 62/62, 0 fail
```
- [ ] 62/62, 0 fail. Compile-fail counts as fail (never a green row).

## 6. Release matrix (from verify-release.sh — run `bash verify-release.sh <NEXT> <VER>`)
- [ ] cwd inside /opt/tali/quanta; no duplicate IR opcodes (grep collision check empty).
- [ ] functional / security / performance all GREEN; no compile-fail present.
- [ ] self-host fixpoint md5 matches §3.
- [ ] valgrind 0 errors (if present).
- [ ] optimizer differential fuzz clean.
- [ ] compiler fuzz fail-closed (0 crashes).
- [ ] differential vs prior golden PASS.
- NOTE: verify-release.sh stage-4 "binary drift" checks `src/x86/qc` which NEVER
  exists here (golden is `bin/x86/qc`, never in `src/`). Ignore that one FAIL when
  `bin/x86/qc` == fixpoint md5 (it does). The real identity is §3.

## 7. CI pin (must match released version)
- [ ] `.github/workflows/ci.yml` golden == `compiler/<VER>/bin/x86/qc` where
      <VER> == `cat VERSION`. A stale CI pin (golden points at an older version than
      `cat VERSION`) is a divergence-in-waiting — fix it on every release.

## 8. Doc/rule sync (§8)
- [ ] ROADMAP.md header "Current compiler: <VER>" matches VERSION; status blocks
      for the version just promoted are written; no stale "BLOCKED" notes.
- [ ] PROJECT_RULES §9/§10 reflect the promotion.
- [ ] No dangling references to removed paths (e.g. old `bootstrap/`, root `bin/`,
      `src/`, or stale `qc-bootstrap-*` seeds).

## 9. Promote <NEXT> (only after 2–8 all pass)
- [ ] `compiler/<NEXT>/bin/x86/qc` is the promoted golden (already committed).
- [ ] Bump VERSION to <NEXT>; scaffold <NEXT+1> from <NEXT> source.
- [ ] Re-run §2 drift check against the new seed before declaring done.
- [ ] Commit; push; verify remote CI uses the new pin.

---
Failure protocol: on ANY non-pass, ROLL BACK to last known-good source and
re-promote from the seed. Do NOT debug a broken gen2 binary by hand. Never declare
"done"/"fixed" without §2–§8 green.
