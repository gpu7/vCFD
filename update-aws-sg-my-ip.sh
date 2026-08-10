#!/usr/bin/env bash
# update-aws-sg-my-ip.sh — vCFD
#
# Detect this machine's public IPv4 and update the vCFD EC2 security group so
# admin SSH allows that IP. Order: authorize NEW first, then revoke others
# (avoids locking yourself out).
#
# By default only port 22 is managed. Ports 80/443 stay world-open for public
# MCP / Caddy unless you explicitly set PORTS to include them.
#
# Usage (on your Mac when home IP changes, from the vCFD repo root):
#   ./update-aws-sg-my-ip.sh
#   ./update-aws-sg-my-ip.sh --dry-run
#   MY_IP=1.2.3.4 ./update-aws-sg-my-ip.sh
#   source deploy/aws/out/latest.env && SG_ID=$SG_ID ./update-aws-sg-my-ip.sh
#
# Env:
#   AWS_REGION  default: us-east-1 (or REGION / AWS_DEFAULT_REGION)
#   SG_ID       default: from deploy/aws/out/latest.env, else sg-052d8e33c3c5145a9
#   PORTS       default: 22  (SSH only)
#   MY_IP       default: auto-detect via checkip.amazonaws.com
#
# Requires: aws CLI, credentials with ec2:Authorize/Revoke/Describe on the SG,
#           python3, curl

set -euo pipefail

# Script lives at repo root
ROOT="$(cd "$(dirname "$0")" && pwd)"
STATE_ENV="$ROOT/deploy/aws/out/latest.env"

DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    -h|--help)
      sed -n '2,28p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      exit 1
      ;;
  esac
done

# Load deploy state if present (non-fatal)
if [[ -f "$STATE_ENV" ]]; then
  # shellcheck disable=SC1090
  set +u
  # shellcheck source=/dev/null
  source "$STATE_ENV"
  set -u
fi

AWS_REGION=${AWS_REGION:-${REGION:-${AWS_DEFAULT_REGION:-us-east-1}}}
SG_ID=${SG_ID:-sg-052d8e33c3c5145a9}
# Admin SSH only — do not put 80/443 here unless you intend to lock public MCP.
PORTS_STR=${PORTS:-"22"}

export AWS_PAGER=""
export AWS_CLI_AUTO_PROMPT=off
export AWS_DEFAULT_REGION="$AWS_REGION"
export AWS_REGION="$AWS_REGION"

for cmd in aws python3 curl; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "Missing required command: $cmd" >&2
    exit 1
  }
done

detect_ip() {
  local ip
  ip=$(curl -4 -sS --max-time 10 https://checkip.amazonaws.com | tr -d '[:space:]' || true)
  if [[ ! "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    ip=$(curl -4 -sS --max-time 10 https://ifconfig.me | tr -d '[:space:]' || true)
  fi
  if [[ ! "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "Could not detect public IPv4. Set MY_IP=x.x.x.x" >&2
    exit 1
  fi
  printf '%s\n' "$ip"
}

MY_IP=${MY_IP:-$(detect_ip)}
MY_CIDR="${MY_IP}/32"

echo "=== update-aws-sg-my-ip (vCFD) ==="
echo "Region:  $AWS_REGION"
echo "SG:      $SG_ID"
echo "New IP:  $MY_CIDR"
echo "Ports:   $PORTS_STR"
echo "Dry-run: $DRY_RUN"
echo ""

if echo " $PORTS_STR " | grep -Eq ' (80|443) '; then
  echo "WARNING: PORTS includes 80 and/or 443." >&2
  echo "  This will revoke world-open 0.0.0.0/0 on those ports and limit them to your IP." >&2
  echo "  That breaks public MCP unless you only use a Cloudflare tunnel." >&2
  echo ""
fi

WORKDIR=$(mktemp -d)
trap 'rm -rf "$WORKDIR"' EXIT
SG_JSON="$WORKDIR/sg.json"
PLAN_JSON="$WORKDIR/plan.json"

aws ec2 describe-security-groups \
  --region "$AWS_REGION" \
  --group-ids "$SG_ID" \
  --output json >"$SG_JSON"

MY_CIDR="$MY_CIDR" PORTS_STR="$PORTS_STR" \
  python3 - "$SG_JSON" "$PLAN_JSON" <<'PY'
import json, os, sys
from collections import defaultdict

sg_path, plan_path = sys.argv[1], sys.argv[2]
ports = {int(p) for p in os.environ["PORTS_STR"].split()}
my_cidr = os.environ["MY_CIDR"]

with open(sg_path) as f:
    data = json.load(f)

existing = defaultdict(set)
for g in data.get("SecurityGroups", []):
    for perm in g.get("IpPermissions", []):
        if perm.get("IpProtocol") != "tcp":
            continue
        fp, tp = perm.get("FromPort"), perm.get("ToPort")
        if fp is None:
            continue
        for r in perm.get("IpRanges", []):
            cidr = r.get("CidrIp")
            if not cidr:
                continue
            for port in range(int(fp), int(tp) + 1):
                if port in ports:
                    existing[port].add(cidr)

to_add, to_revoke = [], []
for port in sorted(ports):
    cidrs = existing.get(port, set())
    if my_cidr not in cidrs:
        to_add.append(port)
    for c in sorted(cidrs):
        if c == my_cidr:
            continue
        to_revoke.append({"port": port, "cidr": c})

with open(plan_path, "w") as f:
    json.dump({"add": to_add, "revoke": to_revoke}, f, indent=2)
PY

python3 - "$PLAN_JSON" "$MY_CIDR" <<'PY'
import json, sys
plan = json.load(open(sys.argv[1]))
my = sys.argv[2]
print("Plan:")
if not plan["add"] and not plan["revoke"]:
    print("  No changes needed.")
else:
    for p in plan["add"]:
        print(f"  + authorize tcp/{p} from {my}")
    for r in plan["revoke"]:
        print(f"  - revoke   tcp/{r['port']} from {r['cidr']}")
PY

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo ""
  echo "Dry-run only. Re-run without --dry-run to apply."
  exit 0
fi

desc_for_port() {
  case "$1" in
    22) echo "SSH-admin" ;;
    80) echo "HTTP admin/Mac" ;;
    443) echo "HTTPS admin/Mac" ;;
    8000) echo "vCFD MCP direct" ;;
    *) echo "vCFD admin/Mac" ;;
  esac
}

