"""The answers contract between the interview skill and the renderer.

The skill writes an answers.json file; `load_answers` validates it and fills defaults.
This is hand-written validation (stdlib only, no JSON Schema). Every key the skill must
ask about appears in REQUIRED_KEYS so tests can check questions.md covers it.
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from pathlib import Path

HARNESSES = ("claude", "codex")
RESEARCH_KINDS = ("theory", "experiment", "formalization")
PROOF_ASSISTANTS = ("lean", "none")

DEFAULT_TIERS = {
    "claude": {"strong": "opus", "worker": "sonnet"},
    # Codex: Astra is the frontier tier, Luna the fast, cheap one. Workers carry out
    # well-specified units, so they run on Luna (colleague trial on Codex, 2026-10-22).
    "codex": {"strong": "gpt-6-astra", "worker": "gpt-6-luna"},
}

# Failure patterns used when the answers give none (the key is absent): messages with which
# common tools report an error and still exit normally. A non-zero exit is caught without a
# pattern. The interview does not ask the owner for these; the reflection loop adds more as
# they turn up (docs/discipline/reflection-loop.md, section 3).
COMMON_SIGNATURES = [
    {"label": "out-of-memory", "regex": r"(?i)\bout of memory\b|MemoryError|std::bad_alloc"},
    {"label": "stack-overflow", "regex": r"(?i)\bstack overflow\b|RecursionError"},
]
TOOL_SIGNATURES = {
    "gp": [{"label": "gp-error", "regex": r"(?m)^\s*\*\*\*\s"}],
    "magma": [{"label": "magma-error", "regex": r"\b(Runtime|User|Internal) error\b"}],
    "gap": [{"label": "gap-error", "regex": r"(?m)^Error, "}],
    "M2": [{"label": "m2-error", "regex": r"\berror:"}],
}


def default_signatures(research_commands: list[str]) -> list[dict]:
    """The common patterns plus those of each research command's tool, without duplicates."""
    sigs = list(COMMON_SIGNATURES)
    for cmd in research_commands:
        for sig in TOOL_SIGNATURES.get(cmd.rsplit("/", 1)[-1], []):
            if sig not in sigs:
                sigs.append(sig)
    return [dict(x) for x in sigs]


# Watchdog limits per experiment tier: wall seconds and resident MB. The interview shows these
# and asks whether to depart from them; bin/exp-run carries the same numbers as its fallback.
DEFAULT_LIMITS = {
    "smoke": {"time_s": 120, "mem_mb": 2000},
    "full": {"time_s": 7200, "mem_mb": 8000},
    "deep": {"time_s": 43200, "mem_mb": 16000},
}

# dotted keys the interview must collect (tests check questions.md mentions each)
REQUIRED_KEYS = (
    "project.name",
    "project.owner",
    "project.field",
    "project.research_kinds",
    "harness",
    "stack.proof_assistant",
)

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_QID_RE = re.compile(r"^Q\d{3}$")
_CID_RE = re.compile(r"^C\d{3}$")
_MOVE_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
# The kinds of support an argued claim may name (docs/discipline/informal-arguments.md); a
# project adds its own through `arguments.labels`.
DEFAULT_LABELS = ("heuristic", "moral", "conditional", "model-only", "analogy")
# The kinds of example a question's examples bank keeps (its `## Examples` lines).
EXAMPLE_KINDS = ("simplest", "structured", "breakers", "outside")
# The moves the attempts module registers itself; a seeded project move may not reuse an id.
BUILTIN_MOVES = ("toy-model", "specialize-generalize", "assume-missing-lemma", "what-if-not",
                 "decoy-object", "port-special-case-proof", "impossibility-as-assumptions",
                 "repair-by-removing-hypothesis", "impose-equality-in-bound",
                 "change-representation", "enumerate-shapes-from-necessary-conditions")


class AnswersError(ValueError):
    pass


def _req(d: dict, key: str, typ, where: str):
    if key not in d:
        raise AnswersError(f"{where}.{key} is required")
    if not isinstance(d[key], typ):
        raise AnswersError(f"{where}.{key} must be {typ}")
    return d[key]


