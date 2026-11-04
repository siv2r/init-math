"""Shared helpers for the scans hook selftests (not a test module itself)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1]
BIN = Path(__file__).resolve().parents[2] / "bin"


def shell(cmd):
    return json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": "/tmp",
                       "tool_input": {"command": cmd}})


def spawn(agent, prompt):
    return json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Agent", "cwd": "/tmp",
                       "tool_input": {"subagent_type": agent, "prompt": prompt}})


class Project:
    """A temp project root with the given bin scripts copied in."""

    def __init__(self, scripts=()):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "bin").mkdir()
        for s in scripts:
            shutil.copy2(BIN / s, self.root / "bin" / s)
        self.env = {**os.environ, "CLAUDE_PROJECT_DIR": str(self.root)}
        for k in list(self.env):
            if k == "HOOKS_QUIET" or k.endswith("_CHECK_OK") or k == "STALE_SCAN_OK":
                self.env.pop(k)

    def write(self, rel, text):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return p

    def run(self, hook, stdin, **extra_env):
        return subprocess.run([sys.executable, str(HOOKS / hook), "--harness", "claude"], input=stdin,
                              capture_output=True, text=True, env={**self.env, **extra_env}, timeout=60)

    def cleanup(self):
        self.tmp.cleanup()
