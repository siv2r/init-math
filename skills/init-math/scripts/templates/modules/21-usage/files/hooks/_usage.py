"""Read token counts out of a harness's own session records (stdlib only).

Shared by hooks/usage-log.py (which copies counts as the work happens) and bin/usage-report
(which summarizes them and can import older sessions). Only COUNTS leave a transcript: the
model name, token numbers, a timestamp, the session id and the agent type. Message text,
tool calls and briefs are never read into a row.

Two transcript formats, recognized per file by its first line:

  Claude Code  one JSON object per line; an assistant line carries message.id,
               message.model and message.usage {input_tokens, output_tokens,
               cache_read_input_tokens, cache_creation_input_tokens}. One API response is
               written as several lines with the same message.id, so responses are counted
               once per id. Subagents write their own files under
               <session>/subagents/agent-<id>.jsonl, with the agent type in a sibling
               agent-<id>.meta.json (`agentType`).
  Codex CLI    a "rollout": first line {"type": "session_meta", "payload": {id, session_id,
               cwd, ...}}; a subagent's rollout says so in that line (thread_source
               "subagent", agent_role, parent_thread_id) and carries the PARENT's session_id.
               `token_usage_record` lines carry one response's usage (payload.usage,
               payload.response_id, payload.thread_id); `turn_context` lines carry the model;
               `event_msg` lines of type `token_count` carry cumulative totals and the plan's
               rate limits. Undocumented format: everything is read defensively.

Normalized counts (the same meaning on both harnesses, so one price table works):
  input        input tokens NOT served from or written to the prompt cache
  cache_read   input tokens served from the cache
  cache_write  input tokens written to the cache
  output       output tokens, INCLUDING reasoning tokens
  reasoning    reasoning tokens (Codex only; already inside `output`, never add them)
Codex reports input_tokens as the total including cached tokens, so input is
input_tokens - cached_input_tokens - cache_write_input_tokens (never below 0).

Each row also keeps `peak_context`: the largest prompt (input + cache_read + cache_write)
of any one response in it, which is how full the context was at that call. It is a maximum,
not a sum; the report compares it with the auto-compaction limit.

Rows are aggregated per (transcript, role, agent type, model, UTC day) for each read, so the
committed log grows by a few rows per turn, not one per response. Each row records how far
into its transcript it read (`src`, `upto`), which is what keeps re-reads from counting twice.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
from contextlib import contextmanager
from pathlib import Path

RECENT = 64  # ids remembered per transcript across reads (a response split over two reads)
COUNTS = ("input", "output", "cache_read", "cache_write", "reasoning")


# --- small helpers -----------------------------------------------------------

def _int(x) -> int:
    try:
        return max(0, int(x or 0))
    except (TypeError, ValueError):
        return 0


def norm_ts(ts) -> str:
    """'2026-10-08T16:29:37.078Z' -> '2026-10-08T16:29:37Z' (UTC as the harness wrote it)."""
    s = str(ts or "")
    m = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", s)
    if not m:
        return ""
    return m.group(1) + ("Z" if s.endswith("Z") or "+00:00" in s or "." in s else "")


def detect_format(path: Path) -> str:
    """'codex' if the first line is a session_meta record, else 'claude'."""
    try:
        with open(path, "rb") as f:
            first = f.readline(1 << 20)
        d = json.loads(first)
        return "codex" if isinstance(d, dict) and d.get("type") == "session_meta" else "claude"
    except (OSError, ValueError):
        return "claude"


def read_chunk(path: Path, offset: int) -> tuple[list[tuple[int, str]], int]:
    """Complete lines from byte `offset` on, as (end offset, text), and the new offset.
    A partial last line (still being written) is left for the next read. A file shorter
    than `offset` (rewritten or replaced) is read from the start."""
    size = path.stat().st_size
    if size < offset:
        offset = 0
    out: list[tuple[int, str]] = []
    pos = offset
    with open(path, "rb") as f:
        f.seek(offset)
        for raw in f:
            if not raw.endswith(b"\n"):
                break
            pos += len(raw)
            out.append((pos, raw.decode("utf-8", errors="replace")))
    return out, pos


# --- Claude Code ------------------------------------------------------------------

def claude_agent_type(path: Path) -> str:
    meta = path.with_name(path.name[: -len(".jsonl")] + ".meta.json") if path.name.endswith(".jsonl") else None
    if meta and meta.exists():
        try:
            return str(json.loads(meta.read_text(encoding="utf-8")).get("agentType") or "")
        except (OSError, ValueError):
            return ""
    return ""


def parse_claude(path: Path, offset: int, st: dict, hint_type: str = "") -> tuple[list[dict], int, list[str]]:
    """Per-response records after `offset`; updates st['recent']. Returns (records, offset, problems)."""
    lines, new_off = read_chunk(path, offset)
    recent = list(st.get("recent") or [])
    seen = set(recent)
    in_subdir = path.parent.name == "subagents"
    atype = claude_agent_type(path) if in_subdir else ""
    by_id: dict[str, dict] = {}
    assistant_lines = with_usage = bad_usage = 0
    for _, line in lines:
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if not isinstance(d, dict) or d.get("type") != "assistant":
            continue
        assistant_lines += 1
        m = d.get("message")
        if not isinstance(m, dict) or not isinstance(m.get("usage"), dict):
            continue
        with_usage += 1
        model = str(m.get("model") or "")
        if not model or model.startswith("<"):  # "<synthetic>": a harness-made message, no API call
            continue
        u = m["usage"]
        if "input_tokens" not in u and "output_tokens" not in u:
            bad_usage += 1
            continue
        mid = str(m.get("id") or d.get("requestId") or d.get("uuid") or "")
        if not mid or mid in seen:
            continue
        sub = in_subdir or bool(d.get("isSidechain"))
        rec = {
            "id": mid, "ts": norm_ts(d.get("timestamp")), "model": model,
            "session": str(d.get("sessionId") or (path.parent.parent.name if in_subdir else path.stem)),
            "role": "subagent" if sub else "main",
            "agent_type": (atype or hint_type) if sub else "",
            "input": _int(u.get("input_tokens")), "output": _int(u.get("output_tokens")),
            "cache_read": _int(u.get("cache_read_input_tokens")),
            "cache_write": _int(u.get("cache_creation_input_tokens")), "reasoning": 0,
        }
        old = by_id.get(mid)
        if old:  # the same response written over several lines: count it once
            for k in COUNTS:
                old[k] = max(old[k], rec[k])
            old["ts"] = rec["ts"] or old["ts"]
        else:
            by_id[mid] = rec
    for mid in by_id:
        recent.append(mid)
    st["recent"] = recent[-RECENT:]
    problems = []
    if assistant_lines and not with_usage:
        problems.append(f"{assistant_lines} assistant lines but none carries message.usage")
    elif bad_usage:
        problems.append(f"{bad_usage} usage records without input_tokens/output_tokens")
    return list(by_id.values()), new_off, problems


def _safe(line: str):
    try:
        return json.loads(line)
    except ValueError:
        return None


# --- Codex CLI ------------------------------------------------------------------------

def codex_identity(path: Path) -> dict | None:
    """From the rollout's FIRST line only (a subagent's rollout repeats its parent's
    session_meta on later lines)."""
    try:
        with open(path, "rb") as f:
            d = json.loads(f.readline(1 << 22))
    except (OSError, ValueError):
        return None
    p = d.get("payload") if isinstance(d, dict) and d.get("type") == "session_meta" else None
    if not isinstance(p, dict):
        return None
    src = p.get("source")
    spawn = (src.get("subagent") or {}).get("thread_spawn") if isinstance(src, dict) else None
    sub = p.get("thread_source") == "subagent" or bool(p.get("parent_thread_id")) or bool(spawn)
    role = p.get("agent_role") or (spawn or {}).get("agent_role") or ""
    tid = str(p.get("id") or "")
    return {"thread": tid, "session": str(p.get("session_id") or tid), "cwd": str(p.get("cwd") or ""),
            "role": "subagent" if sub else "main", "agent_type": str(role) if sub else "",
            "cli_version": str(p.get("cli_version") or "")}


def _codex_prefix(path: Path, offset: int) -> dict:
    """What a lost state would have said at `offset`: the model of the last turn_context,
    whether per-response records exist, and the last cumulative totals."""
    out = {"model": "", "has_records": False, "cum": {}}
    with open(path, "rb") as f:
        pos = 0
        for raw in f:
            pos += len(raw)
            if pos > offset:
                break
            if b'"turn_context"' in raw or b'"token_count"' in raw:
                d = _safe(raw.decode("utf-8", errors="replace"))
                p = d.get("payload") if isinstance(d, dict) else None
                if not isinstance(p, dict):
                    continue
                if d.get("type") == "turn_context":
                    out["model"] = str(p.get("model") or out["model"])
                elif isinstance((p.get("info") or {}).get("total_token_usage"), dict):
                    tot = p["info"]["total_token_usage"]
                    out["cum"] = {k: _int(tot.get(k)) for k in CODEX_CUM}
            elif b'"token_usage_record"' in raw:
                out["has_records"] = True
    return out


CODEX_CUM = ("input_tokens", "cached_input_tokens", "cache_write_input_tokens",
             "output_tokens", "reasoning_output_tokens")


def parse_codex(path: Path, offset: int, st: dict, hint_model: str = "") -> tuple[list[dict], dict | None, int, list[str]]:
    """Per-response records after `offset`, the latest plan limits seen, the new offset,
    problems. Updates st['recent'], st['model'], st['cum']."""
    ident = codex_identity(path)
    if ident is None:
        return [], None, offset, ["first line is not a session_meta record with an id"]
    if offset and "has_records" not in st:  # state was lost: rebuild it from the prefix
        st.update(_codex_prefix(path, offset))
    lines, new_off = read_chunk(path, offset)
    model = st.get("model") or ""
    recent = list(st.get("recent") or [])
    seen = set(recent)
    recs: list[dict] = []
    limits = None
    cum_recs: list[dict] = []  # fallback: deltas of the cumulative totals
    cum = dict(st.get("cum") or {})
    activity = 0
    for _, line in lines:
        d = _safe(line)
        if not isinstance(d, dict):
            continue
        t = d.get("type")
        p = d.get("payload") if isinstance(d.get("payload"), dict) else {}
        if t == "turn_context":
            model = str(p.get("model") or model)
        elif t == "response_item":
            activity += 1
        elif t == "token_usage_record":
            if p.get("thread_id") and ident["thread"] and p["thread_id"] != ident["thread"]:
                continue  # copied from another thread's history
            u = p.get("usage")
            if not isinstance(u, dict):
                continue
            rid = str(p.get("response_id") or f"{ident['thread']}:{d.get('ordinal', '')}:{d.get('timestamp', '')}")
            if rid in seen:
                continue
            seen.add(rid)
            recs.append(_codex_rec(rid, d.get("timestamp"), model or hint_model, ident, u))
            st["has_records"] = True
        elif t == "event_msg" and p.get("type") == "token_count":
            info = p.get("info") if isinstance(p.get("info"), dict) else {}
            tot = info.get("total_token_usage")
            if isinstance(tot, dict):
                delta = {k: _int(tot.get(k)) - _int(cum.get(k)) for k in CODEX_CUM}
                if any(v < 0 for v in delta.values()):  # totals went backwards: a new count
                    delta = {k: _int(tot.get(k)) for k in delta}
                cum = {k: _int(tot.get(k)) for k in delta}
                if any(delta.values()):
                    cum_recs.append(_codex_rec(f"{ident['thread']}:cum:{cum.get('output_tokens')}:"
                                               f"{cum.get('input_tokens')}", d.get("timestamp"),
                                               model or hint_model, ident, delta))
            rl = p.get("rate_limits")
            if isinstance(rl, dict):
                limits = _limits(rl, d.get("timestamp"), ident)
    st["cum"] = cum
    st["model"] = model
    problems = []
    if not st.get("has_records"):  # a Codex without per-response records: use total deltas
        recs = [r for r in cum_recs if r["id"] not in seen]
        st.setdefault("has_records", False)
    for r in recs:
        recent.append(r["id"])
    st["recent"] = recent[-RECENT:]
    if activity and not recs and not cum_recs and limits is None:
        problems.append("no token_usage_record and no token_count totals after "
                        f"{activity} response items (format changed?)")
    return recs, limits, new_off, problems


def _codex_rec(rid: str, ts, model: str, ident: dict, u: dict) -> dict:
    total_in = _int(u.get("input_tokens"))
    cr, cw = _int(u.get("cached_input_tokens")), _int(u.get("cache_write_input_tokens"))
    return {"id": rid, "ts": norm_ts(ts), "model": model or "unknown", "session": ident["session"],
            "role": ident["role"], "agent_type": ident["agent_type"],
            "input": max(0, total_in - cr - cw), "output": _int(u.get("output_tokens")),
            "cache_read": cr, "cache_write": cw, "reasoning": _int(u.get("reasoning_output_tokens"))}


def _limits(rl: dict, ts, ident: dict) -> dict:
    row = {"kind": "limits", "harness": "codex", "session": ident["session"], "ts": norm_ts(ts),
           "plan": str(rl.get("plan_type") or "")}
    for w in ("primary", "secondary"):
        x = rl.get(w)
        if isinstance(x, dict):
            row[f"{w}_used_pct"] = x.get("used_percent")
            row[f"{w}_window_min"] = x.get("window_minutes")
            row[f"{w}_resets_at"] = x.get("resets_at")
    return row


# --- aggregation, the log, the state ------------------------------------------------

def aggregate(recs: list[dict], harness: str, src: str, upto: int) -> list[dict]:
    groups: dict[tuple, dict] = {}
    for r in recs:
        key = (r["session"], r["role"], r["agent_type"], r["model"], r["ts"][:10])
        g = groups.get(key)
        if g is None:
            g = groups[key] = {"kind": "usage", "harness": harness, "session": r["session"],
                               "role": r["role"], "agent_type": r["agent_type"], "model": r["model"],
                               "calls": 0, **{k: 0 for k in COUNTS}, "peak_context": 0,
                               "ts": r["ts"], "src": src, "upto": upto}
        g["calls"] += 1
        for k in COUNTS:
            g[k] += r[k]
        g["peak_context"] = max(g["peak_context"], r["input"] + r["cache_read"] + r["cache_write"])
        if r["ts"] > g["ts"]:
            g["ts"] = r["ts"]
    return [groups[k] for k in sorted(groups)]


def src_of(path: Path) -> str:
    return path.name[: -len(".jsonl")] if path.name.endswith(".jsonl") else path.name


def read_rows(root: Path) -> list[dict]:
    p = root / "logs" / "usage.jsonl"
    rows, seen = [], set()
    if not p.exists():
        return rows
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip() or line in seen:  # a union merge can duplicate a line
            continue
        seen.add(line)
        d = _safe(line)
        if isinstance(d, dict):
            rows.append(d)
    return rows


def logged_upto(root: Path) -> dict[str, int]:
    """How far each transcript (by src) has been read, according to the committed log."""
    out: dict[str, int] = {}
    for r in read_rows(root):
        if r.get("kind", "usage") == "usage" and r.get("src"):
            out[r["src"]] = max(out.get(r["src"], 0), _int(r.get("upto")))
    return out


def append_rows(root: Path, rows: list[dict]) -> None:
    if not rows:
        return
    d = root / "logs"
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "usage.jsonl", "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True) + "\n")


def state_path(root: Path) -> Path:
    d = root / "logs" / "state"
    d.mkdir(parents=True, exist_ok=True)
    return d / "usage-offsets.json"


def load_state(root: Path) -> dict:
    p = state_path(root)
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except ValueError:
        return {}  # a corrupt cache: the log's own src/upto still prevents double counting


def save_state(root: Path, st: dict) -> None:
    p = state_path(root)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, p)


@contextmanager
def locked(root: Path):
    """One reader at a time (a Stop and a SubagentStop can fire together)."""
    lf = open(state_path(root).with_name("usage.lock"), "a")
    try:
        fcntl.flock(lf, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(lf, fcntl.LOCK_UN)
        lf.close()


def collect(root: Path, items: list[tuple[Path, str]], hint_model: str = "",
            check_log: bool = False) -> tuple[list[dict], list[str]]:
    """Read every transcript in `items` ((path, agent type hint) pairs) from where the last
    read stopped, append the new rows to logs/usage.jsonl and advance the state.
    Where the last read stopped is the state's offset for that path; when the state does
    not know the path, or `check_log` is set (a backfill, which may read a COPY of a
    transcript the hook already read), it is also at least the furthest `upto` the log
    records for that transcript's name. Returns (rows written, problems)."""
    written: list[dict] = []
    problems: list[str] = []
    with locked(root):
        state = load_state(root)
        files = state.setdefault("files", {})
        log_upto = None
        done = set()
        for path, hint_type in items:
            path = Path(path)
            if not path.is_file() or path.resolve() in done:
                continue
            done.add(path.resolve())
            key = str(path.resolve())
            st = files.get(key)
            if st is None or check_log:
                if log_upto is None:
                    log_upto = logged_upto(root)
                st = st or {}
                logged = log_upto.get(src_of(path), 0)
                if logged > _int(st.get("offset")) and logged <= path.stat().st_size:
                    st = {"offset": logged}  # read elsewhere: the per-path memory is stale
            off = _int(st.get("offset"))
            if path.stat().st_size == off:
                files[key] = st
                continue
            fmt = detect_format(path)
            if fmt == "codex":
                recs, limits, new_off, probs = parse_codex(path, off, st, hint_model)
            else:
                recs, new_off, probs = parse_claude(path, off, st, hint_type)
                limits = None
            rows = aggregate(recs, fmt, src_of(path), new_off)
            if limits:
                sig = json.dumps({k: v for k, v in limits.items() if k not in ("ts", "session")}, sort_keys=True)
                if sig != st.get("limits_sig"):
                    st["limits_sig"] = sig
                    rows.append(limits)
            append_rows(root, rows)
            written += rows
            st["offset"] = new_off
            if log_upto is not None and any(r["kind"] == "usage" for r in rows):
                log_upto[src_of(path)] = max(log_upto.get(src_of(path), 0), new_off)
            if probs and not st.get("warned"):  # warn once per transcript
                st["warned"] = True
                problems.append(f"{path.name} ({fmt}): {probs[0]}")
            files[key] = st
        for k in [k for k in files if not Path(k).exists()]:
            del files[k]  # the harness deleted that transcript
        save_state(root, state)
    return written, problems


