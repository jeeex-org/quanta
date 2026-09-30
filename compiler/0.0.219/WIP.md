# 0.0.218 — WIP

Created from 0.0.217 (STABLE). `VERSION` points here; this is the only tree
whose `bin/x86/qc` may be modified.

Gate: 15 GREEN / 0 RED. Caches: G5 7/7, G4 8/8, G4-transitive 8/8, G6 5/5.
Self-hosting fixed point: `gen1 = gen2 = gen3 = 78c7a61b78b6`. (`gen0`, the
previous compiler, is `64e8833b1668` and differs — correct, and it is the point:
it means the `--lib` change really did alter codegen rather than being a no-op.)

## `--lib <soname>` — depend on any shared library, not just libc

`--emit-dynamic` used to hardcode `libc.so.6` in three places in `elf.quanta`: the
`.dynstr` seed, its size, and the `DT_NEEDED` value. So a dynamic binary could
only ever need libc — enough to call `puts` and nothing else. There was no way to
depend on `libcuda.so.1`, `libm`, `libstdc++`, `libssl` or anything else, which is
the actual reason to want dynamic linking at all.

`--lib <soname>` is repeatable and additive. `libc.so.6` is seeded
unconditionally so `--emit-dynamic` alone behaves exactly as before.

```sh
qc --emit-dynamic --lib libm.so.6 prog.quanta out
```

Verified:

| case | result |
|---|---|
| `--emit-dynamic` alone | exit 42, `DT_NEEDED: libc.so.6` |
| `--lib libm.so.6` | exit 42, `DT_NEEDED: libm.so.6, libc.so.6` |
| two `--lib` | exit 42, three `DT_NEEDED` in order |
| `sqrt`/`pow` with `--lib libm.so.6` | resolves; exact f64 bit patterns back |
| `sqrt` with **no** `--lib` | loader reports `undefined symbol: sqrt` |

The last two are the ones that matter: it resolves when the library is declared
and correctly fails to when it is not, so `--lib` is doing real work rather than
decorating the binary.

### The bug that made it produce a library called "abs"

