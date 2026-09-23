# syntax=docker/dockerfile:1
FROM node:24-bookworm-slim AS assets
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./frontend/
COPY landing/package.json landing/package-lock.json ./landing/
RUN npm ci --prefix frontend && npm ci --prefix landing
COPY frontend ./frontend
COPY landing ./landing
COPY static ./static
RUN npm run check --prefix frontend && npm run build --prefix frontend \
    && npm run build --prefix landing

FROM python:3.12-slim-trixie AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    BIDPROOF_DATA_ROOT=/data \
    BIDPROOF_JOB_RUNNER=worker
WORKDIR /app
# Debian trixie's PostgreSQL client supports the PostgreSQL 16 deployment's backups.
RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates postgresql-client \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 bidproof \
    && useradd --uid 10001 --gid bidproof --no-create-home --shell /usr/sbin/nologin bidproof
COPY requirements-production.lock ./
RUN pip install --no-cache-dir -r requirements-production.lock
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
COPY --from=assets /build/static ./static
# Only the runtime-imported helpers. Never copy work uploads, corpora, models or backups.
COPY work/backup_restore.py ./work/backup_restore.py
COPY work/eval/sandbox_gates.py ./work/eval/sandbox_gates.py
COPY scripts/entrypoint.sh scripts/serve.sh ./scripts/
RUN chmod 0555 scripts/entrypoint.sh scripts/serve.sh \
    && mkdir -p /data/uploads /data/backups /data/job-staging /data/audit-worm \
    && chown -R 10001:10001 /data \
    && python -c "from pathlib import Path; [p.unlink() for p in Path('static').rglob('*.map')]; p=Path('static/app.js'); p.write_text('\n'.join(line for line in p.read_text().splitlines() if not line.startswith('//# sourceMappingURL='))+'\n')"
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/readyz', timeout=4)" || exit 1
ENTRYPOINT ["./scripts/entrypoint.sh"]
CMD ["./scripts/serve.sh"]
