"""Selftest for hooks/lit-search-gate.py, through its real entry point (git repo, no commits)."""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "lit-search-gate.py"
GIT_ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def run(root, command=None, raw=None, **env_extra):
    env = {k: v for k, v in os.environ.items() if k not in ("HOOKS_QUIET", "LIT_SEARCH_OK")}
    env.update(GIT_ENV)
    env["CLAUDE_PROJECT_DIR"] = root
    env.update(env_extra)
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": command}}
    data = raw if raw is not None else json.dumps(payload)
    return subprocess.run([sys.executable, str(HOOK), "--harness", "claude"], input=data,
                          capture_output=True, text=True, env=env, timeout=30)


class LitSearchGate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        env = {**os.environ, **GIT_ENV}
        subprocess.run(["git", "init", "-q", self.root], check=True, env=env)
        kr = Path(self.root) / "wiki" / "known-results"
        kr.mkdir(parents=True)
        (kr / "bound.md").write_text("# A bound\n\nThis is due to Smith (1990).\n")
        (kr / "plain.md").write_text("# Notes\n\nA computed table.\n")
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True, env=env)

    def tearDown(self):
        self.tmp.cleanup()

    def record_search(self, ts):
        d = Path(self.root) / "logs" / "state"
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "lit-searches.log", "a") as f:
            f.write(f"{int(ts)}\n")

    def test_allow_unflagged_and_non_commit(self):
        self.assertEqual(run(self.root, "git commit -m 'x' -- wiki/known-results/plain.md").returncode, 0)
        self.assertEqual(run(self.root, "git status").returncode, 0)

    def test_trigger_then_reissue_proceeds(self):
        cmd = "git commit -m 'add bound' -- wiki/known-results/bound.md"
        r = run(self.root, cmd)
        self.assertEqual(r.returncode, 2)
        self.assertIn("lit-search-gate", r.stderr)
        self.assertEqual(run(self.root, cmd).returncode, 0)

    def test_staged_files_are_used(self):
        self.assertEqual(run(self.root, "git commit -F msg.txt").returncode, 2)

    def test_recent_search_satisfies(self):
        self.record_search(time.time())
        self.assertEqual(run(self.root, "git commit -m 'b' -- wiki/known-results/bound.md").returncode, 0)

    def test_stale_search_does_not_satisfy(self):
        self.record_search(time.time() - 3 * 24 * 3600)
        self.assertEqual(run(self.root, "git commit -m 'c' -- wiki/known-results/bound.md").returncode, 2)

    def test_bypass_logged(self):
        r = run(self.root, "LIT_SEARCH_OK=1 git commit -m 'd' -- wiki/known-results/bound.md")
        self.assertEqual(r.returncode, 0)
        fb = (Path(self.root) / "logs" / "feedback.jsonl").read_text()
        self.assertIn('"kind": "bypass"', fb)
        self.assertEqual(run(self.root, "git commit -m 'e' -- wiki/known-results/bound.md",
                             LIT_SEARCH_OK="1").returncode, 0)

    def test_failure_fails_open_loudly(self):
        r = run(self.root, raw="{nope")
        self.assertEqual(r.returncode, 0)
        self.assertIn("WARNING", r.stderr)
        self.assertTrue((Path(self.root) / "logs/state/hook-errors.log").exists())


if __name__ == "__main__":
    unittest.main()
