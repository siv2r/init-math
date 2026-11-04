# Interview question bank

The interview asks only what the person alone can tell you: what they work on, the
questions they want answered, and anything they already believe or build on. Everything
else you detect or default, and show once in the read-back, where they can change it. A
default that turns out wrong is fixed later by the project's reflection loop or by asking
any agent; that costs far less than asking a newcomer about details they cannot judge yet.

So the conversation has four exchanges:

1. **What they work on** (one open question) — section 1.
2. **Their questions**, sharpened, and which one to start on — section 2.
3. **Anything they already believe or build on** (optional) — section 3.
4. **Read-back and go** — section 5.

Section 4 lists what you fill without asking. Keys in **bold** are required.

## 1. What they work on

Ask one open question, for example: "In a few sentences: what area is this in, what do you
want to find out, and how do you usually work: on paper, by computing examples (with which
program), or in a proof assistant like Lean?"

From the answer fill these yourself, and ask a short follow-up only if the answer leaves
one of them genuinely open:

| Key | How |
|---|---|
| **`project.field`** | Their field in their words: "number theory", "extremal combinatorics". |
| `project.subarea` | One line on the topic, if they gave one. |
| **`project.research_kinds`** | Subset of `theory`, `experiment`, `formalization`: paper proofs, computing examples, Lean. If the answer does not say whether they compute or formalize, ask that one thing. |
| `stack.tools` | The programs they compute with, e.g. `["PARI/GP", "Python"]`. Run `command -v gp magma sage gap M2 maple mathematica python3 julia lean lake` to see what is installed, but **a program missing here does not override what they say they use** (Magma is often only on a server); record it anyway. |
| `stack.run_cmd` | How one experiment script runs, with `{driver}` for the file: `gp -q {driver}`, `python3 {driver}`, `magma -b {driver}`, `sage {driver}`. Derive it; never ask for a command. One per project: a second tool's command goes in `research_commands`, and a script can call it. |
| `stack.driver` | Leave out: derived from `run_cmd` (`gp` → `driver.gp`, `magma` → `driver.m`, `python3` → `driver.py`). |
| `stack.research_commands` | The first word of `run_cmd` plus each other tool's command, e.g. `["gp", "python3"]`. The failure hook watches only these. |
| **`stack.proof_assistant`** | `lean` if they formalize in Lean, else `none`. |

Never ask for a regular expression, a command template or an exit code.

## 2. Their questions

### Research questions (`seeds.questions`, 1–5)

The one place worth some back-and-forth: the agents work on these questions and nothing
else. A good question is ONE sentence with an answer they do not have yet.

- Draft the sentence(s) from what they said in section 1, and for each propose 1–4
  **answer shapes**: concrete forms the answer could take ("a finite list of exceptions",
  "a criterion in terms of the level", "no: an explicit counterexample"). Show the draft and
  ask: "Is this what you want to know? Change anything." Answer shapes are required (at
  least one per question; `--check-answers` refuses otherwise); for a yes/no question
  "yes: a proof" and "no: a counterexample" are fine.
- If what they gave is a topic ("modular forms mod p"), ask once what they would like to
  know about it that they don't, then offer 2–3 phrasings built ONLY from their words.
  After two tries, keep their own wording with `why: "needs sharpening (owner's words)"`
  and say so; the agents can help sharpen it later.
- `why`: one line on why it matters, from what they said; leave it empty rather than ask.
- If you suspect a question is already known or trivial, say so in a sentence and ask for a
  source or a variant. Flag only; never invent content, and never refuse it.
- `examples`: if they mention examples while talking about a question (the simplest case,
  the most structured one, one that breaks a naive guess, one outside the class they
  study), record them under `simplest`, `structured`, `breakers`, `outside`. Do not ask for
  them; the agents fill the question's examples bank as they work.

### Which question to start on (`seeds.active_question`)

