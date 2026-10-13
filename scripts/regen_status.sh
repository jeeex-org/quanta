#!/bin/bash
# scripts/regen_status.sh -- REGENERATE docs/status.json and docs/status.md.
#
# This is "the regeneration command" named in every failure message printed by the
# gate's verify-status stage (test_suites/scripts/verify_status.quanta). The stage
# no longer rewrites its own input -- a check that regenerates what it checks can
# never detect staleness -- so generation lives here, and the stage only verifies.
#
# Every number below is derived from the tree by a command; nothing is hand-typed.
# Run from anywhere:  bash scripts/regen_status.sh
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")/.."

python3 - <<'PY'
import json, os, re, subprocess, time

ROOT = os.getcwd()

def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout.strip()

def count(pattern, path='.'):
    out = sh(f"find {path} {pattern} -type f 2>/dev/null | wc -l")
    return int(out or 0)

def sanitize(s):
    # matches lib/std/code_synthesizer.quanta sanitize_ident + the lowercase
    # convention the committed stubs used (si_generate.sh lowercases).
    return re.sub(r'[^0-9A-Za-z]', '_', s).lower()

# ---- gap_specs.json (the roadmap) ------------------------------------------
specs = json.load(open('gap_specs.json'))['specs']
total = len(specs)
domains = sorted({s['domain'] for s in specs})
categories = {(s['domain'], s['category']) for s in specs}
modules = sorted({s['module'] for s in specs})
named_modules = len(modules)

# ---- lib/std: real implementations only (stubs were moved to planned/) ------
lib_std = [f for f in os.listdir('lib/std') if f.endswith('.quanta')]
real_modules = set(f[:-7] for f in lib_std)

# which named gap_spec modules have a real implementation today? A module is
# "delivered" when its slug is literally a file in lib/std (e.g. QUIC -> quic.quanta).
# The d_c_m form is NOT the convention the delivered modules use; the flat
# module-slug form is.
mod_slugs = {sanitize(m) for m in modules}
delivered = mod_slugs & real_modules
# The generated d_c_m filename form (what planned/lib_std holds) is reported
# separately so both conventions are visible.
generated_form = set()
for s in specs:
    generated_form.add(f"{sanitize(s['domain'])}_{sanitize(s['category'])}_{sanitize(s['module'])}")

# ---- planned/ (the moved planning tree + manifest) -------------------------
planned_lib_std = count('', 'planned/lib_std')
planned_tests = count('', 'planned/tests')
planned_rows = sum(1 for l in open('planned/INDEX.tsv') if l.strip()) - 1

# ---- SI pipeline modules ---------------------------------------------------
pipeline = ['spec_parser', 'spec_to_ir', 'pattern_library', 'code_synthesizer', 'test_generator', 'si_main']
pipe = []
for m in pipeline:
    p = f'lib/std/{m}.quanta'
    lines = sum(1 for _ in open(p)) if os.path.exists(p) else 0
    pipe.append({"module": f"std/{m}", "file": p, "lines": lines, "present": os.path.exists(p)})

# ---- genuinely missing stdlib targets -------------------------------------
missing_targets = ['net/http', 'jsonrpc', 'lsp', 'html_parser', 'graphics']
missing = [t for t in missing_targets if not os.path.exists(f'lib/std/{t}.quanta')]

# ---- per-domain counts (top 15 by spec count) ------------------------------
by_dom = {}
for s in specs:
    d = by_dom.setdefault(s['domain'], {'specs': 0, 'delivered': 0})
    d['specs'] += 1
    if sanitize(s['module']) in delivered:
        d['delivered'] += 1
dom_list = sorted(by_dom.items(), key=lambda kv: -kv[1]['specs'])[:15]

now = int(time.time())
iso = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(now))

ratio = (len(delivered) / named_modules * 100.0) if named_modules else 0.0

def pct_num(n, d):
    return round(n / d * 100.0, 1) if d else 0.0

