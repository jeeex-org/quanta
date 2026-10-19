#!/usr/bin/env python3
"""Negative controls for the f32 chain kernel's execution verifier.

Copies tests/lfm2_f32_enc_bytes.h and corrupts ONE named sequence's bytes, then
compiles tests/lfm2_f32_enc_verify.c against it and reports how many FAIL lines
the harness prints. A negative control that does NOT make the harness print the
expected failure proves the harness cannot fail -- i.e. it is not evidence.

Usage: python3 tests/lfm2_f32_enc_negctl.py
"""
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HDR = os.path.join(ROOT, "tests/lfm2_f32_enc_bytes.h")
SRC = os.path.join(ROOT, "tests/lfm2_f32_enc_verify.c")
WORK = "/tmp/negctl"


def load_entries(text):
    """name -> (len, [byte ints])"""
    out = {}
    for m in re.finditer(r'\{ "([^"]+)", (\d+), \{ ([^}]*) \} \}', text):
        bs = [int(x.strip(), 16) for x in m.group(3).split(",") if x.strip()]
        out[m.group(1)] = [int(m.group(2)), bs]
    return out


def emit(text, name, newbytes):
    m = re.search(r'\{ "%s", (\d+), \{ ([^}]*) \} \}' % re.escape(name), text)
    assert m, name
    row = ", ".join("0x%02x" % b for b in newbytes)
    rep = '{ "%s", %d, { %s } }' % (name, len(newbytes), row)
    return text[:m.start()] + rep + text[m.end():]


def run():
    if os.path.isdir(WORK):
        shutil.rmtree(WORK)
    os.makedirs(WORK)
    shutil.copy(SRC, WORK)
    orig = open(HDR).read()
    ent = load_entries(orig)

    # (tag, sequence, mutated bytes, expected FAIL substring)
    controls = [
        ("c_pl1 imm 0x55->0x54 (lane 1 -> lane 0)",
         "c_pl1", [0xc4, 0x63, 0x79, 0x04, 0xc6, 0x54],
         "lane-relative single-lane broadcast"),
        ("c_ext imm 1->0 (high half -> low half)",
         "c_ext", [0xc4, 0xe3, 0x7d, 0x19, 0xf7, 0x00],
         "did not take the HIGH 128 bits"),
        ("c_add0 vaddss->vaddps (clobbers lanes 1-3)",
         "c_add0", [0xc5, 0xf8, 0x58, 0xc6],
         "vaddps, not a vaddss"),
        ("c_pl7 corrupted to lane 1 (W beats the reference)",
         "c_pl7", [0xc4, 0x63, 0x79, 0x04, 0xc7, 0x55],
         "chain fold is not"),
        ("c_widen -> vcvtss2sd xmm1 (xmm0 left untouched)",
         "c_widen", [0xc5, 0xfa, 0x5a, 0xc8],
         "exact f32->f64 widen"),
    ]

    bad = 0
    for tag, name, nb, want in controls:
        text = emit(orig, name, nb)
        open(os.path.join(WORK, "lfm2_f32_enc_bytes.h"), "w").write(text)
        b = os.path.join(WORK, "ncbin")
        r = subprocess.run(["gcc", "-O1", "-o", b, os.path.join(WORK, "lfm2_f32_enc_verify.c")], capture_output=True, text=True)
        if r.returncode != 0:
            print("NC '%s': DID NOT COMPILE\n%s" % (tag, r.stderr))
            bad += 1
            continue
        out = subprocess.run([b], capture_output=True, text=True).stdout
        hits = [ln for ln in out.splitlines() if ln.startswith("FAIL") and want in ln]
        if hits:
            print("NC '%s': OK -- harness printed the expected FAIL" % tag)
        else:
            print("NC '%s': *** HARNESS DID NOT FAIL *** (expected %r)" % (tag, want))
            bad += 1

    # and the un-mutated header must still pass, or the controls prove nothing
    open(os.path.join(WORK, "lfm2_f32_enc_bytes.h"), "w").write(orig)
    b = os.path.join(WORK, "okbin")
    subprocess.run(["gcc", "-O1", "-o", b, os.path.join(WORK, "lfm2_f32_enc_verify.c")], capture_output=True, text=True)
    tail = subprocess.run([b], capture_output=True, text=True).stdout.splitlines()[-1]
    print("control (un-mutated): %s" % tail)
    if "PASS" not in tail:
        bad += 1

    print("%d control(s) failed" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(run())
