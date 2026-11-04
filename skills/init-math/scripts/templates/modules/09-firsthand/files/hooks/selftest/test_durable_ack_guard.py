"""Selftest for hooks/durable-ack-guard.py, through its real entry point."""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "durable-ack-guard.py"


def run(root, payload=None, raw=None, **env_extra):
    env = {k: v for k, v in os.environ.items() if k not in ("HOOKS_QUIET", "ACK_OK")}
    env["CLAUDE_PROJECT_DIR"] = root
    env.update(env_extra)
    data = raw if raw is not None else json.dumps(payload)
    return subprocess.run([sys.executable, str(HOOK), "--harness", "claude"], input=data,
                          capture_output=True, text=True, env=env, timeout=30)


def transcript(root, final, tool_input=None):
    content = []
    if tool_input is not None:
        content.append({"type": "tool_use", "id": "t1", "name": "Edit", "input": tool_input})
    lines = [
        {"type": "user", "message": {"role": "user", "content": "Record the result."}},
        {"type": "assistant", "message": {"role": "assistant", "content": content or [
            {"type": "text", "text": "working"}]}},
        {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]}},
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": final}]}},
    ]
    p = Path(root) / "transcript.jsonl"
    p.write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    return str(p)


def stop(path, **extra):
    return {"hook_event_name": "Stop", "transcript_path": path, **extra}


class DurableAckGuard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        d = Path(self.root) / "wiki" / "conjectures"
        d.mkdir(parents=True)
        self.c7 = d / "C007-bound.md"
        self.c7.write_text("status: open\n")
        old = time.time() - 5 * 3600
        os.utime(self.c7, (old, old))

    def tearDown(self):
        self.tmp.cleanup()

    def test_allow_backed_claim(self):
        p = transcript(self.root, "Recorded the new evidence in C007.",
                       {"file_path": str(self.c7), "old_string": "a", "new_string": "b"})
        self.assertEqual(run(self.root, stop(p)).returncode, 0)

    def test_allow_no_claim_and_no_record_dir(self):
        self.assertEqual(run(self.root, stop(transcript(self.root, "The sweep finished."))).returncode, 0)
        self.assertEqual(run(self.root, stop(transcript(self.root, "Recorded it in Q004."))).returncode, 0)
        self.assertEqual(run(self.root, stop(None)).returncode, 0)

    def test_trigger_once(self):
        p = stop(transcript(self.root, "Done. I recorded the verdict in C007 and moved on."))
        r = run(self.root, p)
        self.assertEqual(r.returncode, 2)
        self.assertIn("durable-ack-guard", r.stderr)
        self.assertEqual(run(self.root, p).returncode, 0)

    def test_payload_message_and_recent_mtime(self):
        p = stop(None, last_assistant_message="Updated the ledger entry C007.")
        self.assertEqual(run(self.root, p).returncode, 2)
        os.utime(self.c7, None)
        p2 = stop(None, last_assistant_message="Logged it to C007 again.")
        self.assertEqual(run(self.root, p2).returncode, 0)

    def test_bypass_and_stop_active(self):
        p = stop(transcript(self.root, "Appended the row to C007."))
        self.assertEqual(run(self.root, p, ACK_OK="1").returncode, 0)
        self.assertEqual(run(self.root, p, HOOKS_QUIET="1").returncode, 0)
        self.assertEqual(run(self.root, {**p, "stop_hook_active": True}).returncode, 0)

    def test_failure_fails_open_loudly(self):
        r = run(self.root, raw="{nope")
        self.assertEqual(r.returncode, 0)
        self.assertIn("WARNING", r.stderr)
        self.assertTrue((Path(self.root) / "logs/state/hook-errors.log").exists())


if __name__ == "__main__":
    unittest.main()
