"""guard: refuse a few destructive or gate-bypassing shell commands before they run.

Event: PreToolUse, action `shell`. Three kinds of response (docs/discipline/guard.md):

HARD BLOCK (the owner may lift it by starting the agent with GUARD_OFF=1 in its environment;
a `GUARD_OFF=1` written inside the command itself does nothing):
  - recursive rm in any spelling (-r, -R, -rf, -fr, --recursive, `find -exec rm -r`);
  - `find ... -delete`;
  - a download piped or handed to a shell (`curl x | sh`, `sh -c "$(curl x)"`, `bash <(curl x)`);
  - a force push or a delete push to a main branch (project.toml [guard] main_branches);
  - under zsh only, commands that are certain to fail there: an unquoted word starting with
    `=` after echo/printf, and assignment to the read-only `status` / `pipestatus`.

HARD BLOCK, NEEDS THE OWNER (same GUARD_OFF lift): a step only a human should take.
  - `sudo` / `doas` anywhere in the command (after `env`, `xargs`, `timeout`, in a pipeline,
    inside `sh -c`, run by `find -exec`), except a lookup such as `command -v sudo`;
  - `chmod` that grants write permission to everyone: a numeric mode whose last digit has the
    write bit (777, 0777, 666, 1777, 772, ...) or a symbolic `o+w` / `a+w` / `o=rw` / `ugo+rwx`
    clause, recursive or not. `chmod +w` with no `who` is allowed (the umask keeps `o` out).
  The refusal tells the agent not to retry or work around it, but to write the owner
  step-by-step instructions for only the steps the owner must perform, with what each one
  changes, its risk and how to undo it, and then to carry on with whatever does not need them.

NEVER LIFTED, and logged to logs/feedback.jsonl as a bypass attempt:
  - setting GATE_OK (an owner-only override for commit checks) in the command;
  - `git ... --no-verify`, `git commit -n`, `git -c core.hooksPath=...`.
  Those bypasses belong to the owner, who runs such a command themselves.

NUDGE (once per distinct command; re-issuing proceeds; switch off in project.toml [guard]):
  - `git add -A` / `--all` / `.` (stages whatever else is lying around);
  - in-place `sed -i` / `perl -i` on .md / .tex / .txt (silent encoding damage; breaks the
    harness's record of which files it has read);
  - under zsh, an unquoted `$VAR` passed to git add / git commit / rm (zsh does not split it).

The command is parsed into simple commands (quotes, operators, heredocs, `sh -c` scripts,
`eval`, wrappers like sudo/env/xargs/timeout), so a commit message that mentions `rm -rf`
is not mistaken for one. It is a guardrail against natural spellings, not a sandbox:
deliberate obfuscation can pass. Fails open loudly on an internal error.
"""
from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _payload  # noqa: E402

HOOK = "guard"

# --- parser ------------------------------------------------------------------------------

_OPERATOR_CHARS = frozenset("\n;|&()<>")
_OPERATORS = ("&>>", "&&", "||", ";;", "|&", ">>", "<<", "<&", ">&", "&>", ">|",
              "\n", ";", "|", "&", "(", ")", "<", ">")
_REDIRECTS = frozenset({">", ">>", "<", "<<", "<&", ">&", "&>", "&>>", ">|"})
_HEREDOC_RE = re.compile(r"<<-?[ \t]*(?P<q>['\"]?)(?P<d>[A-Za-z_][A-Za-z0-9_]*)(?P=q)")
_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_WRAPPERS = frozenset({
    "sudo", "doas", "env", "nohup", "setsid", "time", "timeout", "gtimeout", "nice",
    "ionice", "xargs", "command", "exec", "builtin", "stdbuf", "chroot",
    "{", "!", "if", "then", "else", "elif", "do", "while", "until",
})
_TRACKED = frozenset({"rm", "find", "git", "curl", "wget", "chmod"})
_SHELLS = frozenset({"sh", "bash", "zsh", "ksh", "dash", "fish"})
_SCRIPT_RUNNERS = _SHELLS | {"source", "."}
_SUBST_RUNNERS = _SHELLS | {"eval"}
_FIND_EXEC = frozenset({"-exec", "-execdir", "-ok", "-okdir"})
_SUBST_FETCH_RE = re.compile(r"(?:\$\(|`)\s*=?(?:\S*/)?(?:curl|wget)\b")
_IFS_RE = re.compile(r"\$\{IFS\}|\$IFS\b")
_PIPE_INTO = frozenset({"|", "|&", "&&", ";"})
_SHELL_ON_LINE_RE = re.compile(r"\b(?:" + "|".join(sorted(_SHELLS)) + r")\b")
_MAX_DEPTH = 4


