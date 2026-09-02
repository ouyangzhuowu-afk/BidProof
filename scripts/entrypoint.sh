#!/bin/sh
# Bring the schema to the current revision before serving, so a container start after an
# image upgrade cannot serve against an older schema.
set -eu

if [ "${BIDPROOF_SKIP_MIGRATIONS:-0}" = "1" ]; then
  echo "entrypoint: BIDPROOF_SKIP_MIGRATIONS=1, leaving the schema untouched"
else
  echo "entrypoint: applying database migrations"
  # Not plain `alembic upgrade head`: a pilot database created before Alembic has tables but
  # no version row, and needs adopting at the baseline first.
  python -m app.dbctl upgrade
fi

exec "$@"
