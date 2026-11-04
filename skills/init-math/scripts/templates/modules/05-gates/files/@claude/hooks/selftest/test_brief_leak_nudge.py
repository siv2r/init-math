"""Selftest for hooks/brief-leak-nudge.py through its real entry point.

Four branches (docs/discipline/hook-authoring.md): allow, trigger, bypass, failure.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "brief-leak-nudge.py"


def spawn(agent, prompt):
    return json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Agent", "cwd": "/tmp",
                       "tool_input": {"subagent_type": agent, "prompt": prompt}})


class BriefLeakNudge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "work" / "x" / "scratch").mkdir(parents=True)
        self.env = {**os.environ, "CLAUDE_PROJECT_DIR": str(self.root)}
        for k in ("HOOKS_QUIET", "BRIEF_LEAK_OK"):
            self.env.pop(k, None)

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, stdin, env=None):
        return subprocess.run([sys.executable, str(HOOK), "--harness", "claude"], input=stdin,
                              capture_output=True, text=True, env=env or self.env, timeout=30)

    # 1. allow: clean briefs, ordinary words, evidence entries, verdict options, other agents
    def test_allow(self):
        for payload in (
                spawn("claim-auditor", "FILE: work/x/a.md\nCLAIM: every x is y."),
                spawn("proof-referee", "Review work/x/a.md. The proof is axiom-clean; a sound "
                                       "argument for Lemma 2; credence: 0.6 is the owner's."),
                spawn("red-team", "Attack C004.\n- 2026-10-01 · red-team · result: SURVIVED — n<9"),
                spawn("claim-auditor", "LAST LOOK. Answer SOUND or OVER-CLAIMED."),
                spawn("worker", "The auditor found it SOUND; now write it up.")):
            r = self.run_hook(payload)
            self.assertEqual((r.returncode, r.stderr), (0, ""), payload)

    # 2. trigger: each leak refuses once, then the same dispatch proceeds
    def test_trigger(self):
        for i, (agent, prompt) in enumerate((
                ("red-team", "Re-review work/x/a.md; the claim-auditor found it SOUND."),
                ("claim-auditor", "Audit work/x/a.md. Worker return: CREDENCE NOW: 0.9"),
                ("proof-referee", "Review work/x/a.md, which already passed review last week."),
                ("claim-auditor", "Audit it; the author believes the bound is sharp."))):
            p = spawn(agent, prompt + f" ({i})")
            r = self.run_hook(p)
            self.assertEqual(r.returncode, 2, prompt)
            self.assertIn(agent, r.stderr)
            self.assertEqual(self.run_hook(p).returncode, 0, prompt)
        self.assertTrue((self.root / "logs" / "nudges.jsonl").exists())

    def test_brief_file_read(self):
        (self.root / "work" / "x" / "scratch" / "brief.md").write_text(
            "FILE: work/x/a.md\nThe previous round was CLEAN.\n")
        r = self.run_hook(spawn("proof-referee", "brief: work/x/scratch/brief.md"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("CLEAN", r.stderr)

    def test_project_verdicts(self):
        (self.root / "project.toml").write_text('[gates.verdicts]\nclaim-auditor = ["OK"]\n')
        r = self.run_hook(spawn("red-team", "The auditor said OK."))
        self.assertEqual(r.returncode, 2)

    # 3. bypass: env switches
    def test_bypass(self):
        p = spawn("red-team", "It was SOUND before.")
        for extra in ({"BRIEF_LEAK_OK": "1"}, {"HOOKS_QUIET": "1"}):
            r = self.run_hook(p, env={**self.env, **extra})
            self.assertEqual(r.returncode, 0)

    # 4. failure: malformed input fails open, loudly
    def test_failure(self):
        r = self.run_hook("{not json")
        self.assertEqual(r.returncode, 0)
        self.assertIn("WARNING", r.stderr)


if __name__ == "__main__":
    unittest.main()
