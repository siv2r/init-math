# Authoring a module

This is the contract for every module under `skills/init-math/scripts/templates/`. It is
written for whoever distills a module from its source practice (human or agent). Read it
whole before writing a file.

## What a module is

A module is one mechanism from the plan's catalog (e.g. "conjecture ledger", "reflection
loop"), packaged so the renderer can switch it on or off and render it for one harness.
Its id must be a key of `CATALOG` in `renderer/render.py`.

```
templates/modules/NN-<id>/
  module.toml                 # metadata (required)
  AGENTS.fragment.md.tmpl     # its section of the generated AGENTS.md (optional, short)
  glossary.fragment.md.tmpl   # its GLOSSARY entries (optional)
  project.fragment.toml.tmpl  # its tables in project.toml, e.g. [gates] (optional)
  gitignore.fragment.tmpl     # lines for .gitignore (optional)
  files/                      # copied into the project root (paths preserved)
    @claude/ @codex/          # top-level dirs emitted only for that harness, prefix stripped
  skills/<skill-name>/SKILL.md(.tmpl)   # emitted into the harness's skills dir
  agents/<name>.md(.tmpl)     # canonical agent; the adapter renders it per harness
  <item>.md.tmpl              # per-item templates (see [[per_item]])
```

Only `files/`, `skills/`, `agents/`, the fragments and per-item templates are emitted.
Fragments are spliced into files core owns (AGENTS.md, GLOSSARY.md, project.toml,
.gitignore), in module order; a module never writes those files directly.
Anything else in the module directory (notes, say) is for authors and is never emitted.

Files ending `.tmpl` are rendered and lose the suffix; every other file is copied byte for
byte, keeping its mode (make scripts executable in the template tree). Two modules may not
emit the same path: the render fails.

### module.toml

```toml
id = "conjectures"            # a CATALOG key
number = 2                    # catalog number
title = "Conjecture ledger"
group = "A"                   # A direction, B verification, C discipline/experiments, D organization, E learning
status = "included"           # included (on by default) | opt-in | deferred
order = 20                    # position of its AGENTS.md section (number * 10 by default)
summary = "One line, shown by --list-modules."
depends = ["questions"]       # module ids that must also be on
off_in_presets = ["theory-only"]   # presets that switch it off (optional)
requires = { proof_assistant = "lean" }   # optional
allow_tools = ["web_search"]  # optional: tools pre-approved in the harness config (a background
                              # subagent cannot ask); names map via the adapter's TOOL_NAMES,
                              # and a harness without a mapping keeps its default. This widens
                              # what agents do without asking: owner decision only.
allow_commands = ["bin/foo"]  # optional: this module's own scripts that only check or record,
                              # pre-approved so the owner is not asked about them (Claude Code:
                              # `Bash(bin/foo:*)`). Never a script that runs arbitrary code
                              # (exp-run, guard-run, bg-run, lean-build).

[[hooks]]                     # one entry per registration
script = "hooks/foo.py"       # must be emitted by this module (or core)
event = "PreToolUse"          # PreToolUse | PostToolUse | PostToolUseFailure | Stop | SessionStart
                              # | SubagentStart | SubagentStop | SessionEnd
actions = ["spawn"]           # shell | edit | spawn | ask | wakeup | skill  (omit for Stop/SessionStart)
harnesses = ["claude"]        # optional: register only on these; omitted elsewhere, not "skipped"
args = ["--part", "1"]        # optional: appended to the command, shell-quoted

[[per_item]]                  # render one file per seed
template = "question.md.tmpl"
over = "seeds.questions"      # dotted path into the render context
path = "wiki/questions/{id}-{slug}.md"   # str.format over the item's fields
```

