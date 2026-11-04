"""lean-build-nudge: nudge a bare `lake build` toward bin/lean-build.

Event: PreToolUse, action `shell`.

A bare `lake build` skips four checks that `bin/lean-build` makes: it does not compare the
Lean version in use with the project's `lean-toolchain` pin (a mismatch recompiles the whole
library or fails confusingly), a pipe such as `lake build | tail` hides lake's exit code,
nothing warns when the library itself is being compiled from source (hours; the fix is
`lake exe cache get`), and a bare `lake build` run from the wrong directory fails with
"no configuration file" (the wrapper finds the project itself). Fires on a `lake ... build` command outside quotes and heredocs.
`lake env`, `lake exe cache get` and `bin/lean-build` itself do not fire.
See docs/discipline/lean.md.

Nudge, not a ban: once per identical command. Bypass: LEAN_BUILD_OK=1 in the environment
or as an inline prefix.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _payload  # noqa: E402

HOOK = "lean-build-nudge"
HEREDOC = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?.*?\n.*?^\s*\1\s*$", re.S | re.M)
QUOTED = re.compile(r"'[^']*'|\"(?:[^\"\\]|\\.)*\"")
LAKE_BUILD = re.compile(r"(?<![./\w-])lake\s+(?:[^&|;\n]*\s)?build\b")

MESSAGE = (
    "Use bin/lean-build instead of a bare `lake build`. It checks the toolchain pin first, "
    "keeps lake's real exit code (a pipe hides it), summarizes errors and `sorry` warnings, "
    "and warns when the library itself is being recompiled (run `lake exe cache get`). "
    "Long builds belong to the coordinator, not a worker. See docs/discipline/lean.md. "
    "Bypass: LEAN_BUILD_OK=1."
)


def strip(cmd: str) -> str:
    return QUOTED.sub("''", HEREDOC.sub("", cmd))


def main(ev: _payload.Event) -> None:
    if ev.action != "shell" or not ev.command:
        return
    if os.environ.get("LEAN_BUILD_OK") == "1" or re.search(r"(^|[\s;&|])LEAN_BUILD_OK=1\b", ev.command):
        return
    if not LAKE_BUILD.search(strip(ev.command)):
        return
    key = " ".join(ev.command.split())
    _payload.nudge_once(ev, HOOK, key, MESSAGE)


if __name__ == "__main__":
    _payload.run(main, HOOK)
