# Quanta — documentation map

Consolidated 2026-10-05. This file is the index; the docs it lists are the
source of truth. Anything not listed here has been removed as superseded.

> **WARNING — `SPEC.md` is NOT current and must not be used as the normative
> contract until it is refreshed.** It was last edited at the 2026-10-05
> consolidation and **eight promoted versions have landed since** (0.0.229 ->
> 0.0.235), none of them reflected: `asm!`, `naked` / `section` / `no_mangle`,
> packed structs, ring-0 / IDT / bare-metal boot, and the 0.0.235 A2 change that
> makes a float at `print`/`exit` a compile error (`print_f` / `f64bits` are the
> routes) all have **zero mentions**. Measured with
> `grep -ci '<feature>' docs/SPEC.md`. Under rule 1 above this file is in
> violation of its own convention: a doc is either current or gone.
>
> Consequence for defect triage: a classification may not rest on a SPEC.md line
> alone. A1b's "block scope" question is the live example -- SPEC.md:94 calls a
> bare `{ }` block "(scoping)" while the implementation leaks bindings out of it
> and 11 sites in the compiler's own source depend on the leak, so which side is
> authoritative is an author decision, not something the stale line settles.

## Ground rules for docs in this repo

1. **A doc is either current or gone.** No document is kept "for history" — git
   history is the archive. The one exception is `compiler/<VER>/WIP.md`, which
   records the state of a specific release and is frozen with it.
2. **A claim needs a command.** No doc asserts a test count, md5, or pass rate
   unless a command in the same session produced it. This is why several earlier
   claims were deleted: they were false and had been carried forward unverified.
3. **Generated docs are not edited by hand.** They carry a generator banner and
   are rebuilt from source.
4. **Root `VERSION` is the only version pointer.** There is no `compiler/VERSION`.
   Deleted in `3631dd95` after it was found reading `0.0.192` across 30 releases
   while nothing consumed it.
5. **The frozen baseline is the release one behind stable.** With stable at
   `0.0.224` that is `0.0.223` (`md5=ff78dcbbb0cbfb94a1127c7813595f83`),
   measured to rebuild bit-for-bit from its own source. It is never modified
   after promotion; the next release opens as a copy of it. `0.0.222` is one
   behind the baseline and is kept only because it reproduces bit-for-bit too.

## Compiler — current

| Doc | What it is |
|---|---|
| `compiler/0.0.224/WIP.md` | Current stable release record |
| `compiler/0.0.223/WIP.md` | Frozen baseline — one behind stable |
| `compiler/0.0.222/WIP.md` | Older fallback, retained (reproduces bit-for-bit) |
| `docs/SYNTAX.md` | Language syntax reference |
| `docs/SPEC.md` | Language specification |
| `docs/FLAGS.md` | Compiler flags |
| `docs/COMPILER_KNOWLEDGE.md` | **Generated** from current source by `scripts/build_knowledge.py` |

## Research — defect investigations

Each is a dated finding with its reproduction and current status. These are kept
because the reasoning is not recoverable from the diff.

| Doc | Status |
|---|---|
| `docs/research/let-scope-inventory.md` | **Active** — block-scoped `let` migration inventory: the one-line `parse_block` patch, the 11 compiler-internal sites it would break, and the decision inputs (A1b) |
| `docs/research/trait-dispatch-increment-plan.md` | **Active** — the 0.0.224 plan |
| `docs/research/native-inference-gaps.md` | **Active** — verified gap list |
| `docs/research/struct-return-defects.md` | Active — what is fixed, what is not |
| `docs/research/call-order-f64-defect.md` | Resolved, retained as a pattern |

## Native inference

| Doc | Note |
|---|---|
| `docs/NATIVE_INFERENCE.md` | **Consolidated** status of loader + engine |

The loader is verified. The inference engine does not exist yet. Three former
plans (`plans/quanta-native-gguf.md`, `plans/native-inference.md`,
`plans/100-native-rag.md`) were merged into that single file — they described a
superset design that the measured gap list has since made more precise.

## Roadmap

| Doc | Note |
|---|---|
| `docs/roadmap/quanta.md` | Core roadmap and domain index |
| `docs/roadmap/domains/*.md` | 97 domain files |

See "Roadmap accuracy" below — these were stale and have been corrected.

## Safety and release process

| Doc | Note |
|---|---|
| `docs/SAFETY_MANUAL.md` | Safety manual and qualification status |
| `docs/MEMORY_SAFETY_ARGUMENT.md` | The memory-safety argument itself |
| `docs/SECURITY_TOOLING.md` | Security tooling |
| `docs/RELEASE_CHECKLIST.md` | Release and seed verification procedure |

## Design and architecture

| Doc | Note |
|---|---|
| `docs/ARCHITECTURE.md` | System architecture handoff |
| `docs/SELF_IMPROVEMENT.md` | Self-improvement architecture |
| `docs/GPU_ROADMAP.md` | GPU backend roadmap |
| `docs/OS_ROADMAP.md` | OS/kernel roadmap |
| `docs/AUDIT_ROADMAP.md` | Compiler security audit, 86 items |

## Plans — active work

