"""Bisect the 37-pair loop INSIDE tests/test_simple_parse.quanta by replacing
the else-if chain with a reduced one, keeping everything else (prologue, the two
mem_allocs, the read_raw sequence) exactly as written. This stays faithful to the
real test because only the chain varies."""
import subprocess, os

R = '/opt/tali/quanta'
QC = R + '/compiler/0.0.221/bin/x86/qc'
L = open(R + '/tests/test_simple_parse.quanta').read().split('\n')

# lines 29..45 (1-based) are the if/else-if chain
CHAIN_START, CHAIN_END = 28, 45   # 0-based slice bounds

B8 = ['        if vtype == 8 {',
      '            read_raw(fd, klen_buf, 8)',
      '            lseek(fd, mem_load(klen_buf), 1)',
      '        } else if vtype == 9 {',
      '            lseek(fd, 4, 1)',
      '            read_raw(fd, klen_buf, 8)',
      '            let alen = mem_load(klen_buf)',
      '            lseek(fd, alen * 4, 1)',
      '        }']
TAIL = ['        else if vtype == 0 { lseek(fd, 1, 1) }',
        '        else if vtype == 1 { lseek(fd, 1, 1) }',
        '        else if vtype == 4 { lseek(fd, 4, 1) }',
        '        else if vtype == 5 { lseek(fd, 4, 1) }',
        '        else if vtype == 6 { lseek(fd, 4, 1) }',
        '        else if vtype == 7 { lseek(fd, 1, 1) }',
        '        else if vtype == 10 { lseek(fd, 8, 1) }',
        '        else if vtype == 11 { lseek(fd, 8, 1) }',
        '        else if vtype == 12 { lseek(fd, 8, 1) }']


def build(ntail):
    out = L[:CHAIN_START] + B8 + TAIL[:ntail] + L[CHAIN_END:]
    return '\n'.join(out)


def run(ntail, label):
    src = build(ntail)
    open('/tmp/rd.quanta', 'w').write(src)
    subprocess.run(['rm', '-rf', '/tmp/rd_b'])
    c = subprocess.run(['timeout', '300', QC, '/tmp/rd.quanta', '/tmp/rd_b'],
                       capture_output=True, text=True, cwd=R)
    if not os.path.exists('/tmp/rd_b'):
        print('%-40s CFAIL %s' % (label, c.stdout.strip()[:40]))
        return
    r = subprocess.run(['timeout', '30', '/tmp/rd_b'], capture_output=True, text=True)
    print('%-40s rc=%-5d out=%r' % (label, r.returncode,
                                    r.stdout.strip().replace('\n', '|')[:80]))


print('=== reduce the else-if tail of the REAL test ===')
run(0, 'b8+b9 only')
for n in range(1, 9):
    run(n, 'b8+b9 + %d tail branch(es)' % n)

print()
print('=== strip statements from the b9 branch only ===')
VARIANTS = {
    'b9 full': ['            lseek(fd, 4, 1)',
                '            read_raw(fd, klen_buf, 8)',
                '            let alen = mem_load(klen_buf)',
                '            lseek(fd, alen * 4, 1)'],
    'b9 no mul': ['            lseek(fd, 4, 1)',
                  '            read_raw(fd, klen_buf, 8)',
                  '            let alen = mem_load(klen_buf)',
                  '            lseek(fd, alen, 1)'],
    'b9 no len': ['            lseek(fd, 4, 1)',
                  '            read_raw(fd, klen_buf, 8)',
                  '            lseek(fd, mem_load(klen_buf) * 4, 1)'],
    'b9 lseek+read only': ['            lseek(fd, 4, 1)',
                           '            read_raw(fd, klen_buf, 8)'],
}
for lab, stmts in VARIANTS.items():
    src = '\n'.join(L[:CHAIN_START] + B8[:1] + stmts + ['        }'] +
                    TAIL + L[CHAIN_END:])
    open('/tmp/rd.quanta', 'w').write(src)
    subprocess.run(['rm', '-rf', '/tmp/rd_b'])
    c = subprocess.run(['timeout', '300', QC, '/tmp/rd.quanta', '/tmp/rd_b'],
                       capture_output=True, text=True, cwd=R)
    if not os.path.exists('/tmp/rd_b'):
        print('%-40s CFAIL %s' % (lab, c.stdout.strip()[:40]))
        continue
    r = subprocess.run(['timeout', '30', '/tmp/rd_b'], capture_output=True, text=True)
    print('%-40s rc=%-5d out=%r' % (lab, r.returncode,
                                    r.stdout.strip().replace('\n', '|')[:70]))