def _snip(text, n: int = 50) -> str:
    t = " ".join(str(text).split())
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def _label(path: str, xid: str, text) -> str:
    """`seeds.questions[0] (Q001 "Is every…")`: the key path plus enough to recognize the item."""
    return f'{path} ({xid} "{_snip(text)}")' if text else f"{path} ({xid})"


# Default experiment-driver file name, from the program that run_cmd starts. The experiment
# template ships an example driver.py; a project whose run_cmd starts another tool gets a
# driver name that tool can run, so `bin/exp-run` never hands it the Python example.
DRIVER_EXT = {
    "python": "py", "python3": "py", "pypy": "py", "pypy3": "py", "uv": "py",
    "sage": "sage", "gp": "gp", "magma": "m", "julia": "jl", "rscript": "R", "m2": "m2",
    "gap": "g", "maple": "mpl", "wolframscript": "wl", "math": "wl", "matlab": "m",
    "octave": "m", "node": "js", "sh": "sh", "bash": "sh", "zsh": "sh", "maxima": "mac",
}
_WRAPPERS = {"env", "nice", "nohup", "time", "exec", "command"}


def default_driver(run_cmd: str) -> str:
    """driver.<ext> for the tool run_cmd starts; driver.py when it is unknown or empty."""
    for tok in run_cmd.split():
        if tok in _WRAPPERS or "=" in tok or tok.startswith("-"):
            continue
        name = tok.rsplit("/", 1)[-1].lower()
        name = re.sub(r"[\d.]+$", "", name) if name.startswith("python") else name
        return f"driver.{DRIVER_EXT.get(name, 'py')}"
    return "driver.py"


# Comparison signs carry meaning in a statement ("p ≤ 31" vs "p ≥ 31"), so they become words
# instead of vanishing with the other punctuation.
_SLUG_WORDS = {"<=": "le", ">=": "ge", "!=": "ne", "≤": "le", "⩽": "le", "≥": "ge", "⩾": "ge",
               "≠": "ne", "<": "lt", ">": "gt"}
_SLUG_SIGN = re.compile("|".join(map(re.escape, _SLUG_WORDS)))  # two-character signs first


def slugify(s: str) -> str:
    s = _SLUG_SIGN.sub(lambda m: f" {_SLUG_WORDS[m.group()]} ", s)
    # Fold accents first ("Thomassé" -> "thomasse") so names keep their letters.
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s or "project"


