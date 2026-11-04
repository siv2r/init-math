"""Renderer tests: golden fixtures, determinism, module resolution, refusals, independence."""
from __future__ import annotations

import filecmp
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/init-math/scripts"))

from renderer import answers as answers_mod, render  # noqa: E402
from renderer.answers import AnswersError, load_answers, slugify, validate, warnings_for  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
TEMPLATES = render.TEMPLATES_DIR
FIXTURES = ("answers-claude-lean.json", "answers-codex-theory.json", "answers-codex-behavior.json")
# Words that must never appear in templates or rendered output: the generated project
# must not depend on, or name, the machine or project it was distilled from.
FORBIDDEN = re.compile(r"/Users/|/home/")
AGENTS_BUDGET = 20 * 1024


def _render(fixture: str, out: Path, templates: Path = TEMPLATES) -> dict:
    given = json.loads((FIX / fixture).read_text())
    return render.render_project(validate(given), out, templates, given)


def _tree(d: Path) -> list[str]:
    return sorted(p.relative_to(d).as_posix() for p in d.rglob("*") if p.is_file())


class TempDirCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="init-math test ")  # space on purpose
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()


class GoldenTests(TempDirCase):
    def test_fixtures_render(self):
        for fx in FIXTURES:
            with self.subTest(fx):
                out = self.tmp / fx
                rep = _render(fx, out)
                self.assertTrue((out / "AGENTS.md").exists())
                self.assertTrue((out / "project.toml").exists())
                with open(out / "project.toml", "rb") as f:
                    tomllib.load(f)  # must parse
                self.assertIn("core", rep["modules_on"])

    def test_awkward_answers_stay_valid_toml(self):
        # Interview answers are free text: quotes, backslashes and ''' must survive intact.
        a = json.loads((FIX / FIXTURES[0]).read_text())
        nasty = "say \"hi\" \\ back'''slash"
        regex = "out of memory\\s+'''"
        rule = "never write \\lim without a topology '''"
        a["project"]["name"] = nasty
        a["stack"]["run_cmd"] = "run --tag \"x\" {driver}"
        a["stack"]["failure_signatures"] = [{"label": "quote \" label", "regex": regex}]
        a["stack"]["hygiene_rules"] = [rule]
        out = self.tmp / "awkward"
        render.render_project(validate(a), out, TEMPLATES)
        with open(out / "project.toml", "rb") as f:
            t = tomllib.load(f)
        self.assertEqual(t["project"]["name"], nasty)
        self.assertEqual(t["stack"]["run_cmd"], "run --tag \"x\" {driver}")
        self.assertEqual(t["stack"]["failure_signatures"][0]["regex"], regex)
        self.assertEqual(t["hygiene"]["rules"], [rule])

    def test_deterministic(self):
        for fx in FIXTURES:
            with self.subTest(fx):
                a, b = self.tmp / f"{fx}-a", self.tmp / f"{fx}-b"
                _render(fx, a)
                _render(fx, b)
                self.assertEqual(_tree(a), _tree(b))
                _, mismatch, errors = filecmp.cmpfiles(a, b, _tree(a), shallow=False)
                self.assertEqual((mismatch, errors), ([], []))

    def test_stored_answers_rerender_identically(self):
        # docs/init-answers.json is the normalized copy the handover offers in place of the
        # interview's answers file, so it must render the same project.
        for fx in FIXTURES:
            with self.subTest(fx):
                a, b = self.tmp / f"{fx}-a", self.tmp / f"{fx}-b"
                _render(fx, a)
                stored = json.loads((a / "docs/init-answers.json").read_text())
                render.render_project(validate(stored), b, TEMPLATES, stored)
                self.assertEqual(_tree(a), _tree(b))
                _, mismatch, errors = filecmp.cmpfiles(a, b, _tree(a), shallow=False)
                self.assertEqual((mismatch, errors), ([], []))

    def test_stored_answers_leave_defaults_unset(self):
        """docs/init-answers.json keeps what the interview decided but not init-math's
        defaults, so a later init-math (an upgrade) applies its own: a new default worker
        model reaches the re-rendered project; an explicit choice stays."""
        x = self.tmp / "x"
        _render(FIXTURES[1], x)
        stored = json.loads((x / "docs/init-answers.json").read_text())
        self.assertEqual(stored["tiers"], {})
        self.assertNotIn("failure_signatures", stored["stack"])
        self.assertEqual(stored["experiments"]["limits"], {})
        with mock.patch.dict(answers_mod.DEFAULT_TIERS,
                             {"codex": {"strong": "gpt-6-astra", "worker": "newer-worker"}}):
            y = self.tmp / "y"
            render.render_project(load_answers(x / "docs/init-answers.json"), y, TEMPLATES)
        with open(y / ".codex/agents/worker.toml", "rb") as f:
            self.assertEqual(tomllib.load(f)["model"], "newer-worker")
        a = json.loads((FIX / FIXTURES[1]).read_text())
        a["tiers"] = {"worker": "my-worker"}
        a["experiments"] = {"limits": {"full": {"mem_mb": 7000}}}
        z = self.tmp / "z"
        render.render_project(validate(a), z, TEMPLATES, a)
        stored = json.loads((z / "docs/init-answers.json").read_text())
        self.assertEqual(stored["tiers"], {"worker": "my-worker"})
        self.assertEqual(stored["experiments"]["limits"], {"full": {"mem_mb": 7000}})

    def test_harness_specific_files(self):
        c, x = self.tmp / "c", self.tmp / "x"
        _render(FIXTURES[0], c)
        _render(FIXTURES[1], x)
        self.assertEqual((c / "CLAUDE.md").read_text(), "@AGENTS.md\n")
        self.assertFalse((x / "CLAUDE.md").exists())
        self.assertIn("Claude Code", (c / "AGENTS.md").read_text())
        self.assertIn("Codex CLI", (x / "AGENTS.md").read_text())
        self.assertNotIn("Claude Code", (x / "AGENTS.md").read_text())

    def test_codex_git_commits(self):
        # Default: a permission profile that makes .git writable but keeps .codex/.agents read.
        x = self.tmp / "x"
        _render(FIXTURES[1], x)
        with open(x / ".codex/config.toml", "rb") as f:
            cfg = tomllib.load(f)
        self.assertEqual(cfg["default_permissions"], "project-git")
        prof = cfg["permissions"]["project-git"]
        self.assertEqual(prof["extends"], ":workspace")
        self.assertEqual(prof["filesystem"][":workspace_roots"],
                         {".git": "write", ".codex": "read", ".agents": "read"})
        # Opt-out: no profile, and OWNER.md says how to turn it on.
        a = json.loads((FIX / FIXTURES[1]).read_text())
        a["codex"] = {"git_commits": False}
        y = self.tmp / "y"
        render.render_project(validate(a), y, TEMPLATES)
        with open(y / ".codex/config.toml", "rb") as f:
            self.assertEqual(tomllib.load(f), {"model": "gpt-6-astra",
                                               "model_auto_compact_token_limit": 300000})
        self.assertIn('default_permissions = "project-git"', (y / "docs/OWNER.md").read_text())
        a["codex"] = {"git_commits": "no"}
        with self.assertRaises(AnswersError):
            validate(a)
        # Claude projects get no Codex config.
        c = self.tmp / "c"
        _render(FIXTURES[0], c)
        self.assertFalse((c / ".codex").exists())

    def test_auto_compaction_and_codex_worker_tier(self):
        """Both harnesses compact at 300k tokens (Claude `autoCompactWindow`, Codex
        `model_auto_compact_token_limit`); Codex workers default to gpt-6-luna, reviewers stay
        on the strong tier; program review is on by default (colleague trial, 2026-10-22)."""
        c, x = self.tmp / "c", self.tmp / "x"
        _render(FIXTURES[0], c)
        _render(FIXTURES[1], x)
        self.assertEqual(json.loads((c / ".claude/settings.json").read_text())["autoCompactWindow"],
                         300000)
        with open(x / ".codex/config.toml", "rb") as f:
            self.assertEqual(tomllib.load(f)["model_auto_compact_token_limit"], 300000)
        self.assertNotIn("autoCompactWindow", (x / ".codex/hooks.json").read_text())
        with open(x / ".codex/agents/worker.toml", "rb") as f:
            self.assertEqual(tomllib.load(f)["model"], "gpt-6-luna")
        with open(x / ".codex/agents/claim-auditor.toml", "rb") as f:
            self.assertEqual(tomllib.load(f)["model"], "gpt-6-astra")
        for out in (c, x):
            self.assertIn("program_review", json.loads((out / "docs/init-report.json").read_text())
                          ["modules_on"])
            rules = "".join((out / f).read_text() for f in ("AGENTS.md", "COORDINATOR.md") if (out / f).exists())
            self.assertIn("## Program review", rules)

    def test_work_folders_and_doctor(self):
        """Every project has work/ (index + template) and bin/doctor; the notes/ nudge is
        registered for edits (colleague trial, 2026-10-22: 1,046 files in a flat notes/)."""
        for fx in FIXTURES:
            out = self.tmp / f"w-{fx}"
            _render(fx, out)
            with self.subTest(fx):
                self.assertTrue((out / "work/_index.md").is_file())
                self.assertTrue((out / "work/TEMPLATE/README.md").is_file())
                self.assertTrue(os.access(out / "bin/doctor", os.X_OK))
                self.assertIn("work/<slug>/", (out / "AGENTS.md").read_text())
                cfg = (out / (".claude/settings.json" if "claude" in fx else ".codex/hooks.json"))
                self.assertIn("file-home-nudge.py", cfg.read_text())

    def test_agents_md_budget(self):
        for fx in FIXTURES:
            with self.subTest(fx):
                out = self.tmp / fx
                _render(fx, out)
                n = len((out / "AGENTS.md").read_bytes())
                self.assertLessEqual(n, AGENTS_BUDGET, f"AGENTS.md is {n} bytes")

    def test_no_unrendered_tags(self):
        for fx in FIXTURES:
            out = self.tmp / fx
            _render(fx, out)
            for rel in _tree(out):
                text = (out / rel).read_text(encoding="utf-8", errors="replace")
                with self.subTest(fx=fx, file=rel):
                    self.assertNotRegex(text, r"\{\{[#/!]?[a-zA-Z_.@!]")

    def test_selftest_passes(self):
        for fx in FIXTURES:
            with self.subTest(fx):
                out = self.tmp / fx
                _render(fx, out)
                r = subprocess.run([sys.executable, str(out / "bin" / "selftest")],
                                   capture_output=True, text=True, timeout=300)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_report_written(self):
        out = self.tmp / "r"
        _render(FIXTURES[1], out)
        rep = json.loads((out / "docs" / "init-report.json").read_text())
        self.assertEqual(rep["harness"], "codex")
        ans = json.loads((out / "docs" / "init-answers.json").read_text())
        self.assertEqual(ans["project"]["owner"], "B. Mathematician")

    def test_usage_hook_registered(self):
        """Usage statistics stays on under the theory-only preset; its hook is registered on
        Stop and SubagentStop everywhere and on SessionEnd only where the harness has it."""
        want = {FIXTURES[0]: ({"Stop", "SubagentStop", "SessionEnd"}, ".claude/settings.json"),
                FIXTURES[1]: ({"Stop", "SubagentStop"}, ".codex/hooks.json")}
        for fx, (events, cfg_path) in want.items():
            with self.subTest(fx):
                out = self.tmp / f"u-{fx}"
                rep = _render(fx, out)
                self.assertIn("usage", rep["modules_on"])
                hooks = json.loads((out / cfg_path).read_text())["hooks"]
                got = {ev for ev, groups in hooks.items()
                       if any("usage-log.py" in h["command"] for g in groups for h in g["hooks"])}
                self.assertEqual(got, events)
                self.assertNotIn("usage-log.py", json.dumps(rep["hooks_skipped"]))

    def test_web_tools_preapproved_with_firsthand(self):
        """Claude projects pre-approve web search/fetch for the (often background) lit-search
        agent; without the firsthand module, or on Codex, no permissions block is written."""
        c = self.tmp / "c"
        _render(FIXTURES[0], c)
        cfg = json.loads((c / ".claude/settings.json").read_text())
        self.assertEqual(cfg["permissions"]["allow"][:2], ["WebSearch", "WebFetch"])
        self.assertIn("## Web access", (c / "docs/OWNER.md").read_text())
        a = json.loads((FIX / FIXTURES[0]).read_text())
        a.setdefault("modules", {}).setdefault("disable", []).append("firsthand")
        n = self.tmp / "n"
        render.render_project(validate(a), n, TEMPLATES)
        allow = json.loads((n / ".claude/settings.json").read_text())["permissions"]["allow"]
        self.assertFalse({"WebSearch", "WebFetch"} & set(allow), allow)
        self.assertNotIn("## Web access", (n / "docs/OWNER.md").read_text())
        x = self.tmp / "x"
        _render(FIXTURES[1], x)
        self.assertNotIn("permissions", json.loads((x / ".codex/hooks.json").read_text()))

    def test_only_check_scripts_preapproved(self):
        """Claude projects pre-approve the project's own check-and-record scripts, each one
        that exists, and never one that runs an arbitrary command."""
        c = self.tmp / "c"
        _render(FIXTURES[0], c)
        allow = json.loads((c / ".claude/settings.json").read_text())["permissions"]["allow"]
        cmds = {r[len("Bash("):-len(":*)")].removeprefix("./") for r in allow if r.startswith("Bash(")}
        self.assertIn("bin/selftest", cmds)
        self.assertIn("bin/doctor", cmds)
        self.assertIn("bin/wiki-check", cmds)
        self.assertIn("bin/question-check", cmds)
        for cmd in cmds:
            self.assertTrue((c / cmd).is_file(), cmd)
        for runs_anything in ("exp-run", "guard-run", "bg-run", "wait-until-done", "heartbeat",
                              "lean-build"):
            self.assertNotIn(f"bin/{runs_anything}", cmds)


    def test_main_thread_on_strong_tier(self):
        """The main thread runs on the strong tier: Claude's settings.json `model`, Codex's
        config.toml `model` (the 2026-10-09 Codex run had it on the worker model)."""
        c, x = self.tmp / "c", self.tmp / "x"
        _render(FIXTURES[0], c)
        _render(FIXTURES[1], x)
        self.assertEqual(json.loads((c / ".claude/settings.json").read_text())["model"], "opus")
        with open(x / ".codex/config.toml", "rb") as f:
            self.assertEqual(tomllib.load(f)["model"], "gpt-6-astra")
        self.assertNotIn("model", json.loads((x / ".codex/hooks.json").read_text()))
        a = json.loads((FIX / FIXTURES[1]).read_text())
        a["tiers"] = {"strong": "my-best-model"}
        y = self.tmp / "y"
        render.render_project(validate(a), y, TEMPLATES)
        with open(y / ".codex/config.toml", "rb") as f:
            self.assertEqual(tomllib.load(f)["model"], "my-best-model")

    def test_guard_run_without_memory_sampling(self):
        """Where process memory cannot be read (no `ps`, no /proc: the Codex sandbox on macOS),
        guard-run's memory checks are SKIPPED, not failed, and bin/selftest shows a WARN."""
        out = self.tmp / "g"
        _render(FIXTURES[0], out)
        only_sleep = self.tmp / "bin-no-ps"
        only_sleep.mkdir()
        (only_sleep / "sleep").symlink_to(shutil.which("sleep"))
        r = subprocess.run([sys.executable, str(out / "bin/guard-run"), "--selftest"],
                           capture_output=True, text=True, timeout=120,
                           env={**os.environ, "PATH": str(only_sleep)})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotRegex(r.stdout, r"(?m)^FAIL ")
        if not Path("/proc").is_dir():
            self.assertIn("SKIP memory sampling works on this machine", r.stdout)
            self.assertIn("PASS without memory sampling, --json records mem_enforced: false", r.stdout)
        # bin/selftest turns a script's SKIP line into a WARN that does not fail the run.
        fake = out / "bin" / "skipper"
        fake.write_text("#!/usr/bin/env python3\n# selftest: yes\nprint('SKIP x: cannot here')\n")
        fake.chmod(0o755)
        r = subprocess.run([sys.executable, str(out / "bin/selftest")],
                           capture_output=True, text=True, timeout=300)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertRegex(r.stdout, r"WARN\s+bin/skipper --selftest\s+SKIP x: cannot here")