data = {
    "generated_at": iso,
    "generated_at_epoch": now,
    "generator": "scripts/regen_status.sh",
    "freshness_threshold_secs": 2592000,
    "checked_by": "test_suites/scripts/verify_status.quanta (gate stage 12)",
    "ns": "quanta",
    "si_metrics": {
        "gap_specs_total": total,
        "gap_specs_domains": len(domains),
        "gap_specs_categories": len(categories),
        "gap_specs_modules_named": named_modules,
        "modules_delivered_in_lib_std": len(delivered),
        "delivery_ratio_pct": round(ratio, 1),
        "lib_std_real_modules": len(lib_std),
        "test_suites_codes_tests": count(" -name '*.quanta'", 'test_suites/codes'),
        "planned_lib_std_files": planned_lib_std,
        "planned_test_files": planned_tests,
        "planned_index_rows": planned_rows,
        "planned_specs_covered": total,
    },
    "si_pipeline": pipe,
    "missing_stdlib": [
        {"name": f"std/{t}", "file": f"lib/std/{t}.quanta", "status": "missing"}
        for t in missing
    ],
    "domains": [
        {"domain": d, "specs": v['specs'], "delivered": v['delivered'],
         "delivered_pct": pct_num(v['delivered'], v['specs'])}
        for d, v in dom_list
    ],
}

with open('docs/status.json', 'w') as f:
    json.dump(data, f, indent=2)
    f.write('\n')

# ---- human dashboard ------------------------------------------------------
m = data['si_metrics']
lines = []
lines.append('# Quanta Status Dashboard (AUTO-GENERATED)')
lines.append('')
lines.append(f'Generated at **{iso}** (epoch {now}) by `scripts/regen_status.sh`.')
lines.append('Freshness is enforced by the gate\'s verify-status stage')
lines.append('(`test_suites/scripts/verify_status.quanta`, threshold 30 days) --')
lines.append('run `bash scripts/regen_status.sh` to refresh.')
lines.append('')
lines.append('## SI / roadmap delivery')
lines.append('')
lines.append('| metric | value |')
lines.append('|---|---|')
lines.append(f"| gap_specs specs | {m['gap_specs_total']} |")
lines.append(f"| distinct domains | {m['gap_specs_domains']} |")
lines.append(f"| distinct categories | {m['gap_specs_categories']} |")
lines.append(f"| distinct modules named | {m['gap_specs_modules_named']} |")
lines.append(f"| modules delivered in lib/std | {m['modules_delivered_in_lib_std']} |")
lines.append(f"| delivery ratio | {m['delivery_ratio_pct']}% |")
lines.append(f"| lib/std real modules | {m['lib_std_real_modules']} |")
lines.append(f"| test_suites/codes tests | {m['test_suites_codes_tests']} |")
lines.append(f"| planned/ module stubs | {m['planned_lib_std_files']} |")
lines.append(f"| planned/ generated tests | {m['planned_test_files']} |")
lines.append(f"| planned/INDEX.tsv rows | {m['planned_index_rows']} |")
lines.append('')
lines.append('## SI pipeline modules')
lines.append('')
lines.append('| module | file | lines | present |')
lines.append('|---|---|---|---|')
for p in pipe:
    lines.append(f"| {p['module']} | {p['file']} | {p['lines']} | {'yes' if p['present'] else 'NO'} |")
lines.append('')
lines.append('## Genuinely missing stdlib targets')
lines.append('')
if missing:
    for t in missing:
        lines.append(f"- `std/{t}` -- MISSING")
else:
    lines.append('- none')
lines.append('')
lines.append('## Delivery by domain (top 15 by spec count)')
lines.append('')
lines.append('| domain | specs | delivered | % |')
lines.append('|---|---|---|---|')
for d in data['domains']:
    lines.append(f"| {d['domain']} | {d['specs']} | {d['delivered']} | {d['delivered_pct']}% |")
lines.append('')
with open('docs/status.md', 'w') as f:
    f.write('\n'.join(lines))

print(f"wrote docs/status.json + docs/status.md at {iso}")
print(f"  modules named={named_modules} delivered={len(delivered)} ({round(ratio,1)}%)")
print(f"  planned: lib_std={planned_lib_std} tests={planned_tests} index_rows={planned_rows}")
print(f"  missing stdlib: {', '.join('std/'+t for t in missing) or 'none'}")
PY
