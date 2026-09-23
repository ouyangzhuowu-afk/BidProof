#!/bin/sh
# Single-container start-up for hosting plans that have no separate worker.
#
# The production Compose stack runs the migration as a one-shot service and the
# scan worker as its own container. Render's free instance type offers no
# Background Worker, while production still requires BIDPROOF_JOB_RUNNER=worker,
# so this entrypoint applies the migration once, keeps the scan worker supervised
# inside the web container, and then hands the process over to the HTTP server.
#
# /readyz fails when the worker heartbeat is older than 30 seconds, so a worker
# that keeps dying makes the deployment visibly unhealthy instead of silently
# leaving scans queued.
set -eu

python -m app.dbctl upgrade

(
  while :; do
    python -m app.worker || true
    sleep 2
  done
) &

exec ./scripts/serve.sh
