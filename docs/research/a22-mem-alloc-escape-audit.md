# A22 · Static escape/alias audit of every `mem_alloc` call site — can the P2 auto-free ship?

**Date:** 2026-10-16 · **HEAD at start:** `968d3646` · **Method:** static, text-level, no compilation,
no gate run, no model load (peer unit running SI generations). The analyser is committed beside this
report (`a22-escape-audit.py`); it re-runs over the whole corpus in ~2.6 s wall (`python3
docs/research/a22-escape-audit.py /opt/tali/quanta out.json`) and regenerates every number below.

## 1. The answer

**Escapes are neither "very few" nor "everywhere" — they are 115 of 406 let-bound `lib/std` sites
(28 %), they are fully enumerated in §4, and they are structurally patterned, not scattered.** The
auto-free cannot ship on a simple syntactic rule (a "appears in `return` / assigned to a global"
rule misses 56 of the 115 — every out-param store and every retainer pass), but the flow-sensitive
gap is bounded: **9 retainer functions** in `lib/std` cover all 15 Pr sites, one builtin family
(`w64`/`mem_store` into param or global holders) covers all 51 S sites, and explicit-free
cancellation covers all 106 F sites. The recommendation is **implement the bounded interprocedural
escape analysis before shipping the auto-free — neither ship-with-simple-rule nor keep-parked is
supported by the evidence** (§7).

## 2. The rule under audit (source-derived; SPEC.md is stale)

The P2 auto-free as implemented in the **0.0.242 WIP** (`compiler/0.0.242/src/x86/parse.quanta:1503-1525`,
the A5-fixed detector) marks a binding owned iff it is a **`let x = mem_alloc(...)` direct
initialiser**, at any block depth. Frees fire at every exit of the binding's block
(`owned_scope_pop_one`) — i.e. **every iteration of a loop body** — and `owned_pop_all()` frees all
live owned bindings on every `return`, after the return expression is evaluated
(`parse.quanta:486-529`). Plain reassignment `x = mem_alloc(...)` goes through `parse_assign` and is
**never** marked owned; `mem_realloc` results are never owned (name length ≠ 9); wrapped
initialisers (`1 + mem_alloc(n)`) are never owned.

**State of the tree:** the **0.0.245 shipping line still carries the old, broken detector**
(`compiler/0.0.245/src/x86/parse.quanta:1460-1471` — reads `ira1/ira2` as name offset/length, the A5
dead-code bug), so today the auto-free never fires anywhere. Everything below audits the rule *as
fixed in 0.0.242*, which is what would fire when the detector is ported forward.

Three consuming builtins, two different semantics (`emitter.quanta`): `mem_free(p)` and `drop(p)`
push p on the free-list (`[p+8] = head; HEAP_CTRL = p`, correct since 0.0.243), while `free(p)` is
**munmap(p, [p])** of the whole region (`emitter.quanta:1235-1241`). Under auto-free, an explicit
`mem_free` double-pushes the block on the free list (self-loop chain), and an explicit `free` pushes
a **pointer into now-unmapped memory**. `w64(p,v)` ≡ `mem_store(p,v)` (helpers.quanta:8), so every
`w64(holder, ptr)` writes a pointer value into long-lived memory — an escape the eye skips.

## 3. Method and its verified limits

`a22-escape-audit.py` parses every `.quanta` file (comment-stripped, string-aware), extracts
brace-depth-0 globals, functions (both `: type` and `-> type` returns), closure literals and
imports, then walks each `mem_alloc` site's bound name **and derived names** (aliases, interior
pointers) through the enclosing function occurrence-by-occurrence, classifying every use:

| class | meaning | under the 0.0.242 auto-free |
|---|---|---|
| R | the return statement's **value** is (derived from) the block | caller receives a freed block |
| G | assigned to a module global | global points at a freed block |
| S | written via `mem_store`/`w64` into a holder that outlives the scope (param out-holder / global-backed) | holder points at a freed block |
| Pr | passed to a user function that retains that parameter (returns / stores / transitively) | retainer points at a freed block |
| F | explicitly consumed (`mem_free`/`drop`/`free`) | double free-list push, or push into unmapped memory |
| X | consumed by `mem_realloc`/`realloc` | harmless (block dead by contract) |
| L | consumed locally (reader builtins, arithmetic, indexing, content stores) | sound |
| N | not let-bound (reassignment / inline non-escape) | P2 never owns it — unaffected |
| G-nop2 | reassigned into a global | escapes, but P2 never owns it — today's leak, not a P2 hazard |

