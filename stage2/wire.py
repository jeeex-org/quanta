#!/usr/bin/env python3
"""
stage2/wire.py -- the SI loop wired end to end for ONE spec, every stage measured.

  spec (planned/) -> hybrid retrieval -> compact prompt (<=600 tok)
  -> native LFM2 generation (batched prefill, background) -> qc compile
  -> on failure: feed `line N:` back for ONE retry -> run -> compare to spec.

Artifacts land in stage2/run_<id>/: spec.json, retrieval.json, prompt.txt,
tokcount.txt, gen_stdout.txt, attemptN.{raw.txt,quanta}, attemptN.compile.txt,
attemptN.run.txt, run.json (per-stage timings + commands + environment).

The generation runs as a BACKGROUND process. The driver is
stage2/lfm2_gen_driver.quanta = tests/lfm2_generate.quanta + 3 documented
deltas (stage2 conf/prompt paths; max_new clamp 256->1024; prefill through
fc_prefill_batch_lg, the measured batched entry).

Usage (from /opt/tali/quanta):
  python3 stage2/wire.py <spec.quanta>              # retrieval+prompt+launch gen
  python3 stage2/wire.py --poll [--resume-id ID]    # poll the background run
  python3 stage2/wire.py --resume-id ID             # compile/run/attempt stages
                                                    # once generation is DONE
Flags: --max-new N (default 700)  --gen-only (skip compile stages this call)
"""
import json
import os
import re
import subprocess
import sys
import time

REPO = "/opt/tali/quanta"
QC = f"{REPO}/compiler/0.0.244/bin/x86/qc"          # the golden per the brief
RUNNER = f"{REPO}/scripts/quanta_run.sh"
GEN_DRIVER_SRC = f"{REPO}/stage2/lfm2_gen_driver.quanta"
GEN_CONF = "stage2/gen.conf"          # driver reads these relative to REPO
GEN_PROMPT = "stage2/prompt.txt"
EMBED_PY = "/usr/bin/python3"         # config/rag.conf [embed] python
RAG_EMBED = f"{REPO}/scripts/rag_embed_file.py"
RAG_SEARCH = f"{REPO}/scripts/rag_search_file.py"
RAG_DB = "/opt/tali/ti/ai/rag/vectors.db"
CARD_PATH = f"{REPO}/tests/lfm2_compact_card.txt"
MAX_ATTEMPTS = 2                      # attempt 1 + ONE error-feedback retry
PROMPT_TOK_BUDGET = 600
NEIGHBOR_BYTE_CAPS = [900, 600, 400, 250, 0]

# the chat template opens a thinking block; escape so this file survives
# any markup-sensitive transport
THINK_OPEN = "\x3cthink>"
THINK_CLOSE = "\x3c/think>"

_TOK = None


def env_snapshot():
    gov = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"
    gov_v = open(gov).read().strip() if os.path.exists(gov) else "?"
    load = open("/proc/loadavg").read().split()[:3]
    top = subprocess.run(["bash", "-c", "ps -eo pcpu,comm --sort=-pcpu | head -3"],
                         capture_output=True, text=True).stdout.strip().splitlines()
    return {"governor": gov_v, "loadavg": load, "top_cpu": top[:2]}


def run_cmd(cmd, timeout, cwd=REPO):
    t0 = time.time()
    p = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True,
                       cwd=cwd, timeout=timeout)
    return p.returncode, p.stdout + p.stderr, time.time() - t0


def hf_tok_count(text):
    # /usr/bin/python3 is the interpreter config/rag.conf names for the ML
    # stack (transformers 5.5.0); the default python3 on PATH has none.
    p = subprocess.run(
        ["/usr/bin/python3", "-c",
         "import sys;from transformers import AutoTokenizer;"
         "t=AutoTokenizer.from_pretrained("
         "'/opt/tali/ti/ai/models/lfm2.5-2b6',local_files_only=True);"
         "print(len(t.encode(sys.stdin.read())))"],
        input=text, capture_output=True, text=True, timeout=300)
    if p.returncode != 0:
        return f"hf-tokenizer unavailable: {p.stderr[-120:]}"
    return int(p.stdout.strip())


# ------------------------------- retrieval --------------------------------