# --- where a harness keeps its transcripts --------------------------------------------

def claude_store(root: Path) -> list[Path]:
    """~/.claude/projects/<project path with every non-alphanumeric character as '-'>/."""
    base = Path(os.environ.get("CLAUDE_CONFIG_DIR") or (Path.home() / ".claude")) / "projects"
    out = []
    for p in {str(root), str(root.resolve())}:
        d = base / re.sub(r"[^A-Za-z0-9]", "-", p)
        if d.is_dir() and d not in out:
            out.append(d)
    return out


def claude_files(d: Path) -> list[Path]:
    return sorted(d.glob("*.jsonl")) + sorted(d.glob("*/subagents/*.jsonl"))


def claude_subagent_files(transcript: Path) -> list[Path]:
    return sorted((transcript.parent / src_of(transcript) / "subagents").glob("*.jsonl"))


def codex_files(root: Path) -> list[Path]:
    """Rollouts under ~/.codex/sessions whose session_meta cwd is this project (or inside it)."""
    base = Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex")) / "sessions"
    if not base.is_dir():
        return []
    roots = {str(root), str(root.resolve())}
    out = []
    for p in sorted(base.rglob("rollout-*.jsonl")):
        ident = codex_identity(p)
        if not ident or not ident["cwd"]:
            continue
        cwd = ident["cwd"]
        try:
            cwd_r = str(Path(cwd).resolve())
        except OSError:
            cwd_r = cwd
        if any(c == r or c.startswith(r.rstrip("/") + "/") for c in (cwd, cwd_r) for r in roots):
            out.append(p)
    return out
