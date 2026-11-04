from .base import Adapter, Agent, HookReg, parse_frontmatter
from .claude import ClaudeAdapter
from .codex import CodexAdapter

ADAPTERS = {"claude": ClaudeAdapter, "codex": CodexAdapter}

__all__ = ["ADAPTERS", "Adapter", "Agent", "HookReg", "parse_frontmatter"]
