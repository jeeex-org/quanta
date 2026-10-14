#!/usr/bin/env python3
"""KNN search over the sqlite-vec index. Prints ranked rows to stdout.

Reads the query embedding -- the raw little-endian float32 bytes that
rag_embed_file.py produces, written as hex -- from the file named by argv[1],
and the row count from argv[2] (default: rag.default_top_k in config/rag.conf).

WHY THIS EXISTS
  lib/std/rag.quanta's rag_search() used to shell out to a `sqlite3` CLI that is
  NOT installed on this host, calling vec_distance_euclidean(), which is not a
  sqlite-vec function name (the real one is vec_distance_l2). The in-language
  search could therefore never work. This helper does the KNN under the
  interpreter named by embed.python -- the one that actually has sqlite-vec and
  sentence-transformers -- so Quanta only has to run it and read its stdout back.

  Quanta cannot capture a subprocess's stdout directly: its `exec()` builtin is
  execve("/bin/sh","-c",cmd) and REPLACES the process image. So rag_search()
  redirects this script's stdout to a file (the shell does the redirect) and
  reads that file after wait(). Plain stdout here is exactly what makes that
  work, so keep the output on stdout.

OUTPUT  one line per hit:
    source|type|chunk_index|content|distance
  `content` is collapsed to a single line -- newlines, carriage returns, tabs
  and pipe characters are replaced with spaces -- so a row is exactly one line
  and the '|' fields cannot be corrupted by content. `distance` is the vec0 L2
  distance (lower = closer). rag_parse_results() in rag.quanta expects exactly
  this: fields 0 (source) and 3 (content), split on '|'.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rag_config as _CFG

try:
    import sqlite3
    import sqlite_vec
except ImportError as e:  # wrong interpreter, almost always
    sys.stderr.write(
        "rag_search_file: %s\n"
        "  This needs sqlite3 + sqlite-vec. Run it with the interpreter named by\n"
        "  embed.python in config/rag.conf (it has sqlite-vec 0.1.9).\n" % e
    )
    raise SystemExit(3)

DB = _CFG.require("rag", "db", "the vector database")
DIM = _CFG.get_int("embed", "dim", 384)
K_DEFAULT = _CFG.get_int("rag", "default_top_k", 5)

in_path = sys.argv[1] if len(sys.argv) > 1 else ""
k = int(sys.argv[2]) if len(sys.argv) > 2 else K_DEFAULT
if not in_path:
    sys.stderr.write("usage: rag_search_file.py <embedding_hex_file> [k]\n")
    raise SystemExit(2)

with open(in_path, "r") as f:
    hexstr = f.read().strip()

if not hexstr:
    sys.stderr.write("rag_search_file: %s is empty (no embedding)\n" % in_path)
    raise SystemExit(5)

emb = bytes.fromhex(hexstr)
if len(emb) != DIM * 4:
    # Same guard as rag_embed_file.py: a wrong-width vector is a different
    # embedding space, and every distance against it would be meaningless.
    sys.stderr.write(
        "rag_search_file: embedding is %d bytes, expected %d (dim %d). The\n"
        "  query vector and the stored vectors are not in the same space.\n"
        % (len(emb), DIM * 4, DIM)
    )
    raise SystemExit(6)

conn = sqlite3.connect(DB)
# sqlite_vec.load() calls load_extension() without enabling it first; the
# enable must be done on the connection. loadable_path() points at the bundled
# extension -- load_extension("sqlite_vec") by bare name fails (no such .so).
conn.enable_load_extension(True)
conn.load_extension(sqlite_vec.loadable_path())

# vec_chunks is the vec0 index (id TEXT PRIMARY KEY, embedding FLOAT[384]); the
# `chunks` table carries the text and shares the id. Join on id. MATCH + k is
# vec0's KNN interface; `distance` is the L2 distance it returns.
rows = conn.execute(
    "SELECT c.source, c.type, c.chunk_index, c.content, v.distance "
    "FROM vec_chunks v JOIN chunks c ON c.id = v.id "
    "WHERE v.embedding MATCH ? AND k = ? "
    "ORDER BY v.distance",
    (emb, k),
).fetchall()
conn.close()

_ws = re.compile(r"[\r\n\t|]+")
MAXC = 400
for source, ctype, idx, content, dist in rows:
    body = _ws.sub(" ", content or "").strip()
    if len(body) > MAXC:
        body = body[:MAXC] + "..."
    sys.stdout.write("%s|%s|%s|%s|%.6f\n" % (source, ctype, idx, body, dist))
