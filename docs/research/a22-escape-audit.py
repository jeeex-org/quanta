#!/usr/bin/env python3
"""A22 static escape/alias audit of every mem_alloc call site in the Quanta corpus.

Static, text-level, no compilation, ~2 s wall. Method:
  1. Parse every .quanta file (comment-stripped, string-aware): top-level
     (brace-depth-0) globals, function defs with bodies (brace-matched),
     closure literals, imports.
  2. Find every mem_alloc( site; bind it:  let x = mem_alloc(...)  -> the P2
     auto-free universe (parse_let detector, parse.quanta:1503-1525 of 0.0.242);
     x = mem_alloc(...) -> reassignment (NOT owned under P2); bare/inline ->
     classified by its statement.
  3. Walk the bound name and derived names (aliases, interior pointers) through
     the function body occurrence-by-occurrence and classify:
        R   the return statement's VALUE is (derived from) the pointer
        G   stored into a top-level global (any file's, shared namespace)
        S   stored into memory (mem_store/mem_store8 value arg, target != var)
        C   captured by a closure literal (heap env outlives the frame)
        C-t passed to thread_create / closure_call / mk_any (escapes)
        Pr  passed at param position j of user fn f where f RETAINS param j
            (f returns it / stores it / transitively passes it on; fixpoint)
        F   explicitly consumed: mem_free / drop / free  (double-free under P2)
        X   consumed by mem_realloc/realloc
        L   consumed locally (reader builtins, arithmetic, index, compare)
        N   not let-bound (reassignment or inline) - outside P2's rule
       G-nop2  reassigned into a global (escapes, but P2 never owns it)
  4. Retention summaries per function record and parameter position, computed
     to a fixpoint (transitive through call chains, position-sensitive).
  5. Callee resolution is PER CALLER FILE: same-file definition first, then a
     file reachable through the caller's imports, then the single definition
     if unique; lib/std has 189 same-name collisions (parallel module copies).
  6. mem_free/drop/free audit of lib/std: MULTI-FREE, USE-AFTER-FREE,
     P2-OWNED (frees a let-bound mem_alloc -> double free under P2), PARAM,
     IN-LOOP.

Usage: python3 a22-escape-audit.py <repo> [out.json]
"""
import os, re, sys, json, time, bisect
from collections import Counter, defaultdict

CONSUME = {"mem_free", "drop", "free"}
REALLOC = {"mem_realloc", "realloc"}
VSTORE  = {"mem_store", "mem_store8", "w64", "w32", "w16", "w8"}  # w64==mem_store (helpers.quanta:8)
RETAINB = {"thread_create", "closure_call", "mk_any"}
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
CALL_RE = re.compile(r"([A-Za-z_]\w*)\s*\(")
RETURN_RE = re.compile(r"\breturn\b")
ASSIGN_RE = re.compile(r"([A-Za-z_]\w*)\s*=(?![=])")
STMT_END_RE = re.compile(r"[;\n{]")
FN_RE = re.compile(r"\bfn\s+([A-Za-z_]\w*)\s*\(([^()]*)\)\s*(?:(?:->|:)\s*[^{;]+?)?\s*\{")
IMPORT_RE = re.compile(r"^\s*import\s+(\S+)", re.M)

def strip_comments(text):
    out = []; spans = []; i = 0; n = len(text); in_str = False; s0 = 0
    while i < n:
        c = text[i]
        if in_str:
            if c == '\\': out.append(text[i:i+2]); i += 2; continue
            out.append(c)
            if c == '"': in_str = False; spans.append((s0, i))
            i += 1; continue
        if c == '"': in_str = True; s0 = i; out.append(c); i += 1; continue
        if c == '/' and i+1 < n and text[i+1] == '/':
            while i < n and text[i] != '\n': i += 1
            continue
        if c == '/' and i+1 < n and text[i+1] == '*':
            j = text.find('*/', i+2); i = n if j < 0 else j+2; out.append(' '); continue
        out.append(c); i += 1
    return ''.join(out), spans

