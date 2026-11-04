"""A deliberately small, strict template engine (stdlib only).

Syntax
------
  {{path}}                    insert a value (dotted path); missing -> TemplateError
  {{#if path}} … {{else}} … {{/if}}   truthiness: None, False, "", [], {} , 0 are false
  {{#if !path}} … {{/if}}     negation
  {{#each path}} … {{/each}}  iterate a list; inside, the item's keys are in scope,
                              {{.}} is the item itself, {{@index}} / {{@first}} / {{@last}}
  {{!comment}}                dropped
  {{{{raw}}}} … {{{{/raw}}}}  emitted verbatim (for LaTeX / Lean that contains braces)

A line holding only a block tag ({{#…}}, {{else}}, {{/…}}, {{!…}}, raw markers) plus
whitespace is "standalone": the whole line, newline included, is removed.
No HTML escaping is performed. Booleans render as "true"/"false"; lists and dicts may not
be interpolated directly.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

__all__ = ["render", "TemplateError"]


class TemplateError(Exception):
    pass


_RAW_RE = re.compile(r"\{\{\{\{raw\}\}\}\}(.*?)\{\{\{\{/raw\}\}\}\}", re.S)
_TAG_RE = re.compile(r"\{\{(.*?)\}\}", re.S)
_MISSING = object()


@dataclass
class _Node:
    kind: str  # text | var | if | each | raw
    value: str = ""
    children: list = field(default_factory=list)
    else_children: list = field(default_factory=list)
    negate: bool = False
    line: int = 0


def _is_block(tag: str) -> bool:
    return tag[:1] in "#/!" or tag == "else" or tag.startswith("{{")


def _tokenize(src: str) -> list[tuple[str, str, int]]:
    """Return (kind, payload, line) tokens: kind in text|tag|raw.

    Standalone block-tag lines are stripped here.
    """
    # Protect raw blocks first.
    raws: list[str] = []

    def _stash(m: re.Match) -> str:
        raws.append(m.group(1))
        return f"{{{{\x00raw{len(raws) - 1}}}}}"

    src = _RAW_RE.sub(_stash, src)
    if "{{{{raw}}}}" in src or "{{{{/raw}}}}" in src:
        raise TemplateError("unbalanced {{{{raw}}}} block")

    tokens: list[tuple[str, str, int]] = []
    for lineno, line in enumerate(src.splitlines(keepends=True), start=1):
        tags = list(_TAG_RE.finditer(line))
        stripped = _TAG_RE.sub("", line).strip()
        standalone = (
            len(tags) == 1
            and stripped == ""
            and (_is_block(tags[0].group(1).strip()))
            and not tags[0].group(1).startswith("\x00raw")
        )
        if standalone:
            tokens.append(("tag", tags[0].group(1).strip(), lineno))
            continue
        pos = 0
        for m in tags:
            if m.start() > pos:
                tokens.append(("text", line[pos:m.start()], lineno))
            inner = m.group(1)
            if inner.startswith("\x00raw"):
                tokens.append(("raw", raws[int(inner[4:])], lineno))
            else:
                tokens.append(("tag", inner.strip(), lineno))
            pos = m.end()
        if pos < len(line):
            tokens.append(("text", line[pos:], lineno))
    return tokens


def _parse(tokens: list[tuple[str, str, int]]) -> list[_Node]:
    root: list[_Node] = []
    stack: list[tuple[_Node, list[_Node]]] = []
    cur = root
    for kind, payload, line in tokens:
        if kind == "text":
            cur.append(_Node("text", payload, line=line))
        elif kind == "raw":
            cur.append(_Node("raw", payload, line=line))
        else:
            tag = payload
            if tag.startswith("!"):
                continue
            if tag.startswith("#if "):
                expr = tag[4:].strip()
                neg = expr.startswith("!")
                node = _Node("if", expr.lstrip("!").strip(), negate=neg, line=line)
                cur.append(node)
                stack.append((node, cur))
                cur = node.children
            elif tag.startswith("#each "):
                node = _Node("each", tag[6:].strip(), line=line)
                cur.append(node)
                stack.append((node, cur))
                cur = node.children
            elif tag == "else":
                if not stack or stack[-1][0].kind != "if":
                    raise TemplateError(f"line {line}: {{{{else}}}} outside {{{{#if}}}}")
                node = stack[-1][0]
                if cur is node.else_children:
                    raise TemplateError(f"line {line}: duplicate {{{{else}}}}")
                cur = node.else_children
            elif tag in ("/if", "/each"):
                if not stack or stack[-1][0].kind != tag[1:]:
                    raise TemplateError(f"line {line}: unexpected {{{{{tag}}}}}")
                _, cur = stack.pop()
            elif tag[:1] in "#/":
                raise TemplateError(f"line {line}: unknown block tag {{{{{tag}}}}}")
            else:
                cur.append(_Node("var", tag, line=line))
    if stack:
        node = stack[-1][0]
        raise TemplateError(f"line {node.line}: unclosed {{{{#{node.kind} {node.value}}}}}")
    return root


def _lookup(path: str, scopes: list[Any]) -> Any:
    if path == ".":
        for scope in reversed(scopes):
            if isinstance(scope, dict) and "." in scope:
                return scope["."]
        return _MISSING
    head, *rest = path.split(".")
    for scope in reversed(scopes):
        if isinstance(scope, dict) and head in scope:
            val = scope[head]
            break
    else:
        return _MISSING
    for part in rest:
        if isinstance(val, dict) and part in val:
            val = val[part]
        else:
            return _MISSING
    return val


def _render(nodes: list[_Node], scopes: list[Any], out: list[str]) -> None:
    for n in nodes:
        if n.kind in ("text", "raw"):
            out.append(n.value)
        elif n.kind == "var":
            val = _lookup(n.value, scopes)
            if val is _MISSING:
                raise TemplateError(f"line {n.line}: missing variable '{n.value}'")
            if isinstance(val, bool):
                out.append("true" if val else "false")
            elif isinstance(val, (list, dict)):
                raise TemplateError(f"line {n.line}: cannot interpolate a {type(val).__name__} ('{n.value}')")
            elif val is None:
                raise TemplateError(f"line {n.line}: variable '{n.value}' is None")
            else:
                out.append(str(val))
        elif n.kind == "if":
            val = _lookup(n.value, scopes)
            if val is _MISSING:
                raise TemplateError(f"line {n.line}: missing variable '{n.value}' in #if")
            truth = bool(val)
            if n.negate:
                truth = not truth
            _render(n.children if truth else n.else_children, scopes, out)
        elif n.kind == "each":
            seq = _lookup(n.value, scopes)
            if seq is _MISSING:
                raise TemplateError(f"line {n.line}: missing variable '{n.value}' in #each")
            if not isinstance(seq, list):
                raise TemplateError(f"line {n.line}: #each needs a list, got {type(seq).__name__}")
            for i, item in enumerate(seq):
                meta = {"@index": i, "@first": i == 0, "@last": i == len(seq) - 1}
                frame = dict(item) if isinstance(item, dict) else {}
                frame["."] = item
                _render(n.children, scopes + [meta, frame], out)


def render(src: str, context: dict) -> str:
    """Render template source `src` against `context` (strict)."""
    nodes = _parse(_tokenize(src))
    out: list[str] = []
    _render(nodes, [context], out)
    return "".join(out)
