"""Selftest for hooks/reflect-on-failure.py through its real entry point (JSON on stdin).

Four branches (docs/discipline/hook-authoring.md): allow, trigger, bypass, failure.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "reflect-on-failure.py"

TOML = """
[stack]
research_commands = ["solver", "bin/run-model"]

[[stack.failure_signatures]]
label = "out-of-memory"
regex = '''out of memory'''
"""


def post(command, stdout="", stderr="", event="PostToolUse", **extra):
    # Shape of a real Claude Code PostToolUse(Bash) payload: no exit code in tool_response.
    p = {"hook_event_name": event, "tool_name": "Bash", "cwd": "/tmp", "session_id": "s1",
         "tool_input": {"command": command, "description": "run"},
         "tool_response": {"interrupted": False, "isImage": False, "noOutputExpected": False,
                           "stdout": stdout, "stderr": stderr}}
    p.update(extra)
    return json.dumps(p)


class ReflectOnFailure(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "project.toml").write_text(TOML)
        self.env = {**os.environ, "CLAUDE_PROJECT_DIR": str(self.root)}
        self.env.pop("HOOKS_QUIET", None)

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, stdin, env=None):
        return subprocess.run([sys.executable, str(HOOK), "--harness", "claude"], input=stdin,
                              capture_output=True, text=True, env=env or self.env, timeout=30)

    def failures(self):
        f = self.root / "logs" / "failures.jsonl"
        return [json.loads(l) for l in f.read_text().splitlines()] if f.exists() else []

    # 1. allow
    def test_allow_success_and_non_research(self):
        r = self.run_hook(post("solver --n 10", stdout="done: 42"))
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        r = self.run_hook(post("grep -q x file", event="PostToolUseFailure", error="Exit code 1"))
        self.assertEqual(r.returncode, 0)
        r = self.run_hook(post("solver x", event="PostToolUseFailure", error="Exit code 130"))
        self.assertEqual(r.returncode, 0)  # deliberate interrupt
        r = self.run_hook(post("solver y", event="PostToolUseFailure", is_interrupt=True,
                               error="Exit code 1"))
        self.assertEqual(r.returncode, 0)  # interrupted by the user (live Claude field)
        # Claude PostToolUse: output that merely mentions an exit code is not a failure.
        r = self.run_hook(post("solver --report", stdout="Exit code 1 means infeasible"))
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.failures(), [])

    def test_inert_without_research_commands(self):
        (self.root / "project.toml").write_text("[stack]\nresearch_commands = []\n")
        r = self.run_hook(post("solver", event="PostToolUseFailure", error="Exit code 1"))
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        self.assertEqual(self.failures(), [])

    # 2. trigger: silent on the 1st, nudge on the 2nd
    def test_trigger_failure_event(self):
        for i in range(2):
            r = self.run_hook(post(f"solver run{i}", event="PostToolUseFailure",
                                   error="Exit code 1\nsegfault"))
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self.failures()[-1]["signature"], "solver-exit-nonzero")

    def test_trigger_recurrence(self):
        r = self.run_hook(post("nohup timeout 60 solver big", stdout="error: out of memory"))
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        self.assertEqual(self.failures()[0]["signature"], "out-of-memory")
        r = self.run_hook(post("solver bigger", stdout="... out of memory at step 9"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("'out-of-memory' has failed 2 times", r.stderr)
        self.assertIn("reflection-loop.md", r.stderr)
        # A non-zero exit with no signature gets a per-program signature (Codex-style payload).
        codex = json.dumps({"hook_event_name": "PostToolUse", "tool_name": "Bash",
                            "tool_input": {"command": ["bin/run-model", "-x"]},
                            "tool_response": json.dumps({"exit_code": 3, "output": "bad input"})})
        r = subprocess.run([sys.executable, str(HOOK), "--harness", "codex"], input=codex,
                           capture_output=True, text=True, env=self.env, timeout=30)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.failures()[-1]["signature"], "run-model-exit-nonzero")

    def test_cadence_doubles_then_steps_by_1000(self):
        import importlib.util
        sys.path.insert(0, str(HOOK.parent))
        spec = importlib.util.spec_from_file_location("reflect_on_failure", HOOK)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        due = [n for n in range(1, 5100) if mod.nudge_due(n)]
        self.assertEqual(due, [2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2024, 3024, 4024, 5024])

    def test_count_restarts_after_review(self):
        # The real reviewer (bin/journal) marks rows; the hook must then count from zero.
        journal = Path(__file__).resolve().parents[2] / "bin" / "journal"
        if not journal.exists():
            self.skipTest("bin/journal not present")
        fail = post("solver a", event="PostToolUseFailure", error="Exit code 1")
        self.run_hook(fail)
        for flag in ("--show-new", "--mark-reviewed"):
            subprocess.run([sys.executable, str(journal), "--root", str(self.root), flag, "failures"],
                           check=True, capture_output=True, timeout=30)
        r = self.run_hook(fail)
        self.assertEqual(r.returncode, 0)  # first UNREVIEWED failure: silent
        r = self.run_hook(fail)  # identical, possibly in the same second: still counts
        self.assertEqual(r.returncode, 2)

    # 3. bypass
    def test_bypass_quiet(self):
        self.run_hook(post("solver a", stdout="out of memory"))
        r = self.run_hook(post("solver b", stdout="out of memory"),
                          env={**self.env, "HOOKS_QUIET": "1"})
        self.assertEqual((r.returncode, r.stderr), (0, ""))

    # 4. failure: fail open, loudly
    def test_failure_malformed_and_crash(self):
        r = self.run_hook("not json")
        self.assertEqual(r.returncode, 0)
        self.assertIn("WARNING", r.stderr)
        (self.root / "project.toml").write_text("[stack\nbroken")
        r = self.run_hook(post("solver", stdout="out of memory"))
        self.assertEqual(r.returncode, 0)
        self.assertIn("WARNING", r.stderr)
        self.assertTrue((self.root / "logs" / "state" / "hook-errors.log").exists())


if __name__ == "__main__":
    unittest.main()
