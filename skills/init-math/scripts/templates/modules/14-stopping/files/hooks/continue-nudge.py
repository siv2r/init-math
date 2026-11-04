"""continue-nudge: when the owner's last message was a bare "continue", ask once for more work.

Event: Stop (the agent is about to end its turn).

If the owner's most recent message is only a continue signal ("continue", "keep going",
"carry on", ...), ending the turn at an incremental checkpoint is the classic early stop.
This hook asks the agent, once per such message, to keep going if a concrete next step
exists. If the agent really is at a genuine block, fork or worked-through deep core, it
says so and stops again; the hook does not fire twice for the same message.
See docs/discipline/stopping.md.

Needs the session transcript: with no transcript path, or an unreadable one, it does
nothing. Owner switch: CONTINUE_NUDGE_OFF=1 in the environment.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _payload  # noqa: E402

HOOK = "continue-nudge"
MAX_LEN = 150
TAIL_BYTES = 2_000_000  # only the end of a long transcript matters

_CONTINUE_RE = re.compile(
    r"^\s*(?:ok(?:ay)?[,.!]?\s+)?(?:please\s+)?(?:let'?s\s+)?"
    r"(?:continue|keep\s+(?:going|it\s+going|at\s+it)|carry\s+on|go\s+on|proceed|resume)\b",
    re.I,
)

MESSAGE = (
    "The owner's last message was a bare continue signal. If a next step is concretely "
    "specified and nothing genuinely blocks it, do it now and report progress inline. Stop "
    "only at a genuine block (an input you lack), a fork only the owner can decide, or a hard "
    "core you have already broken into bricks and attempted the cheapest of. Never end on an "
    "offer like 'is this a reasonable checkpoint?'. If you are at such a boundary, name it in "
    "one line and stop again; this fires once per message. See docs/discipline/stopping.md."
)


def _text_of(content) -> str | None:
    """Plain text of a user message's content, or None if it is a tool result carrier."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if not isinstance(block, dict):
                continue
            kind = block.get("type")
            if kind in ("tool_result", "function_call_output"):
                return None
            if kind in ("text", "input_text") and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "\n".join(parts)
    return None


def _user_message(obj: dict) -> tuple[str, str] | None:
    """(key, text) if this transcript line is a message typed by the human, else None.

    Tolerates the two common layouts: {"type": "user", "message": {...}} and
    {"type": "response_item", "payload": {"type": "message", "role": "user", ...}}."""
    if obj.get("isSidechain"):
        return None
    msg = None
    if obj.get("type") == "user" and isinstance(obj.get("message"), dict):
        msg = obj["message"]
    elif isinstance(obj.get("payload"), dict) and obj["payload"].get("role") == "user":
        msg = obj["payload"]
    elif obj.get("role") == "user":
        msg = obj
    if not msg or msg.get("role") != "user":
        return None
    text = _text_of(msg.get("content"))
    if text is None:
        return None
    text = text.strip()
    # Harness-injected context (system reminders, environment blocks, notifications).
    if not text or text.startswith("<") or text.startswith("[system") or "<command-name>" in text:
        return None
    key = str(obj.get("timestamp") or obj.get("uuid") or "") + "\n" + text[:200]
    return key, text


def last_user_message(path: str) -> tuple[str, str] | None:
    p = Path(path)
    if not p.is_file():
        return None
    with open(p, "rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(max(0, size - TAIL_BYTES))
        lines = f.read().decode("utf-8", errors="replace").splitlines()
    for line in reversed(lines):
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            hit = _user_message(obj)
            if hit:
                return hit
    return None


def main(ev: _payload.Event) -> None:
    if os.environ.get("CONTINUE_NUDGE_OFF") == "1":
        return
    if ev.raw.get("stop_hook_active"):
        return  # already continuing because of a Stop hook
    if not ev.transcript_path:
        return
    hit = last_user_message(ev.transcript_path)
    if not hit:
        return
    key, text = hit
    if len(text) > MAX_LEN or not _CONTINUE_RE.match(text):
        return
    _payload.stop_continue(ev, HOOK, key, MESSAGE)


if __name__ == "__main__":
    _payload.run(main, HOOK)
