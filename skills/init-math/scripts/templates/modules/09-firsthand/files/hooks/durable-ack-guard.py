"""durable-ack-guard: at the end of a turn, catch a claim that a record was written when no
write to it happened.

Event: Stop.

Fires when the turn's final message has a past-tense write verb (recorded, logged, appended,
wrote, written, saved, added, updated, registered, flipped, transcribed) within 80 characters of a
record token, and nothing backs it:

    C<nnn>         wiki/conjectures/C<nnn>*.md
    Q<nnn>         wiki/questions/Q<nnn>*.md
    analysis.md    experiments/**/analysis.md
    known-results  wiki/known-results/*.md
    ledger         wiki/conjectures/*.md

A token whose directory does not exist is ignored. A claim is backed when, since the last
message from the owner, a tool call mentioned the file (an edit to it, or a command naming
it), or the file was modified in the last hour, or git shows it changed. The bias is toward
NOT firing: a missed nudge costs little, a false one blocks the end of a turn.

Asks the agent to continue once per distinct set of claims; inert when the harness says a
stop hook is already active. Needs the final message (from the payload, or the transcript);
without it, does nothing. Bypass: ACK_OK=1 or HOOKS_QUIET=1. See docs/discipline/firsthand-checks.md.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _payload  # noqa: E402

HOOK = "durable-ack-guard"
RECENT_S = 3600
TAIL_BYTES = 4_000_000
VERB = (r"\b(?:recorded|logged|appended|wrote|written|saved|added|updated|registered|flipped"
        r"|transcribed)\b")
TOKEN = r"\b(?:[CQ]\d{3}\b|analysis\.md\b|known-results\b|ledger\b)"
CLAIM = re.compile(rf"{VERB}[^\n]{{0,80}}?{TOKEN}|{TOKEN}[^\n]{{0,80}}?{VERB}", re.I)
TOKEN_RX = re.compile(TOKEN, re.I)


def _genuine_user(rec: dict) -> bool:
    if rec.get("type") != "user" or rec.get("isSidechain"):
        return False
    c = (rec.get("message") or {}).get("content")
    if isinstance(c, str):
        return bool(c.strip()) and not c.lstrip().startswith("<")
    if isinstance(c, list):
        kinds = {b.get("type") for b in c if isinstance(b, dict)}
        return bool(kinds) and kinds != {"tool_result"}
    return False


def load_turn(path: str | None) -> tuple[str | None, str]:
    """(final assistant text, all tool-call inputs since the last owner message)."""
    if not path or not Path(path).is_file():
        return None, ""
    with open(path, "rb") as f:
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
    start = max((i for i, r in enumerate(recs) if _genuine_user(r)), default=-1) + 1
    final, evidence = None, []
    for r in recs[start:]:
        if r.get("type") != "assistant" or r.get("isSidechain"):
            continue
        content = (r.get("message") or {}).get("content")
        if isinstance(content, str):
            final = content
            continue
        texts = []
        for b in content or []:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "text":
                texts.append(str(b.get("text") or ""))
            elif b.get("type") == "tool_use":
                evidence.append(json.dumps(b.get("input") or {}))
        if texts:
            final = "\n".join(texts)
    return final, "\n".join(evidence)


def candidates(root: Path, token: str) -> list[Path] | None:
    t = token.lower()
    if re.fullmatch(r"c\d{3}", t):
        d = root / "wiki" / "conjectures"
        return sorted(d.glob(f"{token.upper()}*.md")) if d.is_dir() else None
    if re.fullmatch(r"q\d{3}", t):
        d = root / "wiki" / "questions"
        return sorted(d.glob(f"{token.upper()}*.md")) if d.is_dir() else None
    if t == "analysis.md":
        d = root / "experiments"
        return sorted(d.glob("**/analysis.md")) if d.is_dir() else None
    if t == "known-results":
        d = root / "wiki" / "known-results"
        return sorted(d.glob("*.md")) if d.is_dir() else None
    if t == "ledger":
        d = root / "wiki" / "conjectures"
        return sorted(d.glob("*.md")) if d.is_dir() else None
    return None


def git_changed(root: Path) -> set[str]:
    try:
        r = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=root,
                           capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return set()
    return {l[3:].split(" -> ")[-1].strip('"') for l in r.stdout.splitlines() if len(l) > 3}


def backed(root: Path, token: str, evidence: str, changed: set[str]) -> bool:
    files = candidates(root, token)
    if files is None:
        return True  # this project has no such record: not our business
    if token.lower() in evidence.lower():
        return True
    now = time.time()
    for f in files:
        rel = f.relative_to(root).as_posix()
        if rel in evidence or f.name in evidence or rel in changed:
            return True
        try:
            if now - f.stat().st_mtime < RECENT_S:
                return True
        except OSError:
            continue
    return False


def main(ev: _payload.Event) -> None:
    if ev.event != "Stop":
        return
    raw = ev.raw
    if raw.get("stop_hook_active") or os.environ.get("ACK_OK") == "1":
        return
    final = raw.get("last_assistant_message") or raw.get("last-assistant-message")
    t_final, evidence = load_turn(ev.transcript_path)
    final = final or t_final
    if not final:
        return
    root = Path(ev.root)
    changed = git_changed(root)
    unbacked = []
    for m in CLAIM.finditer(str(final)):
        snippet = m.group(0)
        token = TOKEN_RX.search(snippet).group(0)
        if not backed(root, token, evidence, changed):
            unbacked.append(" ".join(snippet.split()))
    if not unbacked:
        return
    _payload.stop_continue(ev, HOOK, "\n".join(sorted(set(unbacked))), (
        "Your final message says a record was written, but no write to it happened in this turn: "
        + "; ".join(f'"{s}"' for s in sorted(set(unbacked))[:3])
        + ". Do the write now, or correct the message. "
          "(If it was written earlier, say where; bypass: ACK_OK=1.)"))


if __name__ == "__main__":
    _payload.run(main, HOOK)