| Doc | Note |
|---|---|
| `docs/plans/bugs.md` | **Active, first** — every verified defect; fixes land from 0.0.234 before any speed work. Includes the LIVE/STALE verification pass (two compiler crashes, `print` on f64, fail-open `gguf_type_size`, recursion ceiling). |
| `docs/plans/performance.md` | **Active, after `bugs.md`** — compiler codegen performance; fix-forward series opening at 0.0.234 (renumbers if the bug pass takes the next versions). Supersedes the 2026-10-12 draft (its `100x`/`no register allocation` claims were wrong; see the plan's §2.3). |
| `docs/plans/lfm2-native-inference-perf.md` | **Active** — native LFM2 *speed* (CPU first, GPU when available). The *what* is `lfm2-native-inference-spec.md`. |
| `docs/plans/kernel-capability.md` | Kernel capability phases A-D done (0.0.233); D4 ring-3 + relocatable BSS base open, then ARM64 |
| `docs/plans/model-loader-features.md` | Loader: 18/18 phases complete |
| `docs/plans/loader-phase67.md` | Loader phase record 6.1/6.2/7.1/7.2 → 0.0.226-0.0.228 (referenced by `kernel-capability.md`) |
| `docs/plans/lfm2-native-inference-spec.md` | **What** to implement (stages 0-7) — the spec behind the engine |
| `docs/plans/arm64-backend.md` | AArch64 backend, deferred post-0.1.0 |

**Sequencing (standing instruction):** defects first (`bugs.md`), then performance (`performance.md`), then
model/inference speed (`lfm2-native-inference-perf.md`). Version numbers are allocated at release time, so the
series renumber as the bug pass consumes versions.

**Convention:** one file per topic, lowercase-hyphenated, **no dates in the filename**; plans live here and
nowhere else (`.hermes_plans/` is gitignored by `.gitignore:19:/*` and can never be committed —
`~/.hermes/plans/` is outside the repo). Work inside a plan is organised by **fix-forward version numbers**
(`VERSION`+1 per release, `RELEASE_CHECKLIST.md` §9) — not by invented stage labels.

## Roadmap accuracy — measured 2026-10-05

The roadmaps were **not** up to date. Measured against reality:

- `docs/status.json` was generated 2026-09-08 at the `0.0.020` era of its own
  version references and had not been regenerated since. It is now generated by
  `test_suites/scripts/verify_status.quanta` and tracked in CI as the
  `verify-status` gate.
- `docs/roadmap/quanta.md` last referenced version `0.0.169`; the tree is at
  `0.0.224`.
- `docs/SPEC.md` and `docs/MEMORY_SAFETY_ARGUMENT.md` are labelled `v0.0.169`.
- `docs/COMPILER_KNOWLEDGE.md` was labelled `0.0.190` and was generated from
  that source. Its generator had the version **hardcoded in the script**, so it
  kept re-emitting a stale label while silently describing newer source. Fixed:
  the generator now reads root `VERSION`.
- 97 domain files carry a total of 65 ✅ marks. Those marks are claims about
  planned modules, not measured test results, and the coverage tables in
  `quanta.md` report `done: 0` for 13 of 15 listed domains.
- `docs/roadmap/G6_SELF_COMPILE_BLOCKED.md` claimed G6 self-compile was
  structurally impossible. It is now GREEN in the `qobj` gate. Stale.

## Removed, and why

| Removed | Reason |
|---|---|
| 50 nested version trees (`compiler/0.0.X/0.0.Y/`) | `cp -r` recursed into existing dirs. Proven byte-identical duplicates of their parent's own `src`. Nothing read them. 369 MB. |
| 69 × `compiler/<old>/STATE.md` | Superseded by `WIP.md`. Referenced only by `RELEASE_CHECKLIST.md` prose and one code comment. |
| `docs/plans/*` (3 files) | Merged into `docs/NATIVE_INFERENCE.md` |
| `docs/roadmap/G5_*.md` (4 files) | Resolved findings, conclusions folded into `docs/NATIVE_INFERENCE.md` and the qobj gate notes |
| `docs/SI_CONTINUOUS.md`, `docs/SKILLS_DESIGN.md`, `docs/BRAIN_DESIGN.md` | Overlapping aspirational designs for the same subsystem; content folded into `docs/SELF_IMPROVEMENT.md` |
| `docs/QOBJ_PLAN.md`, `docs/QOBJ_ROADMAP.md` | Superseded by `docs/roadmap/QOBJ_FEATURE_COVERAGE.md` and the `qobj` gate |
| `docs/PERF_REGRESSION_pre_existing.md` | Finding folded into the gate history |
| `docs/plans/performance.md` (2026-10-12 draft) + `docs/plans/speedup-first.md` | Merged into the rewritten `docs/plans/performance.md`. The draft's two headline claims did not survive measurement (`100x slower than C` was a dead-code-elimination artefact in the C twin; `no register allocation` missed the 13-register pool with a LIFO victim policy). |
| `.hermes_plans/` (repo dir) | Gitignored by `/*` so nothing in it could ever be committed; the two plan files there were moved to `docs/plans/` and the directory removed. |
| `docs/plans/loader-6.1-multi-model.md` | Duplicate: its phase (6.1, 0.0.226) is a ✅ DONE section inside `docs/plans/loader-phase67.md`, which records 6.1/6.2/7.1/7.2. Nothing referenced it except the INDEX row it appeared in. |

## The one thing to read first

`compiler/0.0.224/WIP.md`. It states the measured current state of the compiler,
the root cause of the four trait failures it fixed, and the exact commands that
produced every number in it.