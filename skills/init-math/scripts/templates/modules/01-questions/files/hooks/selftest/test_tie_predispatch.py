"""Selftest for hooks/tie-predispatch.py through its real entry point (JSON on stdin).

Four branches: allow, trigger, bypass, failure.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "tie-predispatch.py"

UNTIED = "Run the sweep for C002 at n = 7 and report the largest cap found."
TIED = UNTIED + "\n\n## Question tie\nquestion: Q002 / A2\nvia: C002\nkind: decides\n"


def spawn(prompt, agent="worker", tool="Agent", key="subagent_type"):
    return json.dumps({"hook_event_name": "PreToolUse", "tool_name": tool, "cwd": "/tmp",
                       "session_id": "s1", "tool_input": {key: agent, "prompt": prompt}})


class TiePredispatch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env = {**os.environ, "CLAUDE_PROJECT_DIR": str(self.root)}
        self.env.pop("HOOKS_QUIET", None)  # bin/selftest sets it; it would mute every nudge
        self.env.pop("TIE_OK", None)

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, stdin, env=None, harness="claude"):
        return subprocess.run([sys.executable, str(HOOK), "--harness", harness], input=stdin,
                              capture_output=True, text=True, env=env or self.env, timeout=30)

    # 1. allow
    def test_allow(self):
        cases = [
            spawn(TIED),                                          # worker with a tie block
            spawn(UNTIED, agent="claim-auditor"),                 # a reviewer
            spawn("Find where the cap set bound is proved.", agent="general-purpose"),  # no task intent
            spawn("Write up the C002 results for the owner.", agent="general-purpose"),  # write-up only
            spawn("tie: Q002 / A2 via C002, see the README\n" + UNTIED),  # one-line pointer
            json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": "/tmp",
                        "tool_input": {"command": "ls"}}),         # not a dispatch
        ]
        for c in cases:
            with self.subTest(c[:80]):
                r = self.run_hook(c)
                self.assertEqual((r.returncode, r.stderr), (0, ""))

    # 2. trigger
    def test_trigger(self):
        r = self.run_hook(spawn(UNTIED))
        self.assertEqual(r.returncode, 2)
        self.assertIn("[tie-predispatch]", r.stderr)
        self.assertIn("docs/discipline/question-ties.md", r.stderr)
        self.assertTrue((self.root / "logs" / "nudges.jsonl").exists())
        r = self.run_hook(spawn("Build the driver for experiments/caps-n7.", agent="general-purpose"))
        self.assertEqual(r.returncode, 2)
        r = self.run_hook(spawn("Run the C004 search.", agent="exp-worker", tool="spawn_agent",
                                key="agent_type"), harness="codex")
        self.assertEqual(r.returncode, 2)

    # 2b. Codex hides the brief (encrypted): a worker spawn gets one reminder per session
    def test_hidden_brief(self):
        hidden = spawn("gAAAAABqx8TuQ9RuotQPtS1DxvGQ7-LbtXlFrGl1TlJ5LXNZ02S_ra3WgtQ-XweF5Sjd9k==", agent="exp-worker", tool="collaborationspawn_agent",
                       key="agent_type").replace('"prompt"', '"message"')
        r = self.run_hook(hidden, harness="codex")
        self.assertEqual(r.returncode, 2)
        self.assertIn("hides", r.stderr)
        self.assertEqual(self.run_hook(hidden, harness="codex").returncode, 0)  # same session
        other = spawn("gAAAAABqx8TuQ9RuotQPtS1DxvGQ7-LbtXlFrGl1TlJ5LXNZ02S_ra3WgtQ-XweF5Sjd9k==", agent="claim-auditor", tool="collaborationspawn_agent",
                      key="agent_type").replace('"prompt"', '"message"')
        self.assertEqual(self.run_hook(other, harness="codex").returncode, 0)  # not a worker

    # 3. bypass
    def test_bypass(self):
        self.assertEqual(self.run_hook(spawn(UNTIED)).returncode, 2)
        self.assertEqual(self.run_hook(spawn(UNTIED)).returncode, 0)  # identical re-issue proceeds
        env = {**self.env, "TIE_OK": "1"}
        r = self.run_hook(spawn("Run the sweep for C001."), env=env)
        self.assertEqual((r.returncode, r.stderr), (0, ""))

    # 4. failure: malformed input fails open, loudly
    def test_failure(self):
        r = self.run_hook("{not json")
        self.assertEqual(r.returncode, 0)
        self.assertIn("WARNING", r.stderr)
        self.assertTrue((self.root / "logs" / "state" / "hook-errors.log").exists())


if __name__ == "__main__":
    unittest.main()
