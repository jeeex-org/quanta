# PRE-EXISTING: performance gate RED (loop-sum) — NOT caused by qobj work

Status: **confirmed pre-existing**. Do not attribute this to the G3/G5 qobj series.

## Symptom

`test_suites/scripts/run_tests.sh` reports `performance : RED`.

    PASS  fib(30)        14ms  <= 4000ms
    FAIL  loop-sum(20M)  20904ms > 2000ms   (then SIGILL, rc=132)
    PASS  memfill(1M*8B) 11ms  <= 2000ms

## Proof it is not the qobj work

Three compilers, all given the identical kernel
(`fn main() { let s=0; let i=0; while i<20000000 { s=s+i; i=i+1 } ... }`)
with `-O`:

| compiler                                   | output md5                  | runtime |
|--------------------------------------------|-----------------------------|---------|
| built from **committed** `src/x86/`        | `aa682a38b7cf3ccd13a7c0faf9aaedab` | 20959 ms, SIGILL |
| built from **qobj WIP** `src/x86/`         | `aa682a38b7cf3ccd13a7c0faf9aaedab` | 21743 ms, SIGILL |
| **committed binary** `4791633d`            | `dcfe378bcbcd618b263a0510b053de44` | 3 ms, rc=0 |

The qobj WIP and the committed source emit **byte-identical** output. The
committed *binary* emits different output and is the only one that runs.

Conclusion: `compiler/0.0.217/bin/x86/qc` as committed does **not** correspond
to the committed source. The binary is stale relative to `src/x86/`.

The committed source *is* a deterministic fixed point of itself — three
successive generations all hash `84363b7686b75ea0d001f4d434372a65` — so the
divergence is between binary and source, not within the source.

## Nature of the defect

The two outputs differ by 114 bytes. Disassembly at file offset 0x27a:

    committed binary:  jmp 0x304
    committed source:  jmp 0x26

A loop-body branch target plus a relocated ~114-byte block. The slow build jumps
backwards across the large block on every one of 20M iterations, and the loop
terminates into an illegal instruction rather than a `ret`.

This is a **loop-body codegen / branch-targeting defect in the committed
source**, reachable with no qobj cache present at all.

## Reproduction

    cd /opt/tali/quanta
    git checkout HEAD -- compiler/0.0.217/src/x86/
    rm -f /tmp/base1 /tmp/base2
    compiler/0.0.217/bin/x86/qc compiler/0.0.217/src/x86/main.quanta /tmp/base1
    /tmp/base1 compiler/0.0.217/src/x86/main.quanta /tmp/base2
    /tmp/base2 -O benchmarks/benchmark_loop_sum.quanta /tmp/ls
    time /tmp/ls          # ~21s then SIGILL

## Status of the G5 work relative to this

Unaffected. With the qobj WIP compiler:

- `functional`, `extern-c`, `extern-ld`, `security`, `valgrind`, `fuzz`,
  `differential`, `generics`, `stdlib`, `multi-tu`, `verify-status` — all GREEN
- source-path output is **byte-identical to the committed compiler** on
  `calltest`, `g5test`, `simple_fadd`, `float_test`
- `simple_fadd` = 7, `float_test` = 159, `g5test` = 0

## Remaining work

1. Fix the loop-body branch targeting in the committed source (this gate).
2. Rebuild and replace the stale `compiler/0.0.217/bin/x86/qc`.
3. G5 cache-only codegen still produces a binary that dereferences a null
   string pointer (5381-byte delta vs the source build). Isolated to how
   cached functions lay out string literals; metadata and IR slices verify
   correct.
