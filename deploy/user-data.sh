#!/bin/bash
# EC2 "user data": runs once, as root, the first time the server boots.
# Paste it into Launch instance -> Advanced details -> User data.
#
# It installs Docker, fetches the code from GitHub, creates deploy/.env with a
# random database password (so no secret ever lives in the repository), and
# starts Postgres + backend + Caddy. Caddy gets an HTTPS certificate for
# api.<public-ip>.sslip.io automatically.
#
# Progress log on the server: /var/log/cloud-init-output.log
set -euxo pipefail

REPO=https://github.com/Kuldip8975/finquiz-live.git
FRONTEND_ORIGIN=https://finquiz-live.reazixtechnologies.workers.dev

# 2 GB swap: a t3.micro has only 1 GB of RAM.
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl git unattended-upgrades
dpkg-reconfigure -f noninteractive unattended-upgrades

# Docker Engine + Compose plugin (official install script)
curl -fsSL https://get.docker.com | sh
usermod -aG docker ubuntu

cd /home/ubuntu
[ -d finquiz-live ] || git clone "$REPO" finquiz-live
cd finquiz-live/deploy

# Public IP from the instance metadata service (IMDSv2)
TOKEN=$(curl -sfX PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 60")
IP=$(curl -sf -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/public-ipv4)

if [ ! -f .env ]; then
  umask 077
  cat > .env <<EOF
POSTGRES_PASSWORD=$(openssl rand -hex 24)
API_DOMAIN=api.${IP//./-}.sslip.io
CORS_ORIGINS=${FRONTEND_ORIGIN}
QUESTION_SECONDS=20
EOF
fi

chown -R ubuntu:ubuntu /home/ubuntu/finquiz-live
docker compose up -d --build
echo "FinQuiz backend: https://api.${IP//./-}.sslip.io/healthz"
