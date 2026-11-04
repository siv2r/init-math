#!/usr/bin/env python3
"""Render a fixture project plus the test-only probe module, for a live harness probe.

    python3 tests/probe/make-probe-project.py claude|codex OUT_DIR [--core-only]

--core-only renders core + the probe module only (useful while modules are being written).
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills/init-math/scripts"))
from renderer import render  # noqa: E402
from renderer.answers import load_answers  # noqa: E402

FIXTURE = {"claude": "answers-claude-lean.json", "codex": "answers-codex-theory.json"}


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--core-only"]
    core_only = len(args) != len(sys.argv) - 1
    if len(args) != 2 or args[0] not in FIXTURE:
        print(__doc__, file=sys.stderr)
        return 2
    harness, out = args[0], Path(args[1])
    with tempfile.TemporaryDirectory() as d:
        t = Path(d) / "templates"
        shutil.copytree(render.TEMPLATES_DIR, t, ignore=shutil.ignore_patterns("__pycache__"))
        if core_only:
            for m in (t / "modules").iterdir():
                shutil.rmtree(m)
        shutil.copytree(ROOT / "tests/fixtures/probe-module", t / "modules/99-probe")
        render.CATALOG["probe"] = 99
        rep = render.render_project(load_answers(ROOT / "tests/fixtures" / FIXTURE[harness]), out, t)
    subprocess.run(["git", "init", "-q"], cwd=out, check=True)
    print(f"rendered {harness} probe project at {out}; modules: {rep['modules_on']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
