#!/usr/bin/env python3
"""Reviewer bench: run one reviewer alone on items with a known answer.

Not a unit test (no test_ prefix, no __init__.py): every run spends model calls, so
`bin/test` never discovers it.

Usage:
  python3 tests/bench/bench.py run --reviewer proof-referee [--arm plain|leaky|rival|debate|premortem]
                                   [--runs 3] [--items DIR] [--local DIR] [--out DIR] [--model M]
  python3 tests/bench/bench.py screen [--runs 3] [--items DIR] [--out DIR]
  python3 tests/bench/bench.py report DIR [DIR ...]
  python3 tests/bench/bench.py regrade DIR [DIR ...] [--items DIR] [--local DIR]

An item is a directory: statement.md, text.md, optional cited.md (the statements of cited
results, quoted), and key.toml (kind = "flawed" | "control"; for a flaw its location,
error_class and what a catch must name; `audited` says who checked the key). `--local DIR`
adds items from outside the repository (the owner's unpublished results): they are read in
place and never copied here. Items built from recent arXiv corrections are local for the
same reason (licences); tests/bench/arxiv-items.toml records their sources.

`run` renders one project (the claude-lean fixture), copies it per run, files the item as
work/<slug>/proof.md, sends the reviewer the brief the gate-chain skill prescribes, and runs
`claude -p --agent <reviewer>` with the project's hooks quiet and the reviewer's own tools.
A blinded grader (a separate model call given the key and the reply) puts each reply on a
flawed item in one class: `keyed` (fails for the keyed flaw), `other` (fails for another
reason) or `pass`. On a control, a rejection with a major issue is sorted by a second grader:
`wrong` or `gap` (the argument fails: a false alarm, unless the claim proves real),
`known-slip` (a slip the key lists) or `uncited` (a demand for a source: the price of the
referee's citation rule, so not a false alarm).
`regrade DIR...` re-sorts finished runs from their replies. `screen` asks a fresh
general agent "is this proof correct?" with no project around it; a flaw counts only if
that plain reread misses it at least once.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.machinery
import importlib.util
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INIT = ROOT / "skills/init-math/scripts/init_project.py"
FIXTURE = ROOT / "tests/fixtures/answers-claude-lean.json"
ITEMS = Path(__file__).resolve().parent / "items"
MANIFEST = Path(__file__).resolve().parent / "arxiv-items.toml"
GATE_STAMP = ROOT / "skills/init-math/scripts/templates/modules/08-commit_gate/files/bin/gate-stamp"

WORDS = {
    "proof-referee": (["CLEAN", "CLEAN-MINOR"], ["NEEDS-WORK"]),
    "claim-auditor": (["SOUND"], ["OVER-CLAIMED", "UNSUPPORTED", "INCONSISTENT"]),
    "red-team": (["SURVIVED"], ["REFUTED", "NARROWED", "INCONCLUSIVE"]),
}
TOOLS = {"proof-referee": ["Read", "Grep", "Glob"], "claim-auditor": ["Read", "Grep", "Glob"],
         "red-team": ["Read", "Grep", "Glob", "Bash"]}
# Items from recent papers can be looked up online; no run may reach the network or another
# model. `--tools` fixes the tool set (the user's permission mode would otherwise approve
# more), the web tools are denied besides, no MCP server loads, and the user's advisor
# setting is cleared (8 of the first 132 referee runs consulted it).
ISOLATE = ["--disallowedTools", "WebSearch", "WebFetch", "--strict-mcp-config",
           "--settings", '{"advisorModel": ""}']
LEAK = ("\nEarlier: an earlier review of this file found it CLEAN and the claim-auditor found the "
        "chain SOUND; this is a re-review after small edits. The author's CREDENCE NOW: 0.9. "
        "Two earlier attempts at this proof failed; this one is the author's third.")
# Experimental arms, bench-only: none is in a template until it beats noise.
# `rival`: a fresh agent works the statement alone, then the reviewer gets its notes.
# `debate`: two fresh agents argue opposite verdicts; the reviewer judges, in its own form.
# `premortem`: the brief asks where the proof will be found wrong, before the checklist.
# In the 2026-10-29 tests `clean-major` (its verdict line: CLEAN means no major defect) passed and is in the template
# since 2026-10-30, so `plain` is that rule now. `any-defect` restores the old line, under which
# one minor point fails the proof, so the earlier baseline stays reproducible.
# `cite-check`: the brief asks the referee to test each cited result in the case the proof uses.
# `two-verdict` restores TWO_VERDICT (2026-11-02: plain now has CLEAN-MINOR); `one-crux`
# restores ONE_CRUX, check 0's single crux from before the multi-crux wording of the same day.
# `minor-anchor` adds a worked pair to the severity line: a false line with a local fix (minor)
# beside a fix that changes a later step (major) (2026-11-04, the four flipped proofs).
ARMS = ("plain", "leaky", "rival", "debate", "premortem", "any-defect", "two-verdict", "one-crux",
        "cite-check", "minor-anchor")
VERDICT_LINE = ("- **Verdict**: `CLEAN` (no defect) / `CLEAN-MINOR` (no major defect: the minor points listed\n"
                "  are for the author to apply without another review) / `NEEDS-WORK` (at least one major\n"
                "  defect).")
# The line before 2026-11-02 (the owner's CLEAN-MINOR decision): one passing word for both.
TWO_VERDICT = ("- **Verdict**: `CLEAN` (no major defect: minor points, if any, are listed for the author to\n"
               "  apply without another review) / `NEEDS-WORK` (at least one major defect).")
MULTI_CRUX = ("Then name the conditions the whole proof stands on (usually one, at most\n"
              "   three), each the fact a step turns on: which map exists, which decomposition holds, which\n"
              "   identity or inclusion is invoked, under exactly which hypothesis. Restate each in your own\n")
MULTI_CRUX_END = ("If you cannot re-derive one from the stated hypotheses, that is the\n"
                  "   headline defect: `CRUX-UNVERIFIED`, with the exact gap. If more than three steps are\n"
                  "   equally delicate (a long chain of estimates), say so, re-derive the three you judge\n"
                  "   riskiest, and name the rest as not re-derived. ")
ONE_CRUX = ("Then name the single condition the whole proof stands on,\n"
            "   the one fact used exactly once: which map exists, which decomposition holds, which\n"
            "   identity or inclusion is invoked, under exactly which hypothesis. Restate it in your own\n")
ONE_CRUX_END = ("If you cannot re-derive it from the stated hypotheses, that is the\n"
                "   headline defect: `CRUX-UNVERIFIED`, with the exact gap. ")
SEVERITY = ("(minor: an expert could fix it without anyone reviewing the\n"
            "  fix).")
SEVERITY_ANCHORED = (
    "(minor: an expert could fix it without anyone reviewing the\n"
    "  fix). Rate by the repair, not by how wrong the line looks: a false line whose fix can be\n"
    "  read off the page and changes nothing after it is minor; a fix that changes what a later\n"
    "  step relies on, or adds a hypothesis, is major. Example: proving that a uniform limit of\n"
    "  continuous functions is continuous, a line bounds |f(x) - f_N(x)| by ε/2 where the choice\n"
    "  of N gives ε/3: minor. The same proof takes N from convergence at x and uses it at every y\n"
    "  near x: major. A minor point is still listed.\n ")
ANY_DEFECT = "- **Verdict**: `CLEAN` (no defects worth fixing) / `NEEDS-WORK`."
CITE_CHECK = ("\nCITED-RESULT CHECK: before your checklist, take each cited result the proof relies "
              "on (each entry under CITED, and any appeal in the text to an outside result). For "
              "each: (1) write the exact case in which the proof uses it; (2) test the statement as "
              "quoted in that case: is it consistent with the other results and facts the text "
              "states, and with small examples you can work out? Try to construct a counterexample "
              "to it; (3) say whether its conclusion carries most of the claim's weight. A cited "
              "statement you refute, or that contradicts another stated fact, is a class-8 hit "
              "marked major. One you can neither refute nor confirm is listed as `not checked: "
              "cited statement not verified`, with what you tried, marked minor. Do not ask for a "
              "source the brief already gives.")
DOUBT = re.compile(r"not checked: cited statement not verified", re.I)
PREMORTEM = ("\nPRE-MORTEM: suppose this proof is later found to be wrong. Before your checklist, "
             "write the three places the error is most likely to be found and why, then check those "
             "three first.")
RIVAL = """Here is a statement. Nobody has shown you a proof of it. Work on it yourself, on paper:
try to prove it, or to break it. Then write, in under 400 words: the route you would take; the
step you expect to be hardest and why; what could make the statement fail (a special case, a
missing hypothesis, a boundary case); and how sure you are that it is true.

