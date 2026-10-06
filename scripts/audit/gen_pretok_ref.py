#!/usr/bin/env python3
"""Generate tests/fixtures/pretok_ref.txt: the LFM2 pre-tokenizer's split of a
set of inputs, using llama.cpp's OWN committed Unicode tables.

The \\p{L}, \\p{N} and \\s tables are parsed out of llama.cpp's generated
src/unicode-data.cpp rather than taken from Python's unicodedata, because the
two disagree: comparing all 0x110000 codepoints found 4382 differing
classifications on L/N alone. Using Python here would make the reference agree
with upstream only on inputs that avoid those codepoints.

The split is the regex llama.cpp uses for pre == "lfm2", expanded to a
leftmost-first alternation exactly as a regex engine evaluates it. That
transcription is a real limitation: it is not upstream's compiled code, so it
cannot detect a mistake in this file. Two consequences, both load-bearing:

  - Every \\s+(?!\\S) case below was checked against llama.cpp's own
    test-tokenizer-0, and those cases are what pin the backtracking.

  - test_suites/codes/stdlib_lfm2_bpe_test.quanta is the test with a compiled
    oracle behind it: it compares exact token ids against the fixture written by
    scripts/audit/gen_tokenizer_ref.py, which drives test-tokenizer-0. When the
    two disagree, believe the ids -- they come from upstream's binary.

WHAT A TRANSCRIPTION CANNOT SEE: branch 6 originally consumed a whole whitespace
run even when a non-space followed. Upstream backtracks one codepoint and hands
that character to branch 2, which absorbs it into the next word, so "test  d"
splits as "test" / " " / " d" and not "test" / "  " / "d". The wrong version
agreed with the wrong implementation, so the gate reported GREEN on a broken
pre-tokenizer. test-tokenizer-0 gives 6093 / 229 / 277 for that input.

Audit/oracle tooling: run once, offline. Native tests read the committed file
and never invoke this.
"""
from __future__ import annotations

import base64
import bisect
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UNICODE_DATA = "/opt/ai/llama.cpp/src/unicode-data.cpp"

NUMBER = 0x0002
LETTER = 0x0004


def load_upstream_tables():
    src = open(UNICODE_DATA, encoding="utf-8").read()
    rows = sorted(
        (int(a, 16), int(b, 16))
        for a, b in re.findall(r"\{0x([0-9A-Fa-f]{6}), 0x([0-9A-Fa-f]{4})\}", src)
    )
    starts = [r[0] for r in rows]

    m = re.search(r"unicode_set_whitespace\s*=\s*\{(.*?)\};", src, re.S)
    if m is None:
        raise SystemExit("unicode_set_whitespace not found in %s" % UNICODE_DATA)
    ws_block = m.group(1)
    ws = sorted(int(x, 16) for x in re.findall(r"0x([0-9A-Fa-f]{4,6})", ws_block))

    def flag_of(cp):
        i = bisect.bisect_right(starts, cp) - 1
        return rows[i][1] if i >= 0 else 0

    def ranges_for(bit):
        out = []
        cur = None
        for idx, (st, fl) in enumerate(rows):
            last = (rows[idx + 1][0] - 1) if idx + 1 < len(rows) else 0x110000 - 1
            if fl & bit:
                if cur is not None and cur[1] + 1 == st:
                    cur = (cur[0], last)
                else:
                    if cur:
                        out.append(cur)
                    cur = (st, last)
            else:
                if cur:
                    out.append(cur)
                    cur = None
        if cur:
            out.append(cur)
        return out

    return ranges_for(LETTER), ranges_for(NUMBER), ws, flag_of


L_RANGES, N_RANGES, WS_SET, _FLAG = load_upstream_tables()
L_STARTS = [r[0] for r in L_RANGES]
N_STARTS = [r[0] for r in N_RANGES]
WS = set(WS_SET)


def in_ranges(starts, ranges, cp):
    i = bisect.bisect_right(starts, cp) - 1
    return i >= 0 and ranges[i][0] <= cp <= ranges[i][1]


def is_L(cp):
    return in_ranges(L_STARTS, L_RANGES, cp)