def validate(a: dict) -> dict:
    """Validate and normalize; returns a new dict with defaults filled in."""
    if not isinstance(a, dict):
        raise AnswersError("answers must be a JSON object")
    out: dict = {}

    p = _req(a, "project", dict, "answers")
    name = _req(p, "name", str, "project").strip()
    if not name:
        raise AnswersError("project.name is empty")
    owner = _req(p, "owner", str, "project").strip()
    if not owner:
        raise AnswersError("project.owner is empty")
    kinds = _req(p, "research_kinds", list, "project")
    bad = [k for k in kinds if k not in RESEARCH_KINDS]
    if bad or not kinds:
        raise AnswersError(f"project.research_kinds must be a non-empty subset of {RESEARCH_KINDS}")
    slug = p.get("slug") or slugify(name)
    if not _SLUG_RE.match(slug):
        raise AnswersError(f"project.slug '{slug}' must match {_SLUG_RE.pattern}")
    out["project"] = {
        "name": name,
        "slug": slug,
        "owner": owner,
        "field": _req(p, "field", str, "project").strip(),
        "subarea": str(p.get("subarea", "")).strip(),
        "research_kinds": [k for k in RESEARCH_KINDS if k in kinds],
        "init_date": str(p.get("init_date", "")),
    }

    harness = _req(a, "harness", str, "answers")
    if harness not in HARNESSES:
        raise AnswersError(f"harness must be one of {HARNESSES}")
    out["harness"] = harness

    tiers = dict(DEFAULT_TIERS[harness])
    tiers.update({k: v for k, v in (a.get("tiers") or {}).items() if k in ("strong", "worker") and v})
    out["tiers"] = tiers

    # Codex only: may sandboxed agents run `git commit`? Codex's workspace-write sandbox
    # keeps .git read-only; the default (True) renders a permission profile that reopens it.
    cx = a.get("codex") or {}
    if not isinstance(cx, dict):
        raise AnswersError("codex must be an object")
    gc = cx.get("git_commits", True)
    if not isinstance(gc, bool):
        raise AnswersError("codex.git_commits must be true or false")
    out["codex"] = {"git_commits": gc}

    s = a.get("stack") or {}
    pa = s.get("proof_assistant", "none")
    if pa not in PROOF_ASSISTANTS:
        raise AnswersError(f"stack.proof_assistant must be one of {PROOF_ASSISTANTS}")
    sigs = []
    for i, sig in enumerate(s.get("failure_signatures") or []):
        if not isinstance(sig, dict) or "regex" not in sig:
            raise AnswersError(f"stack.failure_signatures[{i}] needs a 'regex'")
        try:
            re.compile(sig["regex"])
        except re.error as e:
            raise AnswersError(f"stack.failure_signatures[{i}].regex invalid: {e}") from None
        sigs.append({"label": sig.get("label", f"sig{i + 1}"), "regex": sig["regex"]})
    research_commands = [str(c) for c in s.get("research_commands") or []]
    if s.get("failure_signatures") is None and research_commands:
        sigs = default_signatures(research_commands)
    run_cmd = str(s.get("run_cmd", ""))
    driver = str(s.get("driver") or "") or default_driver(run_cmd)
    if "/" in driver or not driver.strip():
        raise AnswersError(f"stack.driver must be a bare file name, got {driver!r}")
    out["stack"] = {
        "tools": [str(t) for t in s.get("tools") or []],
        "run_cmd": run_cmd,
        "driver": driver,
        "research_commands": research_commands,
        "failure_signatures": sigs,
        "hygiene_rules": [str(r) for r in s.get("hygiene_rules") or []],
        "proof_assistant": pa,
        "lake_path": str(s.get("lake_path", "")),
    }

    m = a.get("modules") or {}
    out["modules"] = {
        "disable": [str(x) for x in m.get("disable") or []],
        "enable": [str(x) for x in m.get("enable") or []],
        "preset": str(m.get("preset", "")),
    }

    seeds = a.get("seeds") or {}

    def seed_slug(given, text: str, where: str, seen: set) -> str:
        """A file-name slug: a given one must already be valid (it becomes a path, so `/`
        or `..` must never get through); a derived one is made unique with -2, -3, …"""
        if given:
            if not _SLUG_RE.match(str(given)):
                raise AnswersError(f"{where}: slug '{given}' must match {_SLUG_RE.pattern}")
            if given in seen:
                raise AnswersError(f"{where}: slug '{given}' is used twice")
            seen.add(given)
            return given
        base = slugify(text)[:40].strip("-") or "untitled"
        slug, n = base, 2
        while slug in seen:
            slug, n = f"{base}-{n}", n + 1
        seen.add(slug)
        return slug

    def unique_id(xid: str, seen: set) -> None:
        if xid in seen:
            raise AnswersError(f"id '{xid}' is used twice")
        seen.add(xid)

    qs = []
    q_slugs: set = set()
    q_ids: set = set()
    for i, q in enumerate(seeds.get("questions") or []):
        qid = q.get("id") or f"Q{i + 1:03d}"
        where = _label(f"seeds.questions[{i}]", qid, q.get("sentence"))
        if not _QID_RE.match(qid):
            raise AnswersError(f"{where}: question id '{qid}' must look like Q001")
        unique_id(qid, q_ids)
        if not q.get("sentence"):
            raise AnswersError(f"{where}: 'sentence' is required")
        # A shape is a string, or {"n", "text"} as stored in docs/init-answers.json.
        answers = [a_["text"] if isinstance(a_, dict) else a_
                   for a_ in (q.get("answer_shapes") or [])]
        answers = [a_ for a_ in answers if str(a_).strip()]
        if not answers:
            raise AnswersError(f"{where}: at least one non-empty answer shape is required "
                               "(answer_shapes: concrete forms the answer could take, e.g. "
                               '["a finite list of exceptions", "no: an explicit counterexample"])')
        exs = q.get("examples") or {}
        if not isinstance(exs, dict) or set(exs) - set(EXAMPLE_KINDS):
            raise AnswersError(f"{where}: 'examples' is an object with keys {list(EXAMPLE_KINDS)}")
        qs.append({
            "id": qid,
            "slug": seed_slug(q.get("slug"), q["sentence"], qid, q_slugs),
            "sentence": q["sentence"].strip(),
            "answer_shapes": [{"n": j + 1, "text": t} for j, t in enumerate(answers)],
            "why": str(q.get("why", "")).strip(),
            "examples": {k: str(exs.get(k) or "").strip() for k in EXAMPLE_KINDS},
        })
    qids = {q["id"] for q in qs}
    cs = []
    c_slugs: set = set()
    c_ids: set = set()
    for i, c in enumerate(seeds.get("conjectures") or []):
        cid = c.get("id") or f"C{i + 1:03d}"
        where = _label(f"seeds.conjectures[{i}]", cid, c.get("statement"))
        if not _CID_RE.match(cid):
            raise AnswersError(f"{where}: conjecture id '{cid}' must look like C001")
        unique_id(cid, c_ids)
        if not c.get("statement"):
            raise AnswersError(f"{where}: 'statement' is required")
        cq = c.get("questions") or []
        if not cq:
            raise AnswersError(f"{where}: name the question(s) it bears on (key 'questions'); "
                               "if none fits, that is a missing research question to add first")
        missing = [q for q in cq if q not in qids]
        if missing:
            raise AnswersError(f"{where}: unknown question ids {missing} in 'questions' "
                               f"(known: {sorted(qids)})")
        cs.append({
            "id": cid,
            "slug": seed_slug(c.get("slug"), c["statement"], cid, c_slugs),
            "statement": c["statement"].strip(),
            "questions": cq,
            "tie": str(c.get("tie", "")).strip(),
            "family": str(c.get("family", "")).strip(),
        })
    srcs = []
    s_slugs: set = set()
    for i, src in enumerate(seeds.get("sources") or []):
        if not src.get("cite"):
            raise AnswersError(f"seeds.sources[{i}]: 'cite' is required")
        srcs.append({
            "cite": src["cite"].strip(),
            "locator": str(src.get("locator", "")).strip(),
            "slug": seed_slug(src.get("slug"), src["cite"], f"seeds.sources[{i}]", s_slugs),
            "why": str(src.get("why", "")).strip(),
        })
    # The one question the owner chose in the interview to start on (or none).
    aq = "" if seeds.get("active_question") is None else seeds["active_question"]
    if not isinstance(aq, str):
        raise AnswersError("seeds.active_question must be a question id such as \"Q001\", or empty")
    aq = aq.strip()
    if aq and aq not in qids:
        raise AnswersError(f"seeds.active_question: '{aq}' is not a seeded question "
                           f"(known: {sorted(qids)})")
    for q in qs:
        q["active"] = q["id"] == aq
    moves = []
    m_ids: set = set()
    for i, mv in enumerate(seeds.get("moves") or []):
        if not isinstance(mv, dict):
            raise AnswersError(f"seeds.moves[{i}]: an object with id, says, when, example")
        mid = str(mv.get("id", "")).strip()
        if not _MOVE_RE.match(mid):
            raise AnswersError(f"seeds.moves[{i}]: id '{mid}' must be lowercase words joined by dashes")
        if mid in BUILTIN_MOVES:
            raise AnswersError(f"seeds.moves[{i}]: '{mid}' is already a built-in move")
        unique_id(mid, m_ids)
        says = str(mv.get("says", "")).strip()
        if not says:
            raise AnswersError(f"seeds.moves[{i}] ({mid}): 'says' (the move in one line) is required")
        moves.append({"id": mid, "says": says, "when": str(mv.get("when", "")).strip(),
                      "example": str(mv.get("example", "")).strip(),
                      "construction": mv.get("construction") is True})
    out["seeds"] = {"questions": qs, "conjectures": cs, "sources": srcs, "active_question": aq,
                    "moves": moves}

    fp = a.get("field_profile") or {}
    if not isinstance(fp, dict) or set(fp) - {"small_cases_informative", "construction"}:
        raise AnswersError("field_profile is an object with keys small_cases_informative, construction")
    for k in fp:
        if not isinstance(fp[k], bool):
            raise AnswersError(f"field_profile.{k} must be true or false")
    out["field_profile"] = {"small_cases_informative": fp.get("small_cases_informative", True),
                            "construction": fp.get("construction", False)}

    qset = a.get("questions") or {}
    if not isinstance(qset, dict) or set(qset) - {"satellites", "satellites_max"}:
        raise AnswersError("questions is an object with keys satellites, satellites_max")
    sat = qset.get("satellites", True)
    cap = qset.get("satellites_max", 0)
    if not isinstance(sat, bool):
        raise AnswersError("questions.satellites must be true or false")
    if isinstance(cap, bool) or not isinstance(cap, int) or cap < 0:
        raise AnswersError("questions.satellites_max must be a whole number, 0 for no limit")
    out["questions"] = {"satellites": sat, "satellites_max": cap}

    arg = a.get("arguments") or {}
    extra = arg.get("labels") or [] if isinstance(arg, dict) else None
    if not isinstance(extra, list) or not all(isinstance(x, str) and _MOVE_RE.match(x.strip().lower()) for x in extra):
        raise AnswersError("arguments.labels is a list of lowercase words (dashes allowed), e.g. [\"numerical\"]")
    labels = list(DEFAULT_LABELS) + [x.strip().lower() for x in extra if x.strip().lower() not in DEFAULT_LABELS]
    out["arguments"] = {"labels": labels}

    ex = {} if a.get("experiments") is None else a["experiments"]
    if not isinstance(ex, dict):
        raise AnswersError("experiments must be an object")
    given = {} if ex.get("limits") is None else ex["limits"]
    if not isinstance(given, dict):
        raise AnswersError("experiments.limits must be an object keyed by smoke, full, deep")
    unknown = sorted(set(given) - set(DEFAULT_LIMITS))
    if unknown:
        raise AnswersError(f"experiments.limits: unknown tier(s) {unknown}; "
                           f"use {list(DEFAULT_LIMITS)}")
    limits = {}
    for tier, dflt in DEFAULT_LIMITS.items():
        t = {} if given.get(tier) is None else given[tier]
        if not isinstance(t, dict):
            raise AnswersError(f"experiments.limits.{tier} must be an object with time_s and mem_mb")
        bad = sorted(set(t) - set(dflt))
        if bad:
            raise AnswersError(f"experiments.limits.{tier}: unknown key(s) {bad}; use time_s, mem_mb")
        limits[tier] = {}
        for k, d in dflt.items():
            v = t.get(k, d)
            if isinstance(v, bool) or not isinstance(v, (int, float)) \
                    or not math.isfinite(v) or v <= 0:
                raise AnswersError(f"experiments.limits.{tier}.{k} must be a positive number "
                                   f"(seconds for time_s, megabytes for mem_mb), got {v!r}")
            limits[tier][k] = int(v) if float(v).is_integer() else v
    out["experiments"] = {"limits": limits}

    # The exposition charter's two slots: the owner's own prior work and one model text.
    xp = {} if a.get("exposition") is None else a["exposition"]
    if not isinstance(xp, dict):
        raise AnswersError("exposition must be an object")
    pw = [] if xp.get("prior_work") is None else xp["prior_work"]
    if not isinstance(pw, list) or not all(isinstance(x, str) for x in pw):
        raise AnswersError("exposition.prior_work must be a list of strings (one per paper)")
    mt = "" if xp.get("model_text") is None else xp["model_text"]
    if not isinstance(mt, str):
        raise AnswersError("exposition.model_text must be a string (one paper, thesis or book)")
    out["exposition"] = {"prior_work": [" ".join(x.split()) for x in pw if x.strip()],
                         "model_text": " ".join(mt.split())}
    return out


