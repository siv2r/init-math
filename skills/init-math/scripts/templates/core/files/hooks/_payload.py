"""Shared runtime for this project's hooks (stdlib only).

Every hook is one Python script that works under any supported harness. The harness
passes a JSON payload on stdin; the registration adds `--harness claude|codex`.
`read_event()` normalizes it into an Event:

    event       PreToolUse | PostToolUse | PostToolUseFailure | Stop | SessionStart |
                SubagentStop | SubagentStart (Codex) | SessionEnd (Claude)
    action      shell | edit | spawn | ask | wakeup | other | None (Stop etc.)
    tool_name   the harness's own tool name
    command     shell command (shell), or patch text (Codex apply_patch)
    paths       files an edit touches
    prompt      a spawned agent's brief (spawn); "" when the harness hides it
    prompt_hidden  True when the harness passed the brief encrypted (Codex does: a hook
                sees the agent type but never the brief's text — probe 2026-10-08)
    agent_type  a spawned agent's type (spawn, SubagentStart/Stop), or the type of the
                subagent a call comes from (Codex adds it to the subagent's own calls)
    report      the subagent's final reply (SubagentStop)
    background  True if a shell call was launched in the background
    transcript_path  or None — every hook must work without it
    cwd, root   working dir and the project root
    raw         the original payload

Responses:
    block(reason)            refuse the tool call (exit 2, reason to the agent)
    nudge_once(ev, key, msg) refuse ONCE per distinct key; re-issuing proceeds
    stop_continue(ev, msg)   at Stop: ask the agent to keep going (once per key)
    allow()                  exit 0

Failure policy (docs/discipline/hook-authoring.md): a hook that crashes fails OPEN (the
tool call proceeds) but never SILENTLY — `run(main)` prints a warning on stderr and
appends the traceback to logs/state/hook-errors.log.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path

# Harness tool names -> semantic action.
_ACTIONS = {
    "Bash": "shell", "shell": "shell", "exec_command": "shell", "local_shell": "shell",
    "Write": "edit", "Edit": "edit", "MultiEdit": "edit", "NotebookEdit": "edit",
    "apply_patch": "edit",
    "Agent": "spawn", "Task": "spawn", "spawn_agent": "spawn",
    # Codex 0.161 names the multi-agent tools "collaboration" + tool (probe 2026-10-08)
    "collaborationspawn_agent": "spawn",
    "AskUserQuestion": "ask",
    "ScheduleWakeup": "wakeup",
    "Skill": "skill",
}
_PATCH_PATH = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", re.M)
_PATCH_MOVE = re.compile(r"^\*\*\* Move to: (.+)$", re.M)
# Codex passes a spawned agent's brief as an opaque token (Fernet-style, "gAAAAA...").
_OPAQUE = re.compile(r"^gAAAAA[A-Za-z0-9_=-]{20,}$")


@dataclass
class Event:
    harness: str
    event: str
    action: str | None
    tool_name: str = ""
    command: str = ""
    paths: list[str] = field(default_factory=list)
    prompt: str = ""
    prompt_hidden: bool = False
    agent_type: str = ""
    report: str = ""
    background: bool = False
    transcript_path: str | None = None
    cwd: str = ""
    root: str = ""
    session_id: str = ""
    raw: dict = field(default_factory=dict)


def _harness_from_argv(argv: list[str]) -> str:
    for i, a in enumerate(argv):
        if a == "--harness" and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith("--harness="):
            return a.split("=", 1)[1]
    return "unknown"


def project_root(cwd: str = "") -> str:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return env
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=cwd or None,
                           capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            return r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return cwd or os.getcwd()


_SHELLS = {"sh", "bash", "zsh", "dash"}


def _argv_to_command(argv: list) -> str:
    """An argv-list command as the shell text that runs: `[bash, -lc, SCRIPT]` -> SCRIPT,
    anything else shell-quoted (so an argument with spaces stays one argument)."""
    argv = [str(a) for a in argv]
    if len(argv) >= 3 and os.path.basename(argv[0]) in _SHELLS and argv[1] in ("-c", "-lc", "-ic"):
        return argv[2]
    return shlex.join(argv)


def normalize(payload: dict, harness: str) -> Event:
    ev_name = payload.get("hook_event_name") or payload.get("event") or ""
    tool = payload.get("tool_name") or ""
    ti = payload.get("tool_input") or {}
    if not isinstance(ti, dict):
        ti = {"command": str(ti)}
    action = _ACTIONS.get(tool, "other") if tool else None
    command, paths, prompt, background, hidden = "", [], "", False, False
    agent_type = str(payload.get("agent_type") or "")
    if action == "shell":
        cmd = ti.get("command", "")
        command = _argv_to_command(cmd) if isinstance(cmd, list) else str(cmd)
        background = bool(ti.get("run_in_background"))
    elif action == "edit":
        if tool == "apply_patch":
            command = str(ti.get("command") or ti.get("patch") or ti.get("input") or "")
            paths = _PATCH_PATH.findall(command) + _PATCH_MOVE.findall(command)
        else:
            fp = ti.get("file_path") or ti.get("notebook_path") or ti.get("path")
            if fp:
                paths = [str(fp)]
    elif action == "spawn":
        prompt = str(ti.get("prompt") or ti.get("message") or ti.get("task") or ti.get("instructions") or "")
        if _OPAQUE.match(prompt.strip()):
            prompt, hidden = "", True
        agent_type = str(ti.get("subagent_type") or ti.get("agent_type") or ti.get("agent") or "")
    cwd = payload.get("cwd") or payload.get("working_dir") or os.getcwd()
    return Event(
        harness=harness, event=ev_name, action=action, tool_name=tool, command=command,
        paths=paths, prompt=prompt, prompt_hidden=hidden, agent_type=agent_type,
        report=str(payload.get("last_assistant_message") or "") if ev_name == "SubagentStop" else "",
        background=background,
        transcript_path=payload.get("transcript_path") or None, cwd=cwd,
        root=project_root(cwd), session_id=str(payload.get("session_id") or ""), raw=payload,
    )


def read_event(argv: list[str] | None = None, stdin=None) -> Event:
    argv = sys.argv[1:] if argv is None else argv
    data = (stdin or sys.stdin).read()
    payload = json.loads(data) if data.strip() else {}
    if not isinstance(payload, dict):
        raise ValueError("hook payload is not a JSON object")
    return normalize(payload, _harness_from_argv(argv))


# --- responses -------------------------------------------------------------

def allow() -> None:
    sys.exit(0)


def block(reason: str) -> None:
    print(reason, file=sys.stderr)
    sys.exit(2)


def state_dir(root: str) -> Path:
    d = Path(root) / "logs" / "state"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _seen(root: str, hook: str, key: str) -> bool:
    """Record `key` for `hook`; return True if it was already recorded."""
    f = state_dir(root) / f"{hook}.seen"
    h = hashlib.sha256(key.encode()).hexdigest()[:16]
    try:
        seen = set(f.read_text().split())
    except FileNotFoundError:
        seen = set()
    if h in seen:
        return True
    with open(f, "a") as fh:
        fh.write(h + "\n")
    return False


def nudge_once(ev: Event, hook: str, key: str, message: str) -> None:
    """Refuse the first time `key` is seen; let an identical re-issue through."""
    if os.environ.get("HOOKS_QUIET") == "1":
        allow()
    if _seen(ev.root, hook, key):
        allow()
    log(ev.root, "nudges", {"hook": hook, "key": key[:200]})
    block(f"[{hook}] {message}\n(Nudge, not a ban: re-issue the same call to proceed.)")


def stop_continue(ev: Event, hook: str, key: str, message: str) -> None:
    """At a Stop event, ask the agent to continue — once per key. HOOKS_QUIET=1 silences it."""
    if os.environ.get("HOOKS_QUIET") == "1":
        allow()
    if _seen(ev.root, hook, key):
        allow()
    log(ev.root, "nudges", {"hook": hook, "key": key[:200]})
    if ev.harness == "codex":
        print(json.dumps({"decision": "block", "reason": f"[{hook}] {message}"}))
        sys.exit(0)
    block(f"[{hook}] {message}")


def log(root: str, name: str, record: dict) -> None:
    """Append one JSON line to logs/<name>.jsonl (append-only)."""
    d = Path(root) / "logs"
    d.mkdir(parents=True, exist_ok=True)
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), **record}
    with open(d / f"{name}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, sort_keys=True) + "\n")


ALIVE = "harness-hooks-seen"


def mark_alive(ev: Event) -> None:
    """Record that the harness itself ran a hook in this project: when, in which session and,
    for the main thread, on which model (Codex reports it). bin/selftest and the commit gate
    warn when no hook ever ran; bin/doctor checks that one ran for its own command. A payload
    with no session id did not come from a harness and does not count."""
    if not ev.session_id:
        return
    try:
        f = state_dir(ev.root) / ALIVE
        try:
            rec = json.loads(f.read_text())
        except (OSError, ValueError):
            rec = {}
        now = time.time()
        rec.update(harness=ev.harness, session=ev.session_id, epoch=now,
                   ts=time.strftime("%Y-%m-%dT%H:%M:%S"))
        if not ev.agent_type:
            rec.update(main_session=ev.session_id, main_epoch=now,
                       main_model=str(ev.raw.get("model") or ""))
        f.write_text(json.dumps(rec, sort_keys=True) + "\n")
    except OSError:
        pass


def run(main, hook: str) -> None:
    """Run `main(event)`; on an unexpected error fail OPEN but loudly."""
    try:
        ev = read_event()
    except Exception:  # malformed payload: fail open, loudly
        _fail(hook, project_root(os.getcwd()))
        return
    mark_alive(ev)
    try:
        main(ev)
    except SystemExit:
        raise
    except Exception:
        _fail(hook, ev.root)
    sys.exit(0)


def _fail(hook: str, root: str) -> None:
    tb = traceback.format_exc()
    print(f"WARNING: hook {hook} crashed and was skipped (failing open). "
          f"Traceback in logs/state/hook-errors.log", file=sys.stderr)
    try:
        with open(state_dir(root) / "hook-errors.log", "a") as f:
            f.write(f"--- {time.strftime('%Y-%m-%dT%H:%M:%S')} {hook}\n{tb}\n")
    except OSError:
        print(tb, file=sys.stderr)
    sys.exit(0)