def is_N(cp):
    return in_ranges(N_STARTS, N_RANGES, cp)


def is_space(cp):
    return cp in WS


def is_nl(cp):
    return cp == 13 or cp == 10


# --- the contraction alternation, as upstream writes it
CONTRACTIONS = [
    "'s", "'S", "'t", "'T", "'re", "'rE", "'Re", "'RE",
    "'ve", "'vE", "'Ve", "'VE",
    "'m", "'M", "'ll", "'d", "'D",
]


def pretokenize(text: str):
    """Leftmost-first alternation, exactly as the regex engine evaluates it."""
    out = []
    i = 0
    n = len(text)
    while i < n:
        start = i

        # branch 1: contraction
        matched = None
        for c in CONTRACTIONS:
            if text.startswith(c, i):
                matched = c
                break
        if matched:
            out.append((start, i + len(matched)))
            i += len(matched)
            continue

        c0 = ord(text[i])

        # branch 2: [^\r\n\p{L}\p{N}]?\p{L}+
        if is_L(c0):
            j = i
            while j < n and is_L(ord(text[j])):
                j += 1
            out.append((start, j))
            i = j
            continue
        if not is_nl(c0) and not is_L(c0) and not is_N(c0):
            j = i + 1
            if j < n and is_L(ord(text[j])):
                while j < n and is_L(ord(text[j])):
                    j += 1
                out.append((start, j))
                i = j
                continue

        # branch 3: \p{N}{1,3}
        if is_N(c0):
            j = i
            while j < n and is_N(ord(text[j])) and (j - i) < 3:
                j += 1
            out.append((start, j))
            i = j
            continue

        # branch 4: ' '?[^\s\p{L}\p{N}]+[\r\n]*
        j = i
        if c0 == 32:
            j = i + 1
        if j < n:
            cj = ord(text[j])
            if not is_space(cj) and not is_L(cj) and not is_N(cj):
                while j < n:
                    cj = ord(text[j])
                    if is_space(cj) or is_L(cj) or is_N(cj):
                        break
                    j += 1
                while j < n and is_nl(ord(text[j])):
                    j += 1
                out.append((start, j))
                i = j
                continue

        # branch 5: \s*[\r\n]+   (greedy \s* with backtracking => whole run)
        #
        # branch 6: \s+(?!\S)
        #
        # (?!\S) is "not followed by a NON-space", so this branch takes a
        # whitespace run only when it REACHES THE END of the text. When a
        # non-space follows, \s+ backtracks one codepoint and stops, handing that
        # last whitespace character to branch 2, which absorbs it into the next
        # word:
        #
        #     "test  d"  ->  "test" / " " / " d"   (NOT "test" / "  " / "d")
        #     "  "       ->  "  "                   (whole run, at end of text)
        #
        # Taking the whole run regardless is the bug documented above.
        #
        # branch 7: \s+ is unreachable: it spans the same range as branch 6.
        if is_space(c0):
            j = i
            while j < n and is_space(ord(text[j])):
                j += 1
            # Backtrack one codepoint ONLY when the run is longer than one and a
            # non-space follows. A one-character run has no codepoint to give up:
            # subtracting from it would land back on i and make no progress, which
            # spins forever on input like "1 22" (i at the space, j == i).
            if j < n and j - i > 1:
                j -= 1
            out.append((start, j))
            i = j
            continue

        # exhaustive fallback
        out.append((start, i + 1))
        i += 1

    return out