class _LexError(Exception):
    pass


def _strip_heredocs(cmd: str) -> tuple[str, list[str]]:
    """Remove heredoc bodies; return those a shell will execute (`bash <<EOF`)."""
    lines = cmd.split("\n")
    out: list[str] = []
    scripts: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        delims = [m.group("d") for m in _HEREDOC_RE.finditer(line)]
        executed = bool(delims) and _SHELL_ON_LINE_RE.search(line) is not None
        i += 1
        for delim in delims:
            start = i
            while i < len(lines) and lines[i].strip() != delim:
                i += 1
            if executed:
                scripts.append("\n".join(lines[start:i]))
            i += 1
    return "\n".join(out), scripts


def _lex(cmd: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    word: list[str] = []
    started = [False]

    def flush():
        if started[0]:
            tokens.append(("word", "".join(word)))
            word.clear()
            started[0] = False

    i, n = 0, len(cmd)
    while i < n:
        c = cmd[i]
        if c in " \t\r":
            flush()
            i += 1
        elif c == "'":
            j = cmd.find("'", i + 1)
            if j < 0:
                raise _LexError("unbalanced single quote")
            word.append(cmd[i + 1:j])
            started[0] = True
            i = j + 1
        elif c == '"':
            j, buf = i + 1, []
            while j < n and cmd[j] != '"':
                if cmd[j] == "\\" and j + 1 < n and cmd[j + 1] in '\\"$`\n':
                    if cmd[j + 1] != "\n":
                        buf.append(cmd[j + 1])
                    j += 2
                else:
                    buf.append(cmd[j])
                    j += 1
            if j >= n:
                raise _LexError("unbalanced double quote")
            word.append("".join(buf))
            started[0] = True
            i = j + 1
        elif c == "\\" and i + 1 < n:
            if cmd[i + 1] != "\n":
                word.append(cmd[i + 1])
                started[0] = True
            i += 2
        elif c in _OPERATOR_CHARS:
            flush()
            for op in _OPERATORS:
                if cmd.startswith(op, i):
                    tokens.append(("op", op))
                    i += len(op)
                    break
        else:
            word.append(c)
            started[0] = True
            i += 1
    flush()
    return tokens


def _simple_commands(tokens) -> list[tuple[list[str], str]]:
    """Group tokens into (words, terminator) simple commands."""
    cmds: list[tuple[list[str], str]] = []
    words: list[str] = []
    redirected = [False]

    def flush(term):
        if words or redirected[0]:
            cmds.append((list(words), term))
        words.clear()
        redirected[0] = False

    i = 0
    while i < len(tokens):
        kind, val = tokens[i]
        if kind == "word":
            words.append(val)
        elif val in _REDIRECTS:
            if i + 1 < len(tokens) and tokens[i + 1][0] == "word":
                i += 1
            redirected[0] = True
        else:
            flush(val)
        i += 1
    flush("")
    return cmds


def _lex_commands(text: str):
    try:
        return _simple_commands(_lex(text))
    except _LexError:  # broken quoting: degrade, but stay command-position
        return _simple_commands(_lex(re.sub(r"['\"]", " ", text)))


def _basename(word: str) -> str:
    # zsh expands a leading `=` in command position to the command's path.
    return word.replace("\\", "/").rsplit("/", 1)[-1].lstrip("=")


def _invocations(words: list[str]) -> list[tuple[str, list[str]]]:
    """(name, args) for a simple command and any command it wraps (sudo rm, xargs rm)."""
    out: list[tuple[str, list[str]]] = []
    i = 0
    while i < len(words) and _ASSIGN_RE.match(words[i]):
        i += 1
    while i < len(words) and len(out) < 4:
        out.append((words[i], words[i + 1:]))
        if _basename(words[i]) not in _WRAPPERS:
            break
        nxt = None
        for j in range(i + 1, len(words)):
            b = _basename(words[j])
            if b in _TRACKED or b in _WRAPPERS or b in _SHELLS:
                nxt = j
                break
        if nxt is None:
            break
        i = nxt
    return out


def _inline_scripts(cmds) -> list[str]:
    out: list[str] = []
    for words, _t in cmds:
        for name, args in _invocations(words):
            b = _basename(name)
            if b == "eval":
                out.append(" ".join(args))
            elif b in _SHELLS:
                for k, a in enumerate(args[:-1]):
                    if a.startswith("-") and not a.startswith("--") and "c" in a[1:]:
                        out.append(args[k + 1])
                        break
    return out


def parse(cmd: str) -> list[tuple[list[str], str]]:
    """Simple commands, including those in a shell-fed heredoc and in `sh -c` / eval scripts."""
    cmds: list[tuple[list[str], str]] = []
    pending = [_IFS_RE.sub(" ", cmd)]
    for _ in range(_MAX_DEPTH):
        if not pending:
            break
        nxt: list[str] = []
        for text in pending:
            stripped, scripts = _strip_heredocs(text)
            lexed = _lex_commands(stripped)
            cmds.extend(lexed)
            nxt.extend(scripts)
            nxt.extend(_inline_scripts(lexed))
        pending = nxt
    return cmds


def raw_command(ev: _payload.Event) -> str:
    """The command as the shell will see it. Codex may send a list (argv); `sh -c SCRIPT`
    is unwrapped to SCRIPT, anything else is re-quoted with shlex.join."""
    ti = ev.raw.get("tool_input") or {}
    cmd = ti.get("command", "") if isinstance(ti, dict) else ti
    if isinstance(cmd, list):
        parts = [str(x) for x in cmd]
        if (len(parts) >= 3 and _basename(parts[0]) in _SHELLS
                and parts[1] in ("-c", "-lc", "-ic")):
            return parts[2]
        return shlex.join(parts)
    return str(cmd or "")


# --- configuration -----------------------------------------------------------------------

_DEFAULTS = {"main_branches": ["main", "master"], "nudge_git_add_all": True,
             "nudge_inplace_docs": True}


def config(root: str) -> dict:
    cfg = dict(_DEFAULTS)
    try:
        import tomllib
        with open(Path(root) / "project.toml", "rb") as f:
            sect = tomllib.load(f).get("guard") or {}
        for k in cfg:
            if k in sect:
                cfg[k] = sect[k]
    except FileNotFoundError:  # no project.toml: defaults
        pass
    except Exception as e:  # broken project.toml: keep guarding with the defaults, but say so
        print(f"WARNING: [{HOOK}] cannot read [guard] from project.toml ({e}); using defaults.",
              file=sys.stderr)
    return cfg


# --- checks ------------------------------------------------------------------------------

def _is_recursive_rm(name: str, args: list[str]) -> bool:
    if _basename(name) != "rm":
        return False
    for a in args:
        if a == "--":
            break
        if a.startswith("--recursive"):
            return True
        if a.startswith("-") and not a.startswith("--") and ("r" in a or "R" in a):
            return True
    return False


def _git_parts(args: list[str]) -> tuple[list[str], str, list[str]]:
    """Split `git` args into (global options, subcommand, subcommand args)."""
    glob: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-c", "-C", "--git-dir", "--work-tree", "--namespace") and i + 1 < len(args):
            glob += [a, args[i + 1]]
            i += 2
        elif a.startswith("-"):
            glob.append(a)
            i += 1
        else:
            return glob, a, args[i + 1:]
    return glob, "", []


def _current_branch(cwd: str) -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd or None,
                           capture_output=True, text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _push_to_main(sub_args: list[str], mains: list[str], cwd: str) -> str | None:
    force = False
    delete = False
    positional: list[str] = []
    for a in sub_args:
        if a in ("--force", "--mirror") or a.startswith("--force-"):
            force = True
        elif a in ("-d", "--delete"):
            delete = True
        elif a.startswith("-") and not a.startswith("--"):
            if "f" in a[1:]:
                force = True
            if "d" in a[1:]:
                delete = True
        elif not a.startswith("-"):
            positional.append(a)
    refspecs = positional[1:]
    targets: list[str] = []
    for spec in refspecs:
        if spec.startswith("+"):
            force = True
            spec = spec[1:]
        if spec.startswith(":"):
            delete = True
        dst = spec.split(":", 1)[-1]
        targets.append(dst.removeprefix("refs/heads/"))
    if not refspecs and (force or delete):
        targets.append(_current_branch(cwd))
    if not (force or delete):
        return None
    hit = [t for t in targets if t in mains]
    if hit:
        what = "delete" if delete else "force push"
        return f"a {what} to the main branch `{hit[0]}`"
    return None


def hard_block(cmds, invs, cfg: dict, cwd: str) -> str | None:
    for _idx, name, args in invs:
        if _is_recursive_rm(name, args):
            return "recursive rm (rm -r / -R / -rf / --recursive, in any spelling)"
        if _basename(name) == "find":
            for k, a in enumerate(args[:-1]):
                if a in _FIND_EXEC and _is_recursive_rm(args[k + 1], args[k + 2:]):
                    return "recursive rm run by find -exec"
            if "-delete" in args:
                return "find ... -delete"
    for idx, name, _args in invs:
        if _basename(name) not in ("curl", "wget") or cmds[idx][1] not in _PIPE_INTO:
            continue
        if idx + 1 >= len(cmds):
            continue
        last = idx + 1
        if cmds[idx][1] in ("|", "|&"):  # follow the whole pipeline: curl x | base64 -d | sh
            while cmds[last][1] in ("|", "|&") and last + 1 < len(cmds):
                last += 1
        for j in range(idx + 1, last + 1):
            if any(_basename(n) in _SHELLS for n, _ in _invocations(cmds[j][0])):
                return "a download piped or chained into a shell"
    for idx, name, args in invs:
        if _basename(name) in _SUBST_RUNNERS and any(_SUBST_FETCH_RE.search(a) for a in args):
            return "a download handed to a shell by command substitution"
        if _basename(name) in ("curl", "wget") and idx > 0 and cmds[idx - 1][1] == "(":
            if any(_basename(n) in _SCRIPT_RUNNERS for n, _ in _invocations(cmds[idx - 1][0])):
                return "a download handed to a shell by process substitution"
    for _idx, name, args in invs:
        if _basename(name) == "git":
            _g, sub, sargs = _git_parts(args)
            if sub == "push":
                hit = _push_to_main(sargs, list(cfg["main_branches"]), cwd)
                if hit:
                    return hit
    return None


_PRIVILEGED = frozenset({"sudo", "doas"})
_OCTAL_RE = re.compile(r"^[0-7]{1,4}$")
_SYMBOLIC_RE = re.compile(r"^([ugoa]*)((?:[-+=][rwxXstugo]*)+)$")


def _grants_world_write(mode: str) -> bool:
    """True if a chmod MODE gives write permission to `other` (everyone)."""
    if _OCTAL_RE.match(mode):
        return bool(int(mode[-1]) & 2)
    for clause in mode.split(","):
        m = _SYMBOLIC_RE.match(clause)
        if not m:
            continue
        who, ops = m.group(1), m.group(2)
        if not who or not ("o" in who or "a" in who):
            continue  # no `who`: the umask keeps `o` out, as for `chmod +w`
        for op in re.findall(r"[-+=][rwxXstugo]*", ops):
            if op[0] in "+=" and "w" in op[1:]:
                return True
    return False


def _is_world_write_chmod(name: str, args: list[str]) -> bool:
    if _basename(name) != "chmod":
        return False
    after_dashdash = False
    for a in args:
        if not after_dashdash and a == "--":
            after_dashdash = True
            continue
        if not after_dashdash and a.startswith("-"):
            if a.startswith("--reference"):
                return False  # the mode comes from a file, not the command line
            continue  # an option, or a mode like -w that only removes permissions
        return _grants_world_write(a)  # the first operand is the mode
    return False


def _is_privileged(name: str, args: list[str]) -> bool:
    return _basename(name) in _PRIVILEGED


def _is_lookup(words: list[str]) -> bool:
    """`command -v sudo` / `command -V sudo` names sudo without running it."""
    i = 0
    while i < len(words) and _ASSIGN_RE.match(words[i]):
        i += 1
    rest = words[i:]
    return len(rest) >= 2 and _basename(rest[0]) == "command" and rest[1] in ("-v", "-V")


def owner_only(cmds, invs) -> str | None:
    """A step only a human should take: privilege escalation or a world-writable chmod."""
    for idx, name, args in invs:
        found: list[tuple[str, list[str]]] = [(name, args)]
        if _basename(name) == "find":
            for k, a in enumerate(args[:-1]):
                if a in _FIND_EXEC:
                    found.extend(_invocations(args[k + 1:]))
        for n, a in found:
            if _is_privileged(n, a) and not _is_lookup(cmds[idx][0]):
                return f"`{_basename(n)}` (running a command with administrator rights)"
            if _is_world_write_chmod(n, a):
                return "a `chmod` that makes files writable by every user on the machine"
    return None


_GATE_SETTERS = frozenset({"export", "env", "declare", "typeset", "local", "readonly"})
_GATE_RE = re.compile(r"^GATE_OK=(.*)$")


def _gate_value_set(word: str) -> bool:
    m = _GATE_RE.match(word)
    return bool(m) and m.group(1) not in ("", "0")


def bypass_attempt(cmds, invs) -> str | None:
    for words, _t in cmds:
        i = 0
        while i < len(words) and _ASSIGN_RE.match(words[i]):
            if _gate_value_set(words[i]):
                return "sets GATE_OK, an owner-only override for commit checks"
            i += 1
    for _idx, name, args in invs:
        b = _basename(name)
        if b in _GATE_SETTERS and any(_gate_value_set(a) for a in args):
            return "sets GATE_OK, an owner-only override for commit checks"
        if b != "git":
            continue
        g, sub, sargs = _git_parts(args)
        if "--no-verify" in args:
            return "passes --no-verify to git (skips the repository's hooks)"
        if any(a.startswith("core.hooksPath") or a.startswith("core.hookspath")
               for k, a in enumerate(g) if k > 0 and g[k - 1] == "-c"):
            return "overrides core.hooksPath (skips the repository's hooks)"
        if sub == "commit":
            for a in sargs:
                if a == "--":
                    break
                if a.startswith("-") and not a.startswith("--"):
                    letters = a[1:]
                    # stop at a letter that takes the rest as its value (-mfoo, -Fmsg)
                    for ch in letters:
                        if ch == "n":
                            return "passes -n (no-verify) to git commit"
                        if ch in "mFCctu":
                            break
    return None


_INPLACE_RE = re.compile(r"^-[A-Za-z0-9]*i")
_DOC_RE = re.compile(r"\.(?:md|tex|txt)$")


def nudge_reason(invs, cfg: dict) -> str | None:
    for _idx, name, args in invs:
        b = _basename(name)
        if b == "git" and cfg.get("nudge_git_add_all", True):
            _g, sub, sargs = _git_parts(args)
            if sub == "add" and any(a in ("-A", "--all", ".", ":/") for a in sargs):
                return ("`git add -A` / `--all` / `.` stages everything in the tree, including "
                        "files another session or a scratch run left behind. Stage the exact "
                        "paths, and commit with an explicit pathspec: `git commit -- <paths>`.")
        if b in ("sed", "perl") and cfg.get("nudge_inplace_docs", True):
            if any(_INPLACE_RE.match(a) for a in args) and any(_DOC_RE.search(a) for a in args):
                return ("an in-place `sed -i` / `perl -i` on a .md/.tex/.txt file. These can "
                        "silently damage UTF-8 (math symbols), and an out-of-band write breaks the "
                        "harness's record of which files it has read. Use the file-editing tool "
                        "instead.")
    return None


_ZSH_EQUALS = re.compile(r"(?:^|[;&|(){}]|\bdo\b|\bthen\b)\s*(?:echo|printf)\b[^;&|\n'\"]*?\s=")
_ZSH_READONLY = re.compile(r"(?:^|[;&|(){}]|\bdo\b|\bthen\b)\s*(?:status|pipestatus)=")
_ZSH_UNSPLIT = re.compile(r"(?:^|[;&|(){}])\s*(?:git\s+(?:add|commit)|rm)\b[^;&|\n]*"
                          r"\s\$(?:\{[A-Za-z_]\w*\}|[A-Za-z_]\w*)(?=\s|$)")


def _code_only(cmd: str) -> str:
    """Blank quoted spans and heredoc bodies, so regexes see only code."""
    stripped, _ = _strip_heredocs(cmd)
    return re.sub(r"'[^']*'|\"(?:\\.|[^\"\\])*\"", "''", stripped)


def zsh_block(cmd: str) -> str | None:
    code = _code_only(cmd)
    if _ZSH_EQUALS.search(code):
        return ("an unquoted word starting with `=` after echo/printf. zsh expands `=word` to the "
                "path of a command named `word`, so this fails ('not found') and aborts the whole "
                "call. Quote it, e.g. `echo '===='`.")
    if _ZSH_READONLY.search(code):
        return ("an assignment to `status` or `pipestatus`, which are read-only in zsh, so this "
                "fails. Use another name, e.g. `rc=`.")
    return None


def zsh_nudge(cmd: str) -> str | None:
    if _ZSH_UNSPLIT.search(_code_only(cmd)):
        return ("an unquoted `$VAR` passed to git add / git commit / rm. zsh does NOT split an "
                "unquoted variable into words, so a list of paths arrives as one path. List the "
                "paths explicitly (or use a zsh array).")
    return None


def _is_zsh() -> bool:
    return os.environ.get("SHELL", "").rsplit("/", 1)[-1] == "zsh"


# --- main --------------------------------------------------------------------------------

def main(ev: _payload.Event) -> None:
    if ev.action != "shell":
        return
    cmd = raw_command(ev)
    if not cmd.strip():
        return
    cmds = parse(cmd)
    invs = [(idx, name, args) for idx, (words, _t) in enumerate(cmds)
            for name, args in _invocations(words)]

    bypass = bypass_attempt(cmds, invs)
    if bypass:
        _payload.log(ev.root, "feedback", {"kind": "bypass", "source": "agent",
                                            "text": f"guard refused: {bypass}: {cmd[:300]}"})
        _payload.block(
            f"[{HOOK}] Refused: this command {bypass}. Skipping a gate or the repository's hooks "
            "is the owner's call, not an agent's: run the command without it, or tell the owner "
            "what you need and let them run it themselves. Logged to logs/feedback.jsonl. "
            "See docs/discipline/guard.md.")

    cfg = config(ev.root)
    lifted = os.environ.get("GUARD_OFF") == "1"
    if not lifted:
        hit = hard_block(cmds, invs, cfg, ev.cwd)
        if hit:
            _payload.block(
                f"[{HOOK}] Refused: {hit}. Use a narrower command (delete named files; write "
                "scratch output into a fresh timestamped directory so nothing needs cleaning up; "
                "push without force). If the owner wants this done, they can run it themselves "
                "or restart the agent with GUARD_OFF=1. See docs/discipline/guard.md.")
        hit = owner_only(cmds, invs)
        if hit:
            _payload.block(
                f"[{HOOK}] Refused: {hit}. That step needs the owner, not an agent. Do NOT "
                "retry it, rephrase it, or find another route to the same effect. Instead, write "
                "the owner short step-by-step instructions covering ONLY the steps they must "
                "perform themselves (the exact commands), and for each step what it changes, "
                "the risk, and how to undo it, plus anything they should check before running "
                "it. Then continue with whatever does not depend on those steps. "
                "See docs/discipline/guard.md.")
        if _is_zsh():
            hit = zsh_block(cmd)
            if hit:
                _payload.block(f"[{HOOK}] Refused (certain to fail under zsh): {hit}")

    reason = nudge_reason(invs, cfg)
    if reason is None and _is_zsh():
        reason = zsh_nudge(cmd)
    if reason:
        _payload.nudge_once(ev, HOOK, cmd, reason + " See docs/discipline/guard.md.")


if __name__ == "__main__":
    _payload.run(main, HOOK)
