#!/bin/bash
# cloud-init user-data for Ubuntu 24.04 EC2 — boots a vCFD MCP host.
# Variables below are substituted by launch-ec2.sh (__VCFD_*__ placeholders).
set -euxo pipefail
exec > >(tee /var/log/vcfd-user-data.log | logger -t vcfd-user-data -s 2>/dev/console) 2>&1

export DEBIAN_FRONTEND=noninteractive

VCFD_GIT_URL="__VCFD_GIT_URL__"
VCFD_GIT_REF="__VCFD_GIT_REF__"
VCFD_AUTH_TOKEN="__VCFD_AUTH_TOKEN__"
VCFD_DOMAIN="__VCFD_DOMAIN__"
VCFD_ACME_EMAIL="__VCFD_ACME_EMAIL__"
VCFD_OPENFOAM_DOCKER_IMAGE="__VCFD_OPENFOAM_DOCKER_IMAGE__"
VCFD_MAX_CONCURRENT_JOBS="__VCFD_MAX_CONCURRENT_JOBS__"

echo "==> vCFD bootstrap starting $(date -Is)"

# --- packages ---
apt-get update -y
apt-get upgrade -y
apt-get install -y \
  ca-certificates curl gnupg git jq unzip \
  ufw fail2ban \
  python3 python3-venv python3-pip

# --- Docker (official apt repo) ---
if ! command -v docker >/dev/null 2>&1; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  . /etc/os-release
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
    https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
fi

# --- data dirs ---
mkdir -p /data/vcfd/cases /data/vcfd/jobs /etc/vcfd /opt
chmod 755 /data/vcfd

# --- env file ---
cat > /etc/vcfd/vcfd.env <<EOF
VCFD_CASES_ROOT=/data/vcfd/cases
VCFD_TEMPLATES_ROOT=/opt/vcfd/cases/templates
VCFD_JOBS_ROOT=/data/vcfd/jobs
VCFD_OPENFOAM_MODE=docker
VCFD_OPENFOAM_DOCKER_IMAGE=${VCFD_OPENFOAM_DOCKER_IMAGE}
VCFD_TRANSPORT=http
VCFD_HOST=0.0.0.0
VCFD_PORT=8000
VCFD_MAX_CONCURRENT_JOBS=${VCFD_MAX_CONCURRENT_JOBS}
VCFD_DEFAULT_JOB_TIMEOUT_SEC=3600
VCFD_AUTH_TOKEN=${VCFD_AUTH_TOKEN}
VCFD_DOMAIN=${VCFD_DOMAIN}
VCFD_ACME_EMAIL=${VCFD_ACME_EMAIL}
VCFD_GIT_URL=${VCFD_GIT_URL}
VCFD_GIT_REF=${VCFD_GIT_REF}
EOF
chmod 600 /etc/vcfd/vcfd.env

# --- clone / update repo ---
if [ -d /opt/vcfd/.git ]; then
  git -C /opt/vcfd fetch --depth 1 origin "${VCFD_GIT_REF}"
  git -C /opt/vcfd checkout -f "${VCFD_GIT_REF}"
  git -C /opt/vcfd reset --hard "origin/${VCFD_GIT_REF}" || git -C /opt/vcfd reset --hard "${VCFD_GIT_REF}"
else
  git clone --depth 1 --branch "${VCFD_GIT_REF}" "${VCFD_GIT_URL}" /opt/vcfd \
    || git clone --depth 1 "${VCFD_GIT_URL}" /opt/vcfd
fi

# --- Caddyfile for domain or plain HTTP ---
CADDY_DIR=/opt/vcfd/deploy/aws/caddy
mkdir -p "${CADDY_DIR}"
if [ -n "${VCFD_DOMAIN}" ]; then
  {
    if [ -n "${VCFD_ACME_EMAIL}" ]; then
      echo "{"
      echo "	email ${VCFD_ACME_EMAIL}"
      echo "}"
      echo
    fi
    cat <<CADDY
${VCFD_DOMAIN} {
	encode gzip
	reverse_proxy vcfd-mcp:8000
	header {
		X-Content-Type-Options nosniff
		Referrer-Policy no-referrer
		-Server
	}
}
CADDY
  } > "${CADDY_DIR}/Caddyfile"
else
  cat > "${CADDY_DIR}/Caddyfile" <<'CADDY'
:80 {
	encode gzip
	reverse_proxy vcfd-mcp:8000
	header {
		X-Content-Type-Options nosniff
		Referrer-Policy no-referrer
		-Server
	}
}
CADDY
fi

# --- firewall ---
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable || true

# --- pull OpenFOAM image (can take several minutes) ---
docker pull "${VCFD_OPENFOAM_DOCKER_IMAGE}" || true

# --- build and start stack ---
cd /opt/vcfd
docker compose -f deploy/aws/docker-compose.prod.yml build
docker compose -f deploy/aws/docker-compose.prod.yml up -d

# --- status marker for launch-ec2.sh polling ---
{
  echo "ready=1"
  echo "time=$(date -Is)"
  echo "domain=${VCFD_DOMAIN}"
  PUBLIC_IP="$(curl -s --max-time 3 http://169.254.169.254/latest/meta-data/public-ipv4 || true)"
  echo "public_ip=${PUBLIC_IP}"
  echo "mcp_path=/mcp"
} > /var/lib/vcfd-ready

# --- lightweight smoke (mock is not used; just ensure container is up) ---
sleep 5
docker compose -f deploy/aws/docker-compose.prod.yml ps || true

echo "==> vCFD bootstrap finished $(date -Is)"
echo "MCP URL (IP mode):  http://${PUBLIC_IP:-<public-ip>}/mcp"
if [ -n "${VCFD_DOMAIN}" ]; then
  echo "MCP URL (domain): https://${VCFD_DOMAIN}/mcp"
fi
echo "Auth: Authorization: Bearer <token from /etc/vcfd/vcfd.env>"