def spec_fields(path):
    txt = open(path, encoding="utf-8", errors="replace").read()
    def grab(k):
        m = re.search(r"^// %s:\s*(.+)$" % k, txt, re.M)
        return m.group(1).strip() if m else ""
    return {"domain": grab("Domain"), "category": grab("Category"),
            "module": grab("Module"), "notes": grab("Notes"),
            "path": path, "basename": os.path.basename(path)}


def name_match(spec):
    t0 = time.time()
    hit = os.path.exists(spec["path"])
    return {"hit": hit, "ms": round((time.time() - t0) * 1000.0, 3),
            "path": spec["path"] if hit else None,
            "how": "spec triple == planned/lib_std filename (the design's "
                   "name-match arm; loop-retrieval-design.md section 3: Kc "
                   "finds the target 9/10, semantic 4/10)"}


def keyword_store_search(spec, k=40):
    """Keyword arm over the repaired store's curated quanta chunks.

    Measured here: this predicate is a full scan of the chunks table (~35 s,
    2026-10-16, load ~10). Results remapped to disk: the store's stale
    lib/std/<name>.quanta paths now live at planned/lib_std/.
    """
    t0 = time.time()
    terms = [w for w in re.split(r"[^a-z0-9]+", spec["module"].lower()) if len(w) > 2]
    terms += [w for w in re.split(r"[^a-z0-9]+", spec["category"].lower()) if len(w) > 2]
    terms = list(dict.fromkeys(terms))[:6]
    if not terms:
        return {"ms": 0, "rows": [], "terms": [], "rc": "no terms"}
    likes = " OR ".join(["content LIKE ?"] * len(terms))
    sql = ("SELECT source, type, chunk_index, substr(content,1,400) FROM chunks "
           "WHERE type='quanta' AND source NOT LIKE 'learning/%' "
           "AND source NOT LIKE 'tools/%' AND source NOT LIKE 'compiler/%' "
           f"AND ({likes}) LIMIT {k}")
    args = ["%" + t + "%" for t in terms]
    code = ("import sqlite3,sys\n"
            "con=sqlite3.connect('file:%s?mode=ro',uri=True)\n"
            "for r in con.execute(sys.stdin.read(), %r): print('|'.join("
            "[str(r[0]),str(r[1]),str(r[2]),(r[3] or '').replace(chr(10),' ')"
            ".replace('|',' ')]))\n" % (RAG_DB, args))
    p = subprocess.run(["python3", "-c", code], input=sql,
                       capture_output=True, text=True, timeout=280)
    rows = []
    for line in p.stdout.splitlines():
        parts = line.split("|", 3)
        if len(parts) == 4:
            rows.append({"source": parts[0], "type": parts[1],
                         "chunk_index": int(parts[2]), "content": parts[3]})
    def score(r):
        c = r["content"].lower()
        return (-sum(1 for t in terms if t in c), r["source"])
    rows.sort(key=score)
    return {"ms": round((time.time() - t0) * 1000.0), "rows": rows[:k],
            "terms": terms, "rc": p.returncode, "stderr": p.stderr[-200:]}


def semantic_store_search(spec, k=4096):
    """Semantic arm, live over the repaired store: embed -> vec0 KNN -> curate."""
    out = {"embed_ms": None, "knn_ms": None, "rows": [], "rc": None}
    qfile = f"{REPO}/stage2/rag_query.txt"
    hfile = f"{REPO}/stage2/rag_query.hex"
    qtext = (f"{spec['domain']} {spec['category']} {spec['module']}. "
             f"{spec['notes']} Implement in Quanta.")
    open(qfile, "w").write(qtext)
    rc, outv, wall = run_cmd(f"{EMBED_PY} {RAG_EMBED} {qfile} > {hfile}", 600)
    out["embed_ms"] = round(wall * 1000.0)
    if rc != 0 or not os.path.exists(hfile) or os.path.getsize(hfile) < 100:
        out["rc"] = f"embed rc={rc}: {outv[-200:]}"
        return out
    rc, outv, wall = run_cmd(
        f"{EMBED_PY} {RAG_SEARCH} {hfile} {k} > {REPO}/stage2/rag_knn_raw.txt", 900)
    out["knn_ms"] = round(wall * 1000.0)
    if rc != 0:
        out["rc"] = f"knn rc={rc}: {outv[-200:]}"
        return out
    rows = []
    for line in open(f"{REPO}/stage2/rag_knn_raw.txt"):
        parts = line.rstrip("\n").split("|", 4)
        if len(parts) == 5:
            rows.append({"source": parts[0], "type": parts[1],
                         "chunk_index": int(parts[2]), "content": parts[3],
                         "distance": float(parts[4])})
    curated = [r for r in rows
               if not r["source"].startswith(("learning/", "tools/", "compiler/"))]
    out["rows"] = curated[:25]
    out["rc"] = 0
    return out


