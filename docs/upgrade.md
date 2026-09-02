# Upgrade and rollback

BidProof schema changes go through Alembic. The container entrypoint runs
`python -m app.dbctl upgrade` on start, which also adopts a pre-Alembic SQLite file (tables
present, no `alembic_version` row) at the baseline before applying later revisions.

Do not run plain `alembic upgrade head` against a pilot database.

## Before an upgrade

1. Take a backup: `python -m work.backup_restore create`
2. Verify it: `python -m work.backup_restore verify <backup-dir>`
3. Record the running image tag and the current revision:

   ```bash
   python -m app.dbctl current
   python scripts/preflight.py
   ```

4. Confirm `current` equals `head` after the new image starts. Preflight fails closed if they
   differ.

## Upgrade (compose)

```bash
docker compose pull   # or docker load -i images.tar for an offline pack
docker compose up -d --build
python scripts/preflight.py
```

The API and worker share the data volume and the same `BIDPROOF_DATABASE_URL`. Only one
schema migrator is needed; both processes are safe to start because Alembic upgrades to an
already-applied head are no-ops.

## Rollback

1. Stop the new image: `docker compose down`
2. Restore the backup taken in step 1:

   ```bash
   # SQLite
   python -m work.backup_restore restore <backup-dir> \
     --target-db /data/bid_agent.sqlite3 \
     --target-uploads /data/uploads

   # PostgreSQL
   python -m work.backup_restore restore <backup-dir> \
     --target-db /data/unused.sqlite3 \
     --target-uploads /data/uploads \
     --database-url "$BIDPROOF_DATABASE_URL"
   ```

3. Start the previous image tag. Do not Alembic-downgrade a PostgreSQL dump that was taken
   after a forward migration; restore the dump instead so data and revision stay together.

## Helm

Set `image.tag` to the previous known-good value and `helm rollback bidproof 1` only after
the matching database backup has been restored. The chart does not automatically reverse
Alembic revisions.
