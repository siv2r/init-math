#!/usr/bin/env python3
"""file-home nudge (PreToolUse, edit): a NEW file under notes/ probably belongs elsewhere,
and a NEW manuscript in a scratch/ folder would be in no commit.

notes/ holds a few standing notes on how the project works. Working files dropped there
pile up into a flat folder nobody can navigate (a long trial run left over a thousand). So
the first time an agent creates a given file under notes/, this refuses once and says where
working files go: the line of work's folder work/<slug>/, or its git-ignored scratch/.
Likewise the first time an agent creates a .tex or .bib file in a scratch/ folder, which
git ignores (a trial run kept every paper draft there, in no commit). Re-issuing the same
edit proceeds. Edits to existing files are never touched.
Bypass: HOOKS_QUIET=1. See docs/discipline/work-folders.md.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _payload  # noqa: E402

HOOK = "file-home-nudge"


def main(ev):
    if ev.action != "edit":
        return
    root = Path(ev.root).resolve()
    notes = root / "notes"
    new, drafts = [], []
    for p in ev.paths:
        f = Path(p) if Path(p).is_absolute() else Path(ev.cwd or ev.root) / p
        f = f.resolve()
        if f.exists() or not f.is_relative_to(root):
            continue
        rel = f.relative_to(root)
        if f.is_relative_to(notes):
            new.append(rel.as_posix())
        elif "scratch" in rel.parts and f.suffix in (".tex", ".bib"):
            drafts.append(rel.as_posix())
    if drafts:
        _payload.nudge_once(
            ev, HOOK, "scratch|" + "|".join(sorted(drafts)),
            f"New manuscript in a scratch/ folder: {', '.join(drafts)}. git ignores scratch/, so "
            "this file would be in no commit and could be lost. A manuscript belongs in "
            "writeups/ or in its line of work's folder, work/<slug>/. If it really is "
            "throwaway, re-issue the edit. See docs/discipline/work-folders.md.")
    if not new:
        return
    _payload.nudge_once(
        ev, HOOK, "|".join(sorted(new)),
        f"New file under notes/: {', '.join(new)}. notes/ is for standing notes on how the "
        "project works (the workflow journal and the like). A working document, proof in "
        "progress, plan or check belongs in its line of work's folder, work/<slug>/ (start one "
        "by copying work/TEMPLATE/ and adding a row to work/_index.md); a brief or throwaway "
        "file in work/<slug>/scratch/, which git ignores. If this really is a "
        "standing note, re-issue the edit. See docs/discipline/work-folders.md.")


if __name__ == "__main__":
    _payload.run(main, HOOK)
