# What a generated project contains

This page describes what a project made by init-math contains. Installation and the
interview are in the [README](../README.md).

## The project in brief

The interview writes a new folder: plain text files in a git repository on your machine,
with no remote. It is yours: you can read and edit every file, and init-math plays no part
afterwards. The agents keep everything that matters in these files, so a new session picks
up where the last one stopped.

The project has two layers. **The core** is always there. **Modules**, 21 of them, add
one mechanism each, such as the question registry, the reviewers or the reflection loop.
Each adds a section to the agents' guide and, usually, a page of reasoning
under `docs/discipline/`, scripts in `bin/`, automatic checks, skills or reviewer agents.

### How modules are chosen

- **All modules are on by default.** The interview does not walk you through them.
- **Theory only.** If you work only on paper, with no computation and no Lean, the
  interview uses the *theory-only* preset, which switches off experiments, the
  computed-results cache, Lean and long runs.
- **Lean** is on only if you said you formalize in Lean.
- **You can ask the interviewer to leave a module out**, except three: the review gates,
  the mechanical scans and the reflection loop. Some modules need others: the conjecture
  ledger needs the question registry; lines of attack need the question registry and the
  model tiers.
- **Later.** init-math never updates a project after creating it. To add a module you left
  out, ask an agent to apply it by hand from init-math's source; your project's
  `docs/OWNER.md` ("Turning a module on later") says how.

A few automatic checks exist only on Claude Code, because Codex hides from hooks what they
need to see; this page notes them.

Many checks below are **nudges**: they refuse an action once, with an explanation, and let
an identical retry through. Your manual says how to silence them for a session or remove
one for good.

## At a glance

