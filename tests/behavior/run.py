#!/usr/bin/env python3
"""Run the behavioral scenarios against a headless agent in freshly generated projects.

    python3 tests/behavior/run.py --dry-run                 set up every scenario, call no model
    python3 tests/behavior/run.py --harness claude --runs 3 [--scenario ID …] [--model M]
    python3 tests/behavior/run.py --rescore DIR             re-score saved runs with the current
                                                            scorers (no model calls)

Each run: create a project from a fixture with init_project.py into
<out>/<scenario>/run<k>/project, apply the scenario's setup, send its prompt(s) to the
harness's headless mode, save the transcript, score from evidence on disk. Results go to
<out>/results.json and a table on stdout (pass rate per scenario, nudge counts).

This spends model tokens; it is NOT part of `bin/test`. The default output directory is
a fresh timestamped directory under the system temp dir, so runs never clobber each other.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
INIT = ROOT / "skills/init-math/scripts/init_project.py"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "skills/init-math/scripts"))
sys.dont_write_bytecode = True
import scenarios as S  # noqa: E402

# The Codex behavior fixture is the Codex theory fixture with every module on (experiments
# too, for record-supported-real), plus a seed conjecture, a research command and a failure
# signature, so every scenario has something to act on.
FIXTURE = {"claude": "answers-claude-lean.json", "codex": "answers-codex-behavior.json"}
# The agent under test must see the generated project, not whatever session launched us.
ENV = {k: v for k, v in os.environ.items()
       if not (k.startswith("CLAUDE") or k.startswith("CODEX"))} | {"PYTHONDONTWRITEBYTECODE": "1"}


TEMPLATES: str | None = None  # --templates override (testing the harness itself)
FIXTURES = ROOT / "tests/fixtures"  # --from-commit reads that commit's fixtures


def create_project(fixture: str, dest: Path, selftest: bool = True) -> dict:
    cmd = [sys.executable, str(INIT), "--answers", str(FIXTURES / fixture), "--out", str(dest)]
    if TEMPLATES:
        cmd += ["--templates", TEMPLATES]
    r = subprocess.run(cmd + ([] if selftest else ["--no-selftest"]), capture_output=True, text=True,
                       env=ENV, timeout=600)
    if r.returncode != 0:
        raise RuntimeError(f"init failed for {dest}:\n{r.stdout}{r.stderr}")
    return json.loads((dest / "docs/init-report.json").read_text())


def agent_cmd(harness: str, prompt: str, model: str | None, resume: bool,
              project: Path | None = None) -> list[str]:
    if harness == "claude":
        cmd = ["claude", "-p", prompt, "--output-format", "stream-json", "--verbose",
               "--permission-mode", "acceptEdits",
               "--allowedTools", "Bash", "Read", "Edit", "Write", "Glob", "Grep", "Agent", "Skill",
               "WebSearch", "WebFetch",
               # The owner's advisor setting would hand the agent a second, stronger model.
               "--settings", '{"advisorModel": ""}']
        if resume:
            cmd.append("--continue")
        if model:
            cmd += ["--model", model]
        return cmd
    # Verified on Codex CLI 0.161.0 (the harness probe). Project hooks are untrusted in a fresh
    # project and `codex exec` skips untrusted hooks, so the run bypasses the trust check.
    # No `-s`: it would replace the project's sandbox profile (.codex/config.toml, which
    # makes .git writable so agents can commit). The run trusts the folder for this call
    # only, as the owner does when Codex first asks, so Codex reads that profile. The
    # override is an inline table: in a dotted `-c projects."<path>".…` key Codex keeps the
    # quotes, the key never matches, and the run falls back to a read-only sandbox.
    cmd = ["codex", "exec", "--json", "--dangerously-bypass-hook-trust"]
    if project is not None:
        cmd += ["-c", f'projects={{{json.dumps(str(project))}={{trust_level="trusted"}}}}']
    if model:
        cmd += ["-m", model]
    if EFFORT:
        cmd += ["-c", f"model_reasoning_effort={EFFORT}"]
    if resume:
        cmd += ["resume", "--last"]
    return cmd + [prompt]


EFFORT: str | None = None  # --effort (Codex reasoning effort)


def _codex_rollouts(thread_ids: list[str]) -> list[Path]:
    root = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "sessions"
    out = []
    for tid in thread_ids:
        out += sorted(root.rglob(f"rollout-*-{tid}.jsonl"))
    return out


_JS_CMD = re.compile(r"tools\.exec_command\(\{\s*\"?cmd\"?\s*:\s*(\"(?:[^\"\\]|\\.)*\")")
_JS_ERR = re.compile(r"\b(blocked|denied|refus\w*)\b|exit (code|status):? *[1-9]|Script (failed|error)", re.I)


def _is_error(res: str) -> bool:
    """A command's exit code when Codex reports one; else a blocked/failed script."""
    m = re.search(r'\\?"exit_code\\?"\s*:\s*(-?\d+)', res)
    if m:
        return int(m.group(1)) != 0
    return bool(_JS_ERR.search(res))


