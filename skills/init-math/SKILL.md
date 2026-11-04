---
name: init-math
description: Interview a mathematician and create a new AI-agent research project for them (research questions, conjecture ledger, honesty reviewers, experiment discipline, reflection loop). Use when someone wants to start a mathematics research project run with AI agents, or says "init-math", "set up a math research project", or similar. Writes only into a new or empty directory.
---

# init-math: interview, then create the project

You are setting up a research project for a mathematician. The project you create gives
their agents a working discipline: a registry of research questions, a ledger of
conjectures with honest evidence, reviewers that check claims before they are recorded,
rules for experiments and proofs, and a reflection loop that improves the setup from its
own friction. Your job is to ask good questions, specialize the generic setup to their
field and tools, and run the generator. You do not write project files yourself.

`SCRIPTS` below means the `scripts/` directory next to this SKILL.md. Run everything with
absolute paths.

## How to interview

The person wants to start working, not to configure software. Ask only what they alone can
tell you, take a sensible default for everything else, and show the defaults once at the
end, where they can change them. A default that turns out wrong costs little: the project's
reflection loop tunes its settings from what actually happens, and any agent can change
one on request.

- Follow [questions.md](questions.md). It has four exchanges: what they work on (one open
  question), their research questions sharpened with which one to start on, anything they
  already believe or build on (optional), and the read-back. Its section 4 lists what you
  fill without asking.
- **Detect, don't ask.** Which agent program you are running in, which tools are installed,
  their name from git, the computer's memory, an existing Lean project: find these and
  propose them in the read-back.
- **Surface only what they need now.** Name what the project is set up for in one line,
  but do not explain how modules, reviewers, hooks or the reflection loop work; the project's `getting-started` skill does that in
  the first session. Avoid jargon; if you must use a term, define it in passing.
- The person describes their work in their own words; you turn it into commands, patterns
  and settings. Never ask them for a regular expression, a command template, an error
  message or an exit code.
- "I don't know" and "skip" are fine everywhere except the research questions themselves.
  If they have no conjectures or sources yet, say that is fine: the agents propose them, and
  their first job is a literature pass on the question.
- Never invent their research content: questions, conjectures and sources are theirs; your
  part is to sharpen the wording and check the shape.

## Procedure

1. **Preflight.** If this session runs on Windows itself (PowerShell, `C:\` paths, a
   Windows VS Code window) rather than inside Linux, stop here: an init-math project runs
   inside WSL, and a project made from this session would be opened from here, where none
   of its skills, hooks, reviewers or settings load. Tell the person to open Ubuntu from the
   Start menu, type `mkdir -p ~/research && cd ~/research`, start the agent there, and ask
   again; do not run the generator through `wsl.exe` from here. Otherwise run
   `python3 SCRIPTS/init_project.py --preflight`. Say nothing if it passes. If it fails, tell the person exactly what to install (the project's hooks run
   `python3` from PATH and need 3.11 or newer) and stop until it passes.
2. **Interview** as in [questions.md](questions.md), sections 1 to 3.
3. **Target directory.** The project goes in a new folder named after the project's slug in
   the current directory (`./<slug>`). Run
   `python3 SCRIPTS/init_project.py --check-target <dir>`; if it refuses (not empty, or not
   writable), choose `<slug>-2` and so on, and mention it in the read-back. Never clear a
   directory. If the current directory is the person's home folder or a system folder,
   use `~/research/<slug>` instead. If the current directory is empty (the person likely
   made it for this project), still propose `./<slug>`. In the read-back, offer the current
   directory itself as the target, and use it if they accept. The answers file then goes
   in a temporary directory. `--check-target` also refuses a folder on the Windows
   drive (`/mnt/c/...`); use `~/research/<slug>` then, never a way around the refusal.
4. **Write answers.json** OUTSIDE the target directory (for example next to it as
   `<target>.answers.json`, or in a temporary directory). Set `project.init_date` to
   today's date (YYYY-MM-DD). The shape is in questions.md, "answers.json shape".
5. **Check.** Run `python3 SCRIPTS/init_project.py --check-answers <answers.json>`. Fix any
   error yourself where you can (errors name the key path and the item), and ask the person
   only about their own content. Fix warnings (a placeholder tie, a `lake_path` that is not
   a Lake project) before the read-back; `modules_off_why` explains every module that is
   off, for your read-back line.
6. **Read back** as in questions.md section 5, and get an explicit go-ahead. If they change
   something, update answers.json and check again.
7. **Create.** Run
   `python3 SCRIPTS/init_project.py --answers <answers.json> --out <target>`.
   This renders the project, makes the initial git commit, switches on the commit hook
   (if that module is on) and runs `bin/selftest`. Report the selftest result honestly; if
   it failed, show the failing lines and run `<target>/bin/selftest -v` for details.
8. **Hand over.** Relay the printed next steps word for word, including the commands to
   leave this session and start the agent in the new folder. **Do not continue the research
   in this session**, even if the person asks to: the project's skills, hooks, reviewers and
   model settings load only in a session started in its folder, so work done from here runs
   without any of them, silently. If they want to stay in this window, say exactly that and
   repeat the steps. Never write an AGENTS.md, CLAUDE.md or any other instructions outside
   the new folder to point an agent into it, and never install the project's skills
   somewhere else. Tell them that there the
   `getting-started` skill walks them through the first session step by step (so they need
   not read the manual first), and that every file is now theirs to change: the project
   evolves through its own reflection loop, and there is no upgrade path from init-math
   afterwards. Offer to delete the answers file (a copy is kept in
   `docs/init-answers.json`).

## Rules

- Do not create a remote repository, push, or publish anything.
- Write nothing outside the new project folder and the answers file: no redirect files in
  a parent folder, no copies of its skills or settings elsewhere.
- If Lean is on, do not run the Lean setup commands; the project prints them in
  `formal/README.md`. If `stack.lake_path` is given there is nothing to set up.
- Only the owner makes a question `active`. In the interview, ask which ONE seeded question
  to start on and recommend one, but the pick is theirs, and "none" is allowed. Never choose
  for them, and never activate more than the one they name; the rest are written `proposed`.
- If the person wants something init-math cannot do (another harness, a module marked
  "not available"), say so plainly and continue without it.