def line_of(text, pos): return text.count('\n', 0, pos) + 1

def match_brace(text, open_pos):
    depth = 0; i = open_pos; n = len(text); in_str = False
    while i < n:
        c = text[i]
        if in_str:
            if c == '\\': i += 2; continue
            if c == '"': in_str = False
            i += 1; continue
        if c == '"': in_str = True
        elif c == '{': depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0: return i
        i += 1
    return -1

def match_paren(text, open_pos):
    depth = 0; i = open_pos; n = len(text); in_str = False
    while i < n:
        c = text[i]
        if in_str:
            if c == '\\': i += 2; continue
            if c == '"': in_str = False
            i += 1; continue
        if c == '"': in_str = True
        elif c == '(': depth += 1
        elif c == ')':
            depth -= 1
            if depth == 0: return i
        i += 1
    return None

def split_args(s):
    args = []; depth = 0; start = 0; i = 0; n = len(s); in_str = False
    while i < n:
        c = s[i]
        if in_str:
            if c == '\\': i += 2; continue
            if c == '"': in_str = False
            i += 1; continue
        if c == '"': in_str = True
        elif c in '([{': depth += 1
        elif c in ')]}': depth -= 1
        elif c == ',' and depth == 0:
            args.append((start, i)); start = i + 1
        i += 1
    if s.strip(): args.append((start, n))
    return args

def stmt_end(text, pos, limit):
    m = STMT_END_RE.search(text, pos, limit)
    return m.start() if m else limit

class Fn:
    __slots__ = ("name","file","pos","b0","b1","params","calls","rets","grhs","stores",
                 "text","loopmap","tokidx","_ret_s","_grhs_s","_call_ops","ret_args","locals")

GLOBALS = set()
CAST_FNS = set()

def scan_globals(text, str_spans):
    """Top-level (brace depth 0) let/const names only."""
    globs = set()
    depth = 0; i = 0; n = len(text); in_str = False
    while i < n:
        c = text[i]
        if in_str:
            if c == '\\': i += 2; continue
            if c == '"': in_str = False
            i += 1; continue
        if c == '"': in_str = True; i += 1; continue
        if c == '{': depth += 1; i += 1; continue
        if c == '}': depth -= 1; i += 1; continue
        if depth == 0 and c in 'lc' and (i == 0 or text[i-1] in '\n;'):
            m = re.match(r"(?:let|const)\s+([A-Za-z_]\w*)", text[i:i+64])
            if m: globs.add(m.group(1))
        i += 1
    return globs

def parse_file(path):
    with open(path, 'r', errors='replace') as f:
        raw = f.read()
    text, str_spans = strip_comments(raw)
    fns = {}; closure_spans = []
    globs = scan_globals(text, str_spans)
    for m in FN_RE.finditer(text):
        b = match_brace(text, m.end()-1)
        if b < 0: continue
        fn = Fn()
        fn.name = m.group(1); fn.file = path; fn.pos = m.start()
        fn.b0 = m.end(); fn.b1 = b
        fn.params = [p.strip().split(':')[0].strip() for p in m.group(2).split(',') if p.strip()]
        fn.text = text
        fns[m.group(1)] = fn
    for m in re.finditer(r"\|[^|]*\|\s*\{", text):
        b = match_brace(text, m.end()-1)
        if b > 0: closure_spans.append((m.start(), b))
    imports = [m.group(1) for m in IMPORT_RE.finditer(text)]
    return text, fns, globs, closure_spans, str_spans, imports