`PostToolUseFailure` and `SessionEnd` exist only on Claude, `SubagentStart` only on Codex; on
the other harness the registration is skipped and listed in `docs/init-report.json` (or use
`harnesses = [...]` to leave it out silently). The same goes for `ask`, `wakeup` and `skill`
actions (`skill` is Claude's Skill tool; Codex loads skills without a tool call).

## The template language (`renderer/tmpl.py`)

- `{{project.name}}`: a value. A missing variable is an ERROR (no silent blanks).
- `{{#if path}}…{{else}}…{{/if}}`, `{{#if !path}}`: truthiness (empty string/list = false).
- `{{#each path}}…{{/each}}`: inside, an item's keys are in scope; `{{.}}` is the item;
  `@index`, `@first`, `@last` are available (e.g. `{{#if !@last}}, {{/if}}`).
- `{{! comment }}`: dropped. `{{{{raw}}}}…{{{{/raw}}}}`: verbatim, for LaTeX or Lean
  text that contains `{{`.
- A line holding only a block tag (`{{#if x}}`, `{{/each}}`, …) is removed entirely.

### The render context

| Key | Meaning |
|---|---|
| `project.{name,slug,owner,field,subarea,research_kinds,init_date}` | from the interview |
| `owner` | shorthand for `project.owner` |
| `harness.{name,is_claude,is_codex,skills_dir,hook_config,context_files}` | the target harness |
| `harness.auto_compact_tokens` | the auto-compaction limit the harness config sets (`AUTO_COMPACT_TOKENS` in `renderer/adapters/base.py`) |
| `harness.cap.<capability>` | see the capability table below |
| `tiers.{strong,worker}` | model names |
| `stack.{tools,run_cmd,driver,research_commands,failure_signatures,hygiene_rules,proof_assistant,lake_path}` | the computational stack; `driver` is the experiment-driver file name, derived from the tool `run_cmd` starts unless the answers give one |
| `modules.<id>` | true if that module is on; any CATALOG id is allowed (unbuilt = false), others fail |
| `has.{computation,formalization,lean,failure_signatures,example_driver}` | derived switches (`example_driver`: the driver is the template's Python `driver.py`) |
| `seeds.{questions,conjectures,sources}` | seed lists (see `renderer/answers.py`); each question carries `active` (true for the one the owner chose to start on) |
| `seeds.active_question` | the id of that question, or `""` for none |
| `experiments.limits.{smoke,full,deep}.{time_s,mem_mb}` | experiment run limits, interview overrides over the defaults (always all six filled) |
| `exposition.{prior_work,model_text}` | the owner's prior work (list) and model text (string) for the readers module; empty when skipped |
| `module_list` | enabled modules, in order (id, number, title, group, summary, core) |
| `item` | inside a per-item template: the current seed |
| `toml.<path>` | the interview answers again, every string already a quoted TOML string. In a `.toml` template write `run_cmd = {{toml.stack.run_cmd}}` with no quotes of your own, so an answer containing `"`, `\` or `'''` cannot break the file |

### Capabilities (`harness.cap.*`)

| Capability | Claude | Codex (unverified) | Use it for |
|---|---|---|---|
| `background_callback` | yes | no | "run it in the background, you will be notified" |
| `resume_subagent` | yes | no | "resume the same worker by message" |
| `schedule_wakeup` | yes | no | scheduled self-wakeups |
| `ask_tool` | yes | no | a structured ask-the-owner tool |
| `transcripts` | yes | yes | reading session transcripts (retro) |
| `hook_spawn` | yes | yes | hooks that fire before an agent is dispatched |
| `tool_allowlist` | yes | no | an agent's tool list is enforced |
| `subagents` | yes | yes | dispatching agents at all |

**Rule:** any sentence that relies on one of these mechanisms goes inside
`{{#if harness.cap.X}}`, with an `{{else}}` that restates the rule in a form that works
without it (e.g. "run long jobs in the foreground and report when done"), or is dropped. Never name a harness-specific tool (`AskUserQuestion`,
`run_in_background`, `SendMessage`, `Explore`) outside such a block.

## Writing rules (distillation)

The source practice is a large, scarred, project-specific rulebook. A new project inherits
the rules without the incidents behind them, so every rule must earn its place.

1. **Rewrite, don't copy.** Generic for any mathematics field. No names of the source
   project, its tools, its people or its machine. The independence test fails on a local
   path (`/Users/`, `/home/`) in any template or generated file; keeping out every name
   specific to the source (its tools, its topics, its conjecture numbers) is the author's
   job.
2. **Shape of a rule:** the rule · why (the failure it prevents, stated generically, in one
   line) · anti-scope (when it does NOT apply). Keep each to a few lines. A rule with no
   failure behind it is cut.
3. **Trigger points.** Every rule names the moment it applies ("before you record a
   result", "when a worker reports stuck"). Doctrine that is only read on demand goes in
   `files/docs/discipline/<topic>.md`, and the moment that needs it must link it: from
   the AGENTS.md fragment, from a skill loaded at that moment, or from a hook message.
4. **AGENTS.md fragments are short:** a `## Heading`, at most ~8 lines, one link into
   `docs/discipline/`. The whole AGENTS.md must stay under 20 KB for every fixture.
   Wrap each rule in `{{#if view.shared}}` (every agent follows it: a worker or reviewer
   could break it, or needs it to find a file) or `{{#if view.coordinator}}` (only the main
   session acts on it: dispatching, committing, stopping, owner levers). On Claude the first
   go to `AGENTS.md`, which every subagent gets, and the second to `COORDINATOR.md`, which
   only the main session gets; a section left with only its heading is dropped. On Codex
   both are on, so the fragment renders as one section.
5. **Plain language.** Define every term in your module's `glossary.fragment.md.tmpl`; never use a
   term another module defines unless you depend on that module (or wrap the use in
   `{{#if modules.<id>}}`). The leave-one-out test renders without each removable module
   and checks nothing dangles.
6. **Owner levers stay the owner's.** Activating a question, `@priority`, approving an ASK
   change, publishing: agents propose, never do.
7. **No telemetry, no daemon, no network calls** in anything emitted. One exception, by the
   owner's decision of 2026-10-08: module 21-usage copies token COUNTS (never text) from the
   harness's local transcripts into the project's own `logs/usage.jsonl`. It stays local,
   sends nothing anywhere, and can be switched off or removed.
8. **Stdlib Python ≥ 3.11 only** for scripts and hooks; POSIX `sh` for tiny wrappers.
   macOS and Linux both (no GNU-only flags: e.g. no `sed -i` without a suffix, no `timeout`
   without a fallback).

## Hooks

- One script per hook in `files/hooks/<name>.py`, built on `hooks/_payload.py`:

  ```python
  import sys; from pathlib import Path
  sys.path.insert(0, str(Path(__file__).resolve().parent))
  import _payload

  def main(ev):
      if ev.action == "shell" and "rm -rf" in ev.command:
          _payload.nudge_once(ev, "my-hook", ev.command, "why, and what to do instead")

  if __name__ == "__main__":
      _payload.run(main, "my-hook")
  ```

- Use `ev.action`, never a harness tool name. Work when `ev.transcript_path` is None.
- Prefer `nudge_once` (refuse once per distinct key, re-issue proceeds) over `block`.
  A hard `block` needs a stated reason in the hook's docstring and an explicit bypass.
- A nudge message says: what was noticed, why it matters (one line), what to do, and that
  re-issuing proceeds. Name the discipline doc that explains more.
- **Selftest** in `files/hooks/selftest/test_<name>.py` (unittest), running the script
  through its real entry point (`subprocess` with a JSON payload on stdin) on all four
  branches: allow, trigger, bypass, and failure (malformed input → exit 0 + warning +
  traceback logged). Set `CLAUDE_PROJECT_DIR` to a temp dir in the subprocess env.

## Scripts

`files/bin/<name>`, executable, stdlib Python (or POSIX sh). Every script supports
`--help`. A script with checkable behavior puts `selftest: yes` in its first 15 lines and
implements `--selftest` (creates its own temp fixtures, exits 0 on success). `bin/selftest`
runs it automatically. Scripts read settings from `project.toml` (via `tomllib`), never
hard-coded paths.

## Agents

`agents/<name>.md` (or `.md.tmpl`) with frontmatter:

```
---
name: claim-auditor
description: one paragraph: when to use it, what it returns, what it does NOT do.
tier: strong            # strong | worker; reviewers are always strong
tools: [Read, Grep, Glob]   # Claude tool names; omit for all tools
sandbox: read-only      # read-only | workspace-write  (Codex sandbox_mode)
---
body: the agent's charter.
```

The Claude adapter writes `.claude/agents/<name>.md` with `model:`; the Codex adapter writes
`.codex/agents/<name>.toml` and prepends a read-only notice when the agent has a tool list
and a read-only sandbox (Codex has no tool allowlist).

## Skills

`skills/<name>/SKILL.md(.tmpl)` with `name` and `description` frontmatter (both harnesses
use the same skill format). The description says when to load it. Skills are where
procedure lives: a skill loaded at its trigger moment is read, while a long doc is often
not.

## Checks before you finish

```bash
python3 -m unittest discover -s tests          # all green, including independence + budget
```
