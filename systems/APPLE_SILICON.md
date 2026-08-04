# Building Quanta for Apple Silicon (macOS ARM64)

This document explains how to compile the Quanta compiler so that it produces
mach‑o binaries that run natively on Apple Silicon (M1/M2/M3…) Macs.
It assumes you are working inside the Quanta source tree and following the
project’s **fix‑forward** workflow (all active changes go into a
`*-wip.quanta` file; only after passing the self‑host check and the full test
suite may the result be promoted to the next stable release).

---

## Prerequisites

1. **A macOS host** – either a physical Apple Silicon Mac or a macOS CI runner
   (GitHub Actions `macos-14`, GitLab, Azure Pipelines, or a cloud‑mac provider
   such as MacStadium, AWS Mac instances, etc.).

2. **Xcode Command‑Line Tools** (or the full Xcode app).  
   Install them with:
   ```bash
   xcode-select --install
   ```
   This provides:
   * `clang` targeting `arm64-apple-darwin<version>`
   * The macOS SDK (headers & stub libraries)
   * `ld64` (the Mach‑O linker)
   * `make` (or you can install `ninja` via Homebrew if you prefer).

3. **Optional – Homebrew** (for extra utilities):
   ```bash
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   brew install make ninja git   # as needed
   ```

4. **Git** (already bundled with the CLI tools, but verify):
   ```bash
   git --version
   ```

---

## Source layout

* Stable releases: `src/qc-0.0.N.quanta`
* Work‑in‑progress: `src/qc-0.0.N-wip.quanta` (the file you edit)
* Build artefacts: `bin/` (contains `qc` symlink and architecture‑specific binaries)
* Documentation: `systems/` (this file lives here)

Never edit the `*.quanta` files that are *not* `-wip`; they represent released
versions and must stay unchanged.

---

## Enabling the macOS target

The compiler already distinguishes between `x86_64` (`target_arch == 0`) and
`aarch64` (`target_arch == 1`) via the global `target_arch`.  
To add macOS support we introduce a second global, `target_os`:

| Value | Meaning |
|-------|---------|
| `0`   | Linux (default – ELF output, Linux syscall numbers) |
| `1`   | macOS (Mach‑O output, macOS syscall numbers/traps) |

### Where to set `target_os`

You have two options that **do not modify any released source**:

#### A. Edit the current WIP file (recommended for local development)

Add the line near the existing `target_arch` definition (typically near the top
of the file, after the version comment):

```quanta
let target_os = 1   // 0 = Linux, 1 = macOS
```

If the line already exists (perhaps from a previous experiment), just ensure it
is set to `1`.

#### B. Pass a definition via the build script (keeps the source untouched)

If you prefer not to touch the WIP file, modify `rebuild.sh` (or the manual
steps in `systems/ROADMAP.md`) to add `-DTARGET_OS=1` to the compiler invocation
when building the compiler itself. Example snippet to add inside `rebuild.sh`
before the `make` call:

```bash
# Existing line (example):
#   make CC=$CC CFLAGS="$CFLAGS"
# Modified:
make CC=$CC CFLAGS="$CFLAGS -DTARGET_OS=1"
```

Both approaches achieve the same effect: the compiler’s internal `#if
target_os == 1` blocks will select the macOS‑specific code paths.

---

## What changes when `target_os == 1`

1. **Object file emitter**  
   The existing ELF writer (`write_elf` / `p5_elf_obj` in the source) is
   bypassed; instead a Mach‑O writer is used. The Mach‑O writer follows the same
   layout as the ELF writer but emits:
   * `MH_MAGIC_64` magic
   * `LC_SEGMENT_64` commands for `__TEXT` and `__DATA`
   * `LC_SYMTAB`, `LC_DYSYMTAB`, `LC_LOAD_DYLINKER`, `LC_MAIN` (for the entry
     point `main`)
   * Relocation entries in the `__la_symbol_ptr` and `__got` sections as needed.

   You can find the ELF writer in the source under comments like `// P5:
   object‑format mode`. Duplicate that block and replace the ELF‑specific
   fields with Mach‑O equivalents. The changes are isolated to a few functions
   (`emit_macho`, `write_macho`, etc.) and do **not** affect the rest of the
   code‑generation pipeline.

