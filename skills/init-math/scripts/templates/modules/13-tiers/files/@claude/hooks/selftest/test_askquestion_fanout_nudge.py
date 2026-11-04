"""Selftest for hooks/askquestion-fanout-nudge.py, through its real entry point."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "askquestion-fanout-nudge.py"


def run(root, payload=None, raw=None, **env_extra):
    env = {k: v for k, v in os.environ.items() if k not in ("HOOKS_QUIET", "ASKQ_FANOUT_OK")}
    env["CLAUDE_PROJECT_DIR"] = root
    env.update(env_extra)
    data = raw if raw is not None else json.dumps(payload)
    return subprocess.run([sys.executable, str(HOOK), "--harness", "claude"], input=data,
                          capture_output=True, text=True, env=env, timeout=30)


def ask(n_options, multi=False):
    opts = [{"label": f"option {i}", "description": "a thread"} for i in range(n_options)]
    return {"hook_event_name": "PreToolUse", "tool_name": "AskUserQuestion",
            "tool_input": {"questions": [{"question": "Which next?", "header": "Next",
                                          "multiSelect": multi, "options": opts}]}}


class AskFanout(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_allow_two_options(self):
        self.assertEqual(run(self.root, ask(2)).returncode, 0)

    def test_allow_multiselect(self):
        self.assertEqual(run(self.root, ask(4, multi=True)).returncode, 0)

    def test_trigger_then_reissue_proceeds(self):
        r = run(self.root, ask(3))
        self.assertEqual(r.returncode, 2)
        self.assertIn("genuine fork", r.stderr)
        self.assertEqual(run(self.root, ask(3)).returncode, 0)

    def test_bypass(self):
        self.assertEqual(run(self.root, ask(4), ASKQ_FANOUT_OK="1").returncode, 0)

    def test_failure_fails_open_loudly(self):
        r = run(self.root, raw="[1, 2")
        self.assertEqual(r.returncode, 0)
        self.assertIn("WARNING", r.stderr)
        self.assertTrue((Path(self.root) / "logs/state/hook-errors.log").exists())


if __name__ == "__main__":
    unittest.main()
