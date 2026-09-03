#!/bin/sh
# Bind to the platform PORT (Render defaults to 10000; local Docker stays 8080).
set -eu
PORT="${PORT:-8080}"
exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --proxy-headers --forwarded-allow-ips='*'