TIE_BRIEF = """# A task

## Question tie
question: Q001 / A1
via: C001
kind: decides
outcomes:
- if a congruence mod l^2 for some l >= 13 fails to lift → C001 is refuted and A1 needs the extra case
- if every congruence found lifts → C001 is confirmed on the family and A1 reduces to the k = 1 list
"""


class InterviewChoiceTests(TempDirCase):
    """The three optional interview answers: the one active question, run limits, and the
    exposition slots. Each is rendered with and without the answer."""

    def _fixture(self, fx: str) -> dict:
        return json.loads((FIX / fx).read_text())

    def _run(self, out: Path, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, *args], input=stdin, capture_output=True,
                              text=True, timeout=120, cwd=out)

    def test_active_question_rendered_and_checked(self):
        # With: the theory fixture chose Q001.
        x = self.tmp / "x"
        _render(FIXTURES[1], x)
        q = next((x / "wiki/questions").glob("Q001-*.md")).read_text()
        self.assertIn("\nstatus: active ", q)
        self.assertIn("\nactivated-by: B. Mathematician\n", q)
        self.assertIn("| active |", (x / "wiki/questions/_index.md").read_text())
        self.assertIn("you chose Q001", (x / "docs/OWNER.md").read_text())
        r = self._run(x, str(x / "bin/question-check"), "--root", str(x))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("0 FAIL", r.stdout)
        # Without: every question proposed, OWNER.md asks the owner to pick one.
        c = self.tmp / "c"
        _render(FIXTURES[0], c)
        q = next((c / "wiki/questions").glob("Q001-*.md")).read_text()
        self.assertIn("\nstatus: proposed ", q)
        self.assertNotIn("| active |", (c / "wiki/questions/_index.md").read_text())
        self.assertIn("Decide the first questions", (c / "docs/OWNER.md").read_text())
        r = self._run(c, str(c / "bin/question-check"), "--root", str(c))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        # tie-check: a task tied to Q001 fails while Q001 is proposed and passes once the
        # owner chose it in the interview (same fixture, only active_question differs).
        r = self._run(c, str(c / "bin/tie-check"), "--root", str(c), "-", stdin=TIE_BRIEF)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("T2", r.stdout)
        a = self._fixture(FIXTURES[0])
        a["seeds"]["active_question"] = "Q001"
        ca = self.tmp / "ca"
        render.render_project(validate(a), ca, TEMPLATES)
        r = self._run(ca, str(ca / "bin/tie-check"), "--root", str(ca), "-", stdin=TIE_BRIEF)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = self._run(ca, str(ca / "bin/question-check"), "--root", str(ca))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("0 FAIL", r.stdout)

    def test_active_question_validated(self):
        for bad in ("Q009", "q001", 1, ["Q001"]):
            with self.subTest(bad):
                a = self._fixture(FIXTURES[1])
                a["seeds"]["active_question"] = bad
                with self.assertRaises(AnswersError):
                    validate(a)
        a = self._fixture(FIXTURES[1])
        a["seeds"]["active_question"] = ""
        self.assertFalse(any(q["active"] for q in validate(a)["seeds"]["questions"]))

    def test_run_limits(self):
        # With: the Lean fixture overrides smoke memory and both deep limits.
        c = self.tmp / "c"
        _render(FIXTURES[0], c)
        with open(c / "project.toml", "rb") as f:
            lim = tomllib.load(f)["experiments"]["limits"]
        self.assertEqual(lim, {"smoke": {"time_s": 120, "mem_mb": 1500},
                               "full": {"time_s": 7200, "mem_mb": 8000},
                               "deep": {"time_s": 86400, "mem_mb": 32000}})
        # Without: the defaults, which bin/exp-run also falls back to.
        a = self._fixture(FIXTURES[0])
        del a["experiments"]
        d = self.tmp / "d"
        render.render_project(validate(a), d, TEMPLATES)
        with open(d / "project.toml", "rb") as f:
            lim = tomllib.load(f)["experiments"]["limits"]
        from renderer.answers import DEFAULT_LIMITS
        self.assertEqual(lim, DEFAULT_LIMITS)
        exp_run = (d / "bin/exp-run").read_text()
        m = re.search(r"^DEFAULT_LIMITS = (\{.*?\})\n", exp_run, re.S | re.M)
        import ast
        self.assertEqual(ast.literal_eval(m.group(1)), DEFAULT_LIMITS)
        # Validation: positive numbers only, known tiers and keys only.
        for bad in ({"smoke": {"time_s": 0}}, {"full": {"mem_mb": -1}}, {"deep": {"time_s": "2h"}},
                    {"deep": {"time_s": True}}, {"huge": {"time_s": 1}}, {"smoke": {"cpu": 1}},
                    {"smoke": {"time_s": float("inf")}}, {"smoke": 5}):
            with self.subTest(bad):
                a["experiments"] = {"limits": bad}
                with self.assertRaises(AnswersError):
                    validate(a)

    def test_exposition_slots(self):
        def owner_item(out: Path) -> str:
            text = (out / "docs/OWNER.md").read_text()
            return " ".join(re.findall(r"^- \*\*(Fill the exposition slots|List your prior work|"
                                       r"Name a model text)", text, re.M))
        # With both: the slots are filled and OWNER.md has nothing left to ask.
        c = self.tmp / "c"
        _render(FIXTURES[0], c)
        ex = (c / "docs/discipline/exposition.md").read_text()
        self.assertIn("- A. Researcher, Congruences for eta-quotients", ex)
        self.assertIn("- Ahlgren, Ono: Congruence properties", ex)
        self.assertNotIn("<title, year", ex)
        self.assertNotIn("<fill in", ex)
        self.assertEqual(owner_item(c), "")
        # Without: both placeholders stay (the reviewers detect them) and OWNER.md asks.
        x = self.tmp / "x"
        _render(FIXTURES[1], x)
        ex = (x / "docs/discipline/exposition.md").read_text()
        self.assertIn("- <title, year", ex)
        self.assertIn("<fill in", ex)
        self.assertEqual(owner_item(x), "Fill the exposition slots")
        # One of the two: OWNER.md asks only for the empty slot.
        for keep, want in (("prior_work", "Name a model text"), ("model_text", "List your prior work")):
            with self.subTest(keep):
                a = self._fixture(FIXTURES[0])
                a["exposition"] = {keep: a["exposition"][keep]}
                out = self.tmp / f"one-{keep}"
                render.render_project(validate(a), out, TEMPLATES)
                self.assertEqual(owner_item(out), want)
        for bad in ({"prior_work": "one paper"}, {"prior_work": [1]}, {"model_text": ["a"]}, []):
            with self.subTest(bad):
                a = self._fixture(FIXTURES[0])
                a["exposition"] = bad
                with self.assertRaises(AnswersError):
                    validate(a)

