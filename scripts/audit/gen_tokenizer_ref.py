#!/usr/bin/env python3
"""Generate reference tokenizer outputs from UPSTREAM llama.cpp, once.

Authority for this stage is the real llama.cpp tokenizer. This drives upstream's
OWN test binary (`test-tokenizer-0`) rather than reimplementing BPE, so the
reference is the actual code path the model was published against -- including
any LFM2 pre-tokenizer behaviour (`pre='lfm2'`) that is not written down.

Why the test binary and not ctypes into libllama.so:
calling llama_model_load_from_file from ctypes requires declaring
struct llama_model_params, whose layout differs between llama.cpp builds. A
mistranscribed layout does not fail loudly -- the library reads a struct of the
wrong shape and segfaults, which is exactly what happened on the first two
attempts. The test binary takes a GGUF path as argv and links that struct
itself, so there is nothing to get wrong.

Writes:
    tests/fixtures/tokenizer_ref.txt

    format, one block per prompt:
        ### <n> <escaped prompt>
        <token id per line, decimal>
        --- end of block

Run deliberately, by hand, when the tokenizer or the fixture changes:
    python3 scripts/audit/gen_tokenizer_ref.py [model.gguf]
"""
import base64
import os
import shutil
import subprocess
import sys
import tempfile

TEST_BIN = '/opt/ai/llama.cpp/build/bin/test-tokenizer-0'
DEFAULT_MODEL = '/opt/ai/models/quanta/QUANTA-LFM2.5-2.6Bv1-Q4_K_M.gguf'

# Fixed prompt set. Chosen to exercise the cases that actually break BPE:
# plain words, leading/trailing space, repeated spaces, newlines, tabs,
# punctuation runs, digits, mixed case, multi-byte UTF-8, an empty string, a
# single character, and a long input. Add cases here if a real prompt ever
# tokenizes wrongly.
PROMPTS = [
    '',
    'a',
    ' ',
    'Hello',
    'Hello world',
    'The quick brown fox jumps over the lazy dog.',
    'hello world',
    ' def',
    'test  double  space',
    'line1\nline2',
    'trailing space ',
    '1234567890',
    'a, b. c; d! e? f',
    'MiXeD CaSe',
    'café naïve résumé',
    'こんにちは',
    'tab\there',
    'hyphen-separated and underscore_separated',
    'quanta compiler native inference',
    '  leading and trailing  ',
    'json={"key": 42, "items": [1, 2, 3]}',
    '()[]{}<>&|',
    'repeat repeat repeat repeat',
    'The rain in Spain falls mainly on the plain.',
    'x' * 200,
    'ÄÖÜ ß æøå þð',
]


def encode_prompt(s):
    """One-line, exactly reversible encoding of an arbitrary prompt.

    Base64, not unicode_escape: unicode_escape is a lossy, ASCII-only
    round-trip for non-ASCII text (it mangles UTF-8 into latin-1 pairs), which
    would silently corrupt any multi-byte prompt in the fixture.
    """
    return base64.b64encode(s.encode('utf-8')).decode('ascii')


def run_one(binary, model, prompt, workdir):
    """Tokenize one prompt, return (ids, detokenized_note)."""
    path = os.path.join(workdir, 'input.txt')
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(prompt)

    out_path = path + '.tokcpp'
    if os.path.exists(out_path):
        os.remove(out_path)

    proc = subprocess.run(
        [binary, model, path],
        capture_output=True, cwd=workdir, timeout=300)
    stdout = proc.stdout.decode('utf-8', 'replace')
    err = proc.stderr.decode('utf-8', 'replace')

    # The binary signals success with "Tests passed" on stdout.
    if 'Tests passed' not in stdout:
        raise RuntimeError(
            'tokenizer run failed for %r\n%s' % (prompt, err[-2000:]))

    if not os.path.exists(out_path):
        raise RuntimeError('no token output for %r' % prompt)

    with open(out_path, 'r', encoding='utf-8') as fh:
        body = fh.read()
    ids = [int(x) for x in body.split() if x.strip()]

    detok = None
    for line in stdout.splitlines():
        if 'detokenized in' in line:
            detok = line.split('detokenized in', 1)[1].strip()

    return ids, detok


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL
    out_path = sys.argv[2] if len(sys.argv) > 2 else \
        'tests/fixtures/tokenizer_ref.txt'

    if not os.path.exists(TEST_BIN):
        print('missing upstream test binary: %s' % TEST_BIN, file=sys.stderr)
        print('build it: cmake --build build --target test-tokenizer-0',
              file=sys.stderr)
        return 1

    print('model  : %s' % model)
    print('binary : %s' % TEST_BIN)
    print('prompts: %d' % len(PROMPTS))

    workdir = tempfile.mkdtemp(prefix='tokref_')
    blocks = []
    try:
        for n, prompt in enumerate(PROMPTS):
            ids, _detok = run_one(TEST_BIN, model, prompt, workdir)
            blocks.append((prompt, ids))
            shown = prompt if len(prompt) <= 42 else prompt[:39] + '...'
            ids_shown = ids if len(ids) <= 12 else ids[:12] + ['...']
            print('%2d %-46r -> %3d tokens  %s' % (
                n, shown, len(ids), ids_shown))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    with open(out_path, 'w', encoding='utf-8') as fh:
        fh.write('# GENERATED by scripts/audit/gen_tokenizer_ref.py '
                 '-- DO NOT EDIT\n')
        fh.write('# upstream llama.cpp %s\n' % TEST_BIN)
        fh.write('# model %s\n' % os.path.basename(model))
        fh.write('# %d prompts\n' % len(blocks))
        fh.write('#\n')
        fh.write('# format:\n')
        fh.write('#   ### <index> <base64 of the prompt, UTF-8>\n')
        fh.write('#   <one token id per line, decimal>\n')
        fh.write('#   --- end of block\n')
        for n, (prompt, ids) in enumerate(blocks):
            fh.write('### %d %s\n' % (n, encode_prompt(prompt)))
            for t in ids:
                fh.write('%d\n' % t)
            fh.write('---\n')

    total = sum(len(i) for _, i in blocks)
    print('\nwrote %s: %d prompts, %d tokens total' % (
        out_path, len(blocks), total))
    return 0


if __name__ == '__main__':
    sys.exit(main())