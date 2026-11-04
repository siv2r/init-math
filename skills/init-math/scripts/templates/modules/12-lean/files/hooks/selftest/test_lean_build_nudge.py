"""Selftest for hooks/lean-build-nudge.py, through its real entry point."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "lean-build-nudge.py"


def run(root, command=None, raw=None, **env_extra):
    env = {k: v for k, v in os.environ.items() if k not in ("HOOKS_QUIET", "LEAN_BUILD_OK")}
    env["CLAUDE_PROJECT_DIR"] = root
    env.update(env_extra)
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": command}}
    data = raw if raw is not None else json.dumps(payload)
    return subprocess.run([sys.executable, str(HOOK), "--harness", "claude"], input=data,
                          capture_output=True, text=True, env=env, timeout=30)


class LeanBuildNudge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_allow_wrapper_and_other_lake_commands(self):
        for cmd in ("bin/lean-build Proofs.Basic", "lake exe cache get", "lake env lean A.lean", "find .lake/build -name A.olean",
                    "git commit -m 'run lake build later'", "echo \"lake build\"",
                    "cat <<'EOF' > notes.txt\nlake build\nEOF"):
            self.assertEqual(run(self.root, cmd).returncode, 0, cmd)

    def test_trigger_then_reissue_proceeds(self):
        cmd = "lake build Proofs 2>&1 | tail -40"
        r = run(self.root, cmd)
        self.assertEqual(r.returncode, 2)
        self.assertIn("lean-build-nudge", r.stderr)
        self.assertEqual(run(self.root, cmd).returncode, 0)

    def test_trigger_with_options(self):
        self.assertEqual(run(self.root, "lake -R build").returncode, 2)

    def test_bypass(self):
        self.assertEqual(run(self.root, "lake build", LEAN_BUILD_OK="1").returncode, 0)
        self.assertEqual(run(self.root, "LEAN_BUILD_OK=1 lake build").returncode, 0)

    def test_failure_fails_open_loudly(self):
        r = run(self.root, raw="{nope")
        self.assertEqual(r.returncode, 0)
        self.assertIn("WARNING", r.stderr)
        self.assertTrue((Path(self.root) / "logs/state/hook-errors.log").exists())


if __name__ == "__main__":
    unittest.main()
