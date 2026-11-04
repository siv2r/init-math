"""Selftest for hooks/lit-search-predispatch.py, through its real entry point."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "lit-search-predispatch.py"


def run(root, payload=None, raw=None, harness="claude", **env_extra):
    env = {k: v for k, v in os.environ.items() if k not in ("HOOKS_QUIET", "LIT_PRIOR_ART_OK")}
    env["CLAUDE_PROJECT_DIR"] = root
    env.update(env_extra)
    data = raw if raw is not None else json.dumps(payload)
    return subprocess.run([sys.executable, str(HOOK), "--harness", harness], input=data,
                          capture_output=True, text=True, env=env, timeout=30)


def spawn(prompt, agent="general-purpose", session="s1"):
    return {"hook_event_name": "PreToolUse", "tool_name": "Agent", "session_id": session,
            "tool_input": {"subagent_type": agent, "prompt": prompt, "description": "search"}}


class LitSearchPredispatch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        (Path(self.root) / "wiki" / "conjectures").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def log_lines(self):
        f = Path(self.root) / "logs" / "state" / "lit-searches.log"
        return f.read_text().split() if f.exists() else []

    def test_allow_unrelated_dispatch(self):
        r = run(self.root, spawn("Refactor the plotting helper."))
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.log_lines(), [])

    def test_trigger_once_per_session_and_record(self):
        p = spawn("Is this already known? Find who proved the bound.", agent="lit-search")
        r = run(self.root, p)
        self.assertEqual(r.returncode, 2)
        self.assertIn("lit-search-predispatch", r.stderr)
        self.assertIn("wiki/conjectures/", r.stderr)
        self.assertEqual(run(self.root, p).returncode, 0)
        self.assertEqual(run(self.root, spawn("Do a literature search on X.")).returncode, 0)
        self.assertEqual(len(self.log_lines()), 3)
        self.assertEqual(run(self.root, spawn("prior art for Y", session="s2")).returncode, 2)

    def test_bypass_env_and_declared(self):
        self.assertEqual(run(self.root, spawn("literature search", agent="lit-search"),
                             LIT_PRIOR_ART_OK="1").returncode, 0)
        declared = "Internal prior art: wiki/conjectures has nothing on X.\nSearch arXiv for X."
        self.assertEqual(run(self.root, spawn(declared, session="s3")).returncode, 0)
        self.assertEqual(len(self.log_lines()), 2)

    def test_hidden_brief_records_without_refusing(self):
        # Codex passes the brief encrypted: the declared line cannot be seen, so never refuse.
        p = spawn("gAAAAA" + "x" * 40, agent="lit-search", session="s4")
        r = run(self.root, p, harness="codex")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(self.log_lines()), 1)

    def test_failure_fails_open_loudly(self):
        r = run(self.root, raw="{nope")
        self.assertEqual(r.returncode, 0)
        self.assertIn("WARNING", r.stderr)
        self.assertTrue((Path(self.root) / "logs/state/hook-errors.log").exists())


if __name__ == "__main__":
    unittest.main()
