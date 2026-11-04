#!/usr/bin/env python3
"""brief-leak-nudge: refuse once a reviewer brief that tells the reviewer the claim's history.

Event: PreToolUse, action `spawn`, for `claim-auditor`, `proof-referee` and `red-team`.
Shipped only to Claude Code projects (it lives under `@claude/`): other harnesses hide the
brief from hooks.

A reviewer judges what it is given. Told that an earlier pass found the claim sound, or
how confident the author is, it judges toward that: models switch from right answers to
wrong ones after reading what peers concluded. So the brief withholds earlier verdicts, the
author's confidence and the exploration (the gate-chain skill, "The brief"). This hook
looks for the leaks it can see:
  * a passing verdict word (SOUND, CLEAN, SURVIVED, ...; from [gates.verdicts] when the
    project has it) as a whole upper-case word, except on a quoted evidence entry
    (`result: <WORD>`) or a line that lists verdict options (it also names a failing word);
  * `CREDENCE NOW` or an `author-miss:` line;
  * a phrase such as "already checked", "previous round", "held up", "the author believes".
When the prompt names a brief file ("brief: work/x/scratch/brief.md"), that file is read
too. Nudge, not a ban: fires once per reviewer and set of leaks; re-issuing proceeds (a
quoted evidence line the reviewer needs is a reason to). It does not check the owner's name
(the provenance reviewer needs it) or scratch paths (briefs live there).
Bypass: BRIEF_LEAK_OK=1, HOOKS_QUIET=1, or re-issue.
"""
from __future__ import annotations

import os
import re
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _payload  # noqa: E402

HOOK = "brief-leak-nudge"
REVIEWERS = {"claim-auditor", "proof-referee", "red-team"}
PASSING = ["SOUND", "CLEAN", "SURVIVED", "SELF-CONTAINED", "READER-READY", "ATTRIBUTION-CLEAN"]
FAILING = ["OVER-CLAIMED", "UNSUPPORTED", "INCONSISTENT", "NEEDS-WORK", "REFUTED", "NARROWED",
           "INCONCLUSIVE", "NEEDS-CONTEXT", "NEEDS-CITATIONS"]
PHRASES = re.compile(
    r"\balready (checked|reviewed|passed|verified)\b|\bprevious (pass|round|review)\b"
    r"|\bheld up\b|\bthe (author|worker) (is confident|believes)\b", re.I)
MARKS = re.compile(r"CREDENCE NOW|author-miss:")
BRIEF_FILE = re.compile(r"\bbrief(?: file)?\s*(?::|is in|at)\s*`?([A-Za-z0-9_./-]+\.(?:md|txt))", re.I)


def _word(w: str) -> re.Pattern:
    return re.compile(r"(?<![A-Za-z-])" + re.escape(w) + r"(?![A-Za-z-])")


def passing_words(root: str) -> list[str]:
    try:
        with open(Path(root) / "project.toml", "rb") as f:
            v = tomllib.load(f).get("gates", {}).get("verdicts") or {}
    except (OSError, tomllib.TOMLDecodeError):
        v = {}
    words = {str(x).upper() for vals in v.values() for x in vals}
    return sorted(words or set(PASSING))


def leaks(text: str, words: list[str]) -> list[str]:
    pats = [(w, _word(w)) for w in words]
    fails = [_word(w) for w in FAILING]
    found = []
    for line in text.splitlines():
        if re.search(r"\bresult:\s*[A-Z-]+", line):
            continue
        if any(p.search(line) for p in fails):
            continue
        for w, p in pats:
            if p.search(line):
                found.append(w)
        found += MARKS.findall(line)
        found += [m.group(0).lower() for m in PHRASES.finditer(line)]
    return sorted(set(found))


def brief_text(prompt: str, root: str) -> str:
    text = prompt
    base = Path(root).resolve()
    for m in BRIEF_FILE.finditer(prompt):
        p = (base / m.group(1)).resolve()
        if base in p.parents and p.is_file():
            try:
                text += "\n" + p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                pass
    return text


def main(ev):
    if ev.action != "spawn" or ev.agent_type not in REVIEWERS:
        return
    if os.environ.get("BRIEF_LEAK_OK") == "1":
        return
    hits = leaks(brief_text(ev.prompt, ev.root), passing_words(ev.root))
    if not hits:
        return
    _payload.nudge_once(
        ev, HOOK, f"{ev.agent_type}|{'|'.join(hits)}",
        f"This {ev.agent_type} brief tells the reviewer the claim's history: {', '.join(hits)}. "
        "A reviewer told that an earlier pass found the claim sound, or how confident the "
        "author is, judges toward it. Give the claim, the text and the evidence; on a "
        "re-review say what changed and where, not how it fared before (the gate-chain skill, "
        "'The brief'). If the line is needed, for example a quoted evidence entry, re-issue "
        "the same dispatch.",
    )


if __name__ == "__main__":
    _payload.run(main, HOOK)