def has_real_body(text):
    body = re.sub(r"^//.*$", "", text, flags=re.M)
    return ("Auto-generated stub" not in body and
            bool(re.search(r"\b(while|for)\b|[&|^~]|<<|>>|mem_alloc|\bsqrt\b"
                           r"|\bi2f\b|\bfadd\b", body)))


def pick_neighbor(spec, kw, sem):
    """One real implementation as neighbour. Name/keyword arm decides (the
    design doc's measured conclusion); semantic ranks are recorded and used
    only as fallback order."""
    tried = set()
    order = [("keyword", kw.get("rows", [])), ("semantic", sem.get("rows", []))]
    for arm, rows in order:
        for r in rows:
            base = os.path.basename(r["source"])
            if base == spec["basename"] or base in tried:
                continue
            tried.add(base)
            disk_opts = [f"{REPO}/{r['source']}",          # test_suites/, docs/
                         f"{REPO}/lib/std/{base}",
                         f"{REPO}/planned/lib_std/{base}"]
            for disk in disk_opts:
                if os.path.exists(disk):
                    body = open(disk, encoding="utf-8", errors="replace").read()
                    if has_real_body(body):
                        return {"disk": disk, "store_source": r["source"],
                                "arm": arm, "bytes": len(body),
                                "head": body[:1200]}, arm
    return None, "none"


# ------------------------------ prompt ------------------------------------

def build_spec_text(spec, neighbor_head):
    lines = [f"TASK: implement Quanta module `{spec['basename'][:-7]}`.",
             f"Domain: {spec['domain']} | Category: {spec['category']} | "
             f"Module: {spec['module']}"]
    if spec["notes"]:
        lines.append(f"Target behaviour: {spec['notes']}")
    lines += ["Implement real logic (never a `return 0` stub). Then main() runs "
              "4-8 checks inline as `if <check> != <expected> { exit(N) }` with "
              "distinct N, prints ok, and returns 0.",
              "Use only integer ops unless the target needs floats."]
    if neighbor_head:
        lines += ["Nearest real module (style reference, trimmed):",
                  neighbor_head]
    return "\n".join(lines) + "\n"


def assemble_prompt(spec_text):
    card = open(CARD_PATH).read()
    return card + "\n===== TASK =====\n" + spec_text


def trim_to_budget(spec, neighbor, budget):
    """Shrink the neighbour head until the prompt fits the token budget.
    Returns (prompt, neighbor_byte_cap, hf_tokens)."""
    caps = NEIGHBOR_BYTE_CAPS if neighbor else [0]
    last = (None, None, None)
    for cap in caps:
        head = neighbor["head"][:cap] if (neighbor and cap > 0) else None
        prompt = assemble_prompt(build_spec_text(spec, head))
        n = hf_tok_count(prompt)
        last = (prompt, cap, n)
        if isinstance(n, int) and n <= budget:
            return last
    return last


# ----------------------------- generation ---------------------------------

def start_generation(run_dir, max_new, vcap_kb=33554432):
    # Run VSZ cap, and why it is 32 GB: VmPeak MEASURED on this run --
    # 4.5 GB after prefill, then ~11 MB of VIRTUAL per decoded token
    # (13.1 GB by token ~1000) against an RSS slope of ~0.35 MB/token. The
    # first attempt died as a silent exit(1) (the allocator's MAP_FAILED
    # guard, lfm2_mm.quanta ~865) when VmPeak reached the old 8 GB cap at
    # ~480 tokens with RSS at only ~340 MB. The cap stays a guard; RSS is
    # sampled on every poll and stays in the hundreds of MB.
    conf = f"20 {max_new} 250 40 12345 1 0"
    open(f"{REPO}/{GEN_CONF}", "w").write(conf + "\n")
    binp = f"{run_dir}/lfm2_gen_driver.bin"
    rc, out, wall = run_cmd(
        f"cd {REPO} && ( ulimit -c 0 -v 8000000; {QC} {GEN_DRIVER_SRC} {binp} )", 600)
    if rc != 0:
        return {"rc": f"driver-compile rc={rc}", "out": out[-800:]}
    cmd = (f"cd {REPO} && ( ulimit -c 0 -v {vcap_kb}; timeout 14400 nice -n 19 "
           f"{binp} </dev/null > {run_dir}/gen_stdout.txt 2>&1 )")
    proc = subprocess.Popen(["bash", "-c", cmd], cwd=REPO,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            start_new_session=True)
    return {"rc": 0, "pid": proc.pid, "cmd": cmd,
            "driver_compile_ms": round(wall * 1000.0), "bin": binp,
            "conf": conf, "note": "background; poll gen_stdout.txt for DONE"}