Agents work only on *active* questions, and only the owner activates one. In the same
message as the draft, ask which ONE to start on, recommending the most ready one in a
sentence (one question first gives a focused first round; more can be activated any time).
With a single question, ask "Shall the agents start on it?". Record its id (`Q001`, … in
order); it is written `status: active` with `activated-by:` their name, and the rest
`proposed`. "Not yet" is a valid answer: leave it empty and say that the agents will only
read and propose until they activate one. Never pick for them. One active question is the
right start even for someone who works on many at once: agents may open *satellite*
questions around it (smaller, independently interesting ones whose answers feed it) and work
them without a new activation (section 4).

## 3. Anything they already believe or build on (optional)

Ask once, and make skipping easy: "Is there anything you already believe about this that the
agents should test, or papers it builds on? Skipping is fine: the agents' first job is a
literature pass anyway."

### Seed conjectures (`seeds.conjectures`)

A statement they believe, scoped to a named family ("for all primes 13 ≤ l ≤ 31"). You fill:
- `questions`: the question id(s) it bears on;
- `tie`: one sentence on what a verdict would change in that question's answer, naming an
  answer shape by number (`A1`, `A2`, … in the order of the shapes). Draft it yourself from
  the answer shapes and show it in the read-back; never copy a placeholder ("tbd",
  "whatever you recommend") through. `--check-answers` warns on a tie under 5 words, one
  matching `whatever|tbd|todo|recommend|n/a`, and one naming a shape by a letter or an
  `A<n>` its question does not have;
- `family`: the scope.

If one fits none of their questions, ask whether to add a question for it. If it is a known
theorem, put the paper under sources with a `why:` naming the result instead.

### Anchor sources (`seeds.sources`)

Papers, theses or notes the project builds on: `cite` (required), `locator` (DOI, arXiv id,
URL or file path), `why`. They land in the literature inbox, to be read and summarized
before experiments start. If they name a paper only vaguely ("that Ahlgren–Ono stuff"),
record their words as `cite` with `why: "to be identified"`; never fill in a title or
locator you guessed.

## 4. What you fill without asking

Each of these goes in the read-back as one plain line, so the person can change it there.

