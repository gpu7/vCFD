"""Analytical Hagen–Poiseuille tests."""

from vcfd.analytics.poiseuille import (
    PipeParams,
    axial_velocity,
    centerline_velocity,
    compare_velocity_profile,
    pressure_drop,
    reynolds_number,
)


def _laminar_pipe() -> PipeParams:
    # Re = ρ U D / μ = 1000 * 0.1 * 0.1 / 0.1 = 100
    return PipeParams(
        radius=0.05,
        length=1.0,
        viscosity=0.1,
        density=1000.0,
        bulk_velocity=0.1,
    )


def test_centerline_is_twice_bulk():
    p = _laminar_pipe()
    assert centerline_velocity(p) == 0.2


def test_wall_velocity_zero():
    p = _laminar_pipe()
    assert axial_velocity(p, p.radius) == 0.0


def test_pressure_drop_positive():
    p = _laminar_pipe()
    assert pressure_drop(p) > 0
    D = 0.1
    expected = 32 * 0.1 * 1.0 * 0.1 / (D**2)
    assert abs(pressure_drop(p) - expected) < 1e-12


def test_reynolds_laminar():
    p = _laminar_pipe()
    assert abs(reynolds_number(p) - 100.0) < 1e-9


def test_compare_perfect_match():
    p = _laminar_pipe()
    radii = [0.0, 0.025, 0.05]
    numerical = [axial_velocity(p, r) for r in radii]
    cmp = compare_velocity_profile(p, radii, numerical)
    assert cmp["max_abs_error"] < 1e-15
    assert cmp["laminar_ok"] is True
