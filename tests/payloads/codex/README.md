# Codex payload fixtures

Captured from real Codex CLI 0.161.0 sessions on 2026-10-08 (the harness probe,
../../probe/codex-probe.md), model gpt-6-luna, `codex exec --dangerously-bypass-hook-trust`.
Paths are anonymized: the project dir is `/tmp/proj`, the Codex home `/home/user/.codex`.
Nothing else was edited.

| File | Run | What it shows |
|---|---|---|
| pre-apply-patch.json, post-apply-patch.json | 2 | apply_patch: patch text in `tool_input.command`; PostToolUse adds `tool_response` (a string) |
| pre-bash-in-subagent.json, post-bash-in-subagent.json | 2 | a subagent's own shell call: same shape plus `agent_id`, `agent_type` |
| pre-spawn.json | 3 | spawn: tool_name `collaborationspawn_agent`; `message` (the brief) is encrypted |
| pre-wait-agent.json | 3 | another multi-agent tool, same `collaboration` prefix |
| subagent-start.json, subagent-stop.json | 3 | SubagentStop carries the subagent's final reply in clear |
| stop.json | 3 | Stop: `last_assistant_message`, `stop_hook_active` |

The run-2 files were copied from the probe log as printed during the session (the log file
itself was reset before run 3); the run-3 files were copied from the log file directly.

`apply-patch-synthetic.json` is the one invented payload, and it is named as such: it
only tests the patch-path parser against the documented `*** Update File:` and
`*** Move to:` forms, which the probe did not exercise.
