# vCFD

**Voice-driven CFD:** [Grok Voice](https://x.ai/api/voice) + [MCP](https://modelcontextprotocol.io/) + [OpenFOAM](https://gitlab.com/openfoam/core/openfoam) + [ParaView](https://www.paraview.org/).

Speak natural language commands; a Grok voice agent calls vCFD MCP tools that set up and run OpenFOAM cases, then summarize results and export data for ParaView on your Mac.

> **JARVIS for CFD (pragmatic edition):** full-duplex speech → tool calls → async solvers → spoken engineering summaries. Not movie magic—solid async job handling and careful tool design.

## Architecture

```
Human (speech)
    ↕ Speech-to-Speech
Grok Voice / Voice Agent Builder
    ↓ Remote MCP (HTTP/SSE + auth)
vCFD MCP Server (Python / FastMCP)
    ↓ subprocess or Docker
OpenFOAM cases & solvers
    ↓ foamToVTK / case zip
ParaView (Mac)
```

vCFD **does not modify OpenFOAM**. It launches OpenFOAM executables and edits case dictionaries. OpenFOAM remains a separate GPLv3 runtime (see [NOTICE](NOTICE)).

## Quick start (Mac Silicon)

### Requirements

- Python 3.12+ and [uv](https://github.com/astral-sh/uv)
- Optional: Docker (for real OpenFOAM; mock mode works offline)
- Optional: ParaView (visualization)
- [Grok Build](https://x.ai) for agentic development / local MCP

### Install

```bash
git clone https://github.com/gpu7/vCFD.git
cd vCFD
uv sync
```

### Run tests (mock OpenFOAM)

```bash
uv run pytest -q
```

### Run MCP server (stdio)

```bash
export VCFD_OPENFOAM_MODE=mock   # or docker | native
./scripts/dev_stdio.sh
```

### Attach to Grok Build

```bash
grok mcp add vcfd -- uv run --directory /path/to/vCFD vcfd-mcp
```

Or configure in `~/.grok/config.toml`:

```toml
[mcp_servers.vcfd]
command = "uv"
args = ["run", "--directory", "/path/to/vCFD", "vcfd-mcp"]
env = { VCFD_OPENFOAM_MODE = "mock" }
enabled = true
```

### First case: Hagen–Poiseuille pipe

Through MCP tools (or voice):

1. `create_case(name="pipe1", template="hagen_poiseuille")`
2. `set_pipe_parameters(case_name="pipe1", radius=0.05, bulk_velocity=0.1)`
3. `generate_mesh(case_name="pipe1")` → `check_mesh(...)`
4. `start_solver(case_name="pipe1")` → `get_job_status(job_id=...)`
5. `summarize_results` / `compare_to_analytical`
6. `export_for_paraview` → open zip/VTK in ParaView

## OpenFOAM modes

| Mode | Env | Use when |
|------|-----|----------|
| `mock` | `VCFD_OPENFOAM_MODE=mock` | Unit tests, no OF install |
| `docker` | `VCFD_OPENFOAM_MODE=docker` | Mac or EC2 with Docker |
| `native` | `VCFD_OPENFOAM_MODE=native` | Ubuntu with OF packages |

See `.env.example` for all settings.

## Voice agent

1. Deploy MCP with HTTP transport (`vcfd serve --transport http`).
2. Protect with `VCFD_AUTH_TOKEN` + reverse proxy TLS.
3. Register remote MCP in Grok Voice Agent Builder or Speech-to-Speech `session.update`.
4. Use system prompt in [`prompts/voice_agent_system.md`](prompts/voice_agent_system.md).

## AWS EC2

See [`deploy/aws/README.md`](deploy/aws/README.md) for Ubuntu host setup, systemd, Docker Compose, and security notes.

## Project layout

```
src/vcfd/           # MCP server, OpenFOAM runner, analytics
cases/templates/    # OpenFOAM case templates (not OF source)
tests/              # pytest
deploy/             # Docker, systemd, AWS notes
prompts/            # Voice agent system prompt
scripts/            # dev helpers
```

## License

- **vCFD code:** [MIT](LICENSE)
- **OpenFOAM:** GPLv3 (external dependency — not distributed as part of this repo’s source)

You may charge for applications or services built with vCFD as an external controller of OpenFOAM. Do not link or redistribute modified OpenFOAM without complying with GPLv3.

## Status

MVP scaffold: mock end-to-end pipe pipeline, MCP tools, analytics, deploy stubs. Real OpenFOAM Docker/native runs and production voice wiring are the next hardening steps.
