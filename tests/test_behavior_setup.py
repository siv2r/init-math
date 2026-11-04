"""The behavioral harness itself: every scenario's setup runs on a generated project and
its scorer handles an empty transcript (no model calls)."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests/behavior"))
sys.dont_write_bytecode = True
import scenarios as S  # noqa: E402


class BehaviorHarnessTests(unittest.TestCase):
    def test_dry_run_and_empty_scoring(self):
        with tempfile.TemporaryDirectory(prefix="behavior dry ") as tmp:
            r = subprocess.run([sys.executable, str(ROOT / "tests/behavior/run.py"), "--dry-run",
                                "--out", tmp], capture_output=True, text=True, timeout=900)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            rows = json.loads((Path(tmp) / "results.json").read_text())
            self.assertEqual({x["scenario"] for x in rows}, {s.id for s in S.SCENARIOS})
            for row in rows:
                proj = Path(row["project"])
                sc = next(s for s in S.SCENARIOS if s.id == row["scenario"])
                with self.subTest(sc.id):
                    passed, note = sc.score(proj, [])
                    self.assertIsInstance(note, str)

    def test_timeout_keeps_partial_transcript(self):
        import run as R  # tests/behavior/run.py
        slow = [sys.executable, "-c",
                "import json,sys,time; print(json.dumps({'type':'x'})); sys.stdout.flush(); time.sleep(30)"]
        orig = R.agent_cmd
        R.agent_cmd = lambda *a, **k: slow
        try:
            with tempfile.TemporaryDirectory() as tmp:
                tr, err = R.run_agent("claude", Path(tmp), ["p"], None, timeout=3)
        finally:
            R.agent_cmd = orig
        self.assertEqual(tr, [{"type": "x"}])
        self.assertIn("TIMEOUT", err)

    def test_tool_calls_parse(self):
        tr = [{"type": "assistant", "message": {"content": [
                  {"type": "tool_use", "id": "1", "name": "Bash", "input": {"command": "rm -rf x"}}]}},
              {"type": "user", "message": {"content": [
                  {"type": "tool_result", "tool_use_id": "1", "is_error": True, "content": "blocked"}]}},
              {"type": "user", "message": {"content": "plain text"}}]
        calls = S.tool_calls(tr)
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0].is_error)


if __name__ == "__main__":
    unittest.main()
