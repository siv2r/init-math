"""Selftest for hooks/gate-dispatch-log.py through its real entry point.

Four branches (docs/discipline/hook-authoring.md): allow (nothing recorded), trigger
(a reviewer dispatch is recorded with the file's blob id), bypass (files the hook must not
record), failure (fail open, loudly). The hook never refuses a call.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "gate-dispatch-log.py"


def spawn(agent, prompt):
    return json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Agent", "cwd": "/tmp",
                       "tool_input": {"subagent_type": agent, "prompt": prompt}})


class GateDispatchLog(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "wiki").mkdir()
        self.doc = self.root / "wiki" / "note.md"
        self.doc.write_text("Lemma. Every finite group of prime order is cyclic.\n")
        self.env = {**os.environ, "CLAUDE_PROJECT_DIR": str(self.root)}
        self.env.pop("HOOKS_QUIET", None)

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, stdin, env=None):
        return subprocess.run([sys.executable, str(HOOK), "--harness", "claude"], input=stdin,
                              capture_output=True, text=True, env=env or self.env, timeout=30)

    def rows(self):
        f = self.root / ".gates" / "dispatches.jsonl"
        return [json.loads(x) for x in f.read_text().splitlines()] if f.exists() else []

    # 1. allow: a non-reviewer dispatch, or a brief naming no file, records nothing
    def test_allow(self):
        r = self.run_hook(spawn("worker", "Tidy wiki/note.md; claim-auditor reviews later."))
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        r = self.run_hook(spawn("claim-auditor", "Review the summary pasted below."))
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.rows(), [])

    # 2. trigger: a reviewer dispatch records gate, path and the git blob id
    def test_trigger(self):
        r = self.run_hook(spawn("claim-auditor", "Audit `wiki/note.md:1` at its stated scope."))
        self.assertEqual(r.returncode, 0)
        data = self.doc.read_bytes()
        blob = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
        rows = self.rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["gate"], rows[0]["path"], rows[0]["blob"]),
                         ("claim-auditor", "wiki/note.md", blob))
        self.assertTrue(rows[0]["id"])
        # no agent type (e.g. another harness): the one reviewer named in the brief
        r = self.run_hook(spawn("", "You are the red-team. Attack wiki/note.md."))
        self.assertEqual(self.rows()[-1]["gate"], "red-team")
        # reviewers come from project.toml when it lists them
        (self.root / "project.toml").write_text('[gates.verdicts]\nlogic-check = ["OK"]\n')
        self.run_hook(spawn("logic-check", "Check wiki/note.md."))
        self.assertEqual(self.rows()[-1]["gate"], "logic-check")
        # an absolute path inside the project is recorded relative to it
        self.run_hook(spawn("logic-check", f"Check {self.doc.resolve()} please."))
        self.assertEqual(self.rows()[-1]["path"], "wiki/note.md")
        self.assertEqual(len(self.rows()), 4)

    # 2b. Codex: the brief is encrypted, so the record comes from the reviewer's final reply
    def test_codex_subagent_stop(self):
        (self.root / "wiki" / "other.md").write_text("x\n")
        hidden = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "collaborationspawn_agent",
                             "cwd": "/tmp", "tool_input": {"agent_type": "claim-auditor",
                                                           "message": "gAAAAABqx8TuQ9RuotQPtS1DxvGQ7-LbtXlFrGl1TlJ5LXNZ02S_ra3WgtQ-XweF5Sjd9k=="}})
        r = subprocess.run([sys.executable, str(HOOK), "--harness", "codex"], input=hidden,
                           capture_output=True, text=True, env=self.env, timeout=30)
        self.assertEqual((r.returncode, self.rows()), (0, []))

        def stop(agent, reply):
            return json.dumps({"hook_event_name": "SubagentStop", "cwd": "/tmp", "agent_type": agent,
                               "agent_id": "a1", "last_assistant_message": reply})
        for agent, reply in [("claim-auditor", "Reviewed: wiki/note.md\nVerdict: SOUND (cf. wiki/other.md)"),
                             ("worker", "Reviewed: wiki/note.md"),
                             ("red-team", "Verdict: SURVIVED. Probed wiki/other.md.")]:
            subprocess.run([sys.executable, str(HOOK), "--harness", "codex"], input=stop(agent, reply),
                           capture_output=True, text=True, env=self.env, timeout=30)
        got = [(x["gate"], x["path"], x["via"]) for x in self.rows()]
        self.assertEqual(got, [("claim-auditor", "wiki/note.md", "report"),
                               ("red-team", "wiki/other.md", "report")])

    # 3. bypass: files the hook must not record
    def test_bypass(self):
        (self.root / ".gates").mkdir()
        (self.root / ".gates" / "stamps.jsonl").write_text("")
        outside = Path(self.tmp.name).parent / "elsewhere.md"
        brief = (f"Audit ../elsewhere.md and {outside} and .gates/stamps.jsonl and "
                 "https://example.org/wiki/note.md and wiki/missing.md")
        r = self.run_hook(spawn("claim-auditor", brief))
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.rows(), [])
        # two reviewer names and no agent type: ambiguous, nothing recorded
        self.run_hook(spawn("", "claim-auditor then red-team on wiki/note.md"))
        self.assertEqual(self.rows(), [])

    # 4. failure: fail open, loudly
    def test_failure(self):
        r = self.run_hook("{not json")
        self.assertEqual(r.returncode, 0)
        self.assertIn("WARNING", r.stderr)
        (self.root / "project.toml").write_text("[gates.verdicts\nbroken")
        r = self.run_hook(spawn("claim-auditor", "Audit wiki/note.md"))
        self.assertEqual(r.returncode, 0)
        self.assertIn("WARNING", r.stderr)
        self.assertTrue((self.root / "logs" / "state" / "hook-errors.log").exists())


if __name__ == "__main__":
    unittest.main()
