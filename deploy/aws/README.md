# AWS EC2 deployment (Ubuntu)

## Recommended starting point

| Item | Suggestion |
|------|------------|
| Instance | `c6i.xlarge` (4 vCPU) or `c6i.large` for demos |
| OS | Ubuntu 24.04 LTS |
| Storage | 50–100 GB gp3 EBS for cases/results |
| Network | Security group: SSH from your IP; HTTPS 443 from internet (or only your IP) |
| TLS | Caddy or nginx + Let’s Encrypt, or ALB + ACM |

## Steps

1. Launch Ubuntu EC2 and attach an EBS volume mounted at `/data/vcfd`.
2. Install Docker **or** OpenFOAM packages + Python 3.12 + `uv`.
3. Clone `https://github.com/gpu7/vCFD` into `/opt/vcfd`.
4. Create `/etc/vcfd/vcfd.env` from `.env.example` with a strong `VCFD_AUTH_TOKEN`.
5. Either:
   - `docker compose -f deploy/docker-compose.yml up -d`, or
   - `uv sync` + install `deploy/systemd/vcfd-mcp.service`.
6. Put Caddy/nginx in front with TLS terminating on 443, proxy to `127.0.0.1:8000`.
7. In Grok Voice Agent Builder (or Speech-to-Speech session), add remote MCP:

```json
{
  "type": "mcp",
  "server_url": "https://YOUR_DOMAIN/mcp",
  "server_label": "vcfd",
  "authorization": "Bearer YOUR_TOKEN"
}
```

Exact MCP path depends on FastMCP streamable-http routing (commonly `/mcp`). Verify with MCP Inspector.

8. Paste system prompt from `prompts/voice_agent_system.md`.

## Secrets

- Store `VCFD_AUTH_TOKEN` and any xAI keys in AWS Secrets Manager or SSM Parameter Store.
- Never commit tokens.

## OpenFOAM on EC2

- **Docker mode**: set `VCFD_OPENFOAM_MODE=docker` and mount docker.sock (understand security implications).
- **Native mode**: install OpenFOAM, set `VCFD_OPENFOAM_MODE=native` and `VCFD_OPENFOAM_BASHRC=/path/to/etc/bashrc`.

## Cost notes

- Stop or hibernate instances when idle.
- Keep demo meshes coarse; cap concurrent jobs via `VCFD_MAX_CONCURRENT_JOBS`.
