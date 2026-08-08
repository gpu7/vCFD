"""Lightweight sampling of OpenFOAM ASCII result fields (no OF library link)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def latest_result_time(case_dir: Path) -> str | None:
    times: list[tuple[float, str]] = []
    for p in case_dir.iterdir():
        if not p.is_dir():
            continue
        name = p.name
        if name in {"0", "0.orig"}:
            continue
        try:
            t = float(name)
        except ValueError:
            continue
        if (p / "U").is_file():
            times.append((t, name))
    if not times:
        return None
    times.sort(key=lambda x: x[0])
    return times[-1][1]


def parse_vector_internal_field(path: Path) -> list[tuple[float, float, float]]:
    """Parse volVectorField internalField (uniform or nonuniform ASCII)."""
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(
        r"internalField\s+uniform\s+\(\s*([^\)]+)\)\s*;",
        text,
    )
    if m:
        comps = [float(x) for x in m.group(1).split()]
        # Single value — treat as one cell; caller may expand.
        x = comps[0]
        y = comps[1] if len(comps) > 1 else 0.0
        z = comps[2] if len(comps) > 2 else 0.0
        return [(x, y, z)]

    m = re.search(
        r"internalField\s+nonuniform\s+List<vector>\s*\n\s*(\d+)\s*\n\s*\(",
        text,
    )
    if not m:
        raise ValueError(f"Could not parse vector internalField in {path}")
    n = int(m.group(1))
    start = m.end()
    # Read vectors until matching close paren at list end — scan line by line.
    vectors: list[tuple[float, float, float]] = []
    for line in text[start:].splitlines():
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        if line.startswith(")"):
            break
        if line.startswith("(") and ")" in line:
            inner = line.strip("(),;")
            parts = inner.split()
            if len(parts) >= 3:
                vectors.append((float(parts[0]), float(parts[1]), float(parts[2])))
        if len(vectors) >= n:
            break
    if len(vectors) != n:
        # Allow partial if truncated but have something useful
        if not vectors:
            raise ValueError(f"Expected {n} vectors, got {len(vectors)} in {path}")
    return vectors


def parse_scalar_internal_field(path: Path) -> list[float]:
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"internalField\s+uniform\s+([0-9.eE+-]+)\s*;", text)
    if m:
        return [float(m.group(1))]
    m = re.search(
        r"internalField\s+nonuniform\s+List<scalar>\s*\n\s*(\d+)\s*\n\s*\(",
        text,
    )
    if not m:
        raise ValueError(f"Could not parse scalar internalField in {path}")
    n = int(m.group(1))
    start = m.end()
    values: list[float] = []
    for line in text[start:].splitlines():
        line = line.strip().rstrip(";")
        if not line or line.startswith("//"):
            continue
        if line.startswith(")"):
            break
        try:
            values.append(float(line))
        except ValueError:
            continue
        if len(values) >= n:
            break
    return values


def sample_pipe_results(
    case_dir: Path,
    *,
    n_axial: int,
    n_radial: int,
    radius: float,
) -> dict[str, Any]:
    """Sample structured half-channel results for Poiseuille comparison.

    Assumes blockMesh hex (n_axial, n_radial, 1) cell ordering with i (axial)
    fastest, then j (radial).
    """
    tname = latest_result_time(case_dir)
    if not tname:
        raise FileNotFoundError("No result time directories with U field found.")
    tdir = case_dir / tname
    u_path = tdir / "U"
    p_path = tdir / "p"
    u_field = parse_vector_internal_field(u_path)
    n_cells = n_axial * n_radial
    if len(u_field) not in {1, n_cells}:
        # Fall back: use actual length
        n_cells = len(u_field)
        # Try to infer n_axial from meta if mismatch
        if n_radial > 0 and n_cells % n_radial == 0:
            n_axial = n_cells // n_radial
        else:
            n_radial = max(1, int(n_cells**0.5))
            n_axial = max(1, n_cells // n_radial)

    # Cell-center y for uniform radial spacing from 0..radius: j+0.5
    # Average Ux over axial direction for each radial band.
    ux_by_j: list[list[float]] = [[] for _ in range(n_radial)]
    for idx, (ux, _uy, _uz) in enumerate(u_field[: n_axial * n_radial]):
        j = (idx // n_axial) % n_radial if n_axial else idx % n_radial
        # OpenFOAM blockMesh cell order: i varies fastest
        i = idx % n_axial
        j = (idx // n_axial) % n_radial
        ux_by_j[j].append(ux)
        _ = i

    radii: list[float] = []
    numerical_u: list[float] = []
    for j in range(n_radial):
        if not ux_by_j[j]:
            continue
        y = (j + 0.5) / n_radial * radius
        radii.append(y)
        numerical_u.append(sum(ux_by_j[j]) / len(ux_by_j[j]))

    ux_all = [u[0] for u in u_field]
    u_max = max(ux_all) if ux_all else 0.0
    u_mean = sum(ux_all) / len(ux_all) if ux_all else 0.0

    delta_p_num = None
    if p_path.is_file():
        try:
            p_field = parse_scalar_internal_field(p_path)
            if len(p_field) >= n_axial * n_radial and n_axial > 1:
                # Approximate inlet/outlet band averages (i=0 and i=n_axial-1)
                inlet_p = []
                outlet_p = []
                for j in range(n_radial):
                    base = j * n_axial
                    inlet_p.append(p_field[base])
                    outlet_p.append(p_field[base + n_axial - 1])
                # p in OpenFOAM incompressible is kinematic (p/rho); convert later if needed
                delta_p_num = (sum(inlet_p) / len(inlet_p)) - (sum(outlet_p) / len(outlet_p))
            elif p_field:
                delta_p_num = max(p_field) - min(p_field)
        except ValueError:
            pass

    return {
        "time": tname,
        "n_cells": len(u_field),
        "n_axial": n_axial,
        "n_radial": n_radial,
        "radii": radii,
        "u_axial_mean_by_radius": numerical_u,
        "u_max": u_max,
        "u_mean": u_mean,
        "delta_p_kinematic": delta_p_num,
    }
