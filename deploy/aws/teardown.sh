#!/usr/bin/env bash
# Terminate the latest (or specified) vCFD EC2 instance.
# Does not delete the key pair or security group by default.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT_DIR="$ROOT/deploy/aws/out"
INSTANCE_ID=""
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
DELETE_SG=0
DELETE_KEY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --instance-id) INSTANCE_ID="$2"; shift 2 ;;
    --region) REGION="$2"; shift 2 ;;
    --delete-sg) DELETE_SG=1; shift ;;
    --delete-key) DELETE_KEY=1; shift ;;
    -h|--help)
      echo "Usage: $0 [--instance-id i-...] [--region us-east-1] [--delete-sg] [--delete-key]"
      exit 0
      ;;
    *) echo "Unknown: $1"; exit 1 ;;
  esac
done

export AWS_DEFAULT_REGION="$REGION"
export AWS_REGION="$REGION"

if [[ -z "$INSTANCE_ID" ]]; then
  if [[ -f "$OUT_DIR/latest.env" ]]; then
    # latest.env may be a symlink to launch-*.env
    # shellcheck disable=SC1090
    source "$OUT_DIR/latest.env"
    INSTANCE_ID="${INSTANCE_ID:-}"
    REGION="${REGION:-$REGION}"
  fi
fi

if [[ -z "$INSTANCE_ID" ]]; then
  echo "No INSTANCE_ID. Pass --instance-id or run launch-ec2.sh first." >&2
  exit 1
fi

echo "==> Terminating $INSTANCE_ID in $REGION"
aws ec2 terminate-instances --instance-ids "$INSTANCE_ID"
aws ec2 wait instance-terminated --instance-ids "$INSTANCE_ID"
echo "==> Terminated."

if [[ "$DELETE_SG" -eq 1 && -n "${SG_ID:-}" ]]; then
  echo "==> Deleting security group $SG_ID"
  aws ec2 delete-security-group --group-id "$SG_ID" || true
fi

if [[ "$DELETE_KEY" -eq 1 && -n "${KEY_NAME:-}" ]]; then
  echo "==> Deleting key pair $KEY_NAME"
  aws ec2 delete-key-pair --key-name "$KEY_NAME" || true
  rm -f "${HOME}/.ssh/${KEY_NAME}.pem" || true
fi

echo "Done."
