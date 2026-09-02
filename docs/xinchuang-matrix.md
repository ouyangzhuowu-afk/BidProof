# 信创适配矩阵

This matrix is a planning surface, not a claim that BidProof has been certified on these
stacks. Private deployments today ship a Python 3.12 image, PostgreSQL 16 (or SQLite for a
single node), and an independent worker process.

| Layer | Shipping default | Next candidate | Notes |
| --- | --- | --- | --- |
| OS | Debian-based `python:3.12-slim` | 银河麒麟 V10 / 统信 UOS | Rebuild the image `FROM` a customer-supplied base; keep glibc. |
| CPU | x86_64 | 鲲鹏 / 飞腾 | Confirm PyMuPDF wheels or build from source; run `scripts/preflight.py`. |
| Database | PostgreSQL 16 | 达梦 / 人大金仓 | SQLAlchemy dialects would be a dedicated adaptation; JSONB usage in `runs` is the main gap. |
| Queue | Postgres `SKIP LOCKED` / SQLite optimistic claim | same | No extra broker. |
| Identity | Local accounts, optional OIDC / LDAP | 客户 IdP | Bind through `BIDPROOF_OIDC_*` or `BIDPROOF_LDAP_*`. |
| License | Optional `BIDPROOF_LICENSE_KEY` | same | Fail closed only when `BIDPROOF_LICENSE_REQUIRED=1`. |

Do not treat a row in this table as a completed certification. Each cell needs a customer
pilot with their ISO, wheelhouse and identity source before it can be marked verified.
