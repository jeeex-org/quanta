#!/usr/bin/env python3
"""
Quanta numeric correctness harness (println-based, full 64-bit).

Generates Quanta source for a battery of arithmetic/shift/overflow expressions,
compiles with the given qc, runs it, and cross-checks every printed value
against Python's exact integer arithmetic (the oracle). This bypasses the
8-bit exit-code mask that makes `return <int>` unusable for values >= 256.

Usage:  numeric_harness.py <qc-path> [--quick]
Exit 0 if all checks pass, else 1.
"""
import subprocess, sys, os, random, tempfile

QCDIR = os.path.dirname(os.path.abspath(__file__))
QCPATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(QCDIR, "..", "compiler", "0.0.78", "bin", "x86", "qc")
QUICK = "--quick" in sys.argv
# Division semantics oracle. Quanta currently emits C-style truncation
# (idiv: truncates toward zero). Pass --floor to compare against Python floor
# semantics (a//b floor, a%b matches). Use this to separate real bugs from the
# floor-vs-trunc design difference.
FLOOR = "--floor" in sys.argv

def trunc_div(a, b):
    q = abs(a) // abs(b)
    if (a < 0) != (b < 0):
        q = -q
    return q

def trunc_mod(a, b):
    q = trunc_div(a, b)
    return a - q * b

def run_quanta(src):
    with tempfile.NamedTemporaryFile("w", suffix=".quanta", delete=False) as f:
        f.write(src); path = f.name
    try:
        p = subprocess.run([QCPATH, path, "/tmp/nh.bin"], capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            return None, p.stderr
        r = subprocess.run(["/tmp/nh.bin"], capture_output=True, text=True, timeout=60)
        return r.stdout, None
    finally:
        os.unlink(path)

def check(name, expr, oracle):
    src = f"fn main(){{ println({expr}) }}\n"
    out, err = run_quanta(src)
    if out is None:
        return ("COMPILE-FAIL", (err or "").strip())
    got = out.strip().split("\n")
    got = [g for g in got if g != ""]
    if len(got) != 1:
        return ("BAD-OUTPUT", f"got {got!r}")
    try:
        gv = int(got[0])
    except ValueError:
        return ("NONINT", got[0])
    if gv == oracle:
        return ("OK", "")
    return ("FAIL", f"got {gv}, want {oracle}")

# Expression battery: (name, quanta_expr, python_oracle)
CASES = []
def add(name, q, py): CASES.append((name, q, py))

# --- basic two-operand arithmetic ---
for (op, po) in [("+","+"),("-","-"),("*","*"),("/","//"),("%","%"),("&","&"),("|","|"),("^","^")]:
    add(f"arith 7{op}3", f"7 {op} 3", eval(f"7 {po} 3"))
add("arith 100*200", "100 * 200", 20000)
add("arith 100/7", "100 / 7", 14)
add("arith 100%7", "100 % 7", 2)

# --- large values within i64 ---
MAX = 9223372036854775807
MIN = -9223372036854775808
add("MAX", "9223372036854775807", MAX)
add("MAX-1", "9223372036854775807 - 1", MAX-1)
add("MAX+1 (wrap)", "9223372036854775807 + 1", MIN)  # two's-complement wrap
add("MIN+1", "-9223372036854775807 - 1 + 1", MIN+1)   # -MIN literal not expressible; use -MAX-1+1
add("MAX*2 (wrap)", "9223372036854775807 * 2", (MAX*2) % (2**64) - 2**64 if MAX*2 >= 2**63 else MAX*2)
add("1000000^3 (wrap)", "1000000 * 1000000 * 1000000", (1000000**3) % (2**64))
if not QUICK:
    # multi-operand
    add("multi 5-term", "32434324 + 43432432432432 + 4324324324324 + 432432432432423 + 3243243243242",
        32434324 + 43432432432432 + 4324324324324 + 432432432432423 + 3243243243242)
    add("multi mixed", "100 + 2000000000 + 300 + 4000000000 + 500",
        100 + 2000000000 + 300 + 4000000000 + 500)
    add("multi neg", "1000000 - 2000000 + 3000000 - 4000000 + 5000000",
        1000000 - 2000000 + 3000000 - 4000000 + 5000000)

# --- shifts (fixed-width: n>=64 -> 0) ---
add("shl 1<<3", "1 << 3", 8)
add("shl 1<<63", "1 << 63", MIN)   # sign bit
add("shl 1<<64", "1 << 64", 0)
add("shl 1<<65", "1 << 65", 0)
add("shl 100<<256", "100 << 256", 0)
add("shl 255<<8", "255 << 8", 255 << 8)
add("shr 255>>8", "255 >> 8", 0)
add("shr 256>>8", "256 >> 8", 1)
add("shr 100>>1", "100 >> 1", 50)
add("shr 1>>64", "1 >> 64", 0)
add("shr -1>>1", "-1 >> 1", -1)          # arithmetic
add("shr -8>>2", "-8 >> 2", -2)          # arithmetic
add("shr -9223372036854775807>>1", "-9223372036854775807 >> 1", -4611686018427387904)

if not QUICK:
    # random fuzz
    random.seed(1234)
    for i in range(200 if not QUICK else 20):
        a = random.randint(-10**18, 10**18)
        b = random.randint(0, 1000)
        add(f"fuzz {i} a+b", f"{a} + {b}", a+b)
        add(f"fuzz {i} a-b", f"{a} - {b}", a-b)
        add(f"fuzz {i} a*b", f"{a} * {b}", ((a*b) % (2**64)) - 2**64 if (a*b) % (2**64) >= 2**63 else (a*b) % (2**64))
        if b != 0:
            add(f"fuzz {i} a/b", f"{a} / {b}", a // b if FLOOR else trunc_div(a, b))
            add(f"fuzz {i} a%b", f"{a} % {b}", a % b if FLOOR else trunc_mod(a, b))
        # shift with small/large counts
        c = random.randint(0, 80)
        want = 0 if c >= 64 else (a << c) % (2**64)
        want = want - 2**64 if want >= 2**63 else want
        add(f"fuzz {i} a<<c", f"{a} << {c}", want)
        wantr = 0 if c >= 64 else (a >> c)  # python >> is arithmetic for negatives
        add(f"fuzz {i} a>>c", f"{a} >> {c}", wantr)

# --- run ---
fails = 0
total = 0
for name, q, oracle in CASES:
    total += 1
    status, detail = check(name, q, oracle)
    if status != "OK":
        fails += 1
        print(f"  {status:12} {name:40} {detail}")
print(f"\nNUMERIC HARNESS: {total-fails}/{total} passed, {fails} failed")
sys.exit(1 if fails else 0)
