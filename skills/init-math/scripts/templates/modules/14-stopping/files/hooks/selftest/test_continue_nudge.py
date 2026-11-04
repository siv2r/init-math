"""Selftest for hooks/continue-nudge.py, through its real entry point."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "continue-nudge.py"


def run(root, payload=None, raw=None, harness="claude", **env_extra):
    env = {k: v for k, v in os.environ.items() if k not in ("HOOKS_QUIET", "CONTINUE_NUDGE_OFF")}
    env["CLAUDE_PROJECT_DIR"] = root
    env.update(env_extra)
    data = raw if raw is not None else json.dumps(payload)
    return subprocess.run([sys.executable, str(HOOK), "--harness", harness], input=data,
                          capture_output=True, text=True, env=env, timeout=30)


def transcript(root, last_user_text, ts="2026-01-01T00:00:00Z"):
    lines = [
        {"type": "user", "message": {"role": "user", "content": "Prove the lemma for n = 2."},
         "timestamp": "2026-01-01T00:00:00Z"},
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "Done."}]}},
        {"type": "user", "message": {"role": "user", "content": last_user_text}, "timestamp": ts},
        {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "x", "content": "ok"}]}},
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "Next I would..."}]}},
    ]
    p = Path(root) / "transcript.jsonl"
    p.write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    return str(p)


def stop(path):
    return {"hook_event_name": "Stop", "transcript_path": path, "stop_hook_active": False}


class ContinueNudge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_allow_no_transcript(self):
        r = run(self.root, {"hook_event_name": "Stop"})
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_allow_ordinary_message(self):
        r = run(self.root, stop(transcript(self.root, "Can you check the case n = 3 as well?")))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_allow_when_already_continuing(self):
        p = stop(transcript(self.root, "keep going"))
        p["stop_hook_active"] = True
        self.assertEqual(run(self.root, p).returncode, 0)

    def test_trigger_once_per_message(self):
        p = stop(transcript(self.root, "Let's continue"))
        r = run(self.root, p)
        self.assertEqual(r.returncode, 2)
        self.assertIn("continue-nudge", r.stderr)
        self.assertEqual(run(self.root, p).returncode, 0)

    def test_trigger_codex_json(self):
        p = stop(transcript(self.root, "keep going", ts="2026-01-02T00:00:00Z"))
        r = run(self.root, p, harness="codex")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(json.loads(r.stdout)["decision"], "block")

    def test_bypass(self):
        p = stop(transcript(self.root, "continue"))
        self.assertEqual(run(self.root, p, CONTINUE_NUDGE_OFF="1").returncode, 0)
        self.assertEqual(run(self.root, p, HOOKS_QUIET="1").returncode, 0)

    def test_failure_fails_open_loudly(self):
        r = run(self.root, raw="{broken")
        self.assertEqual(r.returncode, 0)
        self.assertIn("WARNING", r.stderr)
        self.assertTrue((Path(self.root) / "logs/state/hook-errors.log").exists())


if __name__ == "__main__":
    unittest.main()
