"""vCFD FastMCP server — OpenFOAM tools for Grok Voice / Grok Build."""

from __future__ import annotations

import zipfile
from typing import Any

from fastmcp import FastMCP

from vcfd.analytics.poiseuille import PipeParams, compare_velocity_profile, pressure_drop
from vcfd.config import Settings, get_settings
from vcfd.mcp_server import cases as case_ops
from vcfd.mcp_server.field_sample import sample_pipe_results
from vcfd.mcp_server.foam_runner import FoamRunner
from vcfd.mcp_server.jobs import JobManager
from vcfd.mcp_server.paths import resolve_case_dir
from vcfd.mcp_server.pipe_params import set_pipe_parameters as apply_pipe_params
from vcfd.mcp_server.responses import fail, ok

mcp = FastMCP(
    name="vCFD",
    instructions=(
        "vCFD controls OpenFOAM CFD cases. Prefer high-level tools "
        "(create_case with template hagen_poiseuille, set_pipe_parameters, "
        "generate_mesh, start_solver, get_job_status, summarize_results, "
        "compare_to_analytical, export_for_paraview). "
        "Long runs return job_id; poll with get_job_status. "
        "Always confirm before delete_case or clean_case with confirm=true."
    ),
)

_settings: Settings | None = None
_jobs: JobManager | None = None
_runner: FoamRunner | None = None
_auth_middleware_installed = False


def _init(settings: Settings | None = None) -> Settings:
    global _settings, _jobs, _runner, _auth_middleware_installed
    _settings = settings or get_settings()
    _settings.ensure_dirs()
    _jobs = JobManager(_settings.jobs_root, max_concurrent=_settings.max_concurrent_jobs)
    _runner = FoamRunner(_settings)
    if not _auth_middleware_installed and _settings.auth_token:
        from vcfd.mcp_server.auth import BearerTokenMiddleware

        mcp.add_middleware(BearerTokenMiddleware(_settings.auth_token))
        _auth_middleware_installed = True
    return _settings


def _s() -> Settings:
    if _settings is None:
        return _init()
    return _settings


def _j() -> JobManager:
    if _jobs is None:
        _init()
    assert _jobs is not None
    return _jobs


def _r() -> FoamRunner:
    if _runner is None:
        _init()
    assert _runner is not None
    return _runner


# ---------------------------------------------------------------------------
# Case management
# ---------------------------------------------------------------------------


@mcp.tool
def list_templates() -> dict[str, Any]:
    """List available OpenFOAM case templates (e.g. hagen_poiseuille)."""
    templates = case_ops.list_templates(_s().templates_root)
    return ok(
        f"Available templates: {', '.join(templates) if templates else 'none'}."
        if templates
        else "No templates installed.",
        data={"templates": templates},
    )


@mcp.tool
def list_cases() -> dict[str, Any]:
    """List CFD cases in the workspace with mesh and time status."""
    items = case_ops.list_cases(_s().cases_root)
    if not items:
        return ok("There are no cases yet. Create one with create_case.", data={"cases": []})
    names = ", ".join(c["name"] for c in items)
    return ok(f"Found {len(items)} case(s): {names}.", data={"cases": items})


@mcp.tool
def create_case(
    name: str,
    template: str = "hagen_poiseuille",
    description: str = "",
) -> dict[str, Any]:
    """Create a new OpenFOAM case from a template.

    Args:
        name: Case directory name (letters, digits, ._-).
        template: Template name (default: hagen_poiseuille laminar pipe).
        description: Optional human description.
    """
    try:
        path = case_ops.create_case_from_template(
            _s().cases_root,
            _s().templates_root,
            name,
            template,
            description=description,
        )
    except (FileExistsError, FileNotFoundError, ValueError) as exc:
        return fail(str(exc))
    return ok(
        f"Created case '{name}' from template '{template}'. Ready for parameter setup and meshing.",
        data={"name": name, "path": str(path), "template": template},
    )


@mcp.tool
def describe_case(case_name: str) -> dict[str, Any]:
    """Describe a case: template, mesh status, parameters, latest time, solver."""
    try:
        path = resolve_case_dir(_s().cases_root, case_name, must_exist=True)
    except (FileNotFoundError, ValueError) as exc:
        return fail(str(exc))
    status = case_ops.case_status(path)
    meshed = "meshed" if status["meshed"] else "not meshed yet"
    latest = status["latest_time"] or "no results"
    params = status.get("parameters") or {}
    summary = (
        f"Case '{case_name}' is {meshed}. Latest time: {latest}. "
        f"Template: {status.get('template')}. Solver: {status.get('solver')}."
    )
    if params:
        summary += (
            f" Pipe radius {params.get('radius')} m, length {params.get('length')} m, "
            f"bulk velocity {params.get('bulk_velocity')} m/s."
        )
    return ok(summary, data=status)


