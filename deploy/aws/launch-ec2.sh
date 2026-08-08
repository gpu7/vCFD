#!/usr/bin/env bash
# Launch an Ubuntu EC2 instance for vCFD and print connection details.
#
# Prerequisites:
#   - aws CLI configured (aws sts get-caller-identity works)
#   - permissions: ec2:*, optionally iam for instance profile later
#
# Usage:
#   ./deploy/aws/launch-ec2.sh
#   ./deploy/aws/launch-ec2.sh --instance-type c7g.xlarge --region us-east-1
#   ./deploy/aws/launch-ec2.sh --domain cfd.example.com --email you@example.com
#   ./deploy/aws/launch-ec2.sh --dry-run
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

# Defaults
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
INSTANCE_TYPE="c7g.xlarge"   # Graviton; use c6i.xlarge for x86
KEY_NAME="vcfd-ec2"
SG_NAME="vcfd-mcp-sg"
NAME_TAG="vcfd-mcp"
VOLUME_SIZE_GB=80
GIT_URL="https://github.com/gpu7/vCFD.git"
GIT_REF="master"
OF_IMAGE="opencfd/openfoam-default:2506"
MAX_JOBS=2
DOMAIN=""
ACME_EMAIL=""
DRY_RUN=0
AUTH_TOKEN=""
MY_IP_CIDR=""
WAIT_READY=1

usage() {
  sed -n '1,30p' "$0" | sed 's/^# \{0,1\}//'
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --region) REGION="$2"; shift 2 ;;
    --instance-type) INSTANCE_TYPE="$2"; shift 2 ;;
    --key-name) KEY_NAME="$2"; shift 2 ;;
    --sg-name) SG_NAME="$2"; shift 2 ;;
    --name) NAME_TAG="$2"; shift 2 ;;
    --volume-gb) VOLUME_SIZE_GB="$2"; shift 2 ;;
    --git-url) GIT_URL="$2"; shift 2 ;;
    --git-ref) GIT_REF="$2"; shift 2 ;;
    --of-image) OF_IMAGE="$2"; shift 2 ;;
    --domain) DOMAIN="$2"; shift 2 ;;
    --email) ACME_EMAIL="$2"; shift 2 ;;
    --auth-token) AUTH_TOKEN="$2"; shift 2 ;;
    --my-ip) MY_IP_CIDR="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --no-wait) WAIT_READY=0; shift ;;
    -h|--help) usage ;;
    *) echo "Unknown arg: $1"; usage ;;
  esac
done

export AWS_DEFAULT_REGION="$REGION"
export AWS_REGION="$REGION"

echo "==> Account"
aws sts get-caller-identity

if [[ -z "$AUTH_TOKEN" ]]; then
  AUTH_TOKEN="$(openssl rand -hex 32)"
  echo "==> Generated VCFD_AUTH_TOKEN (save this):"
  echo "    $AUTH_TOKEN"
fi

# Detect arch from instance type family for AMI selection
ARCH="arm64"
case "$INSTANCE_TYPE" in
  c6i.*|c5.*|m6i.*|m5.*|t3.*|t2.*|c6a.*|m6a.*) ARCH="x86_64" ;;
  c7g.*|c6g.*|m7g.*|m6g.*|t4g.*) ARCH="arm64" ;;
esac
echo "==> Instance type $INSTANCE_TYPE (AMI arch $ARCH) in $REGION"

# Latest Ubuntu 24.04 AMI from Canonical
AMI_ID="$(aws ssm get-parameters \
  --names "/aws/service/canonical/ubuntu/server/24.04/stable/current/${ARCH}/hvm/ebs-gp3/ami-id" \
  --query 'Parameters[0].Value' --output text 2>/dev/null || true)"
if [[ -z "$AMI_ID" || "$AMI_ID" == "None" ]]; then
  # Fallback: describe images
  AMI_ID="$(aws ec2 describe-images \
    --owners 099720109477 \
    --filters \
      "Name=name,Values=ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-${ARCH}-server-*" \
      "Name=state,Values=available" \
    --query 'sort_by(Images,&CreationDate)[-1].ImageId' \
    --output text)"
fi
echo "==> AMI $AMI_ID"

# Default VPC + subnet
VPC_ID="$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true \
  --query 'Vpcs[0].VpcId' --output text)"
if [[ -z "$VPC_ID" || "$VPC_ID" == "None" ]]; then
  echo "ERROR: No default VPC in $REGION. Create a VPC or set one up first." >&2
  exit 1
fi
SUBNET_ID="$(aws ec2 describe-subnets \
  --filters "Name=vpc-id,Values=$VPC_ID" "Name=default-for-az,Values=true" \
  --query 'Subnets[0].SubnetId' --output text)"
