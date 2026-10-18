#!/usr/bin/env python3
"""tests/lfm2_f32_ab_analyze.py -- reduce the f32 end-to-end A/B arm logs.

WHY A SCRIPT AND NOT A HAND-READ TABLE. This box's available core count swings by
2.5x INSIDE a single arm, and loadavg is a one-minute average that lags it: the
first eight-arm run produced arm means of 1.93-4.96 tok/s that did not track
loadavg at all. So the arms are reduced in a fixed way (min over each arm's runs =
its least-interfered sample, plus the mean for the record) and the PAIRS of the
palindrome are compared, because the two members of a pair bracket each other in
time.

Usage: python3 tests/lfm2_f32_ab_analyze.py <logdir> [<logdir> ...]
"""
import re
import sys
import os
from collections import OrderedDict

ARMS = ["off1", "f64fma", "f32", "f32fma", "f32fma2", "f322", "f64fma2", "off2"]


def load_dir(d, out):
    for a in ARMS:
        p = os.path.join(d, "arm_%s.log" % a)
        if not os.path.exists(p):
            continue
        t = open(p).read()
        cfg = re.findall(r'fused_fma=(\d) fused_f32=(\d)', t)
        act = re.findall(r'fused_f32_active=(\d)', t)
        drp = re.findall(r'fused_f32_drop=(\d)', t)
        wit = re.findall(r'fused_f32_used=(\d+) fma_used=(\d+)', t)
        xe = [int(x) for x in re.findall(r'xf32_elems=(\d+)', t)]
        tok = [int(x) for x in re.findall(r'tok_per_s_x1000=(\d+)', t)]
        ms = [int(x) for x in re.findall(r'ms_per_token_x100=(\d+)', t)]
        lab = [float(x) for x in re.findall(r'^--- arm .*load_before=([\d.]+)', t, re.M)]
        if not tok:
            continue
        out.append(dict(dir=d, arm=a,
                        f32=cfg[0][1] if cfg else "?", fma=cfg[0][0] if cfg else "?",
                        active=act[0] if act else "?", drop=drp[0] if drp else "?",
                        wit=wit[-1] if wit else None,
                        xe=xe[-1] if xe else 0,
                        tok=tok, ms=ms, load=lab[0] if lab else -1.0))


def main():
    rows = []
    for d in sys.argv[1:]:
        load_dir(d, rows)
    if not rows:
        print("no arm logs found")
        return 1

    print("%-22s %-4s %-4s %-6s %-8s %-9s %-9s %-9s %s"
          % ("run/arm", "f32", "fma", "l0", "wit", "min_tok", "mean_tok",
             "min_ms", "runs_tok/s"))
    for r in rows:
        print("%-22s %-4s %-4s %-6.2f %-8s %-9.3f %-9.3f %-9.2f %s"
              % (os.path.basename(r["dir"]) + "/" + r["arm"], r["f32"], r["fma"],
                 r["load"], "%s/%s" % r["wit"] if r["wit"] else "-",
                 max(r["tok"]) / 1000.0, sum(r["tok"]) / len(r["tok"]) / 1000.0,
                 min(r["ms"]) / 100.0,
                 "/".join("%.2f" % (x / 1000.0) for x in r["tok"])))

    # per-arm best over ALL runs of ALL dirs = the least-interfered sample
    best = OrderedDict()
    for r in rows:
        key = (r["f32"], r["fma"])
        mt = max(r["tok"])
        if key not in best or mt > best[key]:
            best[key] = mt
    print()
    print("least-interfered (max tok/s) per configuration, over every arm run:")
    for k in sorted(best):
        print("  f32=%s fma=%s  %8.3f tok/s  %7.2f ms/token  (%.2fx of the f64 best)"
              % (k[0], k[1], best[k] / 1000.0, 100000.0 / best[k],
                 0.0))
    if ("1", "0") in best and ("0", "0") in best:
        print()
        print("  f32=1 fma=0 over f32=0 fma=0 : %.3fx   (min-ms basis)"
              % (best[("1", "0")] / float(best[("0", "0")])))
    if ("1", "1") in best and ("0", "0") in best:
        print("  f32=1 fma=1 over f32=0 fma=0 : %.3fx"
              % (best[("1", "1")] / float(best[("0", "0")])))
    if ("0", "1") in best and ("0", "0") in best:
        print("  f32=0 fma=1 over f32=0 fma=0 : %.3fx"
              % (best[("0", "1")] / float(best[("0", "0")])))
    # the paired members
    print()
    print("palindrome pairs (the two members bracket each other in time):")
    for lo, hi in (("off1", "off2"), ("f64fma", "f64fma2"), ("f32", "f322"),
                   ("f32fma", "f32fma2")):
        for d in sys.argv[1:]:
            a = [r for r in rows if r["dir"] == d and r["arm"] == lo]
            b = [r for r in rows if r["dir"] == d and r["arm"] == hi]
            if a and b:
                print("  %-10s %s: best %.3f / %.3f tok/s   loads %.2f / %.2f"
                      % (os.path.basename(d), lo + "+" + hi,
                         max(a[0]["tok"]) / 1000.0, max(b[0]["tok"]) / 1000.0,
                         a[0]["load"], b[0]["load"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
