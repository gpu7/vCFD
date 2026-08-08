# Security Policy

## Supported versions

Security fixes are applied to the default branch (`master`) of this repository.

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security-sensitive findings.

Prefer one of:

1. **GitHub private vulnerability reporting** for this repository  
   (Security tab → Report a vulnerability), or  
2. Email the maintainer via the address listed on the [GitHub profile](https://github.com/gpu7) if private reporting is unavailable.

Please include:

- Description of the issue and impact
- Steps to reproduce or a proof of concept
- Affected versions / commits if known

We will acknowledge reports when possible and coordinate disclosure.

## Scope notes

- **vCFD** is an MCP controller that launches **OpenFOAM** as an external process. Do not report OpenFOAM itself here unless the issue is in how vCFD invokes or exposes it.
- **Do not** report secrets found in **your** deployment (`/etc/vcfd/vcfd.env`, AWS keys, xAI tokens). Those belong in your secret store, not in git.
- Public demo tokens and ephemeral tunnel URLs should be rotated if exposed outside a controlled environment.

## Hardening expectations for operators

- Keep `VCFD_AUTH_TOKEN` long and random; require it on remote MCP HTTP.
- Prefer HTTPS for remote MCP (domain + Caddy or a stable tunnel).
- Do not commit `.env`, `deploy/aws/out/`, `*.pem`, or API keys.
- Treat Docker socket mounts as high privilege (single-tenant CFD worker).
