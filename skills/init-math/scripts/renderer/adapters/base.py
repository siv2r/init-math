"""Harness adapter interface.

An adapter turns the harness-neutral pieces of a module (canonical agent files, skills,
hook registrations) into the files one harness reads. Hook scripts themselves are
harness-neutral (hooks/_payload.py normalizes payloads), so only their REGISTRATION
differs per harness.

Capabilities (CAPS) drive `{{#if harness.cap.<name>}}` in templates, so prose that relies
on a harness mechanism is only emitted where that mechanism exists. VERIFIED records
which entries were confirmed by a real probe (see tests/probe/) versus taken from docs.
"""
from __future__ import annotations

import json
import shlex
import re
from dataclasses import dataclass, field

# Semantic hook actions used in module.toml -> per-harness tool matchers.
ACTIONS = ("shell", "edit", "spawn", "ask", "wakeup", "skill")
EVENTS = ("PreToolUse", "PostToolUse", "PostToolUseFailure", "Stop", "SessionStart",
          "SubagentStart", "SubagentStop", "SessionEnd")


@dataclass
class Agent:
    name: str
    description: str
    tier: str  # strong | worker
    body: str
    tools: list[str] = field(default_factory=list)  # Claude tool names; [] = all
    sandbox: str = "read-only"  # read-only | workspace-write


@dataclass
class HookReg:
    script: str  # project-relative path, e.g. hooks/guard.py
    event: str
    actions: list[str]  # empty for Stop/SessionStart
    module: str
    args: list[str] = field(default_factory=list)  # appended to the command, shell-quoted


# Compact the main thread's context once it reaches this many tokens, whatever the model's
# window: a long session past this point costs more per turn and steers worse, and durable
# state lives on disk anyway. A starting value, not a tuned one; the reflection loop puts
# tightening it to the owner (colleague trial on Codex, 2026-10-22: one session reached
# 605k input tokens after its window was raised).
AUTO_COMPACT_TOKENS = 300_000


class Adapter:
    name = "base"
    CAPS: dict[str, bool] = {}
    VERIFIED: dict[str, bool] = {}
    MATCHERS: dict[str, str | None] = {}
    SUPPORTED_EVENTS: tuple[str, ...] = ()
    # Semantic tool name (module.toml `allow_tools`) -> this harness's name for the tool, for
    # tools a module needs approved in advance. A name missing here is left to the harness default.
    TOOL_NAMES: dict[str, str] = {}
    # Permission rule pre-approving one of the project's own scripts (module.toml
    # `allow_commands`), formatted with the script path; None keeps the harness default.
    COMMAND_RULES: tuple[str, ...] = ()
    # True: the hook config file also sets the main thread's model (the strong tier). A harness
    # whose main-thread model lives elsewhere sets it in a template (Codex: .codex/config.toml).
    SETTINGS_MODEL = False
    # Key in the hook config file that sets the auto-compaction point (AUTO_COMPACT_TOKENS),
    # or None when the harness sets it elsewhere (Codex: .codex/config.toml).
    SETTINGS_AUTO_COMPACT: str | None = None
    skills_dir = ""
    context_files: tuple[str, ...] = ()
    # The coordinator's own rules file, given to the main session only (render.py), or "" when
    # the harness cannot do that and AGENTS.md carries the coordinator's rules itself.
    coordinator_file = ""

    def __init__(self, tiers: dict[str, str]):
        self.tiers = tiers

    # -- agents ---------------------------------------------------------
    def agent_path(self, agent: Agent) -> str:
        raise NotImplementedError

    def render_agent(self, agent: Agent) -> str:
        raise NotImplementedError

    # -- hooks ----------------------------------------------------------
    def hook_command(self, script: str) -> str:
        raise NotImplementedError

    def hook_config_path(self) -> str:
        raise NotImplementedError

    def matcher_for(self, actions: list[str]) -> str | None:
        """Return the tool matcher for `actions`, or None if none are supported."""
        parts: list[str] = []
        for a in actions:
            m = self.MATCHERS.get(a)
            if m:
                for p in m.split("|"):
                    if p not in parts:
                        parts.append(p)
        return "|".join(parts) if parts else None

    def hook_config(self, regs: list[HookReg], allow: list[str] = (),
                    commands: list[str] = ()) -> tuple[str, list[str]]:
        """Return (config file text, list of skipped-registration notes).

        `allow` are semantic tool names from module.toml `allow_tools` (e.g. web_search);
        an adapter with a TOOL_NAMES entry for one pre-approves it in the config.
        `commands` are the project's own scripts from module.toml `allow_commands`
        (e.g. bin/question-check), pre-approved through COMMAND_RULES.
        """
        hooks: dict[str, list] = {}
        skipped: list[str] = []
        for r in regs:
            if r.event not in self.SUPPORTED_EVENTS:
                skipped.append(f"{r.script}: event {r.event} unsupported on {self.name}")
                continue
            entry = {"type": "command",
                     "command": " ".join([self.hook_command(r.script), *map(shlex.quote, r.args)])}
            if r.actions:
                matcher = self.matcher_for(r.actions)
                if matcher is None:
                    skipped.append(f"{r.script}: actions {r.actions} unsupported on {self.name}")
                    continue
                group = {"matcher": matcher, "hooks": [entry]}
            else:
                group = {"hooks": [entry]}
            hooks.setdefault(r.event, []).append(group)
        tools = [self.TOOL_NAMES[t] for t in allow if t in self.TOOL_NAMES]
        tools += [rule.format(c) for c in commands for rule in self.COMMAND_RULES]
        return self.wrap_hook_config(hooks, list(dict.fromkeys(tools))), skipped

    def wrap_hook_config(self, hooks: dict, allow: list[str] = ()) -> str:
        cfg: dict = {"model": self.model_for("strong")} if self.SETTINGS_MODEL else {}
        if self.SETTINGS_AUTO_COMPACT:
            cfg[self.SETTINGS_AUTO_COMPACT] = AUTO_COMPACT_TOKENS
        if allow:
            cfg["permissions"] = {"allow": list(allow)}
        cfg["hooks"] = hooks
        return json.dumps(cfg, indent=2) + "\n"

    # -- misc -----------------------------------------------------------
    def model_for(self, tier: str) -> str:
        return self.tiers.get(tier, self.tiers["strong"])


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse a tiny YAML subset: `key: value` lines and `[a, b]` lists, between --- lines."""
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ValueError("unterminated frontmatter")
    meta: dict = {}
    for line in text[4:end].splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, sep, val = line.partition(":")
        if not sep:
            raise ValueError(f"bad frontmatter line: {line!r}")
        val = val.strip()
        if val.startswith("[") and val.endswith("]"):
            meta[key.strip()] = [v.strip().strip("'\"") for v in val[1:-1].split(",") if v.strip()]
        else:
            meta[key.strip()] = val.strip("'\"") if re.match(r"^(['\"]).*\1$", val) else val
    return meta, text[end + 5:]