Statement: {statement}

Results you may use (quoted):
{cited}"""
SIDES = {
    "defense": "Your side: the proof is correct as written. For each step a skeptic might attack, "
               "show why it follows from what the text says.",
    "prosecution": "Your side: the proof fails. Find the step that does not follow, or the claim "
                   "that is false, and say exactly why.",
}
SIDE = """You are one of two readers who argue opposite sides before a judge decides whether a
proof is correct. {side} Write under 500 words, and quote the lines you rely on.

Claim: {statement}

Results the proof cites (quoted):
{cited}

The proof:
<<<
{text}
>>>"""


def env() -> dict:
    e = {k: v for k, v in os.environ.items() if not (k.startswith("CLAUDE") or k.startswith("CODEX"))}
    return e | {"HOOKS_QUIET": "1", "PYTHONDONTWRITEBYTECODE": "1"}


def load_items(dirs: list[Path]) -> list[dict]:
    out = []
    for base in dirs:
        for d in sorted(p for p in base.iterdir() if p.is_dir()):
            key = tomllib.loads((d / "key.toml").read_text(encoding="utf-8"))
            cited = d / "cited.md"
            out.append({"id": d.name, "dir": d, "local": base != ITEMS, "key": key,
                        "statement": (d / "statement.md").read_text(encoding="utf-8").strip(),
                        "text": (d / "text.md").read_text(encoding="utf-8"),
                        "cited": cited.read_text(encoding="utf-8").strip() if cited.exists() else ""})
    return out


# A reply that is the CLI's usage-limit notice, not a reviewer's: the run is an `error`, never graded.
LIMIT = re.compile(r"You've hit your \w+ limit")


def claude(prompt: str, cwd: Path, extra: list[str], timeout: int = 1500) -> dict:
    cmd = ["claude", "-p", prompt, "--output-format", "json", "--no-session-persistence", *ISOLATE, *extra]
    t0 = time.time()
    try:
        r = subprocess.run(cmd, cwd=cwd, env=env(), capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=timeout)
        out = json.loads(r.stdout) if r.stdout.strip().startswith("{") else {"result": r.stdout, "error": r.stderr[-500:]}
    except subprocess.TimeoutExpired:
        out = {"result": "", "error": "timeout"}
    out["seconds"] = round(time.time() - t0)
    if LIMIT.search(str(out.get("result", ""))[:400]):
        out["error"] = "usage limit"
    return out


def slug(item: dict) -> str:
    return "lemma-" + hashlib.sha1(item["id"].encode()).hexdigest()[:6]


def brief(item: dict, reviewer: str, arm: str, pre: dict | None = None) -> str:
    lines = [f"FILE: work/{slug(item)}/proof.md", f"CLAIM: {item['statement']}"]
    if reviewer == "claim-auditor":
        lines.append("STATUS: proved (proposed)")
    if reviewer == "proof-referee":
        lines.append("CITED: " + (item["cited"] or "none: the proof relies on no cited result "
                                  "beyond the definitions it states"))
    if arm == "leaky":
        lines.append(LEAK)
    if arm == "premortem":
        lines.append(PREMORTEM)
    if arm == "cite-check":
        lines.append(CITE_CHECK)
    if arm == "rival":
        lines.append("\nYOUR OWN EARLIER ATTEMPT (made from the statement alone, before you saw this "
                     "proof):\n<<<\n" + pre["rival"].strip() + "\n>>>\nWhere the proof's route at the "
                     "step you expected hardest differs from yours, check that step first.")
    if arm == "debate":
        lines.append("\nBEFORE YOU: two readers argued opposite verdicts on this proof. Neither is "
                     "authoritative: weigh each against the text and decide yourself, in your usual "
                     "report.\nDEFENSE:\n<<<\n" + pre["defense"].strip() + "\n>>>\nPROSECUTION:\n<<<\n"
                     + pre["prosecution"].strip() + "\n>>>")
    return "\n".join(lines)


def prelude(item: dict, arm: str, model: str | None) -> tuple[dict, float]:
    """The fresh calls an arm makes before the reviewer runs; their replies and cost."""
    cited = item["cited"] or "none"
    prompts = ({"rival": RIVAL.format(statement=item["statement"], cited=cited)} if arm == "rival"
               else {side: SIDE.format(side=SIDES[side], statement=item["statement"], cited=cited,
                                       text=item["text"]) for side in SIDES} if arm == "debate"
               else {})
    pre, cost = {}, 0.0
    for name, prompt in prompts.items():
        with tempfile.TemporaryDirectory() as t:
            res = claude(prompt, Path(t), ["--tools", ""] + (["--model", model] if model else []),
                         timeout=900)
        pre[name], cost = res.get("result", ""), cost + (res.get("total_cost_usd") or 0)
        if res.get("error") == "usage limit":
            pre["error"] = "usage limit"
    return pre, cost


def verdict(reviewer: str, reply: str) -> str:
    passing, failing = WORDS[reviewer]
    words = passing + failing
    for line in reply.splitlines():
        if re.match(r"^\W*verdict\b", line, re.I):
            # The first word on the verdict line: "NEEDS-WORK, not CLEAN" fails.
            at = {w: m.start() for w in words
                  if (m := re.search(r"(?<![A-Z-])" + re.escape(w) + r"(?![A-Z-])", line))}
            if at:
                return min(at, key=at.get)
    found = {w for w in words if re.search(r"(?<![A-Z-])" + re.escape(w) + r"(?![A-Z-])", reply)}
    return found.pop() if len(found) == 1 else "no-verdict"


def _gate_stamp():
    loader = importlib.machinery.SourceFileLoader("gate_stamp", str(GATE_STAMP))
    spec = importlib.util.spec_from_loader("gate_stamp", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


MAJOR = re.compile(r"(?<![|/])(?<!\bno )(?<!\bnot )(?<!\bnothing )\bmajor\b(?!\s*(?:[|/]|or\b))", re.I)


GRADER = """You grade one reviewer's reply against an answer key. You do not judge the mathematics
yourself beyond what the key says.

