"""Selftest for the commit gate: .githooks/pre-commit together with bin/gate-stamp.

Runs real `git commit`s in a temporary repository. Four branches: allow (a commit that
records no finding), trigger (missing, stale, or stamp-without-dispatch reviews refuse),
bypass (GATE_OK=1, refuse = "once"), failure (a broken config fails open, loudly).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
PRE_COMMIT = BASE / ".githooks" / "pre-commit"
GATE_STAMP = BASE / "bin" / "gate-stamp"

CONFIG = """[gates]
enabled = true
refuse = "{refuse}"

[gates.verdicts]
claim-auditor = ["SOUND"]
proof-referee = ["CLEAN", "CLEAN-MINOR"]
red-team = ["SURVIVED"]

[gates.proof]
paths = ["**/*.md", "**/*.tex"]
exclude = ["docs/**"]
gates = ["proof-referee", "claim-auditor"]

[[gates.rules]]
paths = ["wiki/conjectures/C*.md"]
status = ["supported"]
gates = ["claim-auditor", "red-team"]

[[gates.rules]]
paths = ["wiki/conjectures/C*.md"]
status = ["proved"]
unless = '^settled-by:\\s*\\S'
gates = ["claim-auditor", "proof-referee", "red-team"]
last_look = ["claim-auditor"]

[[gates.rules]]
paths = ["wiki/conjectures/C*.md"]
status = ["proved"]
when = '^settled-by:\\s*\\S'
gates = ["claim-auditor"]
"""

CONJ = """---
id: C001
status: {status}
---
# C001: every graph in the family has a perfect matching
"""

NOTE = """# Notes

Lemma 1. The sum of the degrees is even.

Proof. Each edge contributes 2 to the sum. ∎

