# Feature Requests: Execution Modes

This document tracks requested execution‑mode features for the Quanta compiler/toolchain. 
Each entry includes a short description, motivation, current status, and any known dependencies or implementation notes.

## Optional `fn` keyword and optional parameter parentheses

**Description**
Allow function declarations in Quanta to be written with or without the `fn` keyword and with or without an explicit parameter list. Both of the following forms should be accepted and treated as equivalent:

```
foo {
    # body
}
fn foo {
    # body
}
fn foo() {
    # body
}
foo(a, b) {
    # body
}
fn foo(a, b) {
    # body
}
```

**Motivation**
* Ergonomics – short helpers, REPL‑style snippets.
* Familiarity – many languages allow omitting `fn` or empty parentheses.
* Flexibility – choose the style that best fits the context (library headers may keep `fn` and `()` for clarity, scripts may drop them).

**Status**
*Not started* – currently `fn` is required and parentheses are required for an empty parameter list (the syntax `fn foo { … }` is not accepted).

**Dependencies / Notes**
* Requires changes to the lexer (make `fn` a contextual keyword) and the parser (optional `fn` and optional parameter list with look‑ahead).
* No changes needed to IR generation, code generation, or any back‑ends.
* Fully backward compatible: all existing source files continue to compile unchanged.

