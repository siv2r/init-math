"""agent-brief-lint: nudge when a dispatch brief asks the agent to run or time a long job.

Event: PreToolUse, action `spawn` (an agent is about to be dispatched).

A dispatched agent cannot wait for a job that outlives its turn: the job keeps running with
nobody to read its result, or dies with the agent. So a brief that says "run the full sweep
yourself" or "time a few representative cases" sets the agent up to orphan the job. The
split that works: the agent validates on one seconds-scale known-answer case and RETURNS the
exact command; the coordinator runs the long job. See docs/discipline/tiers.md.

Nudge, not a ban: fires once per distinct brief; re-issuing the same dispatch proceeds.
Bypass: AGENT_BRIEF_OK=1 in the environment.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _payload  # noqa: E402

HOOK = "agent-brief-lint"

_UNITS = r"(?:items?|cases?|instances?|inputs?|parameters?|runs?|jobs?)"
TELLS = [
    re.compile(r"\bcost[-\s]?prob(?:e|es|ing)\b", re.I),
    re.compile(r"\btim(?:e|ing)\s+(?:(?:a\s+few|several|some|a\s+handful\s+of|the|\d+)\s+)?"
               r"(?:representative\s+|typical\s+|heaviest\s+)?" + _UNITS + r"\b", re.I),
    re.compile(r"\b(?:project|estimate|measure|profile)\s+the\s+per[-\s]?" + _UNITS + r"\s+cost\b", re.I),
    re.compile(r"\brun\s+the\s+(?:full\s+|whole\s+|complete\s+|entire\s+)?"
               r"(?:sweep|search|census|build|computation)\s+yourself\b", re.I),
    # "you run/launch the full sweep": second-person only, so "I will run the full sweep
    # after you return" (the coordinator's own plan) does not match.
    re.compile(r"\byou(?:\s+should|\s+must|\s+will|\s+can)?\s+(?:then\s+)?(?:run|launch|start)\s+the\s+"
               r"(?:full|whole|complete|entire)\s+(?:sweep|search|census|build|computation)\b", re.I),
]
# "do not run it in the background" is the CORRECT instruction, so background wording is
# deliberately not a tell.

MESSAGE = (
    "This brief asks the dispatched agent to run or time a long job (matched: {hits}). "
    "A dispatched agent cannot wait for a job that outlives its turn, so the job is orphaned "
    "and its result lost. Instead: have the agent validate on ONE seconds-scale known-answer "
    "case and RETURN the exact run command; you (the coordinator) run the long job and any "
    "multi-minute timing probe. Also restate in the brief: do not background anything. "
    "See docs/discipline/tiers.md."
)


def main(ev: _payload.Event) -> None:
    if ev.action != "spawn" or not ev.prompt:
        return
    if os.environ.get("AGENT_BRIEF_OK") == "1":
        return
    hits = [m.group(0) for t in TELLS for m in [t.search(ev.prompt)] if m]
    if not hits:
        return
    key = "|".join(h.lower() for h in hits) + "\n" + ev.prompt[:200]
    _payload.nudge_once(ev, HOOK, key, MESSAGE.format(hits="; ".join(repr(h) for h in hits)))


if __name__ == "__main__":
    _payload.run(main, HOOK)
