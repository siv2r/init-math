"""Selftest for hooks/define-check-nudge.py: allow, trigger, bypass, failure."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _scans_fixture import Project, shell  # noqa: E402

HOOK = "define-check-nudge.py"


class DefineCheckNudge(unittest.TestCase):
    def setUp(self):
        self.p = Project(["define-check"])
        self.p.write("wiki/conjectures/_index.md", "| C001 | open | see finding SB2 |\n")

    def tearDown(self):
        self.p.cleanup()

    def test_allow(self):
        self.assertEqual(self.p.run(HOOK, shell("git status")).returncode, 0)
        # Standard public ids (OEIS, MathSciNet) are not invented codes.
        self.p.write("wiki/conjectures/_index.md", "| C001 | open | OEIS A000041, MR1234567 |\n")
        r = self.p.run(HOOK, shell("git commit -m x"))
        self.assertEqual((r.returncode, r.stderr), (0, ""))

    def test_trigger(self):
        r = self.p.run(HOOK, shell("git commit -m x"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("SB2", r.stderr)
        self.assertEqual(self.p.run(HOOK, shell("git commit -m x")).returncode, 0)

    def test_configured_store(self):
        # a ledger moved by [conjectures] dir is still a shared index
        self.p.write("wiki/conjectures/_index.md", "| C001 | open |\n")
        self.p.write("project.toml", '[conjectures]\ndir = "notes/conj"\n')
        self.p.write("notes/conj/_index.md", "| C002 | open | see finding SB2 |\n")
        r = self.p.run(HOOK, shell("git commit -m x"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("SB2", r.stderr)

    def test_bypass(self):
        for extra in ({"DEFINE_CHECK_OK": "1"}, {"HOOKS_QUIET": "1"}):
            self.assertEqual(self.p.run(HOOK, shell("git commit -m x"), **extra).returncode, 0)

    def test_failure(self):
        r = self.p.run(HOOK, "{not json")
        self.assertEqual(r.returncode, 0)
        self.assertIn("WARNING", r.stderr)
        self.assertTrue((self.p.root / "logs" / "state" / "hook-errors.log").exists())


if __name__ == "__main__":
    unittest.main()
