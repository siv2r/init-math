# .gates/

Evidence for the commit gate and the review history. The files are append-only JSON lines, committed, and
union-merged across branches (rows may repeat or be out of order; readers match them as a
set and de-duplicate by `id`). Do not edit them by hand.

- `dispatches.jsonl`: written by `hooks/gate-dispatch-log.py` whenever a reviewer agent is
  dispatched: `{id, ts, gate, path, blob, via}`, one row per file the brief names. `blob`
  is the git blob id of the file's content at that moment.
- `stamps.jsonl`: written by `bin/gate-stamp`: `{id, ts, gate, path, blob, verdict, pass,
  kind, excerpt[, caveat_ok]}`, one row per verdict, passing or not. Only a passing row
  satisfies the commit gate; the others are the review history (`bin/gate-stamp --list`).
- `cycles.jsonl`: written by `bin/gate-stamp --new-cycle`: `{id, ts, path, why}`, where a
  file's review count starts again (the re-review limit, `docs/discipline/gate-chain.md`).

How the pre-commit check uses them: `docs/discipline/commit-gate.md`.
