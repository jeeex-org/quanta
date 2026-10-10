#!/usr/bin/env python3
"""
Audit every committed fixture expectation in tests/test_read_formats.quanta
against the REAL upstream dequantizers.

WHY THIS SHELLS OUT INSTEAD OF RE-DERIVING
-------------------------------------------
This file started as a set of Python transcriptions of the upstream kernels and
immediately produced two false alarms: it re-derived q5_0 and q5_1 as WRONG when
the committed values were correct, because the Python q5 code guessed at the
`qh` high-half extraction and the -16 bias. Comparing against the real
dequantize_row_* from libggml-base settled it: the committed values were right.

That is the same lesson scripts/audit/c_oracle.c records, and the reason this
file no longer contains a single dequantiser. A transcription is a third thing
that can disagree with the other two; the compiled library cannot.

WHAT IT CHECKS
--------------
For each check_fixture(...) in the test file, reduce the fixture with the real
kernel and compare sum / sumsq / min / max to what is committed.

Two formats (q2_K, q3_K, q8_K) are not covered by blocks_oracle because their
block layouts need the k-quant scale unpacking; those stay covered by
scripts/audit/c_oracle.c, which reads a real GGUF instead of a raw block file.
They are listed as covered rather than silently skipped.

usage: audit_fixtures.py [--verbose]
"""

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TESTFILE = REPO / "tests" / "test_read_formats.quanta"
ORACLE_SRC = REPO / "scripts" / "audit" / "blocks_oracle.c"

GGML_LIBDIR = Path("/home/tali/.local/lib/python3.12/site-packages/lib64")
GGML_INC = Path("/tmp/loader-research/llama.cpp/ggml/include")

# dtype -> (oracle format name, committed-fixture family)
DTYPE_TO_ORACLE = {
    3: ("q4_1", "q4_1"),
    6: ("q5_0", "q5_0"),
    7: ("q5_1", "q5_1"),
    20: ("iq4_nl", "iq4_nl"),
    23: ("iq4_xs", "iq4_xs"),
    39: ("mxfp4", "mxfp4"),
    40: ("nvfp4", "nvfp4"),
}

# Covered by c_oracle.c instead (real GGUF, k-quant unpacking).
COVERED_ELSEWHERE = {
    10: "q2_K",
    11: "q3_K",
    15: "q8_K",
}


def build_oracle(verbose=False):
    """Compile blocks_oracle against the installed ggml. Returns the path."""
    out = Path("/tmp/blocks_oracle")
    cmd = [
        "gcc", "-O2", "-w", "-o", str(out), str(ORACLE_SRC),
        f"-I{GGML_INC}", f"-L{GGML_LIBDIR}", "-lggml-base",
        f"-Wl,-rpath,{GGML_LIBDIR}", "-lm",
    ]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        print("could not build the oracle:\n" + p.stderr[:2000])
        return None
    if verbose:
        print("built " + " ".join(cmd[:4]) + " ...\n")
    return out


def reduce_fixture(oracle, fmt, fixture):
    p = subprocess.run([str(oracle), fmt, str(fixture)],
                       capture_output=True, text=True)
    if p.returncode != 0:
        return None
    vals = {}
    for line in p.stdout.strip().split("\n"):
        parts = line.split()
        if len(parts) == 2:
            vals[parts[0]] = float(parts[1])
    need = ("sum", "sumsq", "min", "max")
    if any(k not in vals for k in need):
        return None
    return tuple(vals[k] for k in need)


def main():
    verbose = '--verbose' in sys.argv
    src = TESTFILE.read_text()

    pat = re.compile(
        r'check_fixture\(\s*"([^"]+)"\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*'
        r'([-\d.e+]+)\s*,\s*([-\d.e+]+)\s*,\s*([-\d.e+]+)\s*,\s*([-\d.e+]+)\s*,\s*"([^"]+)"',
        re.S)

    calls = list(pat.finditer(src))
    todo = [m for m in calls if int(m.group(2)) in DTYPE_TO_ORACLE]

    oracle = build_oracle(verbose) if todo else None
    if todo and oracle is None:
        print("fixture audit: ABORTED, no oracle\n")
        return 1

    bad = 0
    checked = 0
    for m in calls:
        rel, dtype, nbytes, nelem, esum, esumsq, emin, emax, label = m.groups()
        dtype = int(dtype)
        nelem = int(nelem)

        if dtype in COVERED_ELSEWHERE:
            print(f"  {label:8s} dtype {dtype:2d}  covered by scripts/audit/c_oracle.c "
                  f"(real GGUF, k-quant unpack)")
            continue
        if dtype not in DTYPE_TO_ORACLE:
            print(f"  {label:8s} dtype {dtype:2d}  NO ORACLE -- REVIEW")
            bad += 1
            continue

        fmt = DTYPE_TO_ORACLE[dtype][0]
        fixture = REPO / rel
        if not fixture.exists():
            print(f"  {label:8s} MISSING FIXTURE {rel}")
            bad += 1
            continue

        got = reduce_fixture(oracle, fmt, fixture)
        if got is None:
            print(f"  {label:8s} oracle produced no output for {rel}")
            bad += 1
            continue

        ref = (float(esum), float(esumsq), float(emin), float(emax))
        ok = all(abs(a - b) <= 1e-4 + 1e-6 * abs(b) for a, b in zip(got, ref))
        checked += 1
        if not ok:
            bad += 1
        print(f"  {label:8s} dtype {dtype:2d}  {'OK  ' if ok else 'WRONG'}")
        if verbose or not ok:
            print(f"        real ggml : sum={got[0]:.6f} sumsq={got[1]:.6f} "
                  f"min={got[2]:.6f} max={got[3]:.6f}")
            print(f"        committed : sum={ref[0]:.6f} sumsq={ref[1]:.6f} "
                  f"min={ref[2]:.6f} max={ref[3]:.6f}")

    print()
    print(f"fixture audit: {checked} re-derived against real ggml, {bad} wrong")
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())