| Key | Default |
|---|---|
| **`project.name`** | A short name from the topic of their first question; `project.slug` is derived. |
| **`project.owner`** | `git config user.name` (setup set it). If empty, ask for their name as it should appear in the project's history. |
| **`harness`** | The agent program running this interview: `claude` (Claude Code) or `codex`. |
| `tiers.strong`, `tiers.worker` | Leave empty for the defaults: Claude `opus`/`sonnet`; Codex `gpt-6-astra`/`gpt-6-luna` (as of 2026-10-22; Astra = frontier, Luna = fast and cheap, for the execution workers). Codex model names cannot be detected, so on Codex the read-back names them and says "if your account offers other models, say which". If they lack the strong model, use their best model for BOTH tiers: a reviewer must never be weaker than the author. |
| `codex.git_commits` | Codex only. Leave the default `true`: agents save their work into the project's history on their own (the commit gate still applies). Mention it in the read-back in those words. |
| `stack.failure_signatures` | **Leave the key out.** The project then gets the standard patterns for the tools in `research_commands` (out of memory, stack overflow, and the error lines of PARI/GP, Magma, GAP and Macaulay2); a command that exits with an error is caught without one. The reflection loop adds patterns when a run fails in a way they miss. Do not ask about error messages. Write the key only when the person volunteers a message, e.g. "my program prints `did not converge` and keeps going" (then include the defaults you still want: an explicit list replaces them). |
| `stack.hygiene_rules` | Leave out. Rules for write-up wording are added later, when the owner corrects the same wording twice. Record one only if the person volunteers it. |
| `stack.lake_path` | If they use Lean, look for `lakefile.lean` or `lakefile.toml` with `lean-toolchain` in the current directory, its parents and the target's siblings; propose any hit in the read-back (absolute path). Otherwise leave empty: the project prints the setup commands. |
| `modules` | The preset for their kind of work (section "Modules" below); no questions. |
| `experiments.limits` | The defaults, lowered to fit this computer (section "Run limits" below). |
| `exposition.prior_work`, `exposition.model_text` | Leave out unless they volunteer them. The project's `getting-started` skill offers both later, when write-ups are near. |
| `field_profile.small_cases_informative` | Inferred from section 1; default `true`. `false` when what they study only shows up at large parameters or beyond computable range (an asymptotic phenomenon, an estimate that bites late); agents then start with the step that would falsify or narrow a plan, not with the smallest case. Read back: "Small cases are treated as informative here; say if they mostly are not." |
| `field_profile.construction` | Inferred; default `false`. `true` when the work is mostly building objects that must meet criteria (protocols, constructions, counterexamples, configurations) rather than proving statements about given ones; construction moves then come first in the agents' menu. Read back in one line. |
| `questions.satellites`, `questions.satellites_max` | Default `true` and `0` (no limit): agents may open satellite questions around an active one and work them without asking. Read back: "Agents may open smaller satellite questions around an active one and work them; say if you want that off, or capped at a number." Record their answer; do not argue for a number. |
| `arguments.labels` | Inferred from the field; leave out to take the defaults (`heuristic`, `moral`, `conditional`, `model-only`, `analogy`). Add a field's own kinds of informal argument, e.g. for cryptography the idealized models it uses are already covered by `model-only (<model>)`, but a field with its own standard heuristic adds a word for it. Read back only if you added one. |
| `seeds.moves` | Only when they volunteer a move they habitually use when stuck ("I always map where the known attacks break first"): one entry each, `id` (a short kebab-case name), `says` (the move in one line), `when`, `example`. It joins the agents' move menu. Do not ask for moves. |

### Modules

Run `python3 SCRIPTS/init_project.py --list-modules` to see the ids, but do not walk the
person through them: most are discipline the agents follow. Choose:

- **Theory only** (no computation, no Lean): preset `theory-only` (`modules.preset`), which
  switches off experiments, the results cache, Lean and long runs (launch).
- **Computation**: keep experiments and the cache on (the default).
- **Lean**: on automatically when `stack.proof_assistant` is `lean`.
- **Program review**: on (an agent offers one every few weeks and when the direction changes). **Usage statistics** (token counts only, never text, in
  a log committed with the project): on.

Record switches in `modules.disable` / `modules.enable`. `--check-answers` reports why each
off module is off; turning off a module others need is an error there. In the read-back say
in one line what is on in plain words ("experiments with a time and memory watchdog, a cache
of computed results, Lean support"), and that any module can be added later by asking an
agent (`docs/OWNER.md`, "Turning a module on later").

### Run limits (`experiments.limits`; only with the experiments module)

Every experiment run goes through a watchdog that stops it when it runs too long or uses too
much memory. The defaults: smoke (a quick check) 2 minutes and 2 GB; full 2 hours and 8 GB;
deep (started only on purpose) 12 hours and 16 GB.

Check this computer's memory (macOS `sysctl -n hw.memsize`, bytes; Linux the `MemTotal`
line of `/proc/meminfo`, kB). Where a default memory limit is more than half of it, use half
the memory (rounded down to whole GB) for that run instead, and record only those changes:
`experiments.limits.<run>.mem_mb` in megabytes (1 GB = 1000 MB), e.g.
`{"limits": {"deep": {"mem_mb": 8000}}}`. Values must be positive. Otherwise leave
`experiments` out. In the read-back, one line: "Experiments are stopped after 2 hours / 8 GB
(longer runs only when you ask); change it any time in `project.toml`." (with the full run's
memory limit as recorded, if you lowered it). On Codex on macOS,
add that Codex's sandbox there lets the watchdog enforce only the time limit.

## 5. Read-back and go

One short message:

- **What will be created and where:** the project name and the folder as a full absolute
  path, saying it is a new folder inside the current one. If the current directory is
  empty, the person probably made it for this project: offer to create the project right
  there instead (SKILL.md step 3).
- **Their questions** as written, with the answer shapes, which one starts active, and any
  conjectures (with the ties you drafted) and sources.
- **Settings chosen for them**, one plain line each, only those that apply: agent program and
  models, what kind of work it is set up for (the modules line), the run limits line, any
  Lean project found, and on Codex the commit line. End with: "All of these can be changed
  later by asking an agent; say now if anything is wrong." The field-profile and satellite
  lines go here too, and one line per volunteered move.
- Then ask: "Shall I create it?"

The modules line names what the project is set up for; do not explain how any part works
(modules, reviewers, hooks, the reflection loop). The project's `getting-started` skill does
that in the first session.

## answers.json shape

```json
{
  "project": {"name": "", "owner": "", "field": "", "subarea": "",
              "research_kinds": ["theory"], "init_date": "YYYY-MM-DD"},
  "harness": "claude",
  "tiers": {"strong": "", "worker": ""},
  "codex": {"git_commits": true},
  "stack": {"tools": [], "run_cmd": "", "research_commands": [],
            "proof_assistant": "none", "lake_path": ""},
  "modules": {"disable": [], "enable": [], "preset": ""},
  "experiments": {"limits": {}},
  "field_profile": {"small_cases_informative": true, "construction": false},
  "questions": {"satellites": true, "satellites_max": 0},
  "arguments": {"labels": []},
  "seeds": {
    "questions": [{"sentence": "", "answer_shapes": [""], "why": "",
                   "examples": {"simplest": "", "structured": "", "breakers": "", "outside": ""}}],
    "active_question": "",
    "conjectures": [{"statement": "", "questions": ["Q001"], "tie": "", "family": ""}],
    "sources": [{"cite": "", "locator": "", "why": ""}],
    "moves": []
  },
  "exposition": {"prior_work": [], "model_text": ""}
}
```

`sentence` and at least one non-empty `answer_shapes` entry per question are REQUIRED (the
blanks above must be filled). Leaving out `stack.failure_signatures` gives the standard
patterns; `"failure_signatures": [{"label": "", "regex": ""}]` (a list) replaces them, and
`[]` means none. `stack.hygiene_rules` is a list of strings: `re:<regex> :: <message>` for a
mechanical scan (case-sensitive; start with `(?i)` otherwise), or a plain sentence for the
reviewer's checklist; backslashes JSON-escaped (`\\b`). A realistic filled seed:

```json
{"questions": [{"sentence": "For which primes l is the sequence a(n) mod l periodic?",
                "answer_shapes": ["a finite list of exceptional primes",
                                  "a criterion in terms of l mod 12",
                                  "no: an explicit counterexample prime"],
                "why": "Periodicity would give a finite check for every congruence."}],
 "conjectures": [{"statement": "a(n) mod l is periodic for every prime 5 <= l <= 101.",
                  "questions": ["Q001"],
                  "tie": "If true, no prime from 5 to 101 is an exception, which supports A1. If refuted, the counterexample prime is an exception any answer must include.",
                  "family": "primes 5 <= l <= 101"}]}
```

A volunteered move is `{"id": "map-attack-boundary", "says": "...", "when": "...", "example":
"...", "construction": true}` in `seeds.moves` (`construction` only for a construction move).
Omit `field_profile` and `questions` when you inferred nothing different from the defaults.

Leave `tiers` values empty (or omit `tiers`) to take the defaults. An empty
`experiments.limits` (or no `experiments`) means the default run limits; an empty
`active_question` means every question starts `proposed`; an empty `exposition` leaves both
fill-in lines in `docs/discipline/exposition.md`. Question and conjecture ids are assigned in
order (`Q001`, `C001`, …) unless given.