def build_fn_index(fn, str_spans, gset):
    text = fn.text; b0, b1 = fn.b0, fn.b1
    sstarts = [s for s, e in str_spans]
    def in_str(p):
        j = bisect.bisect_right(sstarts, p) - 1
        return j >= 0 and str_spans[j][0] <= p < str_spans[j][1]
    calls = []
    for m in CALL_RE.finditer(text, b0, b1):
        op = m.end()-1
        cp = match_paren(text, op)
        if cp is None or cp > b1: continue
        args = [(op+1+a, op+1+b) for a, b in split_args(text[op+1:cp])]
        calls.append((m.group(1), m.start(), op, cp, args))
    fn.calls = calls
    rets = []
    for m in RETURN_RE.finditer(text, b0, b1):
        if in_str(m.start()): continue
        e = stmt_end(text, m.end(), b1)
        rets.append((m.end(), e))
    fn.rets = rets
    ret_args = []
    for (s, e) in rets:
        argspans = []
        for (cname, cs, op, cp, args) in calls:
            if op >= s and cp <= e:
                argspans.extend(args)
        ret_args.append(argspans)
    fn.ret_args = ret_args
    grhs = []
    for m in ASSIGN_RE.finditer(text, b0, b1):
        if m.group(1) not in gset or in_str(m.start()): continue
        e = stmt_end(text, m.end(), b1)
        grhs.append((m.end(), e))
    grhs.sort()
    fn.grhs = grhs
    fn.stores = [args[1] for (name, cs, op, cp, args) in calls
                 if name in VSTORE and len(args) >= 2]
    lm = []
    for m in re.finditer(r"\b(?:while|for)\b[^{;]*\{", text[b0:b1]):
        b = b0 + m.end() - 1
        e = match_brace(text, b)
        if e > 0: lm.append((b, e))
    fn.loopmap = lm
    tokidx = defaultdict(list)
    for t in IDENT.finditer(text, b0, b1):
        tokidx[t.group(0)].append(t.start())
    fn.tokidx = tokidx
    fn._ret_s = [s for s, e in fn.rets]
    fn._grhs_s = [s for s, e in fn.grhs]
    fn._call_ops = [c[2] for c in fn.calls]
    fn.locals = set(m.group(1) for m in re.finditer(r"\blet\s+([A-Za-z_]\w*)", text[b0:b1]))

def holder_root(text, s, e):
    m = IDENT.search(text, s, e)
    return m.group(0) if m else None

def holder_class(fn, root, var, gset):
    """Classify a store TARGET's lifetime: 'self' (the block itself),
    'param'/'global' (outlives), 'local' (same-scope alloc), 'unknown'."""
    if root is None: return 'unknown'
    if root == var: return 'self'
    if root in fn.params: return 'param'
    if root in gset: return 'global'
    if root in fn.locals: return 'local'
    return 'unknown'

def in_span(spans, starts, p):
    j = bisect.bisect_right(starts, p) - 1
    return j >= 0 and spans[j][0] <= p < spans[j][1]

def direct_occurs(fn, s, e, name):
    """True if `name` occurs in [s,e) OUTSIDE any nested call's argument region
    (so the value at that position IS the name, not a call's result)."""
    subs = []
    for (cname, cs, op, cp, args) in fn.calls:
        if op >= s and cp <= e:
            subs.extend(args)
    for t in IDENT.finditer(fn.text, s, e):
        if t.group(0) != name: continue
        tp = t.start()
        if not any(a <= tp < b for (a, b) in subs): return True
    return False

def loop_at(fn, pos):
    return any(b <= pos < e for (b, e) in fn.loopmap)

def snippet(text, pos, w=90):
    s = text[max(0, pos-w):pos+w].replace('\n', ' ')
    return re.sub(r'\s+', ' ', s).strip()[:170]

