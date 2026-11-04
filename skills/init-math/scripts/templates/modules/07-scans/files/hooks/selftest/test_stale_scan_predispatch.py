"""Selftest for hooks/stale-scan-predispatch.py: allow, trigger, bypass, failure."""
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _scans_fixture import Project, spawn  # noqa: E402

HOOK = "stale-scan-predispatch.py"
BRIEF = spawn("claim-auditor", "Audit notes/draft.md.")


class StaleScanPredispatch(unittest.TestCase):
    def setUp(self):
        self.p = Project(["stale-status-scan"])
        self.doc = self.p.write("notes/draft.md", "supported for all n\n")

    def tearDown(self):
        self.p.cleanup()

    def edit(self):
        """Change the file so its mtime is just after the recorded dispatch."""
        state = json.loads((self.p.root / "logs" / "state" / "stale-scan-predispatch.json").read_text())
        self.doc.write_text("supported for n < 100\n")
        t = state["notes/draft.md"] + 0.01
        os.utime(self.doc, (t, t))

    def test_allow(self):
        self.assertEqual(self.p.run(HOOK, BRIEF).returncode, 0)          # first dispatch
        self.assertEqual(self.p.run(HOOK, BRIEF).returncode, 0)          # unchanged since
        self.edit()
        subprocess.run([sys.executable, str(self.p.root / "bin" / "stale-status-scan"),
                        "--phrase", "all n", str(self.doc)], capture_output=True, check=True)
        r = self.p.run(HOOK, BRIEF)                                      # scanned after edit
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        self.assertEqual(self.p.run(HOOK, spawn("worker", "Edit notes/draft.md.")).returncode, 0)

    def test_trigger(self):
        self.p.run(HOOK, BRIEF)
        self.edit()
        r = self.p.run(HOOK, BRIEF)
        self.assertEqual(r.returncode, 2)
        self.assertIn("stale-status-scan", r.stderr)
        self.assertEqual(self.p.run(HOOK, BRIEF).returncode, 0)

    def test_bypass(self):
        self.p.run(HOOK, BRIEF)
        self.edit()
        for extra in ({"STALE_SCAN_OK": "1"}, {"HOOKS_QUIET": "1"}):
            self.assertEqual(self.p.run(HOOK, BRIEF, **extra).returncode, 0)

    def test_failure(self):
        r = self.p.run(HOOK, "{not json")
        self.assertEqual(r.returncode, 0)
        self.assertIn("WARNING", r.stderr)
        self.assertTrue((self.p.root / "logs" / "state" / "hook-errors.log").exists())


if __name__ == "__main__":
    unittest.main()
