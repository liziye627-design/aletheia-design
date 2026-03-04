#!/bin/bash
set -euo pipefail

echo "[dns] preparing WSL DNS fix..."

if [ "$(id -u)" -ne 0 ]; then
  echo "[dns] this script needs root. please run:"
  echo "  sudo bash scripts/fix_wsl_dns.sh"
  exit 1
fi

cat >/etc/wsl.conf <<'EOF'
[network]
generateResolvConf = false
EOF

rm -f /etc/resolv.conf
cat >/etc/resolv.conf <<'EOF'
nameserver 1.1.1.1
nameserver 8.8.8.8
options timeout:2 attempts:2
EOF
chmod 644 /etc/resolv.conf

echo "[dns] done."
echo "[dns] now restart WSL from Windows PowerShell:"
echo "  wsl --shutdown"
echo "then reopen your WSL terminal."

