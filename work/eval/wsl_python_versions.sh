#!/usr/bin/env bash
set -eu
cd /home
echo "=== python versions ==="
ls /usr/bin/python3* 2>/dev/null || true
command -v python3.12 || true
command -v python3.11 || true
command -v python3.10 || true
apt-cache policy python3.12 2>/dev/null | head -5 || true
echo "=== disk ==="
df -h /home | tail -1
