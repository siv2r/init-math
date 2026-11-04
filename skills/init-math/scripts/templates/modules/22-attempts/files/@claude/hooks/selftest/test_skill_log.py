"""Selftest for hooks/skill-log.py, through its real entry point."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "skill-log.py"


def run(root, payload=None, raw=None, **env_extra):
    env = {k: v for k, v in os.environ.items() if k not in ("HOOKS_QUIET", "SKILL_LOG_OFF")}
    env["CLAUDE_PROJECT_DIR"] = root
    env.update(env_extra)
    data = raw if raw is not None else json.dumps(payload)
    return subprocess.run([sys.executable, str(HOOK), "--harness", "claude"], input=data,
                          capture_output=True, text=True, env=env, timeout=30)


def skill(name="attack"):
    # The shape of a live capture (2026-10-25): tool_input.skill names the skill.
    return {"hook_event_name": "PostToolUse", "tool_name": "Skill", "session_id": "s1",
            "tool_input": {"skill": name}, "tool_response": {"success": True, "commandName": name}}


class SkillLog(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.log = Path(self.root) / "logs/skills.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def rows(self):
        return [json.loads(l) for l in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_skill_load_is_one_row(self):
        r = run(self.root, skill("attack"))
        self.assertEqual(r.returncode, 0, r.stderr)
        rows = self.rows()
        self.assertEqual([x["skill"] for x in rows], ["attack"])
        self.assertIn("ts", rows[0])

    def test_other_tool_is_no_row(self):
        p = {"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {"command": "ls"}}
        self.assertEqual(run(self.root, p).returncode, 0)
        self.assertEqual(self.rows(), [])

    def test_bypass(self):
        self.assertEqual(run(self.root, skill(), SKILL_LOG_OFF="1").returncode, 0)
        self.assertEqual(self.rows(), [])

    def test_malformed_fails_open_loudly(self):
        r = run(self.root, raw="[1, 2")
        self.assertEqual(r.returncode, 0)
        self.assertIn("WARNING", r.stderr)


if __name__ == "__main__":
    unittest.main()