def analyze(repo):
    global GSET
    dirs = [("std", os.path.join(repo, "lib/std")),
            ("codes", os.path.join(repo, "test_suites/codes")),
            ("bench", os.path.join(repo, "benchmarks")),
            ("tests", os.path.join(repo, "tests"))]
    files = []
    for tag, d in dirs:
        if not os.path.isdir(d): continue
        for f in sorted(os.listdir(d)):
            if f.endswith('.quanta'): files.append((tag, os.path.join(d, f)))
    t0 = time.time()
    parsed = {}
    records = []              # every Fn record
    by_file = {}              # file -> {name: Fn}
    by_name = defaultdict(list)
    for tag, path in files:
        text, fns, globs, clo, strs, imports = parse_file(path)
        parsed[path] = dict(tag=tag, text=text, fns=fns, clo=clo, strs=strs,
                            imports=imports, globs=globs)
        by_file[path] = fns
        for v in fns.values():
            records.append(v); by_name[v.name].append(v)
        for g in globs: GLOBALS.add(g)
    # module path map: 'std/str' -> file
    mod2file = {}
    for tag, path in files:
        if tag == 'std':
            mod2file['std/' + os.path.basename(path)[:-7]] = path
    # per-file effective globals: own globals + globals of imported std files
    FGLOB = {}
    for tag, path in files:
        g = set(parsed[path]['globs'])
        for imp in parsed[path]['imports']:
            f = mod2file.get(imp)
            if f: g |= parsed[f]['globs']
        FGLOB[path] = g
    def resolve(caller_file, name):
        """same-file first, then imported file, then unique, else first."""
        fns = by_file.get(caller_file, {})
        if name in fns: return fns[name]
        defs = by_name.get(name, [])
        if not defs: return None
        if len(defs) == 1: return defs[0]
        for imp in parsed[caller_file]['imports']:
            f = mod2file.get(imp) or (imp + '.quanta' if not imp.startswith('std/') else None)
            if f:
                for d in defs:
                    if d.file == f: return d
        return defs[0]
    print("parsed %d files in %.1fs" % (len(files), time.time()-t0), flush=True)
    t1 = time.time()
    for path in parsed:
        for fn in by_file[path].values():
            build_fn_index(fn, parsed[path]['strs'], FGLOB[path])
    print("indexed in %.1fs" % (time.time()-t1), flush=True)
    # value-transform casts: `fn u32(x) { return x & 0xffffffff }` returns a
    # MASKED value that cannot be a live userspace pointer -> never retains.
    # Auto-detected: any single-param fn whose body is exactly that shape.
    global CAST_FNS
    CAST_FNS = set()
    for fn in records:
        if len(fn.params) == 1:
            body = fn.text[fn.b0:fn.b1].strip().rstrip(';').strip()
            if re.fullmatch(r"return\s+%s\s*&\s*[0-9xXa-fA-F_ ]+" % re.escape(fn.params[0]), body):
                CAST_FNS.add(id(fn))
    print("cast fns (masked returns, never retain):",
          sorted(f.name for f in records if id(f) in CAST_FNS), flush=True)
    # retention fixpoint over records
    t2 = time.time()
    retains = {id(fn): [False]*len(fn.params) for fn in records}
    for rnd in range(12):
        changed = False
        for fn in records:
            if id(fn) in CAST_FNS: continue
            body = fn.text[fn.b0:fn.b1]
            for i, p in enumerate(fn.params):
                if retains[id(fn)][i]: continue
                pat = re.compile(r"\b%s\b" % re.escape(p))
                if not pat.search(body): continue
                r = False
                for ri in range(len(fn.rets)):
                    s, e = fn.rets[ri]
                    if direct_occurs(fn, s, e, p): r = True; break
                if not r:
                    for (s, e) in fn.grhs:
                        if direct_occurs(fn, s, e, p): r = True; break
                if not r:
                    for (s, e) in fn.stores:
                        if direct_occurs(fn, s, e, p):
                            op = fn.text.rfind('(', 0, s)
                            cp = match_paren(fn.text, op)
                            if cp is None: continue
                            ts, te = op+1, cp
                            args0 = fn.text[ts:te].split(',')[0].strip()
                            hc = holder_class(fn, holder_root(fn.text, ts, ts+len(args0)), p, FGLOB[fn.file])
                            if hc in ('param', 'global', 'unknown'):
                                if not re.search(r"\b%s\b" % re.escape(p), args0):
                                    r = True; break
                if not r:
                    for (cname, cs, op, cp, args) in fn.calls:
                        if cname == 'thread_create' and len(args) > 1 and \
                           pat.search(fn.text[args[1][0]:args[1][1]]): r = True; break
                        if cname in ('closure_call', 'mk_any'):
                            for (s, e) in (args[1:] if cname == 'closure_call' else args[:1]):
                                if pat.search(fn.text[s:e]): r = True; break
                        if r: break
                        g = resolve(fn.file, cname) if cname not in ('thread_create','closure_call','mk_any') else None
                        if g is not None and g is not fn and id(g) not in CAST_FNS:
                            for j, (s, e) in enumerate(args):
                                if j < len(g.params) and retains[id(g)][j] and \
                                   pat.search(fn.text[s:e]): r = True; break
                        if r: break
                if r: retains[id(fn)][i] = True; changed = True
        if not changed: break
    print("retention fixpoint in %.1fs (%d rounds)" % (time.time()-t2, rnd+1), flush=True)
    # ---- sites ----
    t3 = time.time()
    sites = []
    for path, P in parsed.items():
        text = P['text']; fns = P['fns']; clo = P['clo']; strs = P['strs']
        sstarts = [s for s, e in strs]
        def in_str(p):
            j = bisect.bisect_right(sstarts, p) - 1
            return j >= 0 and strs[j][0] <= p < strs[j][1]
        for m in re.finditer(r"\bmem_alloc\s*\(", text):
            fn = None
            for f2 in fns.values():
                if f2.pos < m.start() < f2.b1 and (fn is None or f2.pos > fn.pos):
                    fn = f2
            line = line_of(text, m.start())
            ctx = snippet(text, m.start())
            if fn is None:
                sites.append(dict(file=path, tag=P['tag'], line=line, var=None,
                                  form='toplevel', fn=None, flags=['TOPLEVEL'],
                                  loop=False, ctx=ctx))
                continue
            back = text[max(fn.b0, m.start()-120):m.start()]
            mb = re.search(r"let\s+([A-Za-z_]\w*)\s*=\s*$", back)
            ma = re.search(r"([A-Za-z_]\w*)\s*=\s*$", back)
            loop = loop_at(fn, m.start())
            if mb:
                flags, pread = walk_site(text, fn, mb.group(1), m.start(),
                                         resolve, retains, clo, strs, FGLOB[path])
                sites.append(dict(file=path, tag=P['tag'], line=line,
                                  var=mb.group(1), form='let', fn=fn.name,
                                  flags=flags, loop=loop, ctx=ctx,
                                  pread=sorted(pread)))
            elif ma:
                lhs = ma.group(1)
                fl = ['G-nop2'] if lhs in FGLOB[path] else ['N']
                sites.append(dict(file=path, tag=P['tag'], line=line, var=lhs,
                                  form='reassign', fn=fn.name, flags=fl, loop=loop, ctx=ctx))
            else:
                f = inline_class(text, fn, m.start(), resolve, retains, FGLOB[path])
                sites.append(dict(file=path, tag=P['tag'], line=line, var=None,
                                  form='inline', fn=fn.name, flags=f, loop=loop, ctx=ctx))
    print("sites classified in %.1fs" % (time.time()-t3), flush=True)
    return sites, retains, records, parsed

