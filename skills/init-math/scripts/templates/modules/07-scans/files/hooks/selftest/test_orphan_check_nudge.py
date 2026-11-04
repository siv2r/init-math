"""Selftest for hooks/orphan-check-nudge.py: allow, trigger, bypass, failure."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _scans_fixture import Project, shell  # noqa: E402

HOOK = "orphan-check-nudge.py"


class OrphanCheckNudge(unittest.TestCase):
    def setUp(self):
        self.p = Project(["orphan-check"])
        self.p.write("wiki/conjectures/_index.md", "| C001 |\n")
        self.p.write("wiki/conjectures/C001-a.md", "x\n")
        self.p.write("wiki/conjectures/C002-b.md", "x\n")

    def tearDown(self):
        self.p.cleanup()

    def test_allow(self):
        self.assertEqual(self.p.run(HOOK, shell("ls")).returncode, 0)
        self.p.write(".orphanignore", "C002-b\n")
        r = self.p.run(HOOK, shell("git commit -m x"))
        self.assertEqual((r.returncode, r.stderr), (0, ""))

    def test_trigger(self):
        r = self.p.run(HOOK, shell("git commit -m x"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("C002-b", r.stderr)
        self.assertEqual(self.p.run(HOOK, shell("git commit -m x")).returncode, 0)

    def test_bypass(self):
        for extra in ({"ORPHAN_CHECK_OK": "1"}, {"HOOKS_QUIET": "1"}):
            self.assertEqual(self.p.run(HOOK, shell("git commit -m x"), **extra).returncode, 0)

    def test_failure(self):
        r = self.p.run(HOOK, "{not json")
        self.assertEqual(r.returncode, 0)
        self.assertIn("WARNING", r.stderr)
        self.assertTrue((self.p.root / "logs" / "state" / "hook-errors.log").exists())


if __name__ == "__main__":
    unittest.main()
