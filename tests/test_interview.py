"""Interview skill + init orchestrator: the question bank covers the answers contract, and
`init_project.py` creates a committed, self-testing project (or refuses cleanly)."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/init-math"
INIT = SKILL / "scripts/init_project.py"
FIX = ROOT / "tests/fixtures"
sys.path.insert(0, str(SKILL / "scripts"))
from renderer.answers import REQUIRED_KEYS  # noqa: E402

ENV = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
       # an isolated git identity, so the test never depends on the machine's config
       "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(INIT), *args], capture_output=True, text=True,
                          env=ENV, timeout=600)


class QuestionBankTests(unittest.TestCase):
    def test_required_keys_are_asked(self):
        text = (SKILL / "questions.md").read_text()
        for key in REQUIRED_KEYS:
            with self.subTest(key):
                self.assertIn(f"`{key}`", text)

    def test_optional_interview_keys_are_asked(self):
        """The three optional choices (one active question, run limits, exposition slots)."""
        text = (SKILL / "questions.md").read_text()
        for key in ("seeds.active_question", "experiments.limits", "exposition.prior_work",
                    "exposition.model_text"):
            with self.subTest(key):
                self.assertIn(f"`{key}`", text)
        self.assertIn("project.toml", text.split("### Run limits", 1)[1].split("##", 1)[0])

    def test_skill_frontmatter(self):
        text = (SKILL / "SKILL.md").read_text()
        m = re.match(r"---\nname: init-math\ndescription: (.+?)\n---\n", text, re.S)
        self.assertTrue(m, "SKILL.md needs name + description frontmatter")

    def test_example_shape_validates(self):
        """The answers.json shape shown in questions.md is a valid contract once filled."""
        text = (SKILL / "questions.md").read_text()
        block = text.split("## answers.json shape", 1)[1].split("```json", 1)[1].split("```", 1)[0]
        a = json.loads(block)
        a["project"].update(name="X", owner="Y", field="Z")
        a["seeds"]["questions"][0].update(sentence="Is it?", answer_shapes=["yes"])
        a["seeds"]["conjectures"][0]["statement"] = "It is."
        a["seeds"]["sources"][0]["cite"] = "A paper"
        a["stack"].update(run_cmd="gp -q {driver}", research_commands=["gp"])
        from renderer.answers import validate
        out = validate(a)
        labels = [s["label"] for s in out["stack"]["failure_signatures"]]
        self.assertIn("gp-error", labels)  # left out -> the defaults for the tools named

    def test_failure_signature_defaults(self):
        import re
        from renderer.answers import default_signatures, validate
        sigs = default_signatures(["/opt/bin/gp", "python3", "magma"])
        labels = [s["label"] for s in sigs]
        self.assertEqual(labels, ["out-of-memory", "stack-overflow", "gp-error", "magma-error"])
        pats = {s["label"]: re.compile(s["regex"]) for s in sigs}
        # the failure hook searches the whole output, so line anchors must be multiline
        self.assertTrue(pats["gp-error"].search("? f(1)\n  ***   at top-level: f(1)\n"))
        self.assertTrue(pats["out-of-memory"].search("Fatal: Out of memory"))
        self.assertFalse(pats["gp-error"].search("result 3 *** 4"))
        self.assertIn("gap-error", [s["label"] for s in default_signatures(["gap"])])
        self.assertTrue(re.compile(default_signatures(["gap"])[-1]["regex"]).search("x\nError, oops"))

        def stack(**s):
            base = {"project": {"name": "X", "owner": "Y", "field": "Z",
                                "research_kinds": ["experiment"]},
                    "harness": "claude",
                    "seeds": {"questions": [{"sentence": "Is it?", "answer_shapes": ["yes"]}]},
                    "stack": dict(research_commands=["gp"], **s)}
            return validate(base)["stack"]["failure_signatures"]
        self.assertEqual(len(stack()), 3)                    # key absent -> defaults
        self.assertEqual(stack(failure_signatures=[]), [])   # explicit [] -> none
        own = stack(failure_signatures=[{"label": "nc", "regex": "did not converge"}])
        self.assertEqual([s["label"] for s in own], ["nc"])  # explicit list replaces


class DriverNameTests(unittest.TestCase):
    def test_default_driver(self):
        from renderer.answers import default_driver
        cases = {"gp -q {driver}": "driver.gp", "python3 {driver}": "driver.py",
                 "/usr/local/bin/python3.12 -B {driver}": "driver.py",
                 "env OMP_NUM_THREADS=1 magma -b {driver}": "driver.m",
                 "sage {driver}": "driver.sage", "julia --project {driver}": "driver.jl",
                 "mytool {driver}": "driver.py", "": "driver.py"}
        for cmd, want in cases.items():
            with self.subTest(cmd):
                self.assertEqual(default_driver(cmd), want)

    def test_explicit_driver_wins_and_is_checked(self):
        from renderer.answers import AnswersError, validate
        base = json.loads((FIX / "answers-claude-lean.json").read_text())
        base["stack"]["run_cmd"] = "gp -q {driver}"
        self.assertEqual(validate(base)["stack"]["driver"], "driver.gp")
        base["stack"]["driver"] = "main.g"
        self.assertEqual(validate(base)["stack"]["driver"], "main.g")
        base["stack"]["driver"] = "sub/main.g"
        with self.assertRaises(AnswersError):
            validate(base)


class SlugTests(unittest.TestCase):
    def test_accents_fold(self):
        from renderer.answers import slugify
        self.assertEqual(slugify("Brandt, Thomassé: Erdős–Simonovits"),
                         "brandt-thomasse-erdos-simonovits")
        self.assertEqual(slugify("???"), "project")


class InitProjectTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="init-math interview ")
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_list_modules_json(self):
        r = run("--list-modules", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(r.stdout)
        self.assertIn("not_built", data)

    def test_check_answers(self):
        r = run("--check-answers", str(FIX / "answers-codex-theory.json"))
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["harness"], "codex")
        self.assertEqual(out["active_question"], "Q001")
        self.assertEqual(out["seeds"], {"questions": 1, "conjectures": 0, "sources": 0, "moves": 0})
        self.assertIsNone(out["experiment_limits"])  # theory-only: experiments is off

    def test_check_answers_reports_error(self):
        bad = self.tmp / "bad.json"
        bad.write_text(json.dumps({"project": {"name": "x"}}))
        r = run("--check-answers", str(bad))
        self.assertEqual(r.returncode, 1)
        self.assertIn("error:", r.stderr)

    def test_version_from_an_installed_plugin(self):
        """An installed plugin copy has no .git; Claude Code's install record has the commit."""
        sys.path.insert(0, str(SKILL / "scripts"))
        import init_project
        root = self.tmp / "cache/init-math/init-math/0.1.0"
        (root / ".claude-plugin").mkdir(parents=True)
        (root / ".claude-plugin/plugin.json").write_text('{"version": "0.1.0"}')
        cfg = self.tmp / "claude"
        (cfg / "plugins").mkdir(parents=True)
        self.assertEqual(init_project.init_math_version(root, cfg), "0.1.0")
        (cfg / "plugins/installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": {
            "init-math@init-math": [{"installPath": str(root), "version": "0.1.0",
                                     "gitCommitSha": "d2fdfd15e26d3b52dd3b1ce630c19b64d7bb5e49"}]}}))
        self.assertEqual(init_project.init_math_version(root, cfg), "0.1.0 (commit d2fdfd1)")

    def test_create_commits_and_selftests(self):
        for fx in ("answers-claude-lean.json", "answers-codex-theory.json"):
            with self.subTest(fx):
                out = self.tmp / fx.replace(".json", "")
                r = run("--answers", str(FIX / fx), "--out", str(out))
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                log = subprocess.run(["git", "-C", str(out), "log", "--format=%s"],
                                     capture_output=True, text=True, env=ENV).stdout.split("\n")
                self.assertTrue(log[0].startswith("init: "), log)
                body = subprocess.run(["git", "-C", str(out), "log", "-1", "--format=%b"],
                                      capture_output=True, text=True, env=ENV).stdout
                self.assertRegex(body, r"init-math version: \d+\.\d+\.\d+ \(commit [0-9a-f]+\)")
                st = subprocess.run(["git", "-C", str(out), "status", "--porcelain"],
                                    capture_output=True, text=True, env=ENV).stdout
                self.assertEqual(st.strip(), "", "the initial commit must include everything")
                self.assertIn("Next steps:", r.stdout)
                active = "Q001 is active, as you chose" in r.stdout
                self.assertEqual(active, fx == "answers-codex-theory.json", r.stdout)

    def test_refuses_non_empty(self):
        out = self.tmp / "busy"
        out.mkdir()
        (out / "keep.txt").write_text("mine")
        r = run("--answers", str(FIX / "answers-codex-theory.json"), "--out", str(out))
        self.assertEqual(r.returncode, 1)
        self.assertIn("not empty", r.stderr)
        self.assertEqual(sorted(p.name for p in out.iterdir()), ["keep.txt"])


