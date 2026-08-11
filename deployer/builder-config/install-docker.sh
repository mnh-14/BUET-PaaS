#!/usr/bin/env bash
set -euo pipefail

echo "=== 1. Removing older/conflicting Docker packages ==="
for pkg in docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc; do
  sudo apt-get remove -y "$pkg" || true
done

echo "=== 2. Setting up Docker APT repository ==="
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

echo "=== 3. Installing Docker Engine & Compose ==="
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

echo "=== 4. Enabling service & setting non-root user permissions ==="
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"

echo "=== 5. Testing installation ==="
sudo docker run --rm hello-world

echo ""
echo "SUCCESS: Docker installed!"
echo "NOTE: Log out and back in (or run 'newgrp docker') to use docker without 'sudo'."
