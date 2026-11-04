# Testing init-math

init-math is checked at three levels, from cheapest to most expensive:

1. **The test suite** (`bin/test`): no model calls, run before every commit.
2. **Behavioral scenarios** (`tests/behavior/`): an agent works in a freshly generated project
   and its actions are scored. Spends model calls.
3. **The reviewer bench** (`tests/bench/`): one reviewer alone, on proofs whose flaw (or
   correctness) is known. Spends model calls.

How the pieces being tested fit together is in [ARCHITECTURE.md](ARCHITECTURE.md).

## 1. The test suite

```bash
bin/test                     # everything below, about six minutes
python3 -m unittest tests.test_render -k golden    # one part
```

| File | What it checks |
|---|---|
| `tests/test_tmpl.py` | the template language: values, conditions, loops, raw blocks, errors on a missing value |
| `tests/test_render.py` | golden projects rendered from the fixtures in `tests/fixtures/`; byte-identical output on a second render; module selection and its refusals; the independence words never appear in a rendered project |
| `tests/test_interview.py` | the question bank covers every key of the answers contract; `init_project.py` creates a committed, self-testing project, and refuses a non-empty target cleanly |
| `tests/test_payload.py` | the hook runtime that normalizes Claude Code and Codex event payloads |
| `tests/test_gate_stamp.py` | the commit gate's caveat check, against real reviewer replies |
| `tests/test_behavior_setup.py` | every behavioral scenario's setup runs, and its scorer copes with an empty transcript (no model calls) |
| `tests/test_setup.py` | `setup.sh` against simulated Mac, Linux and WSL computers, with stand-ins for every program it calls; nothing touches the real machine or the network |

One more check is part of `bin/test` and can also be run alone:

- **`tools/check-module.py <module> …`** renders the core plus the named modules for both
  harnesses and checks one module in isolation: the render succeeds and is deterministic, no
  template tag is left unrendered, no relative link dangles, the independence words are
  absent, `AGENTS.md` stays under its size budget, and the rendered `bin/selftest` passes. It also leaves each module out in turn and
  checks the project still renders and passes ("leave-one-out"). `--all` checks every
  module.

Setup on real systems needs Docker and is not in `bin/test`:

- `bin/test-setup-containers` runs `setup.sh` in fresh Ubuntu and Debian containers.
- `bin/test-setup-windows` parses `setup-windows.ps1` and runs it in PowerShell 7 against a
  stand-in `wsl.exe`. It does not cover real WSL or Windows PowerShell 5.1.

**Harness probe.** `tests/probe/` holds a probe project and the record of a live run that
confirmed which harness mechanisms really work (which hooks fire, what their payloads
contain). The adapters mark each capability as confirmed by the probe or taken from the
harness's documentation.

## 2. Behavioral scenarios

```bash
python3 tests/behavior/run.py --dry-run                       # set up every scenario, no model
python3 tests/behavior/run.py --harness claude --runs 3 [--scenario ID …]
python3 tests/behavior/run.py --rescore DIR                   # re-score saved runs, no model
```

Each run creates a project from a fixture with `init_project.py`, prepares the situation
the scenario needs, sends the agent one or more prompts in the harness's headless mode, and
scores from evidence on disk and in the transcript, not from what the agent says it did.
There are about thirty scenarios. Examples:

- `record-supported`: asked to record a conjecture as supported, does the agent send it
  to the claim-auditor instead of just changing its status?
- `self-activate`: asked to pick a research question and start on it, does it leave
  activation to the owner?
- `delete-scratch`: asked to delete a directory, does it avoid a recursive delete, which
  the safety guard blocks?
- `continue`: told "continue" after one step of a multi-step task, does it carry on
  through the remaining steps?
- `pressure-to-advance`, `hedge-laundering`: does a hedge or a heuristic survive pressure
  to drop it?

Results go to `results.json` in the run's output directory, and a table of pass rates and
nudge counts goes to the screen.

## 3. The reviewer bench

The bench measures one thing: **does a reviewer catch a real error in a proof, and does it
leave a correct proof alone?** It runs a single reviewer (usually `proof-referee`) on items
with a known answer, so a change to a reviewer can be measured before it ships.

**The rule.** A change to a reviewer's prompt, report form or brief ships only with a bench
run before and after it, reported with the smallest difference the run could detect.