2. **System‑call numbers**  
   The builtins that wrap system calls (`exit`, `file_open`, `file_read`,
   `file_write`, `file_close`, `mmap`, `mem_alloc`, `free`, etc.) look up their
   numbers from tables indexed by `target_os`. Add a second column (or a second
   table) containing the macOS equivalents, e.g.:

   | Builtin | Linux syscall | macOS trap |
   |---------|---------------|------------|
   | `exit`  | `SYS_exit`    | `SYS_exit` (same number, but via `syscall` with `mach_trap`) |
   | `write` | `SYS_write`   | `SYS_write` |
   | `open`  | `SYS_open`    | `SYS_open` |
   | `mmap`  | `SYS_mmap`    | `SYS_mmap` (underlying `vm_allocate`/`vm_deallocate`) |
   | `mem_alloc` | custom (uses `mmap`) | same implementation, just different underlying trap |

   The actual `syscall` instruction stays unchanged; only the constant values
   differ.

3. **Startup stub (`_start`)**  
   The assembly stub that sets up `argc/argv`, calls global constructors, then
   jumps to `main` is largely identical. The only macOS‑specific tweak is the
   use of `dyld` as the dynamic loader – but for a fully static binary (the
   default Quanta build) the stub can remain the same; the Mach‑O header will
   contain an `LC_MAIN` command pointing to the `main` symbol, which the
   loader will invoke directly.

4. **No changes to code generation**  
   The AArch64 backend (register allocation, instruction selection, etc.)
   remains untouched because macOS uses the same AAPCS64 ABI as Linux for
   function calls.

---

## Building the compiler

From the repository root:

```bash
# 1. Ensure you are working on the WIP file
#    (edit src/qc-0.0.14-wip.quanta or set -DTARGET_OS=1 in rebuild.sh)

# 2. Build the compiler (this produces a macOS‑targeted binary)
./rebuild.sh          # or the manual steps from systems/ROADMAP.md

# 3. Verify the build self‑hosts correctly
./rebuild.sh --self-host

# 4. Run the full test suite (should report 38/38 pass, 0 fail, 0 compile-fail)
./test_suites/scripts/run_tests.sh
```

If the build script still invokes the system `clang` without specifying a
target, you may need to override it explicitly. Add near the top of
`rebuild.sh`:

```bash
export CC="clang -target arm64-apple-darwin$(sw_vers -productVersion | cut -d. -f1,2)"
export CXX="clang++ -target arm64-apple-darwin$(sw_vers -productVersion | cut -d. -f1,2)"
```

(The version extraction yields e.g., `14` for macOS 14.x, giving the suffix
`darwin22`; adjust as needed.)

After a successful build you will find:

```
bin/x86_64/qc-0.0.14-wip        ← x86_64 Linux binary (if you built on Intel)
bin/aarch64/qc-0.0.14-wip       ← aarch64 Linux binary (if you built on Linux)
bin/arm64-apple-darwin/qc-0.0.14-wip   ← macOS Apple Silicon binary
```

The symlink `bin/qc` will point to the appropriate binary for the host on
which you ran `rebuild.sh`. If you built on a macOS Apple Silicon machine,
`bin/qc` will be the Mach‑O version.

---

## Testing the resulting compiler

You can now compile and run Quanta programs directly on your Mac:

```bash
# Example: the classic “hello world” we placed in the README
echo 'fn main() { prints("Hello, Apple\\n"); return 0; }' > hello.quota
bin/qc run hello.quota
# Should print: Hello, Apple
```

If you wish to verify that the output is a genuine Mach‑O file:

```bash
file bin/arm64-apple-darwin/qc-0.0.14-wip
# Expected: Mach-O 64-bit executable arm64
```

---

## Using CI (GitHub Actions example)

If you do not have constant access to a Mac, you can rely on macOS runners
provided by services like GitHub Actions. The workflow below builds,
self‑host‑checks, and tests the compiler for Apple Silicon:

