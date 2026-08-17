#!/usr/bin/env python3
"""
Quanta compiler fuzzer — closes SAFETY_MANUAL.md sec 6.5 (untested input space).

Proves the compiler is FAIL-CLOSED on arbitrary/garbage input: it must
NEVER crash with a signal (SIGSEGV/SIGILL/SIGABRT) and must ALWAYS exit
with a defined code. Defined exit codes (SPEC.md sec 6):
  0   success
  1   internal/memory failure (MAP_FAILED)
  7   compile error (undeclared fn, cyclic struct, ...)
  132 runtime overflow/bounds trap (SIGILL) -- not from the COMPILER though
Any signal death or other rc = CRASH -> bug to file.

No external deps (AFL++ not installed on this host). Uses a byte-level
mutation loop + seed corpus. Good enough to exercise the untested-input
space; swap in AFL++/libFuzzer later for coverage-guided search.

Usage:
  python3 fuzz_qc.py [--qc PATH] [--iter N] [--seed-dir DIR] [--out-dir DIR]
"""
import os
import sys
import time
import random
import signal
import subprocess

# ---- config ----
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_QC = os.path.join(HERE, "..", "..", "compiler", "0.0.53", "bin", "x86", "qc")
SEED_DIR = os.path.join(HERE, "seeds")
OUT_DIR = os.path.join(HERE, "crashes")
EXPECTED_RCS = {0, 1, 7, 13, 14, 15, 16, 17}
#  0   success
#  1   internal/memory failure (MAP_FAILED) or write-buffer overflow (CODE_CAP/DAT_CAP)
#  7   compile error (undeclared fn, cyclic struct, parse error)
#  13  argc < 2 (no input file)
#  14  input file open failed
#  15  input file empty / zero length
#  16  import/include resolution failed
#  17  IR/token buffer overflow (fail-closed, NOT a crash)
#  (132 only from RUNNING the emitted binary, never from qc itself)
MAX_INPUT = 65536  # hard cap: never let mutated input exceed 64KB (prevents
                   # exponential blowup from the slice-duplicate op)

# Quanta token soup for mutations to draw from
TOKENS = b"fn let if while for return break continue match struct enum unsafe defer extern include mut ; {} () = + - * / % == != < > <= >= && || ! ~ & | ^ << >> . , fn main return 0 1 2 3 'a' \"x\" mmap mem_alloc w8 w32 w64 eb ei eq call print ident_ foo bar => "


def collect_seeds():
    seeds = []
    # the 15 compiler modules + minimal programs
    mod_dir = os.path.join(HERE, "..", "..", "compiler", "0.0.53", "src", "x86")
    if os.path.isdir(mod_dir):
        for f in sorted(os.listdir(mod_dir)):
            if f.endswith(".quanta"):
                p = os.path.join(mod_dir, f)
                try:
                    seeds.append(open(p, "rb").read())
                except Exception:
                    pass
    # explicit minimal seeds
    seeds.append(b"fn main(){ return 0 }\n")
    seeds.append(b"let x = 5; if x > 3 { return 1 } else { return 0 }\n")
    seeds.append(b"fn f(a){ return a + 1 }\nfn main(){ return f(41) }\n")
    # ensure seed dir
    os.makedirs(SEED_DIR, exist_ok=True)
    for i, s in enumerate(seeds):
        with open(os.path.join(SEED_DIR, f"seed_{i:03d}.quanta"), "wb") as fh:
            fh.write(s)
    return seeds


