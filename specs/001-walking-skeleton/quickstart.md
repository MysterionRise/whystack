# Walking Skeleton Quickstart

This quickstart describes the repository after feature 001 has been implemented.
It is also the convergence command list for T034.

## Prerequisites

- Docker Engine with Docker Compose v2
- Python 3.12 and `uv`
- Node.js `24.18.0`, selected from `.node-version`
- Corepack pnpm `11.17.0`
- GNU Make

No model-provider credential is required for this feature.

## Configure public-demo mode

1. Copy `.env.example` to `.env`.
2. Keep `APP_MODE=public-demo`.
3. Set fresh local values for the guest-session signing key and database
   password.
4. Keep all connector capability flags disabled.

The public-demo profile uses only the bundled original seed fixture. It must not
mount personal repositories or files.

## Start and inspect

Run:

```sh
docker compose -f infra/compose.yaml up --build --wait
docker compose -f infra/compose.yaml ps
curl --fail http://localhost:8000/api/v1/health/live
curl --fail http://localhost:8000/api/v1/health/ready
```

Open `http://localhost:3000`. Create a decision, revise it once, start the
demonstration run, interrupt the browser connection, and reload. The final
controlled recommendation component must resume without duplicating events.

## Validate

Run:

```sh
./scripts/verify-bootstrap.sh
make node-toolchain-check
make install
make check
make contracts-check
uv run --project services/backend --locked pytest
uv run --project services/backend --locked pytest tests/e2e/test_compose_readiness.py
corepack pnpm --dir apps/web check
corepack pnpm --dir apps/web test
corepack pnpm --dir apps/web test:e2e
make eval-feature FEATURE=001
```

All commands must pass from a clean clone. `make check` is blocking and covers
Ruff linting and formatting, Pyright over backend source and tests, and
frontend linting and type checking.

## Exercise the public-demo boundary

The frontend must display uploads and live connectors as unavailable. Direct API
requests to the reserved upload, local Git, GitHub, and web connector routes
must return HTTP 403 with `capability_disabled` and must create no job or source
record. The denial must be decided without reading the request body, including
when that body is larger than the ordinary 256 KiB JSON limit.

Only the configured web origin may receive CORS access. Untrusted forwarded
headers must not change trusted request or workspace context. Ordinary JSON
bodies larger than 256 KiB must be rejected at both the web proxy and API.
HTML responses must carry a per-response script nonce, a CSP containing
`frame-ancestors 'none'`, `X-Content-Type-Options: nosniff`, and
`Referrer-Policy: no-referrer`.

## Stop and remove local test data

Run:

```sh
docker compose -f infra/compose.yaml down --volumes
```

This command is appropriate only for disposable local Compose data. It is not a
production deletion procedure.

## Local-data profile

Feature 001 proves that `APP_MODE=local-data` derives a fixed local workspace and
reports the different capability profile. Real ingestion and OpenRouter calls
are not implemented until later features, so the walking-skeleton run remains
deterministic in both modes.
