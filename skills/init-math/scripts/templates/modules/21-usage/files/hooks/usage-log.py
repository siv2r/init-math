"""usage-log: copy token COUNTS from the harness's session record into logs/usage.jsonl.

Runs at Stop, SubagentStop and (Claude) SessionEnd. It reads only the part of each
transcript written since its last run (byte offsets in logs/state/usage-offsets.json),
counts each API response once, and appends a few aggregated rows: model, agent role and
type, token counts. It never copies message text. It never blocks or nudges: it always
exits 0, and on a problem it warns on stderr (an unreadable format also adds one
`usage-format-unknown` row to logs/failures.jsonl). See docs/discipline/usage.md.

Off switch: USAGE_LOG_OFF=1 in the environment (HOOKS_QUIET does not apply: this hook is
silent anyway), or remove the module.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _payload  # noqa: E402
import _usage  # noqa: E402

HOOK = "usage-log"


def main(ev):
    if os.environ.get("USAGE_LOG_OFF") == "1":
        return
    root = Path(ev.root)
    items: list[tuple[Path, str]] = []
    tp = Path(ev.transcript_path) if ev.transcript_path else None
    atp = ev.raw.get("agent_transcript_path")
    if atp:  # SubagentStop: the subagent's own transcript, with its type from the payload
        items.append((Path(str(atp)), ev.agent_type))
    if tp:
        items.append((tp, ""))
        if _usage.detect_format(tp) == "claude":  # Claude keeps subagents beside the session
            items += [(p, "") for p in _usage.claude_subagent_files(tp)]
    if not items:
        return
    _, problems = _usage.collect(root, items, hint_model=str(ev.raw.get("model") or ""))
    for pr in problems:
        print(f"WARNING: [{HOOK}] could not read token counts: {pr}. The harness's transcript "
              f"format may have changed; usage for it is not recorded. See "
              f"docs/discipline/usage.md.", file=sys.stderr)
        _payload.log(str(root), "failures", {"signature": "usage-format-unknown",
                                             "command": HOOK, "excerpt": pr[:200],
                                             "id": os.urandom(4).hex()})


if __name__ == "__main__":
    _payload.run(main, HOOK)
