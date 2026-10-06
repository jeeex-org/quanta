import glob, os, sys

# Quanta's lexer rejects any byte outside printable ASCII + tab/newline/CR, even
# inside a // comment. All 17 files of compiler/0.0.225/src/x86 carry typographic
# characters in their comments, so the compiler has been unbuildable from its own
# sources since 0.0.225 was committed -- `qc main.quanta` reports only
# "invalid character in source (byte not a token)", with no line number.
#
# Run ONCE per file. An earlier version was run twice over the same tree and its
# own '?' replacements were then re-decoded as fresh UTF-8 sequences, corrupting
# borrow.quanta into binary garbage. Hence the guard below: refuse anything that
# is not recognisably Quanta source.
#
# Idempotent: a file with no non-ASCII bytes is skipped, and the replacement byte
# is '?', which is itself ASCII, so a second pass is a no-op.

root = sys.argv[1]
ok = set(range(32, 127)) | {9, 10, 13}

for f in sorted(glob.glob(root + "/*.quanta")):
    raw = open(f, "rb").read()
    if b"\x7fELF" in raw[:64]:
        print("SKIP (binary): %s" % os.path.basename(f))
        continue
    if raw.count(b"\nfn ") == 0 and raw.count(b"\n//") == 0:
        print("SKIP (not Quanta source): %s" % os.path.basename(f))
        continue

    bad = sum(1 for c in raw if c not in ok)
    if bad == 0:
        continue

    out = bytearray()
    i = 0
    n = len(raw)
    while i < n:
        c = raw[i]
        if c in ok:
            out.append(c)
            i += 1
            continue
        ln = 2 if c < 0xE0 else (3 if c < 0xF0 else 4)
        try:
            raw[i:i + ln].decode("utf-8")
        except UnicodeDecodeError:
            ln = 1
        out += b"?"
        i += ln
    open(f, "wb").write(bytes(out))
    print("cleaned %-18s %4d non-ascii bytes" % (os.path.basename(f), bad))

# verify
left = 0
for f in sorted(glob.glob(root + "/*.quanta")):
    d = open(f, "rb").read()
    left += sum(1 for c in d if c not in ok)
print("remaining non-ascii bytes: %d" % left)
