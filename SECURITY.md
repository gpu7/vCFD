# Security Policy

## Scope

vCFD is an MCP controller that launches **OpenFOAM** as an external process and exports results for ParaView. It does not modify OpenFOAM.

This policy covers the vCFD server, case templates, deploy scripts, and voice-agent prompts in this repository.

GitHub **code scanning** (CodeQL) runs on `master` and pull requests. Maintainers review alerts at
https://github.com/gpu7/vCFD/security/code-scanning.

## Supported versions

| Version | Supported |
| --- | --- |
| 0.1.0 | Yes |
| Older | No |

Security fixes land on the default branch (`master`).

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security-sensitive findings.

Prefer one of:

1. **GitHub private vulnerability reporting** for this repository
   (Security tab → Report a vulnerability), or
2. Email the maintainer via the address listed on the [GitHub profile](https://github.com/gpu7) if private reporting is unavailable.

Please include:

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Any suggested fix, if known
- Affected version or commit

### Response time

- We will acknowledge receipt within **48 hours**.
- We aim to provide a fuller response within **7 business days**.

### Responsible disclosure

- Do not publicly disclose the vulnerability until we have had time to address it.
- Give us a reasonable time to fix the issue before publishing.

Do not include live tokens, AWS keys, or contents of `deploy/aws/out/` in a report. Describe the impact and redact secrets.

## Security updates

Security fixes ship on `master` and are noted in the GitHub release or commit history for that change.

## Security best practices

### For everyone

- Use the current `master` or the latest release.
- Never commit `.env`, `deploy/aws/out/`, `*.pem`, `*.key`, or API keys.
- `.env.example` lists variable names only. Leave secret values empty.
- Treat any secret that has appeared in chat, tickets, or logs as compromised.
- Install and run **git-secrets** on developer clones (hooks + AWS patterns + working-tree and history scans). Steps: [docs/security-hardening.md](docs/security-hardening.md#git-secrets-required-operator-tooling).
- Run **TruffleHog** over full git history (`trufflehog git file:///path/to/vCFD --results=verified,unknown`). Steps: [docs/security-hardening.md](docs/security-hardening.md#trufflehog-required-operator-tooling--full-git-history).
- Run **Gitleaks** over full git history (`gitleaks git -v`, optional JSON report / `--redact`). Steps: [docs/security-hardening.md](docs/security-hardening.md#gitleaks-required-operator-tooling--full-git-history).

### For operators and integrators

- Configure secrets with environment variables or a secrets manager, not hard-coded source.
- Keep `VCFD_AUTH_TOKEN` long and random. Require it on remote MCP HTTP.
- Prefer HTTPS for remote MCP (domain + Caddy, or a stable tunnel).
- Restrict SSH to your current `/32`. Refresh rules with `./update-aws-sg-my-ip.sh` when your IP changes.
- Do not publish the Docker socket. The OpenFOAM container uses the host socket on a single-tenant worker. That mount is high privilege.
- `delete_case` and `clean_case` require `confirm=true`.
- Mock mode and an empty auth token are for local development. Do not reuse that setup on a public host.
- Keep the host, Docker images, and dependencies updated.
- Maintain a private inventory of secrets and rotation notes (password manager), not in git.

### Scope notes

- Do not report OpenFOAM itself here unless the issue is in how vCFD invokes or exposes it.
- Do not report secrets found in **your** deployment (`/etc/vcfd/vcfd.env`, AWS keys, xAI tokens). Those belong in your secret store, not in git.
- Rotate public demo tokens and ephemeral tunnel URLs if they leave a controlled environment.

### Incident handling (summary)

If a credential or host may be compromised: contain access (stop the MCP service, tighten the security group), rotate `VCFD_AUTH_TOKEN` and cloud keys, stop or isolate affected systems, and restore only from a trusted image. Report product vulnerabilities through the path above, not a public issue.

Operator runbook: [docs/security-hardening.md](docs/security-hardening.md).

### Remote MCP and EC2

A public MCP endpoint is not the default. Before one is exposed:

- Complete the hardening checklist in [docs/security-hardening.md](docs/security-hardening.md).
- Set a unique `VCFD_AUTH_TOKEN`. Do not copy a lab token.
- Put TLS in front of port 8000. Do not leave the token optional.

### What we do not publish

We document security posture at a high level. We do not publish operational secrets, private infrastructure details that enable abuse, or exploit write-ups in public docs.

Lightning, macaroon, and wallet-seed guidance from other projects does not apply here. vCFD does not hold payment keys.

---

Thank you for helping keep vCFD secure.
