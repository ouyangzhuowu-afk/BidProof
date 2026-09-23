# Historical Helm scaffolding

The `bidproof/` chart is retained as a historical reference, **not a supported production target for this release**. It predates the hardened image, explicit migrations, public-origin/Host configuration, independent worker lease lifecycle and shared-volume placement rules. Do not install it unchanged.

The supported scope for this delivery is the root `docker-compose.yml` single-host stack; see `docs/production/deployment.md`. A future Kubernetes release must independently verify migration Jobs, secret references, ingress proxy trust, API readiness, worker probes, shared storage scheduling, Pod security and database backup/restore. This repository does not claim that validation has occurred.