def walk_site(text, fn, var, spos, resolve, retains, clo, strs, fglob):
    """Occurrence-driven walk of var (+derived aliases) through fn's body."""
    tracked = {var}
    dead = set()
    flags = []; pread = set()
    sstarts = [s for s, e in strs]
    def in_str(p):
        j = bisect.bisect_right(sstarts, p) - 1
        return j >= 0 and strs[j][0] <= p < strs[j][1]
    esc = 0; checked = 0
    frontier = [(var, p) for p in fn.tokidx.get(var, []) if p > spos]
    seen = set()
    while frontier:
        (tok, tp) = frontier.pop()
        key = (tok, tp)
        if key in seen or tok in dead: continue
        seen.add(key)
        checked += 1
        if checked > 4000: flags.append('OVERFLOW'); break
        if tp <= spos or in_str(tp): continue
        j = bisect.bisect_right(fn._ret_s, tp) - 1
        direct_ret = False
        if j >= 0 and fn.rets[j][0] <= tp < fn.rets[j][1]:
            direct_ret = not any(a_s <= tp < a_e for (a_s, a_e) in fn.ret_args[j])
        if direct_ret:
            if 'R' not in flags: flags.append('R')
            esc += 1
        else:
            gj = bisect.bisect_right(fn._grhs_s, tp) - 1
            in_grhs_direct = False
            if gj >= 0 and fn.grhs[gj][0] <= tp < fn.grhs[gj][1]:
                in_grhs_direct = direct_occurs(fn, fn.grhs[gj][0], fn.grhs[gj][1], tok)
            if in_grhs_direct:
                if 'G' not in flags: flags.append('G')
                esc += 1
            else:
                ec = enclosing_call(fn, tp)
                if ec:
                    cname, j2 = ec
                    if cname in CONSUME:
                        if 'F' not in flags: flags.append('F')
                    elif cname in REALLOC:
                        if 'X' not in flags: flags.append('X')
                        esc += 1
                    elif cname in VSTORE and j2 == 1:
                        for (nm2, cs2, op2, cp2, args2) in fn.calls:
                            if op2 <= tp < cp2:
                                vs, ve = args2[1]
                                if direct_occurs(fn, vs, ve, var):
                                    ts, te = args2[0]
                                    hc = holder_class(fn, holder_root(text, ts, te), var, fglob)
                                    if hc in ('param', 'global', 'unknown'):
                                        f = 'S:%s' % hc
                                        if f not in flags: flags.append(f)
                                        if 'S' not in flags: flags.append('S')
                                        esc += 1
                                    elif hc == 'local':
                                        if 'S-local' not in flags: flags.append('S-local')
                                break
                    elif cname in RETAINB:
                        if not (cname == 'thread_create' and j2 == 0):
                            if 'C-thread' not in flags: flags.append('C-thread')
                            esc += 1
                    else:
                        g = resolve(fn.file, cname)
                        if g is not None and id(g) not in CAST_FNS:
                            if j2 < len(g.params) and retains[id(g)][j2]:
                                f = 'Pr:%s' % cname
                                if f not in flags: flags.append(f)
                                esc += 1
                            else:
                                pread.add(cname)
                        # unresolved name = extern/builtin reader: fall through
                if any(a <= tp < b for (a, b) in clo):
                    if 'C' not in flags: flags.append('C')
                    esc += 1
        m2 = re.match(r"%s\s*=(?![=])" % re.escape(tok), text[tp:tp+300])
        if m2:
            rhs_s = tp + m2.end()
            rhs_e = stmt_end(text, rhs_s, fn.b1)
            if 'mem_alloc' not in text[rhs_s:rhs_e]:
                isalias = any(direct_occurs(fn, rhs_s, rhs_e, v) for v in tracked)
                if isalias:
                    if tok not in tracked:
                        tracked.add(tok)
                        frontier.extend((tok, p) for p in fn.tokidx.get(tok, []) if p > tp)
                else:
                    tracked.discard(tok); dead.add(tok)
    return flags, pread

