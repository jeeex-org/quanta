# `fc_attn_workers`: the dead parallel attention body is REMOVED, with the measurement that decided it

**Status:** DECIDED — REMOVED (lib/std, no compiler change) · **A-number:** A21 ·
**Owner file:** `lib/std/lfm2_forward.quanta`

## 0. The decision

Defect: `fc_attn_workers` is read by the attention dispatch but had **no setter
anywhere in `lib/std`**, so the parallel attention body it gated
(`fc_attention_par` + `patt_worker`) had never run. Two options were offered —
give it a setter and make it work, or remove it. **I removed it**, for the
measured reason in §3: as written it leaks **1 MB of address space per spawned
thread per call**, i.e. **64 MB per forward token** at 8 workers (8 attention
layers × 8 threads), which kills any run past ~128 tokens under the 8 GB cap. It
is not "a path nobody enabled"; it is a path that **cannot be enabled** for the
workloads it exists for.

It is NOT removed because it was useless. **It is measurably faster** (~1.35× at
position 1600, §2) — the follow-up is to bring that parallelism back **through
the persistent worker pool**, never by re-spawning per call. That is a separate
lever and a separate file (`lib/std/lfm2_mm.quanta`, `pl_*`), queued in A21.

## 1. First: is it reachable at all?

`grep -rn fc_attn_workers` over `lib/`, `tests/`, `test_suites/`, `scripts/`:
only **reads** exist, in `lfm2_forward.quanta` itself. No setter, and no test
sets it. So nothing in the tree ever took the `fc_attn_workers > 1` branch — which
is exactly why the per-layer-norm fix in `fc_attention_par` had to be verified by
reading only (`docs/research/lfm2-perlayer-norm-closeout.md` §3).

One thing worth recording, because it is the only way the path could ever have
been driven: **an importing module CAN assign the global.** A scratch probe
(`import std/lfm2_forward` then `fc_attn_workers = 4`) compiles and prints `4`.
So "unreachable" means "no caller does it", not "impossible from outside" — and it
means the leak below is reachable by a one-line test, which is why the dispatch
branch itself went too and not just the global.

## 2. Measured: enabled, it is ~1.35× faster at long context

Driver: a scratch copy of `tests/lfm2_polite_bench.quanta` that (a) runs each
forward at a single chosen position `POS`, so the attention body has realistic
`O(pos)` size **without** prefilling to `POS` first, and (b) samples
`/proc/self/statm`.

```quanta
mm_set_workers(MW); mm_set_embed_workers(MW)
fc_attn_workers = W                 // the only way to reach the path
mm_pool_begin()
let i = 0
while i < NFORW { if fc_forward_token(35808, POS) != 0 { ... } ; i = i + 1 }
mm_pool_end()
```

```
# conf: "<fc_attn_workers> <nforw> <mm_workers> <pos>"
$ printf '0 3 8 1600\n' > attnpar.conf; ( ulimit -c 0 -v 8000000; nice -n 19 attnpar_probe.bin </dev/null )
$ printf '8 3 8 1600\n' > attnpar.conf; ( ulimit -c 0 -v 8000000; nice -n 19 attnpar_probe.bin </dev/null )
```

Three repeats each, alternating, load 11–16 (`powersave`, ambient `Hermes`
~750 %):

| run | `fc_attn_workers=0` | `fc_attn_workers=8` | argmax | VmSize growth (3 fwd) |
|---|---|---|---|---|
| 1 | 8 832 ms/tok | 6 791 ms/tok | 35808 | 43 184 vs 241 424 kB |
| 2 | 8 886 | 6 803 | 35808 | 43 184 vs 241 424 |
| 3 | 9 226 | 6 397 | 35808 | 43 184 vs 241 424 |

* Speed: **~1.35×** (mean 8 981 → 6 664 ms/tok), reproducible to within ~5 %.
  The reason it helps is that the serial scores/softmax/accumulate is *not* small
  at long context: comparing `pos=0` (6 272 ms/tok) with `pos=1600` (8 900 ms/tok)
  in the serial arm, the attention body is **~2.6 s of an 8.9 s forward** —
  `fc_kv_get` is called per `(t, c)` element with an address computation, so the
  body is expensive enough to parallelise. (My first estimate of "~27 ms, so the
  1.35× must be noise" was wrong; the repeat runs and the pos-0-vs-1600 delta
  settled it.)
* Correctness: `argmax_last = 35808` in both arms — the par body agrees with the
  serial one at this position.
* **Address space: 241 424 − 43 184 = 198 240 kB over 3 forwards = 66 080 kB /
  forward ≈ 64.5 MB.** That is exactly `8 attention layers × 8 threads × 1 MB`.
  `thread_create` mmaps a fresh 1 MB child stack and `thread_join` does not unmap
  it — the identical per-call leak that **A9** already retired from `mm_matvec`
  (`docs/research/threaded-forward-defect.md` §8.1, §8.3). The baseline
  `fc_attn_workers=0` growth of 43 184 kB is the separate residual pool leak A9
  records.

