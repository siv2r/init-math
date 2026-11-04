# init-math — development guide

If you are helping someone install init-math, follow `SETUP-GUIDE.md` instead; this file is
for changing init-math itself.

This repository builds `init-math`, a skill + renderer that interviews a mathematician and
writes an AI-agent research project. Read this before changing anything.

## Layout

| Path | What |
|---|---|
| `skills/init-math/SKILL.md` | the interview procedure (the harness loads this) |
| `skills/init-math/scripts/renderer/` | stdlib-Python renderer: `tmpl.py` (template engine), `answers.py` (answers contract), `render.py` (module resolution + emission), `adapters/` (per-harness output) |
| `skills/init-math/scripts/templates/core/` | always-on core of every generated project |
| `skills/init-math/scripts/templates/modules/NN-<id>/` | one module per mechanism; format in [docs/AUTHORING-MODULES.md](docs/AUTHORING-MODULES.md) |
| `tests/` | unit, golden, leave-one-out and payload tests; `tests/behavior/` the behaviour scenarios, `tests/bench/` the reviewer bench, `tests/probe/` the live harness probe |
| `docs/` | human-readable documentation; [docs/README.md](docs/README.md) is the index |

## Rules

- **Generated projects must be independent of their origin.** Nothing emitted may name the
  practice the templates were distilled from, its tools, its people or any local path. The
  independence test enforces the obvious cases; judgment covers the rest.
- **Deterministic output.** Same answers + templates → byte-identical project. No clock
  reads, no randomness, sorted walks.
- **Stdlib Python ≥ 3.11** for the renderer and for everything emitted.
- Run `bin/test` before every commit; keep it green.
- **A reviewer change is measured.** A change to a reviewer's prompt, report form or brief
  ships with a reviewer-bench run (`tests/bench/`) before and after, reported with its minimum
  detectable effect; what the bench does not cover ships through behaviour scenarios.
- Commit locally with an explicit path list. Do not create a remote or push without the
  owner's go-ahead.
