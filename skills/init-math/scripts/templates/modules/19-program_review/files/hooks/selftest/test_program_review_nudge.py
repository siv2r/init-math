"""Selftest for hooks/program-review-nudge.py through its real entry point.

Four branches (docs/discipline/hook-authoring.md): allow, trigger, bypass, failure.
"""
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "program-review-nudge.py"


def stop(active=False):
    return json.dumps({"hook_event_name": "Stop", "session_id": "s1", "cwd": "/tmp",
                       "stop_hook_active": active})


@unittest.skipUnless(shutil.which("git"), "git not installed")
class ProgramReviewNudge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "project.toml").write_text(
            '[project]\nowner = "Ada"\n\n[program_review]\nevery_days = 21\n')
        (self.root / "notes").mkdir()
        self.reviews = self.root / "notes" / "program-reviews.md"
        self.reviews.write_text("# Program reviews\n")
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith("GIT_") and k != "HOOKS_QUIET"}
        self.env.update({"CLAUDE_PROJECT_DIR": str(self.root), "GIT_CONFIG_GLOBAL": os.devnull,
                         "GIT_CONFIG_NOSYSTEM": "1"})
        self.git("init", "-q")
        self.commit("init", "2026-01-01T12:00:00")
        self.commit("work", "2026-01-10T12:00:00")

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args, env=None):
        return subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=t@example.org",
                               "-c", "commit.gpgsign=false", *args], cwd=self.root,
                              capture_output=True, text=True, env=env or self.env, timeout=60)

    def commit(self, msg, date):
        env = {**self.env, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
        self.git("commit", "-q", "--allow-empty", "-m", msg, env=env)

    def run_hook(self, stdin, env=None, harness="claude"):
        return subprocess.run([sys.executable, str(HOOK), "--harness", harness], input=stdin,
                              capture_output=True, text=True, env=env or self.env, timeout=30)

    # 1. allow: a recent review, or no work since the last one
    def test_allow(self):
        self.reviews.write_text(f"# Program reviews\n\n## {dt.date.today()} — program review\n")
        self.assertEqual(self.run_hook(stop()).returncode, 0)
        self.reviews.write_text("# Program reviews\n\n## 2026-01-20 — program review\n")
        r = self.run_hook(stop())  # overdue, but nothing was committed after 2026-01-20
        self.assertEqual((r.returncode, r.stderr), (0, ""))

    # 2. trigger: overdue with work since; once per week; Codex gets the JSON form
    def test_trigger(self):
        r = self.run_hook(stop())
        self.assertEqual(r.returncode, 2)
        self.assertIn("program review is due", r.stderr)
        self.assertIn("since the project started on 2026-01-01", r.stderr)
        self.assertIn("offer Ada one", r.stderr)
        self.assertEqual(self.run_hook(stop()).returncode, 0)  # not again this week
        self.reviews.write_text("# Program reviews\n\n## 2026-01-05 — program review\n")
        r = self.run_hook(stop(), harness="codex")
        self.assertEqual(r.returncode, 0)
        self.assertIn("The last one was on 2026-01-05", json.loads(r.stdout)["reason"])

    # 3. bypass: continuation turn, HOOKS_QUIET, every_days = 0
    def test_bypass(self):
        self.assertEqual(self.run_hook(stop(active=True)).returncode, 0)
        r = self.run_hook(stop(), env={**self.env, "HOOKS_QUIET": "1"})
        self.assertEqual(r.returncode, 0)
        (self.root / "project.toml").write_text("[program_review]\nevery_days = 0\n")
        self.assertEqual(self.run_hook(stop()).returncode, 0)

    # 4. failure: fail open, loudly
    def test_failure(self):
        r = self.run_hook("{not json")
        self.assertEqual(r.returncode, 0)
        self.assertIn("WARNING", r.stderr)
        (self.root / "project.toml").write_text("[program_review]\nevery_days = 'often'\n")
        r = self.run_hook(stop())
        self.assertEqual(r.returncode, 0)
        self.assertIn("WARNING", r.stderr)
        self.assertTrue((self.root / "logs" / "state" / "hook-errors.log").exists())


if __name__ == "__main__":
    unittest.main()