class GitignoreTests(TempDirCase):
    def test_experiment_bundles_not_ignored(self):
        """The generated .gitignore keeps bin/bg-run's top-level runs/ out of git but never an
        experiment's run bundle (experiments/<slug>/runs/<timestamp>/), which is committed."""
        out = self.tmp / "p"
        _render("answers-claude-lean.json", out)
        subprocess.run(["git", "init", "-q", str(out)], check=True)
        for rel in ("experiments/x/runs/t1/analysis.md", "runs/t2/out.log"):
            (out / rel).parent.mkdir(parents=True, exist_ok=True)
            (out / rel).write_text("x\n")
        def ignored(rel: str) -> bool:
            return subprocess.run(["git", "check-ignore", "-q", rel], cwd=out).returncode == 0
        self.assertFalse(ignored("experiments/x/runs/t1/analysis.md"))
        self.assertTrue(ignored("runs/t2/out.log"))


class IndependenceTests(TempDirCase):
    def test_templates_clean(self):
        for p in sorted(TEMPLATES.rglob("*")):
            if p.is_file() and p.suffix not in (".pyc",):
                with self.subTest(str(p.relative_to(TEMPLATES))):
                    self.assertIsNone(FORBIDDEN.search(p.read_text(encoding="utf-8", errors="replace")))

    def test_rendered_clean(self):
        for fx in FIXTURES:
            out = self.tmp / fx
            _render(fx, out)
            for rel in _tree(out):
                with self.subTest(fx=fx, file=rel):
                    m = FORBIDDEN.search((out / rel).read_text(encoding="utf-8", errors="replace"))
                    self.assertIsNone(m, m and m.group(0))


