"""Update Hagen–Poiseuille pipe case parameters in OpenFOAM dictionaries."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

from vcfd.mcp_server.cases import read_meta, write_meta


def set_pipe_parameters(
    case_dir: Path,
    *,
    radius: float | None = None,
    length: float | None = None,
    viscosity: float | None = None,
    density: float | None = None,
    bulk_velocity: float | None = None,
    n_axial: int | None = None,
    n_radial: int | None = None,
    wedge_half_angle_deg: float | None = None,
) -> dict[str, Any]:
    """Write physical and mesh parameters into case files + vcfd.json."""
    meta = read_meta(case_dir)
    params: dict[str, Any] = dict(meta.get("parameters") or {})

    # Defaults: laminar Re ≈ 100 circular pipe (axisymmetric wedge).
    defaults = {
        "radius": 0.05,
        "length": 2.0,
        "viscosity": 0.1,
        "density": 1000.0,
        "bulk_velocity": 0.1,
        "n_axial": 50,
        "n_radial": 20,
        "wedge_half_angle_deg": 5.0,
    }
    for k, v in defaults.items():
        params.setdefault(k, v)

    if radius is not None:
        params["radius"] = float(radius)
    if length is not None:
        params["length"] = float(length)
    if viscosity is not None:
        params["viscosity"] = float(viscosity)
    if density is not None:
        params["density"] = float(density)
    if bulk_velocity is not None:
        params["bulk_velocity"] = float(bulk_velocity)
    if n_axial is not None:
        params["n_axial"] = int(n_axial)
    if n_radial is not None:
        params["n_radial"] = int(n_radial)
    if wedge_half_angle_deg is not None:
        params["wedge_half_angle_deg"] = float(wedge_half_angle_deg)

    r = float(params["radius"])
    L = float(params["length"])
    nu = float(params["viscosity"]) / float(params["density"])  # kinematic
    U = float(params["bulk_velocity"])
    nx = int(params["n_axial"])
    nr = int(params["n_radial"])
    half_deg = float(params["wedge_half_angle_deg"])

    _update_transport(case_dir, nu=nu)
    _update_u_inlet(case_dir, U=U)
    _write_wedge_block_mesh(
        case_dir,
        radius=r,
        length=L,
        n_axial=nx,
        n_radial=nr,
        wedge_half_angle_deg=half_deg,
    )

    meta["parameters"] = params
    meta.setdefault("physics", {})
    if isinstance(meta["physics"], dict):
        meta["physics"]["geometry"] = "axisymmetric_wedge_pipe"
    write_meta(case_dir, meta)

    re_num = float(params["density"]) * U * (2 * r) / float(params["viscosity"])
    return {
        "parameters": params,
        "kinematic_viscosity": nu,
        "reynolds_number": re_num,
        "laminar_ok": re_num < 2300,
        "geometry": "axisymmetric_wedge_pipe",
    }


def _update_transport(case_dir: Path, *, nu: float) -> None:
    path = case_dir / "constant" / "transportProperties"
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    new_text, n = re.subn(
        r"(nu\s+\[[^\]]+\]\s+)([0-9.eE+-]+)\s*;",
        rf"\g<1>{nu:.8g};",
        text,
        count=1,
    )
    if n == 0:
        new_text, n = re.subn(
            r"(nu\s+)([0-9.eE+-]+)\s*;",
            rf"\g<1>{nu:.8g};",
            text,
            count=1,
        )
    if n:
        path.write_text(new_text, encoding="utf-8")


def _update_u_inlet(case_dir: Path, *, U: float) -> None:
    path = case_dir / "0" / "U"
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    text2 = re.sub(
        r"internalField\s+uniform\s+\([^)]+\)\s*;",
        f"internalField   uniform ({U:.8g} 0 0);",
        text,
        count=1,
    )
    text2 = re.sub(
        r"(inlet\s*\{[^}]*value\s+uniform\s+)\([^)]+\)(\s*;)",
        rf"\g<1>({U:.8g} 0 0)\2",
        text2,
        count=1,
        flags=re.DOTALL,
    )
    path.write_text(text2, encoding="utf-8")


def _write_wedge_block_mesh(
    case_dir: Path,
    *,
    radius: float,
    length: float,
    n_axial: int,
    n_radial: int,
    wedge_half_angle_deg: float = 5.0,
) -> None:
    """Axisymmetric circular pipe (wedge about x-axis).

    Topology matches OpenFOAM tutorials (e.g. LadenburgJet):
    ``mergeType points`` and hex with collapsed axis vertices.
    Radial coordinate is y; ±z form the wedge faces.
    """
    half = math.radians(wedge_half_angle_deg)
    # Place wall at cylindrical radius R: (y,z) = (R*cos θ, ±R*sin θ)
    # For small θ, y≈R, z≈±R*θ. Use cos/sin so wall radius is exact R.
    ry = radius * math.cos(half)
    rz = radius * math.sin(half)
    path = case_dir / "system" / "blockMeshDict"
    content = f"""FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      blockMeshDict;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //
// Axisymmetric circular pipe (wedge). Axis = x, radius = {radius:.8g} m,
// length = {length:.8g} m, half-angle = {wedge_half_angle_deg:.4g} deg.
// Pattern: OpenFOAM mergeType points + collapsed axis hex.

mergeType points;

scale   1;

vertices
(
    (0 0 0)                              // 0 axis inlet
    ({length:.12g} 0 0)                  // 1 axis outlet
    (0 {ry:.12g} {-rz:.12g})             // 2 wall inlet  (-z wedge)
    ({length:.12g} {ry:.12g} {-rz:.12g}) // 3 wall outlet (-z wedge)
    (0 {ry:.12g} {rz:.12g})              // 4 wall inlet  (+z wedge)
    ({length:.12g} {ry:.12g} {rz:.12g})  // 5 wall outlet (+z wedge)
);

blocks
(
    // i = axial, j = radial  (OpenFOAM tutorial ordering)
    hex (0 1 3 2 0 1 5 4) ({n_axial} {n_radial} 1) simpleGrading (1 1 1)
);

edges
(
);

boundary
(
    inlet
    {{
        type patch;
        faces
        (
            (0 2 4 0)
        );
    }}
    outlet
    {{
        type patch;
        faces
        (
            (1 3 5 1)
        );
    }}
    walls
    {{
        type wall;
        faces
        (
            (2 3 5 4)
        );
    }}
    axis
    {{
        type empty;
        faces
        (
            (0 1 1 0)
        );
    }}
    front
    {{
        type wedge;
        faces
        (
            (0 1 5 4)
        );
    }}
    back
    {{
        type wedge;
        faces
        (
            (0 2 3 1)
        );
    }}
);

mergePatchPairs
(
);

// ************************************************************************* //
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