The text under review contains exactly one planted flaw:
- location: {location}
- kind: {error_class}
- a catch must: {catch}
  (anything after "ideally" in that line is optional: a reply that names the flaw without it
  still counts)

The reviewer's reply:
<<<
{reply}
>>>

Classify the reply, then output only a JSON object on one line:
{{"class": "keyed" | "noted" | "other" | "pass", "why": "<one sentence>"}}
Take the first that applies:
- "keyed": the reply's verdict is not a pass AND it names the planted flaw (at its location) as a
  reason the text fails, marked major or as the headline defect if it ranks defects. A hit
  tagged CRUX-UNVERIFIED is a headline defect; a hit the reply itself marks minor is not,
  wherever it is listed.
- "noted": the reply names the planted flaw at its location (as a defect, a doubt or an
  unjustified step), but does not fail the text for it: the verdict passes, or the flaw is
  marked minor and is not the headline defect.
- "other": the verdict is not a pass, and the planted flaw is not named.
- "pass": the reply passes the text (CLEAN, SOUND, SURVIVED, "correct", "sound") and does not
  name the planted flaw."""


def grade(item: dict, reply: str, model: str) -> dict:
    k = item["key"]
    with tempfile.TemporaryDirectory() as t:
        out = claude(GRADER.format(location=k["location"], error_class=k["error_class"],
                                   catch=k["catch"], reply=reply[:12000]), Path(t),
                     ["--model", model, "--tools", ""], timeout=300)
    return parse_grade(out.get("result", ""))


CONTROL_GRADER = """You sort one reviewer's objections to a proof. You do not judge the mathematics
yourself.