Afterword: more examples to come.
"""


@unittest.skipUnless(shutil.which("git"), "git not installed")
class CommitGate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith("GIT_") and k not in ("GATE_OK", "HOOKS_QUIET")}
        self.env.update({"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"})
        self.git("init", "-q")
        for k, v in (("user.name", "Test"), ("user.email", "test@example.org"),
                     ("commit.gpgsign", "false")):
            self.git("config", k, v)
        (self.root / ".githooks").mkdir()
        shutil.copy2(PRE_COMMIT, self.root / ".githooks" / "pre-commit")
        (self.root / "bin").mkdir()
        shutil.copy2(GATE_STAMP, self.root / "bin" / "gate-stamp")
        (self.root / "wiki" / "conjectures").mkdir(parents=True)
        self.conj = self.root / "wiki" / "conjectures" / "C001-matching.md"
        self.conj.write_text(CONJ.format(status="open"))
        self.note = self.root / "wiki" / "note.md"
        self.note.write_text(NOTE)
        self.config("always")
        self.git("add", "-A")
        # like a new project: the first commit is made before the gate is switched on
        self.assertEqual(self.commit("initial").returncode, 0)
        self.git("config", "core.hooksPath", ".githooks")

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args, env=None):
        return subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True,
                              env=env or self.env, timeout=60)

    def commit(self, msg, *paths, env=None):
        args = ["commit", "-q", "-m", msg] + (["--", *paths] if paths else [])
        return self.git(*args, env=env)

    def config(self, refuse):
        (self.root / "project.toml").write_text(CONFIG.format(refuse=refuse))

    def dispatch(self, gate, rel):
        blob = self.git("hash-object", "--", rel).stdout.strip()
        d = self.root / ".gates"
        d.mkdir(exist_ok=True)
        with open(d / "dispatches.jsonl", "a") as f:
            row = json.dumps({"id": f"{gate}-{blob[:8]}", "gate": gate, "path": rel,
                              "blob": blob, "ts": "t"})
            f.write(row + "\n" + row + "\n")  # duplicated, as a union merge may leave it

    def stamp(self, gate, rel, verdict, kind="review"):
        ex = self.root / "excerpt.txt"
        ex.write_text(f"Verdict: {verdict}\n")
        return subprocess.run([sys.executable, str(self.root / "bin" / "gate-stamp"), "--kind", kind,
                               gate, rel, verdict, str(ex)], cwd=self.root, capture_output=True,
                              text=True, env=self.env, timeout=60)

    def flip(self):
        self.conj.write_text(CONJ.format(status="supported"))
        self.git("add", "--", str(self.conj))
        return "wiki/conjectures/C001-matching.md"

    def test_warns_when_harness_hooks_never_ran(self):
        """Committed work but no harness hook ever ran: warn, never refuse; quiet once one has."""
        (self.root / "README.md").write_text("hello\n")
        self.git("add", "README.md")
        r = self.commit("readme")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("never run this project's hooks", r.stderr)
        state = self.root / "logs" / "state"
        state.mkdir(parents=True)
        (state / "harness-hooks-seen").write_text("codex 2026-10-22T10:00:00\n")
        (self.root / "README.md").write_text("hello again\n")
        self.git("add", "README.md")
        r = self.commit("readme 2")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("never run", r.stderr)

    def test_warns_about_manuscripts_in_scratch(self):
        (self.root / ".gitignore").write_text("scratch/\n")
        (self.root / "scratch").mkdir()
        (self.root / "scratch" / "brief.md").write_text("throwaway\n")
        (self.root / "README.md").write_text("hello\n")
        self.git("add", "README.md")
        r = self.commit("readme")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("scratch/ folders", r.stderr)  # a fresh throwaway is fine
        (self.root / "scratch" / "paper.tex").write_text("\\documentclass{article}\n")
        (self.root / "README.md").write_text("hello again\n")
        self.git("add", "README.md")
        r = self.commit("readme 2")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("scratch/paper.tex", r.stderr)

    def test_shows_several_active_questions_warning(self):
        qc = self.root / "bin" / "question-check"
        qc.write_text("#!/bin/sh\necho 'WARN 2 questions are active (Q001, Q002): ...'\n"
                      "echo 'WARN Q001: active, but no conjecture links it yet'\n")
        qc.chmod(0o755)
        (self.root / "README.md").write_text("hello\n")
        self.git("add", "README.md")
        r = self.commit("readme")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("2 questions are active", r.stderr)
        self.assertNotIn("no conjecture links", r.stderr)

    def test_shows_ledger_flags_without_enforcing(self):
        # A project with the attempt ledger: its flags and lint problems are shown, the commit
        # still goes through.
        tool = self.root / "bin" / "attempts"
        tool.write_text("#!/bin/sh\nif [ \"$1\" = --gate ]; then echo 'FLAG: X001 needs a look'; exit 0; fi\n"
                        "echo 'L001-x.md: a record problem'; echo 'summary line'; exit 1\n")
        tool.chmod(0o755)
        (self.root / "README.md").write_text("hello again\n")
        self.git("add", "README.md")
        r = self.commit("readme")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("FLAG: X001 needs a look", r.stderr)
        self.assertIn("a record problem", r.stderr)
        self.assertNotIn("summary line", r.stderr)

    def promoted_with_stamps(self, text):
        """Write a conjecture at `supported` (or proved) with the reviews stamped, then commit."""
        self.conj.write_text(text)
        self.git("add", "--", str(self.conj))
        rel = "wiki/conjectures/C001-matching.md"
        for gate, verdict in (("claim-auditor", "SOUND"), ("red-team", "SURVIVED"), ("proof-referee", "CLEAN")):
            self.dispatch(gate, rel)
            self.stamp(gate, rel, verdict)
        self.stamp("claim-auditor", rel, "SOUND", "last-look")
        return self.commit("promote")

    def test_argued_only_support_needs_the_owner(self):
        # A status above weakly-supported resting only on argued
        # evidence is refused unless the owner's decision is recorded.
        argued = (CONJ.format(status="supported") + "\n## Evidence\n"
                  "- 2026-01-01 · heuristic count · the density argument\n"
                  "  argued: heuristic — work/x/argument.md\n")
        r = self.promoted_with_stamps(argued)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("rests only on argued evidence", r.stderr)
        r = self.promoted_with_stamps(argued + "owner-override: 2026-01-02 Ada: mark it supported\n")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_proved_with_an_open_assumption_is_conditional(self):
        text = (CONJ.format(status="proved") + "\n@assumes: C009 — the lift — argued (moral)\n"
                "\n## Evidence\n- 2026-01-01 · proof · work/x/proof.md\n")
        r = self.promoted_with_stamps(text)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("the proof is conditional", r.stderr)
        r = self.promoted_with_stamps(text.replace("\n## Evidence", "conditional-on: C009 (the lift)\n## Evidence"))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_shows_hedge_scan_findings_without_enforcing(self):
        tool = self.root / "bin" / "hedge-scan"
        tool.write_text("import sys\nprint('hedge-scan --diff: note.md: removed hedge heuristically')\n")
        tool.chmod(0o755)
        (self.root / "README.md").write_text("plain\n")
        self.git("add", "README.md")
        r = self.commit("readme")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("commit gate: hedge-scan --diff: note.md: removed hedge", r.stderr)

    def test_pure_move_needs_no_review(self):
        """Moving a file with a proof, content unchanged, records no finding; a move with an
        edit inside the proof still needs its reviews."""
        (self.root / "work" / "graphs").mkdir(parents=True)
        self.git("mv", "wiki/note.md", "work/graphs/note.md")
        r = self.commit("move the note")
        self.assertEqual(r.returncode, 0, r.stderr)
        moved = self.root / "work" / "graphs" / "note.md"
        self.git("mv", "work/graphs/note.md", "work/note.md")
        (self.root / "work" / "note.md").write_text(NOTE.replace("contributes 2", "adds 2"))
        self.git("add", "-A")
        r = self.commit("move and edit the proof")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("proof-referee", r.stderr)
        self.assertFalse(moved.exists())

    # 1. allow: commits that record no finding
    def test_allow(self):
        (self.root / "README.md").write_text("hello\n")
        self.git("add", "README.md")
        self.assertEqual(self.commit("readme").returncode, 0)
        self.conj.write_text(CONJ.format(status="testing"))
        self.git("add", "-A")
        self.assertEqual(self.commit("start testing").returncode, 0)
        self.note.write_text(NOTE.replace("more examples", "two more examples"))
        self.git("add", "-A")
        r = self.commit("edit outside the proof")
        self.assertEqual(r.returncode, 0, r.stderr)

    # 2. trigger: missing, stale, and stamp-without-dispatch reviews refuse
    def test_trigger(self):
        rel = self.flip()
        r = self.commit("promote")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("needs a passing claim-auditor review", r.stderr)
        self.assertIn("red-team", r.stderr)
        # a stamp is refused until the gate was dispatched on this content
        self.assertNotEqual(self.stamp("claim-auditor", rel, "SOUND").returncode, 0)
        for gate, verdict in (("claim-auditor", "SOUND"), ("red-team", "SURVIVED")):
            self.dispatch(gate, rel)
            self.assertEqual(self.stamp(gate, rel, verdict).returncode, 0)
        r = self.commit("promote")
        self.assertEqual(r.returncode, 0, r.stderr)
        # a proof edit; reviewed, then edited again: stale
        self.note.write_text(NOTE.replace("contributes 2", "contributes exactly 2"))
        for gate, verdict in (("proof-referee", "CLEAN"), ("claim-auditor", "SOUND")):
            self.dispatch(gate, "wiki/note.md")
            self.assertEqual(self.stamp(gate, "wiki/note.md", verdict).returncode, 0)
        self.note.write_text(NOTE.replace("contributes 2", "adds 2"))
        self.git("add", "-A")
        r = self.commit("tweak proof")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("stale", r.stderr)
        # a stamp row with no dispatch row (written by hand)
        blob = self.git("hash-object", "--", "wiki/note.md").stdout.strip()
        with open(self.root / ".gates" / "stamps.jsonl", "a") as f:
            for g in ("proof-referee", "claim-auditor"):
                f.write(json.dumps({"id": g + "x", "gate": g, "path": "wiki/note.md",
                                    "blob": blob, "verdict": "CLEAN" if g[0] == "p" else "SOUND"}) + "\n")
        r = self.commit("tweak proof")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no matching dispatch", r.stderr)

    # 2a. a failing verdict is recorded but never satisfies the gate
    def test_failing_row_does_not_satisfy(self):
        rel = self.flip()
        self.dispatch("claim-auditor", rel)
        self.dispatch("red-team", rel)
        self.assertEqual(self.stamp("claim-auditor", rel, "OVER-CLAIMED").returncode, 0)
        self.assertEqual(self.stamp("red-team", rel, "SURVIVED").returncode, 0)
        r = self.commit("promote")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("needs a passing claim-auditor review", r.stderr)

    # 2b. `git commit -- <paths>` checks the paths being committed, not other staged files
    def test_pathspec_commit(self):
        rel = self.flip()
        (self.root / "other.md").write_text("unrelated\n")
        self.git("add", "other.md")
        r = self.commit("other only", "other.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.commit("promote", rel)
        self.assertNotEqual(r.returncode, 0)
        for gate, verdict in (("claim-auditor", "SOUND"), ("red-team", "SURVIVED")):
            self.dispatch(gate, rel)
            self.stamp(gate, rel, verdict)
        r = self.commit("promote", rel)
        self.assertEqual(r.returncode, 0, r.stderr)

    # 2c. proved by citation (a `settled-by:` line) needs only the claim-auditor
    def test_settled_by(self):
        rel = "wiki/conjectures/C001-matching.md"
        self.conj.write_text(CONJ.format(status="proved"))
        self.git("add", "--", str(self.conj))
        r = self.commit("proved, no citation")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("proof-referee", r.stderr)
        self.assertIn("red-team", r.stderr)
        self.assertIn("needs a passing claim-auditor last look", r.stderr)
        self.conj.write_text(CONJ.format(status="proved") + "settled-by: known-results/hall.md\n")
        self.git("add", "--", str(self.conj))
        r = self.commit("proved by citation")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("proof-referee", r.stderr)
        self.assertNotIn("red-team", r.stderr)
        self.assertNotIn("last look", r.stderr)
        self.dispatch("claim-auditor", rel)
        self.assertEqual(self.stamp("claim-auditor", rel, "SOUND").returncode, 0)
        r = self.commit("proved by citation")
        self.assertEqual(r.returncode, 0, r.stderr)

    # 2d. a last look never stands in for a review; `proved` by our own proof needs one
    def test_last_look(self):
        rel = self.flip()
        self.dispatch("claim-auditor", rel)
        self.dispatch("red-team", rel)
        self.assertEqual(self.stamp("claim-auditor", rel, "SOUND", "last-look").returncode, 0)
        self.assertEqual(self.stamp("red-team", rel, "SURVIVED", "exchange").returncode, 0)
        r = self.commit("promote")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("needs a passing claim-auditor review", r.stderr)
        self.assertNotIn("red-team", r.stderr)
        self.assertNotIn("last look", r.stderr)
        self.conj.write_text(CONJ.format(status="proved"))
        self.git("add", "--", str(self.conj))
        for gate, verdict in (("claim-auditor", "SOUND"), ("proof-referee", "CLEAN"),
                              ("red-team", "SURVIVED")):
            self.dispatch(gate, rel)
            self.assertEqual(self.stamp(gate, rel, verdict).returncode, 0)
        r = self.commit("proved")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("claim-auditor last look is stale", r.stderr)
        self.assertEqual(self.stamp("claim-auditor", rel, "SOUND", "last-look").returncode, 0)
        r = self.commit("proved")
        self.assertEqual(r.returncode, 0, r.stderr)

    # 3. bypass: GATE_OK=1 is logged; refuse = "once" lets an identical retry through
    def test_bypass(self):
        self.flip()
        r = self.commit("promote", env={**self.env, "GATE_OK": "1"})
        self.assertEqual(r.returncode, 0, r.stderr)
        rows = [json.loads(x) for x in
                (self.root / "logs" / "feedback.jsonl").read_text().splitlines()]
        self.assertEqual(rows[-1]["kind"], "bypass")
        self.config("once")
        self.note.write_text(NOTE.replace("contributes 2", "adds 2"))
        self.git("add", "-A")
        self.assertNotEqual(self.commit("proof").returncode, 0)
        self.assertEqual(self.commit("proof").returncode, 0)

    # 3b. a failing bin/question-check refuses the commit
    def test_question_check(self):
        qc = self.root / "bin" / "question-check"
        qc.write_text("#!/bin/sh\necho 'FAIL Q001 active with empty activated-by'\nexit 1\n")
        qc.chmod(0o755)
        (self.root / "README.md").write_text("hello\n")
        self.git("add", "README.md")
        r = self.commit("readme")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("activated-by", r.stderr)

    # 4. failure: a broken config fails open, loudly
    def test_failure(self):
        (self.root / "project.toml").write_text("[gates\nbroken")
        self.flip()
        r = self.commit("promote")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("WARNING", r.stderr)
        self.assertTrue((self.root / "logs" / "state" / "hook-errors.log").exists())


if __name__ == "__main__":
    unittest.main()
