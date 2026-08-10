# AWS EC2 deployment for vCFD

Scripts in this directory launch an Ubuntu 24.04 EC2 host that runs:

- **vCFD MCP** (FastMCP streamable-http on port 8000 inside Docker)
- **Caddy** reverse proxy on **80/443**
- **OpenFOAM** via Docker (`opencfd/openfoam-default:2506`) using the host Docker socket

Your AWS CLI is used from the Mac (`aws sts get-caller-identity`).

## Quick start (from the vCFD repo)

```bash
# 1) Dry-run (no instance created) — validates AMI, VPC, SG plan
./deploy/aws/launch-ec2.sh --dry-run

# 2) Launch (Graviton / arm64 by default — good cost + matches OF arm64 images)
./deploy/aws/launch-ec2.sh

# Or x86:
./deploy/aws/launch-ec2.sh --instance-type c6i.xlarge

# With a real domain for automatic HTTPS:
./deploy/aws/launch-ec2.sh --domain cfd.example.com --email you@example.com
```

Save the printed **VCFD_AUTH_TOKEN** and **public IP**. State is written to:

```
deploy/aws/out/latest.env      # instance id, IP, paths
deploy/aws/out/latest.token    # bearer token only (gitignored)
```

### Status / update / teardown

```bash
./deploy/aws/status.sh
./deploy/aws/update.sh          # git pull + rebuild on the host
./deploy/aws/teardown.sh        # terminate instance
```

### SSH when your home IP changes

```bash
# from repo root
./update-aws-sg-my-ip.sh --dry-run
./update-aws-sg-my-ip.sh   # updates SG port 22 to your current public IP
```

### SSH

```bash
source deploy/aws/out/latest.env
ssh -i "$KEY_FILE" ubuntu@"$PUBLIC_IP"
sudo tail -f /var/log/vcfd-user-data.log
```

Bootstrap typically takes **10–20 minutes** (Docker + OpenFOAM image pull + first build).

## What gets created

| Resource | Name / notes |
|----------|----------------|
| EC2 instance | Tag `Name=vcfd-mcp`, Ubuntu 24.04, default VPC + public IP |
| Key pair | `vcfd-ec2` → `~/.ssh/vcfd-ec2.pem` (created if missing) |
| Security group | `vcfd-mcp-sg`: SSH from your IP `/32`, HTTP/HTTPS from `0.0.0.0/0` |
| Root volume | gp3, default 80 GB |
| On host | `/opt/vcfd` (git clone), `/data/vcfd` (cases/jobs), `/etc/vcfd/vcfd.env` |

## Architecture on the instance

```
Internet → :80/:443 Caddy → vcfd-mcp:8000 (/mcp)
                              ↓ docker.sock
                         OpenFOAM containers
                              ↓
                         /data/vcfd/cases
```

## Grok Voice remote MCP

After the stack is up:

```json
{
  "type": "mcp",
  "server_url": "http://YOUR_PUBLIC_IP/mcp",
  "server_label": "vcfd",
  "authorization": "Bearer YOUR_TOKEN"
}
```

Prefer **HTTPS** once DNS points at the instance:

```json
{
  "type": "mcp",
  "server_url": "https://YOUR_DOMAIN/mcp",
  "server_label": "vcfd",
  "authorization": "Bearer YOUR_TOKEN"
}
```

System prompt: `prompts/voice_agent_system.md`.

> **Note:** Some Voice clients require HTTPS. For IP-only demos, use a tunnel (Cloudflare Tunnel / ngrok) or attach a domain.

## Recommended instance sizes

| Use | Type | Notes |
|-----|------|--------|
| Demo / small laminar cases | `c7g.large` or `c7g.xlarge` | Arm/Graviton, lower cost |
| Heavier CFD | `c7g.2xlarge` or `c6i.2xlarge` | More cores for mesh/solve |
| x86-only images | `c6i.xlarge` | If an OF image is amd64-only |

Default script: **`c7g.xlarge`**.

## Cost control

- Run `./deploy/aws/teardown.sh` when idle (stops compute charges).
- Or stop (not terminate) the instance in the console to keep disk.
- OpenFOAM image + cases use EBS; 80 GB gp3 is a starting point.
- Cap concurrent solvers: `VCFD_MAX_CONCURRENT_JOBS` in `/etc/vcfd/vcfd.env`.

## Security notes

- Bearer token is required for remote MCP when `VCFD_AUTH_TOKEN` is set.
- Docker socket is mounted into the MCP container so it can run OpenFOAM — treat the host as a **single-tenant CFD worker**, not a multi-tenant public PaaS.
- Tighten SG later: restrict 80/443 to your IP or put an ALB + WAF in front.
- Never commit `deploy/aws/out/` or `.pem` files (gitignored).

## Manual / existing instance

1. Launch Ubuntu 24.04 yourself.
2. Copy `user-data.sh` logic or run equivalent steps.
3. Place env at `/etc/vcfd/vcfd.env` (see `env.example`).
4. `docker compose -f deploy/aws/docker-compose.prod.yml up -d` from `/opt/vcfd`.

## Troubleshooting

| Symptom | Check |
|---------|--------|
| SSH timeout | SG SSH CIDR, instance running, public IP |
| `/mcp` connection refused | `sudo tail -100 /var/log/vcfd-user-data.log`, `docker compose ps` |
| OpenFOAM jobs fail | `docker pull opencfd/openfoam-default:2506`, socket mount |
| Auth errors from Voice | Matching `Authorization: Bearer` vs `/etc/vcfd/vcfd.env` |
| HTTPS cert fails | DNS A record, ports 80/443 open, `VCFD_DOMAIN` + email set |

## Next after EC2 is up

1. Confirm `./deploy/aws/status.sh` and hit `/mcp`.
2. Point Grok Voice Agent Builder at the MCP URL + token.
3. Voice: “Create a Hagen–Poiseuille pipe case and mesh it.”