The reviewer failed the proof and marked at least one issue major. Slips already known to be
in the text (real, but not what the proof stands or falls on):
{known}

The reviewer's reply:
<<<
{reply}
>>>

Look only at the issues the reply marks major (or, if it ranks nothing, its headline
defects). Output only a JSON object on one line:
{{"class": "wrong" | "gap" | "known-slip" | "uncited" | "minor-only", "why": "<one sentence>"}}
Take the first that applies:
- "minor-only": the reply in fact marks no issue major (it says none is, or it rates every
  issue minor), so there is nothing to sort.
- "wrong": some major issue, not one of the known slips, says a claim or step is false
  (gives a counterexample, or says it fails).
- "gap": some major issue, not one of the known slips, says a step of the argument does not
  follow as written (an inference left unjustified, a case not covered), without saying
  its conclusion is false.
- "known-slip": some major issue names a known slip.
- "uncited": every major issue only asks for a source, a citation, or a proof of a fact the
  text asserts or cites (a lemma, a standard result), not of a step of the argument."""


def known_slips(item: dict) -> str:
    k = item["key"]
    slips = [str(v) for f, v in sorted(k.items()) if f == "also" or f.startswith("also_")]
    return "\n".join(f"- {x}" for x in slips) or "- none"


def grade_control(item: dict, reply: str, model: str) -> dict:
    """A control's major-issue rejection, sorted: `wrong` (claims an error) or `gap` (claims
    a step does not follow), which count as false alarms unless the claim proves real;
    `known-slip`; or `uncited` (a demand for a source the text does not give, which the
    referee's rules require but a published proof often lacks)."""
    with tempfile.TemporaryDirectory() as t:
        out = claude(CONTROL_GRADER.format(known=known_slips(item), reply=reply[:12000]), Path(t),
                     ["--model", model, "--tools", ""], timeout=300)
    text = out.get("result", "")
    m = re.search(r'"class"\s*:\s*"(wrong|gap|known-slip|uncited|minor-only)"', text)
    return {"class": m.group(1) if m else "ungraded", "why": text.strip()[:300]}


def split_named(g: dict, passed: bool) -> dict:
    """A reply that names the keyed flaw without failing the text for it: `seen` when its
    verdict passes, `noted` when it fails the text but marks the flaw minor. A failing
    verdict blocks the gate whatever the severity, so `keyed` + `noted` is the catch the gate
    enforces; `keyed` alone is the strict one."""
    if passed:
        g["class"] = {"keyed": "seen", "noted": "seen", "other": "pass"}.get(g["class"], g["class"])
    return g


def parse_grade(text: str) -> dict:
    """The grader's class word; its "why" may itself hold braces ({1, 2}), so do not parse JSON."""
    m = re.search(r'"class"\s*:\s*"(keyed|noted|other|pass)"', text)
    return {"class": m.group(1) if m else "ungraded", "why": text.strip()[:300]}


def base_project(out: Path) -> Path:
    base = out / "base"
    if not base.exists():
        r = subprocess.run([sys.executable, str(INIT), "--answers", str(FIXTURE), "--out", str(base),
                            "--no-selftest"], capture_output=True, text=True, env=env(), timeout=600)
        if r.returncode != 0:
            raise SystemExit(f"init failed:\n{r.stdout}{r.stderr}")
    return base


def run_one(item: dict, reviewer: str, arm: str, k: int, out: Path, model: str | None,
            grader: str, gs) -> dict:
    proj = out / "runs" / f"{reviewer}-{arm}" / item["id"] / f"run{k}"
    if proj.exists():
        shutil.rmtree(proj)
    shutil.copytree(base_project(out), proj, symlinks=True)
    # `--agent` makes the reviewer the main session, so SessionStart hooks fire; the coordinator
    # hook (2026-10-31) would hand it COORDINATOR.md, which a dispatched reviewer never gets
    # (HOOKS_QUIET does not silence it). Drop SessionStart so the run sees what a dispatch sees.
    settings = proj / ".claude" / "settings.json"
    if settings.exists():
        conf = json.loads(settings.read_text(encoding="utf-8"))
        if conf.get("hooks", {}).pop("SessionStart", None) is not None:
            settings.write_text(json.dumps(conf, indent=2) + "\n", encoding="utf-8")
    if arm in ("any-defect", "two-verdict"):
        agent = proj / ".claude" / "agents" / f"{reviewer}.md"
        text = agent.read_text(encoding="utf-8")
        if text.count(VERDICT_LINE) != 1:
            raise SystemExit(f"{arm}: the verdict line is not in {agent}")
        agent.write_text(text.replace(VERDICT_LINE, ANY_DEFECT if arm == "any-defect" else TWO_VERDICT),
                         encoding="utf-8")
    if arm == "minor-anchor":
        agent = proj / ".claude" / "agents" / f"{reviewer}.md"
        text = agent.read_text(encoding="utf-8")
        if text.count(SEVERITY) != 1:
            raise SystemExit(f"minor-anchor: the severity line is not in {agent}")
        agent.write_text(text.replace(SEVERITY, SEVERITY_ANCHORED), encoding="utf-8")
    if arm == "one-crux":
        agent = proj / ".claude" / "agents" / f"{reviewer}.md"
        text = agent.read_text(encoding="utf-8")
        if text.count(MULTI_CRUX) != 1 or text.count(MULTI_CRUX_END) != 1:
            raise SystemExit(f"one-crux: check 0's multi-crux wording is not in {agent}")
        agent.write_text(text.replace(MULTI_CRUX, ONE_CRUX).replace(MULTI_CRUX_END, ONE_CRUX_END),
                         encoding="utf-8")
    d = proj / "work" / slug(item)
    d.mkdir(parents=True, exist_ok=True)
    (d / "proof.md").write_text(item["text"], encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=proj, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "a proof for review", "--no-verify"], cwd=proj, capture_output=True)
    pre, pre_cost = prelude(item, arm, model)
    for name, text in pre.items():
        (proj.parent / f"run{k}.{name}.md").write_text(text, encoding="utf-8")
    extra = ["--agent", reviewer, "--tools", ",".join(TOOLS[reviewer]), "--allowedTools", *TOOLS[reviewer]] + (["--model", model] if model else [])
    res = claude(brief(item, reviewer, arm, pre), proj, extra)
    reply = res.get("result", "")
    v = verdict(reviewer, reply)
    passed = v in WORDS[reviewer][0]
    row = {"item": item["id"], "local": item["local"], "kind": item["key"]["kind"], "reviewer": reviewer,
           "arm": arm, "run": k, "verdict": v, "seconds": res.get("seconds"),
           "cost_usd": res.get("total_cost_usd"), "pre_cost_usd": round(pre_cost, 4) if pre else None,
           "turns": res.get("num_turns"),
           "models": sorted((res.get("modelUsage") or {}).keys()), "error": res.get("error"),
           "caveat_pass": bool(passed and gs.caveat_lines(proj, reply)),
           # Severity drift and the cite-check arm's cost: issue lines marked major, and doubts
           # raised about a cited statement without refuting it.
           "majors": sum(bool(MAJOR.search(l)) for l in reply.splitlines()),
           "doubts": len(DOUBT.findall(reply))}
    if res.get("error") == "usage limit" or pre.get("error"):
        row["class"], row["error"] = "error", "usage limit"
    elif item["key"]["kind"] == "flawed":
        g = split_named(grade(item, reply, grader), passed)
        if v == "no-verdict" and g.get("class") == "pass":
            g["class"] = "no-verdict"
        row["class"], row["why"] = g.get("class"), g.get("why")
    else:
        # On a control, a non-pass counts as an alarm only if some issue is marked major: a
        # referee returns NEEDS-WORK for minor polish too, which is strictness, not error.
        row["class"] = ("pass" if passed else "no-verdict" if v == "no-verdict"
                        else "major" if MAJOR.search(reply) else "minor-only")
        if row["class"] == "major":
            g = grade_control(item, reply, grader)
            row["class"], row["why"] = g["class"], g["why"]
    (proj.parent / f"run{k}.reply.md").write_text(reply, encoding="utf-8")
    return row


