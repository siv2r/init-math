"""Give the main session the coordinator's rules (COORDINATOR.md) at its start.

Event: SessionStart (Claude Code), every source: startup, resume, clear and compact, so the
rules come back after the conversation is summarized. Registered PARTS times with
`--part 1` ... `--part N`: Claude Code keeps a hook's added context only up to about 10,000
characters and shows a 2 KB preview past that (probe 2026-10-31: a 12.6 KB file arrived as a
preview; two hooks of 9.9 and 9 KB both arrived whole). So the file is cut at `## ` headings
into parts of at most LIMIT characters, and part k prints the k-th; if the file needs more
parts than are registered, the last one says where the rest starts.

AGENTS.md holds the rules every agent follows, and every agent gets it (CLAUDE.md imports
it, and a subagent gets CLAUDE.md). The coordinator's own rules (what to dispatch, when to
commit, when to stop, what is the owner's) live in COORDINATOR.md, which no dispatched agent
needs. A SessionStart hook's added context reaches the main session only (probe 2026-10-31:
a subagent saw AGENTS.md but not this text), so this hook prints COORDINATOR.md there.

Not a nudge: HOOKS_QUIET=1 does not silence it, since without it the coordinator would work
without its rules. If COORDINATOR.md is missing, it says so instead. Fails open, loudly
(hooks/_payload.py); AGENTS.md then tells the coordinator to read the file itself.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _payload  # noqa: E402

HOOK = "coordinator-context"
FILE = "COORDINATOR.md"
PARTS = 3      # registrations in core/module.toml; bin/selftest checks the file fits
LIMIT = 9000   # characters per part, header included, under the harness's ~10,000


def parts(text: str, limit: int = LIMIT) -> list[str]:
    """The file cut at `## ` headings into pieces of at most `limit` characters (a single
    section longer than that is cut at a line break)."""
    secs, cur = [], []
    for line in text.splitlines(keepends=True):
        if line.startswith("## ") and cur:
            secs.append("".join(cur))
            cur = []
        cur.append(line)
    if cur:
        secs.append("".join(cur))
    out, buf = [], ""
    for s in secs:
        while len(s) > limit:
            cut = s.rfind("\n", 0, limit) + 1 or limit
            if buf:
                out.append(buf)
                buf = ""
            out.append(s[:cut])
            s = s[cut:]
        if len(buf) + len(s) > limit:
            out.append(buf)
            buf = ""
        buf += s
    if buf:
        out.append(buf)
    return out


def context(root: str, k: int) -> str | None:
    try:
        text = (Path(root) / FILE).read_text(encoding="utf-8")
    except OSError:
        return (f"[{HOOK}] {FILE} is missing from {root}. It holds the coordinator's rules; tell "
                "the owner, and follow AGENTS.md meanwhile.") if k == 1 else None
    ps = parts(text, LIMIT - 200)
    if k > len(ps):
        return None
    head = (f"[{HOOK}] The coordinator's rules, from {FILE}, part {k} of {len(ps)} (you are the "
            "coordinator; no dispatched agent sees this):\n\n")
    tail = ""
    if k == PARTS and len(ps) > PARTS:
        first = ps[PARTS].splitlines()[0] if ps[PARTS].strip() else ""
        tail = (f"\n\n[{HOOK}] {FILE} continues past what a hook can show, from \"{first}\": "
                f"read it from there now.")
    return head + ps[k - 1] + tail


def part_arg(argv: list[str]) -> int:
    for i, a in enumerate(argv):
        if a == "--part" and i + 1 < len(argv):
            return int(argv[i + 1])
    return 1


def main(ev):
    if ev.agent_type:
        return  # a subagent's session: the coordinator's rules are not its own
    text = context(ev.root, part_arg(sys.argv))
    if text:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                 "additionalContext": text}}))


if __name__ == "__main__":
    _payload.run(main, HOOK)
