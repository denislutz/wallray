#!/usr/bin/env bash
# Run once on a fresh Hetzner VPS (Ubuntu 24.04) as root.
# Installs Docker and Coolify, then prints the Coolify UI URL.
set -euo pipefail

echo "==> Updating system packages..."
apt-get update -qq && apt-get upgrade -y -qq

echo "==> Installing Coolify (includes Docker)..."
curl -fsSL https://cdn.coollabs.io/coolify/install.sh | bash

SERVER_IP=$(curl -fsSL ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')
echo ""
echo "✅  Coolify installed."
echo "    Open http://${SERVER_IP}:8000 in your browser to complete setup."
echo "    (Port 8000 must be open in the Hetzner firewall — see DEVOPS_PHASE1.md)"
