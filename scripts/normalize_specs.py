#!/usr/bin/env python3
"""scripts/normalize_specs.py -- clean gap_specs.json (the SI roadmap spec data).

Run:  python3 scripts/normalize_specs.py

This is the ONE place the spec-data encoding convention is applied, so the fix is
repeatable and auditable rather than a hand edit of 9,026 records. It is
idempotent: running it twice changes nothing.

Convention (task: "pick ONE encoding convention for generated status fields"):
  * status is PLAIN ASCII and is one of: planned | done | partial
  * priority is a SEPARATE field, one of: "" | low | medium | high | critical
  * version is either the em dash "--" placeholder or a dotted version, never a
    status/priority string

It also records (never silently drops) the cross-domain category contamination and
any duplicate specs into planned/, then rewrites gap_specs.json.
"""
import json, os, re, sys, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

SPECS = 'gap_specs.json'
STATUS_OK = {'planned', 'done', 'partial'}
STATUS_MAP = {
    '\U0001F532 planned': 'planned',   # 🔲 planned
    '\u2705 done': 'done',             # ✅ done
    '\u2705 partial': 'partial',       # ✅ partial
}
PRIO_MAP = {
    '\U0001F7E0 High': 'high',         # 🟠 High
    '\U0001F7E1 Medium': 'medium',     # 🟡 Medium
    '\U0001F534 Critical': 'critical', # 🔴 Critical
}

# Categories under domain=programming_language that are APPLICATION-domain content,
# not language/stdlib capability areas. Their natural domains already exist
# (health/medicine, government, education, retail/wholesale), so they are removed
# from the PL roadmap and recorded verbatim below. Categories such as Audio, Video,
# Robotics, DL, TLS stay: those are stdlib capability areas and several are
# exercised by gate rows (EXPECTED_STDLIB rows programming_language_dl_*,
# _tls_*, _encryption_*, ...).
PL_FOREIGN_CATEGORIES = {'Healthcare', 'Government', 'Education', 'E-Commerce'}


def sanitize(s):
    return re.sub(r'[^0-9A-Za-z]', '_', s).lower()


