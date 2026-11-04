"""Tests for the generated project's hook runtime (templates/core/files/hooks/_payload.py)."""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "skills/init-math/scripts/templates/core/files/hooks"
PAYLOADS = ROOT / "tests" / "payloads"
sys.dont_write_bytecode = True  # never write __pycache__ into the templates
sys.path.insert(0, str(HOOKS))

import _payload  # noqa: E402


def load(rel: str) -> dict:
    return json.loads((PAYLOADS / rel).read_text())


class NormalizeClaude(unittest.TestCase):
    def test_bash(self):
        ev = _payload.normalize(load("claude/pre-bash.json"), "claude")
        self.assertEqual((ev.event, ev.action, ev.command, ev.background),
                         ("PreToolUse", "shell", "rm -rf scratch", True))
        self.assertEqual(ev.transcript_path, "/tmp/t.jsonl")

    def test_edit(self):
        ev = _payload.normalize(load("claude/pre-edit.json"), "claude")
        self.assertEqual(ev.action, "edit")
        self.assertEqual(ev.paths, ["/tmp/proj/wiki/conjectures/C001-x.md"])

    def test_spawn(self):
        ev = _payload.normalize(load("claude/pre-agent.json"), "claude")
        self.assertEqual((ev.action, ev.agent_type), ("spawn", "claim-auditor"))
        self.assertIn("C001", ev.prompt)

    def test_stop(self):
        ev = _payload.normalize(load("claude/stop.json"), "claude")
        self.assertEqual((ev.event, ev.action), ("Stop", None))

    def test_live_captured(self):
        """Payloads captured from real headless Claude sessions (tests/probe, 2026-10-08; the
        Skill payload 2026-10-25, one Haiku session loading a probe skill)."""
        want = {"live-pre-bash": ("PreToolUse", "shell"), "live-post-bash": ("PostToolUse", "shell"),
                "live-pre-write": ("PreToolUse", "edit"), "live-post-write": ("PostToolUse", "edit"),
                "live-pre-agent": ("PreToolUse", "spawn"), "live-stop": ("Stop", None),
                "live-post-skill": ("PostToolUse", "skill")}
        for name, (event, action) in want.items():
            with self.subTest(name):
                ev = _payload.normalize(load(f"claude/{name}.json"), "claude")
                self.assertEqual((ev.event, ev.action), (event, action))
                if action == "edit":
                    self.assertTrue(ev.paths and ev.paths[0].endswith("notes/x.md"), ev.paths)
                if action == "spawn":
                    self.assertEqual(ev.agent_type, "probe-reviewer")
                if action == "shell":
                    self.assertEqual(ev.command, "ls")
        ev = _payload.normalize(load("claude/live-post-bash-failure.json"), "claude")
        self.assertEqual((ev.event, ev.action, ev.command),
                         ("PostToolUseFailure", "shell", "ls /nonexistent-probe-dir"))

    def test_live_failure_reaches_reflect_hook(self):
        """The live PostToolUseFailure payload, piped through the real failure hook, is logged."""
        hook = ROOT / "skills/init-math/scripts/templates/modules/17-reflect/files/hooks/reflect-on-failure.py"
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "hooks").mkdir()
            for src in (HOOKS / "_payload.py", hook):
                (root / "hooks" / src.name).write_text(src.read_text())
            (root / "project.toml").write_text('[stack]\nresearch_commands = ["ls"]\n')
            env = {**os.environ, "CLAUDE_PROJECT_DIR": d, "PYTHONDONTWRITEBYTECODE": "1"}
            env.pop("HOOKS_QUIET", None)
            r = subprocess.run([sys.executable, str(root / "hooks" / hook.name), "--harness", "claude"],
                               input=(PAYLOADS / "claude/live-post-bash-failure.json").read_text(),
                               capture_output=True, text=True, env=env, timeout=30)
            self.assertEqual(r.returncode, 0, r.stderr)  # first occurrence: logged, silent
            rows = [json.loads(l) for l in (root / "logs/failures.jsonl").read_text().splitlines()]
            self.assertEqual(rows[0]["signature"], "ls-exit-nonzero")
            self.assertIn("No such file", rows[0]["excerpt"])

    def test_missing_transcript(self):
        p = load("claude/stop.json")
        del p["transcript_path"]
        self.assertIsNone(_payload.normalize(p, "claude").transcript_path)


