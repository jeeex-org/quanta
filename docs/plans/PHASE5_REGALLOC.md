# Phase 5: Global Register Allocation

## Goal
Extend the per-op register allocator to work across basic blocks using liveness analysis,
so values survive branch/jump boundaries without spilling.

## IR Structure
- IR records: 40 bytes each (`IRS=40`)
  - op (8 bytes), res (8), a0 (8), a1 (8), a2 (8)
- `irc` = number of records in current function
- Block terminators: `IR_BR` (conditional), `IR_JMP` (unconditional)
- Block starts: `IR_LABEL`
- Function boundaries: `IR_PARAM`, `IR_RET`, `IR_CALL`

## Implementation Plan

### Step 1: Build CFG (Control Flow Graph)
- Scan IR, identify block boundaries at IR_LABEL
- Build `block_of[ir_idx]` — which block each IR index belongs to
- Build `succ[block]` — successor blocks (BR → two targets, JMP → one target, fall-through)
- Build `pred[block]` — predecessor blocks
- Handle: `IR_BR` (branch to `a1` if true, `a2` if false), `IR_JMP` (jump to `a0`)

### Step 2: Liveness Analysis (Backward, Per-Block)
- `live_out[block]` — set of vregs alive at block exit
- `live_in[block]` — set of vregs alive at block entry
- Worklist algorithm:
  1. Initialize: `live_out[last_block] = {}` (or RET operand if any)
  2. Backward scan each block:
     - For each op, compute `live = (live - def) ∪ use`
  3. Propagate `live_out` to predecessors' `live_in`
  4. Iterate to fixpoint

### Step 3: Linear-Scan Allocator with Block Awareness
- Maintain `vreg_reg[vr]` — current physical reg for vreg (-1 if spilled)
- At block entry: restore liveness from predecessor state
- At block exit: ensure `live_out` vregs are in registers (or will be loaded by successors)
- Within block: linear scan (reuse expired registers, spill oldest)
- Across block boundary: spill vregs not live in successor, keep vregs live in successor

### Step 4: Spill Code with Block-Aware Reload
- Spill: `wbp(spill_home(vr), reg)` at block exit if vreg not needed by successors
- Reload: `rbp(reg, spill_home(vr))` at block entry if vreg needed by current block
- Only spill/reload if vreg crosses block boundary and is live

### Step 5: Integration with Float Register File
- Same CFG and liveness for float vregs
- Float register file (xmm0-7) allocated separately from GP regs
- At block boundary: spill float regs to `fspill_home(vr)` if not live in successor
- Reload float regs from `fspill_home(vr)` via `frld(xmm, offset)` if live in current block

## Data Structures (in mmap'd globals)
```
let block_of = mmap(2000000)    // block_of[ir_idx] = block number
let block_start = mmap(200000)   // block_start[b] = first IR index of block
let block_end = mmap(200000)     // block_end[b] = last IR index + 1 of block
let succ = mmap(8000000)         // succ[b*100 + i] = i-th successor block (-1 = none)
let pred = mmap(8000000)         // pred[b*100 + i] = i-th predecessor block (-1 = none)
let live_out = mmap(4000000)     // live_out[b*1000 + v] = 1 if vreg v live at block b exit
let live_in = mmap(4000000)      // live_in[b*1000 + v] = 1 if vreg v live at block b entry
let vreg_reg = mmap(400000)      // vreg_reg[v] = physical reg holding vreg v (-1 = spilled)
let vreg_spill_at = mmap(400000) // vreg_spill_at[v] = block where vreg was spilled
```

## Implementation Order
1. `build_cfg()` — identify blocks, successors, predecessors
2. `liveness()` — backward analysis to compute live_in/live_out
3. `allocate_regs()` — linear scan with block-aware spill/reload
4. Integration with `ci_func` to use block-aware allocator
5. Test: ensure no SIGSEGV, correct results, measure speedup

## Expected Impact
- Eliminate redundant spill/reload at every branch/jump
- For tight loops: ~2-4× speedup (values stay in registers across iterations)
- For if/else: ~1.5-2× (no spill on both sides of branch)
- For function calls: same as current (flush_all at callsites unchanged)

## Risks
- Frame layout: float spill region needs frame extension (already attempted, needs verification)
- ASLR interaction: extending frame by 8192 may cause SIGSEGV on low-stack-base binaries
- Label fixups: IR indices must not change (label fixups rely on stable indices)
- Debug complexity: more complex than per-op allocator, harder to debug

## Verification
- All 811 tests must pass
- Benchmark speedup on compute-heavy loops
- No SIGSEGV on small-stack-base binaries