_WEAK_TIE = re.compile(r"whatever|tbd|todo|recommend|n/?a\b", re.I)
# A tie cites an answer shape as A<n>, the number the question file gives it. A shape named by
# a letter or roman numeral ("shape (a)") matches nothing in the question file.
_SHAPE_REF = re.compile(r"\bA(\d+)\b")
_SHAPE_LETTER = re.compile(r"\bshapes?\s*\(?([a-z]|[ivx]{1,4})\)", re.I)


def tie_label_problem(tie: str, shape_counts: dict[str, int]) -> str:
    """Why `tie` cites an answer shape the linked questions do not have, or "" if it is fine.

    `shape_counts` maps each linked question id to its number of answer shapes."""
    m = _SHAPE_LETTER.search(tie)
    if m:
        return (f"names an answer shape as ({m.group(1)}); cite it as A<n>, the number the "
                "question file gives it")
    top = max(shape_counts.values(), default=0)
    bad = sorted({int(n) for n in _SHAPE_REF.findall(tie)} - set(range(1, top + 1)))
    if bad and shape_counts:
        have = ", ".join(f"{q} has A1-A{k}" for q, k in shape_counts.items())
        return f"cites {', '.join(f'A{n}' for n in bad)}, which no linked question has ({have})"
    return ""


