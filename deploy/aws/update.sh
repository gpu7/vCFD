#!/usr/bin/env bash
# Pull latest vCFD on the EC2 host and rebuild containers.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STATE="${1:-$ROOT/deploy/aws/out/latest.env}"
# shellcheck disable=SC1090
source "$STATE"

if [[ -z "${PUBLIC_IP:-}" || -z "${KEY_FILE:-}" ]]; then
  echo "Missing PUBLIC_IP/KEY_FILE in $STATE" >&2
  exit 1
fi

ssh -o StrictHostKeyChecking=accept-new -i "$KEY_FILE" "ubuntu@${PUBLIC_IP}" bash -s <<'REMOTE'
set -euo pipefail
cd /opt/vcfd
sudo git fetch --depth 1 origin master
sudo git reset --hard origin/master
sudo docker compose -f deploy/aws/docker-compose.prod.yml build
sudo docker compose -f deploy/aws/docker-compose.prod.yml up -d
sudo docker compose -f deploy/aws/docker-compose.prod.yml ps
REMOTE

echo "Updated ${PUBLIC_IP}"
