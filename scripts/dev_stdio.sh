#!/usr/bin/env bash
# Run vCFD MCP server over stdio for Grok Build / MCP Inspector.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export VCFD_CASES_ROOT="${VCFD_CASES_ROOT:-$ROOT/cases/workspace}"
export VCFD_TEMPLATES_ROOT="${VCFD_TEMPLATES_ROOT:-$ROOT/cases/templates}"
export VCFD_JOBS_ROOT="${VCFD_JOBS_ROOT:-$ROOT/.vcfd/jobs}"
export VCFD_OPENFOAM_MODE="${VCFD_OPENFOAM_MODE:-mock}"
export VCFD_TRANSPORT=stdio
exec uv run vcfd-mcp