The extern-name fill cursor was `r64(g_dyn_ext + 112) + 11` — a hardcoded 11 for
"empty entry + `libc.so.6\0`", the only string table that existed when it was
written. With two or more `DT_NEEDED` entries, 11 lands in the middle of the
soname region, so the extern fill overwrote the sonames: `libm.so.6` was lost,
`abs` (the program's first extern symbol) was recorded as a library to load, and
the binary died at exec with

```
error while loading shared libraries: abs: cannot open shared object file
```

Fixed to read the cursor as it actually stands after the sonames are written
(`g_dyn_ext + 104`).

A second one, same family: each `DT_NEEDED`'s `d_un` was measured against
`g_dyn_ext + 112`, which is written *below* the loop that reads it, so every value
was a file offset near `0x117d` instead of a small `.dynstr` index. Measured
against the local `dynstr_off` instead.

### `extern "C"` still cannot be removed, and here is the measured reason

Two facts, both verified rather than assumed:

1. **`dlopen`/`dlsym` are libc functions, not syscalls.** There is no syscall
   number for them, so `syscall()` cannot reach them. (An earlier note here
   claimed `dlopen` worked natively on the strength of a `syscall(302, ...)`
   returning a handle; 302 is not a syscall number and the value returned was
   garbage. Corrected.)
2. **Quanta has no indirect call.** `f(x)` where `f` is a runtime value is a
   compile error — `call to undeclared function: f`. `closure_call` exists but
   takes a `[codeptr, env]` tuple and does `mov rdx,[rax]` to load the target, so
   handing it a bare `dlsym` address dereferences the callee's own first
   instructions and segfaults.

So native Quanta can *reach* a library but cannot *call into* one, and every
external library — CUDA's 600+ entry points included — is out of reach natively.
`extern "C"` is not a convenience layer; it is the only door out, and it costs a
build-time declaration of every symbol touched.

**The prerequisite is a first-class indirect call**, `f(args)` on a runtime
value. That has a chicken-and-egg worth naming: the first thing you would call
through it is `dlsym` itself. The IR is close — `IR_CLOSURE_CALL` already loads a
code pointer and sets up SysV registers; what is missing is accepting a bare
pointer rather than a tuple, plus some way to obtain that pointer without
`extern`. Not started; scope undecided.

Note that removing `extern "C"` would **not** remove the dynamic-linking codegen.
Any binary that does `dlopen` still needs libc and `ld.so`, so both `write_elf`
paths survive regardless. This is a decision about the source-language surface,
not about collapsing two execution models.

## Native is the default; extern is optional interop

Quanta builds anything natively. `extern "C"` and the dynamic-linker path are
**optional**, off by default, and never the way anything has to be written. This
is now enforced rather than asserted:

- **New gate stage `native`** (stage 1.4, and a promotion blocker). A program
  covering strings, byte indexing, NUL termination, raw syscalls, raw memory and
  the native allocator must compile in plain EXEC mode — no flags, no extern —
  run correctly, and come out statically linked. The rest of the gate tests
  extern paths; without this one, a gate made only of those would stay green
  while the native surface quietly rotted.
- **`extern "C"` in static EXEC mode is now a hard error**
  (`error: extern "C" needs --emit-dynamic`, exit 1). It used to emit a binary
  that segfaulted on the first call, which reads as "the user's program is
  broken". `--emit-obj` is exempt: it emits relocations the system linker
  resolves, and the multi-TU tests depend on that.

Test: `test_suites/codes/native_capability_test.quanta` — no `extern` in it, runs
to exit 42, `ldd` says "not a dynamic executable", and it does the same on the
gen3 self-compiled binary.

## `--emit-dynamic` with `extern "C"` — works, and stays optional

Opt-in interop, working. Verified on the installed binary *and* gen3:

| case                                   | result |
|----------------------------------------|--------|
| 1 extern (`puts`)                      | exit 42 |
| 3 externs (`puts`, `strlen`, `abs`)    | exit 7  |
| `--emit-dynamic`, no externs           | exit 42 |
| `ldd` on the output                    | resolves `libc.so.6` |
| static, no externs                     | exit 42 (default path) |
| static with `extern "C"`               | hard error, exit 1 |

Test: `test_suites/codes/dyn_extern_test.quanta`.

### What was wrong

Nine distinct defects in the dynamic-ELF path. Most share one root cause: **this
compiler's bootstrap register reuse loses `let` values declared and read far
apart**, so anything crossing a long gap has to live in `g_dyn_ext`. The files
already said this for the cursors; the fix was to extend the same treatment to
every region offset, vaddr and size in the block.

1. `.dynsym` NULL symbol written with ELF32 field offsets (st_name as `w64` at 0,
   st_info at 8) — the loader saw a garbage symbol table.
2. `.dynsym` written at the region start, overwriting the NULL symbol, so the
   extern landed at index 0 and every relocation read "bad symbol index 1".
3. `st_name` computed from the `.got.plt` cursor instead of the `.dynstr` cursor —
   every symbol named the empty string at `.dynstr[0]`.
4. `.dynstr`/`.dynsym`/`.hash` placed by walking the `dyn_ptr` cursor, which is
   stale by the time those writes happen. The symbol landed 0x18 bytes past the
   end of `.dynstr`, inside `.hash`.
5. `hash_size` was `8 + 4*2 + 4*n` — buckets counted as chain entries. Should be
   `8 + 8 + 4*n`. Every region after `.hash` was 8 bytes late, so `DT_HASH`
   pointed into `.gnu.hash`.
6. **PLT0**: `jmp`'s disp32 written at `+10` instead of `+8`, and the padding
   `90 90` then overwrote two bytes of it. `ff 25 0000e2ff` — a jump 1.9MB past
   the GOT.
7. **Per-symbol PLT stub**: `jmp`'s disp32 computed from the stub's *file* offset
   where a *vaddr* is required, and the `90 90` padding overwrote the top two
   bytes of the `e9` back-jump to PLT0.
8. **The `.got.plt` lazy-binding slot** stored a file offset where a vaddr is
   required — the loader's resolution was written back over a random spot in the
   file image.
9. The pushed relocation index was the stub's *index* (0) where glibc's
   `_dl_runtime_resolve` expects the byte *offset* into `.rela.plt` (i*24).

The `.got`/`.got.plt` reserved slot 0 also held the block's unaligned base
rather than the `.dynamic` vaddr, and `dynamic_size` reserved 14 entries while 15
were written, so a stray `dyn_idx` bump truncated the table the loader reads.

### Structural changes

- **`publish_dyn_layout()`** — new, in `elf.quanta`. Writes every region offset
  and vaddr to `g_dyn_ext`. Takes **no parameters**: it was six, and the register
  allocator did not keep them (`gsz` came back wrong, placing `.got.plt` on top
  of `.got`). The caller now writes the inputs to `g_dyn_ext + 304..` first.
- **`exec_extern_patches()`** — new, in `entry.quanta`. The ty==3 extern CALL
  patch loop, lifted out of the main patch loop and called from `write_elf` after
  the layout is final. It previously recomputed the whole layout from independent
  guesses (`dynstr_size = 200` against a real 16, `hash_size = 32` against 20,
  `got_size = 8*(n+3)` against `24+n*8`, no 8-byte round-up) **and** ran before
  `write_elf` published anything, so it patched against zeros. Then it ran before
  the string-literal byte count was final and read it 0x18 low.
- **`g_elf_ht` deleted.** It was set by `write_elf` and read by the patch loop
  that runs before it, so it was always 0. The header size is a constant in
  dynamic mode: `64 + 56*6`.

### Two deliberate non-defaults

- **`DT_FLAGS = DF_BIND_NOW`** rather than lazy binding. glibc's lazy resolver
  assumes a `.plt` shape this emitter does not produce: it computed the symbol
  name as `.dynstr + 0x8000` and read unmapped memory, killing the process inside
  `_dl_lookup_symbol_x` on the first call. Binding up front removes that path.
  A `-z now` binary behaves identically, so this is ordinary, not a workaround.
- **`DT_FLAGS_1 = DF_1_NOW` removed.** It made glibc bind eagerly *and* skip
  initialising the three reserved `.got.plt` slots, so PLT0 pushed and jumped
  through two zero slots.
- **`.gnu.hash` reduced to a valid 20-byte table** (`nbuckets=1, symndx=1,
  maskwords=0, shift2=0, bucket[0]=1`). The old 48-byte version was `symndx=0`
  with no bloom words — malformed. It is not referenced by `DT_GNU_HASH`, so it is
  inert either way, but it should not be garbage.

### Also fixed here

- `LOAD_RW` is now `R|W|X` in dynamic mode. `.plt` is code inside that segment;
  without X the first extern call died with `SEGV_ACCERR` on the stub.
- `scripts/selfhost_test.sh` read `V=0.0.217` hardcoded, so it always tested the
  *previous* stable tree no matter what was installed — a full-gate PASS against
  a binary that is not the one under test. Now reads `VERSION` and honours
  `QC=`.

### Note for future work

The root cause throughout is `codegen.quanta`/`funcscan.quanta` losing long-lived
locals, not any individual site in `write_elf`. This change routes around it with
globals. The real fix belongs in the register allocator; until then, any new
value that has to survive more than a few dozen lines in one function must be
parked in a global with a comment saying which slot is which.