def screen_prompt(item: dict, arm: str, pre: dict) -> str:
    """The plain reread's question, with an arm's additions: the reader's own attempt before
    the proof (`rival`), both sides after it (`debate`), or the pre-mortem before deciding."""
    ask = "Is this proof correct? Answer CORRECT or INCORRECT on the first line, then say why."
    if arm == "premortem":
        ask += (" Before you decide, suppose the proof is later found to be wrong, and check first the "
                "three places the error is most likely to be; name them in your reasons.")
    parts = [ask, f"Claim: {item['statement']}"]
    if arm == "rival":
        parts.append("Your own earlier attempt at this claim, made from the statement alone before you "
                     "saw the proof:\n<<<\n" + pre["rival"].strip() + "\n>>>\n\nThe proof:")
    parts.append(item["text"])
    if arm == "debate":
        parts.append("Two readers argued opposite verdicts on this proof. Neither is authoritative: weigh "
                     "each against the text and decide yourself.\nDEFENSE:\n<<<\n" + pre["defense"].strip()
                     + "\n>>>\nPROSECUTION:\n<<<\n" + pre["prosecution"].strip() + "\n>>>")
    return "\n\n".join(parts)


def screen_one(item: dict, k: int, out: Path, model: str | None, grader: str, arm: str = "plain") -> dict:
    pre, pre_cost = prelude(item, arm, model)
    with tempfile.TemporaryDirectory() as t:
        res = claude(screen_prompt(item, arm, pre), Path(t), ["--tools", ""] + (["--model", model] if model else []),
                     timeout=1500)
    reply = res.get("result", "")
    lines = reply.strip().splitlines()
    bare = [l for l in lines if re.fullmatch(r"\W*(IN)?CORRECT\W*", l.strip())]
    first = lines[0] if lines and re.search(r"\bCORRECT\b|\bINCORRECT\b", lines[0]) else (bare or [""])[0]
    passed = bool(re.search(r"\bCORRECT\b", first)) and "INCORRECT" not in first
    if res.get("error") == "usage limit" or pre.get("error"):
        g = {"class": "error", "why": "usage limit"}
    elif item["key"]["kind"] == "flawed":
        g = split_named(grade(item, reply, grader), passed)
    else:
        g = {"class": "pass", "why": first[:120]} if passed else grade_control(item, reply, grader)
    name = "screen" if arm == "plain" else f"screen-{arm}"
    d = out / name / item["id"]
    d.mkdir(parents=True, exist_ok=True)
    (d / f"run{k}.reply.md").write_text(reply, encoding="utf-8")
    for part, text in pre.items():
        (d / f"run{k}.{part}.md").write_text(text, encoding="utf-8")
    return {"item": item["id"], "local": item["local"], "kind": item["key"]["kind"], "reviewer": "plain-reread",
            "arm": name, "run": k, "passed": passed, "class": g.get("class"), "why": g.get("why"),
            "seconds": res.get("seconds"), "cost_usd": res.get("total_cost_usd"),
            "pre_cost_usd": round(pre_cost, 4) if pre else None}