| Part | What it does for you | When it is on |
|---|---|---|
| [Core](#the-core) | Agents' guide, settings, your manual, self-checks, work folders | always |
| [Research questions](#research-questions) | Ties all work to questions you activate | default |
| [Conjecture ledger](#conjecture-ledger) | One file per conjecture, with status and evidence | default; needs questions |
| [Known results](#known-results) | What the literature already proves, with sources | default |
| [Literature wiki](#literature-wiki) | Sources, a reading inbox, synthesized notes | default |
| [Review gates](#review-gates) | Separate reviewers check each finding before it is recorded | always |
| [Reader reviewers](#reader-reviewers) | Reviewers for write-ups other people will read | default |
| [Mechanical scans](#mechanical-scans) | Quick scripts catch routine defects before review | always |
| [Commit gate](#commit-gate) | Refuses to commit a finding the reviewers have not passed | default |
| [Firsthand checks](#firsthand-checks) | Search before building; verify a claim before relying on it | default |
| [Experiments](#experiments) | Every computation archived as a reproducible run | off in theory-only |
| [Computed-results cache](#computed-results-cache) | Nothing is computed twice | off in theory-only |
| [Lean](#lean) | Conventions and tools for formalizing | only with Lean |
| [Long runs](#long-runs) | Long computations stay tracked and get checked | off in theory-only |
| [Model tiers and workers](#model-tiers-and-workers) | Strong models direct and review; cheaper ones execute | default |
| [When to stop](#when-to-stop) | Agents keep going on clear steps and leave a resume point | default |
| [Lines of attack](#lines-of-attack) | A record of every approach tried, and why it stopped | default; needs questions and tiers |
| [Safety guard](#safety-guard) | Blocks destructive commands; leaves `sudo` to you | default |
| [Reflection loop](#reflection-loop) | Turns recurring friction into fixes to the setup | always |
| [Session retrospective](#session-retrospective) | After a session of corrections, asks what would have prevented them | default |
| [Program review](#program-review) | Every few weeks: is the work moving toward your goals? | default |
| [Usage statistics](#usage-statistics) | Token counts per model and role | default |

"Default" means on unless you asked to leave it out.

## The core

- **`AGENTS.md`**, the agents' operating guide, read at the start of every session (on
  Claude Code through `CLAUDE.md`). Its ground rules: work from the project's folder; keep
  durable state on disk, not in the conversation; report at the scope the evidence
  supports; ask only at a genuine fork; commit finished work locally, naming each file.
  Pushing and publishing are yours. It lists the decisions only you make, and each module
  adds a short section. On Claude Code it is split in two: `AGENTS.md` holds what every
  agent follows (reviewers and workers get it too), and `COORDINATOR.md` what only the main
  session does (dispatching, committing, stopping, your decisions), given to the main
  session alone by a hook at its start. `bin/glossary <term>` prints one glossary entry.
- **`docs/OWNER.md`**, your manual: first steps, your decisions, switching off a nudge,
  models and cost. **`docs/discipline/`** holds one page of reasoning per mechanism.
- **`GLOSSARY.md`** defines terms; **`SEARCH-ALIASES.md`** maps a searched-for word to the
  project's word.
- **`project.toml`**, the settings scripts and hooks read: your tools and how a script
  runs, the two model roles, what kind of field this is.
- **`work/<slug>/`**, one folder per line of work, copied from `work/TEMPLATE/`. Its README
  holds the plan, a **RESUME HERE** naming the exact next step, its files and the outcome.
  Throwaway files go in its `scratch/`, which git ignores; a manuscript never does. A
  nudge fires when an agent first drops a working file into `notes/` (for standing notes
  only).
- **`bin/selftest`** checks the setup's files: hooks compile and pass their tests, scripts
  pass theirs. Run it after changing a hook, a script or `project.toml`.
- **`bin/doctor`** checks the live session: the agent started in this folder, hooks run,
  reviewers run as the project's own agents. The agent runs it first thing.
- **The `getting-started` skill** walks you through your first session.

On Claude Code, scripts in `bin/` that only check or record are pre-approved, so agents
run them without asking you.

## Direction

### Research questions

A short list of questions, each one sentence with an answer you lack. Only you make a
question *active*, and agents work only on active ones. Every task an agent starts or hands
on carries a **question tie**: which possible answer it moves, and what each outcome,
failure included, would change. "Related to the question" is not a tie. When you change
direction, the agent recommends what to do with the other active questions, and edits only
on your word.

You will see:

- `wiki/questions/Q001-<slug>.md` and so on: the question, its readings, numbered *answer
  shapes* (the forms an answer could take), what is known, examples. Status is `proposed`,
  `active`, `parked` or `answered`.
- `bin/question-check` checks the question files and each conjecture's link to them;
  `bin/tie-check` checks a tie's shape.
- The `tie-auditor` reviewer judges a tie's meaning: does the task move the answer, or only
  share a topic? It reads every task bigger than a quick trial.
- The `new-question` skill turns an idea into a `proposed` question.
- A nudge when a research task is handed to an agent without a tie (on Codex, a reminder
  once per session).

Asks of you: activate questions. Set `status: active` and add `activated-by:` with your
name, or ask an agent to. A question you chose in the interview is already active.

### Conjecture ledger

One file per conjecture, stated as a connection between properties on a named family and
tied to a question. Its status says how strongly it is believed: `open`, `testing`,
`weakly-supported`, `supported`, `scope-tight` (holds in its scope; widening is known to
break it), `refuted` or `proved`. Refuted entries are kept. A status is not a to-do list,
since a proved conjecture usually still has next steps: each next step is an `@residue:`
line, and the backlog is rebuilt from them across all statuses.

You will see `wiki/conjectures/` with its index; `bin/residues`, which lists open next
steps with your priorities first; the `new-conjecture` skill, which states a conjecture and
writes its first falsification step; and `@assumes:` lines marking work that relies on an
unproved argument.

Who sets a status: the agent may mark a conjecture weakly supported or refuted after a
claim-auditor pass. For `supported`, `scope-tight` or `proved` by the project's own proof,
it proposes once the required reviewers pass, and you say yes. A `proved` resting on a cited
theorem it may set itself, after reading the theorem and a claim-auditor pass.

Asks of you: approve promotions, and mark `@priority` on what you want first. Nothing
records your yes, so undo a promotion made without asking.

On by default; needs the research questions module.

### Known results

A catalog of what the literature already proves or observes, filed by object of study, in
`wiki/known-results/` (empty at first). Agents look an object up before testing or proving
anything: it may be settled. Each entry records source, section or theorem number, date
accessed, and whether it was read firsthand or from a summary. A claim nobody has read a
source for stays a *seed to verify*. Only a firsthand reading may settle a conjecture. An
entry can say it `settles:` or `suggests:` a conjecture; the scans check the conjecture links
back.

### Literature wiki

A wiki for what the project reads. The rule that matters most: synthesize a source before
experimenting off it; a pasted link is not a reading.

- `wiki/raw/` keeps sources as they came, never edited; `wiki/inbox/` holds sources still to
  read, one per source you named in the interview; `wiki/concepts/` holds synthesized
  articles and `wiki/references/` reading lists. Each folder has an `_index.md`, and
  `wiki/log.md` records every operation.
- The `ingest` skill takes one source in, in one commit: raw record, concept article,
  known-result entries, indexes, log.
- `bin/wiki-check` finds raw sources nothing synthesizes.

Your manual suggests having the agents work through the inbox early.

## Checking

### Review gates

Separate reviewer agents check every finding before it is recorded. Each starts without the
author's context and answers one question. The author proposes; you promote. Always on.

- `claim-auditor`: does each conclusion follow from the cited evidence, at the stated scope?
- `proof-referee`: is the proof rigorous and well written? It re-derives the load-bearing
  step first.
- `red-team`: is it true? It tries to break the claim and reports the cheapest test that
  could refute it, with the result.

How it runs:

- Agents load the `gate-chain` skill the moment they record or report a finding, even in a
  message. Cheapest first: the scans, then the claim-auditor, then the red-team; a proof
  goes to the proof-referee first. Each reviewer's fixes are applied before the next one.
- Each reviewer ends with a one-word verdict; only the passing word lets work go on. A
  report lists each problem with its fix, marked major or minor. The proof-referee passes a
  proof whose points are all minor; you apply them without another review.
- Review scales to the claim: one computed fact gets a recheck, not the chain. After three
  reviews of one document by one reviewer, the claim is recorded at the strength the last
  review supports, with its open issues listed.
- An argument that convinces but is not a proof is recorded as an *argued claim*: labelled,
  usable as evidence, never as a result.
- Nudges: when a reviewer gets a whole document over 400 lines (send a section); on Claude
  Code, when a brief reveals an earlier verdict or the author's confidence, which biases a
  review.

Asks of you: decide the promotions agents propose.

### Reader reviewers

Three more reviewers, for a write-up people outside the project will read. The write-up is
a separate document, drafted from the internal record once its findings are settled.

- `provenance` marks each result and technique as new, your prior work, or classical, and
  recommends citations.
- `expositor` reads as a mathematician who wants to learn from and reuse the work.
- `cold-reader` reads with no project context and lists what a stranger cannot follow.

Asks of you, optionally: in `docs/discipline/exposition.md`, list your published papers (so
write-ups cite rather than re-derive them) and name a paper whose writing you want
imitated.

### Mechanical scans

Scripts that use no AI model and take seconds. They catch routine defects before a reviewer
spends effort. Always on; most only report.

- `bin/hedge-scan`: does each headline carry the qualifiers of the body beneath it?
- `bin/define-check`: invented codes and notation used without a definition.
- `bin/math-hygiene-scan`: proof hygiene, such as analytic language in a formal or finite
  setting or one symbol defined twice, plus rules for your field in `project.toml`.
- `bin/stale-status-scan`: after a claim changes, the places still stating the old one.
- `bin/scope-estimate-scan`: phrases like "intractable" or "multi-week" that could stop work
  and need backing by a real search or attempt.
- `bin/link-check`, `bin/orphan-check`, `bin/backlink-check`: broken links, files no index
  lists, and one-way links between known results and conjectures.

At commit time, nudges fire on undefined codes in shared indexes, unindexed files and
one-way links.

### Commit gate

A check git runs before each commit. It refuses a commit that records a finding (a changed
line inside a proof, or a conjecture status change that needs review) unless each required
reviewer was sent the exact text being committed and its passing verdict was stamped.
Editing after review means reviewing again.

- `.githooks/pre-commit` is the check. It also runs `bin/question-check`, refusing on a
  failure.
- `.gates/` logs, automatically, which text each reviewer was sent; `bin/gate-stamp`
  records a verdict in the reviewer's own words. A passing stamp whose text says
  "sketched" or "not yet verified" is refused unless the caveat is acknowledged.
- `[gates]` in `project.toml` says which changes need which reviewers; you can add rules.

Asks of you: run `bin/setup-hooks` once in any new clone (done for this copy).
`GATE_OK=1 git commit …` commits past the gate when no review is needed; agents may not use
it, and your bypasses are logged so the reflection loop sees when the gate is too strict.

### Firsthand checks

Look before you build: search the project's own record, then the literature, before
constructing a method. Check before you pass it on: a claim that decides work or enters a
record gets one check by the agent itself. It reads a cited theorem itself, searches the
whole library before saying something is missing, scouts before calling a task too hard,
verifies a premise before handing it on, and never says "recorded" unless the write
happened.

- The `lit-search` agent searches the web and preprint servers and reports where a question
  stands, with candidate citations marked by how they were verified.
- Nudges: once per session, search the project's record before the literature; at commit,
  a new status or attribution ("due to", "well-known") with no literature search since the
  file last changed; at the end of a turn, a reply claiming a record was written when
  nothing was.

On Claude Code, web search is allowed without asking, because the search agent often runs
in the background where it cannot ask. Your manual says how to require your approval.

## Computing

All four are off in the theory-only preset.

### Experiments

Every computation is an experiment with its own folder, and every run is archived as a
self-describing bundle, analyzed later from the bundle alone. The doctrine: go wide on small
cases before deep on large ones; try the hardest cases first in a seconds-long trial; every
script re-checks one case whose answer is known independently. When the watchdog kills a
run, make the test cheaper; never just raise the limit.

- `experiments/<slug>/`, from `experiments/TEMPLATE/`: a README (prior art, question tie,
  prediction, method, findings, surprises) and the script.
- `bin/exp-run <slug>` with `--smoke` (seconds), `--full` (the real sweep) or `--deep`
  (larger, opt-in). It records the command, git commit, tool versions and limits, and runs
  the script under a time and memory watchdog. A full or deep run is refused if the question tie
  fails its check.
- `bin/exp-pending` lists bundles not yet analyzed; analysis is written in a fresh session.
- The `exp-worker` agent, on the cheaper model, writes and smoke-tests the script, then
  returns the command for the full run.

The time and memory limits came from the interview; change them in `project.toml`.

### Computed-results cache

A shared table of computed values keyed by a canonical form of each object, so nothing is
computed twice. Agents look a value up before computing it and add it afterwards, with
where it came from. A second, different value for the same object is a conflict to
investigate, never an overwrite. `bin/cache` looks up and appends; tables live in
`cache/results/`.

Asks of you, when an agent first wants to cache a value: describe the keys in
`cache/manifest.md` and set the key columns in `project.toml` (say, a graph's canonical
form as key, its chromatic number as value).

### Lean

A result is done only with no `sorry` and a clean axioms check. A proof of a stronger
statement counts only when the step from it to the target is itself formalized. Library
names are looked up, never written from memory, and a new definition is tested on one case
it must accept and one it must reject.

- `bin/lib-find` searches the whole library, and the project's Lean files, by name.
- `bin/lean-build` builds with checks a bare `lake build` skips: the Lean version matches
  the project's pin, the exit code is kept, and a warning appears when the whole library is
  compiling from source. A bare `lake build` gets a nudge.
- The `lean-worker` agent proves one lemma whose statement is written, then hands back.

Asks of you: set `lake_path` in `project.toml` to your Lean project, unless it is the only
one under `formal/` (the interview may have found it).

On only if you said in the interview that you formalize in Lean.

### Long runs

Before any run longer than about two minutes, the `launch-preflight` skill walks the agent
through a checklist: a freshly verified build, a known-answer check, a fresh output folder,
a resource limit, a progress signal. An exit code of 0 is not the result; the agent checks
the output itself.

- `bin/bg-run` runs a command with progress lines and can keep a record on disk for a
  later session; `bin/heartbeat` flags a stall; `bin/wait-until-done` waits for a job.
- A hook blocks hand-rolled wait loops and nudges on detached launches. On Claude Code it
  also blocks a launch that would escape the harness's tracking, and a nudge fires when the
  agent sets a short wake-up although the job will wake it anyway.

## Working habits

### Model tiers and workers

Two model roles, set in `project.toml`. The **strong** model plans, reviews and writes
anything durable; the cheaper **worker** model carries out well-specified *bricks*, such as
a lemma whose statement is written. A reviewer never runs on a weaker model than the
author it reviews.

- The `worker` agent ends with DONE, PARTIAL or NEED-DIRECTION, and hands back at fixed
  triggers instead of judging its own stuckness: three failed attempts at one goal, an error
  unchanged after two, a choice of route.
- The main agent, the *coordinator*, runs every long job; a worker validates on a
  seconds-scale case and returns the command. A nudge fires when a brief asks a worker to run
  a long job itself.
- On Claude Code, a nudge before the agent asks you to pick among three or more options:
  independent, cheap options it should simply do.

Your manual ("Models") says how to change the models.

### When to stop

Without a "continue" from you, an agent finishes the task it was given, including the cheap
threads inside it, and reports; it asks before starting a new direction. With one, it does
each concrete next step and never ends on "is this a good checkpoint?". Before calling work
"deep" or "multi-session", it lists numbered bricks, cheapest first, and tries the cheapest.
Blocked on a hard step, it states the step as an explicit hypothesis and finishes everything
around it. Multi-step work keeps a RESUME HERE on disk.

A nudge fires when your last message was a bare "continue" and the agent is about to stop:
it is asked once to carry on if a next step exists. `CONTINUE_NUDGE_OFF=1` switches it off.

### Lines of attack

A record of every approach tried on a hard target (a question, a conjecture, a brick, a
lemma): where it broke, what it established anyway, what would revive it. A later session
does not retry a dead route blind, and agents read what blocked a target before briefing
work on it.

- `wiki/attempts/`, written through `bin/attempts` by the coordinator only.
- Flags from `bin/attempts`. *Audit due*: several approaches on one target were set aside,
  so the agent questions the belief behind them before trying again. *Budget reached*: an
  approach used its allotted worker runs, so the coordinator extends it (naming the sign of
  progress), switches, steps down to a special case, or sets it aside. *Stale*: an active
  approach has gone untouched.
- The `attack` skill for choosing a route, with a menu of moves in
  `docs/discipline/moves.md` (a toy model, specialize or generalize, assume the missing
  lemma, ...) ordered by which have worked here.
- `docs/principles.toml`, rules whose use agents record, counted by `bin/principle-usage`
  for the program review.

Asks of you: switching a principle or a move off is your call. Before stepping down from a
question you activated, the agent asks you.

On by default; needs the research questions and model tiers modules.

### Safety guard

A hook refuses a few dangerous commands: recursive deletes, a force push or deletion of the
main branch, a download piped into a shell. `sudo` and making files writable by everyone are
your steps: the agent gives you instructions for only those steps, what each changes and how
to undo it, and carries on with the rest. An agent's attempt to bypass the commit gate is
refused and logged. Nudges favour staging named files over `git add -A`, the edit tool over
in-place `sed`, and against a `cd` that strands later commands in the wrong folder.

Asks of you: run the `sudo` steps when asked. To lift the blocks for a session, run
`export GUARD_OFF=1` before starting the agent, after reading why a command was blocked.

## Learning

### Reflection loop

Friction is written down as it happens, and a periodic pass turns what recurs into small,
tested fixes to the setup. Always on.

- The records: friction an agent or you noticed, failed runs of your research tools (logged
  by a hook), your corrections, all under `logs/`, and prose in
  `notes/workflow-journal.md`. `bin/journal` reads and writes them.
- The `friction` skill logs one line. The `reflect` skill groups what recurred and drafts
  fixes. A small, tested, reversible fix that adds a reminder or repairs a check is applied
  and committed, tagged so you can audit it. Anything that edits `AGENTS.md` or `COORDINATOR.md`, widens a
  permission, adds a blocking or automatic check, or encodes your taste waits for your yes
  (rules in `notes/reflect-autonomy-heuristics.md`).
- Hooks: a suggestion to run a pass when the same kind of failure keeps recurring; every
  few turns, a question about friction not yet logged; and proposals waiting for you,
  listed and numbered at the end of a reply.

Asks of you: answer proposals ("yes to 1, no to 2"); "continue" leaves them waiting. Run
the `reflect` skill now and then, or when an agent suggests it.

### Session retrospective

At the end of a session in which you gave a lot of feedback, the `retro` skill lists what
you had to correct or explain, logs it, and proposes two to four standing changes that would
have made that feedback unnecessary. They join the reflection loop's queue; none is applied
unprompted. Ask for one after such a session.

### Program review

An occasional review, with you present, of whether the research as a whole is moving toward
your written goals. The `program-review` skill drafts findings, each citing evidence or
marked ungrounded; asks you at most three questions about goals; checks whether recent
changes to the setup were used; and records only the findings you accept.

Your goals live in `notes/program-goals.md` (only you write them; agents transcribe your
answers), past reviews in `notes/program-reviews.md`. When a review is due, by default 21
days after the last if anything was committed since, a reminder at most once a week asks
the agent to offer one. It also offers one when you change direction.

Asks of you: fill in starting goals when you have a few minutes; the first review asks about
any left blank. The interval is in `project.toml`.

### Usage statistics

At the end of every turn a hook copies token counts, never text, from the harness's session
record into `logs/usage.jsonl`, per model and per role (main agent or subagent). Agents
consult it before proposing a change of models. `bin/usage-report` totals by model, role,
day, week or session, shows the main agent's share of output and the largest context a
session reached, and with `--backfill` imports earlier sessions the harness still keeps. It
shows tokens, not money: add your own per-model rates in `project.toml` for a cost estimate.
`USAGE_LOG_OFF=1` stops the log.

## Words used here

- **Harness**: the agent program you run, Claude Code or Codex CLI.
- **Skill**: a named procedure the agent follows when asked or when its moment comes (on
  Claude Code `/name`, on Codex `$name`).
- **Hook**: a small script the harness runs automatically before or after an agent's action.
- **Nudge**: a hook that refuses an action once with an explanation and lets an identical
  retry through.
- **Reviewer**: a separate agent, started without the author's context, that checks one
  thing. A **gate** is a point where a reviewer's pass is required before work goes on.
- **Verdict**: the one word a reviewer ends with; only the passing word lets work go on.
- **Coordinator**: the main agent in a session; it plans, chooses routes and runs long jobs.
- **Worker**: an agent on the cheaper model that carries out one brick and hands back.
- **Brick**: a unit of work small and well specified enough to hand to a worker.
