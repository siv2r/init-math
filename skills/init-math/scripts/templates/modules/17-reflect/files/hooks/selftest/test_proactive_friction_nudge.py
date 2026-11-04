"""Selftest for hooks/proactive-friction-nudge.py through its real entry point.

Four branches (docs/discipline/hook-authoring.md): allow, trigger, bypass, failure.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "proactive-friction-nudge.py"


def stop(active=False):
    return json.dumps({"hook_event_name": "Stop", "session_id": "s1", "cwd": "/tmp",
                       "stop_hook_active": active})


class ProactiveFrictionNudge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "project.toml").write_text("[reflect]\nfriction_nudge_every = 3\n")
        self.env = {**os.environ, "CLAUDE_PROJECT_DIR": str(self.root)}
        for k in ("HOOKS_QUIET", "FRICTION_NUDGE_EVERY"):
            self.env.pop(k, None)

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, stdin, env=None, harness="claude"):
        return subprocess.run([sys.executable, str(HOOK), "--harness", harness], input=stdin,
                              capture_output=True, text=True, env=env or self.env, timeout=30)

    # 1. allow: quiet before the Nth stop, and quiet after friction was logged
    def test_allow(self):
        for _ in range(2):
            self.assertEqual(self.run_hook(stop()).returncode, 0)
        logs = self.root / "logs"
        logs.mkdir(exist_ok=True)
        (logs / "friction.jsonl").write_text('{"kind":"x","text":"y","source":"agent"}\n')
        r = self.run_hook(stop())  # 3rd stop, but friction was just logged: restart
        self.assertEqual((r.returncode, r.stderr), (0, ""))

    # 2. trigger: every Nth stop; Codex gets the JSON form
    def test_trigger(self):
        for _ in range(2):
            self.run_hook(stop())
        r = self.run_hook(stop())
        self.assertEqual(r.returncode, 2)
        self.assertIn("friction skill", r.stderr)
        for _ in range(2):
            self.run_hook(stop(), harness="codex")
        r = self.run_hook(stop(), harness="codex")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(json.loads(r.stdout)["decision"], "block")

    # 3. bypass: continuation turn, HOOKS_QUIET, period 0
    def test_bypass(self):
        for _ in range(5):
            self.assertEqual(self.run_hook(stop(active=True)).returncode, 0)
        for _ in range(5):
            r = self.run_hook(stop(), env={**self.env, "HOOKS_QUIET": "1"})
            self.assertEqual(r.returncode, 0)
        for _ in range(5):
            r = self.run_hook(stop(), env={**self.env, "FRICTION_NUDGE_EVERY": "0"})
            self.assertEqual(r.returncode, 0)

    # 4. failure: fail open, loudly
    def test_failure(self):
        r = self.run_hook("{not json")
        self.assertEqual(r.returncode, 0)
        self.assertIn("WARNING", r.stderr)
        r = self.run_hook(stop(), env={**self.env, "FRICTION_NUDGE_EVERY": "often"})
        self.assertEqual(r.returncode, 0)
        self.assertIn("WARNING", r.stderr)
        self.assertTrue((self.root / "logs" / "state" / "hook-errors.log").exists())


if __name__ == "__main__":
    unittest.main()
