#!/usr/bin/env python3
"""init-math: create a research project from an answers file.

    python3 init_project.py --list-modules [--json]     the module menu for the interview
    python3 init_project.py --check-answers A.json      validate; show which modules end up on
    python3 init_project.py --check-target DIR          refuse a non-empty / unwritable target,
                                                        or one on the Windows drive under WSL
    python3 init_project.py --answers A.json --out DIR  create the project (DIR new or empty)
    python3 init_project.py --preflight                 check python3 / git before interviewing

Creating a project = preflight, render, `git init`, initial commit, `bin/setup-hooks`
(when the commit gate is on) and `bin/selftest`, then print the owner's next steps.
The initial commit is made BEFORE the commit gate is switched on: the seeds are questions
(proposed, except the one the owner chose to start on) and open conjectures, which the gate
does not cover anyway.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.dont_write_bytecode = True

MIN_PY = (3, 11)
TEMPLATES = None  # override with --templates (tests)
WINDOWS_DRIVE = re.compile(r"^/mnt/[a-zA-Z](/|$)")


def on_wsl() -> bool:
    """True inside WSL, the Linux system built into Windows. INIT_MATH_WSL=1/0 overrides
    (tests)."""
    if os.environ.get("INIT_MATH_WSL") in ("0", "1"):
        return os.environ["INIT_MATH_WSL"] == "1"
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except OSError:
        return False


def preflight(need_git: bool = True) -> list[str]:
    """Problems that would stop the generated project working. Empty list = fine."""
    problems = []
    if sys.version_info < MIN_PY:
        problems.append(f"this interpreter is Python {sys.version.split()[0]}; init-math needs >= 3.11")
    # Hooks and scripts in the project run `python3` from PATH, which may differ from us.
    py = shutil.which("python3")
    if not py:
        problems.append("no `python3` on PATH (the project's hooks and scripts run `python3`)")
    else:
        r = subprocess.run([py, "-c", "import sys; print(sys.version_info >= (3, 11))"],
                           capture_output=True, text=True)
        if r.stdout.strip() != "True":
            problems.append(f"`python3` on PATH ({py}) is older than 3.11; the project's hooks "
                            "need 3.11+ (install a newer Python and put it first on PATH)")
    if need_git and not shutil.which("git"):
        problems.append("git is not installed")
    return problems


def _templates() -> Path:
    from renderer import render
    return Path(TEMPLATES) if TEMPLATES else render.TEMPLATES_DIR


def list_modules(as_json: bool) -> int:
    from renderer import render
    mods = render.load_modules(_templates())
    built = {m.id for m in mods}
    rows = [{
        "id": m.id, "number": m.number, "title": m.title, "group": m.group,
        "default": "always on" if m.core else {"included": "on", "opt-in": "off",
                                               "deferred": "not available"}[m.status],
        "depends": m.depends, "off_in_presets": m.off_in_presets, "requires": m.requires,
        "summary": m.summary,
    } for m in sorted(mods, key=lambda m: m.number) if m.id != "core"]
    later = [i for i in render.CATALOG if i not in built and i != "core"]
    if as_json:
        print(json.dumps({"modules": rows, "not_built": later}, indent=2))
        return 0
    print("# Module ids below are what `modules.enable` / `modules.disable` take "
          "(e.g. \"lean\", \"experiments\"); `modules.preset` takes a preset name such as "
          "\"theory-only\".")
    print("# Default column: \"always on\" = core, cannot be switched off; \"on\" = on unless the "
          "person switches it off; \"off\" = only if they switch it on. Say which is which when "
          "presenting the menu.")
    for r in rows:
        extra = []
        if r["depends"]:
            extra.append("needs " + ", ".join(r["depends"]))
        if r["off_in_presets"]:
            extra.append("off in " + ", ".join(r["off_in_presets"]))
        if r["requires"]:
            extra.append("requires " + ", ".join(f"{k}={v}" for k, v in r["requires"].items()))
        tail = f"  [{'; '.join(extra)}]" if extra else ""
        print(f"{r['group']} {r['number']:>2} {r['id']:<15} {r['default']:<10} {r['summary']}{tail}")
    if later:
        print("\nnot available in this version: " + ", ".join(later))
    return 0


def target_problem(out: Path) -> str | None:
    """Why `out` cannot be the new project directory, or None. Same wording as create's refusal."""
    out = Path(out)
    if on_wsl() and WINDOWS_DRIVE.match(out.as_posix()):
        # A project on C: is reached from a Windows-side agent session, which loads none of the
        # project's skills, hooks, agents or settings (colleague trial on Codex, 2026-10-22).
        return (f"{out} is on the Windows drive. On Windows, an init-math project lives in the "
                "Linux home folder (for example ~/research/<slug>), and the agent is started "
                "there from an Ubuntu terminal: a session started on the Windows side, "
                "including VS Code not connected to WSL, loads none of the project's skills, "
                "hooks, reviewers or settings")
    if out.exists():
        if not out.is_dir():
            return f"{out} exists and is not a directory"
        if any(out.iterdir()):
            return f"{out} is not empty; init-math only writes into a new or empty directory"
    probe = out
    while not probe.exists():
        if probe.parent == probe:
            break
        probe = probe.parent
    if not os.access(probe, os.W_OK | os.X_OK):
        return f"{out} is not writable (no write permission on {probe})"
    return None