def rss_kb_of(binp):
    p = subprocess.run(["bash", "-c",
                        f"ps -o rss= -C {os.path.basename(binp)} 2>/dev/null | head -1"],
                       capture_output=True, text=True)
    return int(p.stdout.strip()) if p.stdout.strip() else None


def parse_gen_output(txt):
    d = {}
    for key in ("user_bytes", "prompt_bytes", "prompt_ids", "load_ms",
                "prefill_ms", "prefill_ms_per_tok", "new_tokens", "gen_ms",
                "gen_ms_per_token", "decode_tok_per_s_x1000"):
        m = re.search(key + r"=(\d+)", txt)
        if m:
            d[key] = int(m.group(1))
    m = re.search(r"---generated---\n(.*?)\n---end---", txt, re.S)
    d["generated_raw"] = m.group(1) if m else ""
    d["state"] = "done" if "DONE" in txt else ("fail" if "FAIL" in txt else "?")
    return d


def proc_status_fields():
    """comm of the bin is 'lfm2_gen_driver' (exactly 15 chars); pgrep -x
    matches comm, so the bash/timeout wrappers' argv never match. A ZOMBIE
    also matches pgrep, so its state is checked and excluded -- the crashed
    attempt-1 process lingered as Z and read as 'running' otherwise."""
    p = subprocess.run(["bash", "-c", "pgrep -x lfm2_gen_driver | head -5"],
                       capture_output=True, text=True)
    for pid in p.stdout.split():
        try:
            state = open(f"/proc/{pid}/stat").read().split()[2]
            if state == "Z":
                continue
        except (OSError, IndexError):
            continue
        out = {"pid": pid, "state": state}
        try:
            for line in open(f"/proc/{pid}/status"):
                if line.startswith(("VmPeak", "VmRSS", "VmSize")):
                    k, v = line.split(":", 1)
                    out[k] = int(v.strip().split()[0])
        except OSError:
            pass
        return out
    return None


def poll_generation(run_dir):
    sof = f"{run_dir}/gen_stdout.txt"
    if not os.path.exists(sof):
        return {"state": "not started"}
    txt = open(sof, errors="replace").read()
    st = proc_status_fields() or {}
    if "DONE" in txt:
        st.update(parse_gen_output(txt))
    else:
        alive = st.get("pid")
        st.update({"state": "running" if alive else "exited-without-DONE",
                   "stdout_tail": txt[-200:]})
    return st


# ------------------------- compile / run / feedback ------------------------

def extract_code(text):
    # the chat template opens a thinking block; the answer follows its close
    if THINK_CLOSE in text:
        text = text.split(THINK_CLOSE, 1)[1]
    text = re.sub(r"\[hb \d+\]", "", text)   # driver heartbeat markers
    i = text.find("```")
    if i >= 0:
        j = text.find("```", i + 3)
        body = text[i + 3:j if j > 0 else len(text)]
        body = re.sub(r"^(quanta|rust|python)?[ \t]*\n", "", body, count=1)
    else:
        body = text
    return body.replace("<|im_end|>", "").strip() + "\n"


def compile_src(src, binp):
    cmd = f"cd {REPO} && ( ulimit -c 0 -v 8000000; timeout 300 {QC} {src} {binp} )"
    rc, out, wall = run_cmd(cmd, 360)
    return rc, out, round(wall * 1000.0), cmd


def run_bin(binp, run_dir):
    cmd = f"cd {REPO} && QUANTA_TIME_S=60 {RUNNER} {binp} </dev/null"
    rc, out, wall = run_cmd(cmd, 120)
    return rc, out, round(wall * 1000.0), cmd