**Implementation Sketch**
1. **Lexer** – Keep the `FN` token but treat it as contextual: when scanning an identifier, if the letters `f`f` sequence is followed by `(` or `{` (or end` are seen, still return `IDENT`; let the parser decide whether to consume it as the keyword.
2. **Parser** – Modify the function‑declaration entry point:
   * Optionally consume a `FN` token.
   * Consume an `IDENT` (function name).
   * Look ahead one token:
        - If the token is `LPAREN`, consume it, parse an optional `ParameterList`, then consume the matching `RPAREN`.
        - Otherwise, treat the parameter list as empty.
   * Expect a `LBRACE`, parse the function body as a `Block`, then consume the matching `RBRACE`.
   * Return an `FnDef` node containing the (possibly empty) parameter list.
3. **AST / Symbol Table** – Ensure the `FnDef` node can hold an empty parameter list (already the case).
4. **IR Generation / Codegen** – No changes needed; emitting a function with zero parameters already works.
5. **Testing** – Add test cases covering the six allowed forms (with/without `fn`, with/without parentheses, with parameters).
6. **Documentation** – Update `docs/SYNTAX.md` (and any language‑spec files) to reflect the new grammar.

---

## 1. Interpreter Mode  

**Description**  
Add an interpreter that can execute Quanta source directly without emitting a native binary. Typical usage: `qc run <file.quanta>` or `quanta run <file.quanta>` launches an interactive/stack‑based interpreter.

**Motivation**  
* Rapid development / REPL experience.  
* Debugging and teaching – immediate feedback without a compile step.  
* Enables scripting and quick prototyping on platforms where a native binary is undesirable (e.g., embedded environments with limited storage).

**Status**  
*Not started* – the current pipeline is strictly ahead‑of‑time (AOT) compilation to ELF/Mach‑O.

**Dependencies / Notes**  
* Requires a byte‑code or AST‑interpreter representation of the IR.  
* Should reuse the existing IR (or a lightweight subset) to avoid duplicating semantics.  
* Must respect the same ownership/zero‑GC semantics as the compiled version.  
* Interaction with existing `qc run` flag (see §4) – the interpreter can be selected via `--mode=interpreter` or similar.

**Implementation Sketch**  
1. Extend the compiler driver to accept a `--mode=interpreter` option.  
2. After parsing and optional optimization, instead of code‑generation, walk the IR (or a simplified bytecode) with a stack‑machine interpreter.  
3. Provide built‑in I/O primitives (`print`, `read`, etc.) that call the host OS directly.  
4. Ensure panic/unwind handling matches the compiled runtime (traps → exit codes).  

---  

## 2. JIT (Just‑In‑Time) Mode  

**Description**  
Compile Quanta code to machine code at runtime and execute it immediately, similar to a JIT compiler for scripting languages. Usage: `qc jit <file.quanta>` or a flag like `--mode=jit`.

**Motivation**  
* Enables hot‑reloading and dynamic code generation (e.g., plugins, DSLs).  
* Combines the flexibility of interpretation with near‑native performance for long‑running workloads.  
* Useful for research and experimentation where re‑compiling the whole program is costly.

**Status**  
*Not started* – the current toolchain only produces static ELF/Mach‑O binaries.

**Dependencies / Notes**  
* Requires a runtime code emitter (e.g., using `mmap` + `mprotect` or a library like `asmjit`/`dynasm`).  
* Must reuse the existing IR → machine‑code backend (x86‑64 / AArch64) but emit to executable memory instead of writing a file.  
* Need to handle relocation of literals and external calls (e.g., to the standard library) – either embed a mini‑runtime or rely on the host process’ already‑loaded standard‑library routines.  
* Should respect the same security defaults (overflow traps, bounds checks) as the AOT path.

**Implementation Sketch**  
1. Add a `--mode=jit` flag to the driver.  
2. After IR generation and optimization, invoke the existing code‑generation routine but target a writable/executable memory buffer instead of a file object.  
3. Patch any relocations (e.g., addresses of string literals, external function pointers) after code emission.  
4. Transfer control to the generated entry point (typically a function named `main`).  
5. Provide a mechanism to free/jit‑clear code when no longer needed (optional).  

---  

## 3. WASM (WebAssembly) Mode  

**Description**  
Emit WebAssembly (binary .wasm or text .wat) from Quanta source, allowing execution in browsers, WASI runtimes, or any WebAssembly VM. Typical usage: `qc wasm <file.quanta> -o out.wasm`.

**Motivation**  
* Portable deployment across web, edge, and serverless platforms.  
* Enables Quanta to be used as a safe, sandboxed extension language.  
* Leverages the existing type‑safe, ownership‑based semantics which map well to WASM’s linear memory model.

**Status**  
*Not started* – no current backend for WASM emission.

**Dependencies / Notes**  
* Need a WASM emitter that walks the IR (or a slightly adapted IR) and emits the corresponding WebAssembly binary format (sections: Type, Import, Function, Table, Memory, Global, Export, Start, Element, Code, Data).  
* Must map Quanta’s linear memory model (explicit `malloc`/`free` via `mmap`/`munmap`) to WASM linear memory – likely reuse the existing `mem_alloc`/`mem_free` builtins as imports from the host (or implement using `memory.grow`).  
* System calls (file I/O, exit, etc.) should be emitted as imports from the WASI snapshot‑preview1 API (or a custom JS host when targeting browsers).  
* The existing optimizer passes can be reused unchanged.  
* Output should be a standalone `.wasm` that can be instantiated with `WebAssembly.instantiateStreaming` or a WASI runtime.

**Implementation Sketch**  
1. Add a `--wasm` or `--target=wasm` flag to the driver.  
2. After IR generation & optimization, walk each function and emit corresponding WASM instructions (using the existing opcode mapping as a guide).  
3. Emit the WASM binary via a simple binary writer (or use the `wat2wasm` toolchain for debugging).  
4. Provide a small runtime/wrapper (JS or C) that supplies the needed imports (`fd_write`, `fd_read`, `proc_exit`, `memory.grow`, etc.) and invokes the exported `_start` or `main` function.  
5. Test with the existing test suite by compiling to WASM and running via `wasmtime` or Node.js.  

---  

## 4. Pre‑compile Mode (`qc run` / `quanta run`)  

**Description**  
Provide a convenient one‑step command that compiles the source to a temporary binary (or uses a cached compilation) and immediately executes it, akin to `go run` or `rustc --run`. This is distinct from pure interpretation; it still uses the AOT code‑gen path but hides the compile step from the user.

**Motivation**  
* Improves developer ergonomics for quick tests and examples.  
* Aligns with user expectations from other languages (e.g., `go run`, `rustc --run`).  
* Reduces boilerplate in documentation and tutorials.

**Status**  
*Partially present* – the repository already contains a `test_suites/scripts/run_tests.sh` script that builds and runs tests, but there is no user‑facing `qc run` command for arbitrary source files.

**Dependencies / Notes**  
* Leverages the existing native code‑gen backend (ELF/Mach‑O).  
* Should place temporary outputs in a designated directory (e.g., `tmp/` or the system temp folder) and clean up after execution unless the user requests to keep the binary.  
* Must respect the same security defaults (traps on overflow, bounds, etc.).  
* Can optionally cache results based on file hash to avoid recompiling unchanged sources (similar to `go build` caching).

**Implementation Sketch**  
1. Extend the driver to recognize a subcommand `run` or a flag `--run`.  
2. When invoked, compute a hash of the input file(s) (or rely on modification time).  
3. If a valid cached binary exists (matching hash & target), reuse it; otherwise invoke the normal compile pipeline to produce a temporary binary in `$TMPDIR/quota-XXXXXX`.  
4. Execute the binary, forwarding any command‑line arguments to the program.  
5. Propagate the program’s exit code as the exit code of `qc run`.  
6. Offer an optional `--keep-binary` flag to retain the generated artifact.  

---  

## 5. Related Items & Cross‑Cutting Concerns  

| Feature | Overlaps / Dependencies |
|---------|-------------------------|
| Interpreter ↔ JIT | Both may share a common bytecode or IR interpreter core; JIT can be viewed as an “optimizing” interpreter that compiles hot functions to native code. |
| WASM ↔ Native | The same middle‑end (IR + optimizer) feeds either the native codegen or the WASM emitter. |
| Pre‑compile mode ↔ All backends | Simply a driver convenience wrapper; works whichever target (native, wasm, jit, interpreter) is selected via other flags. |

---  

## 6. Suggested Order of Work  

1. **Stabilize the current AOT pipeline** – ensure self‑host & test suite pass.  
2. **Implement the pre‑compile “run” mode** – re‑uses the existing compile path and gives immediate user benefit.  
3. **Add the Interpreter mode** – leverages the IR without needing a complex code emitter.  
4. **Add the JIT mode** – builds on the interpreter infrastructure plus a runtime code emitter.  
5. **Add the WASM backend** – a separate emitter that can reuse the optimizer; can be pursued in parallel with JIT if resources allow.  

---  

*End of document.*