def warnings_for(ans: dict, base: Path | None = None) -> list[str]:
    """Non-fatal problems in a VALIDATED answers dict (never refuses; the interviewer fixes them).

    `base` is the new project root: a relative `stack.lake_path` resolves against it."""
    w: list[str] = []
    for i, c in enumerate(ans["seeds"]["conjectures"]):
        tie = c["tie"]
        if len(tie.split()) < 5 or _WEAK_TIE.search(tie):
            w.append(_label(f"seeds.conjectures[{i}]", c["id"], c["statement"]) +
                     f': tie "{_snip(tie, 60)}" looks like a placeholder; a tie states what a '
                     "verdict would change in the question's answer. Draft one from the question's "
                     "answer shape and confirm it with the owner")
        counts = {q["id"]: len(q["answer_shapes"]) for q in ans["seeds"]["questions"]
                  if q["id"] in c["questions"]}
        why = tie_label_problem(tie, counts)
        if why:
            w.append(_label(f"seeds.conjectures[{i}]", c["id"], c["statement"]) + f": tie {why}")
    lp = ans["stack"]["lake_path"]
    if lp:
        d = Path(lp).expanduser()
        if not d.is_absolute():
            if base is None:
                w.append(f"stack.lake_path: {lp} is relative, so it resolves against the new "
                         "project root and cannot be checked yet; prefer an absolute path")
                return w
            d = base / d
            note = " (relative paths resolve against the new project root; prefer an absolute path)"
        else:
            note = ""
        if not d.is_dir():
            w.append(f"stack.lake_path: {d} is not a directory{note}")
        else:
            if not ((d / "lakefile.lean").exists() or (d / "lakefile.toml").exists()):
                w.append(f"stack.lake_path: {d} has no lakefile.lean or lakefile.toml{note}")
            if not (d / "lean-toolchain").exists():
                w.append(f"stack.lake_path: {d} has no lean-toolchain file{note}")
    return w


