"""Selftest for hooks/cd-drift-nudge.py, through its real entry point."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "cd-drift-nudge.py"


def run(root, command, harness="claude", raw=None, session=None, **env_extra):
    env = {k: v for k, v in os.environ.items() if k not in ("HOOKS_QUIET", "CD_DRIFT_OK")}
    env["CLAUDE_PROJECT_DIR"] = root
    env.update(env_extra)
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": root,
               "tool_input": {"command": command}}
    if session:
        payload["session_id"] = session
    data = raw if raw is not None else json.dumps(payload)
    return subprocess.run([sys.executable, str(HOOK), "--harness", harness], input=data,
                          capture_output=True, text=True, env=env, timeout=30)


class CdDrift(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_allow(self):
        for c in ("grep -n x /abs/file", "cd build && make", "ls src"):
            self.assertEqual(run(self.root, c).returncode, 0, c)

    def test_no_move_cd_allowed(self):
        for c in ('cd "$PWD"; ls wiki', "cd . && grep -rn x wiki", f"cd {self.root} && ls"):
            self.assertEqual(run(self.root, c).returncode, 0, c)

    def test_trigger_then_reissue(self):
        r = run(self.root, "cd src && grep -rn foo .")
        self.assertEqual(r.returncode, 2)
        self.assertIn("cd-drift-nudge", r.stderr)
        self.assertEqual(run(self.root, "cd src && ls").returncode, 0)

    def test_once_per_session(self):
        self.assertEqual(run(self.root, "cd a && ls", session="s1").returncode, 2)
        self.assertEqual(run(self.root, "cd b && ls", session="s1").returncode, 0)
        self.assertEqual(run(self.root, "cd b && ls", session="s2").returncode, 2)

    def test_codex_noop(self):
        self.assertEqual(run(self.root, "cd src && ls", harness="codex").returncode, 0)

    def test_bypass(self):
        self.assertEqual(run(self.root, "cd src && ls", CD_DRIFT_OK="1").returncode, 0)

    def test_failure_fails_open_loudly(self):
        r = run(self.root, "", raw="{nope")
        self.assertEqual(r.returncode, 0)
        self.assertIn("WARNING", r.stderr)


if __name__ == "__main__":
    unittest.main()
