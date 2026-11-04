"""Every few turns, ask the agent whether anything went wrong that it has not logged.

Registered at Stop (the end of an agent turn). Friction the agent catches itself (a wrong
launch, a redundant step, a convention that chafed) tends to go unrecorded until the
owner asks; this is the cheap prompt that makes the friction skill get used.

Low noise by design:
  * it counts stops and speaks only on every Nth (project.toml `[reflect]
    friction_nudge_every`, default 5; environment FRICTION_NUDGE_EVERY overrides;
    0 switches it off);
  * if a friction row was logged since the last stop, the count restarts and it stays
    quiet (you already logged);
  * it never fires on a turn that is itself the continuation of a stop nudge.

Bypass: HOOKS_QUIET=1 or FRICTION_NUDGE_EVERY=0. Fails open, loudly (hooks/_payload.py).
See docs/discipline/reflection-loop.md.
"""
import json
import os
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _payload  # noqa: E402

HOOK = "proactive-friction-nudge"
DEFAULT_EVERY = 5


def period(root: str) -> int:
    env = os.environ.get("FRICTION_NUDGE_EVERY")
    if env is not None and env.strip():
        return int(env)
    p = Path(root) / "project.toml"
    if p.exists():
        with open(p, "rb") as f:
            return int(tomllib.load(f).get("reflect", {}).get("friction_nudge_every", DEFAULT_EVERY))
    return DEFAULT_EVERY


def friction_rows(root: str) -> int:
    p = Path(root) / "logs" / "friction.jsonl"
    if not p.exists():
        return 0
    return sum(1 for line in p.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip())


def main(ev):
    if os.environ.get("HOOKS_QUIET") == "1" or ev.raw.get("stop_hook_active"):
        return
    every = period(ev.root)
    if every <= 0:
        return
    sf = _payload.state_dir(ev.root) / f"{HOOK}.json"
    st = json.loads(sf.read_text()) if sf.exists() else {}
    rows = friction_rows(ev.root)
    if rows != st.get("friction_rows", 0):
        st.update(friction_rows=rows, stops=0)  # friction was logged: nothing to remind about
        sf.write_text(json.dumps(st) + "\n")
        return
    st["stops"] = int(st.get("stops", 0)) + 1
    if st["stops"] < every:
        sf.write_text(json.dumps(st) + "\n")
        return
    st["stops"] = 0
    st["fired"] = int(st.get("fired", 0)) + 1
    sf.write_text(json.dumps(st) + "\n")
    _payload.stop_continue(
        ev, HOOK, f"{ev.session_id}:{st['fired']}",
        "Before you finish: did anything in this stretch of work go wrong or waste effort "
        "(a failed or repeated step, a wrong assumption, a convention that got in the way, "
        "a correction from the owner)? If so, log it now with the friction skill, one line, "
        "so the next reflection pass can see it. If nothing rises to that, just stop again; "
        "this reminder will not repeat for this stop. See docs/discipline/reflection-loop.md.")


if __name__ == "__main__":
    _payload.run(main, HOOK)
