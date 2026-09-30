#!/usr/bin/env python3
"""rag_config.py - read config/rag.conf.

The single reason this exists: a path must be changeable in ONE place. Before
it, ten scripts each carried their own copy of /opt/tali/ti/ai/rag/vectors.db,
and moving the tree meant editing all ten -- and missing one produced a script
that silently read a stale or nonexistent database.

Format is documented in config/rag.conf itself. Kept deliberately small and
dependency-free: these scripts run under whatever interpreter the embedder needs,
which may not be the system python3.

    from rag_config import get, get_int, path
    DB = get("rag", "db")                 # /opt/tali/ti/ai/rag/vectors.db
    N  = get_int("rag", "default_top_k", 5)
"""

import os
import re

# The config is located by walking up from this file, not from the CWD, so a
# script works from any directory. scripts/ -> repo root -> config/rag.conf.
_HERE = os.path.dirname(os.path.abspath(__file__))


def _find_config():
    d = _HERE
    for _ in range(6):
        p = os.path.join(d, "config", "rag.conf")
        if os.path.isfile(p):
            return p
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return os.path.join(_HERE, "config", "rag.conf")


CONFIG_PATH = os.environ.get("QUANTA_RAG_CONF") or _find_config()

_cache = None
_REF = re.compile(r"\$\{([A-Za-z0-9_.-]+)\}")


def _parse():
    """Read the file into {(section, key): raw_value}. Cached."""
    global _cache
    if _cache is not None:
        return _cache
    out = {}
    section = ""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("[") and line.endswith("]"):
                    section = line[1:-1].strip()
                    continue
                if "=" not in line:
                    continue
                k, _, v = line.partition("=")
                out["%s.%s" % (section, k.strip())] = v.strip()
    except OSError:
        pass
    _cache = out
    return out


def _expand(value, _depth=0):
    """Expand ${section.key}. Bounded: a self-referential value must not hang."""
    if _depth > 8 or "${" not in value:
        return value

    def sub(m):
        return _get_raw(m.group(1)) or ""

    return _REF.sub(sub, value)


def _get_raw(name):
    return _expand(_parse().get(name, ""), 1)


def get(section, key, default=""):
    """Value of `key` in `[section]`, with ${...} expanded."""
    v = _get_raw("%s.%s" % (section, key))
    return v if v else default


def get_int(section, key, default=0):
    """Integer value; `default` when unset or unparseable.

    Values like temperature are stored as tenths precisely so this stays exact --
    the language's config reader has no decimal parser.
    """
    v = get(section, key)
    if not v:
        return default
    try:
        return int(v)
    except ValueError:
        return default


def get_float(section, key, default=0.0, scale=1.0):
    """Integer value divided by `scale`.

    temperature = 3 with scale 10 -> 0.3. Kept integer in the file so the Quanta
    reader and this one agree exactly; a float literal would parse in python and
    not in Quanta.
    """
    return get_int(section, key, int(default * scale)) / scale


def path(section, key, default=""):
    """A configured path, expanded. Named `path` to make the intent obvious at
    the call site: `DB = path("rag", "db")`."""
    return get(section, key, default)


def require(section, key, what=""):
    """A value that must be set, or a clear error.

    Used for paths that a previous version of these scripts invented rather than
    verified. Naming the key that is missing beats a FileNotFoundError from a
    path the user never configured.
    """
    v = get(section, key)
    if not v:
        raise SystemExit(
            "rag.conf: [%s] %s is not set%s. Edit config/rag.conf."
            % (section, key, (" (%s)" % what) if what else "")
        )
    return v


def reload():
    """Drop the cache. For tests, and for a long-lived process that edits it."""
    global _cache
    _cache = None


if __name__ == "__main__":
    # `python3 rag_config.py` prints every key with its value resolved. Useful
    # for confirming a move took effect without running anything heavy.
    for k in sorted(_parse()):
        print("%-24s %s" % (k, _get_raw(k)))
