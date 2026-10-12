# AGENTS.md — vCFD

Project rules for AI coding agents (Grok, Claude, Cursor, and others) working in this repository.
Keep this file actionable. Prefer links to `README.md`, `docs/`, and `SECURITY.md` over duplicating long docs.

Adapted from the agent-bitcoin agent rules. Payment, Lightning, LND, and mainnet-wallet personas are omitted: this repo is an OpenFOAM controller, not a wallet.

---

## 1. Project overview and goals

**vCFD** is a voice-driven CFD controller. A Grok voice agent calls MCP tools that set up and run OpenFOAM cases, then summarize results and export data for ParaView.

### Goals

- Expose a small, speakable MCP tool surface for case setup, meshing, solving, and export.
- Keep long solver runs async (`job_id`, then `get_job_status`).
- Stay secure by default: no secrets in git, path-jailed cases, confirm flags on destructive tools, bearer auth on remote HTTP MCP.

### Non-goals (unless explicitly requested)

- Forking or patching OpenFOAM. vCFD launches OpenFOAM and edits case dictionaries.
- Silent EC2 launch, teardown, or security-group changes.
- Deleting or cleaning a case without `confirm=true`.
- New physics templates beyond what the task asks for.

### Key paths

| Path | Role |
|------|------|
| `src/vcfd/mcp_server/server.py` | FastMCP tools |
| `src/vcfd/mcp_server/foam_runner.py` | mock / docker / native OpenFOAM |
| `src/vcfd/mcp_server/jobs.py` | Async job records under `.vcfd/jobs/` |
| `src/vcfd/config.py` | `VCFD_*` settings |
| `src/vcfd/analytics/poiseuille.py` | Hagen–Poiseuille checks |
| `cases/templates/hagen_poiseuille/` | Only built-in case template |
| `cases/workspace/` | Runtime cases (gitignored) |
| `tests/` | pytest against mock OpenFOAM |
| `deploy/aws/` | EC2 launch, Caddy, status, teardown |
| `prompts/` | Voice agent system prompt |
| `scripts/` | stdio dev server, Docker e2e, ParaView S3 helpers |
| `.grok/config.toml` | Project MCP server + permission allow/ask/deny |
| `.grok/sandbox.toml` | Opt-in sandbox profile `vcfd` |

### OpenFOAM modes

| Mode | When |
|------|------|
| `mock` | Unit tests and offline work. Default in `.env.example`. |
| `docker` | Real OpenFOAM (`opencfd/openfoam-default:2506`). Verified path on Mac Silicon. |
| `native` | Host OpenFOAM install. Do not assume it exists. |

Remote HTTP MCP requires a long random `VCFD_AUTH_TOKEN` and TLS. An empty token is for local mock or local Docker only.

---

## 2. Development sub-agents (personas for this repo)

When work is multi-step, delegate with Grok subagents. Use `general-purpose` for implementation, `explore` for read-only investigation, `plan` for design.

### 2.1 Orchestrator

- Owns the user goal, PR scope, and merge readiness.
- Does not launch or tear down EC2, delete cases, or push `master` without an explicit request.
- Keeps secrets out of commits, logs, and chat.

### 2.2 OpenFOAM case agent

**Responsibilities:** templates, `blockMeshDict`, boundary fields, `vcfd.json`, `pipe_params`, mesh and solver invocation.

**Do not:** edit OpenFOAM itself; commit `cases/workspace/`, VTK, or `results/`.

### 2.3 MCP tool agent

**Responsibilities:** tool names, the `{summary, success, job_id, data, warnings}` result contract, job polling, confirm flags.

**Do not:** add a tool that shells out with an unsanitized case name or writes outside the cases root.

### 2.4 Security agent

**Responsibilities:** `VCFD_AUTH_TOKEN`, AWS keys, S3 credentials, SSH keys, `deploy/aws/out/`, `.env`, `*.pem`.

**Rules**

- Never commit `.env`, `deploy/aws/out/`, pem or key files, or live bearer tokens.
- Never read those paths into a chat reply. `.env.example` is safe; `.env` is not.
- Follow `SECURITY.md` and `docs/security-hardening.md`. No public issue with exploit detail or secrets.
- Docker socket access is high privilege. Do not publish the socket or mount extra host paths into the OpenFOAM container.

### 2.5 Testing agent

- `uv run pytest -q` for offline tests.
- Live Docker only when the user asked and Docker is up (`./scripts/e2e_docker.sh`).
- Do not require EC2 or a real token for unit tests.

### 2.6 Docs agent

- Update `README.md` or `docs/` when user-facing workflow or tools change.
- Do not paste live tokens, instance IPs from `deploy/aws/out/`, or presigned URLs.

### 2.7 Deploy agent

**Responsibilities:** `deploy/aws/`, Dockerfile, Caddy, `update-aws-sg-my-ip.sh`.

**Rules**

- Confirm before `launch-ec2.sh`, `teardown.sh`, or security-group edits.
- SSH stays limited to the operator's current `/32`. Do not open MCP port 8000 to the world without the bearer token and TLS.

### User phrases that should select a persona