class ProbeModuleTests(TempDirCase):
    """Exercise every emission path with the test-only probe module."""

    def _templates_with_probe(self) -> Path:
        t = self.tmp / "templates"
        shutil.copytree(TEMPLATES, t)
        shutil.copytree(FIX / "probe-module", t / "modules" / "99-probe")
        return t

    def test_claude_emission(self):
        t = self._templates_with_probe()
        out = self.tmp / "c"
        with mock.patch.dict(render.CATALOG, {"probe": 99}):
            rep = _render(FIXTURES[0], out, t)
        self.assertIn("probe", rep["modules_on"])
        agent = (out / ".claude/agents/probe-reviewer.md").read_text()
        self.assertIn("model: opus", agent)
        self.assertIn("tools: Read, Grep", agent)
        self.assertIn("Partition Congruences", (out / ".claude/skills/probe/SKILL.md").read_text())
        self.assertTrue((out / "probe/Q001-for-which-primes-l-and-moduli-does-p-l-k.md").exists()
                        or any(p.startswith("probe/Q001-") for p in _tree(out)))
        cfg = json.loads((out / ".claude/settings.json").read_text())
        self.assertIn("PreToolUse", cfg["hooks"])
        self.assertIn("## Probe", (out / "AGENTS.md").read_text())

    def test_codex_emission(self):
        t = self._templates_with_probe()
        out = self.tmp / "x"
        with mock.patch.dict(render.CATALOG, {"probe": 99}):
            rep = _render(FIXTURES[1], out, t)
        agent_toml = (out / ".codex/agents/probe-reviewer.toml").read_text()
        parsed = tomllib.loads(agent_toml)
        self.assertEqual(parsed["model"], "gpt-6-astra")
        self.assertIn("READ-ONLY", parsed["developer_instructions"])
        self.assertTrue((out / ".agents/skills/probe/SKILL.md").exists())
        cfg = json.loads((out / ".codex/hooks.json").read_text())
        pre = cfg["hooks"]["PreToolUse"][0]
        self.assertNotIn("AskUserQuestion", pre["matcher"])
        self.assertIn("--harness codex", pre["hooks"][0]["command"])
        self.assertEqual(rep["hooks_skipped"], [])

    def test_probe_hook_runs(self):
        t = self._templates_with_probe()
        out = self.tmp / "c"
        with mock.patch.dict(render.CATALOG, {"probe": 99}):
            _render(FIXTURES[0], out, t)
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                   "tool_input": {"command": "ls"}, "cwd": str(out)}
        r = subprocess.run([sys.executable, str(out / "hooks/probe.py"), "--harness", "claude"],
                           input=json.dumps(payload), capture_output=True, text=True,
                           env={"CLAUDE_PROJECT_DIR": str(out), "PATH": "/usr/bin:/bin"})
        self.assertEqual(r.returncode, 0, r.stderr)
        rec = json.loads((out / "logs/probe-payloads.jsonl").read_text().splitlines()[0])
        self.assertEqual(rec["action"], "shell")


LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def dangling_links(out: Path) -> list[str]:
    """Relative markdown links in rendered .md files whose target does not exist."""
    bad = []
    for rel in _tree(out):
        if not rel.endswith(".md"):
            continue
        for target in LINK.findall((out / rel).read_text(encoding="utf-8")):
            if re.match(r"^[a-z]+:|^#", target):
                continue
            t = target.split("#")[0]
            if not (out / rel).parent.joinpath(t).resolve().exists():
                bad.append(f"{rel} -> {target}")
    return bad


class LinkTests(TempDirCase):
    def test_no_dangling_links(self):
        for fx in FIXTURES:
            with self.subTest(fx):
                out = self.tmp / fx
                _render(fx, out)
                self.assertEqual(dangling_links(out), [])

    def test_leave_one_out(self):
        """Switching off any one removable module (and what depends on it) leaves a
        project with no dangling links that still passes its selftest."""
        mods = render.load_modules(TEMPLATES)
        removable = [m for m in mods if not m.core and m.status != "deferred"]
        outs = {}
        for m in removable:
            off = {m.id} | {d.id for d in mods if m.id in d.depends}
            a = json.loads((FIX / FIXTURES[0]).read_text())
            a["modules"]["disable"] = sorted(off)
            a["modules"]["enable"] = [x.id for x in mods if x.status == "opt-in" and x.id not in off]
            with self.subTest(m.id):
                out = self.tmp / f"loo-{m.id}"
                render.render_project(validate(a), out)
                self.assertEqual(dangling_links(out), [])
                outs[m.id] = out

        # The selftests dominate the time and are independent processes: run them together.
        # At most 4 at a time, with each check's time limit scaled up: on a busy macOS machine
        # their many short-lived subprocesses and freshly written scripts queue up (security
        # scanning, indexing) until time limits fire, although each passes alone (2026-10-25).
        def selftest(out: Path) -> subprocess.CompletedProcess:
            return subprocess.run([sys.executable, str(out / "bin" / "selftest")],
                                  capture_output=True, text=True, timeout=1200,
                                  env={**os.environ, "SELFTEST_TIMEOUT_SCALE": "4"})
        with ThreadPoolExecutor(max_workers=min(4, os.cpu_count() or 2)) as pool:
            results = dict(zip(outs, pool.map(selftest, outs.values())))
        for mid, r in results.items():
            with self.subTest(mid, step="selftest"):
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


# Review-machinery text that names an optional module: with that module (and what depends on it)
# off, none of it may appear in the documents, agents or skills.
SLICE_D_ONLY = {
    "questions": re.compile(r"^READING:", re.M),
    "commit_gate": re.compile(r"--new-cycle|--caveat-ok|--kind (last-look|exchange)"),
    "program_review": re.compile(r"Program review reads them|\(author\|review\)-miss"),
    "lean": re.compile(r"comparison of the formal\s+statement"),
}


