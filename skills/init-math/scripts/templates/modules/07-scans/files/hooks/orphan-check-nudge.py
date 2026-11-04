#!/usr/bin/env python3
"""orphan-check nudge (PreToolUse, shell): at `git commit`, catch unindexed artifacts.

Runs `bin/orphan-check`; if any question, conjecture, known result, experiment or work folder is not
named in its store's _index.md, refuses once per distinct orphan set. An unindexed artifact
is invisible to the next agent. Re-issuing the commit proceeds.
Bypass: ORPHAN_CHECK_OK=1 or HOOKS_QUIET=1. See docs/discipline/scans.md.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _payload  # noqa: E402

HOOK = "orphan-check-nudge"
COMMIT = re.compile(r"\bgit\b[\s\S]*?\bcommit(?![-\w])")


def main(ev):
    if ev.action != "shell" or not COMMIT.search(ev.command) or os.environ.get("ORPHAN_CHECK_OK") == "1":
        return
    script = Path(ev.root) / "bin" / "orphan-check"
    if not script.is_file():
        return
    r = subprocess.run([sys.executable, str(script), "--porcelain"], capture_output=True, text=True,
                       timeout=60, cwd=ev.root)
    orphans = [ln.split("\t", 1)[1] for ln in r.stdout.splitlines() if "\t" in ln]
    if r.returncode != 1 or not orphans:
        return
    _payload.nudge_once(
        ev, HOOK, "|".join(sorted(orphans)),
        "These artifacts are not named in their _index.md: " + ", ".join(orphans[:12])
        + ". An unindexed artifact is invisible to the next agent. Add the index row in this "
        "commit, or list the slug in .orphanignore if it is intentional. "
        "See docs/discipline/scans.md.",
    )


if __name__ == "__main__":
    _payload.run(main, HOOK)