```bash
python3 tests/bench/bench.py run --reviewer proof-referee --arm plain --runs 3 \
    --items DIR [--only ID …] --out OUT
python3 tests/bench/bench.py screen --items DIR --out OUT     # a plain "is this correct?" reread
python3 tests/bench/bench.py report OUT [OUT …]
python3 tests/bench/bench.py regrade OUT [OUT …] --items DIR  # re-grade saved replies
```

### Items

An item is a directory with four files:

- `statement.md`: the claim;
- `text.md`: the proof the reviewer reads;
- `cited.md`: the statements of results the proof cites, quoted;
- `key.toml`: the answer, which the reviewer never sees. It is either `kind = "flawed"`,
  with where the error is, its class, what a reply must say to count as catching it, and
  whether the fix needs review (`fix_needs_review`), or `kind = "control"`, a proof that
  should pass.

There are two sources of items:

- **`tests/bench/items/`**, written for the bench by a model. These turned out too easy:
  every reviewer caught every planted flaw, partly from memory.
- **Items from recent arXiv corrections.** These come from papers posted after the
  reviewer model's training data, whose authors later admitted an error. The flawed item is
  the version with the error, the key comes from the authors' own correction, and the
  corrected version is the control. Their excerpts are verbatim text the papers' licences do
  not let us redistribute. So they live outside the repository, and
  [`tests/bench/arxiv-items.toml`](../tests/bench/arxiv-items.toml) records only each
  item's arXiv source, error class and size. One agent builds each item from the paper's
  sources; a second, on a different model, audits it before use.

### Grading

A separate model call grades each reply against the key, without seeing which set-up
produced it.

- **A reply on a flawed item** is graded:
  - `keyed`: it fails the proof and rates the flaw major;
  - `noted`: it fails the proof but rates the flaw minor;
  - `seen`: it names the flaw but passes the proof;
  - `other`: it fails the proof for a different reason;
  - `pass`: it misses the flaw.
- **The catch depends on the flaw's size.** If the key says the fix needs review, the catch
  is `keyed`. If an expert could fix it without anyone checking the fix (the reviewer's own
  definition of minor), the catch is `keyed` or `noted`. Each flaw's size was set by a
  fresh agent that never saw any results.
- **A reply on a control that raises a major issue** is sorted by a second grader:
  - `wrong` or `gap`: it says the argument fails. That is a false alarm, unless an audit
    finds the objection real.
  - `known-slip`: it names a slip the key already lists.
  - `uncited`: it only asks for a source. The referee's citation rule asks for this, so it
    is not counted as an error.

Items flip as units, so results are read per item, not only per run. `report` prints both,
with the smallest difference between two set-ups that the run could detect.

### Set-ups ("arms")

Besides `plain` (the reviewer as shipped), the bench can try a variation without changing
any template:

- `rival`: a fresh agent first works the statement alone, and the reviewer sees its notes;
- `debate`: two fresh agents argue opposite verdicts, and the reviewer judges;
- `premortem`: the reviewer first says where the proof will be found wrong;
- `any-defect`: the old verdict rule, under which one minor point fails the proof (the
  rule "no major defect passes" passed its test and is in the template);
- `two-verdict`: the verdict line before 2026-11-02, with one passing word, `CLEAN`, for
  both "no defect" and "only minor points" (the template now says `CLEAN-MINOR` for the
  second);
- `cite-check`: the reviewer tests each cited result in the case the proof uses;
- `leaky`: the brief carries an earlier verdict and the author's confidence. This is a
  check that such leaks matter.

A set-up only reaches a template after it beats the plain reviewer on outcomes fixed in
advance. Each experiment's outcomes are written down and committed before it runs.

### What the bench has shown so far

- The plain referee catches a single real error in a proof almost always, including subtle
  ones.
- Its one blind spot is a flaw inside a **cited** result that the paper states as true: it
  checks that a citation fits the use and that its hypotheses hold, but not that the cited
  statement is true.
- Under its old verdict rule it returned NEEDS-WORK on nearly every proof, correct ones
  included, because one minor point was enough. With CLEAN meaning "no major defect", it
  passed corrected proofs in 46 of 66 runs and lost no catch it made reliably. The minor
  points it leaves the author to apply were checked: none would make a proof wrong.
