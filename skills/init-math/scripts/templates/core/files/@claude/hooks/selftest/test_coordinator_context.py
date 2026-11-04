"""Selftest for hooks/coordinator-context.py through its real entry point.

Branches (docs/discipline/hook-authoring.md): trigger (the main session gets each part),
allow (a subagent, or a part past the end, gets nothing), bypass (none: HOOKS_QUIET=1 does
not silence it), failure (a missing file is reported, not skipped).
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "coordinator-context.py"
spec = importlib.util.spec_from_file_location("coordinator_context", HOOK)
cc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cc)


def doc(n_sections, size):
    return "# Coordinator rules\n\nIntro.\n\n" + "".join(
        f"## Section {i}\n\n" + ("- a rule about something.\n" * (size // 26)) + "\n"
        for i in range(n_sections))


class CoordinatorContext(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.env = {**os.environ, "CLAUDE_PROJECT_DIR": str(self.root), "HOOKS_QUIET": "1"}

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, part, payload=None):
        payload = payload or {"hook_event_name": "SessionStart", "source": "compact",
                              "cwd": str(self.root), "session_id": "s1"}
        r = subprocess.run([sys.executable, str(HOOK), "--harness", "claude", "--part", str(part)],
                           input=json.dumps(payload), capture_output=True, text=True,
                           env=self.env, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"] if r.stdout.strip() else None

    def test_parts_rejoin_and_fit(self):
        for text in (doc(3, 500), doc(12, 2000), doc(1, 30000)):
            ps = cc.parts(text, 8800)
            self.assertEqual("".join(ps), text)
            self.assertTrue(all(len(p) <= 8800 for p in ps))

    def test_main_session_gets_every_part_even_when_quiet(self):
        text = doc(10, 1500)
        (self.root / "COORDINATOR.md").write_text(text)
        got = [self.run_hook(k) for k in (1, 2, 3)]
        n = len(cc.parts(text, cc.LIMIT - 200))
        self.assertEqual(n, 2)
        self.assertIn("part 1 of 2", got[0])
        self.assertIsNone(got[2])
        self.assertTrue(all(len(g) <= cc.LIMIT for g in got if g))
        self.assertIn("## Section 9", got[1])

    def test_too_long_points_to_the_rest(self):
        (self.root / "COORDINATOR.md").write_text(doc(30, 1500))
        last = self.run_hook(cc.PARTS)
        self.assertIn("continues past what a hook can show", last)

    def test_subagent_gets_nothing(self):
        (self.root / "COORDINATOR.md").write_text(doc(2, 100))
        self.assertIsNone(self.run_hook(1, {"hook_event_name": "SessionStart", "agent_type": "worker",
                                            "cwd": str(self.root), "session_id": "s2"}))

    def test_missing_file_is_reported(self):
        self.assertIn("is missing", self.run_hook(1))
        self.assertIsNone(self.run_hook(2))


if __name__ == "__main__":
    unittest.main()