if [[ -z "$SUBNET_ID" || "$SUBNET_ID" == "None" ]]; then
  SUBNET_ID="$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" \
    --query 'Subnets[0].SubnetId' --output text)"
fi
echo "==> VPC $VPC_ID subnet $SUBNET_ID"

# SSH source CIDR
if [[ -z "$MY_IP_CIDR" ]]; then
  MY_IP="$(curl -fsS --max-time 5 https://checkip.amazonaws.com | tr -d '[:space:]' || true)"
  if [[ -n "$MY_IP" ]]; then
    MY_IP_CIDR="${MY_IP}/32"
  else
    MY_IP_CIDR="0.0.0.0/0"
    echo "WARN: could not detect public IP; SSH open to world (tighten later)."
  fi
fi
echo "==> SSH from $MY_IP_CIDR"

# Render user-data early (for dry-run inspection)
UD_SRC="$ROOT/deploy/aws/user-data.sh"
UD_RENDERED="$(mktemp)"
sed \
  -e "s|__VCFD_GIT_URL__|${GIT_URL}|g" \
  -e "s|__VCFD_GIT_REF__|${GIT_REF}|g" \
  -e "s|__VCFD_AUTH_TOKEN__|${AUTH_TOKEN}|g" \
  -e "s|__VCFD_DOMAIN__|${DOMAIN}|g" \
  -e "s|__VCFD_ACME_EMAIL__|${ACME_EMAIL}|g" \
  -e "s|__VCFD_OPENFOAM_DOCKER_IMAGE__|${OF_IMAGE}|g" \
  -e "s|__VCFD_MAX_CONCURRENT_JOBS__|${MAX_JOBS}|g" \
  "$UD_SRC" > "$UD_RENDERED"

if ! head -1 "$UD_RENDERED" | grep -q '^#!'; then
  echo "ERROR: user-data missing shebang" >&2
  exit 1
fi

OUT_DIR="$ROOT/deploy/aws/out"
mkdir -p "$OUT_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
STATE_FILE="$OUT_DIR/launch-${STAMP}.env"
cp "$UD_RENDERED" "$OUT_DIR/user-data-${STAMP}.sh"

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "==> DRY RUN — would launch (no key/SG/instance created):"
  echo "    AMI=$AMI_ID type=$INSTANCE_TYPE region=$REGION subnet=$SUBNET_ID"
  echo "    SSH CIDR=$MY_IP_CIDR key=$KEY_NAME sg=$SG_NAME"
  echo "    user-data: $OUT_DIR/user-data-${STAMP}.sh"
  echo "    auth token: $AUTH_TOKEN"
  rm -f "$UD_RENDERED"
  exit 0
fi

# --- Mutating resources below (not dry-run) ---

# Key pair
KEY_FILE="$HOME/.ssh/${KEY_NAME}.pem"
if ! aws ec2 describe-key-pairs --key-names "$KEY_NAME" >/dev/null 2>&1; then
  mkdir -p "$HOME/.ssh"
  echo "==> Creating key pair $KEY_NAME -> $KEY_FILE"
  aws ec2 create-key-pair --key-name "$KEY_NAME" --query 'KeyMaterial' --output text > "$KEY_FILE"
  chmod 600 "$KEY_FILE"
else
  echo "==> Using existing key pair $KEY_NAME (private key expected at $KEY_FILE if you created it here)"
fi

# Security group
SG_ID="$(aws ec2 describe-security-groups \
  --filters "Name=group-name,Values=$SG_NAME" "Name=vpc-id,Values=$VPC_ID" \
  --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || true)"
if [[ -z "$SG_ID" || "$SG_ID" == "None" ]]; then
  echo "==> Creating security group $SG_NAME"
  SG_ID="$(aws ec2 create-security-group \
    --group-name "$SG_NAME" \
    --description "vCFD MCP (SSH + HTTP/HTTPS)" \
    --vpc-id "$VPC_ID" \
    --query 'GroupId' --output text)"
  aws ec2 create-tags --resources "$SG_ID" --tags "Key=Name,Value=$SG_NAME" "Key=Project,Value=vCFD"
  aws ec2 authorize-security-group-ingress --group-id "$SG_ID" \
    --ip-permissions \
    "IpProtocol=tcp,FromPort=22,ToPort=22,IpRanges=[{CidrIp=$MY_IP_CIDR,Description=SSH}]" \
    "IpProtocol=tcp,FromPort=80,ToPort=80,IpRanges=[{CidrIp=0.0.0.0/0,Description=HTTP}]" \
    "IpProtocol=tcp,FromPort=443,ToPort=443,IpRanges=[{CidrIp=0.0.0.0/0,Description=HTTPS}]" \
    >/dev/null