## 3. Why removal, not a setter

1. **It cannot deliver its benefit.** 64 MB per forward token at 8 workers →
   ~128 tokens to exhaust an 8 GB `ulimit -v`. The SI loop's prompt alone is
   **3,638 tokens**; a prefill of that length would need ~232 GB of address
   space. A setter that turns this on is a leak bomb, not a speedup.
2. **No caller, never executed, correctness only ever verified by reading.** It
   already cost one inspection-only fix (the per-layer norm reload). Keeping it
   invites the exact mistake the brief names: trusting code that cannot run.
3. **The fix is a different file and a different lever.** Routing the attention
   body through the persistent pool means a second job type in `pl_worker`
   (`lib/std/lfm2_mm.quanta`) — that file is on the loader's critical path, was
   just changed by the A19 politeness work, and is not this unit's file. One lever
   per version.
4. **Two thread systems in one call, with no guard.** `fc_attention_par`'s
   projections already call `mm_matvec`, which is pooled. Enabling it inserts
   per-call threads *inside* a call that is already using the pool; the polite
   ceiling (`min(affinity_cores/2, 8)`) bounds the pool, and would bound nothing
   about these.

## 4. What was removed

`lib/std/lfm2_forward.quanta`:

* `fc_attention_par()` (was lines 825–1001), `patt_worker()` (757–822) and the
  `patt_*` globals (1004–1014) — 268 lines.
* `let fc_attn_workers = 0` — replaced by a note pointing at the branch comment.
* The dispatch in `fc_layer`: the `if fc_attn_workers > 1 { fc_attention_par } else
  { fc_attention }` became an unconditional `fc_attention` call, with the reason
  in the comment.

**Behaviour-preserving by construction:** the removed branch required
`fc_attn_workers > 1`, and no code in the tree ever set it, so `fc_attention` was
already the only path executed. `fc_attention` keeps its own per-layer norm reload
and its `fc_at_out` zeroing (both were duplicated in the par copy).

## 5. The queued follow-up (A21)

Re-add attention-body parallelism **through the pool**: add a job type to
`pl_worker` that runs `patt_worker`-shaped work over a head slice, with the head
range and pointers in the job cell, and drive it from `fc_attention`. Then:
measure it against the pooled path (the driver below, once it compiles again),
keep bit-identity against the serial path (`argmax` and, better, a KV/state diff),
and add a gate row. Expected win ~1.35× at position 1600, address-space budget
unchanged (the pool allocates once).

## 6. Reproducing §§2–3

The driver cannot live in the tree as-is: it assigns `fc_attn_workers`, which no
longer exists. It was a scratch copy of `tests/lfm2_polite_bench.quanta` with
(a) `POS` from the conf, (b) a `/proc/self/statm` sampler (VM size before, after
each forward, and peak), and (c) one added line, `fc_attn_workers = W`. To
reproduce, check out the parent of this commit, apply those three changes, and run
with `"<W> <nforw> <mm_workers> <pos>"` = `0 3 8 1600` and `8 3 8 1600`.
`tests/lfm2_attn_pos_bench.quanta` (new, committed) is the same driver with the
`fc_attn_workers` line **omitted** so it compiles on this tree — it re-measures the
serial arm and gives the next unit the harness for the pooled version.

## 7. Documents left stale by this removal (NOT this unit's files)

These still assert the path is "dead code, left as-is"; they are now wrong and
were not edited (this unit owns only NEW `docs/research/**` and
`docs/plans/bugs.md`):

* `docs/research/loader-resource-politeness.md` §5 — "`fc_attn_workers` … Left as-is."
* `docs/research/threaded-forward-defect.md` §8.3 — "still spawns per-call threads … unexercised".
* `docs/research/lfm2-perlayer-norm-closeout.md` §3 — "`fc_attention_par` … has no runtime exercise".
* `docs/research/prefill-batching.md` — "remain dead code".
* `docs/plans/lfm2-native-inference-perf.md` — the `fc_set_workers(n)` plan entry.
* `stage1/RESULTS.md` (gitignored scratch).

## 8. Not verified (stated, not hidden)

* The ~1.35× is at **one** position (1600) and `n=3`. It is consistent and the
  pos-0-vs-1600 delta corroborates it, but it is not a full prefill sweep.
* The `pos=1600` forward reads KV entries for positions 0..1599 that were never
  written (the cache is zeroed), so the *values* are meaningless — only the work,
  the timing and the address space are meaningful. `argmax` agreeing at 35808 says
  the par body is not obviously wrong, **not** that it is correct over a real
  sequence.
* `fc_attn_workers` was the only settable knob audited here; no other global in
  `lfm2_forward.quanta` was audited for the same "read but never written"
  pattern.
