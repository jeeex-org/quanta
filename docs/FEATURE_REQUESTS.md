# Feature Requests (post-stdlib)

Tracked hardening/feature work that is **NOT in the 0.0.43–0.50 core-debt window**
and is **deferred to after stdlib (1.0)**. These are defense-in-depth on top of
already-working features, not correctness blockers.

---

## FR-001: `$$(cmd)` command approval system

**Status:** Deferred to post-stdlib. Core `$$(cmd)` is functional and gated
behind `unsafe{}` (commit `0f133eb`, gate GREEN 91/91 + 8/8 + 3/3).

**Motivation:** `$$(cmd)` runs an external command via `/bin/sh -c`. Today any
command is allowed once inside `unsafe{}`. We want a default-deny posture for
destructive commands and an allowlist for common safe ones, while still
permitting interactive commands (ssh, vi, …) with direct terminal access.

### Requirements

1. **Allowlist (default-permitted)** — compile-time embedded list, e.g.:
   `ls`, `cat`, `echo`, `pwd`, `date`, `whoami`, `uname`, `head`, `tail`,
   `wc`, `grep`, `sed`, `awk`, `sort`, `uniq`, `cut`, `tr`, `find` (read-only
   subset), `readlink`, `file`, `stat`, `env` (read).

2. **Denylist (default-denied)** — destructive commands NOT allowed unless
   explicitly granted: `rm`, `fdisk`, `mkfs`, `dd`, `shutdown`, `reboot`,
   `mkfs.*`, `parted`, `chmod` (recursive), `chown` (recursive), `mv` (over
   existing), `cp -r` over existing, `truncate`, `> file` overwrite (handled
   at shell level, best-effort), `sudo`, `su`, `mount`, `umount`, `kill`,
   `killall`, `pkill`, `iptables`, `sysctl`.

3. **Grant mechanism** — runtime opt-in via environment variable, read once at
   program start:
   ```
   QUANTA_ALLOW_CMD="rm,dd,fdisk"
   ```
   Grants the named commands even if on the denylist. Parsed from a
   comma-separated list; each entry matched against the command's first token.

4. **Interactive command support** — commands that need a real TTY must NOT be
   piped. Detected by first-token prefix match against an interactive set:
   `ssh`, `vi`, `vim`, `nano`, `less`, `more`, `top`, `htop`, `emacs`,
   `screen`, `tmux`, `man`, `info`, `watch`, `tail -f`. For these:
   - Child inherits stdio directly (no `dup2` to the capture pipe).
   - Parent does NOT read from the pipe and does NOT wait for output capture;
     it waits for the child to exit (`wait4`) so the interactive session runs
     to completion on the real terminal.
   - `CmdResult.out` / `.err` are empty for interactive commands (no capture).

5. **Rejection behavior** — if a denied command is used without grant:
   - Compile-time: if the cmd is a **string literal** and matches a denylist
     entry, emit a **compile error** (clear message naming the command and
     how to grant via `QUANTA_ALLOW_CMD`).
   - Runtime: if the cmd is a **string variable / dynamic**, the check happens
     at `$$(cmd)` call time — set `code = 127` (or a dedicated sentinel like
     `code = -1`) and `.err = "denied: <cmd> (grant via QUANTA_ALLOW_CMD)"`.
     Never exec a denied command.

6. **`$$` is the only substitution sigil.** There is NO `$${...}`. Cmd argument
   must be a string literal or string variable (non-string not handled — see
   FR-002).

### Design notes / pitfalls (from 2026-08-19 attempt)

- **Do NOT bolt this into `emit_bltn` (emitter.quanta) inline.** The first
  attempt added label/vreg juggling (`is_interactive`, `nl()`-based jump
  tables) directly in the `qc_sys_cmd` builtin. It made the SEED (0.0.53)
  compiler fail to bootstrap (`boot=7`) — the 0.0.55 compiler couldn't compile
  its own complex label logic. The compiler is not yet mature enough for that
  style.
- **Better design:** a dedicated IR pass or a small `cmd_approval` module that
  resolves the allowlist/denylist at compile time for literals and emits a
  thin runtime check only for dynamic cmds. Keep the builtin emitter simple.
- **Interactive detection** must happen BEFORE `fork()`, with the boolean
  result carried into the child (not re-derived in the child via a second
  label maze). Store the flag in a vreg, test it once in the child.
- **Env var parsing** (`get_granted_cmds`) needs a proper string-split helper
  in the compiler's runtime — was stubbed but not wired (the attempt referenced
  `populate_cmd_lists()` / `init_keywords` patterns that weren't completed).

### Acceptance criteria (for the future PR)

- [ ] `$$(“rm -rf /”)` → compile error (literal, denylisted).
- [ ] `QUANTA_ALLOW_CMD=rm ./prog` with `$$(“rm file”)` → runs, code 0.
- [ ] `$$(“ls”)` → allowed by default, out captured, code 0.
- [ ] `$$(“ssh host”)` → interactive: runs on real terminal, out/err empty.
- [ ] `let c = “rm x”; $$(c)` → runtime denied: code sentinel, err message,
      NO exec.
- [ ] Full gate stays GREEN (no bootstrap regression like `boot=7`).
- [ ] Self-hosting fixed point preserved (committed bin/x86/qc → source → qc, byte-identical; and 2nd-stage rebuild).

---

## FR-002: non-string `$$(cmd)` argument

**Status:** Deferred.

Currently `$$(cmd)` requires `cmd` to be a `string` literal or `string`
variable. A non-string (e.g. `$$(42)`, `$$(some_int)`) is a type error /
miscompile territory.

**Requirement:** if `cmd` is a non-string scalar, implicitly convert it to its
decimal string representation before passing to `/bin/sh -c` (i.e.
`$$(42)` ≡ `$$(“42”)`). Keep `string`-only as the documented constraint
otherwise.

---

## FR-003: `CmdResult.err` should capture stderr

**Status:** Deferred.

`o.err` currently returns a valid empty string `""` (stderr is not captured).
For parity with `o.out`, capture the child's stderr (a second pipe, like the
stdout pipe) into `o.err`. Buffer also capped at 4096B.

---

*Added 2026-08-19. Deferred to post-stdlib (1.0+). Core `$$(cmd)` work
(5 bug fixes) shipped in `0f133eb`.*
