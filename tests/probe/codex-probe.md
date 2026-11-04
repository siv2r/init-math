# Harness probe: confirm what each harness actually does

The Codex adapter's capability table (`renderer/adapters/codex.py`, `CAPS`/`VERIFIED`)
comes from documentation, not observation. This procedure replaces every guess with a
recorded observation. It needs Codex CLI installed.

## Setup (once)

```bash
npm i -g @openai/codex        # or: brew install codex
codex login
cd <your init-math clone>
python3 tests/probe/make-probe-project.py codex  /tmp/probe-codex     # renders fixture 2 + probe module
python3 tests/probe/make-probe-project.py claude /tmp/probe-claude    # renders fixture 1 + probe module
```

The probe module registers `hooks/probe.py` on PreToolUse (shell, edit, spawn, ask,
wakeup), PostToolUse (shell, edit) and Stop. It appends every raw payload to
`logs/probe-payloads.jsonl`.

## Steps (Codex; repeat the relevant ones for Claude)

In `/tmp/probe-codex`, start `codex`, run `/hooks` and trust the project hooks, then ask:

| # | Prompt to the agent | Records | Capability row |
|---|---|---|---|
| 1 | "Run `ls` in the shell." | shell payload (Pre + Post) | hook events |
| 2 | "Create notes/x.md containing hello." | apply_patch payload; are paths in `tool_input`? | hook events |
| 3 | "Use the probe-reviewer agent on AGENTS.md." | spawn payload: tool_name, agent field names; does the agent load from `.codex/agents/`? does `model` apply? | `hook_spawn`, `subagents` |
| 4 | "Load the probe skill." | skill found in `.agents/skills/` | — |
| 5 | (end the turn) | Stop payload; does printing `{"decision":"block"}` continue the turn? | Stop semantics |
| 6 | "Run `sleep 30; echo done` in the background and tell me when it finishes." | is there a completion notification? | `background_callback` |
| 7 | "Ask the probe-reviewer a question, then send it a follow-up." | can a finished subagent be resumed? | `resume_subagent` |
| 8 | `codex exec "run ls"` in the same dir | do trusted hooks fire in exec mode? | exec |

## Recording

1. Copy each distinct payload from `logs/probe-payloads.jsonl` (the `raw` field) into
   `tests/payloads/codex/<event>-<action>.json`, anonymizing paths to `/tmp/proj`.
2. Set the matching `VERIFIED[...] = True` (and fix `CAPS[...]`/`MATCHERS[...]` if the
   observation disagrees) in `codex.py`, with a comment citing this probe and the date.
3. Run `python3 -m unittest discover -s tests`: `NormalizeCodex.test_captured` now runs.
