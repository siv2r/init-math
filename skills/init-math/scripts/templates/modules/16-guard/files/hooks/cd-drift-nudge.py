"""cd-drift-nudge: nudge on a `cd <dir> && <lookup>` one-liner.

Event: PreToolUse, action `shell`. In a harness whose shell persists between calls, a `cd`
made for a one-off grep or ls carries the working directory into every later command, and
a later `git commit -- <relative path>` or `bin/<script>` then runs from the wrong place.
Fires when a command STARTS with `cd <path>` followed (`&&` or `;`) by a read or lookup
command (grep, rg, ls, cat, head, tail, find, wc, sed, awk, stat). `cd X && make` and other
intentional cd-then-work commands are untouched.

Nudge, not a ban: once per session (once per target made it fire on every new run
directory); re-issuing proceeds. Bypass: CD_DRIFT_OK=1.
No-op on Codex, whose shell calls do not share a working directory.
See docs/discipline/guard.md.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _payload  # noqa: E402

HOOK = "cd-drift-nudge"
_READ_VERB = r"(?:grep|egrep|fgrep|rg|ls|cat|head|tail|find|wc|sed|awk|stat)"
_CD_LOOKUP = re.compile(r"^\s*(?:\w+=\S+\s+)*cd\s+(\S+)\s*(?:&&|;)\s*" + _READ_VERB + r"\b")

MESSAGE = (
    "This `cd <dir> && <lookup>` changes the working directory for every LATER shell call "
    "too, so a later relative path (a pathspec-scoped commit, a `bin/` script) runs from the "
    "wrong place. For a one-off lookup pass an absolute path instead (`grep -n pattern "
    "/abs/path/file`). If you need the cd, return to the project root afterwards. "
    "See docs/discipline/guard.md."
)


def main(ev: _payload.Event) -> None:
    if ev.action != "shell" or ev.harness == "codex":
        return
    if os.environ.get("CD_DRIFT_OK") == "1":
        return
    m = _CD_LOOKUP.match(ev.command or "")
    if not m or _no_move(m.group(1), ev):
        return
    _payload.nudge_once(ev, HOOK, "cd|" + (ev.session_id or ev.transcript_path or m.group(1)), MESSAGE)


def _no_move(target: str, ev: _payload.Event) -> bool:
    # `cd "$PWD"`, `cd .` and a cd to the project root or the current directory change
    # nothing, so they cannot cause drift (agents often start a command with `cd "$PWD";`).
    t = target.strip("'\"")
    if t in (".", "$PWD", "${PWD}"):
        return True
    try:
        here = {Path(d).resolve() for d in (ev.cwd, ev.root) if d}
        return Path(os.path.expanduser(t)).resolve() in here
    except (OSError, ValueError):
        return False


if __name__ == "__main__":
    _payload.run(main, HOOK)
