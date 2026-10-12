# Security hardening

**Audience:** Operator.
**Related:** [SECURITY.md](../SECURITY.md) · [architecture.md](./architecture.md) · [deploy/aws/README.md](../deploy/aws/README.md)

**Goal:** Keep lab habits (empty auth token, local Docker, mock OpenFOAM) from becoming the configuration of a public MCP host. This is a checklist and policy doc, not a penetration test.

Adapted from the agent-bitcoin operator checklist. Lightning macaroons, wallet seeds, LND gRPC, and mainnet payment limits are omitted: vCFD does not hold those secrets. The analogue of "lab vs mainnet" here is **mock / local Docker** vs **EC2 or any public MCP URL**.

Grok agents in this repo also load `.grok/config.toml` (permission deny rules) and may opt into `.grok/sandbox.toml` profile `vcfd` (`grok --sandbox vcfd`). Those files block reading `.env`, keys, and `deploy/aws/out/`. They are not a substitute for this checklist.

---

## Secrets inventory (keep offline)

Maintain this list in a **password manager**, not git.

| Secret | Where used | Rotate when |
|--------|------------|-------------|
| `VCFD_AUTH_TOKEN` | Remote MCP bearer token | Leak, before any public host, staff change |
| AWS SSH key | EC2 admin | Compromise or key loss |
| AWS API keys | `launch-ec2.sh`, security-group script | Quarterly or on leak |
| S3 credentials | ParaView zip upload (`VCFD_S3_*`) | Leak or bucket policy change |
| Files under `deploy/aws/out/` | `latest.token`, `latest.env`, user-data | After every launch that printed a token; never commit |
| Caddy / TLS material | HTTPS on the MCP host | Certificate reissue or host compromise |
| xAI API key | Voice agent, if used outside Grok Build login | Leak |

**Rotation (bearer token):**

```bash
openssl rand -hex 32
# set VCFD_AUTH_TOKEN on the server; restart the MCP process
# revoke the old token by not deploying it; update the voice-agent MCP client
```

Do not store the new token in git, in `docs/`, or in a chat log.

---

## Network exposure (must-pass)

| Port / service | Local lab | Public MCP host |
|----------------|-----------|-----------------|
| SSH 22 | Your IP `/32` | Your IP `/32` only |
| MCP 8000 | Localhost or Docker publish on your machine | TLS reverse proxy (Caddy) **and** `VCFD_AUTH_TOKEN` |
| Docker socket | Local daemon for OpenFOAM | Host socket for the solver container only. Do not publish it |
| S3 | Optional | Bucket not public. Presigned URLs expire (`VCFD_S3_PRESIGN_EXPIRY_SEC`) |

`./update-aws-sg-my-ip.sh` refreshes SSH for your current IP. It must not open the MCP port to the world without the token and TLS. Review the group after changes:

```bash
aws ec2 describe-security-groups --group-ids "$SG_ID" --query 'SecurityGroups[0].IpPermissions'
```

---

## Lab vs remote credentials

| Item | Mock / local Docker | EC2 or public URL |
|------|---------------------|-------------------|
| `VCFD_AUTH_TOKEN` | Empty is acceptable for stdio and localhost | **Unique, long, random.** Never reuse the lab value |
| `VCFD_OPENFOAM_MODE` | `mock` for tests; `docker` for a real local solve | `docker` (or `native` if OpenFOAM is installed on the host) |
| `deploy/aws/out/` | Absent | Gitignored. Permission and sandbox rules deny it to agents |
| Case data | `cases/workspace/` gitignored | Same. Not a secret store, but do not publish raw cases blindly |

---

## Token and case-data hygiene

Replaces macaroon guidance from other projects. vCFD secrets are bearer tokens and cloud keys, not Lightning credentials.

- Env files that hold a real token: `chmod 600`
- gitignore already blocks `.env`, `.env.*` except `.env.example`, `*.pem`, and `deploy/aws/out/`
- Do not `scp` a token into the repo tree
- `delete_case` and `clean_case` require `confirm=true`
- Case names are jailed under the cases root. Do not pass unsanitized paths into OpenFOAM commands

---

## Git and local paths

Ensure these never land in commits:

- `.env` (`.env.example` is allowed)
- `deploy/aws/out/` (`latest.token`, `latest.env`, user-data scripts)
- `*.pem`, `*.key`, SSH private keys, AWS access keys, xAI API keys
- Gitleaks or TruffleHog report files (they can echo the secret)

```bash
git status   # clean of secrets before every push
```

`cases/workspace/`, `results/`, and `.vcfd/` are gitignored runtime output. They are not credential denials. Agents may read them to debug a solve.

### `git-secrets` (required operator tooling)