def codex_events(stdout_events: list[dict]) -> list[dict]:
    """Claude-shaped tool_use/tool_result/result events from the Codex session rollouts.

    `codex exec --json` does not report subagent spawns, so the scorers read the rollout
    file (`~/.codex/sessions/**/rollout-*-<thread id>.jsonl`), which has every call. Shell
    commands and patches arrive wrapped in a JavaScript `exec` call; the command is pulled
    out of `tools.exec_command({cmd: …})` when present, else the script text is kept.
    """
    tids = list(dict.fromkeys(e["thread_id"] for e in stdout_events if e.get("type") == "thread.started"))
    uses, results, last_msg = [], {}, ""
    for f in _codex_rollouts(tids):
        for line in f.read_text().splitlines():
            try:
                p = json.loads(line).get("payload") or {}
            except json.JSONDecodeError:
                continue
            t, cid = p.get("type"), p.get("call_id")
            if t == "function_call":
                try:
                    args = json.loads(p.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {"raw": p.get("arguments")}
                name = p.get("name", "")
                if name == "spawn_agent":
                    uses.append((cid, "Agent", {"subagent_type": args.get("agent_type", ""),
                                                "description": args.get("task_name", ""),
                                                "prompt": args.get("message", "")}))
                elif name in ("exec_command", "shell"):
                    cmd = args.get("cmd") or args.get("command")
                    uses.append((cid, "Bash", {"command": " ".join(cmd) if isinstance(cmd, list) else str(cmd)}))
                else:
                    uses.append((cid, name, args))
            elif t == "custom_tool_call":
                src = p.get("input") or ""
                if p.get("name") == "apply_patch" or "tools.apply_patch(" in src:
                    uses.append((cid, "Edit", {"patch": src}))
                else:
                    # One script may run several commands; each becomes its own call
                    # (they share the script's combined output).
                    cmds = [json.loads(m.group(1)) for m in _JS_CMD.finditer(src)] or [src]
                    for cmd in cmds:
                        uses.append((cid, "Bash", {"command": cmd, "script": src}))
            elif t in ("function_call_output", "custom_tool_call_output"):
                o = p.get("output")
                results[cid] = o if isinstance(o, str) else json.dumps(o)
            elif t == "agent_message" or (t == "message" and p.get("role") == "assistant"):
                c = p.get("content") or p.get("text") or ""
                text = c if isinstance(c, str) else " ".join(x.get("text", "") for x in c if isinstance(x, dict))
                if text.strip():
                    last_msg = text
    blocks = []
    for k, (cid, name, inp) in enumerate(uses):
        res, uid = results.get(cid, ""), f"{cid}#{k}"
        blocks.append({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": uid, "name": name, "input": inp}]}})
        blocks.append({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": uid, "content": res, "is_error": _is_error(res)}]}})
    final = next((e["item"].get("text", "") for e in reversed(stdout_events)
                  if e.get("type") == "item.completed" and (e.get("item") or {}).get("type") == "agent_message"),
                 last_msg)
    return blocks + [{"type": "result", "result": final}]


def _parse(stdout: str) -> list[dict]:
    out = []
    for line in stdout.splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out


def run_agent(harness: str, project: Path, prompts: list[str], model: str | None,
              timeout: int) -> tuple[list[dict], str]:
    transcript: list[dict] = []
    err = ""
    for i, prompt in enumerate(prompts):
        try:
            # stdin closed: `codex exec` otherwise waits for more input on an open pipe.
            r = subprocess.run(agent_cmd(harness, prompt, model, resume=i > 0, project=project),
                               cwd=project,
                               capture_output=True, text=True, timeout=timeout, env=ENV,
                               stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired as e:
            # Keep what streamed before the kill: the score should see the partial transcript.
            partial = e.stdout.decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
            transcript += _parse(partial)
            err += f"TIMEOUT: prompt {i + 1} timed out after {timeout}s\n"
            break
        transcript += _parse(r.stdout)
        if r.returncode != 0:
            err += f"prompt {i + 1}: exit {r.returncode}: {r.stderr[-2000:]}\n"
    if harness == "codex":
        transcript += codex_events(transcript)
    return transcript, err


def nudge_hooks(proj: Path) -> list[str]:
    return [n.get("hook", "?") for n in S.nudges(proj)]


def table(chosen, results) -> None:
    print(f"\n{'scenario':<20} pass/runs  nudges(mean)  notes")
    for sc in chosen:
        rows = [r for r in results if r["scenario"] == sc.id]
        scored = [r for r in rows if r["passed"] is not None]
        npass = sum(1 for r in scored if r["passed"])
        mean_n = (sum(r.get("nudges", 0) for r in scored) / len(scored)) if scored else 0
        print(f"{sc.id:<20} {npass}/{len(scored):<8} {mean_n:>6.1f}        {rows[0]['note'][:60] if rows else ''}")


def rescore(out: Path, chosen) -> int:
    results = []
    for sc in chosen:
        for run in sorted((out / sc.id).glob("run*")):
            proj, tf = run / "project", run / "transcript.jsonl"
            if not tf.exists():
                continue
            tr = [json.loads(l) for l in tf.read_text().splitlines() if l.strip()]
            try:
                passed, note = sc.score(proj, tr)
            except Exception as e:
                passed, note = None, f"scorer error: {e!r}"
            results.append({"scenario": sc.id, "run": int(run.name[3:]), "project": str(proj),
                            "passed": passed, "note": note, "nudges": len(S.nudges(proj)),
                            "nudge_hooks": nudge_hooks(proj)})
            print(f"{sc.id} {run.name}: {passed} {note}", flush=True)
    (out / "rescored.json").write_text(json.dumps(results, indent=2) + "\n")
    table(chosen, results)
    print(f"\nresults: {out / 'rescored.json'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--harness", choices=("claude", "codex"), default="claude")
    ap.add_argument("--fixture", help="answers fixture (default: per harness)")
    ap.add_argument("--scenario", nargs="*", help="scenario ids (default: all)")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--model")
    ap.add_argument("--effort", help="Codex reasoning effort (low|medium|high)")
    ap.add_argument("--timeout", type=int, default=900, help="seconds per prompt")
    ap.add_argument("--out", help="output directory (default: a fresh temp dir)")
    ap.add_argument("--dry-run", action="store_true", help="set up only; no model calls")
    ap.add_argument("--rescore", metavar="DIR", help="re-score the saved runs in DIR; no model calls")
    ap.add_argument("--templates", help=argparse.SUPPRESS)
    ap.add_argument("--from-commit", metavar="REV",
                    help="generate the projects with init-math as it was at REV (a git worktree "
                         "under the output directory); scenarios and scorers stay current")
    a = ap.parse_args(argv)
    global TEMPLATES, EFFORT, INIT, FIXTURES
    TEMPLATES, EFFORT = a.templates, a.effort

    chosen = [s for s in S.SCENARIOS if not a.scenario or s.id in a.scenario]
    unknown = set(a.scenario or []) - {s.id for s in S.SCENARIOS}
    if unknown:
        ap.error(f"unknown scenario(s): {sorted(unknown)}")
    if a.rescore:
        return rescore(Path(a.rescore), chosen)
    if not a.dry_run and not shutil.which(a.harness):
        print(f"`{a.harness}` is not on PATH", file=sys.stderr)
        return 2
    out = Path(a.out) if a.out else Path(tempfile.mkdtemp(prefix=f"init-math-behavior-{time.strftime('%Y%m%d-%H%M%S')}-"))
    out.mkdir(parents=True, exist_ok=True)
    if a.from_commit:
        wt = out / f"init-math-at-{a.from_commit}"
        if not wt.exists():
            subprocess.run(["git", "worktree", "add", "--detach", "-q", str(wt), a.from_commit],
                           cwd=ROOT, check=True)
        INIT, FIXTURES = wt / INIT.relative_to(ROOT), wt / "tests/fixtures"
    elif not a.templates:
        # Render every run from a snapshot taken now: editing the templates or the renderer
        # while a batch runs must not change the projects of its later runs.
        snap = out / "init-math-snapshot"
        if not snap.exists():
            shutil.copytree(INIT.parent, snap, ignore=shutil.ignore_patterns("__pycache__"))
        INIT = snap / INIT.name
    fixture = a.fixture or FIXTURE[a.harness]
    runs = 1 if a.dry_run else a.runs
    results = []
    for sc in chosen:
        for k in range(1, runs + 1):
            proj = out / sc.id / f"run{k}" / "project"
            report = create_project(fixture, proj, selftest=not a.dry_run)
            off = [m for m in sc.needs if m not in report["modules_on"]]
            row = {"scenario": sc.id, "run": k, "project": str(proj)}
            if off:
                results.append({**row, "passed": None, "note": f"skipped: modules off {off}"})
                continue
            sc.setup(proj)
            if a.dry_run:
                results.append({**row, "passed": None, "note": "dry run: set up OK"})
                continue
            t0 = time.time()
            tr, err = run_agent(a.harness, proj, sc.prompts, a.model, a.timeout)
            (proj.parent / "transcript.jsonl").write_text("".join(json.dumps(e) + "\n" for e in tr))
            try:
                passed, note = sc.score(proj, tr)
            except Exception as e:  # a scorer bug is a harness failure, not an agent failure
                passed, note = None, f"scorer error: {e!r}"
            results.append({**row, "passed": passed, "note": note + (f" | {err.strip()}" if err else ""),
                            "nudges": len(S.nudges(proj)), "nudge_hooks": nudge_hooks(proj),
                            "seconds": round(time.time() - t0)})
            print(f"{sc.id} run{k}: {passed} {note}" + (f" | {err.strip()[:200]}" if err else ""), flush=True)

    (out / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    table(chosen, results)
    print(f"\nresults: {out / 'results.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
