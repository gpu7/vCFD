"""End-to-end MCP tool flow in mock OpenFOAM mode."""

from pathlib import Path

from vcfd.config import OpenFOAMMode, Settings
from vcfd.mcp_server import server as srv

REPO = Path(__file__).resolve().parents[1]


def _setup(tmp_path: Path) -> Settings:
    settings = Settings(
        cases_root=tmp_path / "workspace",
        templates_root=REPO / "cases" / "templates",
        jobs_root=tmp_path / "jobs",
        openfoam_mode=OpenFOAMMode.MOCK,
        max_concurrent_jobs=4,
        default_job_timeout_sec=60,
    )
    settings.ensure_dirs()
    srv._init(settings)
    return settings


def test_full_pipe_pipeline_mock(tmp_path: Path):
    _setup(tmp_path)

    r = srv.create_case(name="pipe_demo", template="hagen_poiseuille")
    assert r["success"] is True

    r = srv.set_pipe_parameters(
        case_name="pipe_demo",
        radius=0.05,
        bulk_velocity=0.1,
        viscosity=0.1,
        density=1000.0,
    )
    assert r["success"] is True
    assert abs(r["data"]["reynolds_number"] - 100.0) < 1e-9

    r = srv.generate_mesh(case_name="pipe_demo", background=False)
    assert r["success"] is True

    r = srv.check_mesh(case_name="pipe_demo")
    assert r["success"] is True

    r = srv.start_solver(case_name="pipe_demo")
    assert r["success"] is True
    job_id = r["job_id"]
    assert job_id

    # Wait briefly for mock job thread
    import time

    for _ in range(50):
        st = srv.get_job_status(job_id=job_id)
        if st["data"].get("state") in {"finished", "failed", "stopped"}:
            break
        time.sleep(0.05)

    st = srv.get_job_status(job_id=job_id)
    assert st["data"]["state"] == "finished"

    r = srv.summarize_results(case_name="pipe_demo")
    assert r["success"] is True

    r = srv.compare_to_analytical(case_name="pipe_demo")
    assert r["success"] is True
    assert "re" in r["data"]
    # Mock U is uniform inlet velocity; profile error vs parabola is expected large.
    assert r["data"]["max_rel_error"] >= 0

    r = srv.export_for_paraview(case_name="pipe_demo")
    assert r["success"] is True
    assert r["data"].get("zip_path")

    r = srv.delete_case(case_name="pipe_demo", confirm=False)
    assert r["success"] is False
    r = srv.delete_case(case_name="pipe_demo", confirm=True)
    assert r["success"] is True


def test_list_empty(tmp_path: Path):
    _setup(tmp_path)
    r = srv.list_cases()
    assert r["success"] is True
    assert r["data"]["cases"] == []