def read_answers(path: str | Path) -> dict:
    """The answers file as given, unvalidated."""
    with open(path, encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as e:
            raise AnswersError(f"{path}: not valid JSON: {e}") from None


def load_answers(path: str | Path) -> dict:
    return validate(read_answers(path))


def stored_answers(given: dict, ans: dict) -> dict:
    """What a project keeps as docs/init-answers.json: the normalized answers, except that a
    value the interview left to init-math's defaults (the model tiers, the run limits, the
    failure patterns, the driver name) stays unset. Re-rendered by the same init-math, it
    gives the same project; re-rendered by a later one (an upgrade), it takes that version's
    defaults instead of freezing these (colleague trial, 2026-10-22: workers stayed on the
    old default model)."""
    out = json.loads(json.dumps(ans))
    out["tiers"] = {k: v for k, v in (given.get("tiers") or {}).items()
                    if k in ("strong", "worker") and v}
    s = given.get("stack") or {}
    if s.get("failure_signatures") is None:
        del out["stack"]["failure_signatures"]
    if not s.get("driver"):
        del out["stack"]["driver"]
    for key in ("field_profile", "questions", "arguments"):
        if not given.get(key):
            del out[key]  # left to this init-math's defaults; a later one may change them
    lim = (given.get("experiments") or {}).get("limits") or {}
    out["experiments"]["limits"] = {
        t: {k: out["experiments"]["limits"][t][k] for k in lim[t]}
        for t in out["experiments"]["limits"] if isinstance(lim.get(t), dict) and lim[t]}
    return out
