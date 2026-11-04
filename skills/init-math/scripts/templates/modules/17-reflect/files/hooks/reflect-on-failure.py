"""Notice failed research commands and suggest a reflection pass when one keeps failing.

Registered after every shell command (PostToolUse; on Claude Code also PostToolUseFailure,
which is how Claude Code reports a non-zero exit: its PostToolUse payload has no exit code). It acts only on RESEARCH commands: those whose program
is listed in project.toml `[stack] research_commands`. With that list empty the hook does
nothing at all.

A research command counts as failed when it exits non-zero (Claude Code: a
PostToolUseFailure event; Codex: the exit code in the PostToolUse payload; deliberate
interrupts such as Ctrl-C are ignored) or when its output matches one of `[[stack.failure_signatures]]` even
though it exited 0. Each failure is appended to logs/failures.jsonl as
{signature, command, excerpt}. The first failure of a signature is silent; the 2nd, 4th,
8th, ..., 1024th unreviewed failure of the same signature, and then every 1000th (2024th,
3024th, ...), nudges the agent to run a reflection pass at its next stopping point. "Unreviewed" = not yet marked by `bin/journal
--mark-reviewed`, so the count starts again after each pass.

Bypass: HOOKS_QUIET=1. Failure policy: fails open, loudly (hooks/_payload.py).
See docs/discipline/reflection-loop.md.
"""
import hashlib
import json
import os
import re
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _payload  # noqa: E402

HOOK = "reflect-on-failure"
# Interrupts the agent or the owner caused on purpose: SIGINT, SIGTERM, SIGHUP, SIGQUIT.
DELIBERATE_EXITS = {129, 130, 131, 143}
WRAPPERS = {"bash", "sh", "zsh", "nohup", "time", "timeout", "gtimeout", "env", "nice",
            "stdbuf", "xargs", "exec", "command"}
SEGMENT = re.compile(r"&&|\|\||;|\n|\|")


def load_stack(root: str) -> tuple[list[str], list[tuple[str, re.Pattern]]]:
    p = Path(root) / "project.toml"
    if not p.exists():
        return [], []
    with open(p, "rb") as f:
        stack = tomllib.load(f).get("stack", {})
    cmds = [str(c) for c in stack.get("research_commands", []) if str(c).strip()]
    sigs = [(str(s.get("label", "signature")), re.compile(s["regex"]))
            for s in stack.get("failure_signatures", []) if s.get("regex")]
    return cmds, sigs


def programs(command: str) -> list[str]:
    """The real program of each pipeline segment, looking through env assignments,
    `cd`, and wrapper prefixes (nohup, timeout 60, env, ...)."""
    out = []
    for seg in SEGMENT.split(command):
        toks = seg.strip().split()
        i = 0
        while i < len(toks):
            t = toks[i]
            if re.match(r"^\w+=", t):
                i += 1
            elif t == "cd":
                break
            elif os.path.basename(t) in WRAPPERS:
                i += 1
                while i < len(toks) and (toks[i].startswith("-") or re.match(r"^\d+[smhd]?$", toks[i])):
                    i += 1
            else:
                out.append(t)
                break
    return out


def is_research(command: str, research: list[str]) -> str:
    for prog in programs(command):
        for r in research:
            if prog == r or os.path.basename(prog) == os.path.basename(r):
                return os.path.basename(r)
    return ""


def output_and_exit(raw: dict) -> tuple[str, int | None]:
    """Pull the command's output text and exit code out of either harness's payload."""
    texts: list[str] = []
    code = None
    resp = raw.get("tool_response", raw.get("tool_output", raw.get("output")))
    if isinstance(resp, str) and resp.lstrip().startswith("{"):
        try:
            resp = json.loads(resp)
        except ValueError:
            pass
    for src in (resp, raw):
        if not isinstance(src, dict):
            continue
        for k in ("stdout", "stderr", "output", "text", "content", "aggregated_output",
                  "formatted_output", "error"):
            v = src.get(k)
            if isinstance(v, str) and v:
                texts.append(v)
        for k in ("exit_code", "exitCode", "returncode", "status"):
            v = src.get(k)
            if isinstance(v, int) and not isinstance(v, bool) and code is None:
                code = v
    if isinstance(resp, str):
        texts.append(resp)
    text = "\n".join(texts)
    if code is None:
        m = re.search(r"^Exit code:? (\d+)", text, re.M)
        if m:
            code = int(m.group(1))
    return text, code