def _answers(**over):
    a = {"project": {"name": "X", "owner": "Y", "field": "Z", "research_kinds": ["theory"]},
         "harness": "claude",
         "seeds": {"questions": [{"sentence": "Is every partition congruence modular?",
                                  "answer_shapes": ["yes: a proof"], "why": "w"}],
                   "conjectures": [{"statement": "All such congruences are Ramanujan type.",
                                    "questions": ["Q001"],
                                    "tie": "A counterexample would rule out the finite-list answer.",
                                    "family": "primes below 100"}]}}
    for k, v in over.items():
        a[k] = v
    return a


class CheckTargetTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="init-math target ")
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_empty_and_missing_ok_even_with_space(self):
        empty = self.tmp / "empty dir"
        empty.mkdir()
        self.assertEqual(run("--check-target", str(empty)).returncode, 0)
        self.assertEqual(run("--check-target", str(self.tmp / "new project")).returncode, 0)

    def test_non_empty_refused_with_create_message(self):
        busy = self.tmp / "busy"
        busy.mkdir()
        (busy / "keep.txt").write_text("mine")
        r = run("--check-target", str(busy))
        self.assertEqual(r.returncode, 1)
        self.assertIn("is not empty; init-math only writes into a new or empty directory", r.stderr)

    def test_windows_drive_refused_under_wsl(self):
        """A project on C: is opened from a Windows-side session that loads none of it
        (colleague trial on Codex, 2026-10-22); create refuses it before rendering."""
        def run_wsl(flag: str, *args: str) -> subprocess.CompletedProcess:
            return subprocess.run([sys.executable, str(INIT), *args], capture_output=True,
                                  text=True, env={**ENV, "INIT_MATH_WSL": flag}, timeout=600)
        target = "/mnt/c/Users/someone/Documents/new-project"
        r = run_wsl("1", "--check-target", target)
        self.assertEqual(r.returncode, 1)
        self.assertIn("is on the Windows drive", r.stderr)
        self.assertIn("~/research/<slug>", r.stderr)
        r = run_wsl("1", "--answers", str(FIX / "answers-codex-theory.json"), "--out", target)
        self.assertEqual(r.returncode, 1)
        self.assertIn("is on the Windows drive", r.stderr)
        self.assertNotIn("Windows drive", run_wsl("0", "--check-target", target).stderr)
        self.assertEqual(run_wsl("1", "--check-target", str(self.tmp / "p")).returncode, 0)

    @unittest.skipIf(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                     "permission bits not enforced")
    def test_unwritable_refused(self):
        ro = self.tmp / "ro"
        ro.mkdir()
        ro.chmod(0o500)
        try:
            r = run("--check-target", str(ro / "child"))
            self.assertEqual(r.returncode, 1)
            self.assertIn("not writable", r.stderr)
        finally:
            ro.chmod(0o700)


