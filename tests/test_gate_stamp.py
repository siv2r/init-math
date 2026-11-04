"""bin/gate-stamp's caveat check against real reviewer replies.

tests/fixtures/saved-stamps.jsonl holds the 42 passing stamps (gate, verdict, excerpt) of an
earlier set of behavior runs. None of them passes over a caveat of its own, so the default caveat
list must match none of them; a list with "gap" or "conditional on" matched 14.
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "skills/init-math/scripts/templates/modules/08-commit_gate/files/bin/gate-stamp"
SAVED = REPO / "tests/fixtures/saved-stamps.jsonl"


def _load():
    loader = importlib.machinery.SourceFileLoader("gate_stamp", str(SCRIPT))
    spec = importlib.util.spec_from_loader("gate_stamp", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class CaveatList(unittest.TestCase):
    def setUp(self):
        self.gs = _load()
        self.root = Path(tempfile.mkdtemp())  # no project.toml: the script's defaults
        self.rows = [json.loads(l) for l in SAVED.read_text(encoding="utf-8").splitlines() if l]

    def test_saved_passing_stamps_not_refused(self):
        self.assertEqual(len(self.rows), 42)
        hits = [(r["gate"], self.gs.caveat_lines(self.root, r["excerpt"])) for r in self.rows]
        self.assertEqual([h for h in hits if h[1]], [])

    def test_broad_list_would_refuse_many(self):
        (self.root / "project.toml").write_text(
            "[gates]\ncaveat_phrases = ['gap', 'conditional on']\n")
        n = sum(1 for r in self.rows if self.gs.caveat_lines(self.root, r["excerpt"]))
        self.assertGreater(n, 5)

    def test_planted_caveat_found(self):
        self.assertTrue(self.gs.caveat_lines(
            self.root, "Verdict: CLEAN\nLemma 2 is quoted from memory."))
        self.assertFalse(self.gs.caveat_lines(
            self.root, "Verdict: SURVIVED\n- **Attack surface**: degree 9 not verified."))
        self.assertFalse(self.gs.caveat_lines(
            self.root, "Verdict: CLEAN\n- [8] p.md:15 — Chebyshev's hypothesis is not checked — note it — minor"))


if __name__ == "__main__":
    unittest.main()