Use [git-secrets](https://github.com/awslabs/git-secrets) so commits and history are scanned for common credential patterns (especially AWS keys). Install once per developer machine that touches this repo.

**Install (macOS):**

```bash
brew install git-secrets
cd /path/to/vCFD   # repo root
```

**Hooks (recommended — blocks matching secrets at commit time):**

```bash
git secrets --install
git secrets --register-aws   # common AWS key patterns
```

`--install` wires pre-commit / commit-msg / prepare-commit-msg hooks for **this clone**. Run it again after a fresh clone. Hooks are local; they are not committed.

**Scan working tree / staged files:**

```bash
git secrets --scan
```

**Scan entire history** (before a public mirror or any backup that includes `.git`):

```bash
git secrets --scan-history
```

**If a scan fails:** treat the hit as a real secret until proven otherwise. Do **not** rewrite history on a shared branch without a rotation plan. Rotate the credential first, then scrub history only with an explicit operator decision (and force-push policy). Prefer fixing the file over a broad `git secrets --add --allowed` entry.

### TruffleHog (required operator tooling — full git history)

Use [TruffleHog](https://github.com/trufflesecurity/trufflehog) as a deeper secret scan of the **entire git history**. It complements `git-secrets`. Run both before publishing a mirror or backing up `.git`.

**Install (macOS):**

```bash
brew install trufflehog
```

**Scan this repo’s history** (run from *outside* the repo directory):

```bash
# From *outside* the repo directory
trufflehog git file:///path/to/vCFD --results=verified,unknown
```

Replace `/path/to/vCFD` with the absolute path to your clone (example: `file:///Users/you/vCFD`).

| Flag / filter | Meaning |
|---------------|---------|
| `git file:///…` | Scan local git history via filesystem URL |
| `--results=verified,unknown` | Report verified findings and unknown (needs review) |

**How these tools differ:**

| Tool | Best for |
|------|----------|
| `git-secrets` | Pre-commit hooks; quick AWS-pattern scan of tree/history |
| TruffleHog | Broader detectors + verification over full history |
| Gitleaks | Fast full-history rules engine; JSON reports; redacted console output |

**If TruffleHog reports findings:** treat `verified` hits as real secrets until proven otherwise. Rotate first, then decide on history rewrite only with an explicit operator plan. Document accepted false positives offline. Do not commit real secrets as fixtures.

You can also scan the remote (`trufflehog git https://github.com/gpu7/vCFD.git`). Prefer a clean local `master` so you know which commit range was scanned.

### Gitleaks (required operator tooling — full git history)

Use [Gitleaks](https://github.com/gitleaks/gitleaks) for a rules-based full-history scan. Run it with the other two tools before a long-lived backup that includes `.git`.

**Install (macOS):**

```bash
brew install gitleaks
cd /path/to/vCFD   # repo root
```

**Full history scan:**

```bash
gitleaks git -v
```

**Save a report** (keep it **outside** the repo — reports may contain secret material). `gitleaks-report.json` is not gitignored today. Do not write it into the work tree.

```bash
gitleaks git --report-path "$HOME/vcfd-gitleaks-report.json" --report-format json
```

**Redact secrets in console output:**

```bash
gitleaks git --redact -v
```

| Flag | Meaning |
|------|---------|
| `git` | Scan git history of the current repository |
| `-v` | Verbose findings |
| `--report-path` / `--report-format json` | Write machine-readable results |
| `--redact` | Mask secret values in printed output (still treat as sensitive) |

**If Gitleaks reports findings:** same policy as the other scanners. Rotate first. History rewrite only with an explicit operator decision. Prefer fixing or removing committed material over broad allowlists. A local `.gitleaks.toml` allowlist is only for a proven false positive.

---

## GitHub repository security (Free tier, public repo)

**Goal:** Block silent direct pushes to `master` without requiring a second human reviewer. Solo maintainer and automated agents keep the **PR → CI green → merge** workflow.

**Already in repo:** `SECURITY.md`, CI workflow `CI` (job `test`: pytest + ruff), CodeQL workflow, Dependabot. There is no CODEOWNERS file. Do not turn on required code-owner review until a second reviewer exists.

### Solo-friendly policy

| Control | Setting | Why |
|---------|---------|-----|
| Require pull request before merging | **On** | No direct `git push` to `master` as the normal path |
| Required approving reviews | **0** | Solo; agents can merge after CI |
| Require review from Code Owners | **Off** | No CODEOWNERS file |
| Require status checks | **On** → `test` | Job name in workflow `CI` |
| Block force pushes | **On** | Protect history |
| Restrict deletions of `master` | **On** | Safety |
| Allow admin bypass of rules | **Off** if possible | Stops accidental force-push. Merging a PR still works |

**Do not enable (for now):** required approvals ≥ 1. That needs a second human and blocks solo merges.

### Step-by-step (GitHub UI) — operator does once

#### 1) Code security toggles

1. Open https://github.com/gpu7/vCFD/settings/security_analysis
   (or **Settings → Code security**).
2. Enable (where shown):
   - Dependency graph
   - Dependabot alerts
   - Dependabot security updates
   - Secret scanning
   - Push protection
   - Private vulnerability reporting
   - **Code scanning** — in-repo workflow `.github/workflows/codeql.yml` (Python, weekly and on pull requests). Alerts: **Security → Code scanning**.
3. Leave paid-only options alone.

#### 2) Pull request defaults

1. **Settings → General → Pull Requests**
2. Enable **Automatically delete head branches**
3. Squash and merge commits are both acceptable

#### 3) Branch ruleset on `master`

1. **Settings → Rules → Rulesets → New ruleset → New branch ruleset**
2. Name: `protect-master`
3. Enforcement status: **Active**
4. Target branches: **Include default branch** (this repo's default is `master`, not `main`)
5. Rules:
   - **Restrict deletions** — On
   - **Block force pushes** — On
   - **Require a pull request before merging** — On
     - Required approvals: **0**
     - Do **not** require review from Code Owners
   - **Require status checks to pass** — On
     - Add check: **`test`** (from workflow **CI**)
6. Bypass list: leave **empty**.
7. Save the ruleset.

#### 4) Verify

```bash
# From a clone — should FAIL once the ruleset is active
git checkout master && git pull
git commit --allow-empty -m "test: direct push should fail"
git push origin master
# expect: rejected by ruleset / protected branch

git reset --hard origin/master
```

Then confirm the PR path still works:

```bash
git checkout -b chore/verify-branch-protection
git commit --allow-empty -m "test: PR path"
git push -u origin HEAD
gh pr create --base master --title "test: verify branch protection" --body "Temp PR; merge after CI is green."
# Wait for job test → merge → delete branch
```

#### 5) Account hygiene (not repo settings)

- Enable **2FA** on the `gpu7` GitHub account
- Prefer fine-grained PATs; revoke unused classic tokens

### If settings become burdensome

Back off in this order:

1. Turn off "require conversation resolution" if you enabled it
2. Turn off "require branch up to date" if you enabled it
3. Allow admin bypass for emergencies only
4. Last resort: disable the ruleset

Do not disable secret scanning or push protection for convenience.

### Agent / Grok workflow after protection

1. Branch from `master` → commit → push the branch
2. `gh pr create --base master`
3. Wait for job **`test`** to pass
4. `gh pr merge` (squash or merge commit). No second reviewer
5. Do **not** `git push origin master`

Project permission rules deny `git push origin master`, `git push origin main`, and force-push. A normal feature-branch push stays allowed.

---

## Operator checklist

- [ ] Secrets inventory exists offline (password manager)
- [ ] `VCFD_AUTH_TOKEN` rotated if it was ever shared in chat or committed
- [ ] Security group reviewed: SSH is your `/32`; MCP is not world-open without token and TLS
- [ ] Public host does not reuse an empty lab token
- [ ] Docker socket is not published
- [ ] Read [SECURITY.md](../SECURITY.md) reporting path
- [ ] `git-secrets` installed; hooks installed; `git secrets --register-aws` done
- [ ] `git secrets --scan` clean on the working tree
- [ ] `git secrets --scan-history` run at least once
- [ ] TruffleHog installed; `trufflehog git file:///…/vCFD --results=verified,unknown` run at least once
- [ ] Gitleaks installed; `gitleaks git --redact -v` run at least once; report kept outside the repo
- [ ] GitHub: secret scanning, push protection, and Dependabot alerts enabled
- [ ] GitHub: `protect-master` ruleset active (PR + job `test`, **0** required approvals)
- [ ] Verified: direct push to `master` rejected; PR merge still works solo

---

## Incident quick path

1. Contain: stop the MCP service, revoke or tighten the security group, stop the EC2 instance if needed
2. Rotate `VCFD_AUTH_TOKEN`, AWS keys, S3 credentials, and the SSH key if it was exposed
3. Invalidate old presigned S3 URLs by rotating credentials or waiting out `VCFD_S3_PRESIGN_EXPIRY_SEC`
4. Restore only from a trusted image or a clean git checkout. Do not restore `deploy/aws/out/` from an untrusted copy
5. Report product vulnerabilities privately ([SECURITY.md](../SECURITY.md))

There is no wallet, macaroon, or channel to revoke. Case directories under `cases/workspace/` are simulation data.

---

## Deliverables in git

- [x] This checklist
- [x] `SECURITY.md` disclosure path and operator rules
- [x] `.grok/config.toml` permission deny / ask rules
- [x] `.grok/sandbox.toml` opt-in profile `vcfd`
- [ ] Operator completed the checklist above (human step, not done by adding this file)
