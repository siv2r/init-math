"""Selftest for hooks/agent-brief-lint.py, through its real entry point."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "agent-brief-lint.py"


def run(root, payload=None, raw=None, **env_extra):
    env = {k: v for k, v in os.environ.items() if k not in ("HOOKS_QUIET", "AGENT_BRIEF_OK")}
    env["CLAUDE_PROJECT_DIR"] = root
    env.update(env_extra)
    data = raw if raw is not None else json.dumps(payload)
    return subprocess.run([sys.executable, str(HOOK), "--harness", "claude"], input=data,
                          capture_output=True, text=True, env=env, timeout=30)


def spawn(prompt):
    return {"hook_event_name": "PreToolUse", "tool_name": "Agent",
            "tool_input": {"subagent_type": "worker", "prompt": prompt}}


class AgentBriefLint(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_allow_clean_brief(self):
        r = run(self.root, spawn("Prove lemma 3 in notes/lemmas.md; validate on n = 5 and return."))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_allow_compliant_brief(self):
        r = run(self.root, spawn("Validate on n = 5 and return the command; I will run the full "
                                 "sweep. Do not run it in the background."))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_allow_other_tool(self):
        r = run(self.root, {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                            "tool_input": {"command": "echo run the full sweep yourself"}})
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_trigger_then_reissue_proceeds(self):
        p = spawn("Build the driver, then run the full sweep yourself and report the table.")
        r = run(self.root, p)
        self.assertEqual(r.returncode, 2)
        self.assertIn("agent-brief-lint", r.stderr)
        self.assertIn("RETURN the exact run command", r.stderr)
        self.assertEqual(run(self.root, p).returncode, 0)

    def test_trigger_timing_probe(self):
        r = run(self.root, spawn("First, time a few representative cases to project the cost."))
        self.assertEqual(r.returncode, 2)

    def test_bypass(self):
        r = run(self.root, spawn("Run the full sweep yourself."), AGENT_BRIEF_OK="1")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_failure_fails_open_loudly(self):
        r = run(self.root, raw="{not json")
        self.assertEqual(r.returncode, 0)
        self.assertIn("WARNING", r.stderr)
        self.assertTrue((Path(self.root) / "logs/state/hook-errors.log").exists())


if __name__ == "__main__":
    unittest.main()
