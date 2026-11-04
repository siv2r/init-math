"""launch-guard: keep every long job tracked; refuse the launches and waits that lose it.

Event: PreToolUse, action `shell`. Three checks (docs/discipline/launch.md, "The hooks"):

BLOCK (the owner may lift it by starting the agent with LAUNCH_GUARD_OFF=1 in its
environment; written inside the command it does nothing):
  1. Double background. The call is already a background job the harness tracks
     (`run_in_background`, Claude Code only) and the command backgrounds again inside
     (`nohup ... &`, `&`, setsid, disown) without waiting for it. The outer shell returns
     at once, the harness reports the job finished, and the real job runs on untracked.
     Never correct, so blocked. On a harness without `run_in_background` (Codex) this
     check cannot fire.
  2. A hand-rolled wait loop: a for/while/until loop that sleeps and probes a process or a
     file (pgrep, ps, jobs, `kill -0`, `test -e/-f`, `[ -e/-f ...]`, a harness task-output
     file). bin/wait-until-done covers every such wait (--pid, --run, --file, PATTERN) with a
     timeout, and its PATTERN form ignores its own command line, which a `pgrep -f` loop
     matches (so it waits forever). Commands naming bin/wait-until-done or bin/bg-run are
     exempt. A retry loop with no probe (`until curl -sf URL; do sleep 5; done`) is allowed.

NUDGE (once per distinct command; re-issuing proceeds):
  3. A detached launch: `&`, setsid or disown in a call that is NOT a tracked background job.
     Nothing will report when the job ends. A deliberate detached job exists (a short helper),
     so this is a nudge, as in the source. Exempt when the same command later waits for or
     kills the job (`a & b & wait`, `server & ...; kill $!`).

Messages depend on the harness (`--harness`): where a background job notifies the agent on
completion (Claude Code) they point at `run_in_background`; elsewhere (Codex) at a
foreground run, `bin/bg-run --runs runs/ --detach` and `bin/wait-until-done`.

Text is scanned with quoted strings, heredoc bodies and comments blanked, so a commit
message mentioning `nohup ... &` is not a launch. A guardrail against natural spellings,
not a sandbox: `sh -c '... &'`, screen and tmux pass. Fails open loudly on an internal error.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _payload  # noqa: E402

HOOK = "launch-guard"
# Harnesses whose background shell jobs notify the agent on completion. Mirrors the
# renderer's `background_callback` capability (renderer/adapters/claude.py).
_HAS_BG_CALLBACK = frozenset({"claude"})

_HEREDOC_RE = re.compile(r"(?<!<)<<-?[ \t]*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
_QUOTED_RE = re.compile(r"'[^']*'|\"(?:\\.|[^\"\\])*\"")
_COMMENT_RE = re.compile(r"(^|[ \t;])#[^\n]*", re.M)
_AMP_RE = re.compile(r"(?<![&>|<])&(?![&>])")
_SETSID_RE = re.compile(r"(?<![\w-])setsid(?![\w-])(?!\s+(?:-w|--wait)\b)")
_DISOWN_RE = re.compile(r"(?<![\w-])disown(?![\w-])")
_REAPED_RE = re.compile(r"(?<![\w-])(?:wait|p?kill)(?!\w)")
_LOOP_RE = re.compile(r"(?<![\w-])(?:for|while|until)(?![\w-])")
_SLEEP_RE = re.compile(r"(?<![\w-])sleep(?![\w-])")
_PROBE_RE = re.compile(
    r"(?<![\w.-])(?:pgrep|ps|jobs)(?![\w.-])"
    r"|(?<![\w-])kill\s+-0(?!\w)"
    r"|/tasks/\S*\.output\b"
    r"|(?<![\w-])test\s+(?:!\s+)?-[ef](?!\w)"
    r"|\[\[?\s+(?:!\s+)?-[ef]\s")
_WAITER_RE = re.compile(r"(?<![\w-])(?:wait-until-done|bg-run)(?![\w-])")


def code_view(cmd: str) -> str:
    """The command with heredoc bodies removed and quoted strings and comments blanked."""
    lines = cmd.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        delims = [m.group(2) for m in _HEREDOC_RE.finditer(line)]
        i += 1
        for d in delims:
            while i < len(lines) and lines[i].strip() != d:
                i += 1
            i += 1
    text = _QUOTED_RE.sub("''", "\n".join(out))
    return _COMMENT_RE.sub(r"\1", text)


def detaches(code: str) -> bool:
    """True if the command leaves a job running after it returns."""
    for m in _AMP_RE.finditer(code):
        if not _REAPED_RE.search(code, m.end()):
            return True
    return bool(_SETSID_RE.search(code) or _DISOWN_RE.search(code))


def wait_loop(code: str) -> bool:
    if _WAITER_RE.search(code):
        return False
    return bool(_LOOP_RE.search(code) and _SLEEP_RE.search(code) and _PROBE_RE.search(code))


def _double_bg_message() -> str:
    return (
        f"[{HOOK}] Refused: this call already runs as a background job the harness tracks "
        "(run_in_background), and the command backgrounds again inside it (`&`, `nohup ... &`, "
        "setsid or disown) without waiting for it. The outer shell then returns at once, the harness reports the job "
        "finished, and the real job runs on untracked: no completion notice, and its result is "
        "lost. Use one mechanism: make the plain command (or `bin/bg-run -- CMD`, for a "
        "heartbeat) the body of the background call, with no inner `&`. "
        "See docs/discipline/launch.md.")


def _wait_loop_message(callback: bool) -> str:
    head = (f"[{HOOK}] Refused: a hand-rolled wait loop (a loop that sleeps and checks a process "
            "or a file). ")
    tool = ("`bin/wait-until-done --pid PID | --run RUN_DIR | --file PATH | PATTERN` does the "
            "same wait with a timeout (exit 2), and its PATTERN form ignores its own command "
            "line, which a `pgrep -f` loop matches, so it waits forever. ")
    if callback:
        return (head + "A job launched with run_in_background already notifies you when it "
                "ends: do other work or end the turn, and continue on that notice. For a job the "
                "harness does not track, " + tool + "See docs/discipline/launch.md.")
    return (head + "Use " + tool + "Better still, run the job itself in the foreground "
            "(`bin/bg-run -- CMD` adds a heartbeat) so there is nothing to wait for. "
            "See docs/discipline/launch.md.")


def _detached_message(callback: bool) -> str:
    head = ("This command detaches a job (`&`, setsid or disown) that nothing tracks: nobody "
            "will notice when it ends, or that it died. ")
    tail = ("To run parallel pieces inside one call, end the call with `wait`. If you mean to "
            "leave a short helper running, re-issue the same call. See docs/discipline/launch.md.")
    if callback:
        return (head + "Run the plain command (or `bin/bg-run -- CMD`) as a background call "
                "with run_in_background instead; the harness notifies you when it ends. " + tail)
    return (head + "This harness does not notify you when a background job ends, and a "
            "detached job can die with the session unnoticed. Run it in the foreground to "
            "completion (`bin/bg-run -- CMD` adds a heartbeat). If it may outlive the session, "
            "run it as `bin/bg-run --runs runs/ --detach -- CMD`, which runs it apart from the "
            "session and records it on disk; check it later with `bin/bg-run --status runs/<ts>` or wait with "
            "`bin/wait-until-done --run runs/<ts>`. " + tail)


def main(ev: _payload.Event) -> None:
    if ev.action != "shell" or not ev.command.strip():
        return
    if os.environ.get("LAUNCH_GUARD_OFF") == "1":
        return
    code = code_view(ev.command)
    callback = ev.harness in _HAS_BG_CALLBACK
    if ev.background and detaches(code):
        _payload.block(_double_bg_message())
    if wait_loop(code):
        _payload.block(_wait_loop_message(callback))
    if not ev.background and detaches(code):
        _payload.nudge_once(ev, HOOK, ev.command, _detached_message(callback))


if __name__ == "__main__":
    _payload.run(main, HOOK)