class AnswersDiagnosticsTests(unittest.TestCase):
    def test_question_error_has_key_path_and_content(self):
        from renderer.answers import AnswersError, validate
        a = _answers()
        a["seeds"]["questions"][0]["answer_shapes"] = [""]
        with self.assertRaises(AnswersError) as cm:
            validate(a)
        msg = str(cm.exception)
        self.assertIn('seeds.questions[0] (Q001 "Is every partition congruence modular?")', msg)
        self.assertIn("answer shape", msg)

    def test_conjecture_error_has_statement(self):
        from renderer.answers import AnswersError, validate
        a = _answers()
        a["seeds"]["conjectures"][0]["questions"] = []
        with self.assertRaises(AnswersError) as cm:
            validate(a)
        msg = str(cm.exception)
        self.assertIn("seeds.conjectures[0] (C001", msg)
        self.assertIn("All such congruences", msg)

    def test_placeholder_tie_warns(self):
        from renderer.answers import validate, warnings_for
        self.assertEqual(warnings_for(validate(_answers())), [])
        for bad in ("whatever you recommend", "tbd", "It would change the answer a lot, n/a"):
            a = _answers()
            a["seeds"]["conjectures"][0]["tie"] = bad
            w = warnings_for(validate(a))
            self.assertEqual(len(w), 1, bad)
            self.assertIn("seeds.conjectures[0]", w[0])

    def test_lake_path_warns(self):
        from renderer.answers import validate, warnings_for
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            a = _answers(stack={"proof_assistant": "lean", "lake_path": str(d / "missing")})
            self.assertIn("not a directory", warnings_for(validate(a))[0])
            a = _answers(stack={"proof_assistant": "lean", "lake_path": str(d)})
            w = " ".join(warnings_for(validate(a)))
            self.assertIn("lakefile", w)
            self.assertIn("lean-toolchain", w)
            (d / "lakefile.toml").write_text("")
            (d / "lean-toolchain").write_text("x")
            self.assertEqual(warnings_for(validate(a)), [])
            rel = _answers(stack={"proof_assistant": "lean", "lake_path": "sub"})
            self.assertIn("not a directory", warnings_for(validate(rel), d)[0])

    def test_check_answers_cli_shows_warnings_and_off_reasons(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "a.json"
            a = _answers()
            a["seeds"]["conjectures"][0]["tie"] = "tbd"
            p.write_text(json.dumps(a))
            r = run("--check-answers", str(p))
            self.assertEqual(r.returncode, 0, r.stderr)
            out = json.loads(r.stdout)
            self.assertTrue(out["warnings"])
            self.assertIn("proof_assistant is none", out["modules_off_why"].get("lean", ""))


if __name__ == "__main__":
    unittest.main()
