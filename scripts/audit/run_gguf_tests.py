"""Run the REAL failing tests against a candidate compiler, and report exactly
which pass. This is the only measurement that counts -- hand-written repros drift
from the real tests, which has already cost three false conclusions."""
import subprocess, os, sys

R = '/opt/tali/quanta'
QC = sys.argv[1] if len(sys.argv) > 1 else R + '/compiler/0.0.221/bin/x86/qc'

TESTS = ['test_simple_parse', 'test_skip_37', 'test_raw2', 'test_no_lib',
         'test_correct_format', 'test_gguf_full_debug', 'test_inline_load',
         'test_list_tensors2', 'test_scan2', 'test_single_file',
         'test_skip_all_kv', 'test_skip_and_read', 'test_skip_loop',
         'test_tensor_read_only', 'test_prealloc_37', 'test_minimal_loader',
         'test_minimal_loader2']

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