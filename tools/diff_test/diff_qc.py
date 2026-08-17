#!/usr/bin/env python3
"""
Quanta differential (cross-implementation) test — addresses SAFETY_MANUAL.md
sec 6.2 (independent implementation route for ISO 26262-8 / IEC 61508-3).

Quanta has ONE self-hosting compiler. To get cross-implementation confidence
without a second hand-written compiler, we compare the CURRENT compiler
(qc_self, rebuilt from source) against an INDEPENDENT artifact from a
different point in history: the bootstrap seed qc-bootstrap-0.0.45.

For each reference program:
  1. compile with CURRENT qc  -> binA, run binA -> rcA
  2. compile with SEED    qc  -> binB, run binB -> rcB
  3. assert rcA == rcB  (behavioral parity)
  4. (optional) assert binA byte-identical to binB for stable programs

If both compilers agree on exit behavior across the suite, that is evidence
the implementation is deterministic and not a one-off accident — a weak but
real form of independent cross-check. When the ARM64 backend lands (Stage 4),
this harness extends to x86-vs-ARM64 differential (two truly independent
emitters over the same IR).

Usage:
  python3 diff_qc.py [--current QC] [--seed QC] [--prog-dir DIR] [--out DIR]
"""
import os
import sys
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CURRENT = os.path.join(HERE, "..", "..", "compiler", "0.0.53", "bin", "x86", "qc")
DEFAULT_SEED = "/opt/tali/quanta/bootstrap/qc-bootstrap-0.0.45"


def run(cmd):
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return -9, b"", b"timeout"


def compile_and_run(qc, src, out_bin):
    rc_c, _, err_c = run([qc, "-O", src, out_bin])
    if rc_c != 0:
        return rc_c, None, err_c  # compile failed
    os.chmod(out_bin, 0o755)
    rc_r, _, _ = run([out_bin])
    return 0, rc_r, err_c  # rc_r = runtime exit code


def collect_progs(prog_dir):
    progs = []
    if os.path.isdir(prog_dir):
        for f in sorted(os.listdir(prog_dir)):
            if f.endswith(".quanta"):
                progs.append(os.path.join(prog_dir, f))
    # fallback minimal reference set
    if not progs:
        ref = [
            "fn main(){ return 0 }",
            "fn main(){ let x=5; if x>3 { return 1 } else { return 2 } }",
            "fn f(a){ return a+1 } fn main(){ return f(41) }",
            "fn main(){ let s=0; let i=0; while i<10 { s=s+i; i=i+1 } return s }",
            "fn main(){ let a=[1,2,3]; return a[1] }",
        ]
        os.makedirs(prog_dir, exist_ok=True)
        for i, s in enumerate(ref):
            p = os.path.join(prog_dir, f"ref_{i}.quanta")
            open(p, "w").write(s + "\n")
            progs.append(p)
    return progs


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--current", default=DEFAULT_CURRENT)
    ap.add_argument("--seed", default=DEFAULT_SEED)
    ap.add_argument("--prog-dir", default=os.path.join(HERE, "programs"))
    ap.add_argument("--out", default=os.path.join(HERE, "out"))
    args = ap.parse_args()

    cur = os.path.abspath(args.current)
    seed = os.path.abspath(args.seed)
    for qc, name in [(cur, "current"), (seed, "seed")]:
        if not os.path.exists(qc):
            print(f"ERROR: {name} qc not found: {qc}", file=sys.stderr)
            sys.exit(2)
    os.makedirs(args.out, exist_ok=True)
    progs = collect_progs(args.prog_dir)

    print(f"Differential test")
    print(f"  current : {cur}")
    print(f"  seed    : {seed}")
    print(f"  programs: {len(progs)}")

    mismatches = 0
    for i, src in enumerate(progs):
        outA = os.path.join(args.out, f"binA_{i}")
        outB = os.path.join(args.out, f"binB_{i}")
        rcA_c, rcA_r, errA = compile_and_run(cur, src, outA)
        rcB_c, rcB_r, errB = compile_and_run(seed, src, outB)
        # both must compile, and runtime rcs must match
        if rcA_c != 0 or rcB_c != 0:
            print(f"  MISMATCH [{i}] compile cur={rcA_c} seed={rcB_c} :: {os.path.basename(src)}")
            mismatches += 1
            continue
        if rcA_r != rcB_r:
            print(f"  MISMATCH [{i}] runtime cur={rcA_r} seed={rcB_r} :: {os.path.basename(src)}")
            mismatches += 1
            continue
        # byte-identical check (informational)
        bA = open(outA, "rb").read()
        bB = open(outB, "rb").read()
        ident = "IDENTICAL" if bA == bB else f"diff({len(bA)}vs{len(bB)})"
        print(f"  [{i}] ok rc={rcA_r} bins={ident} :: {os.path.basename(src)}")

    print(f"\nRESULT: {len(progs)-mismatches}/{len(progs)} programs agree across both compilers.")
    if mismatches == 0:
        print("PASS — current and seed compilers are behaviorally consistent.")
        sys.exit(0)
    else:
        print(f"FAIL — {mismatches} mismatch(es).")
        sys.exit(1)


if __name__ == "__main__":
    main()
