#!/usr/bin/env python3
"""Compute the embedding for one query. Prints ONLY hex to stdout.

Reads the query from a file given as argv[1], or stdin if no argument. A file
survives spaces, quotes and newlines in the query with no shell quoting -- which
is why rag_embed() writes the query out and calls this, rather than passing it
on a command line.

Output is the raw little-endian float32 vector as hex, which is what the
vec0 blob column expects. Width is `embed.dim` in config/rag.conf and must match
what produced the stored vectors: a different width is a different embedding
space, and distances against it are meaningless.

The model comes from config/rag.conf. It is a sentence-transformers NAME, not a
directory: it resolves through the HuggingFace cache. Do not confuse it with
[gguf] in the same file, which holds the local inference models.
"""
import os
import sys
import warnings

warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rag_config as _CFG

try:
    import numpy as np
    from sentence_transformers import SentenceTransformer
except ImportError as e:
    # Almost always means the wrong interpreter. rag.conf's `embed.python` is the
    # one to set; this host does not have one yet.
    sys.stderr.write(
        "rag_embed_file: %s\n"
        "  This script needs numpy + sentence-transformers. Run it with the\n"
        "  interpreter named by embed.python in config/rag.conf.\n" % e
    )
    raise SystemExit(3)

MODEL = _CFG.require("embed", "model", "the embedding model name")
DIM = _CFG.get_int("embed", "dim", 384)

query = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read().strip()

model = SentenceTransformer(MODEL)
vec = model.encode([query], show_progress_bar=False)[0].astype(np.float32)

if vec.shape[0] != DIM:
    # Not a warning: storing this would put a wrong-width vector beside 2.8M
    # correctly-shaped ones, and every distance in the db would become garbage.
    sys.stderr.write(
        "rag_embed_file: model %s produces %d dims, config says %d.\n"
        "  Either fix embed.dim or rebuild the database with this model --\n"
        "  vectors from two different models cannot be compared.\n"
        % (MODEL, vec.shape[0], DIM)
    )
    raise SystemExit(4)

sys.stdout.write(vec.tobytes().hex())
