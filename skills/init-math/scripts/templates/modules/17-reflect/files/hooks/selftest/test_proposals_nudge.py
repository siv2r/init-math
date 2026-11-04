"""Selftest for hooks/proposals-nudge.py through its real entry point.

Four branches (docs/discipline/hook-authoring.md): allow, trigger, bypass, failure.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "proposals-nudge.py"


def stop(session="s1", active=False):
    return json.dumps({"hook_event_name": "Stop", "session_id": session, "cwd": "/tmp",
                       "stop_hook_active": active})


def proposal(pid, text):
    return json.dumps({"ts": "2026-10-21T10:00:00", "kind": "proposal", "id": pid,
                       "source": "retro", "text": text}) + "\n"


class ProposalsNudge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "project.toml").write_text('[project]\nowner = "Ada"\n')
        (self.root / "logs" / "state").mkdir(parents=True)
        self.log = self.root / "logs" / "proposals.jsonl"
        self.env = {**os.environ, "CLAUDE_PROJECT_DIR": str(self.root)}
        self.env.pop("HOOKS_QUIET", None)

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, stdin, env=None, harness="claude"):
        return subprocess.run([sys.executable, str(HOOK), "--harness", harness], input=stdin,
                              capture_output=True, text=True, env=env or self.env, timeout=30)

    # 1. allow: nothing queued, or everything decided
    def test_allow(self):
        self.assertEqual(self.run_hook(stop()).returncode, 0)
        self.log.write_text(proposal("P1a2b", "public-only references")
                            + json.dumps({"kind": "decision", "of": "P1a2b", "decision": "no"}) + "\n")
        r = self.run_hook(stop())
        self.assertEqual((r.returncode, r.stderr), (0, ""))

    # 2. trigger: list new proposals once; then one reminder per session; Codex JSON form
    def test_trigger(self):
        self.log.write_text(proposal("P1a2b", "public-only references in final papers"))
        r = self.run_hook(stop())
        self.assertEqual(r.returncode, 2)
        self.assertIn("have not been put to them yet", r.stderr)
        self.assertIn("P1a2b (retro): public-only references", r.stderr)
        self.assertIn("numbered list", r.stderr)
        # not shown yet, but this set was already raised: the session reminder instead
        r = self.run_hook(stop())
        self.assertEqual(r.returncode, 2)
        self.assertIn("still wait for Ada's decision", r.stderr)
        self.assertEqual(self.run_hook(stop()).returncode, 0)  # once per session
        (self.root / "logs" / "state" / "proposals.shown").write_text("P1a2b\n")
        r = self.run_hook(stop(session="s2"), harness="codex")
        self.assertEqual(r.returncode, 0)
        self.assertIn("still wait", json.loads(r.stdout)["reason"])
        with open(self.log, "a") as f:  # a new proposal is raised again, listing both
            f.write(proposal("P9f9f", "lower the compaction limit"))
        r = self.run_hook(stop(session="s2"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("P1a2b", r.stderr)
        self.assertIn("P9f9f", r.stderr)

    # 3. bypass: continuation turn, HOOKS_QUIET
    def test_bypass(self):
        self.log.write_text(proposal("P1a2b", "x"))
        self.assertEqual(self.run_hook(stop(active=True)).returncode, 0)
        r = self.run_hook(stop(), env={**self.env, "HOOKS_QUIET": "1"})
        self.assertEqual(r.returncode, 0)

    # 4. failure: fail open, loudly; a corrupt row is skipped, not fatal
    def test_failure(self):
        r = self.run_hook("{not json")
        self.assertEqual(r.returncode, 0)
        self.assertIn("WARNING", r.stderr)
        self.log.write_text("not json\n" + proposal("P1a2b", "x"))
        self.assertEqual(self.run_hook(stop()).returncode, 2)
        (self.root / "project.toml").write_text("[project\n")
        r = self.run_hook(stop(session="s3"))
        self.assertEqual(r.returncode, 0)
        self.assertIn("WARNING", r.stderr)


if __name__ == "__main__":
    unittest.main()
