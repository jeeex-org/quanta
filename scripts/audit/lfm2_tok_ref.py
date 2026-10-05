#!/usr/bin/env python3
r"""Python reference for LFM2 BPE tokenization (pre='lfm2').

Purpose: establish, in a language where iteration is fast, that the upstream
algorithm can be reproduced EXACTLY. Only once this agrees with upstream's
test-tokenizer-0 on every prompt is it worth porting to native Quanta.

Upstream facts this encodes (from /opt/ai/llama.cpp/src/llama-vocab.cpp):

  * pre='lfm2' selects LLAMA_VOCAB_PRE_TYPE_LLAMA3 and sets ignore_merges=true
  * add_bos=true
  * the split regex for LLAMA3 is:

      (?:'[sS]|'[tT]|'[rR][eE]|'[vV][eE]|'[mM]|'[lL][lL]|'[dD])
      |[^\r\n\p{L}\p{N}]?\p{L}+
      |\p{N}{1,3}
      | ?[^\s\p{L}\p{N}]+[\r\n]*
      |\s*[\r\n]+
      |\s+(?!\S)
      |\s+

  * tokenize(): for each pre-token, if ignore_merges and the whole pre-token is
    a vocab entry, emit it directly; else run bigram BPE over its UTF-8
    characters using the merge list as ranks.

This file is a development scratchpad. It is NOT the test oracle (that is
upstream's own binary) and NOT on any production path.
"""
import struct
import sys
import unicodedata

MODEL = '/opt/ai/models/quanta/QUANTA-LFM2.5-2.6Bv1-Q4_K_M.gguf'

# The six alternatives, hand-kept so the order is visible and auditable.
APOS = ("'", 's', 't', 'r', 'e', 'v', 'm', 'l', 'd')


def is_L(c):
    return unicodedata.category(c).startswith('L')


def is_N(c):
    return unicodedata.category(c).startswith('N')


def is_space(c):
    # upstream \s under std::regex with default locale: space, \t, \n, \v,
    # \f, \r. Python's str.isspace() also matches U+1C..U+1F and U+85 etc,
    # which std::regex's \s does NOT; be explicit to match C++ semantics.
    return c in ' \t\n\v\f\r'


def load_vocab(path=MODEL):
    """Return (token_to_id, merges_list, bos, eos)."""
    f = open(path, 'rb')
    f.read(24)  # magic, version, n_tensors, n_kv
    n_kv = 37
    SZ = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}

    tokens = []
    merges = []
    bos = eos = None

    for _ in range(n_kv):
        kl = struct.unpack('<Q', f.read(8))[0]
        key = f.read(kl).decode('utf-8', 'replace')
        vt = struct.unpack('<I', f.read(4))[0]
        if vt == 8:  # string
            n = struct.unpack('<Q', f.read(8))[0]
            f.read(n)
        elif vt == 4:  # u32
            v = struct.unpack('<I', f.read(4))[0]
            if key == 'tokenizer.ggml.bos_token_id':
                bos = v
            elif key == 'tokenizer.ggml.eos_token_id':
                eos = v
        elif vt == 9:  # array
            et = struct.unpack('<I', f.read(4))[0]
            cnt = struct.unpack('<Q', f.read(8))[0]
            if et == 8:
                items = []
                for _i in range(cnt):
                    n = struct.unpack('<Q', f.read(8))[0]
                    items.append(f.read(n))
                if key == 'tokenizer.ggml.tokens':
                    tokens = items
                elif key == 'tokenizer.ggml.merges':
                    merges = items
            else:
                f.seek(SZ[et] * cnt, 1)
        else:
            f.seek(SZ[vt], 1)

    # Vocab tokens are raw UTF-8 BYTES of the byte-level-encoded form, while
    # byte_encode() yields a str of code points. Round-trip both through the
    # same encoding so lookups compare bytes.
    t2i = {}
    for i, t in enumerate(tokens):
        if t not in t2i:
            t2i[t] = i

    # merges: "A B" with byte-level encoding already applied to both sides.
    # Upstream splits on the FIRST space and byte-decodes each part.
    ranks = {}
    for rank, m in enumerate(merges):
        sp = m.find(b' ')
        if sp < 0:
            continue
        left = m[:sp]
        right = m[sp + 1:]
        key = (left, right)
        if key not in ranks:
            ranks[key] = rank

    return t2i, ranks, bos, eos