class NormalizeCodex(unittest.TestCase):
    def test_argv_command(self):
        """A list command (Codex shape, unverified) becomes the shell text that runs."""
        def cmd(argv):
            return _payload.normalize({"hook_event_name": "PreToolUse", "tool_name": "shell",
                                       "tool_input": {"command": argv}}, "codex").command
        self.assertEqual(cmd(["bash", "-lc", "rm -rf x && ls"]), "rm -rf x && ls")
        self.assertEqual(cmd(["/bin/zsh", "-c", "ls"]), "ls")
        self.assertEqual(cmd(["git", "commit", "-m", "two words"]), "git commit -m 'two words'")

    def test_apply_patch_paths(self):
        ev = _payload.normalize(load("codex/apply-patch-synthetic.json"), "codex")
        self.assertEqual(ev.action, "edit")
        self.assertEqual(sorted(ev.paths),
                         ["new/name.md", "notes/new.md", "old/name.md", "wiki/conjectures/C001-x.md"])

    def test_captured(self):
        captured = [p for p in sorted((PAYLOADS / "codex").glob("*.json")) if "synthetic" not in p.name]
        if not captured:
            self.skipTest("no captured Codex payloads yet (tests/probe/codex-probe.md)")
        # what each captured payload must normalize to (event, action, paths, agent_type, hidden)
        want = {
            "pre-apply-patch.json": ("PreToolUse", "edit", ["notes/y.md"], "", False),
            "post-apply-patch.json": ("PostToolUse", "edit", ["notes/y.md"], "", False),
            "pre-bash-in-subagent.json": ("PreToolUse", "shell", [], "probe-reviewer", False),
            "post-bash-in-subagent.json": ("PostToolUse", "shell", [], "probe-reviewer", False),
            "pre-spawn.json": ("PreToolUse", "spawn", [], "probe-reviewer", True),
            "pre-wait-agent.json": ("PreToolUse", "other", [], "", False),
            "subagent-start.json": ("SubagentStart", None, [], "probe-reviewer", False),
            "subagent-stop.json": ("SubagentStop", None, [], "probe-reviewer", False),
            "stop.json": ("Stop", None, [], "", False),
        }
        self.assertEqual(sorted(p.name for p in captured), sorted(want))
        for p in captured:
            with self.subTest(p.name):
                ev = _payload.normalize(json.loads(p.read_text()), "codex")
                self.assertEqual((ev.event, ev.action, ev.paths, ev.agent_type, ev.prompt_hidden),
                                 want[p.name])
                self.assertTrue(ev.transcript_path)
                if ev.prompt_hidden:
                    self.assertEqual(ev.prompt, "")
        stop = _payload.normalize(json.loads((PAYLOADS / "codex" / "subagent-stop.json").read_text()), "codex")
        self.assertEqual(stop.report, "pong")
        sh = _payload.normalize(json.loads((PAYLOADS / "codex" / "pre-bash-in-subagent.json").read_text()), "codex")
        self.assertEqual(sh.command, "head -n 1 .agents/skills/probe/SKILL.md")

    def test_shell_list_command(self):
        ev = _payload.normalize({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                                 "tool_input": {"command": ["bash", "-lc", "ls"]}}, "codex")
        self.assertEqual(ev.command, "ls")


