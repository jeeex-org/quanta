#!/usr/bin/env python3
"""Opcode-sequence accounting for the byte-identity differing rows.

WHY `--emit-obj` AND NOT `-O`: the executables this compiler writes carry NO section
headers (`readelf -S` -> "There are no sections in this file"), so `objdump -d` prints
nothing for them. An earlier version of this script compared the resulting EMPTY
instruction lists and therefore reported "only home stores were removed" VACUOUSLY for
every row. It now compiles with `--emit-obj` (a relocatable object, which does have
sections -- the same artefact `scripts/bench_instr.sh` uses) and it REFUSES to report a
verdict when either side disassembles to fewer than 10 instructions.

For every EXPECTED.tsv row it compares the instruction SEQUENCE with difflib, not just
the multiset: a register swap preserved by a multiset (e.g. `test %rax,%rax` ->
`test %rdx,%rdx`) is invisible to a Counter but is exactly the kind of change this
check is supposed to see.

Reports, per row: deleted / inserted / replaced instruction blocks, and whether every
DELETED instruction is a frame-relative store (`mov* reg,-N(%rbp)`) -- which is the F2
lever's whole claim. Usage:
    objdump_seq_diff.py <old_qc> <new_qc> [expected.tsv] [workdir]
"""
import collections
import difflib
import os
import re
import subprocess
import sys
import tempfile

REPO = "/opt/tali/quanta"
OLD, NEW = sys.argv[1], sys.argv[2]
EXP = sys.argv[3] if len(sys.argv) > 3 else f"{REPO}/test_suites/EXPECTED.tsv"
WD = sys.argv[4] if len(sys.argv) > 4 else tempfile.mkdtemp(prefix="seqdiff.")

HOME_STORE = re.compile(r"^(mov|movz|movs)[a-z]*\s+.*%[a-z0-9]+,\s*-[x0-9a-f]*\(%rbp")
MIN_INSTR = 10


def instrs(obj):
    out = subprocess.run(["objdump", "-d", "--no-show-raw-insn", obj],
                         capture_output=True, text=True).stdout
    res = []
    for line in out.splitlines():
        m = re.match(r"^\s*[0-9a-f]+:\t(.+)$", line)
        if m:
            res.append(m.group(1).strip())
    return res


def build(qc, src, out):
    if os.path.exists(out):
        os.unlink(out)
    try:
        subprocess.run([qc, "--emit-obj", src, out], capture_output=True,
                       text=True, timeout=180)
    except subprocess.TimeoutExpired:
        return False
    return os.path.exists(out) and os.path.getsize(out) > 0


rows = []
with open(EXP) as f:
    for line in f:
        p = line.rstrip("\n").split("\t")
        if p and p[0]:
            rows.append(p[0])

ident = cfail = bad = ok = 0
tot_del = tot_ins = 0
nonstore = collections.Counter()
inserted = collections.Counter()
replaced = collections.Counter()
bad_rows = []
for name in rows:
    src = f"{REPO}/test_suites/cases_placeholder"
    src = f"{REPO}/test_suites/codes/{name}"
    a, b = f"{WD}/{name}.old.o", f"{WD}/{name}.new.o"
    if not (build(OLD, src, a) and build(NEW, src, b)):
        cfail += 1
        continue
    ca, cb = instrs(a), instrs(b)
    if len(ca) < MIN_INSTR or len(cb) < MIN_INSTR:
        cfail += 1
        print(f"  REFUSED {name}: disassembly too short (old={len(ca)} new={len(cb)})")
        continue
    if ca == cb:
        ident += 1
        continue
    sm = difflib.SequenceMatcher(a=ca, b=cb, autojunk=False)
    row_ok = True
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        dels, inss = ca[i1:i2], cb[j1:j2]
        tot_del += len(dels)
        tot_ins += len(inss)
        for d in dels:
            if not HOME_STORE.match(d):
                nonstore[d] += 1
                row_ok = False
        for x in inss:
            inserted[x] += 1
        if tag == "replace":
            for d, x in zip(dels, inss):
                replaced[f"{d}  ==>  {x}"] += 1
    if row_ok:
        ok += 1
    else:
        bad += 1
        bad_rows.append(name)

print(f"rows={len(rows)} identical={ident} differing={ok + bad} "
      f"differing-ok={ok} differing-with-non-store-deletes={bad} refused/compile-fail={cfail}")
print(f"deleted instructions: {tot_del}   inserted instructions: {tot_ins}")
print(f"rows where EVERY deleted instruction is a frame-relative store: {ok}")
print(f"distinct inserted instruction texts: {len(inserted)}")
for t, c in inserted.most_common(10):
    print(f"   INS x{c:<4} {t}")
print(f"distinct non-store deletions: {len(nonstore)}")
for t, c in nonstore.most_common(10):
    print(f"   DEL x{c:<4} {t}")
print("replace pairs (top 8):")
for t, c in replaced.most_common(8):
    print(f"   x{c:<4} {t}")
if bad_rows:
    print("rows with a non-store deletion (first 5):", bad_rows[:5])
sys.exit(0 if bad == 0 and cfail == 0 else 1)
