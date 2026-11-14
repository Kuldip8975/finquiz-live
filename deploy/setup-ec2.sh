#!/usr/bin/env bash
# One-time setup on a fresh Ubuntu 24.04 EC2 instance (t3.micro or larger).
# Run on the server:  bash deploy/setup-ec2.sh
set -euo pipefail

sudo apt-get update
sudo apt-get install -y ca-certificates curl git unattended-upgrades
# Security updates install automatically.
sudo dpkg-reconfigure -f noninteractive unattended-upgrades

# 2 GB swap: a t3.micro has only 1 GB of RAM, swap keeps builds and spikes safe.
if ! swapon --show | grep -q /swapfile; then
  sudo fallocate -l 2G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
fi

# Docker Engine + Compose plugin (official convenience script)
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER"
  echo "Docker installed. Log out and back in once, then run this script again."
  exit 0
fi

cd "$(dirname "$0")"
if [ ! -f .env ]; then
  cp .env.example .env
  # Fill a strong random database password automatically.
  sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(openssl rand -hex 24)|" .env
  echo "Created deploy/.env. Edit API_DOMAIN and CORS_ORIGINS, then run this script again."
  exit 0
fi

docker compose up -d --build
docker compose ps
echo "Check: curl https://\$API_DOMAIN/healthz"
