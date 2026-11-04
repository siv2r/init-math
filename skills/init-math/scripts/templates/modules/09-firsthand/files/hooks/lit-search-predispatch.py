"""lit-search-predispatch: record each literature search, and remind once per session to do
the internal half of the prior-art search first.

Event: PreToolUse, action `spawn`.

Fires when the spawned agent is `lit-search`, or when the brief reads like a literature
search ("literature search", "prior art", "is this known", "arxiv", "web search", ...).
Every such dispatch is recorded (a timestamp line in logs/state/lit-searches.log), which is
what the sibling `lit-search-gate` hook reads at commit time. The first one in a session is
refused once with a reminder: search the project's own record first and scope the external
search to the gap. A hook cannot tell whether you did that for THIS topic, so it only
reminds, once per session. See docs/discipline/firsthand-checks.md.

When the harness hides the brief from hooks (Codex), the hook only records the search:
the `Internal prior art:` line cannot be seen, so a refusal could never be satisfied and
would cost a wasted call in every session. The lit-search agent, which does see its
brief, checks for that line itself.

Bypass: LIT_PRIOR_ART_OK=1 in the environment, or a line in the brief starting
`Internal prior art:` (saying what the internal search found).
"""
from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _payload  # noqa: E402

HOOK = "lit-search-predispatch"
LIT_AGENTS = {"lit-search"}
LIT_INTENT = re.compile(
    r"lit(?:erature)?[- ]?search|prior[- ]art|is (?:this|it) (?:already )?known|already known"
    r"|search the literature|survey the literature|arxiv|web ?search", re.I)
DECLARED = re.compile(r"^\s*[-*]?\s*Internal prior art\s*:", re.I | re.M)


def is_lit_search(ev: _payload.Event) -> bool:
    if ev.agent_type in LIT_AGENTS:
        return True
    desc = str((ev.raw.get("tool_input") or {}).get("description") or "")
    return bool(LIT_INTENT.search(ev.prompt) or LIT_INTENT.search(desc))


def record(root: str) -> None:
    with open(_payload.state_dir(root) / "lit-searches.log", "a", encoding="utf-8") as f:
        f.write(f"{int(time.time())}\n")


def message(root: str) -> str:
    r = Path(root)
    places = []
    if (r / "wiki" / "conjectures").is_dir():
        places.append("wiki/conjectures/ (including @residue lines, any status)")
    if (r / "bin" / "question-check").exists():
        places.append("sibling conjectures on the same question (bin/question-check --tsv)")
    if (r / "wiki" / "known-results").is_dir():
        places.append("wiki/known-results/")
    if (r / "experiments").is_dir():
        places.append("experiments/_index.md")
    places.append("the notes and sources under wiki/")
    return ("Before an external literature search, do the internal half: search "
            + "; ".join(places)
            + ". Then scope the search to what the project does not already record, and put a "
              "line 'Internal prior art: <what you found>' in the brief. "
              "See docs/discipline/firsthand-checks.md. Bypass: LIT_PRIOR_ART_OK=1.")


def main(ev: _payload.Event) -> None:
    if ev.action != "spawn" or not is_lit_search(ev):
        return
    record(ev.root)  # before any nudge: nudge_once exits the process
    if os.environ.get("LIT_PRIOR_ART_OK") == "1" or DECLARED.search(ev.prompt):
        return
    if ev.prompt_hidden:
        return  # see the module docstring: the lit-search agent checks its own brief
    key = ev.session_id or ev.transcript_path or "no-session"
    _payload.nudge_once(ev, HOOK, key, message(ev.root))


if __name__ == "__main__":
    _payload.run(main, HOOK)
