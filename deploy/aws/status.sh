#!/usr/bin/env bash
# Show status of the latest launched vCFD instance.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STATE="${1:-$ROOT/deploy/aws/out/latest.env}"

if [[ ! -f "$STATE" ]]; then
  echo "No state file at $STATE" >&2
  exit 1
fi
# shellcheck disable=SC1090
source "$STATE"
export AWS_DEFAULT_REGION="${REGION:-us-east-1}"

echo "State: $STATE"
echo "Instance: ${INSTANCE_ID:-?}"
aws ec2 describe-instances --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].{State:State.Name,IP:PublicIpAddress,Type:InstanceType,AZ:Placement.AvailabilityZone}' \
  --output table

if [[ -n "${PUBLIC_IP:-}" && -n "${KEY_FILE:-}" && -f "${KEY_FILE}" ]]; then
  echo
  echo "Remote docker compose:"
  ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=8 -o BatchMode=yes \
    -i "$KEY_FILE" "ubuntu@${PUBLIC_IP}" \
    "sudo docker compose -f /opt/vcfd/deploy/aws/docker-compose.prod.yml ps; \
     test -f /var/lib/vcfd-ready && cat /var/lib/vcfd-ready || echo 'not ready yet'; \
     sudo tail -20 /var/log/vcfd-user-data.log 2>/dev/null || true" || \
    echo "(SSH not ready yet)"
fi

echo
echo "MCP URL: ${MCP_URL_HTTP:-http://${PUBLIC_IP}/mcp}"
echo "Token file: $ROOT/deploy/aws/out/latest.token"