# 1) Authorize new IP first
while IFS= read -r port; do
  [[ -z "$port" ]] && continue
  echo "Authorizing tcp/$port $MY_CIDR ..."
  DESC=$(desc_for_port "$port")
  if ! aws ec2 authorize-security-group-ingress \
    --region "$AWS_REGION" \
    --group-id "$SG_ID" \
    --ip-permissions "[{\"IpProtocol\":\"tcp\",\"FromPort\":${port},\"ToPort\":${port},\"IpRanges\":[{\"CidrIp\":\"${MY_CIDR}\",\"Description\":\"${DESC}\"}]}]"; then
    echo "  (authorize failed or already exists — continuing)"
  fi
done < <(python3 -c "import json;print('\n'.join(str(p) for p in json.load(open('$PLAN_JSON'))['add']))")

# 2) Revoke old CIDRs
while IFS= read -r line; do
  [[ -z "$line" ]] && continue
  port=${line%% *}
  cidr=${line#* }
  echo "Revoking tcp/$port $cidr ..."
  if ! aws ec2 revoke-security-group-ingress \
    --region "$AWS_REGION" \
    --group-id "$SG_ID" \
    --protocol tcp \
    --port "$port" \
    --cidr "$cidr"; then
    echo "  (revoke failed — check manually)"
  fi
done < <(python3 -c "import json;print('\n'.join(f\"{r['port']} {r['cidr']}\" for r in json.load(open('$PLAN_JSON'))['revoke']))")

STATE_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/vcfd"
mkdir -p "$STATE_DIR"
echo "$MY_IP" >"$STATE_DIR/last-sg-ip"

# Also refresh SSH_CIDR in latest.env if present
if [[ -f "$STATE_ENV" ]]; then
  if grep -q '^SSH_CIDR=' "$STATE_ENV" 2>/dev/null; then
    # portable in-place update
    tmp=$(mktemp)
    sed "s|^SSH_CIDR=.*|SSH_CIDR=${MY_CIDR}|" "$STATE_ENV" >"$tmp"
    mv "$tmp" "$STATE_ENV"
  else
    echo "SSH_CIDR=${MY_CIDR}" >>"$STATE_ENV"
  fi
fi

echo ""
echo "Done. Recorded IP in $STATE_DIR/last-sg-ip"
echo ""
aws ec2 describe-security-groups --region "$AWS_REGION" --group-ids "$SG_ID" \
  --query 'SecurityGroups[].IpPermissions[].{From:FromPort,To:ToPort,Cidrs:IpRanges[].CidrIp}' \
  --output table