def enclosing_call(fn, tp):
    j = bisect.bisect_right(fn._call_ops, tp) - 1
    while j >= 0:
        (cname, cs, op, cp, args) = fn.calls[j]
        if cp > tp:
            for k, (a_s, a_e) in enumerate(args):
                if a_s <= tp < a_e: return (cname, k)
            return None
        j -= 1
    return None

def inline_class(text, fn, pos, resolve, retains, fglob):
    seg_s = max(fn.b0, pos-250)
    seg = text[seg_s:pos]
    ec = enclosing_call(fn, pos)
    if ec and ec[0] == 'mem_alloc':
        # the alloc itself is the argument of... mem_alloc: look for a bare
        # `return` immediately before the statement -> `return mem_alloc(...)`
        m = None
        for mm in RETURN_RE.finditer(seg): m = mm
        if m is not None:
            between = seg[m.end():]
            if ';' not in between and '{' not in between and '\n' not in between.strip():
                return ['R-inline']
        return ['N-inline-discard']
    if ec:
        cname, j = ec
        if cname in CONSUME: return ['F-inline']
        if cname in VSTORE and j == 1:
            for (nm2, cs2, op2, cp2, args2) in fn.calls:
                if op2 <= pos < cp2 and cname == nm2:
                    ts, te = args2[0]
                    hc = holder_class(fn, holder_root(text, ts, te), None, fglob)
                    if hc == 'local': return ['S-local-inline']
                    return ['S-inline']
        if cname in RETAINB and not (cname == 'thread_create' and j == 0):
            return ['C-thread']
        g = resolve(fn.file, cname)
        if g is not None and id(g) not in CAST_FNS and j < len(g.params) and retains[id(g)][j]:
            return ['Pr-inline:%s' % cname]
        return ['N-inline:%s' % cname]
    # bare statement
    m = None
    for mm in RETURN_RE.finditer(seg): m = mm
    if m is not None:
        between = seg[m.end():]
        if ';' not in between and '{' not in between and '\n' not in between.strip():
            return ['R-inline']
    return ['N-inline-discard']