def byte_encode(b):
    """GPT-2 byte-level mapping: byte -> code point in 33..255 or 256..511.

    Values above 255 are code POINTS, not bytes, so this must not use bytes().
    Use a list and compare/slice consistently; vocab tokens are stored as
    UTF-8 encoded strings, so callers encode the code points back to UTF-8.
    """
    # The canonical GPT-2 byte<->unicode table, built the way upstream builds
    # it (llama.cpp: unicode_byte_to_utf8). Printable ASCII stays; the
    # printable Latin-1 range maps to itself; EVERY other byte -- including
    # UTF-8 continuation bytes 0x80..0xBF -- maps to 256+byte. Getting the
    # continuation range wrong silently corrupts every multi-byte prompt.
    cs = []
    n = 0
    for c in range(256):
        if (33 <= c <= 126) or (161 <= c <= 172) or (174 <= c <= 255):
            cs.append(c)
        else:
            cs.append(256 + n)
            n += 1
    return ''.join(chr(cs[c]) for c in b)


# --- the split regex, implemented as an ordered alternation matcher ----------

def split_pretokens(text):
    """Yield pre-tokens per upstream's LLAMA3 regex.

    Python's re has no \\p{L}/\\p{N}, so the character-class branches are
    written as explicit predicates. Alternation is ordered and each match is
    greedy, leftmost-first -- which is what std::regex does for these.
    """
    out = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]

        # 1) contractions: 's 't 're 've 'm 'll 'd  (case-insensitive pairs)
        if c == "'" and i + 1 < n:
            nxt = text[i + 1]
            rest = text[i + 1:]
            if nxt in 'sStT' and len(rest) >= 1:
                out.append("'" + nxt)
                i += 2
                continue
            if nxt in 'rRvVmM' and len(rest) >= 2 and rest[1] in 'eE':
                out.append("'" + rest[0] + rest[1])
                i += 3
                continue
            if nxt in 'lL' and len(rest) >= 2 and rest[1] in 'lL':
                out.append("'" + rest[0] + rest[1])
                i += 3
                continue
            if nxt in 'dD':
                out.append("'" + nxt)
                i += 2
                continue

        # 2) [^\r\n\p{L}\p{N}]? \p{L}+   (optional single leading non-alnum)
        j = i
        if (not in_alnum(c)) and c not in '\r\n' and j + 1 < n and is_L(text[j + 1]):
            j += 1
        k = j
        while k < n and is_L(text[k]):
            k += 1
        if k > j:
            out.append(text[i:k])
            i = k
            continue

        # 3) \p{N}{1,3}
        if is_N(c):
            k = i
            while k < n and is_N(text[k]) and k - i < 3:
                k += 1
            out.append(text[i:k])
            i = k
            continue

        # 4) '?' [^\s\p{L}\p{N}]+ [\r\n]*
        j = i
        if c == ' ' and i + 1 < n and not in_alnum(text[i + 1]) and not is_space(text[i + 1]):
            j += 1
        k = j
        while k < n and (not in_alnum(text[k])) and (not is_space(text[k])):
            k += 1
        if k > j:
            m = k
            while m < n and text[m] in '\r\n':
                m += 1
            out.append(text[i:m])
            i = m
            continue

        # 5) \s* [\r\n]+
        k = i
        while k < n and is_space(text[k]) and text[k] not in '\r\n':
            k += 1
        if k < n and text[k] in '\r\n':
            m = k
            while m < n and text[m] in '\r\n':
                m += 1
            out.append(text[i:m])
            i = m
            continue

        # 6) \s+(?!\S)  -- whitespace run whose next non-ws is end of string
        k = i
        while k < n and is_space(text[k]):
            k += 1
        if k > i and k == n:
            out.append(text[i:k])
            i = k
            continue

        # 7) \s+ (single whitespace char, fallback)
        if is_space(c):
            out.append(c)
            i += 1
            continue

        # Should be unreachable: every char is L, N, space, or punct.
        out.append(c)
        i += 1

    return out