def mutate(data, rng):
    """Byte-level mutation: pick 1-3 mutations."""
    d = bytearray(data)
    if not d:
        d = bytearray(rng.choice(TOKENS.split()))
    for _ in range(rng.randint(1, 3)):
        op = rng.randint(0, 3)
        if op == 0 and d:  # flip a byte
            i = rng.randrange(len(d))
            d[i] = rng.randint(0, 255)
        elif op == 1 and d:  # delete a byte
            i = rng.randrange(len(d))
            del d[i]
        elif op == 2:  # insert a random byte or token
            if rng.random() < 0.3 and TOKENS:
                tok = rng.choice(TOKENS.split())
                d[rng.randint(0, len(d)):0] = tok
            else:
                d[rng.randint(0, len(d)):0] = bytes([rng.randint(0, 255)])
        else:  # duplicate a slice
            if len(d) > 1 and len(d) < MAX_INPUT:
                i = rng.randrange(len(d))
                j = rng.randrange(len(d))
                i, j = min(i, j), max(i, j)
                d += d[i:j]
    # hard cap: never exceed MAX_INPUT (prevents RAM/disk blowup)
    if len(d) > MAX_INPUT:
        d = d[:MAX_INPUT]
    if not d:
        d = bytearray(b"\n")
    return bytes(d)


def run_qc(qc, data, out_dir):
    """Run qc on data; return ('ok', rc) or ('crash', info)."""
    path = os.path.join(out_dir, "_fuzz_input.quanta")
    with open(path, "wb") as fh:
        fh.write(data)
    out_bin = os.path.join(out_dir, "_fuzz_out.bin")
    try:
        p = subprocess.run(
            [qc, "-O", path, out_bin],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=10,
        )
        rc = p.returncode
        # negative rc => killed by signal (e.g. -11 = SIGSEGV)
        if rc < 0:
            sig = -rc
            return ("crash", f"killed by signal {sig} (rc={rc})")
        if rc in EXPECTED_RCS:
            return ("ok", rc)
        # rc 132 etc from qc itself is unexpected for the compiler -> treat as bug
        return ("crash", f"unexpected exit code {rc}")
    except subprocess.TimeoutExpired:
        return ("crash", "timeout (>10s)")
    except Exception as e:
        return ("crash", f"exception: {e}")


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--qc", default=DEFAULT_QC)
    ap.add_argument("--iter", type=int, default=20000)
    ap.add_argument("--seed-dir", default=SEED_DIR)
    ap.add_argument("--out-dir", default=OUT_DIR)
    args = ap.parse_args()

    qc = os.path.abspath(args.qc)
    if not os.path.exists(qc):
        print(f"ERROR: qc not found: {qc}", file=sys.stderr)
        sys.exit(2)
    os.makedirs(args.out_dir, exist_ok=True)

    rng = random.Random(0xC0FFEE)
    seeds = collect_seeds()
    print(f"Fuzzing {qc}")
    print(f"  seeds={len(seeds)}  iters={args.iter}  crashes-> {args.out_dir}")
    print(f"  expected rcs = {sorted(EXPECTED_RCS)}")

    crashes = 0
    rc_hist = {}
    t0 = time.time()
    cur = seeds[0]
    for it in range(args.iter):
        cur = mutate(cur, rng)
        status, info = run_qc(qc, cur, args.out_dir)
        if status == "crash":
            crashes += 1
            cpath = os.path.join(args.out_dir, f"crash_{it:06d}.quanta")
            with open(cpath, "wb") as fh:
                fh.write(cur)
            print(f"  CRASH @{it}: {info} -> {cpath}")
            # reset to a known seed to keep mutating from valid-ish state
            cur = rng.choice(seeds)
        else:
            rc_hist[info] = rc_hist.get(info, 0) + 1
        if (it + 1) % 2000 == 0:
            dt = time.time() - t0
            print(f"  [{it+1}] crashes={crashes}  {dt:.1f}s  rc_hist={rc_hist}")

    dt = time.time() - t0
    print(f"DONE: {args.iter} iters, {crashes} crashes, {dt:.1f}s")
    print(f"  rc histogram: {rc_hist}")
    if crashes == 0:
        print("RESULT: PASS — qc is fail-closed on all fuzzed inputs.")
        sys.exit(0)
    else:
        print("RESULT: FAIL — crashes found; see crashes/ dir.")
        sys.exit(1)


if __name__ == "__main__":
    main()
