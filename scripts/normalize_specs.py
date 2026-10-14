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
# (health/medicine, government, education, retail/wholesale, insurance, logistics),
# so they are removed from the PL roadmap and recorded verbatim in the notes below.
#
#   Healthcare, Government, Education, E-Commerce -- removed in the 318dec22 pass.
#   Audio     -- the whole category is redundant WITHIN PL: its codec modules
#                (Processing/Compression) duplicate Video/Processing+Compression and
#                its Recognition/Synthesis pair duplicates Speech/ASR+TTS, and Audio
#                is itself a content category under entertainment/electronics. It is
#                an application-domain name, not a language capability.
#   Insurance -- the insurance vertical's own operations (Policy/Claims/Actuarial);
#                the natural domain `insurance` already exists.
#   SCM       -- the logistics vertical's own operations (Supply Chain/Procurement/
#                Warehouse/Logistics); the natural domain `logistics` already exists
#                and `Logistics` is literally one of the modules.
#
# Categories such as Video, Robotics, DL, TLS stay: those are stdlib capability
# areas and several are exercised by gate rows (EXPECTED_STDLIB rows
# programming_language_dl_*, _tls_*, _encryption_*, ...). Borderline categories were
# considered and KEPT because a library/framework is a plausible language
# capability: Trading (algorithmic trading), Payments/ERP/Collaboration (SDK /
# protocol integrations), PCB (EDA), Messaging (broker clients), Mobile/Desktop
# (platform targets).
PL_FOREIGN_CATEGORIES = {
    'Healthcare', 'Government', 'Education', 'E-Commerce',   # 318dec22 pass
    'Audio', 'Insurance', 'SCM',                              # this pass
}

# One-line "why foreign" per removed category, written into the audit notes.
PL_FOREIGN_REASONS = {
    'Healthcare': 'medical vertical (health/medicine domains exist)',
    'Government': 'public-sector vertical (government domain exists)',
    'Education': 'education vertical (education domain exists)',
    'E-Commerce': 'retail vertical (retail/wholesale domains exist)',
    'Audio': 'content category under entertainment/electronics; redundant within '
             'PL (codecs duplicate Video, Recognition/Synthesis duplicate Speech)',
    'Insurance': 'insurance vertical operations (insurance domain exists)',
    'SCM': 'logistics vertical operations (logistics domain exists; module '
           'literally named "Logistics")',
}


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

    # Preserve the verbatim removal rows from the PREVIOUS run. This must be read
    # BEFORE the notes file is opened for writing below -- `open(...,'w')`
    # truncates immediately, so a read inside the writing block sees an empty file.
    START = '<!-- removed-verbatim:start -->'
    END = '<!-- removed-verbatim:end -->'
    prev_rows = []
    if os.path.exists('planned/SPEC_DATA_NOTES.md'):
        _old = open('planned/SPEC_DATA_NOTES.md').read()
        if START in _old and END in _old:
            prev_rows = [l for l in _old.split(START, 1)[1].split(END, 1)[0].split('\n')
                         if l.strip()]

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

        # Removal rule -- deterministic, so it survives every re-run.
        f.write('REMOVAL RULE -- every category in `PL_FOREIGN_CATEGORIES` '
                '(`scripts/normalize_specs.py`) is removed from '
                '`domain=programming_language`: it names application/vertical content '
                'whose natural domain already exists, not a language or stdlib '
                'capability area.\n\n')
        for cat in sorted(PL_FOREIGN_CATEGORIES):
            f.write(f"- `{cat}` -- {PL_FOREIGN_REASONS.get(cat, '')}\n")
        f.write('\n')

        # Verbatim rows -- present only on the run that removes them. When this run
        # removed nothing, re-emit the block kept from the previous file so an
        # idempotent re-run cannot erase the record. (Losing it this way is exactly
        # how the 318dec22 removals vanished from the committed notes, which read
        # "(0 specs removed.)".)
        rows = ['| domain | category | module | status | why foreign | notes |',
                '|---|---|---|---|---|---|']
        for x in removed:
            rows.append(f"| {x['domain']} | {x['category']} | {x['module']} | "
                        f"{x['status']} | {PL_FOREIGN_REASONS.get(x['category'], '')} | "
                        f"{x['notes']} |")
        if not removed and len(prev_rows) > 2:
            rows = prev_rows
        f.write('Specs removed from `domain=programming_language`, recorded verbatim:\n\n')
        f.write(START + '\n')
        for r in rows:
            f.write(r + '\n')
        f.write(END + '\n')
        f.write('\n(The table above is preserved across idempotent re-runs; a category '
                'removed by the rule is listed once.)\n\n')

        f.write('KEPT under `programming_language`: Video, Robotics, DL, '
                'Encryption, TLS, Hashing, Key Mgmt, PKI, Protocol, OS, Compiler, '
                'VM, Numerical, Serialization, CPU and the rest -- these are stdlib '
                'capability areas and several are exercised by gate rows in '
                'EXPECTED_STDLIB.tsv (programming_language_dl_*, _tls_*, '
                '_encryption_*, ...). Borderline categories were considered and '
                'KEPT because a library/framework is a plausible language '
                'capability: Trading (algorithmic trading), Payments/ERP/'
                'Collaboration (SDK / protocol integrations), PCB (EDA), Messaging '
                '(broker clients), Mobile/Desktop (platform targets).\n\n')
        f.write('## consequence for derived documents\n\n')
        f.write(f"`gap_specs.json` now holds {len(clean)} specs. `docs/status.json` "
                "(generated) and `docs/SELF_IMPROVEMENT.md` quote that count and are "
                "refreshed by `bash scripts/regen_status.sh`; until that runs they "
                "trail the raw spec file. It is deliberately not run from the removal "
                "commit: it also counts `lib/std`, which a concurrent work unit is "
                "editing, so running it mid-flight would bake in a transient state.\n\n")
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
          f"({', '.join(sorted(PL_FOREIGN_CATEGORIES))})")
    print(f"  duplicate specs recorded={len(dups)}")
    print(f"  wrote planned/SPEC_DATA_NOTES.md, planned/CATEGORY_CONTAMINATION.tsv")


if __name__ == '__main__':
    main()
