# 0.0.237 — WIP · **PROMOTED** (gate fully green, 221/221, STDLIB 108/108)

**Lever: A1b — block bindings are popped. An inner `let` no longer rebinds the
enclosing variable's storage.** One lever, one version, one mechanism.

## What landed

- `src/x86/helpers.quanta` — the mechanism: `a1b_enter()`/`a1b_leave(wm)` plus the
  binding-stack watermark, `varc_hi` (closure-snapshot high-water mark),
  `vars_dead` (warn instrument), `a1b_check`/`a1b_warn`/`a1b_line`/`a1b_int`.
  `vadd()` (line 578) maintains `varc_hi` and clears `vars_dead`; `vfind()` (line
  721) consults the dead check; `vclr()` (line 764) resets both per function.
- `src/x86/parse.quanta` — the watermark is taken at **every block entry point**
  and given back at its **single exit**: `parse_block()` (156 / 455), the
  `for … in` body (1649 / 1699, an inline copy of parse_block's statement loop),
  and the `catch` binder (2417 / 2429). The redundant `vr = zr` at the end of the
  sized-array `let` path was deleted (1329).
- `src/x86/method.quanta` — the two other resolution paths that used to lean on the
  leak: the bare `Some/Ok/Err` payload binding (778) and the enum tuple/unit
  `vr` (1581). `a1b_check` is also called from the three hand-inlined copies of
  `vfind` (method.quanta `self`/field resolution and the fn-typed-param indirect
  call) so the warn instrument cannot under-report.
- `src/x86/globals.quanta` — `clo_scope_save()` (1343) snapshots `varc_hi`, not
  `varc`, so a closure created inside a block can still capture that block's
  variables.
- `src/x86/{lexer,entry,funcscan}.quanta` — the four remaining leak-dependent
  sites (migration table below).
- `lib/std/gguf.quanta` — six dequant dispatch arms that used `raw` without ever
  allocating it (see "The stdlib defect the fix uncovered"). **This file is not in
  this commit**: the A9 unit found it dirty in the shared checkout and committed it
  verbatim as `cc7ff74b` ("preserved, not authored here") rather than revert a live
  fix or sweep it into its own `git add` — the change it carries is this version's,
  every comment in it is `A1b:`-labelled, and `git show cc7ff74b` reproduces this
  lever's edit exactly. The same six-branch fix is applied to this version's own
  snapshot copy, `compiler/0.0.237/lib/std/gguf.quanta`, which IS in this commit.
- `test_suites/codes/a1b_*_test.quanta` ×8 + 8 rows in `test_suites/EXPECTED.tsv`.
- `compiler/0.0.237/bin/x86/qc` — the promoted binary, md5
  `dca6b4ab229f17b0b8e2d7e29874e401`.

## The defect

`vars` is a per-function stack of bindings and `vfind()` scans it NEWEST-first.
Nothing ever popped a block's bindings, so a `let` inside a block stayed the
resolution target for the rest of the enclosing function:

```quanta
fn main() { let p = 11
            if 1 == 1 { let p = 99 }
            print(p) }         // 0.0.236: 99    0.0.237: 11
```

The failure mode is a **store into a different variable's storage** — defect A1's
shape (a `let fi` inside `ci_func` shadowed the `fi` parameter and `IR_CAPREAD`
stored through a wild offset → SIGSEGV). With raw pointers, `mem_alloc`, FFI,
`asm!`, MMIO and a ring-0 target that is a memory-corruption primitive, and
SPEC.md §4.2 requires out-of-contract operations to fail secure rather than
corrupt.

## Mechanism (as implemented)

1. **Watermark.** Every block entry point saves `varc`; every exit restores it
   (`a1b_leave`, helpers.quanta:603). The restore is an index truncation — a
   resize, not a copy — so name lookup cost does not grow with nesting depth and
   popping a block is O(bindings in that block), not O(function). The bindings
   live on a stack, so truncating `varc` IS the pop; nothing has to be scanned.
2. **Symmetry on every exit path.** Every block-entry point has exactly ONE exit
   (`parse_block` returns at one place; the `for … in` body at another; the catch
   binder at a third), and the paths that leave a block early at RUNTIME —
   `break`, `continue`, `return` — do not bypass it: they emit their jump and
   return to the block's parse loop, so the block is still fully parsed and still
   reaches `a1b_leave`. `defer_replay_range()` runs BEFORE the restore, so a
   replayed `defer` still sees the block's bindings and any binding the replay
   creates dies with the block. A trap/error path that aborts the compile
   (`had_error`, `emit_ovf`) parses nothing further, so there is no table state to
   leave inconsistent — the build has already failed, which is fail-closed.
   Verified by probe: `break`/`continue`/`return` rows in
   `a1b_block_scope_loop_exit_test` / `a1b_block_scope_return_test`.
3. **Companion tables.** `vars_own` (the ownership tag at the same slot) and
   `vars_dead` are re-written/cleared by `vadd`, so a reused slot cannot carry
   stale state, and `vclr` sweeps `vars_dead` per function as belt-and-braces.
   The **per-vreg** tables (`vfloat`, `vreg_is_str`, `vreg_struct`, `vreg_is_big`,
   `vreg_clo`, `vreg_type`) are deliberately NOT touched, and that is the safe
   direction: a vreg index is never reused inside a function (`nv()` only ever
   increments `vreg_n`) and `nv()` writes every per-vreg tag AT allocation
   (features.quanta:305-322), so a vreg released by a block cannot carry a tag
   into a later binding. The stale-tag class this project has hit twice is the
   reverse one — a NAME resolving to a binding whose vreg holds a different type —
   and block scoping is what closes it: measured, `let x = 1.5` inside a block no
   longer retags the outer integer `x`, which on 0.0.236 made `print(x)` after the
   block a hard compile error ("print on an f64", defect A2's guard)
   → `a1b_block_scope_float_tag_test`.
4. **Lookup is not pessimised.** `vfind` still scans from `varc-1` and returns on
   the first match; the only addition on that path is one mode-guarded table read
   in `a1b_check`. Measured wall clock, self-build of the compiler's own source,
   3 runs each: 0.0.236 binary 5.64 s (median) vs 0.0.237 binary 5.24 s on the new
   source, and 5.60 s vs 3.85 s on the unmodified 0.0.236 source — the mechanism is
   not slower, and is measurably faster, on a box whose load the numbers share.
   The shorter live table shortens the not-found scans that fall through to
   `gfind`/`findfn`. (Caveat: single box, load average ~14, medians of 3.)
   Block scoping is also what later allows home slots to be REUSED instead of one
   slot per vreg — the same lever as A4 (1104-byte frames) — but that reuse is NOT
   done here; this version only makes the live ranges non-overlapping.
5. **Fail closed.** With the watermark in place a use after its block resolves to
   the newest LIVE binding or becomes an `undeclared variable` compile error
   through the existing located-error path (no new error code, so the message
   style is already the tree's) → `a1b_block_scope_shadow_test` prints 11 where
   0.0.236 printed 99.

`a1b_mode` selects the behaviour: **2 = fail-closed (SHIPPED)**, 1 = warn (see
below), 0 = legacy silent leak. Setting it to 1 rebuilds the measurement
instrument — it changes no semantics, it only reports — so the blast-radius table
below is reproducible from this tree:

```bash
cd <tree> && ulimit -c 0 -v 8000000
sed -i 's/^let a1b_mode = 2$/let a1b_mode = 1/' compiler/0.0.237/src/x86/helpers.quanta
compiler/0.0.236/bin/x86/qc compiler/0.0.237/src/x86/main.quanta /tmp/q237warn.bin   # the WARN instrument
/tmp/q237warn.bin <any>.quanta /tmp/out 2>&1 | grep '^A1B '   # A1B <cat> <merged-line> <name>
```

`A1B 1 <line> <name>` = a LIVE binding of the same name still exists lower in the
stack, so the site compiles today but would resolve to a DIFFERENT vreg once the
block is popped — the silent, storage-changing case (A1's shape). `A1B 2` =
nothing left to resolve to, so the site becomes an `undeclared variable` error.
Merged-stream lines map back to `file:line` with a replica of `expand_includes`
(the mapper used for the table below validated 13/13 sites against the source
text of the identifier each one names).

## Blast radius (WARN-FIRST phase, measured)

Method: the WARN instrument compiled **every** `.quanta` in the compiler's own
source, `lib/std/*` (165), `test_suites/codes/*` (619), `benchmarks/*` (37),
`tools/*`, `scripts/*`, `tests/*`, `temp/*` — 1052 compile units — and every
`A1B` line was mapped to `file:line` and deduped by (file, line, name).

| file | distinct sites | names | of which silent (cat 1) |
|---|---|---|---|
| `lib/std/gguf.quanta` | 12 | `raw` | 0 |
| `compiler/0.0.237/src/x86/method.quanta` | 6 | `a`, `vr` | 0 |
| `compiler/0.0.237/src/x86/entry.quanta` | 3 | `init_call`, `is_novf`, `stub_call` | 0 |
| `compiler/0.0.237/src/x86/lexer.quanta` | 2 | `nlen`, `sc` | **1** (`nlen`) |
| `compiler/0.0.237/src/x86/funcscan.quanta` | 1 | `rp` | 0 |
| `compiler/0.0.237/src/x86/parse.quanta` | 1 | `zr` | 0 |
| `tools/fuzz/seeds/seed_003.quanta` | 1 | `ovf_trap` | 0 |
| **total** | **26** | | **1** |
| `test_suites/codes/*` (619 files) | 0 | | |
| `benchmarks/*` (37) | 0 | | |
| `lib/std/*` other than gguf (164) | 0 | | |

Raw instrument output: 423 `A1B` lines over 1052 units; 26 distinct sites after
dedupe; **0 mapping failures** (each mapped line was checked to contain the
identifier the message names). The seed is a frozen copy of an older `main()`
inside the fuzz corpus and is deliberately left alone; its site is the one the
`git`-tracked compiler fixed at entry.quanta:290.

So the honest figure for this tree is **26 sites in 6 files**, of which exactly
one was the silent (storage-changing) kind — not the "everything is broken"
picture an unwarned flip would have produced, and not zero either.

## Migration (phase B) — every site, and what was done

| site (before) | transformation | why it is semantics-preserving |
|---|---|---|
| `entry.quanta` `is_novf` (in the `else` of the `--overflow-trap` test, read ~60 lines later) | hoisted to the level of the sibling flags `is_obj`/`is_dyn`/`is_qobj` (the shape the rest of that argv loop uses) | the two strings are mutually exclusive, so evaluating both is a no-op |
| `entry.quanta` `init_call`, `stub_call` (recorded inside the startup-stub block, read at the ELF patch) | declared `= 0` at the block's own level; the assignments stay exactly where they were | same value on the path that has a stub; the patch itself is now guarded by the same condition as the stub, so the `--no-start` path writes nothing instead of writing through an unassigned cell |
| `funcscan.quanta` `rp` (declared inside `if mc < 32`, read at `cp = rp`) | hoisted to the arm's level | initialiser is `cp+2` and `cp` does not change inside the arm; the `mc >= 32` path now reads `cp+2` instead of an unassigned cell |
| `lexer.quanta` `nlen` (**silent**, cat 1) | the float arm's own digit count renamed to `fnlen` | the TT_NUM call after the arm can no longer resolve to the float arm's cell; it now reads the integer arm's `nlen = p - sp`, which is what the author wrote (the two sites are now distinct names instead of relying on shadow resolution) |
| `lexer.quanta` `sc` (**not declared in that scope at all**) | the `$$(…)` raw-command arm captures `let sc = c` before it advances — the token's start column, the convention every other `stok()` in that lexer follows | the old value was whatever identifier had been lexed last (a leaked binding from another arm); the new value is the token's own column. **Ambiguous site** — see below |
| `method.quanta` `a` ×3 (bare `Some`/`Ok`/`Err` payload: `let a` in each arm, used after) | `let a = -1` before the arm; the payload arm assigns `a = parse_expr()` | identical value (−1, or the parsed payload); the old code is a real 0.0.236 miscompile (below) |
| `method.quanta` `vr` (tuple/unit enum arms each `let vr = nv()`, used after) | `let vr = nv()` before the branch; `IR_TALLOC` stays in each arm | the vreg NUMBER and the allocation order are unchanged, and `IR_TALLOC` stays where it was in the IR stream |
| `parse.quanta` `vr = zr` (redundant: both arms above already assign `vr = zr`) | deleted; the comment moved above the if/else | dead in both arms; `zr` is the arm's freshly allocated vreg and has no meaning outside it |
| `lib/std/gguf.quanta` `raw` ×12 (6 dequant arms used `raw` without ever allocating it) | each arm now fetches its own bytes, exactly like the 12 sibling arms | see below: the old code passed an uninitialised pointer to the dequant routine and then to `mem_free` |

**Ambiguous sites requiring review (2):**

1. `lexer.quanta:516` (`$$(cmd)` raw-command token's column field). The old value
   was a leaked binding's, i.e. arbitrary; the sibling `$$(…)` string/bracket arm
   passes the column AFTER `$$(` while the convention elsewhere in that lexer is
   the token's START column. I applied the token-start convention. The column
   field is only read by `funcscan`'s token-rewriting passes, never by codegen, so
   this cannot change emitted code either way — but the author may prefer the
   sibling arm's choice.
2. `entry.quanta:1199/1213` (the guarded ELF patch). On `--no-start` (a secondary
   TU, i.e. no startup stub) the old code patched through an unassigned cell's
   offset; it now patches nothing. This is a deliberate, documented behaviour
   change on a path no gate row covers, chosen because SPEC.md §4.2 requires
   failing secure rather than corrupting. Reviewing whether `--no-start` should
   reach that code at all is left to the author.

## The 0.0.236 defects the fix repairs (not just hygiene)

All measured with the golden `compiler/0.0.236/bin/x86/qc` vs the promoted
`compiler/0.0.237/bin/x86/qc`, same source:

| program | 0.0.236 | 0.0.237 |
|---|---|---|
| `fn main() { let p = 11 let a = 1 if a == 1 { let p = 99 } exit(p) }` | `99` | `11` |
| shadow probe via `while` / `for` / `for…in` / `loop` / bare block / `unsafe` / `try` body (7 more forms) | 99 / 77 / 55 / 33 / 22 (the inner value) | 11 (the outer binding) |
| `enum Shape { Point, Rect(i64,i64) }` + `Shape::Rect(3,4)` + match | **compiler SIGSEGV, rc=139, 3/3 runs** | compiles, rc=42 |
| bare `Some/None/Ok/Err` with payloads in ONE function (`Ok(7)` read via match) | `s3 = 50` (the wrong payload: 5, from the `Some(5)` cell) | `s3 = 70` |
| `let x = 1.5` inside a block shadowing an outer int, then `print(x)` | **compile error** ("print on an f64": the block's float tag hijacked the outer name) | `3`, rc=42 |
| `fn g(n) { let r = 1 if n == 0 { let r = 42 return r } return r }` (`g(1)`) | returns a stale `r` (measured exit 126) | returns 1 (exit 44 for the whole probe) |
| `try { throw 1 } catch e { print(e) }` then `exit(e)` | compiles, prints garbage (4194985) | **compile error** (`undeclared variable: e`) — fail-closed |
| every other block form (`while` body, `for` body, `loop`, bare block, `unsafe`, `try` body) with an outer `p = 11` | `99` — the leak | `11` |

## The stdlib defect the fix uncovered

`lib/std/gguf.quanta`'s dequant dispatch has 18 `else if dtype == …` arms. Twelve
of them open with

```quanta
        let n = gguf_tensor_nbytes(idx)
        let raw = mem_alloc(n)
        gguf_read_bytes(offset, raw, n)
```

and six (`dtype` 3/6/7/10/11/15 = Q4_1, Q5_0, Q5_1, Q2_K, Q3_K, Q8_K) did not —
they called `dequant_q4_1(raw, …)` and `mem_free(raw)` on a name that resolved to
the binding leaked from the `dtype == 40` arm. At run time that arm never executes
for those dtypes, so the pointer was **uninitialised**: a wild read inside the
dequant routine and then `mem_free` on a wild pointer (arbitrary free on an
allocator that recycles its free list). With block-scoped bindings the same code
is a compile error, which is what made the missing allocation visible; the fix
adds the three lines each arm needs, mirroring the twelve siblings. This is the
A1b defect causing memory corruption rather than a wrong number — the argument for
treating the leak as a security defect, not a matter of taste.

## Gate

Run with `bash test_suites/scripts/run_tests.sh` on the tree this commit records
(`cc7ff74b` + this commit's files, `VERSION` = 0.0.237, `QC` = the promoted
binary):

```
=== Results: 222/222 pass, 0 fail (incl. 0 compile-fail) [rows: EXPECTED.tsv] ===
  STDLIB: 108/108 GREEN
=== GATE SUMMARY ===
  functional GREEN, native GREEN, float-oper GREEN, float-builtin GREEN,
  float-return GREEN, float-operpath GREEN, extern-c GREEN, extern-ld GREEN,
  security GREEN, performance GREEN, valgrind GREEN, fuzz GREEN,
  differential GREEN, generics GREEN, stdlib GREEN, multi-tu GREEN,
  gguf-corrupt GREEN, verify-status GREEN, qobj GREEN, output-path GREEN,
  naked GREEN, asm-assembler GREEN, bare-metal GREEN, float-print GREEN
EXIT=0
```

Baseline measured before this lever, same tree at 0.0.236 with the golden as
`QC`: 213/213, STDLIB 108/108, all stages GREEN, exit 0. The core row count is
214 at the parent of this commit (213 plus the A9 unit's threaded-pool row), so
the 222 here is 214 core + the 8 rows below — no existing row changed rc, and no
row was removed. An earlier run of this same content in an isolated worktree
(9bd49b67 + this lever only) was also fully green at 221/221, which is why the
numbers can be attributed to this commit rather than to a neighbour's tree.

New rows, all RED before and GREEN after (rc the harness compares):

| row | 0.0.236 | 0.0.237 |
|---|---|---|
| `a1b_block_scope_shadow_test` | rc=1 | rc=42 |
| `a1b_block_scope_loop_exit_test` (break/continue/nested/loop) | rc=1 | rc=42 |
| `a1b_block_scope_return_test` (return from inside a block) | rc=2 | rc=42 |
| `a1b_block_scope_float_tag_test` (per-vreg tag not inherited) | compile fail | rc=42 |
| `a1b_enum_tuple_payload_test` (tuple-payload enum) | compiler SIGSEGV | rc=42 |
| `a1b_multi_ctor_payload_test` (several bare ctors in one fn) | rc=3 | rc=42 |
| `a1b_block_scope_init_per_iteration_test` | rc=42 | rc=42 |
| `a1b_block_scope_try_catch_test` | rc=42 | rc=42 |

The last two are deliberately not red-first: the first is the guard for the
semantics a previous attempt broke (`let x = f()` inside a loop must initialise
EVERY iteration — a hoisted declaration initialises once; measured, the loop sums
60 and 30 and the re-zeroed accumulator is 7), and the second is the guard that
scoping the `catch` binder did not break `try/catch` itself.

## Self-hosting

Three generations, byte-identical (md5 of the promoted binary, of a rebuild by the
golden, and of the generations it produces):

```
dca6b4ab229f17b0b8e2d7e29874e401  q237_gen1.bin   (built by 0.0.236 golden)
dca6b4ab229f17b0b8e2d7e29874e401  q237_gen2.bin   (built by gen1)
dca6b4ab229f17b0b8e2d7e29874e401  q237_gen3.bin   (built by gen2)
distinct: 1
```

The committed golden `compiler/0.0.236/bin/x86/qc` rebuilds the same source to the
same md5, and the promoted `compiler/0.0.237/bin/x86/qc` is that md5.

## State

- Built with the golden: `ulimit -c 0 -v 8000000; compiler/0.0.236/bin/x86/qc
  compiler/0.0.237/src/x86/main.quanta /tmp/q237.bin` → rc 0, md5 above. The
  committed binary is byte-identical to a rebuild by the golden and to its own
  second and third generation.
- Gate: GREEN, 222/222 (214 core + 8 new), STDLIB 108/108, EXIT=0. PROMOTE.
- The 8 `EXPECTED.tsv` rows and their 8 `test_suites/codes/*.quanta` sources are
  in the SAME commit: a row whose source is untracked is a guaranteed
  compile-failure in a clean checkout. Verified after committing by checking the
  commit out into a fresh worktree and compiling every row there.
- Work was first done in a dedicated worktree (`v0.0.237-a1b-block-scope`) because
  the shared checkout carried the A9 unit's in-flight `lib/std/lfm2_*` edits; the
  gate was measured there at 221/221 (this lever only), then re-measured here at
  222/222 once A9's work was committed and the shared checkout was clean again.

## Follow-up queued behind this version (not part of this lever)

Measured by the A9 unit, recorded here so the next unit starts from the
measurement rather than re-deriving it: the threaded matvec pool fixed the
per-call thread leak (clones per forward 2329 → 20; parallel decode now 70.5 s
s/token at 1 worker, 16.7 at 8, 12.8 at 20), but a residual ~20 MB per forward
remains because **`thread_join` never `unmap`s the 1 MiB child stack**. The
complete fix is an emitter `munmap` in `thread_join` — a 0.0.237-family change,
deliberately NOT taken here (one lever per version; this version's lever is
binding scope).
