"""Put queued workflow proposals in front of the owner instead of leaving them in a file.

Registered at Stop (the end of an agent turn). Reflection passes and retrospectives queue
the changes that need the owner's yes in logs/proposals.jsonl (`bin/journal --propose`).
Written there and mentioned in passing, they are never decided: the owner answers
"continue", the run goes on, and the queue only grows.

  * A pending proposal not yet put to the owner (`bin/journal --shown` records that it
    was): ask the agent to end its reply with the pending proposals as a numbered list,
    each with its recommendation, and to run `bin/journal --shown`. Once per set of
    proposals.
  * Proposals put to the owner but still undecided: one line of reminder, once per
    session.
Never on a turn that is itself the continuation of a stop reminder.

Bypass: HOOKS_QUIET=1. Fails open, loudly (hooks/_payload.py).
See docs/discipline/reflection-loop.md.
"""
import json
import os
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _payload  # noqa: E402

HOOK = "proposals-nudge"


def pending(root: str) -> list[dict]:
    p = Path(root) / "logs" / "proposals.jsonl"
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict):
            rows.append(rec)
    decided = {r.get("of") for r in rows if r.get("kind") == "decision"}
    out, seen = [], set()
    for r in rows:
        if r.get("kind") == "proposal" and r.get("id") not in decided and r.get("id") not in seen:
            seen.add(r.get("id"))
            out.append(r)
    return out


def owner(root: str) -> str:
    p = Path(root) / "project.toml"
    if not p.exists():
        return "the owner"
    with open(p, "rb") as f:
        return str(tomllib.load(f).get("project", {}).get("owner", "")).strip() or "the owner"


def main(ev):
    if os.environ.get("HOOKS_QUIET") == "1" or ev.raw.get("stop_hook_active"):
        return
    pend = pending(ev.root)
    if not pend:
        return
    sf = Path(ev.root) / "logs" / "state" / "proposals.shown"
    shown = set(sf.read_text().split()) if sf.exists() else set()
    new = [r for r in pend if r.get("id") not in shown]
    who = owner(ev.root)
    key = "new:" + ",".join(sorted(str(r.get("id")) for r in new))
    raised_f = _payload.state_dir(ev.root) / f"{HOOK}.raised"
    raised = set(raised_f.read_text().split()) if raised_f.exists() else set()
    if new and key not in raised:
        with open(raised_f, "a") as f:
            f.write(key + "\n")
        listing = "; ".join(f"{r.get('id')} ({r.get('source', '?')}): {r.get('text', '')}"
                            for r in pend)
        _payload.stop_continue(
            ev, HOOK, key,
            f"{len(new)} workflow proposal(s) wait for {who}'s decision and have not been put to "
            f"them yet. Pending now: {listing}. End your reply with ALL pending proposals as a "
            "numbered list, in plain words: what would change, what it costs, and your "
            f"recommendation; ask which to apply. Then run `bin/journal --shown`. A 'continue' "
            f"from {who} decides nothing: keep them pending. On a yes or no, run "
            "`bin/journal --decide <id> yes|no` (and on a yes, apply the change).")
    _payload.stop_continue(
        ev, HOOK, f"remind:{ev.session_id or 'none'}",
        f"{len(pend)} workflow proposal(s) still wait for {who}'s decision "
        "(`bin/journal --pending`). Mention that in one line at the end of your reply, and "
        "offer to go through them.")


if __name__ == "__main__":
    _payload.run(main, HOOK)
