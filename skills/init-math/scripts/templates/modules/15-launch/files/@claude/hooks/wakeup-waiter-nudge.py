"""wakeup-waiter-nudge: nudge when a short scheduled wakeup duplicates a tracked background job.

Event: PreToolUse, action `wakeup` (the harness's scheduled self-wakeup tool). Harnesses
without such a tool never register this hook; the file is still shipped so the hook set is
the same everywhere.

A background job the harness tracks already wakes the agent when it finishes. Scheduling a
short wakeup on top of it is a redundant waiter: the agent wakes mid-job, polls, and spends
a turn learning nothing. Fires when, in the current turn (after the owner's last message), a
tracked background command was launched and the wakeup is short (under 20 minutes).
A long wakeup (a deliberate backstop) and a wakeup that ends a loop are allowed.
See docs/discipline/launch.md.

Needs the transcript; without one it does nothing. Nudge, not a ban: once per identical
call. Bypass: WAKEUP_OK=1 in the environment.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _payload  # noqa: E402

HOOK = "wakeup-waiter-nudge"
LONG_FALLBACK_S = 1200
TAIL_BYTES = 2_000_000

MESSAGE = (
    "You launched a background job the harness tracks in this turn; its completion notice "
    "already wakes you. A short scheduled wakeup on top of it only makes you poll a running "
    "job. End the turn and wait for the notice. If this is a deliberate backstop, use a delay "
    "of 20 minutes or more, or re-issue the same call. See docs/discipline/launch.md."
)


def _genuine_user(rec: dict) -> bool:
    if rec.get("type") != "user" or rec.get("isSidechain"):
        return False
    c = (rec.get("message") or {}).get("content")
    if isinstance(c, str):
        return bool(c.strip()) and not c.lstrip().startswith("<")
    if isinstance(c, list):
        kinds = {b.get("type") for b in c if isinstance(b, dict)}
        return "text" in kinds and "tool_result" not in kinds
    return False


def background_launch_this_turn(path: str) -> bool:
    p = Path(path)
    if not p.is_file():
        return False
    with open(p, "rb") as f:
        f.seek(0, os.SEEK_END)
        f.seek(max(0, f.tell() - TAIL_BYTES))
        lines = f.read().decode("utf-8", errors="replace").splitlines()
    recs = []
    for line in lines:
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if isinstance(r, dict):
            recs.append(r)
    last_user = max((i for i, r in enumerate(recs) if _genuine_user(r)), default=-1)
    for r in recs[last_user + 1:]:
        content = (r.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use" \
                    and (block.get("input") or {}).get("run_in_background") is True:
                return True
    return False


def main(ev: _payload.Event) -> None:
    if ev.action != "wakeup":
        return
    if os.environ.get("WAKEUP_OK") == "1":
        return
    ti = ev.raw.get("tool_input") or {}
    if not isinstance(ti, dict) or ti.get("stop") is True:
        return
    delay = ti.get("delaySeconds")
    if isinstance(delay, (int, float)) and delay >= LONG_FALLBACK_S:
        return
    if not ev.transcript_path or not background_launch_this_turn(ev.transcript_path):
        return
    key = hashlib.sha1(json.dumps(ti, sort_keys=True).encode()).hexdigest()
    _payload.nudge_once(ev, HOOK, key, MESSAGE)


if __name__ == "__main__":
    _payload.run(main, HOOK)
