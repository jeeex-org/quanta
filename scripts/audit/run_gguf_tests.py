"""Run the REAL failing tests against a candidate compiler, and report exactly
which pass. This is the only measurement that counts -- hand-written repros drift
from the real tests, which has already cost three false conclusions."""
import subprocess, os, sys

R = '/opt/tali/quanta'
QC = sys.argv[1] if len(sys.argv) > 1 else R + '/compiler/0.0.221/bin/x86/qc'

# Discovered, not hardcoded. The previous list named 33 tests that no longer
# exist; a stale list makes this script silently test nothing.
def discover():
    d = R + '/tests'
    return sorted(os.path.basename(p)[:-7] for p in
                  (d + '/' + f for f in os.listdir(d)) if p.endswith('.quanta'))

TESTS = discover()

ok = fail = nobin = 0
for t in TESTS:
    p = R + '/tests/' + t + '.quanta'
    if not os.path.exists(p):
        print('%-26s NO SUCH TEST' % t)
        continue
    out = '/tmp/real_' + t
    subprocess.run(['rm', '-rf', out])
    c = subprocess.run(['timeout', '300', QC, p, out],
                       capture_output=True, text=True, cwd=R)
    if not os.path.exists(out):
        print('%-26s COMPILE-FAIL %s' % (t, c.stdout.strip()[:40]))
        nobin += 1
        continue
    r = subprocess.run(['timeout', '60', out], capture_output=True, text=True)
    if r.returncode == 0:
        print('%-26s PASS' % t)
        ok += 1
    else:
        print('%-26s rc=%d' % (t, r.returncode))
        fail += 1
print('\nPASS=%d FAIL=%d COMPILE-FAIL=%d of %d' % (ok, fail, nobin, len(TESTS)))