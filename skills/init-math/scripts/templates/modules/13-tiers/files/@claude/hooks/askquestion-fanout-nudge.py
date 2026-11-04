"""askquestion-fanout-nudge: nudge before asking the owner a pick-one question with 3+ options.

Event: PreToolUse, action `ask` (the harness's structured ask-the-owner tool). Shipped only
to Claude Code projects (it lives under `@claude/`); harnesses without such a tool do not
get it.

A pick-one menu of next steps is often a list of complementary threads that could all run.
Making the owner choose stalls the work and hands them a decision that was not theirs.
If the options are independent, cheap and within what you were asked to do, do them
(in parallel where possible) and report; ask only at a genuine fork: mutually exclusive
designs, an irreversible or outward-facing call, or a scope only the owner decides.
See docs/discipline/tiers.md.

Nudge, not a ban: fires once per distinct question set; re-issuing proceeds.
Bypass: ASKQ_FANOUT_OK=1 in the environment.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _payload  # noqa: E402

HOOK = "askquestion-fanout-nudge"
MIN_OPTIONS = 3

MESSAGE = (
    "You are about to ask the owner to pick ONE of {n} options. If two or more of them are "
    "independent, cheap threads within what you were asked to do, do them (in parallel where "
    "you can) and report instead, keeping only the real choice as a one-line note. Ask only "
    "at a genuine fork: mutually exclusive designs, an irreversible or outward-facing call, "
    "or a scope decision only the owner can make. See docs/discipline/tiers.md."
)


def main(ev: _payload.Event) -> None:
    if ev.action != "ask":
        return
    if os.environ.get("ASKQ_FANOUT_OK") == "1":
        return
    ti = ev.raw.get("tool_input") or {}
    qs = ti.get("questions") if isinstance(ti, dict) else None
    if not isinstance(qs, list):
        return
    sizes = [len(q.get("options") or []) for q in qs
             if isinstance(q, dict) and not q.get("multiSelect")]
    big = [n for n in sizes if n >= MIN_OPTIONS]
    if not big:
        return
    key = hashlib.sha1(json.dumps(qs, sort_keys=True).encode()).hexdigest()
    _payload.nudge_once(ev, HOOK, key, MESSAGE.format(n=max(big)))


if __name__ == "__main__":
    _payload.run(main, HOOK)