else
  echo "==> Reusing security group $SG_ID"
fi

echo "==> Launching instance..."
INSTANCE_ID="$(aws ec2 run-instances \
  --image-id "$AMI_ID" \
  --instance-type "$INSTANCE_TYPE" \
  --key-name "$KEY_NAME" \
  --security-group-ids "$SG_ID" \
  --subnet-id "$SUBNET_ID" \
  --associate-public-ip-address \
  --block-device-mappings "[{\"DeviceName\":\"/dev/sda1\",\"Ebs\":{\"VolumeSize\":${VOLUME_SIZE_GB},\"VolumeType\":\"gp3\",\"DeleteOnTermination\":true}}]" \
  --user-data "file://${UD_RENDERED}" \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=${NAME_TAG}},{Key=Project,Value=vCFD}]" \
  --query 'Instances[0].InstanceId' \
  --output text)"

rm -f "$UD_RENDERED"
echo "==> Instance $INSTANCE_ID launching..."

aws ec2 wait instance-running --instance-ids "$INSTANCE_ID"
PUBLIC_IP="$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)"
PUBLIC_DNS="$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].PublicDnsName' --output text)"

{
  echo "INSTANCE_ID=$INSTANCE_ID"
  echo "REGION=$REGION"
  echo "PUBLIC_IP=$PUBLIC_IP"
  echo "PUBLIC_DNS=$PUBLIC_DNS"
  echo "KEY_NAME=$KEY_NAME"
  echo "KEY_FILE=$KEY_FILE"
  echo "SG_ID=$SG_ID"
  echo "VCFD_AUTH_TOKEN=$AUTH_TOKEN"
  echo "VCFD_DOMAIN=$DOMAIN"
  echo "MCP_URL_HTTP=http://${PUBLIC_IP}/mcp"
  if [[ -n "$DOMAIN" ]]; then
    echo "MCP_URL_HTTPS=https://${DOMAIN}/mcp"
  fi
  echo "LAUNCHED_AT=$(date -Is)"
} | tee "$STATE_FILE"

# Also write latest pointer
ln -sfn "$(basename "$STATE_FILE")" "$OUT_DIR/latest.env"
# Store secrets separately (gitignored)
echo "$AUTH_TOKEN" > "$OUT_DIR/latest.token"
chmod 600 "$OUT_DIR/latest.token" "$STATE_FILE" 2>/dev/null || true

echo
echo "=============================================="
echo " Instance:  $INSTANCE_ID"
echo " Public IP: $PUBLIC_IP"
echo " SSH:       ssh -i $KEY_FILE ubuntu@$PUBLIC_IP"
echo " MCP (HTTP while bootstrapping): http://$PUBLIC_IP/mcp"
if [[ -n "$DOMAIN" ]]; then
  echo " Point DNS A record for $DOMAIN -> $PUBLIC_IP"
  echo " MCP (HTTPS after cert): https://$DOMAIN/mcp"
fi
echo " Auth header: Authorization: Bearer $AUTH_TOKEN"
echo " State file:  $STATE_FILE"
echo " Bootstrap log (after SSH): sudo tail -f /var/log/vcfd-user-data.log"
echo "=============================================="

if [[ "$WAIT_READY" -eq 1 ]]; then
  echo "==> Waiting for cloud-init / docker stack (up to ~20 min)..."
  READY=0
  for i in $(seq 1 80); do
    if ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=5 -o BatchMode=yes \
      -i "$KEY_FILE" "ubuntu@${PUBLIC_IP}" \
      "test -f /var/lib/vcfd-ready && grep -q ready=1 /var/lib/vcfd-ready" 2>/dev/null; then
      READY=1
      break
    fi
    # cloud-init may still be installing; also try HTTP
    if curl -fsS --max-time 3 "http://${PUBLIC_IP}/mcp" >/dev/null 2>&1; then
      READY=1
      break
    fi
    printf "."
    sleep 15
  done
  echo
  if [[ "$READY" -eq 1 ]]; then
    echo "==> Host reports ready (or /mcp is responding)."
  else
    echo "==> Timed out waiting. SSH in and check:"
    echo "    sudo tail -100 /var/log/vcfd-user-data.log"
    echo "    cd /opt/vcfd && sudo docker compose -f deploy/aws/docker-compose.prod.yml ps"
  fi
fi

echo
echo "Grok Voice remote MCP config snippet:"
cat <<EOF
{
  "type": "mcp",
  "server_url": "http://${PUBLIC_IP}/mcp",
  "server_label": "vcfd",
  "authorization": "Bearer ${AUTH_TOKEN}"
}
EOF
if [[ -n "$DOMAIN" ]]; then
  echo "(Prefer https://${DOMAIN}/mcp once DNS + cert are ready.)"
fi
