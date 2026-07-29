# Northstar Relay Repository Snapshot

This synthetic snapshot represents the service before the architecture decisions in the
evaluation corpus.

The API is a Python 3.12 FastAPI service. Durable application data, background-job leases,
and the audit log are stored in Postgres 16.

The web application is Next.js with TypeScript. It communicates with the API through a
server-side backend-for-frontend; model-provider credentials are never sent to a browser.

Background work currently uses a Postgres `jobs` table with `FOR UPDATE SKIP LOCKED`.
Workers are idempotent and a lease can be reclaimed after sixty seconds.

The prototype search implementation uses Postgres full-text search. Dense retrieval and a
rebuildable external vector index are candidates for the pilot.

No message broker or Kubernetes cluster is deployed. Local development and the pilot
deployment use the same container images through Docker Compose.