def check_target(path: str) -> int:
    msg = target_problem(Path(path).expanduser().resolve())
    if msg:
        print(f"error: {msg}", file=sys.stderr)
        return 1
    print(f"OK: {Path(path).expanduser().resolve()} is new or empty and writable")
    return 0


def _why_off(m, ans: dict) -> str:
    sel = ans["modules"]
    if m.status == "deferred":
        return "not available in this version"
    pa = m.requires.get("proof_assistant")
    if pa and ans["stack"]["proof_assistant"] != pa:
        return f"proof_assistant is {ans['stack']['proof_assistant']}, this module needs {pa}"
    if m.id in sel["disable"]:
        return "listed in modules.disable"
    if sel["preset"] and sel["preset"] in m.off_in_presets:
        return f"preset {sel['preset']}"
    return "opt-in module, not enabled"


def check_answers(path: str, out: str | None = None) -> int:
    from renderer import render
    from renderer.answers import AnswersError, load_answers, warnings_for
    try:
        ans = load_answers(path)
        mods = render.load_modules(_templates())
        on = render.resolve_enabled(mods, ans)
    except (AnswersError, render.RenderError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    by_id = {m.id: m for m in mods}
    print(json.dumps({
        "harness": ans["harness"], "tiers": ans["tiers"],
        "modules_on": sorted(i for i, v in on.items() if v and i != "core"),
        "modules_off": sorted(i for i, v in on.items() if not v),
        "modules_off_why": {i: _why_off(by_id[i], ans) for i, v in sorted(on.items()) if not v},
        "seeds": {k: len(v) for k, v in ans["seeds"].items() if isinstance(v, list)},
        "active_question": ans["seeds"]["active_question"] or None,
        "experiment_limits": ans["experiments"]["limits"] if on.get("experiments") else None,
        "exposition": ans["exposition"] if on.get("readers") else None,
        "warnings": warnings_for(ans, Path(out).expanduser().resolve() if out else None),
    }, indent=2))
    return 0


def _git(out: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(out), *args], capture_output=True, text=True,
                          check=check)


def init_math_version(root: Path | None = None, claude_dir: Path | None = None) -> str:
    """This copy of init-math: its plugin version, and its git commit when known, from a git
    checkout or from Claude Code's record of the installed plugin (the installed copy has no
    .git). Codex installs give the version only."""
    root = (root or HERE.parents[2]).resolve()
    try:
        version = json.loads((root / ".claude-plugin/plugin.json").read_text())["version"]
    except (OSError, ValueError, KeyError):
        version = "unknown"
    sha = ""
    try:
        top = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True)
        # Only init-math's own repository, never one that happens to contain this folder.
        if top.returncode == 0 and Path(top.stdout.strip()).resolve() == root:
            sha = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                                 capture_output=True, text=True).stdout.strip()
    except OSError:
        pass
    if not sha:
        claude_dir = claude_dir or Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
        try:
            rec = json.loads((claude_dir / "plugins/installed_plugins.json").read_text())
            for installs in rec.get("plugins", {}).values():
                for i in installs:
                    if Path(i.get("installPath", "")).resolve() == root:
                        sha = i.get("gitCommitSha", "")
        except (OSError, ValueError, AttributeError, TypeError):
            pass
    return f"{version} (commit {sha[:7]})" if sha else version