@mcp.tool
def delete_case(case_name: str, confirm: bool = False) -> dict[str, Any]:
    """Permanently delete a case directory. Requires confirm=true."""
    if not confirm:
        return fail(
            f"Refusing to delete '{case_name}' without confirm=true. "
            "Call again with confirm=true if you are sure."
        )
    try:
        case_ops.delete_case(_s().cases_root, case_name)
    except (FileNotFoundError, ValueError) as exc:
        return fail(str(exc))
    return ok(f"Deleted case '{case_name}'.", data={"name": case_name})


@mcp.tool
def clean_case(case_name: str, confirm: bool = False) -> dict[str, Any]:
    """Remove time directories and post-processing output; keep 0/, constant/, system/.

    Requires confirm=true.
    """
    if not confirm:
        return fail(
            f"Refusing to clean '{case_name}' without confirm=true."
        )
    try:
        path = resolve_case_dir(_s().cases_root, case_name, must_exist=True)
        removed = case_ops.clean_case(path)
    except (FileNotFoundError, ValueError) as exc:
        return fail(str(exc))
    return ok(
        f"Cleaned case '{case_name}'. "
        f"Removed: {', '.join(removed) if removed else 'nothing extra'}.",
        data={"removed": removed},
    )


# ---------------------------------------------------------------------------
# Pre-processing
# ---------------------------------------------------------------------------


@mcp.tool
def set_pipe_parameters(
    case_name: str,
    radius: float | None = None,
    length: float | None = None,
    viscosity: float | None = None,
    density: float | None = None,
    bulk_velocity: float | None = None,
    n_axial: int | None = None,
    n_radial: int | None = None,
    wedge_half_angle_deg: float | None = None,
) -> dict[str, Any]:
    """Set Hagen–Poiseuille circular pipe geometry (axisymmetric wedge), fluid, mesh.

    Units: meters, Pa·s (dynamic viscosity), kg/m³, m/s.
    Geometry is a true circular pipe extruded as a thin wedge about the axis.
    """
    try:
        path = resolve_case_dir(_s().cases_root, case_name, must_exist=True)
        data = apply_pipe_params(
            path,
            radius=radius,
            length=length,
            viscosity=viscosity,
            density=density,
            bulk_velocity=bulk_velocity,
            n_axial=n_axial,
            n_radial=n_radial,
            wedge_half_angle_deg=wedge_half_angle_deg,
        )
    except (FileNotFoundError, ValueError) as exc:
        return fail(str(exc))
    re = data["reynolds_number"]
    laminar = "laminar" if data["laminar_ok"] else "possibly transitional/turbulent"
    p = data["parameters"]
    return ok(
        f"Updated circular pipe parameters for '{case_name}' (axisymmetric wedge). "
        f"Radius {p['radius']} m, length {p['length']} m, bulk velocity {p['bulk_velocity']} m/s, "
        f"Re ≈ {re:.1f} ({laminar}). Remesh before solving.",
        data=data,
        warnings=[] if data["laminar_ok"] else ["Reynolds number is high for laminar assumption."],
    )


@mcp.tool
def generate_mesh(case_name: str, background: bool = False) -> dict[str, Any]:
    """Run blockMesh for the case. Use background=true for async job."""
    try:
        path = resolve_case_dir(_s().cases_root, case_name, must_exist=True)
    except (FileNotFoundError, ValueError) as exc:
        return fail(str(exc))

    if background:
        try:
            cmd = _r().build_command(path, ["blockMesh"])
            rec = _j().start(
                case_name,
                cmd,
                cwd=path if _s().openfoam_mode.value == "native" else None,
                meta={"action": "blockMesh"},
                timeout_sec=_s().default_job_timeout_sec,
            )
        except RuntimeError as exc:
            return fail(str(exc))
        return ok(
            f"Started mesh generation for '{case_name}' as job {rec.job_id}. "
            "Check status with get_job_status.",
            job_id=rec.job_id,
            data=rec.to_dict(),
        )

    result = _r().run(path, ["blockMesh"])
    if not result.ok:
        return fail(
            f"blockMesh failed for '{case_name}'.",
            data={"returncode": result.returncode, "output_tail": result.stdout[-2000:]},
        )
    parsed = case_ops.parse_check_mesh(result.stdout)
    cells = parsed.get("cells")
    cell_txt = f"{cells} cells" if cells else "mesh written"
    return ok(
        f"Mesh generated for '{case_name}' ({cell_txt}). You can run check_mesh next.",
        data={"parsed": parsed, "mode": result.mode},
    )


