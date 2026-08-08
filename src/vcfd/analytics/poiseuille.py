"""Analytical Hagen–Poiseuille relations for laminar pipe flow validation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PipeParams:
    """Pipe geometry and fluid properties (SI units)."""

    radius: float  # m
    length: float  # m
    viscosity: float  # Pa·s (dynamic)
    density: float  # kg/m³
    bulk_velocity: float  # m/s mean axial velocity


def reynolds_number(p: PipeParams) -> float:
    diameter = 2.0 * p.radius
    return p.density * p.bulk_velocity * diameter / p.viscosity


def pressure_drop(p: PipeParams) -> float:
    """Δp for fully developed laminar pipe flow [Pa]."""
    diameter = 2.0 * p.radius
    return 32.0 * p.viscosity * p.length * p.bulk_velocity / (diameter**2)


def centerline_velocity(p: PipeParams) -> float:
    """Maximum (centerline) velocity = 2 * bulk for laminar Poiseuille."""
    return 2.0 * p.bulk_velocity


def axial_velocity(p: PipeParams, r: float) -> float:
    """u_z(r) for pressure-driven Hagen–Poiseuille flow with given bulk velocity."""
    if r < 0 or r > p.radius + 1e-15:
        raise ValueError(f"Radius r={r} outside pipe [0, R={p.radius}].")
    # u(r) = 2 U_bulk (1 - (r/R)^2)
    return 2.0 * p.bulk_velocity * (1.0 - (r / p.radius) ** 2)


def compare_velocity_profile(
    p: PipeParams,
    radii: list[float],
    numerical_u: list[float],
) -> dict:
    """Compare numerical axial velocities to analytical profile."""
    if len(radii) != len(numerical_u):
        raise ValueError("radii and numerical_u must have the same length.")
    if not radii:
        raise ValueError("Need at least one sample point.")

    errors: list[dict] = []
    abs_errors: list[float] = []
    for r, u_num in zip(radii, numerical_u, strict=True):
        u_an = axial_velocity(p, r)
        err = abs(u_num - u_an)
        rel = err / max(abs(u_an), 1e-12)
        abs_errors.append(err)
        errors.append(
            {
                "r": r,
                "u_numerical": u_num,
                "u_analytical": u_an,
                "abs_error": err,
                "rel_error": rel,
            }
        )

    max_abs = max(abs_errors)
    mean_abs = sum(abs_errors) / len(abs_errors)
    max_rel = max(e["rel_error"] for e in errors)
    u_max_an = centerline_velocity(p)
    dp = pressure_drop(p)
    re = reynolds_number(p)

    return {
        "re": re,
        "delta_p_analytical_pa": dp,
        "u_centerline_analytical": u_max_an,
        "u_bulk": p.bulk_velocity,
        "max_abs_error": max_abs,
        "mean_abs_error": mean_abs,
        "max_rel_error": max_rel,
        "points": errors,
        "laminar_ok": re < 2300,
    }