def feedback_text(compile_out=None, run_out=None, run_rc=None):
    brevity = ("IMPORTANT: your previous generations spent the ENTIRE token "
               "budget inside the thinking section. Emit the fence and the "
               "file IMMEDIATELY after at most two or three lines of "
               "thinking; the file itself is only ~20 lines.\n")
    if compile_out is not None:
        return (brevity +
                "Your previous file FAILED TO COMPILE. Compiler diagnostics:\n"
                + compile_out[-1200:]
                + "\nFix exactly these errors and emit the COMPLETE corrected "
                  "file in one ```quanta block. Do not explain.")
    return (brevity +
            f"Your previous file COMPILED but its self-test FAILED (exit {run_rc}). "
            "Runner output:\n" + (run_out or "(no output)")[-800:]
            + "\nFix the logic so main() returns 0, and emit the COMPLETE "
              "corrected file in one ```quanta block. Do not explain.")


# --------------------------------- main ------------------------------------

def load_run(run_id):
    run_dir = f"{REPO}/stage2/run_{run_id}"
    R = json.load(open(f"{run_dir}/run.json"))
    return run_dir, R


def save_run(run_dir, R):
    json.dump(R, open(f"{run_dir}/run.json", "w"), indent=2)


def new_run(run_dir, spec_path):
    head = subprocess.run(["bash", "-c", "git rev-parse --short HEAD"],
                          capture_output=True, text=True, cwd=REPO).stdout.strip()
    qcmd = subprocess.run(["bash", "-c", f"md5sum {QC}"],
                          capture_output=True, text=True).stdout.strip()
    R = {"run_id": os.path.basename(run_dir).replace("run_", ""),
         "spec_path": spec_path, "git_head": head, "qc": qcmd,
         "model": {"path": "/opt/ai/models/quanta/QUANTA-LFM2.5-2.6Bv1-Q4_K_M.gguf"},
         "env": env_snapshot(), "stages": {}}
    os.makedirs(run_dir, exist_ok=True)
    save_run(run_dir, R)
    return R


