#!/usr/bin/env bash
# Watch the vCFD S3 paraview/ prefix; auto-download new zips and open ParaView.
#
# Foreground:
#   ./scripts/watch_paraview_s3.sh
#   ./scripts/watch_paraview_s3.sh --once   # single poll (for testing)
#
# Background (launchd):
#   ./scripts/install_paraview_s3_watch.sh install
#
# Env:
#   VCFD_S3_BUCKET   (default: vcfd-results-<account> or latest.env)
#   VCFD_S3_PREFIX   default paraview
#   VCFD_S3_REGION   default us-east-1
#   DEST_DIR         default <repo>/results
#   POLL_SEC         default 30
#   OPEN_PARAVIEW    default 1 (set 0 to download only)
#   STATE_FILE       default ~/.config/vcfd/s3-watch-state

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ONCE=0
POLL_SEC="${POLL_SEC:-30}"
OPEN_PARAVIEW="${OPEN_PARAVIEW:-1}"
DEST_DIR="${DEST_DIR:-$ROOT/results}"
PREFIX="${VCFD_S3_PREFIX:-paraview}"
AWS_REGION="${VCFD_S3_REGION:-${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}}"
BUCKET="${VCFD_S3_BUCKET:-}"
STATE_FILE="${STATE_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/vcfd/s3-watch-state}"
LOG_FILE="${LOG_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/vcfd/s3-watch.log}"

for arg in "$@"; do
  case "$arg" in
    --once) ONCE=1 ;;
    -h|--help)
      sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
  esac
done

if [[ -f "$ROOT/deploy/aws/out/latest.env" ]]; then
  set +u
  # shellcheck source=/dev/null
  source "$ROOT/deploy/aws/out/latest.env"
  set -u
  BUCKET="${VCFD_S3_BUCKET:-${BUCKET:-}}"
  AWS_REGION="${VCFD_S3_REGION:-${REGION:-$AWS_REGION}}"
fi

if [[ -z "$BUCKET" ]]; then
  ACCT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || true)
  if [[ -n "$ACCT" && "$ACCT" != "None" ]]; then
    BUCKET="vcfd-results-${ACCT}"
  fi
fi

if [[ -z "$BUCKET" ]]; then
  echo "Set VCFD_S3_BUCKET" >&2
  exit 1
fi

export AWS_PAGER=""
export AWS_DEFAULT_REGION="$AWS_REGION"
export AWS_REGION="$AWS_REGION"

mkdir -p "$(dirname "$STATE_FILE")" "$DEST_DIR" "$(dirname "$LOG_FILE")"

log() {
  local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $*"
  echo "$msg" | tee -a "$LOG_FILE"
}

latest_key() {
  aws s3api list-objects-v2 --bucket "$BUCKET" --prefix "${PREFIX}/" \
    --query 'reverse(sort_by(Contents,&LastModified))[0].Key' \
    --output text 2>/dev/null || true
}

object_etag() {
  local key="$1"
  aws s3api head-object --bucket "$BUCKET" --key "$key" \
    --query 'ETag' --output text 2>/dev/null | tr -d '"' || true
}

open_in_paraview() {
  local case_dir="$1"
  local foam="" series=""
  foam=$(find "$case_dir" -maxdepth 1 -name '*.foam' 2>/dev/null | head -1 || true)
  series=$(find "$case_dir/VTK" -maxdepth 1 -name '*.vtm.series' 2>/dev/null | head -1 || true)
  local target="${series:-$foam}"
  if [[ -z "$target" || ! -e "$target" ]]; then
    log "No .foam or .vtm.series under $case_dir — open folder in Finder"
    open "$case_dir" 2>/dev/null || true
    return
  fi
  log "Opening ParaView: $target"
  if open -a ParaView "$target" 2>/dev/null; then
    return
  fi
  # Fallback common app names
  if open -a "paraview" "$target" 2>/dev/null; then
    return
  fi
  log "ParaView app not found; opening file with default handler"
  open "$target" 2>/dev/null || open "$case_dir" 2>/dev/null || true
}

process_key() {
  local key="$1"
  local etag="$2"
  local base
  base=$(basename "$key")
  local out="$DEST_DIR/$base"
  log "New export: s3://${BUCKET}/${key}"
  aws s3 cp "s3://${BUCKET}/${key}" "$out"
  echo "${key}|${etag}" >"$STATE_FILE"

  if [[ "$out" == *.zip ]] && unzip -t "$out" >/dev/null 2>&1; then
    local unpack="${DEST_DIR}/$(basename "$out" .zip)_export"
    rm -rf "$unpack"
    mkdir -p "$unpack"
    unzip -q -o "$out" -d "$unpack"
    local case_dir
    case_dir=$(find "$unpack" -maxdepth 2 -type d -name system 2>/dev/null | head -1 | xargs dirname 2>/dev/null || true)
    if [[ -n "${case_dir:-}" && -d "$case_dir" ]]; then
      touch "${case_dir}/$(basename "$case_dir").foam"
      log "Unpacked: $case_dir"
      if [[ "$OPEN_PARAVIEW" == "1" ]]; then
        open_in_paraview "$case_dir"
      fi
    else
      log "Unpacked to $unpack (no case root found)"
      [[ "$OPEN_PARAVIEW" == "1" ]] && open "$unpack" 2>/dev/null || true
    fi
  else
    log "Saved (not a zip or invalid): $out"
  fi
}

poll_once() {
  local key etag prev_key prev_etag
  key=$(latest_key)
  if [[ -z "$key" || "$key" == "None" ]]; then
    log "No objects under s3://${BUCKET}/${PREFIX}/"
    return 0
  fi
  etag=$(object_etag "$key")
  prev_key=""
  prev_etag=""
  if [[ -f "$STATE_FILE" ]]; then
    IFS='|' read -r prev_key prev_etag <"$STATE_FILE" || true
  fi
  if [[ "$key" == "$prev_key" && "$etag" == "$prev_etag" ]]; then
    return 0
  fi
  process_key "$key" "$etag"
}

log "Watching s3://${BUCKET}/${PREFIX}/ every ${POLL_SEC}s → $DEST_DIR (open_paraview=$OPEN_PARAVIEW)"

if [[ "$ONCE" -eq 1 ]]; then
  poll_once
  exit 0
fi

while true; do
  poll_once || log "Poll error (will retry)"
  sleep "$POLL_SEC"
done
