"""Case directory management and status helpers."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from vcfd.mcp_server.paths import resolve_case_dir, validate_case_name

META_NAME = "vcfd.json"


def list_templates(templates_root: Path) -> list[str]:
    if not templates_root.is_dir():
        return []
    return sorted(
        p.name
        for p in templates_root.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    )


def create_case_from_template(
    cases_root: Path,
    templates_root: Path,
    name: str,
    template: str,
    description: str = "",
) -> Path:
    validate_case_name(name)
    dest = resolve_case_dir(cases_root, name, must_exist=False)
    if dest.exists():
        raise FileExistsError(f"Case '{name}' already exists.")
    src = templates_root / template
    if not src.is_dir():
        available = list_templates(templates_root)
        raise FileNotFoundError(
            f"Template '{template}' not found. Available: {', '.join(available) or '(none)'}"
        )
    shutil.copytree(src, dest)
    meta = {
        "name": name,
        "template": template,
        "description": description,
        "parameters": {},
    }
    # Preserve template defaults if present
    template_meta = src / META_NAME
    if template_meta.is_file():
        try:
            base = json.loads(template_meta.read_text(encoding="utf-8"))
            if isinstance(base, dict):
                meta["parameters"] = base.get("parameters", {})
                meta["solver"] = base.get("solver", "simpleFoam")
                meta["physics"] = base.get("physics", {})
        except json.JSONDecodeError:
            pass
    write_meta(dest, meta)
    return dest


def write_meta(case_dir: Path, meta: dict[str, Any]) -> None:
    (case_dir / META_NAME).write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


def read_meta(case_dir: Path) -> dict[str, Any]:
    path = case_dir / META_NAME
    if not path.is_file():
        return {"name": case_dir.name}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    return {"name": case_dir.name}


def list_cases(cases_root: Path) -> list[dict[str, Any]]:
    if not cases_root.is_dir():
        return []
    result = []
    for path in sorted(cases_root.iterdir()):
        if not path.is_dir() or path.name.startswith("."):
            continue
        result.append(case_status(path))
    return result


def case_status(case_dir: Path) -> dict[str, Any]:
    meta = read_meta(case_dir)
    meshed = (case_dir / "constant" / "polyMesh" / "points").is_file()
    times = time_directories(case_dir)
    return {
        "name": case_dir.name,
        "template": meta.get("template"),
        "description": meta.get("description", ""),
        "meshed": meshed,
        "latest_time": times[-1] if times else None,
        "n_time_dirs": len(times),
        "parameters": meta.get("parameters", {}),
        "solver": meta.get("solver", "simpleFoam"),
    }


def time_directories(case_dir: Path) -> list[str]:
    times: list[tuple[float, str]] = []
    for p in case_dir.iterdir():
        if not p.is_dir():
            continue
        name = p.name
        if name in {"0", "0.orig"}:
            times.append((0.0, name))
            continue
        try:
            t = float(name)
        except ValueError:
            continue
        times.append((t, name))
    times.sort(key=lambda x: x[0])
    return [t[1] for t in times]


def clean_case(case_dir: Path, *, keep_zero: bool = True) -> list[str]:
    removed: list[str] = []
    for name in time_directories(case_dir):
        if keep_zero and name in {"0", "0.orig"}:
            continue
        path = case_dir / name
        if path.is_dir():
            shutil.rmtree(path)
            removed.append(name)
    for extra in ("VTK", "postProcessing", "dynamicCode"):
        p = case_dir / extra
        if p.exists():
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
            removed.append(extra)
    for p in case_dir.glob("processor*"):
        if p.is_dir():
            shutil.rmtree(p)
            removed.append(p.name)
    return removed


def delete_case(cases_root: Path, name: str) -> None:
    path = resolve_case_dir(cases_root, name, must_exist=True)
    shutil.rmtree(path)


def parse_check_mesh(output: str) -> dict[str, Any]:
    cells = _search_int(output, r"cells:\s*(\d+)")
    max_nonortho = _search_float(output, r"Max non-orthogonality\s*=\s*([0-9.eE+-]+)")
    mesh_ok = "Mesh OK" in output or "mesh OK" in output.lower()
    return {
        "cells": cells,
        "max_non_orthogonality": max_nonortho,
        "mesh_ok": mesh_ok,
        "raw_tail": "\n".join(output.strip().splitlines()[-15:]),
    }


def parse_residuals_from_log(log: str) -> dict[str, Any]:
    # Grab last residual-like lines
    lines = [ln for ln in log.splitlines() if "residual" in ln.lower() or "Solving for" in ln]
    return {"residual_lines": lines[-12:], "n_lines": len(lines)}


def _search_int(text: str, pattern: str) -> int | None:
    m = re.search(pattern, text, re.IGNORECASE)
    return int(m.group(1)) if m else None


def _search_float(text: str, pattern: str) -> float | None:
    m = re.search(pattern, text, re.IGNORECASE)
    return float(m.group(1)) if m else None
