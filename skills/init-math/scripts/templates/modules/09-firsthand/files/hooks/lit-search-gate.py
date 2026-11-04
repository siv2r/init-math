"""lit-search-gate: nudge a commit that adds a status change or an attribution to a durable
document when no literature search has been recorded since the file last changed.

Event: PreToolUse, action `shell` (a `git commit` command).

Durable documents: wiki/conjectures/*.md, wiki/known-results/*.md, any *.tex, and any
*writeup*.md (templates, checklists and guides excluded). The commit's files are the paths
after `--`, else (with -a) the modified tracked files, else the staged files.

Fires when a changed line of such a file contains `status:` or an attribution marker
(\\cite, "due to", "attributed to", "theorem of", "corollary of", "classical(ly)",
"well-known", "special case of"), and no literature search is recorded after the file's
last commit (or in the last 24 hours, for a new file). A search counts when the
`lit-search-predispatch` hook recorded one (logs/state/lit-searches.log) or, when a
transcript is available, a web search or fetch ran. See docs/discipline/firsthand-checks.md.

Nudge, not a ban: once per set of files. Bypass: LIT_SEARCH_OK=1 in the environment or as
an inline prefix (logged as a bypass in logs/feedback.jsonl).
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _payload  # noqa: E402

HOOK = "lit-search-gate"
DAY = 24 * 3600
COMMIT = re.compile(r"(?:^|[;&|(]\s*|\s)git\s+(?:-C\s+\S+\s+)?commit\b")
DURABLE = [re.compile(p) for p in (
    r"(?:^|/)wiki/conjectures/[^/]+\.md$",
    r"(?:^|/)wiki/known-results/[^/]+\.md$",
    r"\.tex$",
    r"writeup[^/]*\.md$",
)]
EXCLUDE = re.compile(r"(?:^|/)TEMPLATE|template|checklist|guide", re.I)
MARKER = re.compile(
    r"\bstatus\s*:|\\cite|\bdue to\b|\battributed to\b|\btheorem of\b|\bcorollary of\b"
    r"|\bclassical(?:ly)?\b|\bwell[- ]known\b|\bspecial case of\b", re.I)
WEB_TOOLS = {"WebSearch", "WebFetch", "web_search", "web_fetch"}
LIT_INTENT = re.compile(r"lit(?:erature)?[- ]?search|prior[- ]art|is (?:this|it) (?:already )?known"
                        r"|already known|search the literature|arxiv|web ?search", re.I)


def git(root: str, *args: str) -> str:
    try:
        r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout if r.returncode == 0 else ""


def commit_segment(cmd: str) -> str | None:
    m = COMMIT.search(cmd)
    if not m:
        return None
    seg = cmd[m.start():]
    cut = re.search(r"\n|<<|&&|\|\||;|\|", seg)
    return seg[:cut.start()] if cut else seg


def target_files(root: str, seg: str) -> list[str]:
    try:
        words = shlex.split(seg)
    except ValueError:
        words = seg.split()
    if "--" in words:
        return [w for w in words[words.index("--") + 1:] if w]
    if any(w == "-a" or w == "--all" or (re.fullmatch(r"-[a-zA-Z]*a[a-zA-Z]*", w) and not w.startswith("--"))
           for w in words[2:]):
        return git(root, "diff", "--name-only", "HEAD").split()
    return git(root, "diff", "--cached", "--name-only").split()


def durable(path: str) -> bool:
    p = path.replace(os.sep, "/")
    return any(r.search(p) for r in DURABLE) and not EXCLUDE.search(p)


def changed_lines(root: str, path: str) -> list[str]:
    diff = git(root, "diff", "HEAD", "--", path) or git(root, "diff", "--cached", "--", path)
    if diff:
        return [l[1:] for l in diff.splitlines()
                if l[:1] in "+-" and not l.startswith(("+++", "---"))]
    f = Path(root) / path
    if f.is_file() and not git(root, "log", "-1", "--format=%ct", "--", path).strip():
        return f.read_text(encoding="utf-8", errors="replace").splitlines()  # new file: all added
    return []


def threshold(root: str, path: str) -> float:
    ct = git(root, "log", "-1", "--format=%ct", "--", path).strip()
    return float(ct) if ct.isdigit() else time.time() - DAY


def logged_searches(root: str) -> list[float]:
    f = Path(root) / "logs" / "state" / "lit-searches.log"
    try:
        return [float(x) for x in f.read_text().split() if x.replace(".", "", 1).isdigit()]
    except FileNotFoundError:
        return []


def transcript_searches(path: str | None) -> list[float]:
    out: list[float] = []
    if not path or not Path(path).is_file():
        return out
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if '"tool_use"' not in line:
                continue
            try:
                rec = json.loads(line)
                ts = datetime.fromisoformat(str(rec.get("timestamp"))).timestamp()
            except (ValueError, TypeError):
                continue
            for b in (rec.get("message") or {}).get("content") or []:
                if not isinstance(b, dict) or b.get("type") != "tool_use":
                    continue
                inp = b.get("input") or {}
                if b.get("name") in WEB_TOOLS or inp.get("subagent_type") == "lit-search" \
                        or LIT_INTENT.search(str(inp.get("prompt") or "")):
                    out.append(ts)
    return out


def main(ev: _payload.Event) -> None:
    if ev.action != "shell" or not ev.command:
        return
    seg = commit_segment(ev.command)
    if seg is None:
        return
    if os.environ.get("LIT_SEARCH_OK") == "1" or re.search(r"(^|[\s;&|])LIT_SEARCH_OK=1\b", ev.command):
        _payload.log(ev.root, "feedback", {"kind": "bypass", "text": f"{HOOK}: LIT_SEARCH_OK=1"})
        return
    files = [f for f in target_files(ev.root, seg) if durable(f)]
    flagged = [f for f in files if any(MARKER.search(l) for l in changed_lines(ev.root, f))]
    if not flagged:
        return
    searches = logged_searches(ev.root) + transcript_searches(ev.transcript_path)
    unsearched = [f for f in flagged if not any(t >= threshold(ev.root, f) for t in searches)]
    if not unsearched:
        return
    _payload.nudge_once(ev, HOOK, "\n".join(sorted(unsearched)), (
        "This commit adds a status change or an attribution ('due to', 'classical', a citation, "
        "...) to " + ", ".join(sorted(unsearched)) + ", and no literature search is recorded "
        "since the file last changed. If the claim rests on 'is this known?', dispatch the "
        "lit-search agent first, and check any theorem number it reports yourself before citing "
        "it. See docs/discipline/firsthand-checks.md. Bypass: LIT_SEARCH_OK=1."))


if __name__ == "__main__":
    _payload.run(main, HOOK)
