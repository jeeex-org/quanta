# 0.0.221 — WIP

Promoted from `0.0.220` at commit `caa372c5`, whose state was verified before
the copy:

    compiler/0.0.220/bin/x86/qc
    size=2921088
    md5=c4194801bd7d4540d321129d557fa536
    self-hosted 3 generations byte-identical
    suite PASS=118 CFAIL=0 RFAIL=33 of 151

`0.0.220` is a good state and stays as the stable fallback. All new work
happens here; `0.0.220/src` is never modified.

(The WIP.md copied from an older tree was stale — 0.0.218's, describing
`--emit-dynamic` work. Replaced, not appended to.)

## Plan

### Phase 0 — promotion

Done: copy, VERSION pointer moved, gate re-verified on the copy.

### Phase 1 — `std/math` as a real module

**Blocking: a second-module import SIGILLs the compiler.**

Adding `import std/math` to `lib/std/gguf.quanta` — with `std/math` having no
imports of its own and no globals, so it is not circular — produces SIGILL at
run time in `test_all_final` and `test_inference_verify`, dropping the suite to
PASS=116. Removing the import makes `expf` undeclared (compile failure), so both
symptoms have one cause: the second module is what breaks.

Diagnose this before any further stdlib work. Nothing below is safe while a
second import can corrupt code generation.

Then finish the `expf` extraction and run a clean audit. Work preserved at
`/tmp/keep/` (`math_expf.quanta`, `gguf_expf.quanta`,
`expf_extraction.patch`). The earlier "246 bad" was a broken harness — duplicate
JSON keys, then `inf` comparisons — not a real result. `expf` passes standalone
but has never had a clean full audit.

### Phase 2 — transcendentals as reduced-argument polynomials

`sin`/`cos`/`tan`/`log`/`pow` are x87 today (`fsin`, `fyl2x`). x87 gives ~1 ULP
*absolute* error, so relative accuracy collapses near roots:

    sin(0.001)  result 1.0e-03   exact
    sin(1.0)    result 8.4e-01   exact
    sin(pi)     result 3.2e-15   rel err 1.25e-06

glibc reduces `x = n + r` with `|r| <= pi/4` and evaluates a polynomial, so
absolute error stays proportional to `r` and relative accuracy holds. Same
treatment fixes accuracy and speed at once, which is why it precedes the AVX
work.

Bar: raw bits vs glibc, <= 1 ULP.

### Phase 3 — FMA in the inference inner loops

Never emitted anywhere in the compiler today. `acc = fma(x, w, acc)` in
`gguf_matvec`, `rms_norm`, `dequant_q4k` — one rounding instead of two, and the
largest speed win for the smallest change.

### Phase 4 — AVX2 matvec

4 doubles per `ymm` instead of scalar SSE. **Measure before building**: at
2048x10752 f64 the working set is large enough that this is likely
bandwidth-bound, so 4x may not appear. The i9-13905H has AVX2 but not AVX512.

### Phase 5 — runtime CPUID dispatch

Must precede any FMA/AVX2 code intended to run on older hardware. The compiler
emits no dispatch today.

## Sequencing

Phase 1 gates everything. Phases 3 and 4 do not depend on 2 and could overlap.

## Standing open

- Multi-argument `print`/`println` drops every argument after the first. The
  emitter treats `argc == 2` as its internal `print(buf, len)` form, so a
  user-written `println("a", 42)` is routed into it. Root cause identified; a
  parser-lowering attempt got values printing but emitted a spurious blank
  line and raw float bits, then broke the compiler outright (`CFAIL=151`) and
  was reverted.
- Q6_K and Q8_0 dequantisation are invalid for real data.
- 33 suite failures, triaged only far enough to confirm none are new.

## Carried over from earlier notes

The root cause of much register corruption is `codegen.quanta` /
`funcscan.quanta` losing long-lived locals rather than any individual site. Any
new value that must survive more than a few dozen lines in one function should
be parked in a global, commented with which slot is which.