def unreviewed_count(root: str, signature: str) -> int:
    """How many unreviewed rows of logs/failures.jsonl carry `signature`.
    Reviewed rows are listed by bin/journal in logs/state/journal-failures.reviewed,
    identified by sha256(stripped line)[:16]."""
    logf = Path(root) / "logs" / "failures.jsonl"
    if not logf.exists():
        return 0
    rev = Path(root) / "logs" / "state" / "journal-failures.reviewed"
    reviewed = set(rev.read_text().split()) if rev.exists() else set()
    n = 0
    for line in logf.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        # No de-duplication: a merge duplicate may count twice, which only advances the nudge.
        if hashlib.sha256(line.strip().encode("utf-8")).hexdigest()[:16] in reviewed:
            continue
        try:
            if json.loads(line).get("signature") == signature:
                n += 1
        except (ValueError, AttributeError):
            continue
    return n


DOUBLING_CAP = 1024  # nudge at 2, 4, 8, ..., 1024; after that every STEP_AFTER_CAP failures
STEP_AFTER_CAP = 1000


def nudge_due(n: int) -> bool:
    """True at the 2nd, 4th, 8th, ..., 1024th unreviewed failure, then the 2024th, 3024th, ..."""
    if n <= DOUBLING_CAP:
        return n >= 2 and n & (n - 1) == 0
    return (n - DOUBLING_CAP) % STEP_AFTER_CAP == 0

def main(ev):
    if os.environ.get("HOOKS_QUIET") == "1" or ev.action != "shell":
        return
    research, sigs = load_stack(ev.root)
    if not research:
        return  # inert: no research commands configured
    prog = is_research(ev.command, research)
    if not prog:
        return
    text, code = output_and_exit(ev.raw)
    resp = ev.raw.get("tool_response")
    if (code in DELIBERATE_EXITS or ev.raw.get("is_interrupt") is True
            or (isinstance(resp, dict) and resp.get("interrupted") is True)):
        return
    if ev.event == "PostToolUseFailure":
        failed_exit = True
    elif ev.harness == "claude":
        # Claude Code's PostToolUse carries no exit code (a non-zero exit arrives as a separate
        # PostToolUseFailure), so here only an output signature counts; an "Exit code" string
        # in ordinary output must not be read as one.
        failed_exit = False
    else:
        failed_exit = code is not None and code != 0
    match = next(((label, pat) for label, pat in sigs if pat.search(text)), None)
    if not match and not failed_exit:
        return
    if match:
        signature = match[0]
        excerpt = next((l.strip() for l in text.splitlines() if match[1].search(l)), "")
    else:
        signature = f"{prog}-exit-nonzero"
        excerpt = next((l.strip() for l in reversed(text.splitlines()) if l.strip()), "")
    first_line = ev.command.strip().splitlines()[0] if ev.command.strip() else ""
    # `id` keeps identical failures in the same second distinct (rows are reviewed by content).
    _payload.log(ev.root, "failures", {"signature": signature, "command": first_line[:200],
                                       "excerpt": excerpt[:200], "id": os.urandom(4).hex()})
    n = unreviewed_count(ev.root, signature)
    if nudge_due(n):
        _payload.log(ev.root, "nudges", {"hook": HOOK, "key": signature})
        _payload.block(
            f"[{HOOK}] '{signature}' has failed {n} times since the last reflection pass "
            f"(logs/failures.jsonl). A repeated failure usually has a cause worth fixing once. "
            f"Finish the step you are on; at the next natural stopping point run the reflect "
            f"skill (or log what you already know with the friction skill). "
            f"See docs/discipline/reflection-loop.md. This is information, not a refusal: "
            f"the command already ran.")


if __name__ == "__main__":
    _payload.run(main, HOOK)
