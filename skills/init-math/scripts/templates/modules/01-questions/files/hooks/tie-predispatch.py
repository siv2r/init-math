#!/usr/bin/env python3
"""tie-predispatch: before an agent is dispatched on a research task, check that its brief
says which research question the task moves (a `## Question tie` block).

Fires on a spawn (agent dispatch) when ALL hold:
  * the agent is a worker (exp-worker, lean-worker, worker), or a general agent whose
    brief reads like a research task (names a conjecture id, an experiments/ path, a
    `@residue`, a sweep, a driver, a proof brick, a .lean file);
  * the brief has no `Question tie` heading and no one-line `tie: Qxxx / A<n>` pointer;
  * this brief has not been nudged before (re-issuing the same dispatch proceeds).
Reviewers and search agents never trigger: a review or a search spends no research compute.
A brief that only writes up results (no computation) is exempt.

When the harness hides the brief from hooks (Codex encrypts it), the tie cannot be read,
so a worker dispatch gets a once-per-session reminder instead of a check.

Bypass: set TIE_OK=1 or HOOKS_QUIET=1 in the environment, or re-issue the identical dispatch.
Failure: fails open (the dispatch proceeds) with a warning and a logged traceback.
Explained in docs/discipline/question-ties.md.
"""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _payload  # noqa: E402

HOOK = "tie-predispatch"
WORKERS = {"exp-worker", "lean-worker", "worker"}
GENERIC = {"", "general-purpose", "general", "default", "claude"}
TASK_INTENT = re.compile(
    r"\bC\d{3}\b|experiments/[A-Za-z0-9_.-]+|@residue|bin/exp-run|\.lean\b|\bsorry\b|"
    r"\bbrick\b|\bsweep\b|\bdriver\b|\bfalsif", re.I)
HAS_TIE = re.compile(r"^#{1,6}\s*Question tie\b|\btie:\s*Q\d{3}\s*/\s*A\d+|\bQuestion tie\b",
                     re.I | re.M)
WRITE_UP = re.compile(r"\bwrite[- ]?up\b", re.I)
RUNS_COMPUTE = re.compile(r"bin/exp-run|\.lean\b|\bsweep\b|\bdriver\b", re.I)

MESSAGE = (
    "This dispatch sends a {agent} agent on a research task, but its brief has no question "
    "tie.\nWhy: every task states which research question it moves and what each outcome "
    "would change, so the work can be judged before it is spent.\nWhat to do: add a "
    "`## Question tie` block (question: Qxxx / A<n>, via, kind, at least two `if ... → ...` "
    "outcomes including a failure branch; a bridge for a transfer; or kind explore with a "
    "cap and looking-for), lint it with "
    "`bin/tie-check -` (brief on stdin), and above smoke scale have the tie-auditor agent "
    "read it. See docs/discipline/question-ties.md.\nIf this is not a research task (a scout, "
    "a refactor, a review), re-issue the same dispatch."
)

HIDDEN_MESSAGE = (
    "This harness hides a spawned agent's brief from hooks, so the question tie cannot be "
    "checked here. Before dispatching a worker on a research task, make sure its brief has a "
    "`## Question tie` block and lint it with `bin/tie-check -` (brief on stdin). See "
    "docs/discipline/question-ties.md. Reminder once per session; re-issue to proceed."
)


def is_task(agent: str, prompt: str) -> bool:
    if agent in WORKERS:
        return True
    if agent in GENERIC and TASK_INTENT.search(prompt):
        return not (WRITE_UP.search(prompt) and not RUNS_COMPUTE.search(prompt))
    return False


def main(ev):
    if ev.action != "spawn" or os.environ.get("TIE_OK") == "1":
        return
    agent = (ev.agent_type or "").strip()
    prompt = ev.prompt or ""
    if ev.prompt_hidden:
        if agent in WORKERS:
            _payload.nudge_once(ev, HOOK, "hidden|" + (ev.session_id or "no-session"), HIDDEN_MESSAGE)
        return
    if not is_task(agent, prompt) or HAS_TIE.search(prompt):
        return
    _payload.nudge_once(ev, HOOK, agent + "|" + prompt[:400], MESSAGE.format(agent=agent or "general"))


if __name__ == "__main__":
    _payload.run(main, HOOK)
