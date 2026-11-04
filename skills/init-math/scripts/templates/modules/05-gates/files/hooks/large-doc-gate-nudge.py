#!/usr/bin/env python3
"""Large-document gate nudge (PreToolUse, spawn).

When a review agent (claim-auditor, proof-referee, red-team, cold-reader, expositor,
provenance) is dispatched on a document of more than 400 lines and the brief shows no sign
of being scoped to a section, refuse once and suggest a section extract plus a short
preamble of trusted context. Why: a whole long document fed to one reviewer dilutes its
attention, and real defects in one section pass unnoticed. Re-issuing the identical
dispatch proceeds (a small document, or one that is entirely the finding, is fed whole).

Paths named as a reference, style model or lookup source in the ~80 characters before them
are skipped: they are not the document under review. Explained in the gate-chain skill (rule 4,
"Large documents"). Bypass: LARGE_DOC_GATE_OK=1, HOOKS_QUIET=1, or re-issue.
"""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _payload  # noqa: E402

HOOK = "large-doc-gate-nudge"
REVIEWERS = {"claim-auditor", "proof-referee", "red-team", "cold-reader", "expositor", "provenance"}
THRESHOLD = 400

PATH_RE = re.compile(r"(?<![\w/:.-])(?!https?://)[A-Za-z0-9_][A-Za-z0-9_./-]*\.(?:md|tex)\b")
SCOPED_RE = re.compile(
    r"section|extract|preamble|excerpt|\bL\d+\b|\bl\.\s?\d+|\blines?\s+~?\d+|diff-scoped|§"
    r"|\bonly the\b|\bjust the\b",
    re.I,
)
REF_CUE_RE = re.compile(
    r"referenc|style model|as a model|model:|full ?text|look ?up|consult|source file|sources?:"
    r"|cross-check against|compare against|for context",
    re.I,
)


def _lines(path: Path) -> int:
    with open(path, "rb") as fh:
        return sum(1 for _ in fh)


def oversized_target(prompt: str, root: str):
    base = Path(root).resolve()
    for m in PATH_RE.finditer(prompt):
        if REF_CUE_RE.search(prompt[max(0, m.start() - 80):m.start()]):
            continue
        p = (base / m.group(0)).resolve()
        if base not in p.parents or not p.is_file():
            continue
        n = _lines(p)
        if n > THRESHOLD:
            return m.group(0), n
    return None


def main(ev):
    if ev.action != "spawn" or ev.agent_type not in REVIEWERS:
        return
    if os.environ.get("LARGE_DOC_GATE_OK") == "1":
        return
    if SCOPED_RE.search(ev.prompt):
        return
    hit = oversized_target(ev.prompt, ev.root)
    if not hit:
        return
    rel, n = hit
    _payload.nudge_once(
        ev, HOOK, f"{ev.agent_type}|{rel}|{ev.prompt[:200]}",
        f"This {ev.agent_type} dispatch targets {rel} ({n} lines, over {THRESHOLD}) and the brief "
        "shows no section scoping (a section name, an extract, a line range). A whole long "
        "document dilutes the reviewer's attention, so defects in one section get missed. "
        "Give the reviewer the new or changed section plus a short preamble of the definitions "
        "and already-reviewed results it leans on, marked 'assume correct, do not re-review'. "
        "If the whole document really is the finding, re-issue the same dispatch (or set "
        "LARGE_DOC_GATE_OK=1). See the gate-chain skill, rule 4 (Large documents).",
    )


if __name__ == "__main__":
    _payload.run(main, HOOK)
