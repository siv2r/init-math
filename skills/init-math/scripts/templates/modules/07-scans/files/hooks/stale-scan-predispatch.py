#!/usr/bin/env python3
"""stale-scan pre-dispatch nudge (PreToolUse, spawn).

When claim-auditor, proof-referee or red-team is dispatched AGAIN on a file that was edited
since its previous dispatch, and `bin/stale-status-scan` has not been run on that file since
the edit, refuse once. Why: a fix that changes a claim usually leaves the old phrasing in
other places in the file, and the reviewer then spends a round finding them.
Run `bin/stale-status-scan --phrase "<old phrase>" <file>` and re-dispatch, or re-issue the
same dispatch to proceed. Bypass: STALE_SCAN_OK=1 or HOOKS_QUIET=1.
Reads logs/state/stale-scan-times.json (written by bin/stale-status-scan); keeps its own
dispatch times in logs/state/stale-scan-predispatch.json. See docs/discipline/scans.md.
"""
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _payload  # noqa: E402

HOOK = "stale-scan-predispatch"
REVIEWERS = {"claim-auditor", "proof-referee", "red-team"}
PATH_RE = re.compile(r"(?<![\w/:.-])(?!https?://)[A-Za-z0-9_][A-Za-z0-9_./-]*\.(?:md|tex|txt)\b")


def _load(p: Path) -> dict:
    try:
        d = json.loads(p.read_text())
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def main(ev):
    if ev.action != "spawn" or ev.agent_type not in REVIEWERS or os.environ.get("STALE_SCAN_OK") == "1":
        return
    root = Path(ev.root).resolve()
    state = _payload.state_dir(str(root))
    disp_f = state / "stale-scan-predispatch.json"
    dispatched = _load(disp_f)
    scans = _load(state / "stale-scan-times.json")
    now, stale = time.time(), []
    for m in PATH_RE.finditer(ev.prompt):
        p = (root / m.group(0)).resolve()
        if root not in p.parents or not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        mtime = p.stat().st_mtime
        last = dispatched.get(rel)
        if last is not None and mtime > last and scans.get(rel, 0) < mtime:
            stale.append((rel, int(mtime)))
        dispatched[rel] = now
    disp_f.write_text(json.dumps(dispatched, indent=1, sort_keys=True))
    if not stale:
        return
    names = ", ".join(r for r, _ in stale)
    _payload.nudge_once(
        ev, HOOK, "|".join(f"{r}@{t}" for r, t in stale),
        f"Re-dispatching {ev.agent_type} on {names}, which changed since the last review, with no "
        "stale-status-scan since the change. A fix that changes a claim usually leaves the old "
        "wording elsewhere in the file. Run bin/stale-status-scan --phrase \"<old phrase>\" "
        f"{names} first, or re-issue to proceed. See docs/discipline/scans.md.",
    )


if __name__ == "__main__":
    _payload.run(main, HOOK)
