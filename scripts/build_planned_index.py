#!/usr/bin/env python3
"""scripts/build_planned_index.py -- rebuild planned/INDEX.tsv (the SI manifest).

Run:  python3 scripts/build_planned_index.py

planned/ holds the generated stubs and tests that were moved out of lib/std and
test_suites/codes. Their CONTENTS are the byte-identical historical record, so
they are never rewritten; this script only rebuilds the DERIVED manifest that
makes every count reproducible by command.

Columns:
  path domain category module status version status_norm priority
    * status/version are the raw values as they appear in the file header
      (useful for auditing the original defects: mojibake, priority-in-status);
    * status_norm/priority apply the ONE encoding convention
      (scripts/normalize_specs.py): status in {planned,done,partial}, priority in
      {"",low,medium,high,critical}.
Header fields absent from a test file are derived from its paired module stub.
"""
import os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

KEYS = ('Domain', 'Category', 'Module', 'Status', 'Version')
STATUS_OK = {'planned', 'done', 'partial'}
STATUS_MAP = {
    '\U0001F532 planned': 'planned',
    '\u2705 done': 'done',
    '\u2705 partial': 'partial',
}
PRIO_MAP = {
    '\U0001F7E0 High': 'high',
    '\U0001F7E1 Medium': 'medium',
    '\U0001F534 Critical': 'critical',
}


def parse(path):
    d = {}
    for ln in open(path, errors='replace').read(800).split('\n'):
        if '//' not in ln:
            continue
        for seg in ln.split('//', 1)[1].split('|'):
            m = re.match(r'\s*([A-Za-z]+)\s*:\s*(.*)$', seg)
            if m and m.group(1) in KEYS and m.group(1) not in d:
                d[m.group(1)] = m.group(2).strip()
    return d


def normalize_status(raw):
    if raw in STATUS_OK:
        return raw, ''
    if raw in STATUS_MAP:
        return STATUS_MAP[raw], ''
    if raw in PRIO_MAP:
        return 'planned', PRIO_MAP[raw]
    return 'planned', ''


def main():
    # module lookup (slug -> domain/category/module) from the module stubs
    modmap = {}
    for f in os.listdir('planned/lib_std'):
        d = parse('planned/lib_std/' + f)
        modmap[f[:-7]] = (d.get('Domain', ''), d.get('Category', ''), d.get('Module', ''))

    out = ['path\tdomain\tcategory\tmodule\tstatus\tversion\tstatus_norm\tpriority']
    for dirp in ('planned/lib_std', 'planned/tests'):
        for f in sorted(os.listdir(dirp)):
            d = parse(f'{dirp}/{f}')
            dom, cat, mod = d.get('Domain', ''), d.get('Category', ''), d.get('Module', '')
            if not dom and dirp == 'planned/tests':
                slug = f[:-7]
                if slug.startswith('std_'):
                    slug = slug[4:]
                if slug.endswith('_const_test'):
                    slug = slug[:-11]
                if slug in modmap:
                    dom, cat, mod = modmap[slug]
            st = d.get('Status', '')
            snorm, prio = normalize_status(st)
            out.append(f"{dirp}/{f}\t{dom}\t{cat}\t{mod}\t{st}\t{d.get('Version','')}\t{snorm}\t{prio}")

    with open('planned/INDEX.tsv', 'w') as fh:
        fh.write('\n'.join(out) + '\n')
    print(f"wrote planned/INDEX.tsv: {len(out)-1} rows")


if __name__ == '__main__':
    main()
