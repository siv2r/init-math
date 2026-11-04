"""Claude Code adapter."""
from __future__ import annotations

from .base import Adapter, Agent


class ClaudeAdapter(Adapter):
    name = "claude"
    CAPS = {
        "background_callback": True,  # run_in_background + completion notification
        "resume_subagent": True,      # SendMessage to a finished agent
        "schedule_wakeup": True,      # ScheduleWakeup / loops
        "ask_tool": True,             # AskUserQuestion
        "transcripts": True,          # session JSONL under ~/.claude/projects
        "hook_spawn": True,           # PreToolUse on Agent|Task
        "spawn_brief_visible": True,  # tool_input.prompt is plain text
        "tool_allowlist": True,       # agent frontmatter `tools` is enforced
        "subagents": True,
    }
    VERIFIED = {k: True for k in CAPS}  # Claude Code is the harness the templates were developed and observed on
    MATCHERS = {
        "shell": "Bash",
        "edit": "Write|Edit|MultiEdit|NotebookEdit",
        "spawn": "Agent|Task",
        "ask": "AskUserQuestion",
        "wakeup": "ScheduleWakeup",
        "skill": "Skill",
    }
    # SubagentStop and SessionEnd are documented Claude Code hook events; no payload of either
    # is captured in tests/payloads/claude yet, so hooks on them read only the common fields.
    SUPPORTED_EVENTS = ("PreToolUse", "PostToolUse", "PostToolUseFailure", "Stop", "SessionStart",
                        "SubagentStop", "SessionEnd")
    # A background subagent cannot show a permission prompt, so a tool it needs must be allowed
    # here or its calls are refused (seen in the 2026-10-09 end-to-end run: lit-search lost the web).
    TOOL_NAMES = {"web_search": "WebSearch", "web_fetch": "WebFetch"}
    # The project's own check-and-record scripts, so the owner is not asked to judge a command
    # line they cannot read (onboarding review 2026-10-10). `:*` matches with or without arguments.
    COMMAND_RULES = ("Bash({}:*)", "Bash(./{}:*)")
    # Without it the main thread runs on whatever model the person last picked, which may be
    # weaker than the reviewers' (the 2026-10-09 Codex run had its main thread on the worker tier).
    SETTINGS_MODEL = True
    # Token count, 100k-1M, allowed in project settings (code.claude.com settings reference,
    # read 2026-10-22).
    SETTINGS_AUTO_COMPACT = "autoCompactWindow"
    skills_dir = ".claude/skills"
    context_files = ("AGENTS.md", "CLAUDE.md")
    # A subagent gets CLAUDE.md (and so AGENTS.md) but not a SessionStart hook's added context
    # (probe 2026-10-31: a custom subagent saw AGENTS.md and its SubagentStart text, not the
    # SessionStart text). So the coordinator's rules reach only the main session, by the core
    # hook hooks/coordinator-context.py.
    coordinator_file = "COORDINATOR.md"

    def agent_path(self, agent: Agent) -> str:
        return f".claude/agents/{agent.name}.md"

    def render_agent(self, agent: Agent) -> str:
        lines = ["---", f"name: {agent.name}", f"description: {_one_line(agent.description)}"]
        if agent.tools:
            lines.append(f"tools: {', '.join(agent.tools)}")
        lines.append(f"model: {self.model_for(agent.tier)}")
        lines.append("---")
        return "\n".join(lines) + "\n" + agent.body.lstrip("\n")

    def hook_command(self, script: str) -> str:
        return f'python3 "$CLAUDE_PROJECT_DIR/{script}" --harness claude'

    def hook_config_path(self) -> str:
        return ".claude/settings.json"


def _one_line(s: str) -> str:
    return " ".join(s.split())