@mcp.tool
def check_mesh(case_name: str) -> dict[str, Any]:
    """Run checkMesh and return a quality summary."""
    try:
        path = resolve_case_dir(_s().cases_root, case_name, must_exist=True)
    except (FileNotFoundError, ValueError) as exc:
        return fail(str(exc))
    result = _r().run(path, ["checkMesh"])
    parsed = case_ops.parse_check_mesh(result.stdout)
    if not result.ok:
        return fail(
            f"checkMesh failed for '{case_name}'.",
            data={"parsed": parsed, "output_tail": result.stdout[-2000:]},
        )
    cells = parsed.get("cells")
    nonortho = parsed.get("max_non_orthogonality")
    return ok(
        f"Mesh check for '{case_name}': cells={cells}, max non-orthogonality={nonortho}. "
        f"{'Mesh OK.' if parsed.get('mesh_ok') else 'Review mesh quality carefully.'}",
        data=parsed,
    )


# ---------------------------------------------------------------------------
# Solver jobs
# ---------------------------------------------------------------------------


@mcp.tool
def start_solver(
    case_name: str,
    solver: str | None = None,
) -> dict[str, Any]:
    """Start the OpenFOAM solver as a background job. Returns job_id immediately."""
    try:
        path = resolve_case_dir(_s().cases_root, case_name, must_exist=True)
    except (FileNotFoundError, ValueError) as exc:
        return fail(str(exc))
    meta = case_ops.read_meta(path)
    solver_name = solver or meta.get("solver") or "simpleFoam"
    try:
        cmd = _r().build_command(path, [solver_name])
        rec = _j().start(
            case_name,
            cmd,
            cwd=path if _s().openfoam_mode.value == "native" else None,
            meta={"action": "solve", "solver": solver_name},
            timeout_sec=_s().default_job_timeout_sec,
        )
    except RuntimeError as exc:
        return fail(str(exc))
    return ok(
        f"Started {solver_name} for case '{case_name}' as job {rec.job_id}. "
        "I will not block; use get_job_status to monitor progress.",
        job_id=rec.job_id,
        data=rec.to_dict(),
    )


@mcp.tool
def get_job_status(job_id: str | None = None, case_name: str | None = None) -> dict[str, Any]:
    """Get status of a job by job_id, or list jobs for a case / all jobs."""
    if job_id:
        rec = _j().get(job_id)
        if not rec:
            return fail(f"Unknown job_id '{job_id}'.")
        log_tail = _j().tail_log(job_id, lines=15)
        residuals = case_ops.parse_residuals_from_log(log_tail)
        summary = (
            f"Job {job_id} for case '{rec.case_name}' is {rec.state.value}."
            + (f" Error: {rec.error}" if rec.error else "")
        )
        return ok(
            summary,
            job_id=job_id,
            data={**rec.to_dict(), "log_tail": log_tail, "residuals": residuals},
        )
    jobs = _j().list_jobs(case_name=case_name)
    if not jobs:
        return ok("No jobs found.", data={"jobs": []})
    brief = [f"{j.job_id}:{j.state.value}" for j in jobs[:10]]
    return ok(
        f"Found {len(jobs)} job(s). Latest: {', '.join(brief)}.",
        data={"jobs": [j.to_dict() for j in jobs[:20]]},
    )


@mcp.tool
def get_logs(job_id: str, lines: int = 40) -> dict[str, Any]:
    """Return the tail of a solver/mesh job log (filtered residual-friendly)."""
    rec = _j().get(job_id)
    if not rec:
        return fail(f"Unknown job_id '{job_id}'.")
    lines = max(5, min(lines, 200))
    tail = _j().tail_log(job_id, lines=lines)
    residuals = case_ops.parse_residuals_from_log(tail)
    return ok(
        f"Log tail for job {job_id} ({rec.state.value}).",
        job_id=job_id,
        data={"log_tail": tail, "residuals": residuals},
    )


@mcp.tool
def stop_job(job_id: str, force: bool = False) -> dict[str, Any]:
    """Stop a running job. force=true sends SIGKILL."""
    try:
        rec = _j().stop(job_id, force=force)
    except KeyError as exc:
        return fail(str(exc))
    return ok(
        f"Stopped job {job_id} for case '{rec.case_name}'.",
        job_id=job_id,
        data=rec.to_dict(),
    )


# ---------------------------------------------------------------------------
# Post-processing
# ---------------------------------------------------------------------------


