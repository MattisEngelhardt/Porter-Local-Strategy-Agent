"""Tolerant JSON extraction from LLM output (Phase 3).

Local models often wrap JSON in prose or ```json fences, or emit trailing text. These helpers
pull the first *balanced* JSON object/array out of a response so the agent degrades gracefully
on imperfect formatting instead of crashing (SPEC REQ-5). Returning ``None`` lets callers fall
back to conservative defaults.
"""

from __future__ import annotations

import json
from typing import Any


def _first_balanced(text: str, open_ch: str, close_ch: str) -> str | None:
    """Return the first balanced ``open_ch … close_ch`` span, respecting JSON strings/escapes."""
    start = text.find(open_ch)
    if start == -1:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == open_ch:
            depth += 1
        elif char == close_ch:
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def extract_json_object(text: str) -> dict[str, Any] | None:
    """Parse the first balanced JSON object in ``text`` into a dict (or ``None`` on failure)."""
    blob = _first_balanced(text, "{", "}")
    if blob is None:
        return None
    try:
        data: Any = json.loads(blob)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def extract_json_array(text: str) -> list[Any] | None:
    """Parse the first balanced JSON array in ``text`` into a list (or ``None`` on failure)."""
    blob = _first_balanced(text, "[", "]")
    if blob is None:
        return None
    try:
        data: Any = json.loads(blob)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, list) else None
