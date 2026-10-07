"""Minimal YAML-subset reader for workspace.yaml.

Supports exactly what the workspace schema needs: nested mappings, lists of
mappings, and scalar strings/booleans/null. No flow style, no anchors, no
multi-line scalars, no comments. A full YAML library is deliberately not a
dependency here, so `ws` runs on a bare python3 interpreter everywhere this
repo's installer targets.
"""

from __future__ import annotations


def _strip_comment_free_line(line):
    return line.rstrip("\n")


def _parse_scalar(token):
    token = token.strip()
    if token == "" or token == "~" or token == "null":
        return None
    if token in ("true", "True"):
        return True
    if token in ("false", "False"):
        return False
    if len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'":
        return token[1:-1]
    return token


def _indent_of(line):
    return len(line) - len(line.lstrip(" "))


def _load_lines(lines, index, indent):
    if index >= len(lines):
        return None, index
    line = lines[index]
    if line.strip() == "":
        return _load_lines(lines, index + 1, indent)
    if _indent_of(line) < indent:
        return None, index
    stripped = line.strip()
    if stripped.startswith("- "):
        return _load_list(lines, index, _indent_of(line))
    return _load_map(lines, index, _indent_of(line))


def _load_list(lines, index, indent):
    items = []
    while index < len(lines):
        line = lines[index]
        if line.strip() == "":
            index += 1
            continue
        if _indent_of(line) != indent or not line.strip().startswith("- "):
            break
        rest = line.strip()[2:]
        if ":" in rest and not rest.startswith("["):
            key, _, value = rest.partition(":")
            sub_lines = [" " * (indent + 2) + rest] + lines[index + 1 :]
            item, consumed = _load_map(sub_lines, 0, indent + 2)
            index = index + consumed
            items.append(item)
        else:
            items.append(_parse_scalar(rest))
            index += 1
    return items, index


def _load_map(lines, index, indent):
    result = {}
    while index < len(lines):
        line = lines[index]
        if line.strip() == "":
            index += 1
            continue
        cur_indent = _indent_of(line)
        if cur_indent < indent:
            break
        if cur_indent > indent:
            break
        stripped = line.strip()
        if stripped.startswith("- "):
            break
        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip()
        if value == "":
            child, next_index = _load_lines(lines, index + 1, indent + 1)
            result[key] = child if child is not None else {}
            index = next_index
        else:
            result[key] = _parse_scalar(value)
            index += 1
    return result, index


def load(text):
    lines = [_strip_comment_free_line(l) for l in text.split("\n")]
    doc, _ = _load_map(lines, 0, 0)
    return doc


def load_path(path):
    with open(path, "r", encoding="utf-8") as handle:
        return load(handle.read())
