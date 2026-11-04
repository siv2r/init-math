"""Selftest for hooks/file-home-nudge.py through its real entry point.

Four branches (docs/discipline/hook-authoring.md): allow, trigger, bypass, failure.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "file-home-nudge.py"


class FileHomeNudge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        (self.root / "notes").mkdir()
        (self.root / "notes" / "workflow-journal.md").write_text("# Workflow journal\n")
        self.env = {**os.environ, "CLAUDE_PROJECT_DIR": str(self.root)}
        self.env.pop("HOOKS_QUIET", None)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, path):
        return json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Write",
                           "tool_input": {"file_path": str(path), "content": "x"},
                           "cwd": str(self.root), "session_id": "s1"})

    def patch(self, rel):
        return json.dumps({"hook_event_name": "PreToolUse", "tool_name": "apply_patch",
                           "tool_input": {"command": f"*** Begin Patch\n*** Add File: {rel}\n+x\n"
                                                     "*** End Patch"},
                           "cwd": str(self.root), "session_id": "s1"})

    def run_hook(self, stdin, env=None, harness="claude"):
        return subprocess.run([sys.executable, str(HOOK), "--harness", harness], input=stdin,
                              capture_output=True, text=True, env=env or self.env, timeout=30)

    # 1. allow: an existing notes file, and new files elsewhere
    def test_allow(self):
        for path in (self.root / "notes" / "workflow-journal.md",
                     self.root / "work" / "corner" / "estimate.md"):
            r = self.run_hook(self.write(path))
            self.assertEqual((r.returncode, r.stderr), (0, ""))

    # 2. trigger: a new file under notes/, once per file; Codex apply_patch with a relative path
    def test_trigger(self):
        path = self.root / "notes" / "corner-estimate-review.txt"
        r = self.run_hook(self.write(path))
        self.assertEqual(r.returncode, 2)
        self.assertIn("notes/corner-estimate-review.txt", r.stderr)
        self.assertIn("work/<slug>/", r.stderr)
        self.assertEqual(self.run_hook(self.write(path)).returncode, 0)  # re-issue proceeds
        r = self.run_hook(self.patch("notes/checks/run.py"), harness="codex")
        self.assertEqual(r.returncode, 2)
        self.assertIn("notes/checks/run.py", r.stderr)

    def test_scratch_manuscript(self):
        r = self.run_hook(self.write(self.root / "work" / "corner" / "scratch" / "paper.tex"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("would be in no commit", r.stderr)
        r = self.run_hook(self.write(self.root / "work" / "corner" / "scratch" / "brief.md"))
        self.assertEqual((r.returncode, r.stderr), (0, ""))  # a throwaway brief is fine
        r = self.run_hook(self.write(self.root / "writeups" / "paper.tex"))
        self.assertEqual((r.returncode, r.stderr), (0, ""))

    # 3. bypass: HOOKS_QUIET
    def test_bypass(self):
        r = self.run_hook(self.write(self.root / "notes" / "new.md"),
                          env={**self.env, "HOOKS_QUIET": "1"})
        self.assertEqual(r.returncode, 0)

    # 4. failure: fail open, loudly
    def test_failure(self):
        r = self.run_hook("{not json")
        self.assertEqual(r.returncode, 0)
        self.assertIn("WARNING", r.stderr)
        self.assertTrue((self.root / "logs" / "state" / "hook-errors.log").exists())


if __name__ == "__main__":
    unittest.main()
