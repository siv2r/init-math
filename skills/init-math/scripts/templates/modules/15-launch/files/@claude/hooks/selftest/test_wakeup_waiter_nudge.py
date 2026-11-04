"""Selftest for hooks/wakeup-waiter-nudge.py, through its real entry point."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "wakeup-waiter-nudge.py"


def run(root, payload=None, raw=None, **env_extra):
    env = {k: v for k, v in os.environ.items() if k not in ("HOOKS_QUIET", "WAKEUP_OK")}
    env["CLAUDE_PROJECT_DIR"] = root
    env.update(env_extra)
    data = raw if raw is not None else json.dumps(payload)
    return subprocess.run([sys.executable, str(HOOK), "--harness", "claude"], input=data,
                          capture_output=True, text=True, env=env, timeout=30)


def transcript(root, background):
    lines = [
        {"type": "user", "message": {"role": "user", "content": "Run the census for n <= 40."}},
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "t1", "name": "Bash",
             "input": {"command": "bin/bg-run -- python3 census.py", "run_in_background": background}}]}},
        {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "started"}]}},
    ]
    p = Path(root) / "transcript.jsonl"
    p.write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    return str(p)


def wake(path, delay=270, **extra):
    return {"hook_event_name": "PreToolUse", "tool_name": "ScheduleWakeup", "transcript_path": path,
            "tool_input": {"delaySeconds": delay, "prompt": "check the job", **extra}}


class WakeupWaiter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_allow_no_background_job(self):
        self.assertEqual(run(self.root, wake(transcript(self.root, False))).returncode, 0)

    def test_allow_long_backstop(self):
        self.assertEqual(run(self.root, wake(transcript(self.root, True), delay=1800)).returncode, 0)

    def test_allow_no_transcript(self):
        self.assertEqual(run(self.root, wake(None)).returncode, 0)

    def test_trigger_then_reissue_proceeds(self):
        p = wake(transcript(self.root, True))
        r = run(self.root, p)
        self.assertEqual(r.returncode, 2)
        self.assertIn("wakeup-waiter-nudge", r.stderr)
        self.assertEqual(run(self.root, p).returncode, 0)

    def test_bypass(self):
        self.assertEqual(run(self.root, wake(transcript(self.root, True)), WAKEUP_OK="1").returncode, 0)

    def test_failure_fails_open_loudly(self):
        r = run(self.root, raw="{nope")
        self.assertEqual(r.returncode, 0)
        self.assertIn("WARNING", r.stderr)
        self.assertTrue((Path(self.root) / "logs/state/hook-errors.log").exists())


if __name__ == "__main__":
    unittest.main()