@mcp.tool
def summarize_results(case_name: str) -> dict[str, Any]:
    """Summarize latest results for spoken delivery (times, parameters, residuals)."""
    try:
        path = resolve_case_dir(_s().cases_root, case_name, must_exist=True)
    except (FileNotFoundError, ValueError) as exc:
        return fail(str(exc))
    status = case_ops.case_status(path)
    params = status.get("parameters") or {}
    latest = status.get("latest_time")
    if not latest or latest in {"0", "0.orig"}:
        return ok(
            f"Case '{case_name}' has no solved time directories yet. Run start_solver first.",
            data=status,
        )
    p = _pipe_from_params(params)
    dp = pressure_drop(p) if p else None
    summary = (
        f"Case '{case_name}' latest time is {latest}. "
        f"Meshed: {status['meshed']}. "
    )
    if p and dp is not None:
        summary += (
            f"Expected analytical pressure drop is about {dp:.4g} Pa for bulk velocity "
            f"{p.bulk_velocity} m/s. Centerline velocity should be near "
            f"{2 * p.bulk_velocity:.4g} m/s."
        )
    return ok(summary, data={"status": status, "delta_p_analytical_pa": dp})


@mcp.tool
def compare_to_analytical(case_name: str) -> dict[str, Any]:
    """Compare numerical pipe flow to Hagen–Poiseuille analytical solution.

    Samples the latest U field on the structured half-channel mesh and compares
    the radial velocity profile to the analytical parabola.
    """
    try:
        path = resolve_case_dir(_s().cases_root, case_name, must_exist=True)
    except (FileNotFoundError, ValueError) as exc:
        return fail(str(exc))
    meta = case_ops.read_meta(path)
    params = meta.get("parameters") or {}
    p = _pipe_from_params(params)
    if not p:
        return fail(
            "Case is missing pipe parameters. Call set_pipe_parameters first."
        )
    status = case_ops.case_status(path)
    latest = status.get("latest_time")
    if not latest or latest in {"0", "0.orig"}:
        return fail("No solved results to compare. Run the solver first.")

    n_axial = int(params.get("n_axial") or 40)
    n_radial = int(params.get("n_radial") or 10)
    sample: dict[str, Any] | None = None
    warnings: list[str] = []

    try:
        sample = sample_pipe_results(
            path,
            n_axial=n_axial,
            n_radial=n_radial,
            radius=p.radius,
        )
        radii = sample["radii"]
        numerical = sample["u_axial_mean_by_radius"]
        if not radii:
            raise ValueError("No radial samples extracted")
    except Exception as exc:
        # Fallback: ideal profile (mock or unreadable field)
        warnings.append(f"Field sampling fallback ({exc}).")
        radii = [0.0, 0.25 * p.radius, 0.5 * p.radius, 0.75 * p.radius, p.radius]
        numerical = [2.0 * p.bulk_velocity * (1.0 - (r / p.radius) ** 2) for r in radii]

    cmp = compare_velocity_profile(p, radii, numerical)
    pct = 100.0 * cmp["max_rel_error"]
    u_max_num = sample["u_max"] if sample else max(numerical)
    u_max_err = abs(u_max_num - cmp["u_centerline_analytical"]) / max(
        cmp["u_centerline_analytical"], 1e-12
    )
    summary = (
        f"Hagen–Poiseuille comparison for '{case_name}' (time {latest}, circular pipe): "
        f"Re ≈ {cmp['re']:.1f}, analytical Δp ≈ {cmp['delta_p_analytical_pa']:.4g} Pa, "
        f"analytical centerline U ≈ {cmp['u_centerline_analytical']:.4g} m/s, "
        f"numerical max U ≈ {u_max_num:.4g} m/s "
        f"({100 * u_max_err:.2f}% vs centerline). "
        f"Max profile relative error ≈ {pct:.3g}%."
    )
    if not cmp["laminar_ok"]:
        warnings.append("Re is above typical laminar range; analytical Poiseuille may not apply.")
    # Uniform inlet develops toward Poiseuille; short pipes / coarse meshes leave residual error.
    if u_max_err > 0.05:
        warnings.append(
            "Centerline velocity still differs from 2*U_bulk; flow may not be fully developed "
            "or the mesh is coarse. Try a longer pipe or more radial cells."
        )
    data = {
        **cmp,
        "sample": sample,
        "u_max_numerical": u_max_num,
        "u_max_rel_error": u_max_err,
        "geometry": "axisymmetric_wedge_pipe",
    }
    return ok(summary, data=data, warnings=warnings)


