FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BIDPROOF_DATA_ROOT=/data

WORKDIR /app

COPY requirements.txt requirements-postgres.txt ./
RUN pip install --no-cache-dir -r requirements-postgres.txt

COPY app ./app
COPY static ./static
COPY work ./work
COPY migrations ./migrations
COPY alembic.ini ./
COPY scripts/entrypoint.sh ./scripts/entrypoint.sh
RUN chmod +x ./scripts/entrypoint.sh

RUN mkdir -p /data/uploads /data/backups /data/job-staging

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz')" || exit 1

ENTRYPOINT ["./scripts/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers"]
