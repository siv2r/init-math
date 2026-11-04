"""When a program review is overdue, ask the agent to offer the owner one.

Registered at Stop (the end of an agent turn). A program review only happens if someone
thinks of it, and inside a long run nobody does: work drifts from the owner's goals, old
questions stay active after the direction changed, and nothing steps back to notice.

Due when both hold:
  * at least N days have passed since the last review or declined offer (the last
    `## YYYY-MM-DD` heading in notes/program-reviews.md) or, before the first one, since the project's first
    commit; N is project.toml `[program_review] every_days` (default 21; 0 switches the
    reminder off);
  * something was committed since then.
It speaks at most once per calendar week while a review stays due, and never on a turn
that is itself the continuation of a stop reminder. It asks the agent to OFFER a review at
the end of its reply, not to start one: the review needs the owner present.

Bypass: HOOKS_QUIET=1, or every_days = 0. Fails open, loudly (hooks/_payload.py).
See docs/discipline/reflection-loop.md.
"""
import datetime as dt
import re
import subprocess
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _payload  # noqa: E402

HOOK = "program-review-nudge"
DEFAULT_EVERY = 21
HEADING = re.compile(r"^## (\d{4}-\d{2}-\d{2})\b", re.M)


def settings(root: str) -> tuple[int, str]:
    p = Path(root) / "project.toml"
    if not p.exists():
        return DEFAULT_EVERY, ""
    with open(p, "rb") as f:
        cfg = tomllib.load(f)
    every = int(cfg.get("program_review", {}).get("every_days", DEFAULT_EVERY))
    return every, str(cfg.get("project", {}).get("owner", "")).strip()


def git(root: str, *args: str) -> str:
    r = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, timeout=30)
    return r.stdout.strip() if r.returncode == 0 else ""


def last_review(root: str) -> str:
    p = Path(root) / "notes" / "program-reviews.md"
    dates = HEADING.findall(p.read_text(encoding="utf-8")) if p.exists() else []
    return max(dates) if dates else ""


def main(ev):
    if ev.raw.get("stop_hook_active"):
        return
    every, owner = settings(ev.root)
    if every <= 0:
        return
    last = last_review(ev.root)
    since = last or git(ev.root, "log", "--reverse", "--format=%cs").split("\n")[0]
    if not since:
        return  # not a git repository yet, or no commits
    today = dt.date.today()
    if (today - dt.date.fromisoformat(since)).days < every:
        return
    if not git(ev.root, "log", "-1", "--format=%h", f"--since={since}T23:59:59"):
        return  # nothing happened since: no review to offer
    year, week, _ = today.isocalendar()
    who = owner or "the owner"
    when = (f"The last one was on {last}." if last else
            f"There has been none since the project started on {since}.")
    _payload.stop_continue(
        ev, HOOK, f"{since}:{year}-W{week:02d}",
        f"A program review is due. {when} At the end of your reply, offer {who} one in a "
        "sentence (the program-review skill: is the work, taken together, moving toward their "
        "goals in notes/program-goals.md, and do the active questions still match the "
        "direction?). Do not start it unless they say yes; it needs them present. If they "
        "decline, append `## <today> — offer declined` to notes/program-reviews.md, so the "
        "next offer waits a full interval. This reminder will not repeat this week.")


if __name__ == "__main__":
    _payload.run(main, HOOK)