def main():
    args = sys.argv[1:]
    resume_id = args[args.index("--resume-id") + 1] if "--resume-id" in args else None
    if "--poll" in args:
        rid = resume_id or sorted(os.listdir(f"{REPO}/stage2"))[-1].replace("run_", "")
        run_dir = f"{REPO}/stage2/run_{rid}"
        print(json.dumps(poll_generation(run_dir), indent=1))
        return
    spec_path = next((a for a in args if a.endswith(".quanta")),
                     f"{REPO}/planned/lib_std/mathematics_algebra_boolean_algebra.quanta")
    max_new = int(args[args.index("--max-new") + 1]) if "--max-new" in args else 700
    run_id = resume_id or time.strftime("%Y%m%d_%H%M%S")
    run_dir = f"{REPO}/stage2/run_{run_id}"
    dry = "--dry" in args
    R = new_run(run_dir, spec_path) if not resume_id else \
        json.load(open(f"{run_dir}/run.json"))
    spec = spec_fields(spec_path)
    json.dump(spec, open(f"{run_dir}/spec.json", "w"), indent=2)

    # ---- retrieval + prompt + launch (skipped when resuming) ----
    if not resume_id:
        t0 = time.time()
        nm = name_match(spec)
        kw = keyword_store_search(spec)
        sem = semantic_store_search(spec)
        neighbor, arm = pick_neighbor(spec, kw, sem)
        R["stages"]["retrieval"] = {
            "wall_ms": round((time.time() - t0) * 1000.0),
            "name_match": nm,
            "keyword_store": {"ms": kw["ms"], "terms": kw["terms"],
                              "n_rows": len(kw["rows"]),
                              "top_sources": [r["source"] for r in kw["rows"][:8]],
                              "rc": kw["rc"]},
            "semantic_store": {"embed_ms": sem["embed_ms"], "knn_ms": sem["knn_ms"],
                               "n_curated_rows": len(sem["rows"]),
                               "top": [{"source": r["source"],
                                        "distance": r["distance"]}
                                       for r in sem["rows"][:8]],
                               "rc": sem["rc"]},
            "neighbor": {"disk": neighbor["disk"] if neighbor else None,
                         "store_source": neighbor["store_source"] if neighbor else None,
                         "arm": arm,
                         "bytes": neighbor["bytes"] if neighbor else 0},
        }
        save_run(run_dir, R)
        print(f"[retrieval] name={nm['hit']} kw={len(kw['rows'])} rows "
              f"({kw['ms']} ms) sem embed={sem['embed_ms']}ms "
              f"knn={sem['knn_ms']}ms curated={len(sem['rows'])} "
              f"neighbor={neighbor['disk'] if neighbor else None} (arm={arm})")

        t0 = time.time()
        prompt, ncap, ntok = trim_to_budget(spec, neighbor, PROMPT_TOK_BUDGET)
        open(f"{REPO}/{GEN_PROMPT}", "w").write(prompt)
        open(f"{run_dir}/prompt.txt", "w").write(prompt)
        R["stages"]["prompt"] = {
            "wall_ms": round((time.time() - t0) * 1000.0),
            "hf_tokens": ntok, "bytes": len(prompt),
            "budget": PROMPT_TOK_BUDGET, "neighbor_byte_cap": ncap,
            "card": CARD_PATH,
            "note": "hf_tokens = pre-flight estimate; ground truth is the "
                    "driver's own prompt_ids= (in-tree BPE, see tokcount.txt)"}
        save_run(run_dir, R)
        print(f"[prompt] {len(prompt)} bytes, ~{ntok} hf-tokens "
              f"(budget {PROMPT_TOK_BUDGET}, neighbor cap {ncap})")

        # in-tree BPE ground truth before the expensive run
        binp = f"{run_dir}/tok_count.bin"
        rc, out, wall = run_cmd(
            f"cd {REPO} && ( ulimit -c 0 -v 8000000; {QC} "
            f"{REPO}/stage2/tok_count.quanta {binp} ) && {binp}", 600)
        open(f"{run_dir}/tokcount.txt", "w").write(out)
        m = re.search(r"prompt_ids=(\d+)", out)
        if m:
            R["stages"]["prompt"]["intree_tokens"] = int(m.group(1))
        R["stages"]["prompt"]["tokcount_cmd"] = "qc stage2/tok_count.quanta + run"
        R["stages"]["prompt"]["tokcount_ms"] = round(wall * 1000.0)
        save_run(run_dir, R)
        print(f"[prompt] in-tree BPE count: {out.strip().splitlines()[-1] if out.strip() else out[-200:]}")
        if dry:
            print("[dry] prompt written; generation NOT launched")
            return

        t0 = time.time()
        g = start_generation(run_dir, max_new)
        R["stages"]["generate_launch"] = {**g,
                                          "launch_ms": round((time.time() - t0) * 1000.0),
                                          "max_new": max_new,
                                          "env": env_snapshot()}
        save_run(run_dir, R)
        if g.get("rc") != 0:
            print(f"[generate] LAUNCH FAILED: {g}")
            return
        print(f"[generate] launched pid={g['pid']} conf='{g['conf']}' "
              f"(background; poll: python3 stage2/wire.py --poll "
              f"--resume-id {run_id})")
        return

    # ---- resume: compile/run attempts (+ ONE feedback retry per pass) ----
    sof = f"{run_dir}/gen_stdout.txt"
    txt = open(sof, errors="replace").read() if os.path.exists(sof) else ""
    if "DONE" not in txt:
        if "--relaunch" in args:
            st = proc_status_fields()
            if st and st.get("pid"):
                print("[relaunch] generation still running; refusing. Poll first.")
                return
            crash = {"state": "generation-crash",
                     "stdout_tail": txt[-400:],
                     "note": "driver exited without DONE and without a FAIL "
                             "line; the allocator's MAP_FAILED guard is a "
                             "silent exit(1) (lfm2_mm.quanta ~865)",
                     "env": env_snapshot()}
            R.setdefault("stages", {}).setdefault("generation_crashes", []).append(crash)
            ncrash = len(R["stages"]["generation_crashes"])
            if os.path.exists(sof):
                os.replace(sof, f"{run_dir}/gen_stdout.crash{ncrash}.txt")
            save_run(run_dir, R)
            fb = ("Your previous generation was CUT OFF before the complete "
                  "file was produced. Think briefly (a few lines at most) and "
                  "then emit the COMPLETE corrected file in one ```quanta "
                  "block. Do not explain.")
            prompt2 = open(f"{run_dir}/prompt.txt").read() + \
                "\n===== FIX REQUEST (retry) =====\n" + fb
            open(f"{REPO}/{GEN_PROMPT}", "w").write(prompt2)
            open(f"{run_dir}/prompt_attempt{len(R['stages'].get('attempts', [])) + 1}.txt",
                 "w").write(prompt2)
            R["stages"]["retry_prompt_hf_tokens"] = hf_tok_count(prompt2)
            save_run(run_dir, R)
            print(f"[relaunch] after crash; retry prompt ~"
                  f"{R['stages']['retry_prompt_hf_tokens']} hf-tokens")
            g2 = start_generation(run_dir, max_new)
            R["stages"]["generate_launch"] = {**g2, "retry": "after-crash",
                                              "max_new": max_new,
                                              "env": env_snapshot()}
            save_run(run_dir, R)
            print(f"[relaunch] launched pid={g2.get('pid')}")
            return
        print("[wait] generation not finished; poll first:")
        print(json.dumps(poll_generation(run_dir), indent=1))
        return
    if "attempts" not in R["stages"]:
        R["stages"]["generate"] = parse_gen_output(txt)
        R["stages"]["generate"]["env"] = env_snapshot()
        save_run(run_dir, R)

    attempts = R["stages"].get("attempts", [])
    max_attempts = int(args[args.index("--max-attempts") + 1]) \
        if "--max-attempts" in args else MAX_ATTEMPTS
    if R["stages"].get("outcome") in ("pass",) or len(attempts) >= max_attempts:
        print(f"[done] outcome={R['stages'].get('outcome')} "
              f"attempts={len(attempts)}")
        return
    # the pending generation (attempt 1 or the retry) is in gen_stdout.txt
    attempt_no = len(attempts) + 1
    gen = R["stages"]["generate"]
    raw = gen["generated_raw"]
    open(f"{run_dir}/attempt{attempt_no}.raw.txt", "w").write(raw)
    code = extract_code(raw)
    src = f"{run_dir}/attempt{attempt_no}.quanta"
    open(src, "w").write(code)
    binp = f"{run_dir}/attempt{attempt_no}.bin"
    crc, cout, cms, ccmd = compile_src(src, binp)
    open(f"{run_dir}/attempt{attempt_no}.compile.txt", "w").write(cout)
    att = {"attempt": attempt_no, "src": src, "compile_rc": crc,
           "compile_ms": cms, "compile_cmd": ccmd, "compile_out": cout[-2500:]}
    rrc = rout = None
    if crc == 0:
        rrc, rout, rwall, rcmd = run_bin(binp, run_dir)
        open(f"{run_dir}/attempt{attempt_no}.run.txt", "w").write(rout)
        att.update({"run_rc": rrc, "run_ms": rwall, "run_cmd": rcmd,
                    "run_out": rout[-1500:]})
    attempts.append(att)
    R["stages"]["attempts"] = attempts
    passed = crc == 0 and rrc == 0
    R["stages"]["outcome"] = "pass" if passed else \
        ("compile-fail" if crc != 0 else "run-fail")
    R["stages"]["env"] = env_snapshot()
    save_run(run_dir, R)
    print(f"[attempt {attempt_no}] compile_rc={crc} run_rc={rrc} -> "
          f"{R['stages']['outcome']}")

    if not passed and attempt_no < max_attempts:
        fb = feedback_text(cout if crc != 0 else None, rout, rrc)
        prompt2 = open(f"{run_dir}/prompt.txt").read() + \
            "\n===== FIX REQUEST (retry) =====\n" + fb
        open(f"{REPO}/{GEN_PROMPT}", "w").write(prompt2)
        open(f"{run_dir}/prompt_attempt{attempt_no + 1}.txt", "w").write(prompt2)
        R["stages"]["retry_prompt_hf_tokens"] = hf_tok_count(prompt2)
        save_run(run_dir, R)
        print(f"[retry] prompt+feedback ~{R['stages']['retry_prompt_hf_tokens']} "
              f"hf-tokens; relaunching generation")
        g2 = start_generation(run_dir, max_new)
        R["stages"]["generate_launch"] = {**g2, "retry": True, "max_new": max_new,
                                          "env": env_snapshot()}
        save_run(run_dir, R)
        print(f"[retry] launched pid={g2.get('pid')}; poll again")


if __name__ == "__main__":
    main()