Callee resolution is per caller file (own file → imported file → unique definition; `lib/std` has
189 same-name collisions from parallel module copies). Retention summaries are computed to a
fixpoint, position-sensitive. A direct-occurrence test (token not nested inside a call's argument
region) separates `return buf` (R) from `return file_open(cp + 8, ...)` (arg-pass — the case
0.0.242's ordering fix made sound); the same test separates `mem_store(holder, buf)` (escape) from
`mem_store8(dst, mem_load8(buf + i))` (content read); and `u32(x) { return x & 0xffffffff }`
(x25519.quanta:9) is auto-detected as a value cast whose masked result cannot be a live pointer.

**Verified by reading, not just by heuristic:** all 6 G sites (store lines quoted in §4), all 15 Pr
sites and their 6 retainer functions, the 3 `free()` munmap sites, `fs.open`/`stat` (the L shape
0.0.242 §4 proved sound), `substr`, `big_alloc`, `sha256`, `log_leaf_hash` (R+F both real), and both
SEQ-DOUBLE-FREE candidates (re-assignment between frees — false positives, now excluded).
Known-heuristic limits are in §8.

## 4. `lib/std` — every `mem_alloc` site classified (564 sites, 49 files)

Counts by class: **L 185 · G-nop2 113 · F 106 · S 51 (41 into param out-holders, 12 into
global-backed holders) · N 43 · R 44 (43 + 1 inline) · Pr 15 · G 6 · top-level 1.**
Let-bound universe (the P2 rule's reach): **406 sites — 185 L (46 %), 221 (54 %) escape or
double-free.** 13 let-bound non-L sites sit inside loop bodies (per-iteration UAF).

The 6 G sites, store lines verified: `key_derivation.quanta:611,776` (`keystore_master_key =
master_key`), `key_derivation.quanta:864` (`keystore_entries = new_entries`),
`lfm2_bpe.quanta:111,112` (`mt_key = key; mt_val = val` — the source comment itself warns
"module-global CELLS"), `spiffe.quanta:772` (`mtls_ctx = ctx`). The 15 Pr sites pass fresh blocks to
6 retainer functions: `config_expand` (returns its arg), `gguf_ctx_set_kv_index`, `_kv_arr_off`,
`_kv_arr_len`, `_kv_etype`, `_set_tensor_data`, `_set_tensor_dims` (store the param into the
long-lived ctx via `mem_store(ctx + OFF, ptr)`).

| site | var | class | rationale |
|---|---|---|---|
| `aes_gcm.quanta:13` | `res` | R | returned as the function's value |
| `aes_gcm.quanta:17` | `v` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `aes_gcm.quanta:68` | `tag` | R | returned as the function's value |
| `aes_gcm.quanta:76` | `block` | L | consumed locally (reader builtins, arithmetic, content stores); inside a loop body (free would fire every iteration) |
| `aes_gcm.quanta:105` | `block` | L | consumed locally (reader builtins, arithmetic, content stores); inside a loop body (free would fire every iteration) |
| `aes_gcm.quanta:131` | `len_block` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `aes_gcm.quanta:179` | `zero_block` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `aes_gcm.quanta:186` | `J0` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `aes_gcm.quanta:194` | `ctr` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `aes_gcm.quanta:241` | `zero_block` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `aes_gcm.quanta:247` | `J0` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `aes_gcm.quanta:258` | `expected_tag` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `aes_gcm.quanta:277` | `ctr` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `audit_log.quanta:65` | `log_ctx` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `audit_log.quanta:92` | `hash` | R | returned as the function's value; explicitly freed - auto-free would double-push |
| `audit_log.quanta:96` | `prefix` | F | explicitly freed - auto-free would double-push |
| `audit_log.quanta:120` | `hash` | R | returned as the function's value; explicitly freed - auto-free would double-push |
| `audit_log.quanta:124` | `prefix` | F | explicitly freed - auto-free would double-push |
| `audit_log.quanta:162` | `new_leaves` | S | written into a global-backed holder via mem_store/w64 |
| `audit_log.quanta:215` | `next_hashes` | L | consumed locally (reader builtins, arithmetic, content stores); inside a loop body (free would fire every iteration) |
| `audit_log.quanta:341` | `next_hashes` | L | consumed locally (reader builtins, arithmetic, content stores); inside a loop body (free would fire every iteration) |
| `audit_log.quanta:489` | `sig` | S | written into a caller-owned out-param (mem_store/w64); explicitly freed - auto-free would double-push |
| `audit_log.quanta:619` | `pkg` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `big.quanta:35` | `r` | R | returned as the function's value |
| `big.quanta:763` | `-` | ? | top-level let initialised by mem_alloc (module-load) |
| `big.quanta:783` | `buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `code_synthesizer.quanta:70` | `name_copy` | S | written into a global-backed holder via mem_store/w64 |
| `config.quanta:103` | `buf` | R | returned as the function's value |
| `config.quanta:237` | `val` | Pr | passed to config_expand, which retains that parameter; inside a loop body (free would fire every iteration) |
| `config.quanta:292` | `name` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `config.quanta:324` | `sec` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `config.quanta:332` | `kk` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `config.quanta:345` | `pre` | Pr | passed to config_expand, which retains that parameter |
| `config.quanta:353` | `suf` | Pr | passed to config_expand, which retains that parameter |
| `config.quanta:444` | `rev` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `config.quanta:456` | `o` | R | returned as the function's value |
| `crypto.quanta:109` | `H` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `crypto.quanta:119` | `w` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `crypto.quanta:172` | `out` | R | returned as the function's value |
| `crypto.quanta:233` | `kpad` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `crypto.quanta:245` | `inner` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `crypto.quanta:255` | `ibuf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `crypto.quanta:262` | `outer` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `crypto.quanta:271` | `obuf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `crypto.quanta:556` | `st` | R | returned as the function's value |
| `crypto.quanta:560` | `rk` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `ct.quanta:72` | `log_id` | F | explicitly freed - auto-free would double-push |
| `ct.quanta:126` | `signature` | F | explicitly freed - auto-free would double-push |
| `ct.quanta:138` | `sct` | R | returned as the function's value |
| `ct.quanta:168` | `scts` | S | written into a caller-owned out-param (mem_store/w64) |
| `ct.quanta:203` | `new_scts` | L | consumed locally (reader builtins, arithmetic, content stores); inside a loop body (free would fire every iteration) |
| `ct.quanta:307` | `current_hash` | F | explicitly freed - auto-free would double-push |
| `ct.quanta:320` | `combined` | F | explicitly freed - auto-free would double-push; inside a loop body (free would fire every iteration) |
| `cuda_daemon.quanta:72` | `tmp` | F | explicitly freed - auto-free would double-push |
| `cuda_daemon.quanta:96` | `tmp` | F | explicitly freed - auto-free would double-push |
| `cuda_daemon.quanta:178` | `buf` | F | explicitly freed - auto-free would double-push |
| `cuda_daemon.quanta:242` | `line` | F | explicitly freed - auto-free would double-push |
| `cuda_daemon.quanta:266` | `reply_buf` | R | returned as the function's value; explicitly freed - auto-free would double-push |
| `cuda_daemon.quanta:321` | `cmd` | F | explicitly freed - auto-free would double-push |
| `cuda_daemon.quanta:334` | `cmd` | F | explicitly freed - auto-free would double-push |
| `cuda_daemon.quanta:348` | `cmd` | F | explicitly freed - auto-free would double-push |
| `cuda_daemon.quanta:358` | `cmd` | F | explicitly freed - auto-free would double-push |
| `cuda_daemon.quanta:372` | `cmd` | F | explicitly freed - auto-free would double-push |
| `cuda_daemon.quanta:382` | `cmd` | F | explicitly freed - auto-free would double-push |
| `cuda_daemon.quanta:395` | `cmd` | F | explicitly freed - auto-free would double-push |
| `cuda_daemon.quanta:405` | `cmd` | F | explicitly freed - auto-free would double-push |
| `cuda_daemon.quanta:427` | `cmd` | F | explicitly freed - auto-free would double-push |
| `cuda_daemon.quanta:460` | `cmd` | F | explicitly freed - auto-free would double-push |
| `cuda_daemon.quanta:496` | `cuda_pool` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `cuda_daemon.quanta:587` | `cmd` | F | explicitly freed - auto-free would double-push |
| `cuda_daemon.quanta:609` | `cmd` | F | explicitly freed - auto-free would double-push |
| `cuda_daemon.quanta:635` | `cmd` | F | explicitly freed - auto-free would double-push |
| `cuda_daemon.quanta:654` | `cmd` | F | explicitly freed - auto-free would double-push |
| `cuda_subprocess.quanta:53` | `tmp` | F | explicitly freed - auto-free would double-push |
| `cuda_subprocess.quanta:78` | `tmp` | F | explicitly freed - auto-free would double-push |
| `cuda_subprocess.quanta:117` | `sh` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `cuda_subprocess.quanta:118` | `dash_c` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `cuda_subprocess.quanta:119` | `cmdbuf` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `cuda_subprocess.quanta:120` | `argv` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `cuda_subprocess.quanta:138` | `status` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `cuda_subprocess.quanta:152` | `buf` | R | returned as the function's value; explicitly freed - auto-free would double-push |
| `cuda_subprocess.quanta:187` | `cmd` | F | explicitly freed - auto-free would double-push |
| `cuda_subprocess.quanta:202` | `cmd` | F | explicitly freed - auto-free would double-push |
| `cuda_subprocess.quanta:218` | `cmd` | F | explicitly freed - auto-free would double-push |
| `cuda_subprocess.quanta:230` | `cmd` | F | explicitly freed - auto-free would double-push |
| `cuda_subprocess.quanta:246` | `cmd` | F | explicitly freed - auto-free would double-push |
| `cuda_subprocess.quanta:258` | `cmd` | F | explicitly freed - auto-free would double-push |
| `cuda_subprocess.quanta:272` | `cmd` | F | explicitly freed - auto-free would double-push |
| `cuda_subprocess.quanta:284` | `cmd` | F | explicitly freed - auto-free would double-push |
| `cuda_subprocess.quanta:305` | `cmd` | F | explicitly freed - auto-free would double-push |
| `fmt.quanta:9` | `buf` | F | explicitly freed - auto-free would double-push |
| `fs.quanta:13` | `cp` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `fs.quanta:27` | `buf` | R | returned as the function's value |
| `fs.quanta:56` | `cp` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `fs.quanta:66` | `cp` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `fs.quanta:76` | `cp` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `fs.quanta:86` | `cp` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `fs.quanta:96` | `co` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `fs.quanta:101` | `cn` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `fs.quanta:111` | `cp` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:226` | `klen_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:227` | `vtype_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:228` | `slen_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:238` | `gguf_kv_index` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `gguf.quanta:239` | `gguf_kv_arr_off` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `gguf.quanta:240` | `gguf_kv_arr_len` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `gguf.quanta:241` | `gguf_kv_etype` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `gguf.quanta:344` | `gguf_tensor_data` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `gguf.quanta:346` | `nlen_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:347` | `ndims_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:348` | `dim_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:349` | `dtype_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:350` | `off_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:351` | `name_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:355` | `gguf_tensor_dims` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `gguf.quanta:388` | `name_copy` | S | written into a global-backed holder via mem_store/w64; inside a loop body (free would fire every iteration) |
| `gguf.quanta:415` | `hdr` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:706` | `buf` | R | returned as the function's value |
| `gguf.quanta:926` | `lb` | L | consumed locally (reader builtins, arithmetic, content stores); inside a loop body (free would fire every iteration) |
| `gguf.quanta:929` | `kb` | L | consumed locally (reader builtins, arithmetic, content stores); inside a loop body (free would fire every iteration) |
| `gguf.quanta:950` | `lb` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:954` | `tb` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:963` | `lb` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:974` | `b` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:997` | `b` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:1023` | `lb` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:1026` | `buf` | R | returned as the function's value |
| `gguf.quanta:1040` | `lb` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:1118` | `lb` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:1137` | `lb` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:1148` | `buf` | R | returned as the function's value |
| `gguf.quanta:1178` | `lb` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:1209` | `lb` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:1380` | `raw` | F | explicitly freed - auto-free would double-push |
| `gguf.quanta:1386` | `raw` | F | explicitly freed - auto-free would double-push |
| `gguf.quanta:1392` | `raw` | F | explicitly freed - auto-free would double-push |
| `gguf.quanta:1398` | `raw` | F | explicitly freed - auto-free would double-push |
| `gguf.quanta:1404` | `raw` | F | explicitly freed - auto-free would double-push |
| `gguf.quanta:1410` | `raw` | F | explicitly freed - auto-free would double-push |
| `gguf.quanta:1416` | `raw` | F | explicitly freed - auto-free would double-push |
| `gguf.quanta:1422` | `raw` | F | explicitly freed - auto-free would double-push |
| `gguf.quanta:1428` | `raw` | F | explicitly freed - auto-free would double-push |
| `gguf.quanta:1434` | `raw` | F | explicitly freed - auto-free would double-push |
| `gguf.quanta:1445` | `raw` | F | explicitly freed - auto-free would double-push |
| `gguf.quanta:1456` | `raw` | F | explicitly freed - auto-free would double-push |
| `gguf.quanta:1467` | `raw` | F | explicitly freed - auto-free would double-push |
| `gguf.quanta:1478` | `raw` | F | explicitly freed - auto-free would double-push |
| `gguf.quanta:1489` | `raw` | F | explicitly freed - auto-free would double-push |
| `gguf.quanta:1500` | `raw` | F | explicitly freed - auto-free would double-push |
| `gguf.quanta:1544` | `raw` | F | explicitly freed - auto-free would double-push |
| `gguf.quanta:2128` | `scratch` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:2381` | `sb` | L | consumed locally (reader builtins, arithmetic, content stores); inside a loop body (free would fire every iteration) |
| `gguf.quanta:3141` | `tmp` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:3279` | `tmp` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:3324` | `tile_tmp` | L | consumed locally (reader builtins, arithmetic, content stores); inside a loop body (free would fire every iteration) |
| `gguf.quanta:3340` | `block` | L | consumed locally (reader builtins, arithmetic, content stores); inside a loop body (free would fire every iteration) |
| `gguf.quanta:3387` | `block` | L | consumed locally (reader builtins, arithmetic, content stores); inside a loop body (free would fire every iteration) |
| `gguf.quanta:3461` | `pl_tensor_idx` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `gguf.quanta:3462` | `pl_tensor_size` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `gguf.quanta:3463` | `pl_tensor_data` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `gguf.quanta:3464` | `pl_tensor_lru` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `gguf.quanta:3524` | `buf` | R | returned as the function's value; written into a global-backed holder via mem_store/w64; explicitly freed - auto-free would double-push |
| `gguf.quanta:3525` | `raw` | F | explicitly freed - auto-free would double-push |
| `gguf.quanta:3631` | `moe_slot_data` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `gguf.quanta:3632` | `moe_slot_ready` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `gguf.quanta:3633` | `moe_slot_done` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `gguf.quanta:3634` | `moe_slot_consumed` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `gguf.quanta:3847` | `b8` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:3848` | `b4` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:3902` | `buf` | R | returned as the function's value |
| `gguf.quanta:4057` | `ctx` | R | returned as the function's value |
| `gguf.quanta:4315` | `hdr` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:4350` | `buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:4368` | `lb` | L | consumed locally (reader builtins, arithmetic, content stores); inside a loop body (free would fire every iteration) |
| `gguf.quanta:4372` | `kb` | L | consumed locally (reader builtins, arithmetic, content stores); inside a loop body (free would fire every iteration) |
| `gguf.quanta:4394` | `lb` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:4403` | `klen_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:4404` | `vtype_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:4405` | `slen_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:4412` | `kv_index` | Pr | passed to gguf_ctx_set_kv_index, which retains that parameter |
| `gguf.quanta:4413` | `kv_arr_off` | Pr | passed to gguf_ctx_set_kv_arr_off, which retains that parameter |
| `gguf.quanta:4414` | `kv_arr_len` | Pr | passed to gguf_ctx_set_kv_arr_len, which retains that parameter |
| `gguf.quanta:4415` | `kv_etype` | Pr | passed to gguf_ctx_set_kv_etype, which retains that parameter |
| `gguf.quanta:4499` | `tdata` | Pr | passed to gguf_ctx_set_tensor_data, which retains that parameter |
| `gguf.quanta:4502` | `tdims` | Pr | passed to gguf_ctx_set_tensor_dims, which retains that parameter |
| `gguf.quanta:4505` | `nlen_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:4506` | `ndims_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:4507` | `dim_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:4508` | `dtype_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:4509` | `off_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:4510` | `name_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:4547` | `name_copy` | L | consumed locally; also stored into a same-scope block (safe under auto-free); inside a loop body (free would fire every iteration) |
| `gguf.quanta:4649` | `buf` | R | returned as the function's value |
| `gguf_ctx.quanta:27` | `ctx` | R | returned as the function's value |
| `gguf_ctx.quanta:285` | `hdr` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf_ctx.quanta:320` | `buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf_ctx.quanta:338` | `lb` | L | consumed locally (reader builtins, arithmetic, content stores); inside a loop body (free would fire every iteration) |
| `gguf_ctx.quanta:342` | `kb` | L | consumed locally (reader builtins, arithmetic, content stores); inside a loop body (free would fire every iteration) |
| `gguf_ctx.quanta:364` | `lb` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf_ctx.quanta:373` | `klen_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf_ctx.quanta:374` | `vtype_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf_ctx.quanta:375` | `slen_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf_ctx.quanta:382` | `kv_index` | Pr | passed to gguf_ctx_set_kv_index, which retains that parameter |
| `gguf_ctx.quanta:383` | `kv_arr_off` | Pr | passed to gguf_ctx_set_kv_arr_off, which retains that parameter |
| `gguf_ctx.quanta:384` | `kv_arr_len` | Pr | passed to gguf_ctx_set_kv_arr_len, which retains that parameter |
| `gguf_ctx.quanta:385` | `kv_etype` | Pr | passed to gguf_ctx_set_kv_etype, which retains that parameter |
| `gguf_ctx.quanta:469` | `tdata` | Pr | passed to gguf_ctx_set_tensor_data, which retains that parameter |
| `gguf_ctx.quanta:472` | `tdims` | Pr | passed to gguf_ctx_set_tensor_dims, which retains that parameter |
| `gguf_ctx.quanta:475` | `nlen_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf_ctx.quanta:476` | `ndims_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf_ctx.quanta:477` | `dim_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf_ctx.quanta:478` | `dtype_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf_ctx.quanta:479` | `off_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf_ctx.quanta:480` | `name_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf_ctx.quanta:517` | `name_copy` | L | consumed locally; also stored into a same-scope block (safe under auto-free); inside a loop body (free would fire every iteration) |
| `gguf_ctx.quanta:619` | `buf` | R | returned as the function's value |
| `hsm.quanta:368` | `pkcs11_slots` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `hsm.quanta:426` | `pkcs11_sessions` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `hsm.quanta:719` | `pubkey` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `hsm.quanta:720` | `privkey` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `hsm.quanta:726` | `pub_obj` | S | written into a caller-owned out-param (mem_store/w64) |
| `hsm.quanta:734` | `priv_obj` | S | written into a caller-owned out-param (mem_store/w64) |
| `hsm.quanta:748` | `pubkey` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `hsm.quanta:749` | `privkey` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `hsm.quanta:754` | `pub_obj` | S | written into a caller-owned out-param (mem_store/w64) |
| `hsm.quanta:761` | `priv_obj` | S | written into a caller-owned out-param (mem_store/w64) |
| `hsm.quanta:775` | `pubkey` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `hsm.quanta:776` | `privkey` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `hsm.quanta:791` | `pub_obj` | S | written into a caller-owned out-param (mem_store/w64) |
| `hsm.quanta:798` | `priv_obj` | S | written into a caller-owned out-param (mem_store/w64) |
| `hsm.quanta:920` | `tpm_handles` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `hsm.quanta:1015` | `enclave_report` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `hsm.quanta:1023` | `enclave_report` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `hsm.quanta:1032` | `report` | S | written into a caller-owned out-param (mem_store/w64) |
| `hsm.quanta:1053` | `report` | S | written into a caller-owned out-param (mem_store/w64) |
| `hsm.quanta:1072` | `quote` | S | written into a caller-owned out-param (mem_store/w64) |
| `hsm.quanta:1169` | `attestation` | S | written into a caller-owned out-param (mem_store/w64) |
| `hsm.quanta:1176` | `quote` | S | written into a caller-owned out-param (mem_store/w64) |
| `hsm.quanta:1183` | `report` | S | written into a caller-owned out-param (mem_store/w64) |
| `hsm.quanta:1232` | `-` | N | inline call, no binding |
| `json.quanta:83` | `out` | R | returned as the function's value |
| `json.quanta:250` | `v` | R | returned as the function's value |
| `json.quanta:259` | `v` | R | returned as the function's value |
| `json.quanta:269` | `v` | R | returned as the function's value |
| `json.quanta:280` | `v` | R | returned as the function's value |
| `json.quanta:289` | `v` | R | returned as the function's value |
| `json.quanta:303` | `v` | R | returned as the function's value; inside a loop body (free would fire every iteration) |
| `json.quanta:318` | `v` | R | returned as the function's value; inside a loop body (free would fire every iteration) |
| `json.quanta:335` | `v` | R | returned as the function's value; inside a loop body (free would fire every iteration) |
| `json.quanta:359` | `v` | R | returned as the function's value; inside a loop body (free would fire every iteration) |
| `key_derivation.quanta:14` | `ipad` | F | explicitly freed - auto-free would double-push |
| `key_derivation.quanta:15` | `opad` | F | explicitly freed - auto-free would double-push |
| `key_derivation.quanta:29` | `inner` | F | explicitly freed - auto-free would double-push |
| `key_derivation.quanta:55` | `u` | F | explicitly freed - auto-free would double-push |
| `key_derivation.quanta:56` | `f` | F | explicitly freed - auto-free would double-push |
| `key_derivation.quanta:57` | `block_salt` | F | explicitly freed - auto-free would double-push |
| `key_derivation.quanta:125` | `zero_salt` | F | explicitly freed - auto-free would double-push |
| `key_derivation.quanta:146` | `t` | F | explicitly freed - auto-free would double-push |
| `key_derivation.quanta:164` | `ipad` | F | explicitly freed - auto-free would double-push; inside a loop body (free would fire every iteration) |
| `key_derivation.quanta:165` | `opad` | F | explicitly freed - auto-free would double-push; inside a loop body (free would fire every iteration) |
| `key_derivation.quanta:217` | `prk` | F | explicitly freed - auto-free would double-push |
| `key_derivation.quanta:300` | `v` | F | explicitly freed - auto-free would double-push |
| `key_derivation.quanta:301` | `xy` | F | explicitly freed - auto-free would double-push |
| `key_derivation.quanta:302` | `b` | F | explicitly freed - auto-free would double-push |
| `key_derivation.quanta:306` | `pbkdf2_out` | F | explicitly freed - auto-free would double-push |
| `key_derivation.quanta:384` | `memory` | F | explicitly freed - auto-free would double-push |
| `key_derivation.quanta:388` | `h0` | F | explicitly freed - auto-free would double-push |
| `key_derivation.quanta:536` | `keystore_ctx` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `key_derivation.quanta:562` | `keystore_path` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `key_derivation.quanta:603` | `salt` | S | written into a global-backed holder via mem_store/w64; explicitly freed - auto-free would double-push |
| `key_derivation.quanta:607` | `nonce` | S | written into a global-backed holder via mem_store/w64; explicitly freed - auto-free would double-push |
| `key_derivation.quanta:611` | `master_key` | G | assigned to a module global; explicitly freed - auto-free would double-push |
| `key_derivation.quanta:639` | `keystore_entries` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `key_derivation.quanta:651` | `entries_data` | F | explicitly freed - auto-free would double-push |
| `key_derivation.quanta:667` | `encrypted` | F | explicitly freed - auto-free would double-push |
| `key_derivation.quanta:668` | `tag` | F | explicitly freed - auto-free would double-push |
| `key_derivation.quanta:687` | `tag_ptr` | S | written into a global-backed holder via mem_store/w64; explicitly freed - auto-free would double-push |
| `key_derivation.quanta:776` | `master_key` | G | assigned to a module global; explicitly freed - auto-free would double-push |
| `key_derivation.quanta:793` | `encrypted` | F | explicitly freed - auto-free would double-push |
| `key_derivation.quanta:808` | `entries_data` | F | explicitly freed - auto-free would double-push |
| `key_derivation.quanta:814` | `tag` | F | explicitly freed - auto-free would double-push |
| `key_derivation.quanta:832` | `keystore_entries` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `key_derivation.quanta:864` | `new_entries` | G | assigned to a module global |
| `key_derivation.quanta:1006` | `new_key` | L | consumed locally; also stored into a same-scope block (safe under auto-free); inside a loop body (free would fire every iteration) |
| `key_derivation.quanta:1067` | `entry` | F | explicitly freed - auto-free would double-push |
| `key_derivation.quanta:1078` | `entry` | F | explicitly freed - auto-free would double-push |
| `kv_cache.quanta:14` | `kv_k_ptr` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `kv_cache.quanta:15` | `kv_v_ptr` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_bpe.quanta:111` | `key` | G | assigned to a module global |
| `lfm2_bpe.quanta:112` | `val` | G | assigned to a module global |
| `lfm2_bpe.quanta:176` | `ml_buf` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_bpe.quanta:248` | `bpe_vocab` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_bpe.quanta:250` | `bpe_merges` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_bpe.quanta:272` | `bpe_byte_id` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_bpe.quanta:273` | `tmp` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `lfm2_bpe.quanta:319` | `bpe_sym_off` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_bpe.quanta:320` | `bpe_sym_cap_arr` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_bpe.quanta:414` | `bl` | L | consumed locally (reader builtins, arithmetic, content stores); inside a loop body (free would fire every iteration) |
| `lfm2_bpe.quanta:596` | `cell` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `lfm2_bpe.quanta:606` | `bpe_special_ids` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_bpe.quanta:607` | `bpe_special_len` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_bpe.quanta:608` | `bpe_special_ptr` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_bpe.quanta:670` | `idcell` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `lfm2_bpe.quanta:686` | `bl` | L | consumed locally (reader builtins, arithmetic, content stores); inside a loop body (free would fire every iteration) |
| `lfm2_forward.quanta:94` | `fc_nkv` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:107` | `cell` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `lfm2_forward.quanta:211` | `fc_sc_ip` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:212` | `fc_sc_bx` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:213` | `fc_sc_kw` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:214` | `fc_sc_g` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:215` | `fc_sc_k` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:216` | `fc_sc_y` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:385` | `fc_kvbuf` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:436` | `fc_cos` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:437` | `fc_sin` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:567` | `fc_at_qn` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:568` | `fc_at_kn` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:571` | `fc_at_q` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:572` | `fc_at_k` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:573` | `fc_at_v` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:574` | `fc_at_h` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:584` | `fc_at_sc` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:585` | `fc_at_out` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:790` | `fc_fw_x` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:791` | `fc_fw_n` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:792` | `fc_fw_a` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:793` | `fc_fw_ff` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:794` | `fc_fw_f` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:795` | `fc_fw_logits` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:799` | `fc_fw_conv` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:833` | `fc_fw_normbuf` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:876` | `fc_ffn_f_gate` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:877` | `fc_ffn_f_up` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:1085` | `fc_pf_src` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:1086` | `fc_pf_dst` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:1087` | `fc_pf_r` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:1088` | `fc_pf_n` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:1089` | `fc_pf_a` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:1090` | `fc_pf_o` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:1091` | `fc_pf_g` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:1092` | `fc_pf_u` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:1093` | `fc_pf_f` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:1094` | `fc_pf_q` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:1095` | `fc_pf_k` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:1096` | `fc_pf_v` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:1097` | `fc_pf_bcx` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:1098` | `fc_pf_sc` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:1099` | `fc_pf_h` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:1100` | `fc_pf_qn` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:1101` | `fc_pf_kn` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:1102` | `fc_pf_sg` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:1103` | `fc_pf_sk` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:1104` | `fc_pf_sbx` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:1105` | `fc_pf_skw` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:1360` | `fc_fw_normbuf` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_mm.quanta:47` | `mm_rowbuf` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_mm.quanta:50` | `mm_rowraw` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_mm.quanta:132` | `mm_blk_raw` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_mm.quanta:134` | `mm_blk_f64` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_mm.quanta:324` | `mask` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `lfm2_mm.quanta:341` | `buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `lfm2_mm.quanta:369` | `buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `lfm2_mm.quanta:769` | `raw` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `lfm2_mm.quanta:770` | `f64b` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `lfm2_mm.quanta:772` | `acc` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `lfm2_mm.quanta:773` | `cell` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `lfm2_mm.quanta:824` | `mm_dot_acc` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_mm.quanta:825` | `mm_dot_tmp` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_mm.quanta:1193` | `pl_genp` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_mm.quanta:1194` | `pl_stopp` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_mm.quanta:1195` | `pl_donep` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_mm.quanta:1196` | `pl_slots` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_model.quanta:129` | `LFM2_SLOTS` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `linalg.quanta:19` | `p` | R | returned as the function's value |
| `linalg.quanta:192` | `buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `linalg.quanta:244` | `aug` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `loader_traits.quanta:46` | `qmodel_ctx_table` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `loader_traits.quanta:114` | `buf` | N | plain reassignment, not let-bound |
| `loader_traits.quanta:124` | `buf` | N | plain reassignment, not let-bound |
| `loader_traits.quanta:138` | `b` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `map.quanta:75` | `map_last_chunk` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `map.quanta:92` | `map_chunk_tab` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `math.quanta:268` | `b` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `matmul_q4k.quanta:131` | `w` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `ml_kem.quanta:16` | `u64` | N | plain reassignment, not let-bound; inside a loop body (free would fire every iteration) |
| `ml_kem.quanta:24` | `u64` | N | plain reassignment, not let-bound; inside a loop body (free would fire every iteration) |
| `ml_kem.quanta:116` | `u64` | N | plain reassignment, not let-bound; inside a loop body (free would fire every iteration) |
| `ml_kem.quanta:124` | `u64` | N | plain reassignment, not let-bound; inside a loop body (free would fire every iteration) |
| `ml_kem.quanta:143` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:151` | `u64` | N | plain reassignment, not let-bound; inside a loop body (free would fire every iteration) |
| `ml_kem.quanta:229` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:230` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:234` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:238` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:239` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:254` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:291` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:309` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:317` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:322` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:325` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:326` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:327` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:342` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:345` | `u64` | N | plain reassignment, not let-bound; inside a loop body (free would fire every iteration) |
| `ml_kem.quanta:353` | `u64` | N | plain reassignment, not let-bound; inside a loop body (free would fire every iteration) |
| `ml_kem.quanta:367` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:376` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:389` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:391` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:393` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:416` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:422` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:435` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:437` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:441` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:443` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:468` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem_constants.quanta:102` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem_constants.quanta:119` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem_constants.quanta:139` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem_constants.quanta:146` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem_constants.quanta:187` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem_constants.quanta:194` | `u64` | N | plain reassignment, not let-bound |
| `mmap_access.quanta:18` | `mmap_ptr` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `ocsp.quanta:156` | `req` | S | written into a caller-owned out-param (mem_store/w64) |
| `ocsp.quanta:179` | `certids` | S | written into a caller-owned out-param (mem_store/w64) |
| `ocsp.quanta:207` | `algo_oid_buf` | L | consumed locally (reader builtins, arithmetic, content stores); inside a loop body (free would fire every iteration) |
| `ocsp.quanta:216` | `issuer_hash` | L | consumed locally; also stored into a same-scope block (safe under auto-free); inside a loop body (free would fire every iteration) |
| `ocsp.quanta:221` | `issuer_key_hash` | L | consumed locally; also stored into a same-scope block (safe under auto-free); inside a loop body (free would fire every iteration) |
| `ocsp.quanta:226` | `serial` | L | consumed locally; also stored into a same-scope block (safe under auto-free); inside a loop body (free would fire every iteration) |
| `ocsp.quanta:230` | `certid` | L | consumed locally; also stored into a same-scope block (safe under auto-free); inside a loop body (free would fire every iteration) |
| `ocsp.quanta:289` | `resp` | S | written into a caller-owned out-param (mem_store/w64) |
| `ocsp.quanta:317` | `oid_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `ocsp.quanta:378` | `key_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `ocsp.quanta:418` | `sig_buf` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `ocsp.quanta:437` | `resp` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `ocsp.quanta:452` | `ocsp_resp` | S | written into a caller-owned out-param (mem_store/w64) |
| `ocsp.quanta:505` | `resps` | S | written into a caller-owned out-param (mem_store/w64) |
| `ocsp.quanta:559` | `single` | L | consumed locally; also stored into a same-scope block (safe under auto-free); inside a loop body (free would fire every iteration) |
| `ocsp.quanta:681` | `ocsp_cache` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `pattern_library.quanta:38` | `name_copy` | S | written into a global-backed holder via mem_store/w64 |
| `patterns.quanta:37` | `name_copy` | S | written into a global-backed holder via mem_store/w64 |
| `qmodel_cache.quanta:67` | `qmc_table` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `qmodel_cache.quanta:68` | `qmc_budget` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `qmodel_cache.quanta:69` | `qmc_used` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `qmodel_cache.quanta:70` | `qmc_ntensors` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `qmodel_cache.quanta:71` | `qmc_stat` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `quantum.quanta:149` | `st` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `quantum.quanta:212` | `out` | R | returned as the function's value |
| `quantum.quanta:218` | `out` | R | returned as the function's value |
| `quantum.quanta:224` | `out` | R | returned as the function's value |
| `quantum.quanta:230` | `out` | R | returned as the function's value |
| `rag.quanta:94` | `b` | R | returned as the function's value |
| `safetensors.quanta:104` | `lb` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `safetensors.quanta:117` | `buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `safetensors.quanta:431` | `tmp` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `safetensors.quanta:438` | `tmp` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `safetensors.quanta:504` | `ctx` | R | returned as the function's value |
| `safetensors.quanta:575` | `lb` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `safetensors.quanta:581` | `buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `safetensors.quanta:820` | `tmp` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `safetensors.quanta:826` | `tmp` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `sha3_hash.quanta:57` | `st` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `sidechannel.quanta:125` | `ptr` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `sidechannel.quanta:309` | `r` | F | explicitly freed - auto-free would double-push |
| `sidechannel.quanta:411` | `sk_mask` | F | explicitly freed - auto-free would double-push |
| `sidechannel.quanta:412` | `sk_share` | F | explicitly freed - auto-free would double-push |
| `sidechannel.quanta:417` | `tmp_sk` | F | explicitly freed - auto-free would double-push |
| `sidechannel.quanta:437` | `r_mask` | F | explicitly freed - auto-free would double-push |
| `sidechannel.quanta:457` | `sk` | F | explicitly freed - auto-free would double-push |
| `sidechannel.quanta:550` | `sk` | F | explicitly freed - auto-free would double-push |
| `sidechannel.quanta:606` | `sk` | F | explicitly freed - auto-free would double-push |
| `sidechannel.quanta:618` | `sk` | F | explicitly freed - auto-free would double-push |
| `sidechannel.quanta:741` | `timing_samples` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `sp_tokenizer.quanta:20` | `stat_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `sp_tokenizer.quanta:25` | `raw` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `sp_tokenizer.quanta:36` | `sp_vocab_ptr` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `spec_to_ir.quanta:100` | `ir` | R | returned as the function's value |
| `spiffe.quanta:113` | `td_buf` | S | written into a caller-owned out-param (mem_store/w64); explicitly freed - auto-free would double-push |
| `spiffe.quanta:123` | `path_buf` | S | written into a caller-owned out-param (mem_store/w64) |
| `spiffe.quanta:145` | `id` | S | written into a caller-owned out-param (mem_store/w64) |
| `spiffe.quanta:215` | `id_copy` | S | written into a caller-owned out-param (mem_store/w64); inside a loop body (free would fire every iteration) |
| `spiffe.quanta:351` | `id_copy` | S | written into a caller-owned out-param (mem_store/w64); inside a loop body (free would fire every iteration) |
| `spiffe.quanta:454` | `svid` | S | written into a caller-owned out-param (mem_store/w64) |
| `spiffe.quanta:470` | `svid` | S | written into a caller-owned out-param (mem_store/w64) |
| `spiffe.quanta:527` | `td` | S | written into a caller-owned out-param (mem_store/w64); explicitly freed - auto-free would double-push |
| `spiffe.quanta:530` | `name_copy` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `spiffe.quanta:570` | `bundle` | S | written into a caller-owned out-param (mem_store/w64); explicitly freed - auto-free would double-push |
| `spiffe.quanta:573` | `td_copy` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `spiffe.quanta:609` | `fed` | S | written into a caller-owned out-param (mem_store/w64); explicitly freed - auto-free would double-push |
| `spiffe.quanta:612` | `td_copy` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `spiffe.quanta:644` | `workload` | S | written into a caller-owned out-param (mem_store/w64); explicitly freed - auto-free would double-push |
| `spiffe.quanta:647` | `id_copy` | F | explicitly freed - auto-free would double-push |
| `spiffe.quanta:659` | `sel_copy` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `spiffe.quanta:772` | `ctx` | G | assigned to a module global; written into a caller-owned out-param (mem_store/w64); explicitly freed - auto-free would double-push |
| `spiffe.quanta:775` | `id_copy` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `st_ctx.quanta:16` | `-` | R-inline | inline `return mem_alloc(...)` |
| `st_ctx.quanta:82` | `lb` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `st_ctx.quanta:88` | `buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `st_ctx.quanta:327` | `tmp` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `st_ctx.quanta:333` | `tmp` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `str.quanta:39` | `buf` | R | returned as the function's value |
| `str.quanta:109` | `num_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `supply_chain.quanta:43` | `sc_ctx` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `supply_chain.quanta:47` | `policies` | S | written into a global-backed holder via mem_store/w64 |
| `supply_chain.quanta:54` | `cache` | S | written into a global-backed holder via mem_store/w64 |
| `supply_chain.quanta:79` | `new_policies` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `supply_chain.quanta:113` | `results` | S | written into a caller-owned out-param (mem_store/w64) |
| `supply_chain.quanta:323` | `ctx` | F | explicitly freed - auto-free would double-push |
| `tls_resumption.quanta:63` | `key` | S | written into a caller-owned out-param (mem_store/w64); explicitly freed - auto-free would double-push |
| `tls_resumption.quanta:67` | `name` | S | written into a caller-owned out-param (mem_store/w64) |
| `tls_resumption.quanta:83` | `ticket_keys` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `tls_resumption.quanta:154` | `tag` | F | explicitly freed - auto-free would double-push |
| `tls_resumption.quanta:158` | `aad` | F | explicitly freed - auto-free would double-push |
| `tls_resumption.quanta:183` | `aad` | F | explicitly freed - auto-free would double-push |
| `tls_resumption.quanta:213` | `iv` | F | explicitly freed - auto-free would double-push |
| `tls_resumption.quanta:218` | `ciphertext` | F | explicitly freed - auto-free would double-push |
| `tls_resumption.quanta:224` | `tag` | F | explicitly freed - auto-free would double-push |
| `tls_resumption.quanta:231` | `aad` | F | explicitly freed - auto-free would double-push |
| `tls_resumption.quanta:270` | `ticket` | S | written into a caller-owned out-param (mem_store/w64) |
| `tls_resumption.quanta:324` | `parsed` | S | written into a caller-owned out-param (mem_store/w64); explicitly freed - auto-free would double-push |
| `tls_resumption.quanta:361` | `ciphertext` | F | explicitly freed - auto-free would double-push |
| `tls_resumption.quanta:363` | `tag` | F | explicitly freed - auto-free would double-push |
| `tls_resumption.quanta:380` | `plaintext` | S | written into a caller-owned out-param (mem_store/w64); explicitly freed - auto-free would double-push |
| `tls_resumption.quanta:387` | `aad` | F | explicitly freed - auto-free would double-push |
| `tls_resumption.quanta:446` | `info` | F | explicitly freed - auto-free would double-push |
| `tls_resumption.quanta:485` | `psk` | S | written into a caller-owned out-param (mem_store/w64) |
| `tls_resumption.quanta:517` | `expected_binder` | F | explicitly freed - auto-free would double-push; inside a loop body (free would fire every iteration) |
| `tls_resumption.quanta:564` | `zero` | F | explicitly freed - auto-free would double-push |
| `tls_resumption.quanta:596` | `replay_cache` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `tls_resumption.quanta:635` | `hash` | S | written into a global-backed holder via mem_store/w64 |
| `tls_resumption.quanta:676` | `buf` | S | written into a caller-owned out-param (mem_store/w64) |
| `tokenizer_trait.quanta:217` | `VT_BUF` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `vec.quanta:44` | `h` | R | returned as the function's value |
| `x25519.quanta:136` | `p` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `x25519.quanta:225` | `t` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `x25519.quanta:255` | `base` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `x25519.quanta:256` | `tmp` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `x25519.quanta:257` | `result` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `x25519.quanta:286` | `k` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `x25519.quanta:297` | `x1` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `x25519.quanta:298` | `x2` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `x25519.quanta:299` | `z2` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `x25519.quanta:300` | `x3` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `x25519.quanta:301` | `z3` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `x25519.quanta:302` | `A24` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `x25519.quanta:305` | `t0` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `x25519.quanta:306` | `t1` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `x25519.quanta:307` | `t2` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `x25519.quanta:308` | `t3` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `x25519.quanta:309` | `t4` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `x509.quanta:57` | `cert` | R | returned as the function's value; explicitly freed - auto-free would double-push |
| `x509.quanta:95` | `serial_buf` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `x509.quanta:112` | `algo_oid_buf` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `x509.quanta:179` | `pk_algo_oid_buf` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `x509.quanta:188` | `pk_bits` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `x509.quanta:229` | `sig_bits` | F | explicitly freed - auto-free would double-push |
| `x509.quanta:355` | `san_buf` | S | written into a caller-owned out-param (mem_store/w64) |
| `x509.quanta:372` | `oid_buf` | F | explicitly freed - auto-free would double-push; inside a loop body (free would fire every iteration) |
| `x509.quanta:432` | `val_buf` | L | consumed locally; also stored into a same-scope block (safe under auto-free); inside a loop body (free would fire every iteration) |
| `x509.quanta:446` | `val_buf` | L | consumed locally; also stored into a same-scope block (safe under auto-free); inside a loop body (free would fire every iteration) |
| `x509.quanta:609` | `b64_buf` | F | explicitly freed - auto-free would double-push |
| `x509.quanta:618` | `der_buf` | S | written into a caller-owned out-param (mem_store/w64); explicitly freed - auto-free would double-push |

## 5. The rest of the corpus (counts; same analyser)

| corpus | sites | L | R | S | Pr | G | F | X | N/G-nop2/other |
|---|---|---|---|---|---|---|---|---|---|
| `test_suites/codes` (50 of 637 files) | 725 | 680 | 4 | 0 | 16 | 2 | 10 | 3 | 10 |
| `benchmarks` | 19 | 19 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `tests/` | 653 | 611 | 16 | 1 | 9 | 2 | 3 | 0 | 11 |
| **corpus total** | **1961** | **1495** | **64** | **52** | **40** | **10** | **119** | **3** | **178** |

Let-bound only (the P2 universe): **1780 sites — L 1495 (84 %), 285 escape-or-double-free.**
The `big` module (`big.quanta`) is the extreme case: every bignum VALUE is a `mem_alloc` block, and
`big_alloc`/`big_norm`/arithmetic return them — the return-escape is the language's value model, not
a coding accident.

## 6. The `mem_free`/`drop`/`free` audit (the aliasing hazard from the other side)

329 consuming call sites in `lib/std` (13 files with `mem_free`/`drop`, plus `free()` = munmap in 7
files). With the free-list encoding correct (0.0.243+), audited for double-free patterns:

F| site | var | class | rationale |
|---|---|---|---|
| `aes_gcm.quanta:13` | `res` | R | returned as the function's value |
| `aes_gcm.quanta:17` | `v` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `aes_gcm.quanta:68` | `tag` | R | returned as the function's value |
| `aes_gcm.quanta:76` | `block` | L | consumed locally (reader builtins, arithmetic, content stores); inside a loop body (free would fire every iteration) |
| `aes_gcm.quanta:105` | `block` | L | consumed locally (reader builtins, arithmetic, content stores); inside a loop body (free would fire every iteration) |
| `aes_gcm.quanta:131` | `len_block` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `aes_gcm.quanta:179` | `zero_block` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `aes_gcm.quanta:186` | `J0` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `aes_gcm.quanta:194` | `ctr` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `aes_gcm.quanta:241` | `zero_block` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `aes_gcm.quanta:247` | `J0` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `aes_gcm.quanta:258` | `expected_tag` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `aes_gcm.quanta:277` | `ctr` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `audit_log.quanta:65` | `log_ctx` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `audit_log.quanta:92` | `hash` | R | returned as the function's value; explicitly freed - auto-free would double-push |
| `audit_log.quanta:96` | `prefix` | F | explicitly freed - auto-free would double-push |
| `audit_log.quanta:120` | `hash` | R | returned as the function's value; explicitly freed - auto-free would double-push |
| `audit_log.quanta:124` | `prefix` | F | explicitly freed - auto-free would double-push |
| `audit_log.quanta:162` | `new_leaves` | S | written into a global-backed holder via mem_store/w64 |
| `audit_log.quanta:215` | `next_hashes` | L | consumed locally (reader builtins, arithmetic, content stores); inside a loop body (free would fire every iteration) |
| `audit_log.quanta:341` | `next_hashes` | L | consumed locally (reader builtins, arithmetic, content stores); inside a loop body (free would fire every iteration) |
| `audit_log.quanta:489` | `sig` | S | written into a caller-owned out-param (mem_store/w64); explicitly freed - auto-free would double-push |
| `audit_log.quanta:619` | `pkg` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `big.quanta:35` | `r` | R | returned as the function's value |
| `big.quanta:763` | `-` | ? | top-level let initialised by mem_alloc (module-load) |
| `big.quanta:783` | `buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `code_synthesizer.quanta:70` | `name_copy` | S | written into a global-backed holder via mem_store/w64 |
| `config.quanta:103` | `buf` | R | returned as the function's value |
| `config.quanta:237` | `val` | Pr | passed to config_expand, which retains that parameter; inside a loop body (free would fire every iteration) |
| `config.quanta:292` | `name` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `config.quanta:324` | `sec` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `config.quanta:332` | `kk` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `config.quanta:345` | `pre` | Pr | passed to config_expand, which retains that parameter |
| `config.quanta:353` | `suf` | Pr | passed to config_expand, which retains that parameter |
| `config.quanta:444` | `rev` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `config.quanta:456` | `o` | R | returned as the function's value |
| `crypto.quanta:109` | `H` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `crypto.quanta:119` | `w` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `crypto.quanta:172` | `out` | R | returned as the function's value |
| `crypto.quanta:233` | `kpad` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `crypto.quanta:245` | `inner` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `crypto.quanta:255` | `ibuf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `crypto.quanta:262` | `outer` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `crypto.quanta:271` | `obuf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `crypto.quanta:556` | `st` | R | returned as the function's value |
| `crypto.quanta:560` | `rk` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `ct.quanta:72` | `log_id` | F | explicitly freed - auto-free would double-push |
| `ct.quanta:126` | `signature` | F | explicitly freed - auto-free would double-push |
| `ct.quanta:138` | `sct` | R | returned as the function's value |
| `ct.quanta:168` | `scts` | S | written into a caller-owned out-param (mem_store/w64) |
| `ct.quanta:203` | `new_scts` | L | consumed locally (reader builtins, arithmetic, content stores); inside a loop body (free would fire every iteration) |
| `ct.quanta:307` | `current_hash` | F | explicitly freed - auto-free would double-push |
| `ct.quanta:320` | `combined` | F | explicitly freed - auto-free would double-push; inside a loop body (free would fire every iteration) |
| `cuda_daemon.quanta:72` | `tmp` | F | explicitly freed - auto-free would double-push |
| `cuda_daemon.quanta:96` | `tmp` | F | explicitly freed - auto-free would double-push |
| `cuda_daemon.quanta:178` | `buf` | F | explicitly freed - auto-free would double-push |
| `cuda_daemon.quanta:242` | `line` | F | explicitly freed - auto-free would double-push |
| `cuda_daemon.quanta:266` | `reply_buf` | R | returned as the function's value; explicitly freed - auto-free would double-push |
| `cuda_daemon.quanta:321` | `cmd` | F | explicitly freed - auto-free would double-push |
| `cuda_daemon.quanta:334` | `cmd` | F | explicitly freed - auto-free would double-push |
| `cuda_daemon.quanta:348` | `cmd` | F | explicitly freed - auto-free would double-push |
| `cuda_daemon.quanta:358` | `cmd` | F | explicitly freed - auto-free would double-push |
| `cuda_daemon.quanta:372` | `cmd` | F | explicitly freed - auto-free would double-push |
| `cuda_daemon.quanta:382` | `cmd` | F | explicitly freed - auto-free would double-push |
| `cuda_daemon.quanta:395` | `cmd` | F | explicitly freed - auto-free would double-push |
| `cuda_daemon.quanta:405` | `cmd` | F | explicitly freed - auto-free would double-push |
| `cuda_daemon.quanta:427` | `cmd` | F | explicitly freed - auto-free would double-push |
| `cuda_daemon.quanta:460` | `cmd` | F | explicitly freed - auto-free would double-push |
| `cuda_daemon.quanta:496` | `cuda_pool` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `cuda_daemon.quanta:587` | `cmd` | F | explicitly freed - auto-free would double-push |
| `cuda_daemon.quanta:609` | `cmd` | F | explicitly freed - auto-free would double-push |
| `cuda_daemon.quanta:635` | `cmd` | F | explicitly freed - auto-free would double-push |
| `cuda_daemon.quanta:654` | `cmd` | F | explicitly freed - auto-free would double-push |
| `cuda_subprocess.quanta:53` | `tmp` | F | explicitly freed - auto-free would double-push |
| `cuda_subprocess.quanta:78` | `tmp` | F | explicitly freed - auto-free would double-push |
| `cuda_subprocess.quanta:117` | `sh` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `cuda_subprocess.quanta:118` | `dash_c` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `cuda_subprocess.quanta:119` | `cmdbuf` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `cuda_subprocess.quanta:120` | `argv` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `cuda_subprocess.quanta:138` | `status` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `cuda_subprocess.quanta:152` | `buf` | R | returned as the function's value; explicitly freed - auto-free would double-push |
| `cuda_subprocess.quanta:187` | `cmd` | F | explicitly freed - auto-free would double-push |
| `cuda_subprocess.quanta:202` | `cmd` | F | explicitly freed - auto-free would double-push |
| `cuda_subprocess.quanta:218` | `cmd` | F | explicitly freed - auto-free would double-push |
| `cuda_subprocess.quanta:230` | `cmd` | F | explicitly freed - auto-free would double-push |
| `cuda_subprocess.quanta:246` | `cmd` | F | explicitly freed - auto-free would double-push |
| `cuda_subprocess.quanta:258` | `cmd` | F | explicitly freed - auto-free would double-push |
| `cuda_subprocess.quanta:272` | `cmd` | F | explicitly freed - auto-free would double-push |
| `cuda_subprocess.quanta:284` | `cmd` | F | explicitly freed - auto-free would double-push |
| `cuda_subprocess.quanta:305` | `cmd` | F | explicitly freed - auto-free would double-push |
| `fmt.quanta:9` | `buf` | F | explicitly freed - auto-free would double-push |
| `fs.quanta:13` | `cp` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `fs.quanta:27` | `buf` | R | returned as the function's value |
| `fs.quanta:56` | `cp` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `fs.quanta:66` | `cp` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `fs.quanta:76` | `cp` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `fs.quanta:86` | `cp` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `fs.quanta:96` | `co` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `fs.quanta:101` | `cn` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `fs.quanta:111` | `cp` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:226` | `klen_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:227` | `vtype_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:228` | `slen_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:238` | `gguf_kv_index` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `gguf.quanta:239` | `gguf_kv_arr_off` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `gguf.quanta:240` | `gguf_kv_arr_len` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `gguf.quanta:241` | `gguf_kv_etype` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `gguf.quanta:344` | `gguf_tensor_data` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `gguf.quanta:346` | `nlen_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:347` | `ndims_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:348` | `dim_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:349` | `dtype_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:350` | `off_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:351` | `name_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:355` | `gguf_tensor_dims` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `gguf.quanta:388` | `name_copy` | S | written into a global-backed holder via mem_store/w64; inside a loop body (free would fire every iteration) |
| `gguf.quanta:415` | `hdr` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:706` | `buf` | R | returned as the function's value |
| `gguf.quanta:926` | `lb` | L | consumed locally (reader builtins, arithmetic, content stores); inside a loop body (free would fire every iteration) |
| `gguf.quanta:929` | `kb` | L | consumed locally (reader builtins, arithmetic, content stores); inside a loop body (free would fire every iteration) |
| `gguf.quanta:950` | `lb` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:954` | `tb` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:963` | `lb` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:974` | `b` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:997` | `b` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:1023` | `lb` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:1026` | `buf` | R | returned as the function's value |
| `gguf.quanta:1040` | `lb` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:1118` | `lb` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:1137` | `lb` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:1148` | `buf` | R | returned as the function's value |
| `gguf.quanta:1178` | `lb` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:1209` | `lb` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:1380` | `raw` | F | explicitly freed - auto-free would double-push |
| `gguf.quanta:1386` | `raw` | F | explicitly freed - auto-free would double-push |
| `gguf.quanta:1392` | `raw` | F | explicitly freed - auto-free would double-push |
| `gguf.quanta:1398` | `raw` | F | explicitly freed - auto-free would double-push |
| `gguf.quanta:1404` | `raw` | F | explicitly freed - auto-free would double-push |
| `gguf.quanta:1410` | `raw` | F | explicitly freed - auto-free would double-push |
| `gguf.quanta:1416` | `raw` | F | explicitly freed - auto-free would double-push |
| `gguf.quanta:1422` | `raw` | F | explicitly freed - auto-free would double-push |
| `gguf.quanta:1428` | `raw` | F | explicitly freed - auto-free would double-push |
| `gguf.quanta:1434` | `raw` | F | explicitly freed - auto-free would double-push |
| `gguf.quanta:1445` | `raw` | F | explicitly freed - auto-free would double-push |
| `gguf.quanta:1456` | `raw` | F | explicitly freed - auto-free would double-push |
| `gguf.quanta:1467` | `raw` | F | explicitly freed - auto-free would double-push |
| `gguf.quanta:1478` | `raw` | F | explicitly freed - auto-free would double-push |
| `gguf.quanta:1489` | `raw` | F | explicitly freed - auto-free would double-push |
| `gguf.quanta:1500` | `raw` | F | explicitly freed - auto-free would double-push |
| `gguf.quanta:1544` | `raw` | F | explicitly freed - auto-free would double-push |
| `gguf.quanta:2128` | `scratch` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:2381` | `sb` | L | consumed locally (reader builtins, arithmetic, content stores); inside a loop body (free would fire every iteration) |
| `gguf.quanta:3141` | `tmp` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:3279` | `tmp` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:3324` | `tile_tmp` | L | consumed locally (reader builtins, arithmetic, content stores); inside a loop body (free would fire every iteration) |
| `gguf.quanta:3340` | `block` | L | consumed locally (reader builtins, arithmetic, content stores); inside a loop body (free would fire every iteration) |
| `gguf.quanta:3387` | `block` | L | consumed locally (reader builtins, arithmetic, content stores); inside a loop body (free would fire every iteration) |
| `gguf.quanta:3461` | `pl_tensor_idx` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `gguf.quanta:3462` | `pl_tensor_size` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `gguf.quanta:3463` | `pl_tensor_data` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `gguf.quanta:3464` | `pl_tensor_lru` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `gguf.quanta:3524` | `buf` | R | returned as the function's value; written into a global-backed holder via mem_store/w64; explicitly freed - auto-free would double-push |
| `gguf.quanta:3525` | `raw` | F | explicitly freed - auto-free would double-push |
| `gguf.quanta:3631` | `moe_slot_data` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `gguf.quanta:3632` | `moe_slot_ready` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `gguf.quanta:3633` | `moe_slot_done` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `gguf.quanta:3634` | `moe_slot_consumed` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `gguf.quanta:3847` | `b8` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:3848` | `b4` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:3902` | `buf` | R | returned as the function's value |
| `gguf.quanta:4057` | `ctx` | R | returned as the function's value |
| `gguf.quanta:4315` | `hdr` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:4350` | `buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:4368` | `lb` | L | consumed locally (reader builtins, arithmetic, content stores); inside a loop body (free would fire every iteration) |
| `gguf.quanta:4372` | `kb` | L | consumed locally (reader builtins, arithmetic, content stores); inside a loop body (free would fire every iteration) |
| `gguf.quanta:4394` | `lb` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:4403` | `klen_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:4404` | `vtype_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:4405` | `slen_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:4412` | `kv_index` | Pr | passed to gguf_ctx_set_kv_index, which retains that parameter |
| `gguf.quanta:4413` | `kv_arr_off` | Pr | passed to gguf_ctx_set_kv_arr_off, which retains that parameter |
| `gguf.quanta:4414` | `kv_arr_len` | Pr | passed to gguf_ctx_set_kv_arr_len, which retains that parameter |
| `gguf.quanta:4415` | `kv_etype` | Pr | passed to gguf_ctx_set_kv_etype, which retains that parameter |
| `gguf.quanta:4499` | `tdata` | Pr | passed to gguf_ctx_set_tensor_data, which retains that parameter |
| `gguf.quanta:4502` | `tdims` | Pr | passed to gguf_ctx_set_tensor_dims, which retains that parameter |
| `gguf.quanta:4505` | `nlen_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:4506` | `ndims_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:4507` | `dim_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:4508` | `dtype_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:4509` | `off_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:4510` | `name_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf.quanta:4547` | `name_copy` | L | consumed locally; also stored into a same-scope block (safe under auto-free); inside a loop body (free would fire every iteration) |
| `gguf.quanta:4649` | `buf` | R | returned as the function's value |
| `gguf_ctx.quanta:27` | `ctx` | R | returned as the function's value |
| `gguf_ctx.quanta:285` | `hdr` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf_ctx.quanta:320` | `buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf_ctx.quanta:338` | `lb` | L | consumed locally (reader builtins, arithmetic, content stores); inside a loop body (free would fire every iteration) |
| `gguf_ctx.quanta:342` | `kb` | L | consumed locally (reader builtins, arithmetic, content stores); inside a loop body (free would fire every iteration) |
| `gguf_ctx.quanta:364` | `lb` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf_ctx.quanta:373` | `klen_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf_ctx.quanta:374` | `vtype_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf_ctx.quanta:375` | `slen_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf_ctx.quanta:382` | `kv_index` | Pr | passed to gguf_ctx_set_kv_index, which retains that parameter |
| `gguf_ctx.quanta:383` | `kv_arr_off` | Pr | passed to gguf_ctx_set_kv_arr_off, which retains that parameter |
| `gguf_ctx.quanta:384` | `kv_arr_len` | Pr | passed to gguf_ctx_set_kv_arr_len, which retains that parameter |
| `gguf_ctx.quanta:385` | `kv_etype` | Pr | passed to gguf_ctx_set_kv_etype, which retains that parameter |
| `gguf_ctx.quanta:469` | `tdata` | Pr | passed to gguf_ctx_set_tensor_data, which retains that parameter |
| `gguf_ctx.quanta:472` | `tdims` | Pr | passed to gguf_ctx_set_tensor_dims, which retains that parameter |
| `gguf_ctx.quanta:475` | `nlen_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf_ctx.quanta:476` | `ndims_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf_ctx.quanta:477` | `dim_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf_ctx.quanta:478` | `dtype_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf_ctx.quanta:479` | `off_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf_ctx.quanta:480` | `name_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `gguf_ctx.quanta:517` | `name_copy` | L | consumed locally; also stored into a same-scope block (safe under auto-free); inside a loop body (free would fire every iteration) |
| `gguf_ctx.quanta:619` | `buf` | R | returned as the function's value |
| `hsm.quanta:368` | `pkcs11_slots` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `hsm.quanta:426` | `pkcs11_sessions` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `hsm.quanta:719` | `pubkey` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `hsm.quanta:720` | `privkey` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `hsm.quanta:726` | `pub_obj` | S | written into a caller-owned out-param (mem_store/w64) |
| `hsm.quanta:734` | `priv_obj` | S | written into a caller-owned out-param (mem_store/w64) |
| `hsm.quanta:748` | `pubkey` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `hsm.quanta:749` | `privkey` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `hsm.quanta:754` | `pub_obj` | S | written into a caller-owned out-param (mem_store/w64) |
| `hsm.quanta:761` | `priv_obj` | S | written into a caller-owned out-param (mem_store/w64) |
| `hsm.quanta:775` | `pubkey` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `hsm.quanta:776` | `privkey` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `hsm.quanta:791` | `pub_obj` | S | written into a caller-owned out-param (mem_store/w64) |
| `hsm.quanta:798` | `priv_obj` | S | written into a caller-owned out-param (mem_store/w64) |
| `hsm.quanta:920` | `tpm_handles` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `hsm.quanta:1015` | `enclave_report` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `hsm.quanta:1023` | `enclave_report` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `hsm.quanta:1032` | `report` | S | written into a caller-owned out-param (mem_store/w64) |
| `hsm.quanta:1053` | `report` | S | written into a caller-owned out-param (mem_store/w64) |
| `hsm.quanta:1072` | `quote` | S | written into a caller-owned out-param (mem_store/w64) |
| `hsm.quanta:1169` | `attestation` | S | written into a caller-owned out-param (mem_store/w64) |
| `hsm.quanta:1176` | `quote` | S | written into a caller-owned out-param (mem_store/w64) |
| `hsm.quanta:1183` | `report` | S | written into a caller-owned out-param (mem_store/w64) |
| `hsm.quanta:1232` | `-` | N | inline call, no binding |
| `json.quanta:83` | `out` | R | returned as the function's value |
| `json.quanta:250` | `v` | R | returned as the function's value |
| `json.quanta:259` | `v` | R | returned as the function's value |
| `json.quanta:269` | `v` | R | returned as the function's value |
| `json.quanta:280` | `v` | R | returned as the function's value |
| `json.quanta:289` | `v` | R | returned as the function's value |
| `json.quanta:303` | `v` | R | returned as the function's value; inside a loop body (free would fire every iteration) |
| `json.quanta:318` | `v` | R | returned as the function's value; inside a loop body (free would fire every iteration) |
| `json.quanta:335` | `v` | R | returned as the function's value; inside a loop body (free would fire every iteration) |
| `json.quanta:359` | `v` | R | returned as the function's value; inside a loop body (free would fire every iteration) |
| `key_derivation.quanta:14` | `ipad` | F | explicitly freed - auto-free would double-push |
| `key_derivation.quanta:15` | `opad` | F | explicitly freed - auto-free would double-push |
| `key_derivation.quanta:29` | `inner` | F | explicitly freed - auto-free would double-push |
| `key_derivation.quanta:55` | `u` | F | explicitly freed - auto-free would double-push |
| `key_derivation.quanta:56` | `f` | F | explicitly freed - auto-free would double-push |
| `key_derivation.quanta:57` | `block_salt` | F | explicitly freed - auto-free would double-push |
| `key_derivation.quanta:125` | `zero_salt` | F | explicitly freed - auto-free would double-push |
| `key_derivation.quanta:146` | `t` | F | explicitly freed - auto-free would double-push |
| `key_derivation.quanta:164` | `ipad` | F | explicitly freed - auto-free would double-push; inside a loop body (free would fire every iteration) |
| `key_derivation.quanta:165` | `opad` | F | explicitly freed - auto-free would double-push; inside a loop body (free would fire every iteration) |
| `key_derivation.quanta:217` | `prk` | F | explicitly freed - auto-free would double-push |
| `key_derivation.quanta:300` | `v` | F | explicitly freed - auto-free would double-push |
| `key_derivation.quanta:301` | `xy` | F | explicitly freed - auto-free would double-push |
| `key_derivation.quanta:302` | `b` | F | explicitly freed - auto-free would double-push |
| `key_derivation.quanta:306` | `pbkdf2_out` | F | explicitly freed - auto-free would double-push |
| `key_derivation.quanta:384` | `memory` | F | explicitly freed - auto-free would double-push |
| `key_derivation.quanta:388` | `h0` | F | explicitly freed - auto-free would double-push |
| `key_derivation.quanta:536` | `keystore_ctx` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `key_derivation.quanta:562` | `keystore_path` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `key_derivation.quanta:603` | `salt` | S | written into a global-backed holder via mem_store/w64; explicitly freed - auto-free would double-push |
| `key_derivation.quanta:607` | `nonce` | S | written into a global-backed holder via mem_store/w64; explicitly freed - auto-free would double-push |
| `key_derivation.quanta:611` | `master_key` | G | assigned to a module global; explicitly freed - auto-free would double-push |
| `key_derivation.quanta:639` | `keystore_entries` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `key_derivation.quanta:651` | `entries_data` | F | explicitly freed - auto-free would double-push |
| `key_derivation.quanta:667` | `encrypted` | F | explicitly freed - auto-free would double-push |
| `key_derivation.quanta:668` | `tag` | F | explicitly freed - auto-free would double-push |
| `key_derivation.quanta:687` | `tag_ptr` | S | written into a global-backed holder via mem_store/w64; explicitly freed - auto-free would double-push |
| `key_derivation.quanta:776` | `master_key` | G | assigned to a module global; explicitly freed - auto-free would double-push |
| `key_derivation.quanta:793` | `encrypted` | F | explicitly freed - auto-free would double-push |
| `key_derivation.quanta:808` | `entries_data` | F | explicitly freed - auto-free would double-push |
| `key_derivation.quanta:814` | `tag` | F | explicitly freed - auto-free would double-push |
| `key_derivation.quanta:832` | `keystore_entries` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `key_derivation.quanta:864` | `new_entries` | G | assigned to a module global |
| `key_derivation.quanta:1006` | `new_key` | L | consumed locally; also stored into a same-scope block (safe under auto-free); inside a loop body (free would fire every iteration) |
| `key_derivation.quanta:1067` | `entry` | F | explicitly freed - auto-free would double-push |
| `key_derivation.quanta:1078` | `entry` | F | explicitly freed - auto-free would double-push |
| `kv_cache.quanta:14` | `kv_k_ptr` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `kv_cache.quanta:15` | `kv_v_ptr` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_bpe.quanta:111` | `key` | G | assigned to a module global |
| `lfm2_bpe.quanta:112` | `val` | G | assigned to a module global |
| `lfm2_bpe.quanta:176` | `ml_buf` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_bpe.quanta:248` | `bpe_vocab` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_bpe.quanta:250` | `bpe_merges` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_bpe.quanta:272` | `bpe_byte_id` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_bpe.quanta:273` | `tmp` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `lfm2_bpe.quanta:319` | `bpe_sym_off` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_bpe.quanta:320` | `bpe_sym_cap_arr` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_bpe.quanta:414` | `bl` | L | consumed locally (reader builtins, arithmetic, content stores); inside a loop body (free would fire every iteration) |
| `lfm2_bpe.quanta:596` | `cell` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `lfm2_bpe.quanta:606` | `bpe_special_ids` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_bpe.quanta:607` | `bpe_special_len` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_bpe.quanta:608` | `bpe_special_ptr` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_bpe.quanta:670` | `idcell` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `lfm2_bpe.quanta:686` | `bl` | L | consumed locally (reader builtins, arithmetic, content stores); inside a loop body (free would fire every iteration) |
| `lfm2_forward.quanta:94` | `fc_nkv` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:107` | `cell` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `lfm2_forward.quanta:211` | `fc_sc_ip` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:212` | `fc_sc_bx` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:213` | `fc_sc_kw` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:214` | `fc_sc_g` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:215` | `fc_sc_k` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:216` | `fc_sc_y` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:385` | `fc_kvbuf` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:436` | `fc_cos` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:437` | `fc_sin` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:567` | `fc_at_qn` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:568` | `fc_at_kn` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:571` | `fc_at_q` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:572` | `fc_at_k` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:573` | `fc_at_v` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:574` | `fc_at_h` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:584` | `fc_at_sc` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:585` | `fc_at_out` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:790` | `fc_fw_x` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:791` | `fc_fw_n` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:792` | `fc_fw_a` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:793` | `fc_fw_ff` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:794` | `fc_fw_f` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:795` | `fc_fw_logits` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:799` | `fc_fw_conv` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:833` | `fc_fw_normbuf` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:876` | `fc_ffn_f_gate` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:877` | `fc_ffn_f_up` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:1085` | `fc_pf_src` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:1086` | `fc_pf_dst` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:1087` | `fc_pf_r` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:1088` | `fc_pf_n` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:1089` | `fc_pf_a` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:1090` | `fc_pf_o` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:1091` | `fc_pf_g` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:1092` | `fc_pf_u` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:1093` | `fc_pf_f` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:1094` | `fc_pf_q` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:1095` | `fc_pf_k` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:1096` | `fc_pf_v` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:1097` | `fc_pf_bcx` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:1098` | `fc_pf_sc` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:1099` | `fc_pf_h` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:1100` | `fc_pf_qn` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:1101` | `fc_pf_kn` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:1102` | `fc_pf_sg` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:1103` | `fc_pf_sk` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:1104` | `fc_pf_sbx` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:1105` | `fc_pf_skw` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_forward.quanta:1360` | `fc_fw_normbuf` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_mm.quanta:47` | `mm_rowbuf` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_mm.quanta:50` | `mm_rowraw` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_mm.quanta:132` | `mm_blk_raw` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_mm.quanta:134` | `mm_blk_f64` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_mm.quanta:324` | `mask` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `lfm2_mm.quanta:341` | `buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `lfm2_mm.quanta:369` | `buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `lfm2_mm.quanta:769` | `raw` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `lfm2_mm.quanta:770` | `f64b` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `lfm2_mm.quanta:772` | `acc` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `lfm2_mm.quanta:773` | `cell` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `lfm2_mm.quanta:824` | `mm_dot_acc` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_mm.quanta:825` | `mm_dot_tmp` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_mm.quanta:1193` | `pl_genp` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_mm.quanta:1194` | `pl_stopp` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_mm.quanta:1195` | `pl_donep` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_mm.quanta:1196` | `pl_slots` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `lfm2_model.quanta:129` | `LFM2_SLOTS` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `linalg.quanta:19` | `p` | R | returned as the function's value |
| `linalg.quanta:192` | `buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `linalg.quanta:244` | `aug` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `loader_traits.quanta:46` | `qmodel_ctx_table` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `loader_traits.quanta:114` | `buf` | N | plain reassignment, not let-bound |
| `loader_traits.quanta:124` | `buf` | N | plain reassignment, not let-bound |
| `loader_traits.quanta:138` | `b` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `map.quanta:75` | `map_last_chunk` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `map.quanta:92` | `map_chunk_tab` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `math.quanta:268` | `b` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `matmul_q4k.quanta:131` | `w` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `ml_kem.quanta:16` | `u64` | N | plain reassignment, not let-bound; inside a loop body (free would fire every iteration) |
| `ml_kem.quanta:24` | `u64` | N | plain reassignment, not let-bound; inside a loop body (free would fire every iteration) |
| `ml_kem.quanta:116` | `u64` | N | plain reassignment, not let-bound; inside a loop body (free would fire every iteration) |
| `ml_kem.quanta:124` | `u64` | N | plain reassignment, not let-bound; inside a loop body (free would fire every iteration) |
| `ml_kem.quanta:143` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:151` | `u64` | N | plain reassignment, not let-bound; inside a loop body (free would fire every iteration) |
| `ml_kem.quanta:229` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:230` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:234` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:238` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:239` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:254` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:291` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:309` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:317` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:322` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:325` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:326` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:327` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:342` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:345` | `u64` | N | plain reassignment, not let-bound; inside a loop body (free would fire every iteration) |
| `ml_kem.quanta:353` | `u64` | N | plain reassignment, not let-bound; inside a loop body (free would fire every iteration) |
| `ml_kem.quanta:367` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:376` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:389` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:391` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:393` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:416` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:422` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:435` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:437` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:441` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:443` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem.quanta:468` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem_constants.quanta:102` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem_constants.quanta:119` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem_constants.quanta:139` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem_constants.quanta:146` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem_constants.quanta:187` | `u64` | N | plain reassignment, not let-bound |
| `ml_kem_constants.quanta:194` | `u64` | N | plain reassignment, not let-bound |
| `mmap_access.quanta:18` | `mmap_ptr` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `ocsp.quanta:156` | `req` | S | written into a caller-owned out-param (mem_store/w64) |
| `ocsp.quanta:179` | `certids` | S | written into a caller-owned out-param (mem_store/w64) |
| `ocsp.quanta:207` | `algo_oid_buf` | L | consumed locally (reader builtins, arithmetic, content stores); inside a loop body (free would fire every iteration) |
| `ocsp.quanta:216` | `issuer_hash` | L | consumed locally; also stored into a same-scope block (safe under auto-free); inside a loop body (free would fire every iteration) |
| `ocsp.quanta:221` | `issuer_key_hash` | L | consumed locally; also stored into a same-scope block (safe under auto-free); inside a loop body (free would fire every iteration) |
| `ocsp.quanta:226` | `serial` | L | consumed locally; also stored into a same-scope block (safe under auto-free); inside a loop body (free would fire every iteration) |
| `ocsp.quanta:230` | `certid` | L | consumed locally; also stored into a same-scope block (safe under auto-free); inside a loop body (free would fire every iteration) |
| `ocsp.quanta:289` | `resp` | S | written into a caller-owned out-param (mem_store/w64) |
| `ocsp.quanta:317` | `oid_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `ocsp.quanta:378` | `key_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `ocsp.quanta:418` | `sig_buf` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `ocsp.quanta:437` | `resp` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `ocsp.quanta:452` | `ocsp_resp` | S | written into a caller-owned out-param (mem_store/w64) |
| `ocsp.quanta:505` | `resps` | S | written into a caller-owned out-param (mem_store/w64) |
| `ocsp.quanta:559` | `single` | L | consumed locally; also stored into a same-scope block (safe under auto-free); inside a loop body (free would fire every iteration) |
| `ocsp.quanta:681` | `ocsp_cache` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `pattern_library.quanta:38` | `name_copy` | S | written into a global-backed holder via mem_store/w64 |
| `patterns.quanta:37` | `name_copy` | S | written into a global-backed holder via mem_store/w64 |
| `qmodel_cache.quanta:67` | `qmc_table` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `qmodel_cache.quanta:68` | `qmc_budget` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `qmodel_cache.quanta:69` | `qmc_used` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `qmodel_cache.quanta:70` | `qmc_ntensors` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `qmodel_cache.quanta:71` | `qmc_stat` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `quantum.quanta:149` | `st` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `quantum.quanta:212` | `out` | R | returned as the function's value |
| `quantum.quanta:218` | `out` | R | returned as the function's value |
| `quantum.quanta:224` | `out` | R | returned as the function's value |
| `quantum.quanta:230` | `out` | R | returned as the function's value |
| `rag.quanta:94` | `b` | R | returned as the function's value |
| `safetensors.quanta:104` | `lb` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `safetensors.quanta:117` | `buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `safetensors.quanta:431` | `tmp` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `safetensors.quanta:438` | `tmp` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `safetensors.quanta:504` | `ctx` | R | returned as the function's value |
| `safetensors.quanta:575` | `lb` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `safetensors.quanta:581` | `buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `safetensors.quanta:820` | `tmp` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `safetensors.quanta:826` | `tmp` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `sha3_hash.quanta:57` | `st` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `sidechannel.quanta:125` | `ptr` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `sidechannel.quanta:309` | `r` | F | explicitly freed - auto-free would double-push |
| `sidechannel.quanta:411` | `sk_mask` | F | explicitly freed - auto-free would double-push |
| `sidechannel.quanta:412` | `sk_share` | F | explicitly freed - auto-free would double-push |
| `sidechannel.quanta:417` | `tmp_sk` | F | explicitly freed - auto-free would double-push |
| `sidechannel.quanta:437` | `r_mask` | F | explicitly freed - auto-free would double-push |
| `sidechannel.quanta:457` | `sk` | F | explicitly freed - auto-free would double-push |
| `sidechannel.quanta:550` | `sk` | F | explicitly freed - auto-free would double-push |
| `sidechannel.quanta:606` | `sk` | F | explicitly freed - auto-free would double-push |
| `sidechannel.quanta:618` | `sk` | F | explicitly freed - auto-free would double-push |
| `sidechannel.quanta:741` | `timing_samples` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `sp_tokenizer.quanta:20` | `stat_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `sp_tokenizer.quanta:25` | `raw` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `sp_tokenizer.quanta:36` | `sp_vocab_ptr` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `spec_to_ir.quanta:100` | `ir` | R | returned as the function's value |
| `spiffe.quanta:113` | `td_buf` | S | written into a caller-owned out-param (mem_store/w64); explicitly freed - auto-free would double-push |
| `spiffe.quanta:123` | `path_buf` | S | written into a caller-owned out-param (mem_store/w64) |
| `spiffe.quanta:145` | `id` | S | written into a caller-owned out-param (mem_store/w64) |
| `spiffe.quanta:215` | `id_copy` | S | written into a caller-owned out-param (mem_store/w64); inside a loop body (free would fire every iteration) |
| `spiffe.quanta:351` | `id_copy` | S | written into a caller-owned out-param (mem_store/w64); inside a loop body (free would fire every iteration) |
| `spiffe.quanta:454` | `svid` | S | written into a caller-owned out-param (mem_store/w64) |
| `spiffe.quanta:470` | `svid` | S | written into a caller-owned out-param (mem_store/w64) |
| `spiffe.quanta:527` | `td` | S | written into a caller-owned out-param (mem_store/w64); explicitly freed - auto-free would double-push |
| `spiffe.quanta:530` | `name_copy` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `spiffe.quanta:570` | `bundle` | S | written into a caller-owned out-param (mem_store/w64); explicitly freed - auto-free would double-push |
| `spiffe.quanta:573` | `td_copy` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `spiffe.quanta:609` | `fed` | S | written into a caller-owned out-param (mem_store/w64); explicitly freed - auto-free would double-push |
| `spiffe.quanta:612` | `td_copy` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `spiffe.quanta:644` | `workload` | S | written into a caller-owned out-param (mem_store/w64); explicitly freed - auto-free would double-push |
| `spiffe.quanta:647` | `id_copy` | F | explicitly freed - auto-free would double-push |
| `spiffe.quanta:659` | `sel_copy` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `spiffe.quanta:772` | `ctx` | G | assigned to a module global; written into a caller-owned out-param (mem_store/w64); explicitly freed - auto-free would double-push |
| `spiffe.quanta:775` | `id_copy` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `st_ctx.quanta:16` | `-` | R-inline | inline `return mem_alloc(...)` |
| `st_ctx.quanta:82` | `lb` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `st_ctx.quanta:88` | `buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `st_ctx.quanta:327` | `tmp` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `st_ctx.quanta:333` | `tmp` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `str.quanta:39` | `buf` | R | returned as the function's value |
| `str.quanta:109` | `num_buf` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `supply_chain.quanta:43` | `sc_ctx` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `supply_chain.quanta:47` | `policies` | S | written into a global-backed holder via mem_store/w64 |
| `supply_chain.quanta:54` | `cache` | S | written into a global-backed holder via mem_store/w64 |
| `supply_chain.quanta:79` | `new_policies` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `supply_chain.quanta:113` | `results` | S | written into a caller-owned out-param (mem_store/w64) |
| `supply_chain.quanta:323` | `ctx` | F | explicitly freed - auto-free would double-push |
| `tls_resumption.quanta:63` | `key` | S | written into a caller-owned out-param (mem_store/w64); explicitly freed - auto-free would double-push |
| `tls_resumption.quanta:67` | `name` | S | written into a caller-owned out-param (mem_store/w64) |
| `tls_resumption.quanta:83` | `ticket_keys` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `tls_resumption.quanta:154` | `tag` | F | explicitly freed - auto-free would double-push |
| `tls_resumption.quanta:158` | `aad` | F | explicitly freed - auto-free would double-push |
| `tls_resumption.quanta:183` | `aad` | F | explicitly freed - auto-free would double-push |
| `tls_resumption.quanta:213` | `iv` | F | explicitly freed - auto-free would double-push |
| `tls_resumption.quanta:218` | `ciphertext` | F | explicitly freed - auto-free would double-push |
| `tls_resumption.quanta:224` | `tag` | F | explicitly freed - auto-free would double-push |
| `tls_resumption.quanta:231` | `aad` | F | explicitly freed - auto-free would double-push |
| `tls_resumption.quanta:270` | `ticket` | S | written into a caller-owned out-param (mem_store/w64) |
| `tls_resumption.quanta:324` | `parsed` | S | written into a caller-owned out-param (mem_store/w64); explicitly freed - auto-free would double-push |
| `tls_resumption.quanta:361` | `ciphertext` | F | explicitly freed - auto-free would double-push |
| `tls_resumption.quanta:363` | `tag` | F | explicitly freed - auto-free would double-push |
| `tls_resumption.quanta:380` | `plaintext` | S | written into a caller-owned out-param (mem_store/w64); explicitly freed - auto-free would double-push |
| `tls_resumption.quanta:387` | `aad` | F | explicitly freed - auto-free would double-push |
| `tls_resumption.quanta:446` | `info` | F | explicitly freed - auto-free would double-push |
| `tls_resumption.quanta:485` | `psk` | S | written into a caller-owned out-param (mem_store/w64) |
| `tls_resumption.quanta:517` | `expected_binder` | F | explicitly freed - auto-free would double-push; inside a loop body (free would fire every iteration) |
| `tls_resumption.quanta:564` | `zero` | F | explicitly freed - auto-free would double-push |
| `tls_resumption.quanta:596` | `replay_cache` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `tls_resumption.quanta:635` | `hash` | S | written into a global-backed holder via mem_store/w64 |
| `tls_resumption.quanta:676` | `buf` | S | written into a caller-owned out-param (mem_store/w64) |
| `tokenizer_trait.quanta:217` | `VT_BUF` | G-nop2 | reassigned into a module global (not let-bound; P2 never owns it) |
| `vec.quanta:44` | `h` | R | returned as the function's value |
| `x25519.quanta:136` | `p` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `x25519.quanta:225` | `t` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `x25519.quanta:255` | `base` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `x25519.quanta:256` | `tmp` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `x25519.quanta:257` | `result` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `x25519.quanta:286` | `k` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `x25519.quanta:297` | `x1` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `x25519.quanta:298` | `x2` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `x25519.quanta:299` | `z2` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `x25519.quanta:300` | `x3` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `x25519.quanta:301` | `z3` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `x25519.quanta:302` | `A24` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `x25519.quanta:305` | `t0` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `x25519.quanta:306` | `t1` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `x25519.quanta:307` | `t2` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `x25519.quanta:308` | `t3` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `x25519.quanta:309` | `t4` | L | consumed locally (reader builtins, arithmetic, content stores) |
| `x509.quanta:57` | `cert` | R | returned as the function's value; explicitly freed - auto-free would double-push |
| `x509.quanta:95` | `serial_buf` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `x509.quanta:112` | `algo_oid_buf` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `x509.quanta:179` | `pk_algo_oid_buf` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `x509.quanta:188` | `pk_bits` | L | consumed locally; also stored into a same-scope block (safe under auto-free) |
| `x509.quanta:229` | `sig_bits` | F | explicitly freed - auto-free would double-push |
| `x509.quanta:355` | `san_buf` | S | written into a caller-owned out-param (mem_store/w64) |
| `x509.quanta:372` | `oid_buf` | F | explicitly freed - auto-free would double-push; inside a loop body (free would fire every iteration) |
| `x509.quanta:432` | `val_buf` | L | consumed locally; also stored into a same-scope block (safe under auto-free); inside a loop body (free would fire every iteration) |
| `x509.quanta:446` | `val_buf` | L | consumed locally; also stored into a same-scope block (safe under auto-free); inside a loop body (free would fire every iteration) |
| `x509.quanta:609` | `b64_buf` | F | explicitly freed - auto-free would double-push |
| `x509.quanta:618` | `der_buf` | S | written into a caller-owned out-param (mem_store/w64); explicitly freed - auto-free would double-push |

* **0 same-path double-frees and 0 use-after-frees found in `lib/std` today.** The earlier raw
  MULTI-FREE/UAF hits dissolved under path analysis: they were exclusive error paths
  (`mem_free(log_id); return 0` seven times in `ct.quanta`) and re-binding between frees
  (`level_hashes = next_hashes` in `audit_log.quanta`). The free discipline in the 13 files is
  clean; the deferred-reuse-free design (alloc ignores the list) has been masking every latent
  aliasing bug.
* **199 of the 329 sites free a let-bound `mem_alloc` binding of the same function.** Every one of
  them becomes a double free-list push under the 0.0.242 auto-free (explicit push + scope-exit
  push). This is the same aliasing hazard A5 warned about (`codegen.quanta:2741`), from the other
  side. 97 of the 199 are the multi-error-path shape; the rest are single frees.
* **23 sites free a PARAMETER** (callee-frees contract, e.g. `spiffe`/`ocsp` destructors). Under
  auto-free these need the *caller's* ownership cancelled too — the retention machinery with the
  opposite sign.
* **`free()` (munmap) sites: 11, e.g. `fmt.quanta:13` `free(buf)`** — the canonical 0.0.242 §5c
  casualty. Under auto-free: the block is unmapped, then the scope-exit push writes `[p+8]` and
  `HEAP_CTRL` **in unmapped memory** — SIGSEGV or silent corruption of whatever mmap'd there next.

## 7. Recommendation

**Implement the bounded interprocedural escape analysis; do not ship a simple rule; do not keep it
parked.** The evidence:

1. **A simple escape rule is unsound.** "Escapes iff it appears in a `return` or is assigned to a
   global" covers only R+G = 50 of the 115 let-bound `lib/std` escapes. Missed: 41 out-param stores
   (`w64(svid_out, svid)` — the SPIFFE/TLS/HSM out-param idiom), 12 global-backed-holder stores, 15
   retainer passes. Every missed class lives in load-bearing modules (gguf loader, config, keystore,
   mTLS). Shipping 0.0.242 as-is broke 26 gate rows (WIP §5b) — those rows are these classes.
2. **The flow-sensitive gap is bounded and now enumerated.** For `lib/std`: 6 retainer functions
   carry all 15 Pr sites (`config_expand` + 5 `gguf_ctx_set_*`), one builtin family carries all 51
   S sites, and explicit-free cancellation carries all 106 F sites plus the 23 PARAM frees. The
   analyser beside this report implements the whole check in ~600 lines of Python at 2.6 s/corpus;
   the compiler-side version works on IR it already has (IR_CALL name spans, IR_STOREG, param
   tables).
3. **Parking is no longer justified.** Today: 100 % of blocks leak to process exit, the free-list
   machinery is dead code, and the deferred-reuse design masks the 199+23 sites' aliasing semantics.
   The blocker A5 named ("escape/alias detection does not exist") is now specified to the site.
4. **Shape of the shipping rule** (what the analysis must prove before marking owned): the binding
   is owned iff its block (a) is never the direct value of a `return` (arg-passes to readers are
   fine — the 0.0.242 return-ordering fix), (b) is never written into a holder whose lifetime
   outlives the scope (param holders, global cells, global-backed structs), (c) is never passed at
   a retaining parameter position of any callee (fixpoint summaries), (d) is never explicitly
   freed — locally or by a callee (free cancels ownership), and (e) — the 13 loop-body sites —
   either satisfies (a)-(d) per iteration or is not owned. Failing any, the binding falls back to
   today's leak (safe), never to a free.
5. **Do NOT add `tests/raii_autofree_test.quanta` to EXPECTED.tsv yet** (unchanged from 0.0.242 §6):
   it stays red-first until this analysis lands.

## 8. Not verified / limits

* The classification is static and path-insensitive at statement granularity; every non-L/N
  `lib/std` site was verified by reading, but the 1495 L sites were verified by spot-reading
  (`fs`, `aes_gcm`, `gguf`, `lfm2_bpe` shapes), not one-by-one. A wrong L verdict hides an escape
  the same way the old detector hid the free.
* Cross-module global assignment is assumed impossible (per-file global namespaces); if a program
  assigns another module's global, that store is not counted.
* The 1 top-level site (`big.quanta:763 let _putc_buf = mem_alloc(1)`) — whether the P2 detector
  even reaches top-level `let`s is unverified; it is excluded from the let-bound counts.
* Multi-line `return` expressions (call closing on a later line) are classified as arg-pass, the
  conservative direction for R but not for Pr; no such site was found in `lib/std`.
* The retention fixpoint is name-based; a function that retains a param only under a runtime
  condition is still marked retaining (conservative), and one that returns a masked pointer
  arithmetic (`& 0xffffffff`) is detected as a cast only for the single-param exact shape (exactly
  `u32` in this corpus).
* No timing was measured or quoted; the box stayed CPU-light (analysis peak ~2.6 s single-core).

*A-number: A22 (next free after A21; the stale "see A21/A22" forward-reference at bugs.md line 647
points at the same fc_attn_workers decision that became A21).*
