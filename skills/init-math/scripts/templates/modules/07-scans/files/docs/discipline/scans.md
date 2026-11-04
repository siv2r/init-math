# Mechanical scans

Eight small scripts in `bin/`, each catching one kind of defect a reviewer or a reader would
otherwise spend effort on. They cost seconds and use no model. Every one has `--help` and a
`--selftest`. None of them replaces a reviewer: they remove the noise so the reviewer can
spend its attention on substance.

| Script | Run it | It catches | Exit |
|---|---|---|---|
| `hedge-scan` | on a draft, before the claim-auditor | strength words ("proved", "always", "for all"), headlines and summary lines first | 0 |
| `hedge-scan --diff` | on staged changes, before committing | a hedge ("heuristically", an argued label) that the change removes; a plain `hedge-scan` cannot see what was removed | 0 |
| `define-check` | on a document, before a reviewer or reader | invented codes (`F12`, `SB2`), made-up multi-letter names with subscripts (like `n_max` or `dim_K`), and acronyms, when neither the document nor GLOSSARY.md defines them | 0 (`--strict`: 1) |
| `math-hygiene-scan` | on a proof-bearing document, before the proof-referee | setting hygiene, notation clashes, double end-of-proof marks, uncited "classical" claims, this field's rules | 0 (`--strict`: 1) |
| `stale-status-scan` | after a fix that changed a claim, before re-dispatching a reviewer | the old wording surviving elsewhere. Run `bin/stale-status-scan --phrase "<old>" <files>`; add one `--phrase` per changed wording and list the document plus every file that may repeat the claim | 0 |
| `scope-estimate-scan` | on a handoff, plan or write-up, before committing | difficulty and absence estimates ("multi-week", "from scratch", "out of scope") | 0 |
| `link-check` | before committing a document with references | relative links and conjecture or question wikilinks that point nowhere | 1 on a problem |
| `orphan-check` | before committing a new artifact | artifacts no index names | 1 on a problem |
| `backlink-check` | before committing a known result | known results whose conjecture never links back | 1 on a problem |

## Why each one exists

- **hedge-scan.** The body of a finding is usually honest; the headline over-reads it,
  because headlines are written last and read alone. A reviewer then fails the document on
  the header. Match each headline to the most hedged body claim it summarizes before the
  review. Anti-scope: a strength word in the body that its evidence supports is fine.
- **define-check.** A term you coined is obvious to you and opaque to everyone else, and
  that is the most common complaint a reader has about agent-written text. The script only
  sees codes and notation; invented plain words ("the lo branch", "the core") need a cold
  read by a fresh-context reader.
- **math-hygiene-scan.** The cheapest proof defects are mechanical, and a referee who
  spends its effort on them misses the load-bearing step. Field rules live in
  `project.toml` `[hygiene] rules`: a plain sentence is shown as a checklist item, and an
  entry `re:<regex> :: <message>` is applied to every line. Add a rule when the same
  field-specific slip recurs.
- **stale-status-scan.** A corrected claim usually also lives in a summary, an index row,
  a docstring. Spot edits leave contradictions, and each costs a review round. It matches
  the literal phrase only, so it misses a reworded restatement. It prints two lists: the
  hits with no correction marker nearby (places you forgot to update), and the `~~` bucket,
  the hits that sit next to a correction marker (a ~~strikethrough~~, REFUTED, SUPERSEDED
  and the like). Read the `~~` bucket too: a stale claim can survive inside the correction
  that supersedes it.
- **scope-estimate-scan.** "This needs weeks" or "this is not in the library" can stop
  work that would have taken an hour. Before writing such an estimate, run one search or
  one reduction attempt; if the estimate is inherited, say where it came from. The scan
  over-reports by design; dismiss a hit that is backed.
- **link-check, orphan-check, backlink-check.** The project's records are only as useful as
  they are findable. A broken link, an artifact no index names, and a one-way link from the
  literature to a conjecture all make work invisible to the next agent. Register the index
  row in the same commit as the artifact.

## Hooks

Three nudges fire at `git commit` (define-check on the shared index files, orphan-check,
backlink-check). The shared index files are the `_index.md` files at the top of the wiki and of each
store (questions, conjectures, known results, experiments; whichever this project has). Every agent reads them, so an undefined
code there costs the most. A definition goes in `GLOSSARY.md`, which the scan reads for
headwords. The nudge is not the script: the script `bin/define-check` only advises (exit 0),
but the commit hook refuses once per distinct set of problems, then lets an identical
retry through. A fourth nudge fires when a reviewer is re-dispatched on a file that changed
since its last review with no stale-status-scan since the change. Each of the four refuses
once per distinct set of problems and lets an identical retry through. Bypasses: `DEFINE_CHECK_OK=1`,
`ORPHAN_CHECK_OK=1`, `BACKLINK_CHECK_OK=1`, `STALE_SCAN_OK=1`, or `HOOKS_QUIET=1` for all.
