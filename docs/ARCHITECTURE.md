# How init-math works

This page is for anyone who wants to change init-math or understand how it is built. For
installing and using it, see the [README](../README.md); for what a generated project
contains, see [MODULES.md](MODULES.md).

## The path from interview to project

```
 the interview            the answers file          the generator              the project
 (an agent following  ->  answers.json        ->    init_project.py     ->     a new git repository
  SKILL.md)               (plain JSON)              + renderer/                you own
```

1. **The interview.** The harness (Claude Code or Codex CLI) loads the `init-math` skill,
   [`skills/init-math/SKILL.md`](../skills/init-math/SKILL.md). The agent follows it and its
   question bank, [`questions.md`](../skills/init-math/questions.md): four short exchanges
   about the person's work, their research questions, what they already believe, and a
   read-back of everything it chose for them. It detects what it can (the harness, the
   installed software, the computer's memory, an existing Lean project) instead of asking.
   The agent never writes project files itself; it writes one answers file.
2. **The answers file.** A JSON file with the project's name and owner, the kinds of
   research (proofs, computation, formalization), the software stack, the seeded research
   questions and conjectures, and which modules to switch on or off.
   [`renderer/answers.py`](../skills/init-math/scripts/renderer/answers.py) is the contract:
   it validates the file by hand (standard library only) and fills in defaults. Every key
   the interview must ask about is listed there, and a test checks that the question bank
   covers each one.
3. **The generator.**
   [`init_project.py`](../skills/init-math/scripts/init_project.py) checks the target
   folder (it must be new or empty, and not on the Windows drive under WSL), renders the
   project, runs `git init`, makes the first commit, turns on the commit gate's git hook,
   and runs the project's own self-check, `bin/selftest`. It then prints the owner's next
   steps. It also offers `--list-modules` (the menu the interview shows) and
   `--check-answers` (validate a file and show which modules end up on).
4. **The project.** Plain files in a new git repository with no remote. It keeps a copy of
   the answers (`docs/init-answers.json`) and a report of what was rendered
   (`docs/init-report.json`). From here on the project does not need init-math.

## The renderer

The renderer lives in [`skills/init-math/scripts/renderer/`](../skills/init-math/scripts/renderer/)
and uses only the Python 3.11 standard library.

- **[`tmpl.py`](../skills/init-math/scripts/renderer/tmpl.py): the template language.** A
  small, strict engine: `{{value}}`, `{{#if}}…{{else}}…{{/if}}`, `{{#each}}`, comments and
  raw blocks (for LaTeX and Lean, which are full of braces). A missing value is an error,
  never a silent blank.
- **[`render.py`](../skills/init-math/scripts/renderer/render.py): choosing and rendering
  modules.** It reads every module's metadata, decides which are on, builds the values the
  templates see, and writes the files.
  - Which modules are on: core modules always; every module marked `included` unless the
    answers switch it off; a preset (`theory-only`) switches off the computation modules; a
    module that needs a proof assistant is on only if the owner uses it; and a module whose
    dependencies are off is an error, not a silent drop.
  - Module fragments (each module's section of `AGENTS.md`, its glossary entries, its tables
    in `project.toml`, its `.gitignore` lines) are spliced into files the core owns, in
    module order. Two modules may never write the same file.
  - On Claude Code, `AGENTS.md` is rendered twice: once with only the rules every agent
    follows (`view.shared`), as `AGENTS.md`, and once with only the main session's
    (`view.coordinator`), as `COORDINATOR.md`. A subagent gets `CLAUDE.md` and so
    `AGENTS.md`; the core hook `coordinator-context.py` gives `COORDINATOR.md` to the main
    session only, at SessionStart. On Codex both views are on and there is one `AGENTS.md`
    (whether a Codex subagent reads it is unchecked).
- **[`adapters/`](../skills/init-math/scripts/renderer/adapters/): one per harness.** The
  templates are harness-neutral. An adapter turns the neutral pieces into what one harness
  reads: where skills go, how a reviewer agent's file looks, and how hooks are registered.
  Claude Code and Codex CLI differ in all three.
  - The hook scripts themselves are the same for both. A shared helper, `hooks/_payload.py`,
    normalizes the two harnesses' event payloads.
  - Each adapter declares capabilities (for example, whether hooks can read a reviewer's
    brief). Templates test them with `{{#if harness.cap.…}}`, so prose that depends on a
    mechanism appears only where the mechanism exists. The adapter records which
    capabilities a live probe confirmed (`tests/probe/`) and which come from the harness's
    documentation.

Two rules hold for everything the renderer writes:

- **Deterministic.** The same answers and templates give a byte-identical project: sorted
  directory walks, sorted JSON keys, no clock reads (the project's date comes from the
  answers), no randomness.
- **Independent.** Nothing emitted names the practice the templates were distilled from,
  its tools, its people or any local path. A test enforces the obvious cases.

## The templates

[`skills/init-math/scripts/templates/`](../skills/init-math/scripts/templates/) holds:

- **`core/`**, always emitted: the project's `AGENTS.md` (the agents' standing
  instructions; on Claude also `COORDINATOR.md`, the main session's), `GLOSSARY.md` (and
  `bin/glossary` to look one term up), `project.toml` (settings), the owner's manual
  `docs/OWNER.md`, the work-folder layout, `bin/selftest` and `bin/doctor`, the hook
  runtime, and the `getting-started` skill for the first session.
- **`modules/NN-<id>/`**, one per mechanism. Each has a `module.toml` (title, summary,
  status, dependencies, hook registrations), the files it emits (`files/`, `skills/`,
  `agents/`, fragments). The full format is in [AUTHORING-MODULES.md](AUTHORING-MODULES.md).

The project's `bin/selftest` finds module checks by convention: every hook must compile,
every test under `hooks/selftest/` runs, and every script in `bin/` marked `selftest: yes`
runs with `--selftest`. A module adds its own checks just by shipping them, and a broken
piece shows up in the generated project too.

## Distribution

The repository is a harness plugin: [`plugin.json`](../plugin.json) names the skill
directory, and the repository itself serves as the plugin marketplace. `setup.sh` (Mac,
Linux, WSL) and `setup-windows.ps1` (Windows) check a computer, write a plan of the steps
they would take, and run it only after a yes. Each step checks first and skips itself if
it is already done. The [README](../README.md) and the agent-facing
[SETUP-GUIDE.md](../SETUP-GUIDE.md) cover them.

## Testing

`bin/test` runs the unit, golden, independence and setup tests, with no model
calls. The behavioral scenarios and the reviewer bench spend model calls and run
separately. All of it is described in [TESTING.md](TESTING.md).