def enclosing_block_end(text, b0, p):
    """End offset of the innermost {...} block (starting at b0) containing p."""
    depth = 0; best = -1; i = b0; n = len(text); in_str = False
    while i < p:
        c = text[i]
        if in_str:
            if c == '\\': i += 2; continue
            if c == '"': in_str = False
            i += 1; continue
        if c == '"': in_str = True
        elif c == '{':
            if depth >= 0: best = i
            depth += 1
        elif c == '}': depth -= 1
        i += 1
    if best < 0: return n
    e = match_brace(text, best)
    return e if e > 0 else n

def audit_frees(parsed):
    rows = []
    for path, P in sorted(parsed.items()):
        if P['tag'] != 'std': continue
        text = P['text']; fns = P['fns']
        for m in re.finditer(r"\b(mem_free|drop|free)\s*\(", text):
            name = m.group(1); line = line_of(text, m.start())
            fn = None
            for f2 in fns.values():
                if f2.pos < m.start() < f2.b1 and (fn is None or f2.pos > fn.pos):
                    fn = f2
            if fn is None:
                rows.append((path, line, name, '?', 'TOPLEVEL')); continue
            op = m.end()-1; cp = match_paren(text, op)
            arg = text[op+1:cp].strip() if cp else '?'
            am = IDENT.match(arg)
            av = am.group(0) if am else None
            info = []
            if av:
                frees = re.findall(r"\b(?:mem_free|drop|free)\s*\(\s*%s\b" % re.escape(av),
                                   text[fn.b0:fn.b1])
                nallocs = len(re.findall(r"let\s+%s\s*=\s*mem_alloc\s*\(" % re.escape(av),
                                         text[fn.b0:fn.b1]))
                # sequential double-free: two frees of av with no `return`, no
                # re-`let av =`, and no other free-of-av consumed in between...
                # conservative: flag only when a free is followed by another free
                # of av before any `return` or re-binding of av.
                seq_double = False
                positions = [m.start() for m in re.finditer(
                    r"\b(?:mem_free|drop|free)\s*\(\s*%s\s*\)" % re.escape(av), text[fn.b0:fn.b1])]
                for a, p1 in enumerate(positions):
                    for p2 in positions[a+1:]:
                        between = text[fn.b0+p1:fn.b0+p2]
                        if re.search(r"\breturn\b", between): break
                        if re.search(r"let\s+%s\s*=" % re.escape(av), between): break
                        if re.search(r"\b%s\s*=(?![=])" % re.escape(av), between): break
                        seq_double = True
                        break
                    if seq_double: break
                if seq_double: info.append('SEQ-DOUBLE-FREE')
                last = None
                for fmm in re.finditer(r"\b(?:mem_free|drop|free)\s*\(\s*%s\s*\)" % re.escape(av),
                                       text[fn.b0:fn.b1]):
                    last = fmm
                # use after free: any use of av between a free and the end of
                # the enclosing block / next `return` / re-binding of av
                uaf = False
                for fmm in re.finditer(r"\b(?:mem_free|drop|free)\s*\(\s*%s\s*\)" % re.escape(av),
                                       text[fn.b0:fn.b1]):
                    w_s = fn.b0 + fmm.end()
                    b_end = enclosing_block_end(text, fn.b0, w_s)
                    mret = RETURN_RE.search(text, w_s, b_end)
                    mlet = re.search(r"let\s+%s\s*=" % re.escape(av), text[w_s:b_end])
                    w_e = b_end
                    if mret: w_e = min(w_e, mret.start())
                    if mlet: w_e = min(w_e, w_s + mlet.start())
                    window = text[w_s:w_e]
                    for t in IDENT.finditer(window):
                        if t.group(0) != av: continue
                        ctx = window[t.start():t.start()+200]
                        if re.match(r"%s\s*=(?![=])" % re.escape(av), ctx): break
                        uaf = True; break
                    if uaf: break
                if uaf: info.append('USE-AFTER-FREE')
                if nallocs >= 1 and len(frees) > nallocs:
                    info.append('FREES(%d)>ALLOCS(%d)' % (len(frees), nallocs))
                if nallocs >= 1: info.append('P2-OWNED')
                if av in fn.params: info.append('PARAM')
                if last and loop_at(fn, fn.b0+last.start()): info.append('IN-LOOP')
            rows.append((path, line, name, arg, ','.join(info) if info else 'ok'))
    return rows

