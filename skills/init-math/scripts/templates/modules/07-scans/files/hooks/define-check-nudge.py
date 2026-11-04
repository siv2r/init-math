#!/usr/bin/env python3
"""define-check nudge (PreToolUse, shell): at `git commit`, catch private codes in shared indexes.

Shared indexes (wiki/_index.md, wiki/*/_index.md, experiments/_index.md, and the _index.md
of a store moved by [questions] dir / [conjectures] dir in project.toml) are read by every
agent and by the owner. A finding code invented inside one experiment (F12, SB2) means
nothing there. This runs `bin/define-check --codes-only` on them and refuses once per
distinct set of undefined codes. Re-issuing the commit proceeds.
Bypass: DEFINE_CHECK_OK=1 or HOOKS_QUIET=1. See docs/discipline/scans.md.
"""
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _payload  # noqa: E402

HOOK = "define-check-nudge"
COMMIT = re.compile(r"\bgit\b[\s\S]*?\bcommit(?![-\w])")


def shared_docs(root: Path) -> list[Path]:
    out = [root / "wiki" / "_index.md", root / "experiments" / "_index.md"]
    out += sorted((root / "wiki").glob("*/_index.md"))
    try:
        cfg = tomllib.loads((root / "project.toml").read_text(encoding="utf-8"))
    except FileNotFoundError:
        cfg = {}
    for store in ("questions", "conjectures"):
        rel = cfg.get(store, {}).get("dir")
        if rel and root / rel / "_index.md" not in out:
            out.append(root / rel / "_index.md")
    return [p for p in out if p.is_file()]


def main(ev):
    if ev.action != "shell" or not COMMIT.search(ev.command) or os.environ.get("DEFINE_CHECK_OK") == "1":
        return
    root = Path(ev.root)
    script = root / "bin" / "define-check"
    docs = shared_docs(root)
    if not script.is_file() or not docs:
        return
    r = subprocess.run([sys.executable, str(script), "--codes-only", "--porcelain", *map(str, docs)],
                       capture_output=True, text=True, timeout=60, cwd=root)
    hits = []
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) == 4:
            hits.append(f"{Path(parts[0]).relative_to(root).as_posix()}:{parts[1]} {parts[3]}")
    if not hits:
        return
    _payload.nudge_once(
        ev, HOOK, "|".join(sorted(hits)),
        "Shared index files use codes with no definition: " + "; ".join(hits[:12])
        + ". Codes invented inside one experiment mean nothing to other readers. Replace each "
        "with plain words, define it where it appears, or add a GLOSSARY.md entry. "
        "See docs/discipline/scans.md.",
    )


if __name__ == "__main__":
    _payload.run(main, HOOK)
