"""Safe path resolution under the cases root (path traversal protection)."""

from __future__ import annotations

import re
from pathlib import Path

CASE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def validate_case_name(name: str) -> str:
    if not name or not CASE_NAME_RE.match(name):
        raise ValueError(
            "Invalid case name. Use 1–64 chars: letters, digits, dot, underscore, hyphen; "
            "must start with alphanumeric."
        )
    if name in {".", ".."}:
        raise ValueError("Invalid case name.")
    return name


def resolve_case_dir(cases_root: Path, name: str, *, must_exist: bool = False) -> Path:
    validate_case_name(name)
    root = cases_root.resolve()
    path = (root / name).resolve()
    if not str(path).startswith(str(root)):
        raise ValueError("Path escapes cases root.")
    if must_exist and not path.is_dir():
        raise FileNotFoundError(f"Case '{name}' not found.")
    return path