def statement_one(item: dict, k: int, out: Path, model: str | None) -> dict:
    """Diagnostic: the statement alone, no proof. A false statement recognized from recall is
    caught without reading the proof, so a catch on such an item measures memory."""
    with tempfile.TemporaryDirectory() as t:
        res = claude(f"Is this statement true? Answer TRUE, FALSE or UNSURE on the first line, then say why "
                     f"briefly.\n\n{item['statement']}", Path(t),
                     ["--tools", ""] + (["--model", model] if model else []), timeout=300)
    first = (res.get("result", "").strip().splitlines() or [""])[0].upper()
    word = next((w for w in ("UNSURE", "FALSE", "TRUE") if w in first), "none")
    return {"item": item["id"], "local": item["local"], "kind": item["key"]["kind"], "reviewer": "statement-only",
            "arm": "statements", "run": k, "class": word.lower(), "seconds": res.get("seconds"),
            "cost_usd": res.get("total_cost_usd")}


def needs_review() -> dict[str, bool]:
    """Item id -> its key's `fix_needs_review`. Where that is false an expert could fix the flaw
    unreviewed, so `minor` is the right rating and the catch is `keyed` + `noted`."""
    items = tomllib.loads(MANIFEST.read_text(encoding="utf-8"))["item"]
    return {it["id"]: it["fix_needs_review"] for it in items if "fix_needs_review" in it}