| User says | Prefer |
|-----------|--------|
| "change the pipe mesh / solver dicts" | OpenFOAM case |
| "add or change an MCP tool" | MCP tool |
| "security review" | Security |
| "add tests" | Testing |
| "update the voice prompt or README" | Docs |
| "EC2 / Caddy / security group" | Deploy |

---

## 3. How to invoke sub-agents

```text
You are the <Persona Name> for vCFD.
Repo root: vCFD (gpu7/vCFD). Default branch: master.
Constraints from AGENTS.md apply (no secrets, confirm destructive tools, do not push master).
Task: <specific outcome>
Done when: <tests / files / commands>
```

Grok permission rules in `.grok/config.toml` deny reads of `.env`, keys, and `deploy/aws/out/`. They also deny `rm -rf`, force-push, and a direct push to `master` or `main`. `delete_case` and `clean_case` are ask rules; the tools still require `confirm=true`.

Sandbox profile `vcfd` is opt-in (`grok --sandbox vcfd`). Project config cannot set `sandbox.profile`.

---

## 4. Preferred model settings

| Setting | Preference |
|---------|------------|
| Model | Session default |
| Reasoning effort | **high** for solver, deploy, auth, and permission changes; **medium** for docs |
| Context | Read targeted files. Do not dump `deploy/aws/out/` or solver logs that may contain tokens |

---

## 5. Coding conventions

- Python **3.12+**. Package manager: **uv** (`uv sync`, `uv run …`).
- Lint: **Ruff** (`uv run ruff check src tests`). Line length 100.
- Settings: **Pydantic** `Settings` with the `VCFD_` prefix.
- MCP: **FastMCP**. Every tool returns `summary`, `success`, optional `job_id`, `data`, and `warnings`.
- Case names go through `validate_case_name` / `resolve_case_dir`.
- Match surrounding style. No drive-by refactors.
- Do not add unsolicited markdown. Update an existing doc when behavior changes.

### Version strings

`pyproject.toml` `version` and `vcfd.__version__` stay in sync. Do not bump them unless the task is a release.

---

## 6. Testing conventions

```bash
uv sync
uv run pytest -q
uv run ruff check src tests
```

Docker end-to-end (optional, needs Docker Desktop and the OpenFOAM image):

```bash
./scripts/e2e_docker.sh
```

Definition of done for code changes:

- Relevant tests pass, or new tests cover the change.
- No secrets in the diff.
- Docs updated if a tool or operator workflow changed.

---

## 7. Project-specific rules

### Where a run is allowed to go

| Environment | Default for development? | Automation allowed? |
|-------------|--------------------------|---------------------|
| **mock** | **Yes** (tests) | Yes |
| **local Docker** | When the user wants a real solve | Yes, on the local machine |
| **native OpenFOAM** | Only if installed | Ask if unsure |
| **EC2 / public MCP** | **No** | Only when the user explicitly asks to launch, update, or tear down |

This replaces the agent-bitcoin regtest / mainnet split. Mock is the lab. A public host with a real token is the production path.

### Security

- Never commit: `.env`, `deploy/aws/out/`, `*.pem`, `*.key`, AWS keys, `VCFD_AUTH_TOKEN`, S3 credentials, SSH private keys, xAI API keys.
- `.env.example` documents names only. Leave secrets empty.
- `delete_case` and `clean_case` require `confirm=true`.
- Report vulnerabilities per `SECURITY.md` (private GitHub report or maintainer email). Do not open a public issue with exploit detail.
- Incident: contain the host, rotate the auth token and cloud keys, restore only from a trusted image. Details in `docs/security-hardening.md`.

### Infrastructure safety

- Prefer `./deploy/aws/status.sh` and `update.sh` over teardown.
- Confirm before: instance terminate, security-group changes, `docker volume` wipes, deleting a case.
- Do not hardcode a live public IP or bearer token into docs or code. `deploy/aws/out/` is gitignored and denied to the agent.

---

## 8. Common commands

```bash
uv sync
uv run pytest -q

export VCFD_OPENFOAM_MODE=mock
./scripts/dev_stdio.sh

# Real OpenFOAM (Docker Desktop)
docker pull opencfd/openfoam-default:2506
./scripts/e2e_docker.sh

# Remote host (only when asked)
./deploy/aws/status.sh
./update-aws-sg-my-ip.sh
```

---

## 9. Git and PR hygiene

- Branch from current `master`. Do not push `master` directly.
- Do not force-push. Do not commit `.env` or `deploy/aws/out/`.
- PR description: what, why, and whether mock tests ran.
- Wait for the CI job `test` (workflow `CI`) before merge.
- Squash or merge commit is fine. Delete the head branch after merge.

---

## 10. Quick decision guide

| Situation | Action |
|-----------|--------|
| Unsure mock vs EC2 | Use **mock**. Ask before any AWS change |
| Touching a tool result | Keep `summary` speakable and `data` structured |
| Touching case paths | Stay inside `resolve_case_dir` |
| "Make the voice agent smarter" | Edit `prompts/`, not scattered strings in the server |
| Secret might be in the diff | Stop. Do not commit. Rotate if it was pushed |

---

*This file is the source of truth for agent behavior in-repo. Human docs remain in `README.md` and `docs/`.*
