# init-math

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23973379.svg)](https://doi.org/10.5281/zenodo.23973379)

Set up a mathematics research project worked on by AI agents, through a short interview.

init-math asks about your field, how you work (proofs on paper, computing examples,
formalizing in Lean; any mix) and the questions you want answered. It then writes a project
that gives the agents a working discipline: a question registry and conjecture ledger,
independent reviewers that check claims and referee proofs before anything is recorded,
archived experiment runs, rules for checking citations firsthand, and a reflection loop
that turns recurring friction into fixes. The project is plain files, and it is yours: it
does not need init-math after the interview. [docs/MODULES.md](docs/MODULES.md) describes
every part.

> Status: v1 (version 0.2.0). Expect rough edges; please report what got in your way.

## Install

You need a Mac, Linux, or Windows 10 or 11 computer, and a paid plan for the agent program:
Claude (Pro or Max, for Claude Code) or ChatGPT (for Codex). Agents use far more than chat
does; Max is recommended.

1. **Install the agent program** (skip if you have it). Paste one line into Terminal (Mac:
   Cmd+Space, type Terminal; Linux) or PowerShell (Windows: Start menu, type PowerShell):

   | | Mac / Linux | Windows |
   |---|---|---|
   | Claude Code | `curl -fsSL https://claude.ai/install.sh \| bash` | `irm https://claude.ai/install.ps1 \| iex` |
   | Codex | `curl -fsSL https://chatgpt.com/codex/install.sh \| sh` | `irm https://chatgpt.com/codex/install.ps1 \| iex` |

2. **Start it and paste one sentence.** In a new Terminal or PowerShell window, type `claude`
   or `codex`, log in, and paste the sentence below. (If it says `command not found`, open a
   new window and try again. On Windows, if Claude Code asks for Git for Windows, install it
   from <https://git-scm.com/downloads/win> with the default choices.)

   ```
   Download https://github.com/nkohen/init-math/archive/refs/heads/main.tar.gz, unpack it into ~/research/init-math, and walk me through its SETUP-GUIDE.md, one step at a time.
   ```

The agent fetches init-math, checks your computer and walks you through the rest in plain
words, one step at a time. Besides that download it runs only checks; you run what
installs, in a second window. Ask it anything along the way: how to update or undo,
Windows, VS Code, what it costs. To update later, ask an agent to update init-math.

Prefer no agent? Click **Code**, then **Download ZIP** on this page, unpack it, and run
`bash setup.sh` in it (Windows: `powershell -ExecutionPolicy Bypass -File
setup-windows.ps1`); `bash setup.sh --help` lists the options, including `--ssh`.

## Start a project

In the folder that should hold your projects (on Windows, inside Ubuntu), start the agent
and type `/init-math:init-math` (Codex: `Use the init-math:init-math skill to set up a
research project.`). The interview creates the project folder, then tells you how to open
it. **Always start the agent in the project's own folder**: elsewhere it works without the
project's rules and reviewers, and nothing tells you so.

What you type and the files the agents read go to Anthropic (Claude Code) or OpenAI
(Codex), as in any chat with them. The project is a local git repository: nothing is pushed
or published.

## Feedback

Problems with init-math itself: open an issue at
<https://github.com/nkohen/init-math/issues>, with the version that made your project (its
first commit records it). Setup logs and project files contain your user name and folder
paths; read them before you attach them. Colleagues trying init-math with Nadav: write to
Nadav directly, as before.

## Cite

If init-math helped your work, please cite it ("Cite this repository" on GitHub, from
[CITATION.cff](CITATION.cff)):

> Nadav Kohen, *init-math*, version 0.2.0, https://doi.org/10.5281/zenodo.23973379

That DOI covers every release and resolves to the latest; version 0.2.0 on its own is
https://doi.org/10.5281/zenodo.23973380.

MIT-licensed ([LICENSE](LICENSE)). Projects it generates are yours: the files it writes into
them carry no license notice and no obligation.

## Develop

[AGENTS.md](AGENTS.md) explains how this repository is organized; [docs/](docs/README.md)
indexes the rest (architecture, modules, tests). `bin/test` runs the test suite.
