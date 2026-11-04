"""Selftest for hooks/large-doc-gate-nudge.py through its real entry point.

Four branches (docs/discipline/hook-authoring.md): allow, trigger, bypass, failure.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "large-doc-gate-nudge.py"


def spawn(agent, prompt):
    return json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Agent", "cwd": "/tmp",
                       "tool_input": {"subagent_type": agent, "prompt": prompt}})


class LargeDocGateNudge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "notes").mkdir()
        (self.root / "notes" / "big.md").write_text("line\n" * 500)
        (self.root / "notes" / "small.md").write_text("line\n" * 20)
        self.env = {**os.environ, "CLAUDE_PROJECT_DIR": str(self.root)}
        for k in ("HOOKS_QUIET", "LARGE_DOC_GATE_OK"):
            self.env.pop(k, None)

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, stdin, env=None):
        return subprocess.run([sys.executable, str(HOOK), "--harness", "claude"], input=stdin,
                              capture_output=True, text=True, env=env or self.env, timeout=30)

    # 1. allow: small doc, non-reviewer agent, scoped brief, reference-only path
    def test_allow(self):
        for payload in (spawn("claim-auditor", "Audit notes/small.md please."),
                        spawn("worker", "Edit notes/big.md."),
                        spawn("proof-referee", "Review the section 3 extract of notes/big.md."),
                        spawn("expositor", "Review notes/small.md; style model: notes/big.md")):
            r = self.run_hook(payload)
            self.assertEqual((r.returncode, r.stderr), (0, ""), payload)

    # 2. trigger: a reviewer on a large doc with no scoping refuses once, then proceeds
    def test_trigger(self):
        p = spawn("claim-auditor", "Audit notes/big.md for over-claims.")
        r = self.run_hook(p)
        self.assertEqual(r.returncode, 2)
        self.assertIn("notes/big.md", r.stderr)
        self.assertEqual(self.run_hook(p).returncode, 0)
        self.assertTrue((self.root / "logs" / "nudges.jsonl").exists())

    # 3. bypass: env switches
    def test_bypass(self):
        p = spawn("red-team", "Attack notes/big.md.")
        for extra in ({"LARGE_DOC_GATE_OK": "1"}, {"HOOKS_QUIET": "1"}):
            r = self.run_hook(p, env={**self.env, **extra})
            self.assertEqual(r.returncode, 0)

    # 4. failure: malformed input fails open, loudly
    def test_failure(self):
        r = self.run_hook("{not json")
        self.assertEqual(r.returncode, 0)
        self.assertIn("WARNING", r.stderr)
        self.assertTrue((self.root / "logs" / "state" / "hook-errors.log").exists())


if __name__ == "__main__":
    unittest.main()