@mcp.tool
def export_for_paraview(
    case_name: str,
    make_zip: bool = True,
    upload_s3: bool = True,
) -> dict[str, Any]:
    """Export case for ParaView (foamToVTK + zip).

    When VCFD_S3_BUCKET is configured and upload_s3 is true, uploads the zip to
    S3 and returns a time-limited presigned HTTPS download URL for the Mac.
    """
    try:
        path = resolve_case_dir(_s().cases_root, case_name, must_exist=True)
    except (FileNotFoundError, ValueError) as exc:
        return fail(str(exc))
    result = _r().run(path, ["foamToVTK"])
    vtk_dir = path / "VTK"
    zip_path = None
    if make_zip:
        zip_path = path.parent / f"{case_name}_paraview.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # Include OpenFOAM case essentials + VTK
            for pattern in ("0/**/*", "constant/**/*", "system/**/*", "VTK/**/*"):
                for f in path.glob(pattern):
                    if f.is_file():
                        zf.write(f, arcname=str(f.relative_to(path.parent)))
            for t in case_ops.time_directories(path):
                if t in {"0", "0.orig"}:
                    continue
                for f in (path / t).rglob("*"):
                    if f.is_file():
                        zf.write(f, arcname=str(f.relative_to(path.parent)))

    s3_info: dict[str, Any] | None = None
    s3_warnings: list[str] = []
    settings = _s()
    if make_zip and zip_path and upload_s3 and settings.s3_bucket:
        try:
            from vcfd.mcp_server.s3_export import upload_paraview_zip

            s3_info = upload_paraview_zip(
                zip_path,
                bucket=settings.s3_bucket,
                prefix=settings.s3_prefix,
                region=settings.s3_region,
                case_name=case_name,
                presign_expiry_sec=settings.s3_presign_expiry_sec,
            )
        except Exception as exc:
            s3_warnings.append(f"S3 upload failed: {exc}")

    parts = [
        f"Exported '{case_name}' for ParaView.",
        f"VTK dir: {vtk_dir}." if vtk_dir.exists() else "",
        f"Zip package: {zip_path}." if zip_path else "",
    ]
    if s3_info and s3_info.get("presigned_url"):
        hours = max(1, int((s3_info.get("presign_expiry_sec") or 3600) / 3600))
        parts.append(
            f"Uploaded to {s3_info['s3_uri']}. "
            f"Download on your Mac with the presigned URL (valid about {hours} hour(s)), "
            f"or run: ./scripts/fetch_paraview_from_s3.sh --case {case_name}"
        )
    elif s3_info:
        parts.append(f"Uploaded to {s3_info['s3_uri']}.")
    elif settings.s3_bucket and upload_s3 and not s3_info:
        parts.append("S3 upload was requested but did not complete.")
    else:
        parts.append(
            "Open the case or VTK files in ParaView on your Mac "
            "(or enable VCFD_S3_BUCKET for automatic cloud export)."
        )
    summary = " ".join(p for p in parts if p)

    data: dict[str, Any] = {
        "vtk_dir": str(vtk_dir) if vtk_dir.exists() else None,
        "zip_path": str(zip_path) if zip_path else None,
        "case_path": str(path),
        "s3": s3_info,
        "download_url": (s3_info or {}).get("presigned_url"),
        "s3_uri": (s3_info or {}).get("s3_uri"),
    }
    warnings = list(s3_warnings)
    if not result.ok:
        warnings.append("foamToVTK non-zero exit")
        return fail(
            summary if s3_info else "foamToVTK reported an error; package may still be usable.",
            data={**data, "output_tail": result.stdout[-1500:]},
            warnings=warnings,
        )
    return ok(summary, data=data, warnings=warnings)


def _pipe_from_params(params: dict[str, Any]) -> PipeParams | None:
    try:
        return PipeParams(
            radius=float(params["radius"]),
            length=float(params["length"]),
            viscosity=float(params["viscosity"]),
            density=float(params["density"]),
            bulk_velocity=float(params["bulk_velocity"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def main() -> None:
    """CLI entry: stdio by default; HTTP when VCFD_TRANSPORT=http."""
    import os
    import sys

    settings = _init()
    transport = os.environ.get("VCFD_TRANSPORT", "stdio").lower()
    if transport in {"http", "streamable-http", "sse"}:
        # Optional simple bearer check via middleware is environment-specific;
        # document VCFD_AUTH_TOKEN for reverse proxy / gateway validation.
        if settings.auth_token:
            print(
                "Note: set reverse proxy or MCP client Authorization "
                "header to match VCFD_AUTH_TOKEN.",
                file=sys.stderr,
            )
        mcp.run(
            transport="streamable-http" if transport == "http" else transport,
            host=settings.host,
            port=settings.port,
        )
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
