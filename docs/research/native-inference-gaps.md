# Native inference: verified gap list

Each item below was established by running the compiler, not by reading
source. "Verified" means a minimal reproducer was executed.

Status: 2026-10-04, v0.0.222, compiler md5 2a11a7594fb31f02c6fbe26718befa1e

## Confirmed available (probed and working)

- `malloc` / `free` — malloc returns the BASE, payload at base+8
- `mem_alloc(n)` — raw, no header, no payload offset
- `mem_load` / `mem_store` — 8 bytes
- `mem_load8` / `mem_store8` — 1 byte
- `fadd` `fsub` `fmul` `fdiv` `i2f` `f2i`, f64 params/returns/comparisons
- `expf` via `import std/math`; `fmin`/`fmax`/`clamp`/`imin`/`imax`/`iabs`
- structs (with `,` separators), `-> f64` returns, `i64[n]` arrays
- byte-copy by explicit loop (no builtin needed)
- fixed-point float printing via integer ops (see below)

## GAPS

### 1. `lib/std/native_inference.quanta` never compiled — FIXED to diagnose

Line 4 is `import std/mem`. No such module exists in `lib/std/`. Because a
missing import exited 16 silently, this was invisible.

Remains to do: the file uses `sizeof`, `*u8`/`*f32`/`*u64` pointer types,
comma-free struct bodies, and `struct X { a: i64, b: i64 }`. The compiler
accepts none of those (verified: `sizeof` is absent from the parser
entirely). It must be rewritten in the accepted syntax.

### 2. Both generation loops are empty comments

`quanta_infer` lines 537-551:
    while pos < n_tokens { // ... full transformer forward ... }
    while gen < max_new  { // Forward / Sample / Print }
There is no forward pass, no sampling, no output.

### 3. Tokenizer is a stub

`tokenizer_encode` writes out_ids[0]=1, [1]=2, [2]=3 and returns 3.
`tokenizer_load` never reads the GGUF vocab. BPE must be implemented to feed
the model real text.

### 4. ~~NO `sqrt` ANYWHERE~~ -- WRONG, retracted

There is no `sqrt` in `lib/std/math.quanta`, but it is a **BUILTIN** in the
emitter (`sqrtsd xmm0, xmm0`, emitter.quanta ~line 3517), as are `sin`,
`cos`, `tan`, `log`, `pow`, `floor`, `ceil`, `f64of`, `fisnan`, `fisinf`.
All verified correct to 6 decimals.

I first "discovered" this as missing and wrote a software Newton-Raphson
`sqrtf`. It works and is committed, but it is redundant -- the builtin `sqrt`
is exact and a single instruction. Do NOT reach for the software version.

The real lesson: **the emitter has a large builtin surface and none of it is
documented in one place.** Extract it by grepping the emitter for the
`if nl==N&&r8(nm)=='x'&&...` builtin-name comparisons. Doing that first would
have saved the detour.

Also note `q4k_dot` and `qaddf_avx2` exist as builtins -- these are directly
on the critical path for a fast Q4_K_M path.

### 5. NO `mem_copy`, `mem_zero`, `mem_fill`, `sizeof`

Weight loading and buffer init need these. Byte/word loops work; whether
that is fast enough for a multi-GB model is unmeasured.

### 6. `print` is BROKEN for all f64

`print(2.5)` emits `4612811918334230528` — the raw bit pattern. The integer
print loop does `idiv rcx, 10` on the bits.

This has NEVER been caught: every float gate in test_suites/codes verifies
by COMPARISON (`if half(10.0) != 5.0 { return 10 }`) and never prints.
The float-oper / float-return / float-operpath gates are all GREEN while
this is broken.

Workaround verified working — fixed-point formatting in pure Quanta:
    let s = f2i(fmul(v, i2f(1000000)))     // 6 decimal places
    printi(s / 1000000); prints(".")       // then 6 single digits
Do NOT hand-patch the emitter for this; an attempt at a byte-emitting SSE
float formatter was started and reverted as unverified.

## Suggested order

1. `sqrt` in std/math (needed by RMSNorm, blocks everything downstream)
2. `print` float fix, ideally as a stdlib `pf64` using the fixed-point form
3. Real BPE tokenizer from GGUF vocab
4. Q4_K_M dequant -> real weight buffers
5. Vertical slice: embed -> 1 layer -> logits for ONE token
6. Only then 24 layers, KV cache, sampling, benchmark vs llama-server