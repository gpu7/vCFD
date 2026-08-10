#!/usr/bin/env bash
# Install / uninstall a launchd agent that runs watch_paraview_s3.sh on the Mac.
#
#   ./scripts/install_paraview_s3_watch.sh install
#   ./scripts/install_paraview_s3_watch.sh uninstall
#   ./scripts/install_paraview_s3_watch.sh status

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.gpu7.vcfd.paraview-s3-watch"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
WATCH="$ROOT/scripts/watch_paraview_s3.sh"
LOG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/vcfd"
mkdir -p "$LOG_DIR" "$(dirname "$PLIST")"

cmd="${1:-status}"

case "$cmd" in
  install)
    if [[ ! -x "$WATCH" ]]; then
      chmod +x "$WATCH"
    fi
    # Resolve aws + paths for launchd (minimal PATH)
    AWS_BIN=$(command -v aws || true)
    if [[ -z "$AWS_BIN" ]]; then
      echo "aws CLI not found on PATH. Install AWS CLI and re-run." >&2
      exit 1
    fi
    # Prefer repo latest.env bucket if set
    BUCKET_LINE=""
    if [[ -f "$ROOT/deploy/aws/out/latest.env" ]]; then
      B=$(grep '^VCFD_S3_BUCKET=' "$ROOT/deploy/aws/out/latest.env" | cut -d= -f2- || true)
      [[ -n "$B" ]] && BUCKET_LINE="$B"
    fi
    if [[ -z "$BUCKET_LINE" ]]; then
      ACCT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || true)
      [[ -n "$ACCT" && "$ACCT" != "None" ]] && BUCKET_LINE="vcfd-results-${ACCT}"
    fi

    cat >"$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>${WATCH}</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${ROOT}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    <key>HOME</key>
    <string>${HOME}</string>
    <key>AWS_DEFAULT_REGION</key>
    <string>us-east-1</string>
    <key>VCFD_S3_BUCKET</key>
    <string>${BUCKET_LINE}</string>
    <key>VCFD_S3_PREFIX</key>
    <string>paraview</string>
    <key>POLL_SEC</key>
    <string>30</string>
    <key>OPEN_PARAVIEW</key>
    <string>1</string>
    <key>DEST_DIR</key>
    <string>${ROOT}/results</string>
    <key>LOG_FILE</key>
    <string>${LOG_DIR}/s3-watch.log</string>
    <key>STATE_FILE</key>
    <string>${LOG_DIR}/s3-watch-state</string>
  </dict>
  <key>StandardOutPath</key>
  <string>${LOG_DIR}/s3-watch.stdout.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/s3-watch.stderr.log</string>
</dict>
</plist>
EOF
    launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
    launchctl bootstrap "gui/$(id -u)" "$PLIST"
    launchctl enable "gui/$(id -u)/${LABEL}" 2>/dev/null || true
    launchctl kickstart -k "gui/$(id -u)/${LABEL}" 2>/dev/null || true
    echo "Installed and started: $PLIST"
    echo "Bucket: ${BUCKET_LINE:-unset}"
    echo "Logs:   $LOG_DIR/s3-watch.log"
    echo "Stop:   $0 uninstall"
    ;;
  uninstall)
    launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
    rm -f "$PLIST"
    echo "Removed launchd agent $LABEL"
    ;;
  status)
    echo "Plist: $PLIST"
    if [[ -f "$PLIST" ]]; then
      echo "Installed: yes"
    else
      echo "Installed: no"
    fi
    launchctl print "gui/$(id -u)/${LABEL}" 2>/dev/null | head -25 || echo "Not loaded"
    if [[ -f "$LOG_DIR/s3-watch.log" ]]; then
      echo "--- last log lines ---"
      tail -10 "$LOG_DIR/s3-watch.log"
    fi
    ;;
  *)
    echo "Usage: $0 install|uninstall|status" >&2
    exit 1
    ;;
esac