def main():
    data = json.load(open(SPECS))
    specs = data['specs']

    notes = []          # human-readable change log
    status_fixed = collections.Counter()
    prio_extracted = collections.Counter()
    version_fixed = collections.Counter()

    # ---- 1. normalize status / priority / version --------------------------
    clean = []
    removed = []
    for x in specs:
        st = x['status']
        priority = x.get('priority', '')   # preserve an already-normalized priority
        if st in STATUS_OK:
            norm = st
        elif st in STATUS_MAP:
            norm = STATUS_MAP[st]
            status_fixed[st] += 1
        elif st in PRIO_MAP:
            priority = PRIO_MAP[st]
            norm = 'planned'
            prio_extracted[st] += 1
        else:
            # numeric / markdown / mojibake junk -> planned (recorded)
            norm = 'planned'
            status_fixed[st] += 1

        ver = x['version']
        if ver == '\u2014':            # em dash placeholder
            vnorm = ver
        elif re.match(r'^\d+(\.\d+)+$', ver):
            vnorm = ver
        else:
            vnorm = '\u2014'
            version_fixed[ver] += 1

        # ---- 2. cross-domain contamination (record + drop) -----------------
        if x['domain'] == 'programming_language' and x['category'] in PL_FOREIGN_CATEGORIES:
            removed.append(x)
            continue

        clean.append({
            'domain': x['domain'],
            'category': x['category'],
            'module': x['module'],
            'status': norm,
            'priority': priority,
            'version': vnorm,
            'stdlib': x['stdlib'],
            'notes': x['notes'],
        })

    # ---- 3. exact-duplicate specs (same domain/category/module) ------------
    seen = {}
    dups = []
    for x in clean:
        k = (x['domain'], x['category'], x['module'])
        if k in seen:
            dups.append(x)
        else:
            seen[k] = x

    # ---- 4. cross-domain category map (record only) ------------------------
    cat2dom = collections.defaultdict(set)
    for x in clean:
        cat2dom[x['category']].add(x['domain'])
    shared = sorted((c, sorted(ds)) for c, ds in cat2dom.items() if len(ds) > 1)

    data['specs'] = clean
    with open(SPECS, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=True)
        f.write('\n')

    # ---- 5. write the audit trail -----------------------------------------
    os.makedirs('planned', exist_ok=True)

    with open('planned/CATEGORY_CONTAMINATION.tsv', 'w') as f:
        f.write('# categories that appear in more than one domain (recorded, not dropped)\n')
        f.write('category\tdomains\n')
        for c, ds in shared:
            f.write(f"{c}\t{','.join(ds)}\n")

    with open('planned/SPEC_DATA_NOTES.md', 'w') as f:
        f.write('# gap_specs.json normalization (scripts/normalize_specs.py)\n\n')
        f.write('Regenerate + re-apply with `python3 scripts/normalize_specs.py` '
                '(idempotent).\n\n')
        f.write('## Encoding convention\n\n')
        f.write('- `status` is plain ASCII: one of `planned`, `done`, `partial`.\n')
        f.write('- `priority` is a separate field: `""`, `low`, `medium`, `high`, '
                '`critical`.\n')
        f.write('- `version` is the em-dash placeholder or a dotted version.\n\n')

        f.write('## status values normalized -> planned/done/partial\n\n')
        for k, v in status_fixed.most_common():
            f.write(f"- {v} x {k!r} -> planned\n")
        f.write('\n## priority extracted out of status\n\n')
        for k, v in prio_extracted.most_common():
            f.write(f"- {v} x {k!r} -> priority {PRIO_MAP[k]!r}, status 'planned'\n")
        f.write('\n## version values reset to the em-dash placeholder\n\n')
        for k, v in version_fixed.most_common():
            f.write(f"- {v} x {k!r}\n")

        f.write('\n## cross-domain category contamination\n\n')
        f.write(f"{len(shared)} categories appear in more than one domain; the full "
                "map is in `planned/CATEGORY_CONTAMINATION.tsv`.\n\n")
        f.write('REMOVED from `domain=programming_language` (they are application '
                'content whose natural domains already exist), recorded verbatim:\n\n')
        f.write('| domain | category | module | status | notes |\n')
        f.write('|---|---|---|---|---|\n')
        for x in removed:
            f.write(f"| {x['domain']} | {x['category']} | {x['module']} | "
                    f"{x['status']} | {x['notes']} |\n")
        f.write(f"\n({len(removed)} specs removed.)\n\n")
        f.write('KEPT under `programming_language`: Audio, Video, Robotics, DL, '
                'Encryption, TLS, Hashing, Key Mgmt, PKI, Protocol, OS, Compiler, '
                'VM, Numerical, Serialization, CPU and the rest -- these are stdlib '
                'capability areas and several are exercised by gate rows in '
                'EXPECTED_STDLIB.tsv (programming_language_dl_*, _tls_*, '
                '_encryption_*, ...).\n\n')
        f.write('## exact duplicate specs (recorded, not dropped)\n\n')
        if dups:
            for x in dups:
                f.write(f"- {x['domain']}/{x['category']}/{x['module']}\n")
        else:
            f.write('- none\n')
        f.write('\n')

    print(f"gap_specs.json normalized: {len(specs)} -> {len(clean)} specs")
    print(f"  status fixed={sum(status_fixed.values())} "
          f"priority extracted={sum(prio_extracted.values())} "
          f"version fixed={sum(version_fixed.values())}")
    print(f"  removed from programming_language={len(removed)} "
          f"(Healthcare/Government/Education/E-Commerce)")
    print(f"  duplicate specs recorded={len(dups)}")
    print(f"  wrote planned/SPEC_DATA_NOTES.md, planned/CATEGORY_CONTAMINATION.tsv")


if __name__ == '__main__':
    main()
