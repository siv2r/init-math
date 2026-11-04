"""Probe hook: append the raw payload + normalized event to logs/probe-payloads.jsonl."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _payload  # noqa: E402


def main(ev):
    _payload.log(ev.root, "probe-payloads", {
        "harness": ev.harness, "event": ev.event, "action": ev.action,
        "tool_name": ev.tool_name, "paths": ev.paths, "agent_type": ev.agent_type,
        "has_transcript": bool(ev.transcript_path), "raw": ev.raw,
    })


if __name__ == "__main__":
    _payload.run(main, "probe")
