#!/usr/bin/env python3
"""Check one or more modules IN ISOLATION: core + the named modules (+ their declared
dependencies), rendered for both golden fixtures. Safe to run while other modules are
half-written, because it ignores every module it was not asked about.

    python3 tools/check-module.py conjectures questions
    python3 tools/check-module.py --all          # every module (same as the test suite)

Checks: render succeeds for each fixture (Claude and Codex), output is deterministic,
no unrendered template tags, no dangling relative links, independence words absent,
AGENTS.md under budget, the rendered bin/selftest passes, and switching each named module
off (leave-one-out) still renders cleanly.
"""
from __future__ import annotations

import filecmp
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/init-math/scripts"))
sys.dont_write_bytecode = True
from renderer import render  # noqa: E402
from renderer.answers import load_answers, validate  # noqa: E402

FIX = ROOT / "tests/fixtures"
FIXTURES = ("answers-claude-lean.json", "answers-codex-theory.json")
FORBIDDEN = re.compile(r"/Users/|/home/")
TAG = re.compile(r"\{\{[#/!]?[a-zA-Z_.@!]")
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
BUDGET = 20 * 1024

problems: list[str] = []


def tree(d: Path) -> list[str]:
    return sorted(p.relative_to(d).as_posix() for p in d.rglob("*") if p.is_file())


def module_dir(mid: str) -> Path:
    for d in (render.TEMPLATES_DIR / "modules").iterdir():
        if d.is_dir() and re.sub(r"^\d+-", "", d.name) == mid:
            return d
    raise SystemExit(f"no module directory for id '{mid}' (expected modules/NN-{mid})")


def build_templates(ids: list[str], dest: Path) -> list[str]:
    shutil.copytree(render.TEMPLATES_DIR / "core", dest / "core",
                    ignore=shutil.ignore_patterns("__pycache__"))
    (dest / "modules").mkdir()
    todo, done = list(ids), []
    while todo:
        mid = todo.pop()
        if mid in done or mid == "core":
            continue
        d = module_dir(mid)
        shutil.copytree(d, dest / "modules" / d.name, ignore=shutil.ignore_patterns("__pycache__"))
        done.append(mid)
        import tomllib
        with open(d / "module.toml", "rb") as f:
            todo += tomllib.load(f).get("depends", [])
    return done


def answers(fx: str, mods: list, disable: list[str]) -> dict:
    a = json.loads((FIX / fx).read_text())
    a["modules"]["disable"] = disable
    a["modules"]["enable"] = [m.id for m in mods if m.status == "opt-in" and m.id not in disable]
    return validate(a)


def check_output(out: Path, label: str) -> None:
    for rel in tree(out):
        text = (out / rel).read_text(encoding="utf-8", errors="replace")
        if TAG.search(text):
            problems.append(f"{label}: unrendered template tag in {rel}")
        m = FORBIDDEN.search(text)
        if m and not rel.startswith("docs/init-"):
            problems.append(f"{label}: forbidden word '{m.group(0)}' in {rel}")
        if rel.endswith(".md"):
            for t in LINK.findall(text):
                if re.match(r"^[a-z]+:|^#", t):
                    continue
                if not (out / rel).parent.joinpath(t.split("#")[0]).resolve().exists():
                    problems.append(f"{label}: dangling link {rel} -> {t}")
    # Every hook script shipped must be registered with the harness (else it is dead weight).
    cfg = next((out / c for c in (".claude/settings.json", ".codex/hooks.json") if (out / c).exists()), None)
    reg = cfg.read_text() if cfg else ""
    for h in sorted((out / "hooks").glob("*.py")) if (out / "hooks").is_dir() else []:
        if not h.name.startswith("_") and f"hooks/{h.name}" not in reg:
            problems.append(f"{label}: hooks/{h.name} is emitted but not registered"
                            " (put a one-harness hook under files/@<harness>/)")
    n = len((out / "AGENTS.md").read_bytes())
    if n > BUDGET:
        problems.append(f"{label}: AGENTS.md is {n} bytes (> {BUDGET})")
    r = subprocess.run([sys.executable, str(out / "bin/selftest"), "-v"], capture_output=True,
                       text=True, timeout=600)
    if r.returncode != 0:
        problems.append(f"{label}: bin/selftest failed:\n{r.stdout}{r.stderr}")


def main() -> int:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 2
    if args == ["--all"]:
        args = sorted(re.sub(r"^\d+-", "", d.name) for d in (render.TEMPLATES_DIR / "modules").iterdir()
                      if d.is_dir())
    with tempfile.TemporaryDirectory(prefix="check-module ") as tmp:
        tmp = Path(tmp)
        ids = build_templates(args, tmp / "t")
        mods = render.load_modules(tmp / "t")
        for fx in FIXTURES:
            for run in ("a", "b"):
                out = tmp / f"{fx}-{run}"
                try:
                    render.render_project(answers(fx, mods, []), out, tmp / "t")
                except Exception as e:  # report, don't crash
                    problems.append(f"{fx}: render failed: {e}")
                    break
            else:
                a, b = tmp / f"{fx}-a", tmp / f"{fx}-b"
                _, mism, err = filecmp.cmpfiles(a, b, tree(a), shallow=False)
                if mism or err or tree(a) != tree(b):
                    problems.append(f"{fx}: output not deterministic: {mism + err}")
                check_output(a, fx)
                rep = json.loads((a / "docs/init-report.json").read_text())
                print(f"{fx}: on={rep['modules_on']} skipped_hooks={len(rep['hooks_skipped'])}")
        for mid in ids:
            m = next(x for x in mods if x.id == mid)
            if m.core or m.status == "deferred":
                continue
            off = sorted({mid} | {d.id for d in mods if mid in d.depends})
            out = tmp / f"loo-{mid}"
            try:
                render.render_project(answers(FIXTURES[0], mods, off), out, tmp / "t")
                check_output(out, f"without {off}")
            except Exception as e:
                problems.append(f"without {off}: render failed: {e}")
    for p in problems:
        print("FAIL", p)
    print(f"\n{len(problems)} problem(s) for modules {ids}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
