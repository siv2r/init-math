"""Selftest for hooks/usage-log.py through its real entry point (JSON on stdin).

Four branches (docs/discipline/hook-authoring.md): allow, trigger, bypass, failure.
"Allow" here is the normal path: counts are copied, each response once, incrementally.
The transcripts are synthetic, in the shapes the two harnesses write.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "usage-log.py"


def claude_line(mid, model, inp, out, cr=0, cw=0, side=False, ts="2026-10-08T10:00:00.000Z"):
    return json.dumps({"type": "assistant", "sessionId": "sess1", "isSidechain": side,
                       "timestamp": ts, "uuid": os.urandom(4).hex(),
                       "message": {"id": mid, "model": model, "role": "assistant",
                                   "content": [{"type": "text", "text": "SECRET TEXT"}],
                                   "usage": {"input_tokens": inp, "output_tokens": out,
                                             "cache_read_input_tokens": cr,
                                             "cache_creation_input_tokens": cw}}}) + "\n"


def codex_meta(tid, session, sub=False):
    p = {"id": tid, "session_id": session, "cwd": "/w", "cli_version": "0.0.1",
         "thread_source": "subagent" if sub else "user"}
    if sub:
        p.update(parent_thread_id=session, agent_role="reviewer")
    return json.dumps({"timestamp": "2026-10-08T11:00:00Z", "type": "session_meta", "payload": p}) + "\n"


def codex_record(tid, rid, inp, cached, out, reasoning):
    return json.dumps({"timestamp": "2026-10-08T11:00:05Z", "type": "token_usage_record",
                       "payload": {"thread_id": tid, "turn_id": "t", "response_id": rid,
                                   "usage": {"input_tokens": inp, "cached_input_tokens": cached,
                                             "output_tokens": out,
                                             "reasoning_output_tokens": reasoning}}}) + "\n"


def codex_count(total_in, total_out, used=12.5):
    return json.dumps({"timestamp": "2026-10-08T11:00:06Z", "type": "event_msg", "payload": {
        "type": "token_count",
        "info": {"total_token_usage": {"input_tokens": total_in, "cached_input_tokens": 0,
                                       "output_tokens": total_out}},
        "rate_limits": {"plan_type": "plus",
                        "primary": {"used_percent": used, "window_minutes": 300, "resets_at": 1},
                        "secondary": {"used_percent": 3.0, "window_minutes": 10080,
                                      "resets_at": 2}}}}) + "\n"


TURN = json.dumps({"timestamp": "2026-10-08T11:00:01Z", "type": "turn_context",
                   "payload": {"model": "gpt-test"}}) + "\n"


class UsageLog(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "proj"
        self.root.mkdir()
        self.store = Path(self.tmp.name) / "store"
        self.store.mkdir()
        self.env = {**os.environ, "CLAUDE_PROJECT_DIR": str(self.root)}
        for k in ("USAGE_LOG_OFF", "HOOKS_QUIET"):
            self.env.pop(k, None)

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, payload, harness="claude", env=None):
        data = payload if isinstance(payload, str) else json.dumps(payload)
        return subprocess.run([sys.executable, str(HOOK), "--harness", harness], input=data,
                              capture_output=True, text=True, env=env or self.env, timeout=30)

    def rows(self, kind="usage"):
        p = self.root / "logs" / "usage.jsonl"
        if not p.exists():
            return []
        return [r for r in map(json.loads, p.read_text().splitlines()) if r["kind"] == kind]

    def total(self, field, **match):
        return sum(r[field] for r in self.rows() if all(r.get(k) == v for k, v in match.items()))

    # 1. allow: Claude main + subagent files, split ids, incremental reads, lost state
    def test_allow_claude(self):
        main = self.store / "sess1.jsonl"
        sub = self.store / "sess1" / "subagents"
        sub.mkdir(parents=True)
        main.write_text(json.dumps({"type": "user", "message": {"content": "hi"}}) + "\n"
                        + claude_line("m1", "model-a", 10, 5, 100, 20)
                        + claude_line("m1", "model-a", 10, 5, 100, 20)  # same response, 2nd block
                        + claude_line("s1", "<synthetic>", 0, 0))
        (sub / "agent-x1.jsonl").write_text(claude_line("m2", "model-b", 3, 4, side=True))
        (sub / "agent-x1.meta.json").write_text(json.dumps({"agentType": "lit-search",
                                                            "description": "never read"}))
        stop = {"hook_event_name": "Stop", "session_id": "sess1", "cwd": str(self.root),
                "transcript_path": str(main)}
        r = self.run_hook(stop)
        self.assertEqual((r.returncode, r.stderr, r.stdout), (0, "", ""))
        self.assertEqual(self.total("calls", role="main"), 1)
        self.assertEqual([self.total(f, role="main") for f in ("input", "output", "cache_read", "cache_write")],
                         [10, 5, 100, 20])
        self.assertEqual(self.total("output", role="subagent", agent_type="lit-search", model="model-b"), 4)
        self.assertNotIn("SECRET", (self.root / "logs" / "usage.jsonl").read_text())
        self.assertNotIn("never read", (self.root / "logs" / "usage.jsonl").read_text())
        n = len(self.rows())
        self.assertEqual(self.run_hook(stop).returncode, 0)
        self.assertEqual(len(self.rows()), n)  # nothing new: nothing written
        with open(main, "a") as f:  # m1 continues across the read boundary; m3 is new;
            f.write(claude_line("m1", "model-a", 10, 5, 100, 20) + claude_line("m3", "model-a", 1, 1))
            f.write(claude_line("m4", "model-a", 7, 7)[:-30])  # m4 is still being written
        self.run_hook(stop)
        self.assertEqual(self.total("calls", role="main"), 2)
        self.assertEqual(self.total("output", role="main"), 6)
        (self.root / "logs" / "state" / "usage-offsets.json").unlink()  # lost state
        self.run_hook(stop)
        self.assertEqual(self.total("calls", role="main"), 2)  # recovered from the log
        with open(main, "a") as f:
            f.write(claude_line("m4", "model-a", 7, 7)[-30:])
        self.run_hook({**stop, "hook_event_name": "SessionEnd"})
        self.assertEqual(self.total("output", role="main"), 13)

    # 1b. allow: Codex main + subagent rollout, per-response records, plan limits
    def test_allow_codex(self):
        main = self.store / "rollout-main.jsonl"
        sub = self.store / "rollout-sub.jsonl"
        main.write_text(codex_meta("T1", "T1") + TURN + codex_record("T1", "r1", 1000, 800, 50, 20)
                        + codex_count(1000, 50))
        sub.write_text(codex_meta("T2", "T1", sub=True) + codex_meta("T1", "T1") + TURN
                       + codex_record("T1", "r1", 1000, 800, 50, 20)  # the parent's, copied in
                       + codex_record("T2", "r2", 300, 100, 30, 0))
        r = self.run_hook({"hook_event_name": "Stop", "session_id": "T1", "cwd": str(self.root),
                           "transcript_path": str(main), "model": "gpt-test"}, harness="codex")
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.assertEqual([self.total(f, role="main", model="gpt-test") for f in
                          ("input", "cache_read", "output", "reasoning")], [200, 800, 50, 20])
        lim = self.rows("limits")
        self.assertEqual((len(lim), lim[0]["primary_used_pct"], lim[0]["plan"]), (1, 12.5, "plus"))
        r = self.run_hook({"hook_event_name": "SubagentStop", "session_id": "T1",
                           "cwd": str(self.root), "transcript_path": str(main),
                           "agent_transcript_path": str(sub), "agent_type": "reviewer"},
                          harness="codex")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.total("input", role="subagent", agent_type="reviewer", session="T1"), 200)
        self.assertEqual(self.total("calls"), 2)  # the copied parent record is not counted twice
        with open(main, "a") as f:
            f.write(codex_count(1000, 50))  # same limits again: no new limits row
        self.run_hook({"hook_event_name": "Stop", "transcript_path": str(main)}, harness="codex")
        self.assertEqual(len(self.rows("limits")), 1)

    # 1c. allow: a Codex without per-response records falls back to deltas of the totals
    def test_allow_codex_totals_only(self):
        main = self.store / "rollout-old.jsonl"
        main.write_text(codex_meta("T3", "T3") + TURN + codex_count(100, 10))
        stop = {"hook_event_name": "Stop", "transcript_path": str(main)}
        self.run_hook(stop, harness="codex")
        with open(main, "a") as f:
            f.write(codex_count(250, 30))
        self.run_hook(stop, harness="codex")
        self.assertEqual((self.total("input"), self.total("output")), (250, 30))

    # 2. trigger: an unreadable format warns once and logs one failures row
    def test_trigger_format_unknown(self):
        main = self.store / "sess2.jsonl"
        main.write_text(json.dumps({"type": "assistant", "message": {"id": "m", "content": []}}) + "\n")
        stop = {"hook_event_name": "Stop", "transcript_path": str(main)}
        r = self.run_hook(stop)
        self.assertEqual(r.returncode, 0)
        self.assertIn("WARNING", r.stderr)
        fails = (self.root / "logs" / "failures.jsonl").read_text().splitlines()
        self.assertEqual(json.loads(fails[0])["signature"], "usage-format-unknown")
        with open(main, "a") as f:
            f.write(json.dumps({"type": "assistant", "message": {"id": "n"}}) + "\n")
        r = self.run_hook(stop)
        self.assertEqual((r.returncode, r.stderr), (0, ""))  # once per transcript
        rollout = self.store / "rollout-new.jsonl"
        rollout.write_text(codex_meta("T4", "T4") + TURN + json.dumps(
            {"type": "response_item", "payload": {"type": "message"}}) + "\n")
        r = self.run_hook({"hook_event_name": "Stop", "transcript_path": str(rollout)}, harness="codex")
        self.assertIn("usage-format-unknown", (self.root / "logs" / "failures.jsonl").read_text())
        self.assertIn("WARNING", r.stderr)

    # 3. bypass: USAGE_LOG_OFF=1 records nothing
    def test_bypass(self):
        main = self.store / "sess3.jsonl"
        main.write_text(claude_line("m1", "model-a", 1, 1))
        r = self.run_hook({"hook_event_name": "Stop", "transcript_path": str(main)},
                          env={**self.env, "USAGE_LOG_OFF": "1"})
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        self.assertFalse((self.root / "logs" / "usage.jsonl").exists())
        r = self.run_hook({"hook_event_name": "Stop"})  # no transcript: nothing to do
        self.assertEqual((r.returncode, r.stderr), (0, ""))

    # 4. failure: malformed input fails open, loudly
    def test_failure(self):
        r = self.run_hook("{not json")
        self.assertEqual(r.returncode, 0)
        self.assertIn("WARNING", r.stderr)
        self.assertTrue((self.root / "logs" / "state" / "hook-errors.log").exists())
        state = self.root / "logs" / "state"
        (state / "usage-offsets.json").write_text("{corrupt")  # a corrupt cache is not fatal
        main = self.store / "sess4.jsonl"
        main.write_text(claude_line("m1", "model-a", 1, 2))
        r = self.run_hook({"hook_event_name": "Stop", "transcript_path": str(main)})
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.total("output"), 2)


if __name__ == "__main__":
    unittest.main()
