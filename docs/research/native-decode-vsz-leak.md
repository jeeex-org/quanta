# Native LFM2 decode: silent OOM exit and ~11 MB/token VIRTUAL growth

Status: measured 2026-10-16 during the stage2 SI-loop wiring, HEAD `968d3646`,
model `QUANTA-LFM2.5-2.6Bv1-Q4_K_M.gguf`, driver
`stage2/lfm2_gen_driver.quanta` (the tracked `tests/lfm2_generate.quanta` with
stage2 paths, max_new clamp 1024, batched prefill). Raw evidence:
`stage2/run_20261016_112523/` (`gen_stdout.crash1.txt`, `run.json` VmPeak
samples, per-attempt stdout). Nothing in `lib/std` or the compiler was
changed; this documents two runtime defects the SI loop hit, for their owners.

## Finding 1: an allocation failure is a SILENT exit(1)

A 700-token generation died mid-decode with NO output change: no `FAIL`
marker, no stack, no message. The zombie's exit status (read from
`/proc/<pid>/stat` field 52) was **256 = the program's own exit(1)**.

`lib/std/lfm2_mm.quanta` (~line 865, the emitter's MAP_FAILED guard) is
`mov edi,1; mov eax,60; syscall` — mmap failure = exit(1) with nothing
printed. Any long native run that exceeds its address-space cap therefore
just stops, and a caller that did not record the exit status cannot tell a
crash from a hang. The stage2 driver prints a heartbeat every 32 tokens
(`[hb N]`) so the death point is localised in the log; `wire.py` treats
"exited without DONE" as a distinct, recorded failure class
(`generation_crashes[]`).

## Finding 2: decode grows ~11 MB/token of ADDRESS SPACE (RSS grows only ~0.35 MB/token)

VmPeak sampled from `/proc/<pid>/status` during a 1024-token decode
(20 workers, temp 0.25, top_k 40):

| point | VmPeak | VmRSS |
|---|---:|---:|
| after load | ~1.7 GB (model mmap) | ~140 MB |
| after prefill (697 tokens, B=64) | 4.5–4.6 GB | 185–235 MB |
| ~500 decoded tokens | ~9 GB | ~300 MB |
| ~1000 decoded tokens | 12.9–13.2 GB | ~500 MB |

Slope after prefill: **~11 MB of VIRTUAL per decoded token** against
**~0.35 MB/token of RSS** — the leak is almost entirely unmapped-but-reserved
address space (per-allocation mmap + per-call sampler scratch that is never
released, in `sample_full`'s per-token path), not resident growth. Two
measured consequences:

- **The documented 8 GB run cap cannot hold a long generation.** The first
  attempt died at ~480 tokens with RSS at only ~342 MB. RSS-based sizing is
  the wrong instrument for this runtime; cap VmPeak (or expect death at
  ~8 GB / ~480 tokens from a ~4.5 GB post-prefill VmPeak).
- **Any fixed cap is a token ceiling.** At 11 MB/token: 16 GB ≈ 1,000 tokens,
  32 GB ≈ 2,500 (from the post-prefill base). The stage2 loop raised its run
  cap to 32 GB with RSS sampled every poll (stayed 165–500 MB; the box kept
  25+ GB available), which is a guard, not a fix.

The fix belongs where the allocation lives: `sample_full`'s per-token scratch
(128k-element buffers per call in `lib/std/sampling.quanta`) and/or the
forward's per-call allocations should be hoisted out of the token loop or
freed; and the MAP_FAILED guard should print `error: out of memory` + the
requested size before exiting. Neither is attempted here (stage2 owns only
`stage2/**`; no compiler or lib/std change).

## Reproduce

```
# the crash: 8 GB cap, ~480 tokens
( ulimit -c 0 -v 8000000; nice -n 19 stage2/run_20261016_112523/lfm2_gen_driver.bin )
#   -> exit 1, stdout ends mid-token, no FAIL line
# the trajectory: same binary, 32 GB cap, poll /proc/<pid>/status VmPeak
```

`stage2/wire.py` (functions `start_generation`, `proc_status_fields`,
`poll_generation`) is the working instrumentation.