def in_alnum(c):
    return is_L(c) or is_N(c)


def bpe_word(word_bytes, ranks, t2i):
    """Bigram BPE over the CODE POINTS of one byte-encoded pre-token.

    Splitting on UTF-8 bytes would break every multi-byte code point (the
    byte-level encoder maps e.g. byte 0x20 to U+0120, which is 2 bytes:
    \xc4\xa0). Symbols must be whole code points, because that is the
    granularity the merge list uses.
    """
    # A symbol is the UTF-8 encoding of one code point, stored as `bytes`,
    # so pair keys compare directly against the merge list.
    # Each symbol is ONE CODE POINT's UTF-8 bytes, so concatenating two
    # symbols yields the merged token's bytes and pair keys match the merge
    # list. Splitting on raw bytes would tear multi-byte code points (U+0120
    # 'Ġ' is \xc4\xa0) into two meaningless symbols.
    symbols = [c.encode('utf-8') for c in word_bytes.decode('utf-8')]
    if len(symbols) <= 1:
        return symbols

    while True:
        best = None
        best_rank = None
        for k in range(len(symbols) - 1):
            pair = (symbols[k], symbols[k + 1])
            r = ranks.get(pair)
            if r is not None and (best_rank is None or r < best_rank):
                best_rank = r
                best = k
        if best is None:
            break
        symbols[best:best + 2] = [symbols[best] + symbols[best + 1]]

    return symbols


def tokenize(text, t2i, ranks, bos, add_bos=True):
    ids = []
    if add_bos and bos is not None:
        ids.append(bos)
    for word in split_pretokens(text):
        enc = byte_encode(word.encode('utf-8')).encode('utf-8')
        # ignore_merges fast path: whole pre-token present in vocab
        tok = t2i.get(enc)
        if tok is not None:
            ids.append(tok)
            continue
        pieces = bpe_word(enc, ranks, t2i)
        for piece in pieces:
            tok = t2i.get(piece)
            if tok is None:
                raise KeyError('piece not in vocab: %r word=%r' % (piece, word))
            ids.append(tok)
    return ids


def main():
    ref = '/opt/tali/quanta/tests/fixtures/tokenizer_ref.txt'
    blocks = []
    cur_prompt = None
    cur_ids = []
    for line in open(ref, encoding='utf-8'):
        line = line.rstrip('\n')
        if not line or line.strip() == '---':
            continue
        if line.startswith('###'):
            if cur_prompt is not None:
                blocks.append((cur_prompt, cur_ids))
            rest = line[3:].strip()
            idx, _, esc = rest.partition(' ')
            # undo the generator's escaping. encode() first: the generator
            # wrote latin-1-safe escapes of the UTF-8 bytes, and a bare
            # unicode_escape round-trip would re-mangle non-ASCII.
            import base64 as _b64
            cur_prompt = _b64.b64decode(esc).decode('utf-8')
            cur_ids = []
            continue
        if line.startswith('#'):
            continue
        tok = line.strip()
        if tok.isdigit():
            cur_ids.append(int(tok))
    if cur_prompt is not None:
        blocks.append((cur_prompt, cur_ids))

    t2i, ranks, bos, eos = load_vocab()
    print('fixture prompts: %d' % len(blocks))
    print('vocab %d tokens, %d merge ranks, bos=%s eos=%s' % (
        len(t2i), len(ranks), bos, eos))

    ok = 0
    bad = []
    for prompt, expected in blocks:
        got = tokenize(prompt, t2i, ranks, bos, add_bos=False)
        if got == expected:
            ok += 1
        else:
            bad.append((prompt, expected, got))

    print('MATCH %d/%d' % (ok, len(blocks)))
    for prompt, exp, got in bad[:8]:
        print('----')
        print('  prompt : %r' % prompt[:60])
        print('  expect : %s' % exp[:16])
        print('  got    : %s' % got[:16])
        pts = split_pretokens(prompt)
        print('  split  : %s' % [p[:14] for p in pts[:10]])


if __name__ == '__main__':
    main()