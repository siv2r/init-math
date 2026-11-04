"""Selftest for hooks/launch-guard.py, through its real entry point, on both harnesses."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "launch-guard.py"
STRIP = ("HOOKS_QUIET", "LAUNCH_GUARD_OFF")


def run(root, command, harness="claude", background=None, raw=None, **env_extra):
    env = {k: v for k, v in os.environ.items() if k not in STRIP}
    env["CLAUDE_PROJECT_DIR"] = root
    env.update(env_extra)
    ti = {"command": command}
    if background is not None:
        ti["run_in_background"] = background
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": root, "tool_input": ti}
    data = raw if raw is not None else json.dumps(payload)
    return subprocess.run([sys.executable, str(HOOK), "--harness", harness], input=data,
                          capture_output=True, text=True, env=env, timeout=30)


ALLOW = (
    "ls -la", "python3 census.py > out/census.txt 2>&1", "make &> build.log",
    "a && b || c", "bin/bg-run -- python3 census.py",
    "python3 part1.py & python3 part2.py & wait",
    "python3 -m http.server 8000 & sleep 1; curl -s localhost:8000; kill $!",
    "until curl -sf http://localhost:8000; do sleep 2; done",
    "for i in 1 2 3; do python3 step.py $i; sleep 1; done",
    "bin/wait-until-done --pid 4242 --max-min 30",
    "bin/wait-until-done 'census.py'",
    "git commit -m 'never nohup x & or loop on pgrep with sleep' -- a.md",
    "git commit -F - -- a.md <<'EOF'\nwhile pgrep x; do sleep 5; done\nnohup y &\nEOF",
    "echo done  # then run nohup z &",
    "cat <<<foo",
    "for f in *.ps; do convert $f out.pdf; sleep 1; done",
)
WAIT_LOOPS = (
    "until ! pgrep -f census.py; do sleep 60; done",
    "while kill -0 4242 2>/dev/null; do sleep 5; done",
    "while [ ! -f out/done ]; do sleep 10; done",
    "until test -e out/done; do sleep 10; done",
    "for i in $(seq 100); do tail -1 /tmp/x/tasks/abc.output; sleep 30; done",
    "while ps -p 4242 > /dev/null; do sleep 5; done",
)
DETACHED = (
    "nohup python3 census.py > out.log 2>&1 &",
    "bin/bg-run -- python3 census.py &",
    "setsid python3 census.py",
    "python3 census.py & disown",
    "python3 census.py &\necho launched",
)


class LaunchGuard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_allow_ordinary(self):
        for h in ("claude", "codex"):
            for c in ALLOW:
                r = run(self.root, c, harness=h)
                self.assertEqual(r.returncode, 0, (h, c, r.stderr))
        for c in ("python3 census.py", "bin/bg-run -- python3 census.py",
                  "python3 a.py & python3 b.py & wait"):
            self.assertEqual(run(self.root, c, background=True).returncode, 0, c)

    def test_double_background_blocks_every_time(self):
        for c in ("nohup python3 census.py &", "( until ! pgrep x; do sleep 60; done ) &",
                  "setsid python3 census.py", "python3 census.py & disown"):
            for _ in range(2):
                r = run(self.root, c, background=True)
                self.assertEqual(r.returncode, 2, c)
                self.assertIn("[launch-guard]", r.stderr)
                self.assertNotIn("re-issue", r.stderr)

    def test_wait_loop_blocks_every_time(self):
        for h in ("claude", "codex"):
            for c in WAIT_LOOPS:
                for _ in range(2):
                    r = run(self.root, c, harness=h)
                    self.assertEqual(r.returncode, 2, (h, c))
                    self.assertIn("bin/wait-until-done", r.stderr)
        self.assertIn("run_in_background", run(self.root, WAIT_LOOPS[0]).stderr)
        self.assertNotIn("run_in_background", run(self.root, WAIT_LOOPS[0], harness="codex").stderr)

    def test_detached_launch_nudges_once_claude(self):
        for c in DETACHED:
            r = run(self.root, c)
            self.assertEqual(r.returncode, 2, c)
            self.assertIn("run_in_background", r.stderr)
            self.assertIn("re-issue", r.stderr)
            self.assertEqual(run(self.root, c).returncode, 0, c)

    def test_detached_launch_nudges_once_codex(self):
        for c in DETACHED:
            r = run(self.root, c, harness="codex")
            self.assertEqual(r.returncode, 2, c)
            self.assertIn("foreground", r.stderr)
            self.assertIn("bin/bg-run --runs runs/ --detach", r.stderr)
            self.assertNotIn("run_in_background", r.stderr)
            self.assertEqual(run(self.root, c, harness="codex").returncode, 0, c)

    def test_codex_argv_command(self):
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": self.root,
                   "tool_input": {"command": ["bash", "-lc", "until ! pgrep -f x; do sleep 9; done"]}}
        r = run(self.root, "", harness="codex", raw=json.dumps(payload))
        self.assertEqual(r.returncode, 2)

    def test_bypass_only_from_hook_environment(self):
        for c in DETACHED + WAIT_LOOPS:
            self.assertEqual(run(self.root, c, LAUNCH_GUARD_OFF="1").returncode, 0, c)
        self.assertEqual(run(self.root, "nohup x &", background=True,
                             LAUNCH_GUARD_OFF="1").returncode, 0)
        self.assertEqual(run(self.root, "LAUNCH_GUARD_OFF=1 " + WAIT_LOOPS[0]).returncode, 2)
        self.assertEqual(run(self.root, DETACHED[0], HOOKS_QUIET="1").returncode, 0)

    def test_other_tool_ignored(self):
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Read",
                   "tool_input": {"file_path": "x"}}
        self.assertEqual(run(self.root, "", raw=json.dumps(payload)).returncode, 0)

    def test_failure_fails_open_loudly(self):
        r = run(self.root, "", raw="{nope")
        self.assertEqual(r.returncode, 0)
        self.assertIn("WARNING", r.stderr)
        self.assertTrue(Path(self.root, "logs/state/hook-errors.log").exists())


if __name__ == "__main__":
    unittest.main()