def cls_of(r):
    fl = r['flags']
    for key in ('R', 'R-inline', 'G', 'S', 'S-inline', 'C', 'C-thread'):
        if key in fl: return key
    if any(x.startswith('Pr') for x in fl): return 'Pr'
    if 'F' in fl or 'F-inline' in fl: return 'F'
    if 'X' in fl: return 'X'
    if 'G-nop2' in fl: return 'G-nop2'
    if any(x.startswith('N') for x in fl): return 'N'
    if r['form'] == 'let': return 'L'
    return '?'

def main():
    repo = sys.argv[1] if len(sys.argv) > 1 else '/opt/tali/quanta'
    outp = sys.argv[2] if len(sys.argv) > 2 else 'a22-escape-audit.json'
    sites, retains, records, parsed = analyze(repo)
    frees = audit_frees(parsed)
    json.dump(dict(sites=sites, frees=frees), open(outp, 'w'), indent=1, default=list)
    for tag in ('std', 'codes', 'bench', 'tests'):
        c = Counter(cls_of(r) for r in sites if r.get('tag') == tag)
        print(tag, dict(sorted(c.items())), "n=", sum(c.values()))
    c = Counter(cls_of(r) for r in sites)
    print("ALL", dict(sorted(c.items())), "n=", sum(c.values()))
    let_sites = [r for r in sites if r['form'] == 'let']
    c2 = Counter(cls_of(r) for r in let_sites)
    print("LET-BOUND ONLY (the P2 universe):", dict(sorted(c2.items())), "n=", len(let_sites))
    print("frees audited:", len(frees))
    loops = Counter(r['loop'] for r in let_sites if cls_of(r) not in ('L','N'))
    print("non-L/N let sites inside loop bodies:", dict(loops))
    flagged = [r for r in sites if cls_of(r) in ('R','G','S','C','C-thread','F','X','Pr')]
    print("flagged:", len(flagged))
    for r in flagged:
        print("  %s:%s [%s] %s %s | %s" % (os.path.basename(r['file']), r['line'],
              cls_of(r), r['form'], ','.join(r['flags']), r['ctx'][:110]))

if __name__ == '__main__':
    main()
