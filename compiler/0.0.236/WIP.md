# 0.0.236 — WIP · **PROMOTED** (gate fully green, 212/212)

**Lever: A6 + A7, one fix — an untyped parameter takes the type of the argument the caller passes.**

## What landed

- `src/x86/funcscan.quanta`: new pass **`scan_call_types()`** (plus helpers `sct_args`, `sct_mark`,
  `sct_param_ev`, `sct_ret_ev`, `sct_nm_eq`), called from `entry.quanta` right after `scan_retstr()`.
- `src/x86/globals.quanta`: four scratch tables for it (`sct_tok`, `sct_fi`, `sct_stk`, `sct_sdp`).
- `lib/std/code_synthesizer.quanta` (and its `compiler/0.0.236/lib/std/` copy): the memory-safety and
  correctness fixes the A6/A7 fix uncovered — see "The uncovered stdlib defect" below.
- `lib/std/code_synthesizer.quanta` is `lib/std` and rule #12 defers stdlib to the stdlib stage, so the
  exception is recorded here explicitly rather than silently: this was not a stdlib feature change, it is the
  bug the promoted core fix exposed, and the gate cannot be green without it.

`scan_call_float()` already inferred a float parameter from a call site, but **only from a float
LITERAL**. That leaves the forwarding case dead:

    fn qmult(x) -> f64 { let y = x * (2.0/3.14159...) ... }   // x UNTYPED
    fn reduce(x) -> f64 { ... let nf = qmult(x) ... }         // x is an IDENTIFIER here
    reduce(0.5)                                               // reduces param marked, qmult's not

and that is the whole of A6 — including the "a dead `qmult(0.5)` fixes it" puzzle: that unreachable
call has the literal the old rule needs, and this pass reads the TOKEN stream, so reachability never
enters into it. A7 (string) had **no call-site scan at all**: `fn_parstr` was written only from a
declared `: str` signature (`funcscan.quanta:319`) and from cached-import metadata
(`objfmt.quanta:1252`) — verified by grep, no string analogue existed.

New rule (monotone fixpoint over the token stream, run to a fixed point because a mark made in one
round is the evidence a later call site needs): for every call `name(args)` inside function `g`,
argument `k` carries a type when

1. it contains a float/string literal at argument depth, or
2. it names a parameter of `g` whose `fn_parflt`/`fn_parstr` slot is already set, or
3. it is a call to a function whose `fn_retflt`/`fn_retstr` flag is set,

and then parameter `k` of every top-level function called `name` is marked float/string — under
`scan_call_float`'s existing guard (never overwrite a slot with a declared type) and only when a slot
actually flips, so integer call sites are untouched and the fixpoint terminates.

The enclosing function `g` is resolved with a **brace stack over a body-token-ordered function list**,
not from a name: "this identifier is spelled like some function's float parameter" is not evidence, and
a wrongly-float parameter is the same miscompile class the fix removes (movq over an integer, or
cvtsi2sd over an f64 bit pattern). Method calls (`s.push(x)`) are skipped (a preceding `.`).

## The uncovered stdlib defect (fixed in the same change)

The A6/A7 fix flips exactly two slots in `std_code_synthesizer_const_test`'s code (its module's `main`
is the entry, and `synthesize_all` p0 / `register_pattern` p0, both string, are the slots). Before the fix
`file_open("gap_specs.json")` on the untyped path parameter returned `-2` and the module returned 0
immediately; after the fix the path is live and `lib/std/code_synthesizer.quanta` really runs. It was
broken on its own — three defects, all fixed:

| defect | before | after |
|---|---|---|
| `read(2)` into a 2 MB mapping | `mmap(2097152)` then `file_read(fd, buf+8, 16777216)` — `gap_specs.json` is 2,290,042 B, so ~193 KB was written past the end of the mapping (SIGBUS / hang) | buffer sized from the file (`file_size()` = lseek SEEK_END): `mmap(fsz+16)`, `file_read(fd, buf+8, fsz)`, read length clamped to `fsz` |
| `sanitize_ident()` returned a headerless buffer | bytes written at `out+0` with no length header, but every caller used `len(out)` and `mem_load8(out+8+i)` — `len()` read the first 8 ASCII bytes as an int (~7.6e18 for "accounting") and the copy loops ran off the mapping | returns a real Quanta string (`mem_store(out, len_n)`, bytes at `out+8`); the three `file_write` calls pass `clean_x + 8` |
| `file_open(out_path, 577)` was 2-arg | with O_CREAT the mode comes from R10 (garbage), so files were created mode 000 and every later run's O_TRUNC open-for-write got EACCES — measured: run 1 -> 9,026 modules, runs 2..n -> 0 | `file_open(out_path, 577, 420)` (0o644) |

