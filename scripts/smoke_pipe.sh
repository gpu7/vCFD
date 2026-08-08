#!/usr/bin/env bash
# Offline smoke: create → mesh → solve → compare (mock mode).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export VCFD_OPENFOAM_MODE=mock
export VCFD_CASES_ROOT="$ROOT/cases/workspace"
export VCFD_TEMPLATES_ROOT="$ROOT/cases/templates"
export VCFD_JOBS_ROOT="$ROOT/.vcfd/jobs"
uv run pytest tests/test_tools_mock.py -q
echo "smoke_pipe: OK"
