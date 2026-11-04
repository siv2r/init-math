"""Render a research project from validated answers + module templates.

Usage:  python3 -m renderer --answers answers.json --out DIR [--templates DIR]

Deterministic: the same answers + templates give byte-identical output (sorted walks,
sorted JSON keys, no clock reads — the init date comes from the answers).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .adapters import ADAPTERS, Agent, HookReg, parse_frontmatter
from .adapters.base import AUTO_COMPACT_TOKENS
from .answers import AnswersError, load_answers, read_answers, stored_answers, validate
from .tmpl import TemplateError, render as render_tmpl

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
STATUSES = ("included", "opt-in", "deferred")

# Every module id the catalog defines, built or not. Templates may test
# `{{#if modules.<id>}}` for any of these (an unbuilt module reads as off); any other
# id is a typo and fails the render. Number = the module's place in the plan.
CATALOG = {
    "core": 0,
    "questions": 1, "conjectures": 2, "known_results": 3, "literature": 4,
    "gates": 5, "readers": 6, "scans": 7, "commit_gate": 8,
    "firsthand": 9, "experiments": 10, "cache": 11, "lean": 12,
    "tiers": 13, "stopping": 14, "launch": 15, "guard": 16,
    "reflect": 17, "retro": 18, "program_review": 19, "daemon": 20, "usage": 21,
    "attempts": 22,
}


# Module-root fragment file -> context key holding the rendered fragments (enabled modules,
# in order). Core templates splice them in with {{#each <key>}}{{.}}{{/each}}.
FRAGMENTS = {
    "AGENTS.fragment.md.tmpl": "module_sections",
    "glossary.fragment.md.tmpl": "glossary_sections",
    "project.fragment.toml.tmpl": "project_toml_sections",
    "gitignore.fragment.tmpl": "gitignore_sections",
}


class RenderError(Exception):
    pass


@dataclass
class Module:
    id: str
    dir: Path
    number: int
    title: str
    group: str
    status: str
    core: bool
    order: int
    summary: str
    depends: list[str] = field(default_factory=list)
    off_in_presets: list[str] = field(default_factory=list)
    requires: dict = field(default_factory=dict)
    hooks: list[dict] = field(default_factory=list)
    per_item: list[dict] = field(default_factory=list)
    allow_tools: list[str] = field(default_factory=list)
    allow_commands: list[str] = field(default_factory=list)


def load_modules(templates: Path) -> list[Module]:
    mods = []
    dirs = [templates / "core"] + sorted(p for p in (templates / "modules").iterdir() if p.is_dir())
    for d in dirs:
        mt = d / "module.toml"
        if not mt.exists():
            raise RenderError(f"{d}: missing module.toml")
        with open(mt, "rb") as f:
            t = tomllib.load(f)
        status = t.get("status", "included")
        if status not in STATUSES:
            raise RenderError(f"{mt}: status must be one of {STATUSES}")
        mods.append(Module(
            id=t["id"], dir=d, number=int(t.get("number", 0)), title=t["title"],
            group=t.get("group", ""), status=status, core=bool(t.get("core", False)),
            order=int(t.get("order", t.get("number", 0) * 10)), summary=t.get("summary", ""),
            depends=list(t.get("depends", [])), off_in_presets=list(t.get("off_in_presets", [])),
            requires=dict(t.get("requires", {})), hooks=list(t.get("hooks", [])),
            per_item=list(t.get("per_item", [])), allow_tools=list(t.get("allow_tools", [])),
            allow_commands=list(t.get("allow_commands", [])),
        ))
    ids = [m.id for m in mods]
    unknown = [i for i in ids if i not in CATALOG]
    if unknown:
        raise RenderError(f"module ids not in CATALOG (renderer/render.py): {unknown}")
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        raise RenderError(f"duplicate module ids: {sorted(dup)}")
    return mods


def resolve_enabled(mods: list[Module], ans: dict) -> dict[str, bool]:
    known = {m.id for m in mods}  # only BUILT modules can be switched
    sel = ans["modules"]
    for key in ("disable", "enable"):
        unknown = [x for x in sel[key] if x not in known]
        if unknown:
            raise RenderError(f"modules.{key}: unknown module ids {unknown}")
    on: dict[str, bool] = {}
    for m in mods:
        if m.core:
            if m.id in sel["disable"]:
                raise RenderError(f"module '{m.id}' is core and cannot be disabled")
            on[m.id] = True
            continue
        if m.status == "deferred":
            on[m.id] = False
            continue
        enabled = m.status == "included" or m.id in sel["enable"]
        if sel["preset"] and sel["preset"] in m.off_in_presets and m.id not in sel["enable"]:
            enabled = False
        if m.id in sel["disable"]:
            enabled = False
        pa = m.requires.get("proof_assistant")
        if pa and ans["stack"]["proof_assistant"] != pa:
            enabled = False
        on[m.id] = enabled
    for m in mods:
        if on[m.id]:
            missing = [d for d in m.depends if not on.get(d)]
            if missing:
                raise RenderError(f"module '{m.id}' needs {missing}, which are off")
    return on


def _toml_view(x):
    """The same tree with every string as a quoted TOML basic string. A JSON string literal
    is a valid TOML basic string, so answers containing quotes or backslashes stay intact."""
    if isinstance(x, dict):
        return {k: _toml_view(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_toml_view(v) for v in x]
    return json.dumps(x, ensure_ascii=False) if isinstance(x, str) else x


def build_context(ans: dict, mods: list[Module], on: dict[str, bool], adapter) -> dict:
    ctx = json.loads(json.dumps(ans))  # deep copy
    ctx["owner"] = ans["project"]["owner"]
    # For TOML files: write `key = {{toml.stack.run_cmd}}` (no quotes of your own).
    ctx["toml"] = _toml_view(ans)
    ctx["harness"] = {
        "name": adapter.name,
        "is_claude": adapter.name == "claude",
        "is_codex": adapter.name == "codex",
        "cap": dict(adapter.CAPS),
        "skills_dir": adapter.skills_dir,
        "hook_config": adapter.hook_config_path(),
        "context_files": list(adapter.context_files),
        "coordinator_file": adapter.coordinator_file,
        "auto_compact_tokens": AUTO_COMPACT_TOKENS,
    }
    # Which agents' rules a template is rendered for (AGENTS.md.tmpl and the AGENTS fragments):
    # `shared` is every agent's, `coordinator` the main session's. Without a coordinator file
    # both are on and AGENTS.md holds everything; with one, AGENTS.md is rendered with only
    # `shared` and the coordinator file with only `coordinator`.
    ctx["view"] = {"shared": True, "coordinator": not adapter.coordinator_file}
    ctx["modules"] = {i: False for i in CATALOG}
    ctx["modules"].update({m.id: on[m.id] for m in mods})
    kinds = ans["project"]["research_kinds"]
    ctx["has"] = {
        "computation": "experiment" in kinds,
        "formalization": "formalization" in kinds,
        "lean": ans["stack"]["proof_assistant"] == "lean",
        "failure_signatures": bool(ans["stack"]["failure_signatures"]),
        "example_driver": ans["stack"]["driver"] == "driver.py",
    }
    ctx["module_list"] = [
        {"id": m.id, "number": m.number, "title": m.title, "group": m.group,
         "summary": m.summary, "core": m.core}
        for m in sorted(mods, key=lambda m: m.order) if on[m.id]
    ]
    return ctx


def _render_text(src: str, ctx: dict, where: str) -> str:
    try:
        return render_tmpl(src, ctx)
    except TemplateError as e:
        raise RenderError(f"{where}: {e}") from None


class Emitter:
    def __init__(self, out: Path):
        self.out = out
        self.owner: dict[str, str] = {}

    def write(self, rel: str, data: str | bytes, origin: str, mode: int | None = None):
        rel = rel.replace(os.sep, "/")
        if rel in self.owner:
            raise RenderError(f"{rel}: written by both {self.owner[rel]} and {origin}")
        self.owner[rel] = origin
        p = self.out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, str):
            p.write_text(data, encoding="utf-8")
        else:
            p.write_bytes(data)
        if mode is not None:
            p.chmod(mode)


_SKIP_NAMES = {".DS_Store"}
_SKIP_SUFFIXES = {".pyc", ".pyo"}


def _walk(d: Path):
    for p in sorted(d.rglob("*")):
        if p.is_file() and p.name not in _SKIP_NAMES and p.suffix not in _SKIP_SUFFIXES \
                and "__pycache__" not in p.parts:
            yield p


def _emit_tree(src_dir: Path, dest_prefix: str, em: Emitter, ctx: dict, origin: str, harness: str):
    if not src_dir.is_dir():
        return
    for p in _walk(src_dir):
        rel = p.relative_to(src_dir).as_posix()
        first, _, rest = rel.partition("/")
        if first.startswith("@"):
            if first[1:] != harness:
                continue
            rel = rest
        mode = stat.S_IMODE(p.stat().st_mode)
        if rel.endswith(".tmpl"):
            text = _render_text(p.read_text(encoding="utf-8"), ctx, f"{origin}:{rel}")
            em.write(dest_prefix + rel[: -len(".tmpl")], text, origin, mode)
        else:
            em.write(dest_prefix + rel, p.read_bytes(), origin, mode)


def _load_agent(path: Path, ctx: dict, origin: str) -> Agent:
    text = path.read_text(encoding="utf-8")
    if path.name.endswith(".tmpl"):
        text = _render_text(text, ctx, f"{origin}:{path.name}")
    meta, body = parse_frontmatter(text)
    for k in ("name", "description", "tier"):
        if k not in meta:
            raise RenderError(f"{origin}:{path.name}: frontmatter needs '{k}'")
    if meta["tier"] not in ("strong", "worker"):
        raise RenderError(f"{origin}:{path.name}: tier must be strong|worker")
    tools = meta.get("tools", [])
    if isinstance(tools, str):
        tools = [t.strip() for t in tools.split(",") if t.strip()]
    return Agent(name=meta["name"], description=meta["description"], tier=meta["tier"],
                 body=body, tools=tools, sandbox=meta.get("sandbox", "read-only"))


def _fragments(active: list[Module], fname: str, ctx: dict) -> list[str]:
    """Each enabled module's rendered `fname`, in order; a section left with nothing but its
    heading (all of it is for the other view) is dropped."""
    parts = []
    for m in active:
        frag = m.dir / fname
        if frag.exists():
            text = _render_text(frag.read_text(encoding="utf-8"), ctx, f"{m.id}:{fname}").strip("\n")
            if any(ln.strip() and not ln.lstrip().startswith("#") for ln in text.splitlines()):
                parts.append(text)
    return parts


def render_project(ans: dict, out: Path, templates: Path = TEMPLATES_DIR,
                   given: dict | None = None) -> dict:
    """Render the project for validated answers `ans`. `given` is the answers file as the
    interview wrote it: with it, docs/init-answers.json leaves init-math's defaults unset
    (answers.stored_answers); without it, the normalized answers are stored."""
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        raise RenderError(f"{out} is not empty; init-math only writes into a new or empty directory")
    mods = load_modules(templates)
    on = resolve_enabled(mods, ans)
    adapter = ADAPTERS[ans["harness"]](ans["tiers"])
    ctx = build_context(ans, mods, on, adapter)
    active = sorted((m for m in mods if on[m.id]), key=lambda m: (m.order, m.id))

    # Fragments first: each module's contribution to a file core assembles.
    for fname, key in FRAGMENTS.items():
        ctx[key] = _fragments(active, fname, ctx)

    out.mkdir(parents=True, exist_ok=True)
    em = Emitter(out)
    regs: list[HookReg] = []
    agents_emitted: list[str] = []
    for m in active:
        _emit_tree(m.dir / "files", "", em, ctx, m.id, adapter.name)
        _emit_tree(m.dir / "skills", adapter.skills_dir + "/", em, ctx, m.id, adapter.name)
        adir = m.dir / "agents"
        if adir.is_dir():
            for p in sorted(adir.iterdir()):
                if p.suffix in (".md", ".tmpl") and p.is_file():
                    ag = _load_agent(p, ctx, m.id)
                    em.write(adapter.agent_path(ag), adapter.render_agent(ag), m.id)
                    agents_emitted.append(ag.name)
        for item_spec in m.per_item:
            seq = ctx
            for part in item_spec["over"].split("."):
                seq = seq[part]
            tsrc = (m.dir / item_spec["template"]).read_text(encoding="utf-8")
            for item in seq:
                ictx = dict(ctx)
                ictx["item"] = item
                rel = item_spec["path"].format(**item)
                em.write(rel, _render_text(tsrc, ictx, f"{m.id}:{item_spec['template']}"), m.id)
        for h in m.hooks:
            # `harnesses` limits a registration to the harnesses it is meant for; elsewhere it
            # is left out by design, not reported as a skipped hook.
            if "harnesses" in h and ans["harness"] not in h["harnesses"]:
                continue
            regs.append(HookReg(script=h["script"], event=h["event"],
                                actions=list(h.get("actions", [])), module=m.id,
                                args=[str(a) for a in h.get("args", [])]))

    if adapter.coordinator_file:
        cctx = dict(ctx, view={"shared": False, "coordinator": True})
        cctx["module_sections"] = _fragments(active, "AGENTS.fragment.md.tmpl", cctx)
        src = templates / "core" / "files" / "AGENTS.md.tmpl"
        em.write(adapter.coordinator_file,
                 _render_text(src.read_text(encoding="utf-8"), cctx, "core:AGENTS.md.tmpl (coordinator)"), "core")

    # Index of the discipline docs every module emitted (core links here from AGENTS.md).
    docs = []
    for rel in sorted(em.owner):
        if rel.startswith("docs/discipline/") and rel.endswith(".md"):
            first = (out / rel).read_text(encoding="utf-8").lstrip().splitlines()[:1]
            title = first[0].lstrip("# ").strip() if first and first[0].startswith("#") else rel
            docs.append({"file": rel[len("docs/discipline/"):], "title": title,
                         "module": em.owner[rel]})
    idx = templates / "core" / "discipline-index.md.tmpl"
    if idx.exists():
        ictx = dict(ctx, discipline_docs=docs)
        em.write("docs/discipline/README.md",
                 _render_text(idx.read_text(encoding="utf-8"), ictx, "core:discipline-index"), "core")

    for r in regs:
        if r.script not in em.owner:
            raise RenderError(f"hook {r.script} (module {r.module}) is registered but not emitted")
    allow = [t for m in active for t in m.allow_tools]
    commands = [c for m in active for c in m.allow_commands]
    for c in commands:
        if c not in em.owner:
            raise RenderError(f"allow_commands: {c} is not emitted by any active module")
    cfg, skipped = adapter.hook_config(regs, allow, commands)
    if regs or allow or commands:
        em.write(adapter.hook_config_path(), cfg, "adapter")

    report = {
        "harness": adapter.name,
        "modules_on": [m.id for m in active],
        "modules_off": sorted(m.id for m in mods if not on[m.id]),
        "agents": sorted(agents_emitted),
        "hooks_registered": len(regs) - len(skipped),
        "hooks_skipped": skipped,
        "capabilities": adapter.CAPS,
        "capabilities_verified": adapter.VERIFIED,
    }
    em.write("docs/init-report.json", json.dumps(report, indent=2, sort_keys=True) + "\n", "renderer")
    stored = stored_answers(given, ans) if given is not None else ans
    em.write("docs/init-answers.json", json.dumps(stored, indent=2, sort_keys=True) + "\n", "renderer")
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="renderer", description=__doc__.splitlines()[0])
    ap.add_argument("--answers", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--templates", default=str(TEMPLATES_DIR))
    args = ap.parse_args(argv)
    if sys.version_info < (3, 11):
        print("init-math needs Python >= 3.11", file=sys.stderr)
        return 2
    try:
        given = read_answers(args.answers)
        report = render_project(validate(given), Path(args.out), Path(args.templates), given)
    except (AnswersError, RenderError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(json.dumps({k: report[k] for k in ("harness", "modules_on", "modules_off", "hooks_skipped")}, indent=2))
    return 0


__all__ = ["render_project", "load_modules", "resolve_enabled", "validate", "RenderError", "main"]

if __name__ == "__main__":
    raise SystemExit(main())