class Responses(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.root = self._t.name
        self.ev = _payload.Event(harness="claude", event="PreToolUse", action="shell", root=self.root)

    def tearDown(self):
        self._t.cleanup()

    def test_nudge_once(self):
        with mock.patch.dict(os.environ, {"HOOKS_QUIET": ""}):
            with self.assertRaises(SystemExit) as cm:
                _payload.nudge_once(self.ev, "h", "k", "msg")
            self.assertEqual(cm.exception.code, 2)
            with self.assertRaises(SystemExit) as cm:
                _payload.nudge_once(self.ev, "h", "k", "msg")
            self.assertEqual(cm.exception.code, 0)
        self.assertTrue((Path(self.root) / "logs/nudges.jsonl").exists())

    def test_quiet(self):
        with mock.patch.dict(os.environ, {"HOOKS_QUIET": "1"}):
            with self.assertRaises(SystemExit) as cm:
                _payload.nudge_once(self.ev, "h", "k2", "msg")
            self.assertEqual(cm.exception.code, 0)

    def test_mark_alive_only_for_harness_events(self):
        """A harness payload (it has a session id) leaves the marker bin/selftest and the
        commit gate look for; a hand-made payload does not."""
        marker = Path(self.root) / "logs/state" / _payload.ALIVE
        _payload.mark_alive(_payload.Event(harness="codex", event="Stop", action=None,
                                           root=self.root))
        self.assertFalse(marker.exists())
        _payload.mark_alive(_payload.Event(harness="codex", event="Stop", action=None,
                                           root=self.root, session_id="s1",
                                           raw={"model": "big-model"}))
        rec = json.loads(marker.read_text())
        self.assertEqual((rec["harness"], rec["main_session"], rec["main_model"]),
                         ("codex", "s1", "big-model"))
        # a subagent's hook refreshes the marker but not the main thread's model
        _payload.mark_alive(_payload.Event(harness="codex", event="PreToolUse", action="shell",
                                           root=self.root, session_id="s1", agent_type="worker",
                                           raw={"model": "small-model"}))
        self.assertEqual(json.loads(marker.read_text())["main_model"], "big-model")
        # Every payload captured from a live session carries a session id, so a real
        # session always leaves the marker (no permanent "hooks never ran" warning).
        for rel in ("codex/stop.json", "codex/subagent-start.json", "codex/pre-apply-patch.json",
                    "codex/post-bash-in-subagent.json", "claude/live-stop.json",
                    "claude/live-pre-bash.json"):
            with self.subTest(rel):
                ev = _payload.normalize(load(rel), rel.split("/")[0])
                self.assertTrue(ev.session_id)

    def test_stop_continue_codex_json(self):
        ev = _payload.Event(harness="codex", event="Stop", action=None, root=self.root)
        buf = io.StringIO()
        with mock.patch("sys.stdout", buf), self.assertRaises(SystemExit) as cm:
            _payload.stop_continue(ev, "h", "k", "keep going")
        self.assertEqual(cm.exception.code, 0)
        self.assertEqual(json.loads(buf.getvalue())["decision"], "block")


class FailOpen(unittest.TestCase):
    """A crashing hook must exit 0, warn on stderr and log the traceback."""

    def _run(self, script: str, stdin: str):
        with tempfile.TemporaryDirectory() as d:
            hooks = Path(d) / "hooks"
            hooks.mkdir()
            (hooks / "_payload.py").write_text((HOOKS / "_payload.py").read_text())
            (hooks / "boom.py").write_text(script)
            r = subprocess.run([sys.executable, str(hooks / "boom.py"), "--harness", "claude"],
                               input=stdin, capture_output=True, text=True,
                               env={"CLAUDE_PROJECT_DIR": d, "PATH": "/usr/bin:/bin"})
            log = Path(d) / "logs/state/hook-errors.log"
            return r, (log.read_text() if log.exists() else "")

    BOOM = ("import sys; sys.path.insert(0, __import__('os').path.dirname(__file__))\n"
            "import _payload\n"
            "def main(ev):\n    raise RuntimeError('kaboom')\n"
            "_payload.run(main, 'boom')\n")

    def test_crash_fails_open_loudly(self):
        r, log = self._run(self.BOOM, json.dumps({"hook_event_name": "Stop"}))
        self.assertEqual(r.returncode, 0)
        self.assertIn("WARNING", r.stderr)
        self.assertIn("kaboom", log)

    def test_malformed_payload(self):
        r, log = self._run(self.BOOM, "{not json")
        self.assertEqual(r.returncode, 0)
        self.assertIn("WARNING", r.stderr)
        self.assertIn("JSONDecodeError", log)


if __name__ == "__main__":
    unittest.main()