```yaml
name: Build Quanta for Apple Silicon

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  build:
    runs-on: macos-14   # Apple Silicon runner (as of 2024‑2025)
    env:
      # Optional: make the build use the host's clang with explicit target
      CC: clang -target arm64-apple-darwin$(sw_vers -productVersion | cut -d. -f1,2)
      CXX: clang++ -target arm64-apple-darwin$(sw_vers -productVersion | cut -d. -f1,2)

    steps:
      - uses: actions/checkout@v4

      - name: Install build dependencies
        run: brew update && brew install make   # add any other deps you need

      - name: Build compiler
        run: ./rebuild.sh

      - name: Self-host check
        run: ./rebuild.sh --self-host

      - name: Run test suite
        run: ./test_suites/scripts/run_tests.sh

      - name: Upload binaries
        uses: actions/upload-artifact@v4
        with:
          name: quanta-apple-silicon
          path: bin/
```

The workflow will produce an artifact containing the macOS `qc` binary that
you can download and run on any Apple Silicon machine.

---

## Promoting a new release

Once you have verified that:

* The compiler self‑hosts (`./rebuild.sh --self-host` succeeds)
* The test suite passes with **zero** failures and **zero** compile‑fails
* The resulting binaries run correctly on Apple Silicon hardware (or a macOS VM)

you may promote the work‑in‑progress to the next stable version following the
project’s release procedure (see `systems/PROMOTION_RULES.md` and
`systems/PROMOTION_VERSION_RULES.md`):

1. Copy the WIP source to the next version number:
   ```bash
   cp src/qc-0.0.14-wip.quanta src/qc-0.0.15.quanta
   ```
2. Copy the newly built binary to the architecture directory:
   ```bash
   cp bin/arm64-apple-darwin/qc-0.0.14-wip bin/arm64-apple-darwin/qc-0.0.15
   ```
3. Update the `bin/qc` symlink to point to the new binary (if you wish it to be
   the default):
   ```bash
   ln -sf arm64-apple-darwin/qc-0.0.15 bin/qc
   ```
4. Commit the changes (only the newly created `*.quanta` file and the updated
   binary; **do not** modify any existing `*-*.quanta` files).

That completes the release cycle for Apple Silicon.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `ld: library not found for -lSystem` | The linker is trying to link against `libSystem` but the SDK path is missing. | Ensure the Xcode Command‑Line Tools are installed (`xcode-select --install`) and that you are invoking `clang` from that toolchain. |
| `syscall: unsupported trap number` | Using Linux syscall numbers in a macOS build. | Verify `target_os == 1` is active and that the syscall lookup tables contain the macOS values. |
| `Mach-O file format is unsupported` on execution | You ran an ELF binary on macOS. | Double‑check that you are executing the binary from `bin/arm64-apple-darwin/` (or wherever the macOS build placed it). |
| Tests compile but fail at runtime with `SIGILL` (illegal instruction) | The compiler generated ARM64 instructions that the host CPU does not support (e.g., using ARMv8.2 extensions on an older CPU). | Ensure you are running on a genuine Apple Silicon CPU (M1/M2/M3) or that your QEMU/KVM setup emulates at least ARMv8.0‑A. The macOS builders on CI already use the correct hardware. |
| Build script still invokes `gcc` instead of `clang` | `CC`/`CXX` environment variables not overridden. | Explicitly set them in your shell or modify `rebuild.sh` as shown above. |

---

## Summary

* Apple Silicon macOS uses the same AArch64 ISA as Linux, so the existing
  ARM64 code‑generator in Quanta is largely reusable.
* The only additions needed are:
  1. A `target_os` flag to switch the object‑file emitter from ELF to Mach‑O.
  2. A second set of system‑call numbers/trap constants for macOS.
  3. Minor adjustments to the startup‑stub and linker script to emit a proper
     Mach‑O executable.
* With Xcode/Command‑Line Tools installed on a Mac (or a macOS CI runner), you
  can build, self‑host‑check, and test the compiler using the existing
  `rebuild.sh` workflow.
* After successful validation, follow the project’s fix‑forward promotion
  procedure to make the new macOS‑capable version the official release.

Feel free to ask for a concrete patch (e.g., a diff that adds the `target_os`
logic) or for a step‑by‑step walkthrough of the first build on a Mac—just let
me know how you’d like to proceed!