CASES = [
    "",
    "a",
    "Hello world",
    "Hello, world!",
    "it's a test",
    "IT'S A TEST",
    "don't we're I'll you've I'd he'd",
    "'s 'S 't",
    "'re 'rE 'Re 'RE 've 'vE",
    "1234567890",
    "1 22 333 4444 55555",
    "a1b22c333",
    "  leading",
    "trailing  ",
    "   ",
    "\n",
    "\r\n",
    "\n\n",
    " \n\n",
    "a\nb",
    "a\n\nb",
    "\n\n\n\n\n",
    "line1\nline2\nline3",
    "text\n",
    "text\n   ",
    "text   \n   more",
    "\t",
    "a\tb",
    "\ta",
    "a\t",
    "  \t  \n  \t  ",
    "...",
    "!@#$%^&*()",
    "  ...  ",
    "...\n",
    "...\n\n",
    "!?\n\n?!",
    "   a",
    "a   ",
    "a   b",
    "MiXeD CaSe",
    "café",
    "café",
    "café au lait",
    "über",
    "naïve",
    "résumé",
    "ÅÄÖ",
    "日本語",
    "日本語テキスト",
    "日本語 テキスト",
    "こんにちは",
    "안녕하세요",
    "Привет",
    "مرحبا",
    "αβγδ",
    "\U0001F389\U0001F389",
    "\U0001F389 emoji \U0001F389",
    "a\U0001F389b",
    "  \U0001F389  ",
    "123\U0001F389456",
    "\U0001F600\U0001F601",
    "tab\there",
    "mix \n \t \r\n end",
    "a" * 200,
    " " * 50,
    "\n" * 20,
    ("hello world " * 20),
    ("1234567890" * 10),
    ("é" * 40),
    ("日本語" * 20),
    "  123  ",
    "a" + " " * 3 + "b",
    "a" + "\n" * 3 + "b",
    "word\tword\tword",
    "===",
    "a=b+c",
    "3.14159",
    "-42",
    "+7",
    "$1,234.56",
    "C++",
    "don't stop",
    "I'm sure it's Bob's, y'all",
    "x'y",
    "a'b",
    "'",
    "''",
    "'''",
    "''''",
    "'''''",
    "1'",
    "'1",
    "e.g. i.e. U.S.A.",
    "a b",
    "a  b",
    "a　b",
    " ",
    "  ",
    "  ",
    "x\ty\n\nz  ",
    # \s+(?!\S): a whitespace run before a word backtracks one codepoint, while a
    # run at end of text keeps the whole run. These pin the branch-6 fix; taken
    # from llama.cpp's own test-tokenizer-0.
    "test  double  space",
    "  leading and trailing  ",
    "a  b",
    "a   b",
    "trailing  ",
    "test  d",
    "  a",
    "a  ",
    "  x",
    "x  ",
]


def main():
    # Round-trip every case through UTF-8 and reject lone surrogates, which the
    # native side would have to represent as U+FFFD and could not byte-match.
    cases = []
    for c in CASES:
        try:
            c.encode("utf-8")
        except UnicodeEncodeError:
            continue
        cases.append(c)

    out = os.path.join(ROOT, "tests", "fixtures", "pretok_ref.txt")
    lines = [
        "# LFM2 (LLAMA3) pre-tokenizer split reference.",
        "# Generated by scripts/audit/gen_pretok_ref.py using llama.cpp's own",
        "# committed Unicode tables (src/unicode-data.cpp), NOT Python's",
        "# unicodedata. Audit tooling only; native tests read this file.",
        "#",
        "# The split here is a TRANSCRIPTION of upstream's regex, not upstream's",
        "# compiled code. Where it disagrees with stdlib_lfm2_bpe_test (which has",
        "# test-tokenizer-0 behind it), believe the ids.",
        "#",
        "# ### <index> <base64 of UTF-8 input>",
        "# <byte offset> <byte length>      (one line per pre-token)",
        "# --- end of block",
        "",
    ]
    total = 0
    for idx, c in enumerate(cases):
        toks = pretokenize(c)
        total += len(toks)
        lines.append("### %d %s" % (idx, base64.b64encode(c.encode("utf-8")).decode("ascii")))
        # Map char indices to UTF-8 byte offsets once, rather than trying to
        # re-slice by char index into an already-encoded buffer.
        b = c.encode("utf-8")
        pre = [0]
        for ch in c:
            pre.append(pre[-1] + len(ch.encode("utf-8")))
        for ch_off, ch_end in toks:
            boff = pre[ch_off]
            blen = pre[ch_end] - boff
            lines.append("%d %d" % (boff, blen))
        lines.append("--- end of block")

    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print("wrote %s: %d blocks, %d pre-tokens" % (out, len(cases), total))


if __name__ == "__main__":
    main()