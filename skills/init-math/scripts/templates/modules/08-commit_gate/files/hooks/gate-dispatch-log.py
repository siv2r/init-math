#!/usr/bin/env python3
"""Gate dispatch log (PreToolUse, spawn). Never refuses anything.

When a reviewer agent is dispatched, record which files its brief names, and the hash of
each file's current content, in `.gates/dispatches.jsonl`:

    {"id": ..., "ts": ..., "gate": "claim-auditor", "path": "wiki/x.md", "blob": "<git blob sha1>", "via": "agent_type"}

`bin/gate-stamp` refuses to record a verdict for a (gate, file, content) that was never
dispatched, and the pre-commit check (.githooks/pre-commit) wants both. The point: a
verdict is recorded against evidence that the reviewer was actually sent the text being
committed, not on the author's word. It is a reminder, not security: anyone can append a
line by hand.

Reviewers are the keys of `[gates.verdicts]` in project.toml (default: the six review
agents). The gate is the dispatched agent's type; if the harness gives no type, the one
reviewer name the brief mentions. Paths are the existing files under the project root
that the brief names.

Codex hides a spawned agent's brief from hooks (it arrives encrypted; probe 2026-10-08), so
on Codex this script is also registered on SubagentStop and records from the reviewer's own
final reply instead: the files on its `Reviewed:` line, or, with no such line, every
project file the reply names (`"via": "report"`). The hash is then taken when the reviewer
finishes, which is what the stamp checks against. The file is union-merged across branches, so rows may repeat or be
out of order; readers de-duplicate by `id` and never rely on order.

Explained in docs/discipline/commit-gate.md. Bypass: none needed (it only records).
"""
import hashlib
import json
import re
import subprocess
import sys
import time
import tomllib
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _payload  # noqa: E402

HOOK = "gate-dispatch-log"
DEFAULT_REVIEWERS = ["claim-auditor", "proof-referee", "red-team", "cold-reader", "expositor",
                     "provenance"]
# a relative or absolute path; absolute paths outside the project are dropped below
TOKEN_RE = re.compile(r"(?<![\w/:.-])(?!https?://)[A-Za-z0-9_./][A-Za-z0-9_./-]*[A-Za-z0-9_]")


def reviewers(root: Path) -> list[str]:
    try:
        with open(root / "project.toml", "rb") as f:
            cfg = tomllib.load(f)
    except FileNotFoundError:
        return DEFAULT_REVIEWERS
    names = list((cfg.get("gates", {}).get("verdicts") or {}).keys())
    return names or DEFAULT_REVIEWERS


def blob_of(root: Path, rel: str) -> str:
    """The git blob id of the file's content (what `git hash-object` prints)."""
    try:
        r = subprocess.run(["git", "hash-object", "--", rel], cwd=root, capture_output=True,
                           text=True, timeout=20)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    data = (root / rel).read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def named_files(prompt: str, root: Path) -> list[str]:
    base = root.resolve()
    out = []
    for m in TOKEN_RE.finditer(prompt):
        tok = m.group(0).split(":")[0]
        p = (base / tok).resolve()
        if base in p.parents and p.is_file():
            rel = p.relative_to(base).as_posix()
            if not rel.startswith(".gates/") and rel not in out:
                out.append(rel)
    return out


def which_gate(ev, names: list[str]):
    if ev.agent_type:
        return (ev.agent_type, "agent_type") if ev.agent_type in names else (None, None)
    hits = [n for n in names if re.search(rf"(?<![\w-]){re.escape(n)}(?![\w-])", ev.prompt or "")]
    return (hits[0], "prompt") if len(hits) == 1 else (None, None)


REVIEWED_RE = re.compile(r"^\W*Reviewed\W*:(.*)$", re.I | re.M)


def report_files(report: str, root: Path) -> list[str]:
    """Files a reviewer's final reply says it reviewed (its `Reviewed:` line, else any)."""
    lines = REVIEWED_RE.findall(report)
    return named_files(" ".join(lines) if lines else report, root)


def main(ev):
    root = Path(ev.root)
    if ev.event == "SubagentStop":
        gate = ev.agent_type if ev.agent_type in reviewers(root) else None
        via, files = "report", (report_files(ev.report, root) if gate else [])
    elif ev.action == "spawn":
        gate, via = which_gate(ev, reviewers(root))
        files = named_files(ev.prompt or "", root) if gate else []
    else:
        return
    if not gate:
        return
    rows = []
    for rel in files:
        rows.append({"id": uuid.uuid4().hex[:16], "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                     "gate": gate, "path": rel, "blob": blob_of(root, rel), "via": via})
    if not rows:
        return
    d = root / ".gates"
    d.mkdir(exist_ok=True)
    with open(d / "dispatches.jsonl", "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True) + "\n")


if __name__ == "__main__":
    _payload.run(main, HOOK)
