"""OpenAI Codex CLI adapter.

Sources: Codex docs (hooks, subagents, skills, AGENTS.md), read 2026-10-08, and the harness
probe (tests/probe/codex-probe.md) run on Codex CLI 0.161.0 on 2026-10-08 with three short
`codex exec` sessions; captured payloads are in tests/payloads/codex/. VERIFIED marks what
the probe observed directly; everything else is still the docs' word.

Probe facts the rest of this file relies on:
  * Hooks fire under `codex exec` (with --dangerously-bypass-hook-trust; an interactive
    session trusts them via /hooks), for the main agent AND inside subagents, whose
    payloads add `agent_id` and `agent_type`.
  * apply_patch fires PreToolUse/PostToolUse with tool_name "apply_patch" and the patch
    text in tool_input.command.
  * spawn_agent fires PreToolUse with tool_name "collaborationspawn_agent" — the docs'
    "matches Agent" alias did NOT match in 0.161, so the matcher names all three. Its
    tool_input has agent_type and task_name in clear, but the brief (`message`) is
    encrypted, also in the subagent's own rollout: no hook can read a brief on Codex.
  * SubagentStart / SubagentStop fire, matcher on agent_type; SubagentStop carries the
    subagent's final reply (last_assistant_message) in clear.
  * followup_task gives a finished subagent a new task and it keeps its context, so
    resuming a worker by message works.
  * Custom agents in .codex/agents/*.toml load: the spawned agent ran as its own type on
    the model its file names.
"""
from __future__ import annotations

from .base import Adapter, Agent


class CodexAdapter(Adapter):
    name = "codex"
    CAPS = {
        "background_callback": False,  # no documented completion-notification for bg shells
        "resume_subagent": True,       # followup_task (probe 2026-10-08)
        "schedule_wakeup": False,
        "ask_tool": False,
        "transcripts": True,           # hook payloads carry transcript_path (probe)
        "hook_spawn": True,            # fires, as collaborationspawn_agent (probe)
        "spawn_brief_visible": False,  # the brief reaches hooks encrypted (probe)
        "tool_allowlist": False,       # only per-agent sandbox_mode
        "subagents": True,             # .codex/agents/*.toml load (probe)
    }
    VERIFIED = {k: False for k in CAPS} | {
        k: True for k in ("resume_subagent", "transcripts", "hook_spawn",
                          "spawn_brief_visible", "subagents")}
    MATCHERS = {
        "shell": "Bash",
        "edit": "apply_patch|Edit|Write",
        "spawn": "collaborationspawn_agent|spawn_agent|Agent",
        "ask": None,
        "wakeup": None,
    }
    SUPPORTED_EVENTS = ("PreToolUse", "PostToolUse", "Stop", "SessionStart",
                        "SubagentStart", "SubagentStop")
    skills_dir = ".agents/skills"
    context_files = ("AGENTS.md",)
    # Not split: whether a Codex subagent reads AGENTS.md, and whether SessionStart can add
    # context only to the main session, are unchecked, so AGENTS.md keeps
    # the coordinator's rules.
    coordinator_file = ""

    def agent_path(self, agent: Agent) -> str:
        return f".codex/agents/{agent.name}.toml"

    def render_agent(self, agent: Agent) -> str:
        body = agent.body.lstrip("\n")
        if agent.sandbox == "read-only" and agent.tools:
            body = (
                "You are READ-ONLY: do not create, edit or delete files and do not run "
                "commands that change state. Codex enforces this with sandbox_mode; this "
                "line restates it because Codex has no per-agent tool list.\n\n" + body
            )
        out = [
            f"name = {_toml_str(agent.name)}",
            f"description = {_toml_str(' '.join(agent.description.split()))}",
            f"model = {_toml_str(self.model_for(agent.tier))}",
            f"sandbox_mode = {_toml_str(agent.sandbox)}",
            f"developer_instructions = {_toml_multiline(body)}",
        ]
        return "\n".join(out) + "\n"

    def hook_command(self, script: str) -> str:
        return f'python3 "$(git rev-parse --show-toplevel)/{script}" --harness codex'

    def hook_config_path(self) -> str:
        return ".codex/hooks.json"


def _toml_str(s: str) -> str:
    esc = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{esc}"'


def _toml_multiline(s: str) -> str:
    if "'''" not in s:
        return "'''\n" + s + "'''"
    esc = s.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
    return '"""\n' + esc + '"""'