def report(rows: list[dict]) -> None:
    errors = [r for r in rows if r["class"] == "error"]
    if errors:
        print(f"{len(errors)} runs left out (usage limit): "
              + ", ".join(f"{r['item']} {r['arm']} run{r['run']}" for r in errors))
    rows = [r for r in rows if r["class"] != "error"]
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        groups.setdefault((r["reviewer"], r["arm"]), []).append(r)
    for (rev, arm), rs in sorted(groups.items()):
        print(f"\n{rev} / {arm}: {len(rs)} runs, {len({r['item'] for r in rs})} items")
        if rev == "statement-only":
            byi = {}
            for r in rs:
                byi.setdefault((r["kind"], r["item"]), []).append(r["class"])
            for (kind, item), cls in sorted(byi.items()):
                print(f"    {kind:<8} {item}: {' '.join(cls)}")
            continue
        # A control's false alarm is a major issue saying the argument fails (`wrong`, `gap`);
        # rows from before the control grader say `alarm` (any major issue).
        for kind, hit in (("flawed", ("keyed",)), ("control", ("wrong", "gap", "alarm"))):
            per = {}
            for r in rs:
                if r["kind"] == kind:
                    per.setdefault(r["item"], []).append(1.0 if r["class"] in hit else 0.0)
            if not per:
                continue
            means = [sum(v) / len(v) for v in per.values()]
            rate = sum(means) / len(means)
            se = statistics.stdev(means) / math.sqrt(len(means)) if len(means) > 1 else float("nan")
            mde = 2.8 * math.sqrt(2) * se
            label = "catch rate" if kind == "flawed" else "false-alarm rate"
            print(f"  {label}: {rate:.2f} over {len(means)} items (SE clustered by item {se:.2f}; "
                  f"a difference between two arms below about {mde:.2f} is not detectable)")
            for item, v in sorted(per.items()):
                print(f"    {item}: {sum(v):.0f}/{len(v)}")
        fl = [r for r in rs if r["kind"] == "flawed"]
        if fl:
            named = sum(r["class"] in ("keyed", "noted") for r in fl)
            print(f"  flaw named in a failing reply (keyed + noted, the catch the gate enforces): "
                  f"{named}/{len(fl)} runs")
            nr = needs_review()
            sized = [r for r in fl if r["item"] in nr]
            if sized:
                hit = sum(r["class"] == "keyed" or (r["class"] == "noted" and not nr[r["item"]])
                          for r in sized)
                print(f"  catch by flaw size (keyed where the fix needs review, else keyed + noted): "
                      f"{hit}/{len(sized)} runs over {len({r['item'] for r in sized})} items")
        for cls, what in (("noted", "named but marked minor in a failing reply"),
                          ("seen", "named in a passing reply")):
            hits = [r for r in rs if r["class"] == cls]
            if hits:
                print(f"  {cls} ({what}): " + ", ".join(f"{r['item']} run{r['run']}" for r in hits))
        other = [r for r in rs if r["class"] in ("other", "no-verdict", "ungraded", "minor-only",
                                                 "uncited", "known-slip", "wrong", "gap")]
        if other:
            print("  other classes: " + ", ".join(f"{r['item']} run{r['run']} {r['class']}" for r in other))
        cav = [r for r in rs if r.get("caveat_pass")]
        if cav:
            print(f"  passes carrying a caveat phrase: {len(cav)}")
        secs = [r["seconds"] for r in rs if r.get("seconds")]
        cost = [r["cost_usd"] for r in rs if r.get("cost_usd")]
        if secs:
            print(f"  seconds per run: median {statistics.median(secs):.0f}; cost per run: "
                  f"{(sum(cost) / len(cost)) if cost else float('nan'):.3f} USD")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("mode", choices=("run", "screen", "statements", "report", "regrade"))
    ap.add_argument("dirs", nargs="*", help="report: result directories")
    ap.add_argument("--reviewer", choices=sorted(WORDS), default="proof-referee")
    ap.add_argument("--arm", choices=ARMS, default="plain")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--items", default=str(ITEMS))
    ap.add_argument("--only", nargs="*", help="item ids")
    ap.add_argument("--local", help="extra items outside the repository")
    ap.add_argument("--out")
    ap.add_argument("--model")
    ap.add_argument("--grader", default="sonnet")
    ap.add_argument("--flawed", action="store_true", help="regrade: re-grade flawed rows too")
    ap.add_argument("--from-commit", metavar="REV",
                    help="review with the project init-math generated at REV (a git worktree under "
                         "--out); the bench, its items and its grader stay current")
    a = ap.parse_args(argv)
    if a.from_commit and a.mode != "report":
        global INIT, FIXTURE
        if not a.out:
            ap.error("--from-commit needs --out")
        wt = Path(a.out) / f"init-math-at-{a.from_commit}"
        if not wt.exists():
            wt.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "worktree", "add", "--detach", "-q", str(wt), a.from_commit],
                           cwd=ROOT, check=True)
        INIT, FIXTURE = wt / INIT.relative_to(ROOT), wt / FIXTURE.relative_to(ROOT)
    if a.mode == "regrade":
        # Re-sort the controls' major-issue rejections of finished runs with the control
        # grader, from the saved replies, and with --flawed re-grade flawed rows (a grader
        # change, such as the `noted` class); the old class is kept as `class_before`.
        items = {i["id"]: i for i in load_items([Path(a.items)] + ([Path(a.local)] if a.local else []))}
        for d in map(Path, a.dirs):
            rows = [json.loads(l) for l in (d / "results.jsonl").read_text().splitlines() if l]
            for r in rows:
                ctl = r["kind"] == "control" and r["class"] in (
                    "alarm", "major", "wrong", "gap", "known-slip", "uncited", "ungraded")
                flw = a.flawed and r["kind"] == "flawed" and r["class"] != "no-verdict"
                if r["item"] in items and (ctl or flw):
                    sub = (d / r["arm"] / r["item"] if r["arm"].startswith("screen")
                           else d / "runs" / f"{r['reviewer']}-{r['arm']}" / r["item"])
                    reply = (sub / f"run{r['run']}.reply.md").read_text(encoding="utf-8")
                    if ctl:
                        # A reread reply ranks nothing, so only a reviewer's reply needs a major issue.
                        g = (grade_control(items[r["item"]], reply, a.grader)
                             if r["arm"].startswith("screen") or MAJOR.search(reply)
                             else {"class": "minor-only", "why": "no issue marked major"})
                    else:
                        passed = (r["verdict"] in WORDS[r["reviewer"]][0] if "verdict" in r
                                  else r.get("passed", r.get("class_before", r["class"]) in ("pass", "seen")))
                        g = split_named(grade(items[r["item"]], reply, a.grader), passed)
                    r.setdefault("class_before", r["class"])
                    r["class"], r["why"] = g["class"], g["why"]
                    print(f"{d.name} {r['item']} run{r['run']}: {r['class_before']} -> {r['class']}", flush=True)
            (d / "results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        report([json.loads(l) for d in a.dirs for l in (Path(d) / "results.jsonl").read_text().splitlines() if l])
        return 0
    if a.mode == "report":
        rows = [json.loads(l) for d in a.dirs for l in (Path(d) / "results.jsonl").read_text().splitlines() if l]
        report(rows)
        return 0
    dirs = [Path(a.items)] + ([Path(a.local)] if a.local else [])
    items = [i for i in load_items(dirs) if not a.only or i["id"] in a.only]
    missing = set(a.only or ()) - {i["id"] for i in items}
    if missing:
        raise SystemExit(f"no such item: {' '.join(sorted(missing))}")
    out = Path(a.out or tempfile.mkdtemp(prefix=f"init-math-bench-{time.strftime('%Y%m%d-%H%M%S')}-"))
    out.mkdir(parents=True, exist_ok=True)
    gs = _gate_stamp()
    with open(out / "results.jsonl", "a", encoding="utf-8") as f:
        for item in items:
            for k in range(1, a.runs + 1):
                row = (screen_one(item, k, out, a.model, a.grader, a.arm) if a.mode == "screen"
                       else statement_one(item, k, out, a.model) if a.mode == "statements"
                       else run_one(item, a.reviewer, a.arm, k, out, a.model, a.grader, gs))
                f.write(json.dumps(row) + "\n")
                f.flush()
                print(f"{row['item']} run{k}: {row.get('verdict', '')} {row['class']} "
                      f"({row.get('seconds')}s)", flush=True)
    report([json.loads(l) for l in (out / "results.jsonl").read_text().splitlines() if l])
    print(f"\nresults: {out / 'results.jsonl'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
