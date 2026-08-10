#!/usr/bin/env bash
# Download the latest (or named) ParaView export from the vCFD S3 bucket to the Mac.
#
# Usage:
#   ./scripts/fetch_paraview_from_s3.sh
#   ./scripts/fetch_paraview_from_s3.sh --case voice_pipe
#   ./scripts/fetch_paraview_from_s3.sh --uri s3://bucket/paraview/voice_pipe/....zip
#   VCFD_S3_BUCKET=my-bucket ./scripts/fetch_paraview_from_s3.sh --latest
#
# Env:
#   VCFD_S3_BUCKET   default: vcfd-results-<account-id> or from deploy/aws/out/latest.env
#   VCFD_S3_PREFIX   default: paraview
#   VCFD_S3_REGION   default: us-east-1
#   DEST_DIR         default: ./results

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

CASE=""
URI=""
LATEST=1
DEST_DIR="${DEST_DIR:-$ROOT/results}"
AWS_REGION="${VCFD_S3_REGION:-${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}}"
PREFIX="${VCFD_S3_PREFIX:-paraview}"
BUCKET="${VCFD_S3_BUCKET:-}"

if [[ -f "$ROOT/deploy/aws/out/latest.env" ]]; then
  # shellcheck disable=SC1091
  set +u
  source "$ROOT/deploy/aws/out/latest.env"
  set -u
  BUCKET="${VCFD_S3_BUCKET:-${BUCKET:-}}"
  AWS_REGION="${VCFD_S3_REGION:-${REGION:-$AWS_REGION}}"
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --case) CASE="$2"; LATEST=0; shift 2 ;;
    --uri) URI="$2"; shift 2 ;;
    --latest) LATEST=1; shift ;;
    --bucket) BUCKET="$2"; shift 2 ;;
    --dest) DEST_DIR="$2"; shift 2 ;;
    -h|--help)
      sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) echo "Unknown: $1" >&2; exit 1 ;;
  esac
done

export AWS_PAGER=""
export AWS_DEFAULT_REGION="$AWS_REGION"

if [[ -z "$BUCKET" && -z "$URI" ]]; then
  # Try default naming convention
  ACCT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || true)
  if [[ -n "$ACCT" && "$ACCT" != "None" ]]; then
    BUCKET="vcfd-results-${ACCT}"
  fi
fi

mkdir -p "$DEST_DIR"

if [[ -n "$URI" ]]; then
  KEY="${URI#s3://}"
  KEY="${KEY#*/}"  # drop bucket/
  B="${URI#s3://}"
  B="${B%%/*}"
  OUT="$DEST_DIR/$(basename "$KEY")"
  echo "Downloading $URI -> $OUT"
  aws s3 cp "s3://${B}/${KEY}" "$OUT"
else
  if [[ -z "$BUCKET" ]]; then
    echo "Set VCFD_S3_BUCKET or pass --bucket / --uri" >&2
    exit 1
  fi
  if [[ -n "$CASE" ]]; then
    PREFIX_PATH="${PREFIX}/${CASE}/"
  else
    PREFIX_PATH="${PREFIX}/"
  fi
  echo "Listing s3://${BUCKET}/${PREFIX_PATH} ..."
  # Newest object under prefix
  OBJ=$(aws s3api list-objects-v2 --bucket "$BUCKET" --prefix "$PREFIX_PATH" \
    --query 'reverse(sort_by(Contents,&LastModified))[0].Key' --output text 2>/dev/null || true)
  if [[ -z "$OBJ" || "$OBJ" == "None" ]]; then
    echo "No objects found under s3://${BUCKET}/${PREFIX_PATH}" >&2
    exit 1
  fi
  OUT="$DEST_DIR/$(basename "$OBJ")"
  echo "Downloading s3://${BUCKET}/${OBJ} -> $OUT"
  aws s3 cp "s3://${BUCKET}/${OBJ}" "$OUT"
fi

# Unzip if zip
if [[ "$OUT" == *.zip ]]; then
  UNPACK="${DEST_DIR}/$(basename "$OUT" .zip)_export"
  rm -rf "$UNPACK"
  mkdir -p "$UNPACK"
  unzip -q -o "$OUT" -d "$UNPACK"
  # Create .foam helper if case folder present
  CASE_DIR=$(find "$UNPACK" -maxdepth 2 -type d -name 'system' 2>/dev/null | head -1 | xargs dirname 2>/dev/null || true)
  if [[ -n "${CASE_DIR:-}" && -d "$CASE_DIR" ]]; then
    touch "${CASE_DIR}/$(basename "$CASE_DIR").foam"
    echo "Unpacked case: $CASE_DIR"
    echo "ParaView: open ${CASE_DIR}/$(basename "$CASE_DIR").foam"
    echo "     or: ${CASE_DIR}/VTK/*.vtm.series"
  else
    echo "Unpacked to: $UNPACK"
  fi
fi

echo "Done: $OUT"
