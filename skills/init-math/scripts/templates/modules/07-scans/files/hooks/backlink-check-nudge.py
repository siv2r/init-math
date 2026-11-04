#!/usr/bin/env python3
"""backlink-check nudge (PreToolUse, shell): at `git commit`, catch one-way literature links.

Runs `bin/backlink-check`; if a known result settles or suggests a conjecture whose file
never mentions it, refuses once per distinct set. Otherwise an agent reading the
conjecture never learns the literature already bears on it. Re-issuing proceeds.
Bypass: BACKLINK_CHECK_OK=1 or HOOKS_QUIET=1. See docs/discipline/scans.md.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _payload  # noqa: E402

HOOK = "backlink-check-nudge"
COMMIT = re.compile(r"\bgit\b[\s\S]*?\bcommit(?![-\w])")


def main(ev):
    if ev.action != "shell" or not COMMIT.search(ev.command) or os.environ.get("BACKLINK_CHECK_OK") == "1":
        return
    script = Path(ev.root) / "bin" / "backlink-check"
    if not script.is_file():
        return
    r = subprocess.run([sys.executable, str(script), "--porcelain"], capture_output=True, text=True,
                       timeout=60, cwd=ev.root)
    seams = [ln.replace("\t", " ") for ln in r.stdout.splitlines() if ln.count("\t") >= 2]
    if r.returncode != 1 or not seams:
        return
    _payload.nudge_once(
        ev, HOOK, "|".join(sorted(seams)),
        "One-way links from known results to conjectures: " + "; ".join(seams[:8])
        + ". Add a line to each conjecture's evidence naming the known result, so a reader "
        "of the conjecture finds it. See docs/discipline/scans.md.",
    )


if __name__ == "__main__":
    _payload.run(main, HOOK)
