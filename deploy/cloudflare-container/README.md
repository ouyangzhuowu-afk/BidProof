# BidProof Cloudflare Container

This deployment publishes the existing FastAPI application at `bidproof.marketcase.net` without replacing the MarketCase root site.

The container starts with an empty SQLite database and empty upload directory. The current local demo database is intentionally excluded. Container disk is ephemeral; this is a pilot/preview deployment until persistent R2/D1 storage is added.

The Worker injects `BIDPROOF_ENV=production`, disables trusted identity headers, and reads `BIDPROOF_BOOTSTRAP_TOKEN` from a Cloudflare Worker secret. Set the secret after the first Worker exists and before allowing the first container request:

```powershell
npx wrangler secret put BIDPROOF_BOOTSTRAP_TOKEN
```

Do not place the token in this directory, the Docker image, or command output. Cloudflare Containers also requires an account plan with Containers access. On the current account, `/accounts/.../containers/me` returns HTTP 401, so the public pilot currently uses the existing Cloudflare Tunnel instead of this container package.

## Commands

```powershell
npm install
npm test
docker build -t bidproof-marketcase .
npx wrangler deploy
```
