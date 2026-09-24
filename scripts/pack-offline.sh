#!/bin/sh
# Build the compose images and wrap them with the chart, compose file and runbooks so an
# air-gapped install can `docker load` then `docker compose up` without hitting a registry.
set -eu

ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="${1:-$ROOT/dist/bidproof-offline-$STAMP.tar}"

mkdir -p "$(dirname "$OUT")" "$ROOT/dist/staging"
cd "$ROOT"

echo "preflight: python scripts/preflight.py --skip-database"
python scripts/preflight.py --skip-database

echo "building images"
docker compose build

IMAGES="$(docker compose config --images | sort -u)"
echo "saving images:"
echo "$IMAGES"

BUNDLE_DIR="$ROOT/dist/staging/bundle"
rm -rf "$BUNDLE_DIR"
mkdir -p "$BUNDLE_DIR"
docker save -o "$BUNDLE_DIR/images.tar" $IMAGES

cp docker-compose.yml Dockerfile .env.example alembic.ini "$BUNDLE_DIR/"
cp -R deploy "$BUNDLE_DIR/deploy"
cp -R docs "$BUNDLE_DIR/docs"
cp scripts/preflight.py scripts/entrypoint.sh "$BUNDLE_DIR/"
printf '%s\n' $IMAGES > "$BUNDLE_DIR/images.txt"
cat > "$BUNDLE_DIR/INSTALL.txt" <<'EOF'
离线安装
1. docker load -i images.tar
2. cp .env.example .env 并填写 POSTGRES_PASSWORD、BIDPROOF_BOOTSTRAP_TOKEN
3. python preflight.py   # 或在应用容器内执行
4. docker compose up -d
5. 打开 http://localhost:8016/app
升级与回滚见 docs/upgrade.md。
EOF

tar -C "$ROOT/dist/staging" -cf "$OUT" bundle
rm -rf "$BUNDLE_DIR"
echo "wrote $OUT"
