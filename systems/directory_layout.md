## 11. Directory Layout

```
/opt/tali/quanta/
├── bootstrap/qc-bootstrap-0.0.0     # Seed binary (historic)
├── src/qc-0.0.13.quanta             # STABLE compiler source (P9 traits, frozen)
├── src/qc-0.0.14-wip.quanta         # WIP compiler source (P10 for-in, active)
├── bin/qc                           # Symlink → x86_64/qc-0.0.13
├── bin/x86_64/qc-0.0.13             # x86-64 compiler binary (stable bootstrap)
├── bin/aarch64/                     # ARM64 compiler binaries (cross-compiled)
├── docs/SYNTAX.md                   # Public language reference
├── systems/                         # Internal docs (ROADMAP, rules, status)
├── test_suites/
│   ├── scripts/run_tests.sh         # Test runner (QC=<compiler> bash ...)
│   ├── codes/                       # .quanta test source files
│   ├── bin/                         # Compiled test binaries
│   └── EXPECTED.tsv                 # Exit-code expectations (untracked)
└── README.md
```

**Workflow:**
1. Edit only WIP source (`src/qc-0.0.14-wip.quanta`). Never edit stable.
2. Build with the stable bootstrap: `bin/x86_64/qc-0.0.13 src/qc-0.0.14-wip.quanta /tmp/wX`.
3. Verify: self-host fixed point (`/tmp/wX src/qc-0.0.14-wip.quanta /tmp/shX`, `cmp`), full suite (`QC=/tmp/wX bash test_suites/scripts/run_tests.sh`), ARM cross-compile (`--target=arm64`).
4. Promote via the promotion rules (see systems/PROMOTION_RULES.md).

> Note: `test_suites/` and `systems/` are NOT git-tracked (removed from tracking in commit e40544b); `bin/`, `src/`, `docs/`, `bootstrap/`, `README.md` are tracked.
