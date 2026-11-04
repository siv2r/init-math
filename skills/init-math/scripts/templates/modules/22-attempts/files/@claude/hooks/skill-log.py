"""skill-log: record each skill load, for the principle-usage report.

Event: PostToolUse, action `skill` (Claude Code's Skill tool). Shipped only to Claude Code
projects (it lives under `@claude/`): Codex loads a skill without a tool call, so no hook
can see it there, and the report shows `—` for skill loads.

Appends `{"skill": <name>, "ts": ...}` to logs/skills.jsonl. bin/principle-usage counts the
loads of the skill that carries each principle (its `skill =` entry in docs/principles.toml),
so a principle whose skill is never loaded shows up. Records only; never refuses.
Bypass: SKILL_LOG_OFF=1 in the environment.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _payload  # noqa: E402

HOOK = "skill-log"


def main(ev: _payload.Event) -> None:
    if ev.action != "skill" or os.environ.get("SKILL_LOG_OFF") == "1":
        return
    ti = ev.raw.get("tool_input") or {}
    name = ti.get("skill") if isinstance(ti, dict) else None
    if not isinstance(name, str) or not name.strip():
        return
    _payload.log(ev.root, "skills", {"skill": name.strip(), "session": ev.session_id})


if __name__ == "__main__":
    _payload.run(main, HOOK)
