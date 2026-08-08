#!/usr/bin/env bash
# OS-level hardening for Ubuntu 24.04 vCFD hosts. Run once after first boot:
#   sudo bash /opt/vcfd/deploy/aws/harden-os.sh
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash $0" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive

echo "==> Packages"
apt-get update -y
apt-get install -y unattended-upgrades fail2ban ufw curl ca-certificates

echo "==> Unattended security upgrades"
cat >/etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF
# Enable security updates only (defaults usually OK)
dpkg-reconfigure -f noninteractive unattended-upgrades || true

echo "==> SSH harden (sshd)"
SSHD=/etc/ssh/sshd_config
cp -a "$SSHD" "${SSHD}.bak.$(date +%s)"
# Drop-in for clarity (Ubuntu uses sshd_config.d)
mkdir -p /etc/ssh/sshd_config.d
cat >/etc/ssh/sshd_config.d/99-vcfd-hardening.conf <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
X11Forwarding no
AllowTcpForwarding no
ClientAliveInterval 300
ClientAliveCountMax 2
MaxAuthTries 3
LoginGraceTime 30
EOF
systemctl reload ssh || systemctl reload sshd || true

echo "==> UFW"
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
ufw status verbose

echo "==> fail2ban (sshd)"
systemctl enable --now fail2ban
# minimal jail
cat >/etc/fail2ban/jail.d/sshd.local <<'EOF'
[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 5
bantime = 1h
EOF
systemctl restart fail2ban

echo "==> Kernel / network sysctl"
cat >/etc/sysctl.d/99-vcfd-hardening.conf <<'EOF'
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.default.rp_filter = 1
net.ipv4.icmp_echo_ignore_broadcasts = 1
net.ipv4.conf.all.accept_source_route = 0
net.ipv4.conf.default.accept_source_route = 0
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.default.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv4.tcp_syncookies = 1
net.ipv6.conf.all.accept_redirects = 0
net.ipv6.conf.default.accept_redirects = 0
EOF
sysctl --system >/dev/null || true

echo "==> Permissions on secrets"
if [[ -f /etc/vcfd/vcfd.env ]]; then
  chown root:root /etc/vcfd/vcfd.env
  chmod 600 /etc/vcfd/vcfd.env
fi
chmod 700 /etc/vcfd 2>/dev/null || true

echo "==> Docker: no TCP daemon socket (unix only)"
# Ensure we don't expose docker remotely
if [[ -f /etc/docker/daemon.json ]]; then
  echo "Existing /etc/docker/daemon.json — review manually"
else
  mkdir -p /etc/docker
  cat >/etc/docker/daemon.json <<'EOF'
{
  "icc": false,
  "live-restore": true,
  "userland-proxy": false,
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
EOF
  systemctl restart docker || true
fi

echo "==> OS hardening complete"
echo "Note: IMDSv2 hop-limit is set at AWS instance metadata options (host)."
echo "Restart SSH sessions if sshd was reloaded."
