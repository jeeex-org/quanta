#!/usr/bin/env python3
"""Phase-3 opcode-multiset accounting for the byte-identity differing rows.

For every EXPECTED.tsv row that is NOT byte-identical between the predecessor golden
and the new golden, disassemble both emitted executables and compare the instruction
MULTISET (full instruction text, so a `mov` that only changed its operand counts as a
change; similarly a register RENAME counts as one added and one removed instruction,
which is exactly the discriminator this test needs).

The F2 lever claims to remove dead home stores and nothing else, so for every
differing row:

    new_multiset - old_multiset  MUST be empty      (nothing added, nothing renamed)
    old_multiset - new_multiset  MUST contain only   (only home stores removed)
        mov-family instructions whose destination is -N(%rbp[,...])

Exit 0 only if every differing row satisfies both. Usage:
    objdump_multiset_diff.py <old_qc> <new_qc> [expected.tsv] [workdir]
"""
import collections
import os
import re
import subprocess
import sys
import tempfile

REPO = "/opt/tali/quanta"
OLD, NEW = sys.argv[1], sys.argv[2]
EXP = sys.argv[3] if len(sys.argv) > 3 else f"{REPO}/test_suites/EXPECTED.tsv"
WD = sys.argv[4] if len(sys.argv) > 4 else tempfile.mkdtemp(prefix="msdiff.")

HOME_STORE = re.compile(r"^(mov|movz|movs)[a-z]*\s+.*%[a-z0-9]+,\s*-[x0-9a-f]*\(%rbp")


def instrs(binary):
    out = subprocess.run(["objdump", "-d", "--no-show-raw-insn", binary],
                         capture_output=True, text=True).stdout
    c = collections.Counter()
    for line in out.splitlines():
        m = re.match(r"^\s*[0-9a-f]+:\t(.+)$", line)
        if m:
            c[m.group(1).strip()] += 1
    return c


def build(qc, src, out):
    if os.path.exists(out):
        os.unlink(out)
    try:
        subprocess.run([qc, "-O", src, out], capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        return False
    return os.path.exists(out) and os.path.getsize(out) > 0


rows = []
with open(EXP) as f:
    for line in f:
        parts = line.rstrip("\n").split("\t")
        if parts and parts[0]:
            rows.append(parts[0])

ok = 0
bad = 0
identical = 0
cfail = 0
bad_rows = []
for name in rows:
    src = f"{REPO}/test_suites/codes/{name}"
    a, b = f"{WD}/{name}.old", f"{WD}/{name}.new"
    if not (build(OLD, src, a) and build(NEW, src, b)):
        cfail += 1
        continue
    with open(a, "rb") as fa, open(b, "rb") as fb:
        if fa.read() == fb.read():
            identical += 1
            continue
    ca, cb = instrs(a), instrs(b)
    added = list((cb - ca).elements())
    removed = list((ca - cb).elements())
    nonstore = [t for t in removed if not HOME_STORE.match(t)]
    if not added and not nonstore:
        ok += 1
    else:
        bad += 1
        bad_rows.append((name, len(added), added[:4], len(nonstore), nonstore[:4]))

print(f"rows={len(rows)} identical={identical} differing={ok + bad} compile-fail={cfail}")
print(f"  differing rows where the ONLY change is removed home stores: {ok}")
print(f"  differing rows with any other change:                        {bad}")
for r in bad_rows[:10]:
    print(f"    BAD {r[0]}: +{r[1]} instrs (e.g. {r[2]}), non-store removals={r[3]} (e.g. {r[4]})")
sys.exit(0 if bad == 0 and cfail == 0 else 1)