class CoordinatorSplitTests(TempDirCase):
    """On Claude, AGENTS.md holds every agent's rules and COORDINATOR.md the main session's
    (a SessionStart hook gives it to the main session only); on Codex AGENTS.md holds both."""

    def test_claude_split_keeps_every_rule(self):
        out = self.tmp / "split"
        _render("answers-claude-lean.json", out)
        with mock.patch.object(render.ADAPTERS["claude"], "coordinator_file", ""):
            _render("answers-claude-lean.json", self.tmp / "whole")
        agents = (out / "AGENTS.md").read_text(encoding="utf-8")
        coord = (out / "COORDINATOR.md").read_text(encoding="utf-8")
        for h in ("## Safety guard", "## Known results", "## Experiments", "## Lean"):
            self.assertIn(h, agents)
            self.assertNotIn(h, coord)
        for h in ("## Commit gate", "## Keep going", "## Research questions", "## Lines of attack"):
            self.assertIn(h, coord)
            self.assertNotIn(h, agents)
        self.assertIn("read COORDINATOR.md before your first action", agents)
        whole = (self.tmp / "whole" / "AGENTS.md").read_text(encoding="utf-8").splitlines()
        have = set(agents.splitlines()) | set(coord.splitlines())
        lost = [ln for ln in whole if ln.strip() and ln not in have]
        # reworded on purpose: the coordinator paragraph (3 lines), the ASK line, the split
        # firsthand line, and the reflection loop's ASK list, which also names COORDINATOR.md
        self.assertLessEqual(len(lost), 6, lost)
        cfg = json.loads((out / ".claude/settings.json").read_text())
        cmds = [h["command"] for g in cfg["hooks"]["SessionStart"] for h in g["hooks"]]
        self.assertEqual(sorted(c.split()[-1] for c in cmds if "coordinator-context" in c), ["1", "2", "3"])

    def test_codex_keeps_one_file(self):
        out = self.tmp / "codex"
        _render("answers-codex-behavior.json", out)
        self.assertFalse((out / "COORDINATOR.md").exists())
        agents = (out / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("## Safety guard", agents)
        self.assertIn("You are the coordinator unless your brief says you are a worker", agents)
        self.assertNotIn("COORDINATOR.md", agents)


class SliceDTests(TempDirCase):
    def test_review_machinery_present(self):
        """The brief, the last look, the re-review limit and the miss line reach the skill and
        the reviewers; the brief nudge is registered for Claude only."""
        for fx in FIXTURES:
            with self.subTest(fx):
                out = self.tmp / fx
                _render(fx, out)
                skills = next(out / d for d in (".claude/skills", ".agents/skills") if (out / d).is_dir())
                gate = (skills / "gate-chain/SKILL.md").read_text(encoding="utf-8")
                for needle in ("## The brief", "LAST LOOK", "**three reviews**", "review-miss:",
                               "owner-decision:", "## Disagreements"):
                    self.assertIn(needle, gate)
                agents = next(out / d for d in (".claude/agents", ".codex/agents") if (out / d).is_dir())
                text = {p.stem: p.read_text(encoding="utf-8") for p in agents.iterdir()}
                self.assertIn("LAST LOOK", text["claim-auditor"])
                self.assertIn("Predicted hardest step:", text["proof-referee"])
                self.assertIn("not checked: statement not supplied", text["proof-referee"])
                self.assertIn("Predicted hardest step:", text["red-team"])
                claude = "claude" in fx
                self.assertEqual("an **adjudicator**" in gate, claude)
                self.assertEqual((out / "hooks/brief-leak-nudge.py").is_file(), claude)
                cfg = out / (".claude/settings.json" if claude else ".codex/hooks.json")
                self.assertEqual("brief-leak-nudge.py" in cfg.read_text(), claude)

    def test_module_text_absent_when_off(self):
        mods = render.load_modules(TEMPLATES)
        for mid, pat in SLICE_D_ONLY.items():
            off = {mid} | {d.id for d in mods if mid in d.depends}
            a = json.loads((FIX / FIXTURES[0]).read_text())
            a["modules"]["disable"] = sorted(set(a["modules"].get("disable") or []) | off)
            a["modules"]["enable"] = [x for x in (a["modules"].get("enable") or []) if x not in off]
            with self.subTest(mid):
                out = self.tmp / f"off-{mid}"
                render.render_project(validate(a), out)
                hits = [rel for rel in _tree(out)
                        if rel.endswith(".md")
                        and pat.search((out / rel).read_text(encoding="utf-8", errors="replace"))]
                self.assertEqual(hits, [])


# Strings that only the attempts module (22) may put into a project. With the module off, a
# mention anywhere (a pointer in another module's doc, a plain script) would dangle.
ATTEMPTS_ONLY = re.compile(
    r"wiki/attempts|bin/attempts|principle-usage|principles\.toml|@principle:|\(principle:|"
    r"AUDIT DUE|STALE:|BUDGET REACHED|stall-audit|load .attack.|\$attack|`attack` skill|"
    r"attack skill|moves\.md|budget_returns|kind = \"move\"")


class AttemptsTests(TempDirCase):
    def test_absent_when_off(self):
        """With the attempts module off, nothing in the project mentions it."""
        for fx in FIXTURES:
            with self.subTest(fx):
                a = json.loads((FIX / fx).read_text())
                a["modules"]["disable"] = sorted(set(a["modules"].get("disable") or []) | {"attempts"})
                out = self.tmp / fx
                render.render_project(validate(a), out)
                hits = [rel for rel in _tree(out)
                        if ATTEMPTS_ONLY.search((out / rel).read_text(encoding="utf-8", errors="replace"))]
                self.assertEqual(hits, [])

    def test_claim_line_and_abstention_reach_the_worker(self):
        """The worker charter and the handoff carry the CLAIM line and the rule that
        abstaining comes after attempting."""
        for fx in FIXTURES:
            with self.subTest(fx):
                out = self.tmp / fx
                _render(fx, out)
                charter = next((out / d).glob("worker.*") for d in (".claude/agents", ".codex/agents")
                               if (out / d).is_dir())
                text = next(charter).read_text(encoding="utf-8")
                self.assertIn("NONE (escalated:", text)
                self.assertIn("abstain after, never instead", text)
                handoff = (out / "docs/templates/worker-handoff.md").read_text(encoding="utf-8")
                self.assertIn("CLAIM:", handoff)
                self.assertIn("Sub-goal:", handoff)

    def test_registry_is_valid(self):
        """The rendered principle registry parses, uses valid ids and trigger values, and
        every home doc it names exists (so a module guard cannot drop a rule's doc while
        keeping its entry)."""
        for fx in FIXTURES:
            with self.subTest(fx):
                out = self.tmp / fx
                _render(fx, out)
                r = subprocess.run([sys.executable, str(out / "bin/principle-usage"), "--check"],
                                   cwd=out, capture_output=True, text=True, timeout=120)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_attack_skill_and_moves(self):
        """Phase 2: the attack skill is emitted for each harness with the Budgets and Audit
        sections the flags name, every registered move has a section in moves.md, and core
        carries the field profile with or without the module."""
        for fx in FIXTURES:
            with self.subTest(fx):
                out = self.tmp / fx
                _render(fx, out)
                skill = next(p for d in (".claude/skills", ".agents/skills")
                             for p in [out / d / "attack/SKILL.md"] if p.is_file())
                text = skill.read_text(encoding="utf-8")
                self.assertIn("## 3. Budgets", text)
                self.assertIn("## 4. Audit (principle: stall-audit)", text)
                with open(out / "docs/principles.toml", "rb") as f:
                    reg = tomllib.load(f)
                moves = [k for k, v in reg.items() if v.get("kind") == "move"]
                self.assertEqual(len(moves), 13)
                doc = (out / "docs/discipline/moves.md").read_text(encoding="utf-8")
                for m in moves:
                    self.assertIn(f"\n## {m}\n", doc)
                with open(out / "project.toml", "rb") as f:
                    cfg = tomllib.load(f)
                self.assertEqual(cfg["field_profile"], {"small_cases_informative": True,
                                                        "construction": False})
                self.assertEqual(cfg["attempts"]["budget_returns"], 4)

    def test_phase2c_text_reaches_the_project(self):
        """The author check, anonymous reviewer briefs, rivals and credence, the experiment
        prediction, the Lean worker's CLAIM line and the core seeds-are-claims rule are all
        emitted where the agents read them."""
        for fx in FIXTURES:
            with self.subTest(fx):
                out = self.tmp / fx
                _render(fx, out)
                skills = next(out / d for d in (".claude/skills", ".agents/skills") if (out / d).is_dir())
                gate = (skills / "gate-chain/SKILL.md").read_text(encoding="utf-8")
                self.assertIn("the author check", gate)
                self.assertIn("Do not tell a reviewer who wrote or proposed the claim", gate)
                self.assertIn("seeds and framings are claims too", (out / "AGENTS.md").read_text(encoding="utf-8"))
                ledger = (out / "docs/discipline/conjecture-ledger.md").read_text(encoding="utf-8")
                self.assertIn("`rivals:`", ledger)
                self.assertIn("`credence:`", ledger)
                readme = out / "experiments/TEMPLATE/README.md"
                if readme.is_file():
                    self.assertIn("## Prediction", readme.read_text(encoding="utf-8"))
                lean = [p for d in (".claude/agents", ".codex/agents") for p in (out / d).glob("lean-worker.*")
                        if (out / d).is_dir()]
                for p in lean:
                    self.assertIn("CLAIM: PROVED", p.read_text(encoding="utf-8"))

    def test_fresh_project_usage_report_sees_a_gap(self):
        """In a project initialised today, a stall audit that came due and was not run shows
        as "trigger seen, unused", not "no data yet" (the registry is younger than the
        30-day window, which must not hide a trigger that already fired)."""
        out = self.tmp / "p"
        _render(FIXTURES[0], out)
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
        for cmd in (["git", "init", "-q"], ["git", "add", "-A"], ["git", "commit", "-qm", "init", "--no-verify"]):
            subprocess.run(cmd, cwd=out, env=env, check=True, capture_output=True)
        att = [sys.executable, str(out / "bin/attempts")]
        for i in (1, 2, 3):
            subprocess.run(att + ["new", "Q001", f"Approach {i}"], cwd=out, check=True, capture_output=True)
            subprocess.run(att + ["set-aside", f"L00{i}", "--broke", "x", "--kind", "method", "--revive", "y"],
                           cwd=out, check=True, capture_output=True)
        r = subprocess.run([sys.executable, str(out / "bin/principle-usage"), "--json"], cwd=out,
                           capture_output=True, text=True, timeout=120)
        rows = {x["id"]: x for x in json.loads(r.stdout)["rows"]}
        self.assertEqual(rows["stall-audit"]["verdict"], "trigger seen, unused", rows["stall-audit"])

    def test_interview_additions_render(self):
        """Phase 3: the field profile, the satellite settings, a question's seed examples and
        a volunteered move reach project.toml, the question file, the registry and moves.md;
        only the answers given are stored."""
        a = json.loads((FIX / FIXTURES[0]).read_text())
        a["field_profile"] = {"small_cases_informative": False, "construction": True}
        a["questions"] = {"satellites": False, "satellites_max": 2}
        a["seeds"]["questions"][0]["examples"] = {"simplest": "l = 5", "outside": "l = 13"}
        a["seeds"]["moves"] = [{"id": "map-attack-boundary", "says": "Map where known attacks break.",
                                "when": "a construction must resist attacks", "construction": True}]
        out = self.tmp / "p"
        render.render_project(validate(a), out, TEMPLATES, a)
        with open(out / "project.toml", "rb") as f:
            cfg = tomllib.load(f)
        self.assertEqual(cfg["field_profile"], {"small_cases_informative": False, "construction": True})
        self.assertEqual((cfg["questions"]["satellites"], cfg["questions"]["satellites_max"]), (False, 2))
        q = next((out / "wiki/questions").glob("Q001-*.md")).read_text(encoding="utf-8")
        self.assertIn("Simplest: l = 5", q)
        self.assertIn("Outside probes: l = 13", q)
        with open(out / "docs/principles.toml", "rb") as f:
            reg = tomllib.load(f)
        self.assertEqual((reg["map-attack-boundary"]["kind"], reg["map-attack-boundary"]["construction"]),
                         ("move", True))
        self.assertIn("## map-attack-boundary", (out / "docs/discipline/moves.md").read_text(encoding="utf-8"))
        r = subprocess.run([sys.executable, str(out / "bin/principle-usage"), "--check"], cwd=out,
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout)
        a2 = json.loads((FIX / FIXTURES[0]).read_text())
        out2 = self.tmp / "q"
        render.render_project(validate(a2), out2, TEMPLATES, a2)
        stored = json.loads((out2 / "docs/init-answers.json").read_text())
        self.assertNotIn("field_profile", stored)  # left to the defaults: not frozen
        a2["seeds"]["moves"] = [{"id": "toy-model", "says": "x"}]
        with self.assertRaises(Exception):
            validate(a2)

    def test_records_do_not_disturb_question_checks(self):
        """Attempt ids (L<nnn>) are invisible to the question tools, which parse A<n> as an
        answer shape: adding records changes neither question-check nor tie-check."""
        out = self.tmp / "p"
        _render(FIXTURES[0], out)
        env = {**os.environ, "ATTEMPTS_TODAY": "2026-01-01"}

        def checks() -> list[tuple[int, str]]:
            res = []
            for tool in ("question-check", "tie-check"):
                r = subprocess.run([sys.executable, str(out / "bin" / tool)], cwd=out,
                                   capture_output=True, text=True, env=env, timeout=120)
                res.append((r.returncode, r.stdout))
            return res

        before = checks()
        r = subprocess.run([sys.executable, str(out / "bin/attempts"), "new", "Q001",
                            "Induction on the size, see A1"], cwd=out, capture_output=True,
                           text=True, env=env, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((out / "wiki/attempts/L001-induction-on-the-size-see.md").is_file())
        self.assertEqual(checks(), before)


# Argued-evidence terms that only the tiers module (13) and the conjecture ledger (02) may put into
# a project's documents. Scripts and hooks may name them (they guard at runtime), so only
# documents, agent files and skills are scanned.
ARGUED_ONLY = re.compile(r"\bARGUED\b")
CONJECTURES_ONLY = re.compile(r"@assumes|bin/residues|owner-override|conditional-on:|`argued:`")


def _doc_files(out: Path) -> list[str]:
    return [rel for rel in _tree(out) if rel.endswith(".md") and not rel.startswith(("bin/", "hooks/", ".githooks/"))]


class InformalArgumentTests(TempDirCase):
    def test_argued_verdict_and_method_reach_the_project(self):
        for fx in FIXTURES:
            with self.subTest(fx):
                out = self.tmp / fx
                _render(fx, out)
                charter = next(p for d in (".claude/agents", ".codex/agents") for p in (out / d).glob("worker.*")
                               if (out / d).is_dir())
                self.assertIn("ARGUED (", charter.read_text(encoding="utf-8"))
                self.assertIn("ARGUED (", (out / "docs/templates/worker-handoff.md").read_text(encoding="utf-8"))
                doc = (out / "docs/discipline/informal-arguments.md").read_text(encoding="utf-8")
                self.assertIn("## Perturb, do not reread", doc)
                self.assertTrue((out / "docs/templates/informal-argument.md").is_file())
                with open(out / "project.toml", "rb") as f:
                    self.assertIn("heuristic", tomllib.load(f)["arguments"]["labels"])

    def test_interview_labels_extend_the_vocabulary(self):
        a = json.loads((FIX / FIXTURES[0]).read_text())
        a["arguments"] = {"labels": ["numerical"]}
        out = self.tmp / "labels"
        render.render_project(validate(a), out, TEMPLATES, a)
        with open(out / "project.toml", "rb") as f:
            labels = tomllib.load(f)["arguments"]["labels"]
        self.assertEqual(labels[-1], "numerical")
        self.assertIn("heuristic", labels)
        a["arguments"] = {"labels": ["Not A Word"]}
        with self.assertRaises(Exception):
            validate(a)

    def _render_without(self, fx: str, off: set[str]) -> Path:
        a = json.loads((FIX / fx).read_text())
        mods = render.load_modules(TEMPLATES)
        off = set(off)
        while True:  # also switch off whatever depends on a module switched off
            more = {m.id for m in mods if set(m.depends) & off} - off
            if not more:
                break
            off |= more
        a["modules"]["disable"] = sorted(set(a["modules"].get("disable") or []) | off)
        out = self.tmp / (fx + "-" + "-".join(sorted(off)))
        render.render_project(validate(a), out)
        return out

    def test_argued_absent_without_tiers(self):
        for fx in FIXTURES:
            with self.subTest(fx):
                out = self._render_without(fx, {"tiers"})
                hits = [r for r in _doc_files(out) if ARGUED_ONLY.search((out / r).read_text(encoding="utf-8"))]
                self.assertEqual(hits, [])

    def test_assumptions_absent_without_conjectures(self):
        for fx in FIXTURES:
            with self.subTest(fx):
                out = self._render_without(fx, {"conjectures"})
                hits = [r for r in _doc_files(out) if CONJECTURES_ONLY.search((out / r).read_text(encoding="utf-8"))]
                self.assertEqual(hits, [])


class ResolutionTests(unittest.TestCase):
    def setUp(self):
        self.mods = render.load_modules(TEMPLATES)
        self.base = validate(json.loads((FIX / FIXTURES[0]).read_text()))

    def test_core_cannot_be_disabled(self):
        a = json.loads(json.dumps(self.base))
        a["modules"]["disable"] = ["core"]
        with self.assertRaises(render.RenderError):
            render.resolve_enabled(self.mods, a)

    def test_unknown_module_rejected(self):
        a = json.loads(json.dumps(self.base))
        a["modules"]["disable"] = ["no-such-module"]
        with self.assertRaises(render.RenderError):
            render.resolve_enabled(self.mods, a)

    def test_catalog_typo_fails_render(self):
        with tempfile.TemporaryDirectory() as d:
            t = Path(d) / "t"
            shutil.copytree(TEMPLATES, t)
            frag = t / "core" / "AGENTS.fragment.md.tmpl"
            frag.write_text("{{#if modules.questoins}}x{{/if}}\n")
            with self.assertRaises(render.RenderError):
                render.render_project(self.base, Path(d) / "out", t)


class RefusalTests(TempDirCase):
    def test_nonempty_target_refused(self):
        (self.tmp / "keep.txt").write_text("x")
        with self.assertRaises(render.RenderError):
            _render(FIXTURES[0], self.tmp)

    def test_bad_answers(self):
        with self.assertRaises(AnswersError):
            validate({"project": {"name": "x"}})
        bad = json.loads((FIX / FIXTURES[0]).read_text())
        bad["seeds"]["conjectures"][0]["questions"] = ["Q009"]
        with self.assertRaises(AnswersError):
            validate(bad)

    def test_seed_slugs_and_ids(self):
        base = json.loads((FIX / FIXTURES[0]).read_text())
        for mutate, why in [
            (lambda a: a["seeds"]["sources"][0].update(slug="../escape"), "path in slug"),
            (lambda a: a["seeds"]["conjectures"][0].update(questions=[]), "conjecture with no question"),
            (lambda a: a["seeds"]["questions"].append(dict(a["seeds"]["questions"][0], id="Q001")),
             "duplicate id"),
        ]:
            with self.subTest(why):
                a = json.loads(json.dumps(base))
                mutate(a)
                with self.assertRaises(AnswersError):
                    validate(a)
        a = json.loads(json.dumps(base))
        a["seeds"]["sources"] = [{"cite": "Same Title"}, {"cite": "Same Title"}]
        slugs = [s["slug"] for s in validate(a)["seeds"]["sources"]]
        self.assertEqual(slugs, ["same-title", "same-title-2"])

    def test_slugs_keep_comparison_signs(self):
        self.assertEqual(slugify("No congruences for 13 ≤ l ≤ 31"), "no-congruences-for-13-le-l-le-31")
        self.assertEqual(slugify("a <= b, c >= d, e != f, p > k"), "a-le-b-c-ge-d-e-ne-f-p-gt-k")
        self.assertEqual(slugify("Thomassé"), "thomasse")

    def test_tie_must_cite_answer_shapes_as_numbers(self):
        base = json.loads((FIX / FIXTURES[2]).read_text())
        self.assertEqual(warnings_for(validate(base)), [])  # its tie cites A2 of Q001
        for tie, want in [
            ("If true, answer shape (a) holds for every large k.", "names an answer shape as (a)"),
            ("If true, A5 is answered with an explicit bound.", "cites A5, which no linked question"),
        ]:
            with self.subTest(tie):
                a = json.loads(json.dumps(base))
                a["seeds"]["conjectures"][0]["tie"] = tie
                w = warnings_for(validate(a))
                self.assertTrue(any(want in x for x in w), w)

    def test_cli(self):
        out = self.tmp / "cli out"
        r = subprocess.run([sys.executable, "-m", "renderer", "--answers", str(FIX / FIXTURES[1]),
                            "--out", str(out)], cwd=ROOT / "skills/init-math/scripts",
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["harness"], "codex")


if __name__ == "__main__":
    unittest.main()