Output is also staged under a CWD-relative **`synth_out/`** (created by the module, git-ignored) instead
of the hard-coded `lib/std/`: a gate run executes this code, and the old target rewrote 9,026 module stubs
straight into the tracked tree on every run.

## Verification (raw)

| check | 0.0.235 golden | 0.0.236 |
|---|---|---|
| A6 repro `/tmp/g9/iso_B.quanta` | `-4336984033343832063` | **`4602678819172646912`** |
| A7 repro `tests/a7_untyped_str_param_defect.quanta` | `11093937761109393744` / `11093938081109393840` | **`untyped tag: GLOBAL`** / **`untyped lit: TEXT`** |
| `tests/f64_call_order_defect.quanta` (already correct) | `0` then `4602678819172646912` | `0` then `4602678819172646912` |
| gate row `codes/f64_call_order_test.quanta` | compile 0, **run rc=1** | compile 0, **run rc=0** |
| `codes/embedding_test.quanta` (must not regress) | run rc=0 | run rc=0 (`EMBEDDING EXTRACTION PASS`) |
| §2 drift: 0.0.235 golden rebuilds 0.0.236 src | — | **IDENTICAL**, md5 `203e0d772ca38e903ad27c921645d10a` |
| §2b `scripts/selfhost_consistency.sh` | — | **SELFHOST: 7/7**, rc 0 |
| §3 fixpoint, 3 generations | — | **`203e0d772ca38e903ad27c921645d10a`**, 3/3 identical, == the installed binary, distinct = 1 |
| §4 smoke (`exit(f2i(fmul(fadd(i2f(2),i2f(3)), i2f(4))))`) | — | **rc=20** |
| gate row `std_code_synthesizer_const_test.quanta` | — | **rc=0 in 9/9 consecutive runs** (`Generated modules: 9026` each) |
| STDLIB suite (108 rows) | GREEN | **STDLIB: 108/108 GREEN** |

One change fixed both A6 and A7: the string evidence is the same rule on `fn_parstr`/`vreg_is_str`
(which `entry.quanta:893` turns into the parameter's tag at parse time). Measured directly, an untyped
parameter used as a path: `file_open(p, 0)` returned **-2** on 0.0.235 and **3** on 0.0.236, while
`fn p: str` returns 3 on both.

### Red-first for the buffer defect, on the PRISTINE compiler

The original module with only its parameter typed `: str` and its buffer enlarged (A6/A7 out of the
picture), compiled by the **untouched 0.0.235 golden**, over nine runs:

    rc=0 x3   rc=124 (timeout) x4   rc=135 (SIGBUS) x2

Flaky, and not the expected 0 — the module was broken before this change, which is why the row was green
only because A6/A7 short-circuited it. (An earlier session recorded rc=0 x3 / rc=124 x2 / rc=135 x4 on
the same shape; the re-measurement above is the authority.)

## Gate (promoted tree, official command, this environment)

    QC=./compiler/0.0.236/bin/x86/qc bash test_suites/scripts/run_tests.sh   -> rc=0
    === Results: 212/212 pass, 0 fail (incl. 0 compile-fail) ===

Every layer GREEN (functional, native, float-oper, float-builtin, float-return, float-operpath,
extern-c, extern-ld, security, performance, valgrind, fuzz, differential, generics, stdlib, multi-tu,
gguf-corrupt, verify-status, qobj, output-path, naked, asm-assembler, bare-metal, float-print).
`STDLIB: 108/108 GREEN`.

    bash scripts/verify-release.sh 0.0.236 0.0.235   -> 14 passed, 0 failed

(The earlier 821-row figures this file used to carry are obsolete: the gate row list was corrected
upstream to 212 rows — 605 no-op `std_programming_language_*` rows and a dangling `recv_loop_test` row
removed, the duplicated `std_code_synthesizer_const_test` row deduped. Do not quote them.)

## Promotion record

- Promoted **0.0.236**; `VERSION` bumped from `0.0.235`. `compiler/0.0.236/bin/x86/qc` is the golden and
  equals the fixpoint md5 `203e0d772ca38e903ad27c921645d10a`.
- `0.0.235` is now the frozen baseline: its `src` rebuilds to its committed md5 `7e48d93cfaa822c0eb9bde9565b1cda3`
  bit-for-bit (`verify-release.sh` pass).
- Added gate row `std_code_synthesizer_const_test.quanta` stays in `EXPECTED.tsv` (1 row) and passes.
- Not done, deliberately: promoting `tests/a7_untyped_str_param_defect.quanta` into a gate row alongside
  `codes/f64_call_order_test.quanta`. The A6 row is gated; the A7 (string) half has no gate row yet. Left
  as a follow-up so this promotion did not change the row list under a reviewed gate.
