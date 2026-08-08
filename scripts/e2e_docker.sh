#!/usr/bin/env bash
# End-to-end pipe case using OpenFOAM in Docker.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export VCFD_OPENFOAM_MODE=docker
export VCFD_OPENFOAM_DOCKER_IMAGE="${VCFD_OPENFOAM_DOCKER_IMAGE:-opencfd/openfoam-default:2506}"
export VCFD_CASES_ROOT="$ROOT/cases/workspace"
export VCFD_TEMPLATES_ROOT="$ROOT/cases/templates"
export VCFD_JOBS_ROOT="$ROOT/.vcfd/jobs"

if ! docker image inspect "$VCFD_OPENFOAM_DOCKER_IMAGE" >/dev/null 2>&1; then
  echo "Pulling $VCFD_OPENFOAM_DOCKER_IMAGE ..."
  docker pull "$VCFD_OPENFOAM_DOCKER_IMAGE"
fi

NAME="e2e_pipe_$$"
uv run python - <<PY
import time
from pathlib import Path
from vcfd.config import Settings, OpenFOAMMode
from vcfd.mcp_server import server as srv

settings = Settings(
    cases_root=Path("$VCFD_CASES_ROOT"),
    templates_root=Path("$VCFD_TEMPLATES_ROOT"),
    jobs_root=Path("$VCFD_JOBS_ROOT"),
    openfoam_mode=OpenFOAMMode.DOCKER,
    openfoam_docker_image="$VCFD_OPENFOAM_DOCKER_IMAGE",
    max_concurrent_jobs=2,
    default_job_timeout_sec=600,
)
srv._init(settings)
name = "$NAME"
assert srv.create_case(name=name, template="hagen_poiseuille")["success"]
assert srv.set_pipe_parameters(case_name=name, viscosity=0.1, density=1000.0, bulk_velocity=0.1)["success"]
assert srv.generate_mesh(case_name=name)["success"]
assert srv.check_mesh(case_name=name)["success"]
r = srv.start_solver(case_name=name)
assert r["success"], r
job_id = r["job_id"]
for _ in range(180):
    st = srv.get_job_status(job_id=job_id)
    if st["data"]["state"] in {"finished", "failed", "stopped"}:
        break
    time.sleep(1)
assert st["data"]["state"] == "finished", st
cmp = srv.compare_to_analytical(case_name=name)
print(cmp["summary"])
ex = srv.export_for_paraview(case_name=name)
print(ex["summary"])
print("E2E_DOCKER_OK", name)
PY
