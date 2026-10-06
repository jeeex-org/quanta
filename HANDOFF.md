# HANDOFF — read this first, every session

Written continuously, not at end of session. If you are a model that just took
over, this file is the state. Verify anything here before trusting it, but start
here rather than rediscovering it.

Repo: `/opt/tali/quanta`   VERSION: `0.0.225`   HEAD: `3136229b`

---

## Current task

Complete the production-native LFM2 inference runtime in `.quanta`: 30 layers
(8 attention + 22 short-conv), GPT-2 BPE tokenizer with `pre='lfm2'`, embedding
wiring, conv+attention KV caches, RoPE, logits, sampling, stopping. Native GGUF
row storage for F32/F16/BF16 and the Q4_0…Q6_K family, descriptor-driven
(bounded, not full f64 materialisation — that is ~20.1 GB against a 6 GB limit).

**Last verified green on this task:** the LFM2 pre-tokenizer matches the upstream
reference on all 101 fixture blocks.

    compiler/0.0.225/bin/x86/qc temp/ptsmoke.quanta /tmp/ptsmoke && /tmp/ptsmoke
    blocks=101 tokens=320 fails=0 OK ptsmoke

---

## OPEN — a real regression, do not start new work until this is understood

    bash test_suites/scripts/run_tests.sh
      functional     : RED
      FAIL break_continue.quanta (expected rc=0, got rc=1)

The compiler's **source and shipped binary disagree**. Rebuilt from its own
source, the compiler computes `s=25` for this:

    let s=0 let i=0
    while i<10 { i=i+1; if i%2==0 { continue }; s=s+i }

The shipped binary gives the golden `36`. Suspect is `parse_while()` in
`compiler/0.0.225/src/x86/parse.quanta:1433` — `w64(lbl_cont+bi*8,st)` sets the
`continue` target to the condition label, which appears right. **That has not
been established; it is a hypothesis.** 0.0.220–0.0.224 all use `ct` here, and
0.0.225 uses `st`, so something changed in this version and the binary was not
rebuilt afterwards.

Detect it in one command:

    bash scripts/selfhost_consistency.sh

It reports `SELFHOST: 6/7`, failing on exactly this. It rebuilds `qc` from
source and diffs behaviour against the shipped binary across four fixtures.

Note: byte-comparing the two binaries will never match — the rebuild embeds
absolute build-time addresses in 32-byte stack-slot initialisers (~44 bytes
differ). Compare behaviour, not bytes.

---

## Uncommitted

    M .gitignore                                  negation so the new gate commits
    ?? scripts/selfhost_consistency.sh             the new gate
    M compiler/0.0.225/src/x86/codegen.quanta      revert of a bad +8, see below
    M compiler/0.0.225/bin/x86/qc                  rebuilt from that source
    ?? docs/plans/arm64-backend.md                 not mine, pre-existing

`codegen.quanta` currently carries a **revert** of the `IR_STR` /
`IR_ARRAY_LEN` `+8` change that HEAD `3136229b` introduced. A string expression
is the `[u64 len][chars][NUL]` **header** pointer — `print`, `str`, `substr`,
`file_open`, `qc_sys_cmd` all read length at `[s]` and bytes at `s+8`. Pointing
the vreg at the characters instead shifts all of them by 8 and silently breaks
`print()`. The revert is correct and needed for src/bin agreement.

---

## Proven wrong — do not re-investigate these

**`continue` in `while` is not broken.** Chased to ground. It does re-evaluate
the condition. My "fixes" were no-ops and one of them produced a compiler that
could not print strings at all.

**String literals reading "8 bytes early" is not a defect.** `mem_load8(lit+i)`
returning the length at `i=0` is the documented header layout, not a bug.

**G6 was already GREEN and is not the task.** It is a module-cache round-trip
stage. I went there after a detour. `scripts/g6_selfcache.sh:22` hardcodes
`V=0.0.217` over the `VERSION` read on line 21, so that gate reports about a
compiler eight versions stale — worth fixing sometime, deliberately not touched
here. 12 other bisect/debug scripts have the same pin.

**`g5_*` bisect scripts are scratch.** Do not run them expecting gate results.

---

## How a regression like this hides

Every other gate stage compiles fixtures with the *shipped* binary. If source
has drifted, they all still pass — the correct binary is what they use. Here
**all 19 stages reported GREEN while the tree was broken.** Only rebuilding from
source exposed it. Hence `scripts/selfhost_consistency.sh`.

---

## Rules that would have prevented this

1. Commit only after the gate is green, and state the observed output in the
   message, not the intent. `3136229b` bundles three unrelated changes — the
   pretokenizer, an unverified codegen change, and a stale `parse.quanta` edit —
   under a message claiming a "fix" that was in fact the bug.
2. Verify a source change by rebuilding, not by re-reading the diff.
3. When a result is verified, write it here immediately. The `fails=0` above
   existed for a while and was lost on the first model switch.