def create(answers: str, out: Path, run_selftest: bool = True) -> int:
    from renderer import render
    from renderer.answers import AnswersError, read_answers, validate
    problems = preflight()
    if problems:
        for p in problems:
            print(f"preflight: {p}", file=sys.stderr)
        return 2
    from renderer.answers import warnings_for
    msg = target_problem(out)
    if msg:
        print(f"error: {msg}", file=sys.stderr)
        return 1
    try:
        given = read_answers(answers)
        ans = validate(given)
        for w in warnings_for(ans, out):
            print(f"warning: {w}", file=sys.stderr)
        report = render.render_project(ans, out, _templates(), given)
    except (AnswersError, render.RenderError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    _git(out, "init", "-q")
    _git(out, "add", "-A")
    ident = []
    if not _git(out, "config", "user.email", check=False).stdout.strip():
        # No git identity configured: commit as the owner, and say so.
        print("note: git, which keeps the project's history, does not know your name and email, "
              "so the first saved version uses your name and a placeholder email. Before the "
              "agents save more, run in a terminal:\n"
              "    git config --global user.name \"Your Name\"\n"
              "    git config --global user.email you@example.org")
        ident = ["-c", f"user.name={ans['project']['owner']}", "-c", "user.email=owner@localhost"]
    r = subprocess.run(["git", "-C", str(out), *ident, "commit", "-q", "-m",
                        f"init: {ans['project']['name']} (generated by init-math)", "-m",
                        f"init-math version: {init_math_version()}"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"error: initial commit failed:\n{r.stderr}", file=sys.stderr)
        return 1

    if (out / "bin/setup-hooks").exists():
        r = subprocess.run([sys.executable, str(out / "bin/setup-hooks")], cwd=out,
                           capture_output=True, text=True)
        if r.returncode != 0:
            print(f"warning: bin/setup-hooks failed:\n{r.stdout}{r.stderr}", file=sys.stderr)

    ok = True
    if run_selftest:
        r = subprocess.run([sys.executable, str(out / "bin/selftest")], cwd=out,
                           capture_output=True, text=True)
        print(r.stdout.rstrip())
        ok = r.returncode == 0
        if not ok:
            print(f"\nbin/selftest FAILED. Details: {out}/bin/selftest -v", file=sys.stderr)

    print(next_steps(ans, report, out))
    return 0 if ok else 1


def next_steps(ans: dict, report: dict, out: Path) -> str:
    on = set(report["modules_on"])
    prog = "codex" if ans["harness"] == "codex" else "claude"
    s = [f"\nCreated {ans['project']['name']} in {out}", "", "Next steps:"]
    s.append(f"1. Leave this session (type /exit), then start the agent in the new project:\n"
             f"       cd {shlex.quote(str(out))}\n       {prog}\n"
             "   Always start it in that folder. Started anywhere else, this session included, "
             "the agent works without the project's skills, automatic checks, reviewers and "
             "model settings, and nothing says so.")
    if ans["harness"] == "codex":
        s.append("2. Codex asks whether to trust the folder: say yes. Then type /hooks and trust "
                 "the project's hooks (Codex skips hooks you have not trusted).")
    else:
        s.append("2. Claude Code asks whether to trust the folder: say yes.")
    ask = ("type /getting-started" if ans["harness"] != "codex"
           else 'type $getting-started (Codex runs a skill when you type $ and its name; '
                '/skills lists them)')
    s.append(f"3. Then {ask} and the agent walks you through the first session, one step at "
             "a time: a check that the session loaded the project (bin/doctor), the question to "
             "start on, and your sources. If the agent does not know the getting-started skill, "
             "it was started in the wrong folder: leave and start it again as in step 1. "
             "Your manual, docs/OWNER.md, says the same for reference; you need not read it first.")
    n = 4
    aq = ans["seeds"]["active_question"]
    if "questions" in on and aq:
        s.append(f"{n}. {aq} is active, as you chose; your other questions wait until you "
                 "activate them.")
        n += 1
    if "lean" in on and not ans["stack"]["lake_path"]:
        s.append(f"{n}. Set up Lean: see formal/README.md (the commands are printed there, not run).")
        n += 1
    if report["hooks_skipped"]:
        s.append(f"\n{len(report['hooks_skipped'])} hook registration(s) do not apply to "
                 f"{ans['harness']}; see docs/init-report.json.")
    return "\n".join(s)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--list-modules", action="store_true")
    g.add_argument("--check-answers", metavar="ANSWERS")
    g.add_argument("--check-target", metavar="DIR")
    g.add_argument("--answers", metavar="ANSWERS")
    g.add_argument("--preflight", action="store_true")
    ap.add_argument("--json", action="store_true", help="with --list-modules")
    ap.add_argument("--out", help="with --answers (or --check-answers): the new or empty project "
                                  "directory")
    ap.add_argument("--no-selftest", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--templates", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    global TEMPLATES
    TEMPLATES = a.templates
    if sys.version_info < MIN_PY:
        print(f"init-math needs Python >= 3.11 (this is {sys.version.split()[0]})", file=sys.stderr)
        return 2
    if a.preflight:
        problems = preflight()
        for p in problems:
            print(f"FAIL {p}")
        if not problems:
            print("PASS python3 >= 3.11 on PATH, git present")
        return 1 if problems else 0
    if a.list_modules:
        return list_modules(a.json)
    if a.check_answers:
        return check_answers(a.check_answers, a.out)
    if a.check_target:
        return check_target(a.check_target)
    if not a.out:
        ap.error("--answers needs --out")
    return create(a.answers, Path(a.out).expanduser().resolve(), not a.no_selftest)


if __name__ == "__main__":
    sys.exit(main())
