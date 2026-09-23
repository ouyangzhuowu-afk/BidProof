#!/bin/sh
# This process serves HTTP only. The worker is a separate supervised container.
set -eu
_bidproof_port="${PORT:-8080}"
_bidproof_proxy_ips="${BIDPROOF_TRUSTED_PROXY_IPS:-127.0.0.1}"
case "$_bidproof_proxy_ips" in
  *\**) echo 'Wildcard proxy trust is not supported' >&2; exit 1 ;;
esac
exec uvicorn app.main:app --host 0.0.0.0 --port "$_bidproof_port" \
  --workers "${BIDPROOF_WEB_CONCURRENCY:-2}" \
  --proxy-headers --forwarded-allow-ips "$_bidproof_proxy_ips" \
  --limit-concurrency 64 --backlog 128 \
  --timeout-keep-alive 10 --no-access-log
