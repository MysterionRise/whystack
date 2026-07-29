---
feature_id: "001"
status: "implementation-in-progress"
inception_baseline: "IB-001"
constitution_version: "1.0.0"
---

# Implementation Plan: Walking Skeleton

## Technical objective

Establish the production-shaped path from a Next.js/CopilotKit interface through
a FastAPI boundary and Postgres-backed LangGraph worker to a durable,
schema-validated AG-UI event stream. The path deliberately uses deterministic
fixtures instead of retrieval or a model provider.

## Constitution check

| Principle | Design evidence | Result |
|---|---|---|
| Inspectable evidence | No evidence claims are emitted in this slice; the fake recommendation is labeled demonstration output. | Pass |
| Deterministic authority | Server derives mode/workspace; Pydantic validates input; code owns revisions, idempotency, and event sequence. | Pass |
| Typed interfaces | OpenAPI 3.1 and JSON Schema 2020-12 define the public boundary; generated TypeScript is checked. | Pass |
| User-owned memory | Memory is absent from this slice; no inferred or durable preference is created. | Pass |
| Product-owned presentation | Only `recommendation-summary@1.0` and the disabled `view-evidence` action are accepted; loading, empty, partial-evidence, abstention, error, reconnect, and completed states remain product-owned. | Pass |
| Privacy and scope | Signed guest context or local deployment derives workspace; denial occurs before side effects. | Pass |
| Test-first delivery | `tasks.md` creates each behavioral test before its production path. | Pass |
| Durable and observable runs | Input snapshots, jobs, ordered events, terminal state, replay, readiness, and redaction are included. | Pass |
| Performance and spend | A fake-model load test exercises the four-second first-useful-UI target; provider spend is zero. | Pass |
| Reproducibility | Compose, locked package managers, migrations, seed fixture, and clean commands are defined. | Pass |

EPIC-001 requires the full controlled-UI and interactive-performance gates.
Its security and operations coverage is explicitly partial: this slice owns
workspace/capability/request/UI/telemetry security plus decision/run/session
durability, idempotency, leases, replay, restart, and reset deletion jobs.
Ingestion/model/connector security and outcome/memory/source/Qdrant/blob
operations remain with the features that introduce those surfaces.

## Runtime topology

| Process | Technology | Responsibility |
|---|---|---|
| `web` | Next.js App Router, React, TypeScript, CopilotKit/AG-UI client | Decision framing, controlled component rendering, resumable event consumption |
| `api` | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 async | Configuration, guest session, decisions, runs, streaming, authorization, health |
| `worker` | Python 3.12, LangGraph, SQLAlchemy 2 async | Lease jobs, run deterministic graph, persist ordered events and terminal state |
| `postgres` | PostgreSQL | Canonical records, idempotency, outbox jobs, event stream |
| `qdrant` | Qdrant | Readiness-only dependency in feature 001; derived vectors begin in feature 002 |

The Next.js server is a thin browser-facing proxy. It forwards the signed guest
cookie and streams API events but stores no domain state and possesses no model
provider key. The browser never calls FastAPI directly in the public deployment.
The Python backend is an installable `src` package built with the locked
`uv_build` backend. Tests, containers, and production entry points import that
installed package and do not depend on `PYTHONPATH`.

Phase A establishes only process topology. The web and worker are reachable
through Compose health checks; the worker has no HTTP or job API. FastAPI
exposes the versioned liveness and readiness paths directly from `main.py`.
T021 later extracts and hardens those probes without changing their contract.
The backend includes an Alembic scaffold with no revision or domain table; an
empty database head set is current only when it exactly equals the repository's
empty head set. T009 introduces `0001_walking_skeleton.py`, updates fresh
Compose startup to apply it before readiness, and changes the permanent
acceptance expectation to exact database/repository equality at that head. The
recorded T002–T003 RED/GREEN evidence remains the proof of the earlier
empty-head state.

## Source layout to create

```text
apps/web/
├── app/
│   ├── api/backend/[...path]/route.ts
│   ├── decisions/new/page.tsx
│   ├── decisions/[decisionId]/page.tsx
│   ├── health/route.ts
│   ├── layout.tsx
│   └── page.tsx
├── src/
│   ├── components/decision/decision-frame-form.tsx
│   ├── components/recommendation/recommendation-summary.tsx
│   ├── contracts/generated.ts
│   ├── contracts/ui-envelope.ts
│   ├── lib/api-client.ts
│   ├── lib/config.ts
│   └── lib/run-stream.ts
├── tests/
└── e2e/

services/backend/
├── alembic.ini
├── migrations/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/                 # empty until T009
├── src/ai_cto_cockpit/
│   ├── api/routes/config.py
│   ├── api/routes/decisions.py
│   ├── api/routes/runs.py
│   ├── api/routes/health.py
│   ├── api/dependencies/context.py
│   ├── contracts/_base.py
│   ├── contracts/config.py
│   ├── contracts/decision.py
│   ├── contracts/errors.py
│   ├── contracts/run.py
│   ├── contracts/ui.py
│   ├── contracts/generate.py
│   ├── domain/ids.py
│   ├── domain/idempotency.py
│   ├── domain/revisions.py
│   ├── persistence/models.py
│   ├── persistence/repositories.py
│   ├── persistence/session.py
│   ├── runs/fake_graph.py
│   ├── runs/jobs.py
│   ├── runs/service.py
│   ├── security/guest_session.py
│   ├── settings.py
│   ├── telemetry.py
│   ├── main.py
│   └── worker.py
└── tests/

contracts/generated/
├── openapi.json
└── ui-envelope.schema.json

infra/
├── compose.yaml
└── env/demo.env
```

## Request and event flow

1. Next.js requests `/api/v1/config` through its server route. FastAPI verifies
   or creates the guest session, derives its workspace, and returns capabilities
   without a raw workspace identifier.
2. A first `/api/v1/session/reset` call validates an active signed guest cookie,
   computes the normalized request hash, and in one transaction creates the
   replacement workspace/session, revokes the old session, queues old-workspace
   deletion, and stores a ten-minute `ResetReplayReceipt` outside either guest
   overlay. If the response is lost, the reset route may verify the signature
   and well-formed immutable claims of the revoked old cookie, derive its
   fingerprint, and replay only the unexpired receipt with the same idempotency
   key and request hash. The receipt lifetime—not the old session's now-revoked
   business expiry—is the replay deadline. The route decrypts the replacement
   token, verifies its hash against the receipt in constant time, and uses the
   receipt's fixed issue/expiry fields with the deterministic cookie serializer
   and signer. It writes the receipt's stored response bytes directly,
   reproducing the original body, content type, and exact `Set-Cookie` value.
   Every other route rejects the revoked cookie.
3. A decision mutation includes `Idempotency-Key`. An update also includes
   `If-Match` with the expected integer revision. The API locks the decision,
   validates the revision and every lossless entered-weight string before
   materializing a coefficient. The accepted lexical form has no sign, exponent,
   or leading zero, at most ten integer digits and eight fractional digits, and
   value from `0.00000001` through `9999999999.99999999`. The API converts the
   strings to common-scale integer coefficients and uses integer `divmod` to
   apportion one million `0.0001`-percentage units by largest remainder with
   criterion-ID tie-breaking. It then inserts an immutable
   `decision_revisions` row containing the exact entered strings and formatted
   normalized strings, and stores the idempotent response in the same
   transaction.
4. Run creation locks the decision, snapshots its current revision, inserts a
   queued run and leased-job candidate, and stores its idempotent response in one
   transaction.
5. The worker claims the oldest available job with `FOR UPDATE SKIP LOCKED`,
   records its lease, and executes a three-node LangGraph:
   `load-snapshot → emit-demonstration → complete-run`.
6. Each graph transition appends a `run_events` row and updates the run
   watermark transactionally. The terminal event includes the validated
   `UiEnvelope`.
7. The API stream polls persisted events after the requested sequence, emits SSE
   `id` equal to the event sequence, sends a heartbeat every fifteen seconds,
   and closes after a terminal event.
8. Next.js validates every envelope before dispatching it to the fixed React
   component map. Invalid or unknown envelopes render a safe error state and
   cannot expose actions. Valid stream and snapshot conditions drive the seven
   product-owned presentation states: loading, empty, partial-evidence,
   abstention, error, reconnect, and completed. Those states do not introduce a
   new event or envelope kind, recommendation intelligence, retrieval, evidence
   claims, or a model call.

## Security and deployment decisions

- `APP_MODE` is exactly `public-demo` or `local-data` and is read only at process
  startup.
- Public-demo sessions use an opaque, signed, `HttpOnly`, `SameSite=Lax` cookie;
  `Secure` is required outside the local Compose profile. Session material is
  stored as a one-way hash.
- A revoked guest cookie is unauthorized everywhere except the reset replay
  branch. That branch first verifies the cookie cryptographically, then requires
  an unexpired receipt matching its fingerprint, operation, idempotency key, and
  normalized request hash. A same-key hash mismatch is HTTP 409; a different
  key, missing/expired receipt, or any other use is HTTP 401.
- Replacement session material in a reset replay receipt is encrypted with an
  authenticated, domain-separated key derived from the session key ring and is
  deleted when the ten-minute receipt expires. The receipt stores no workspace
  content, decision text, source data, or run payload. Cookie signing and
  receipt-encryption key IDs are versioned, and the corresponding keys remain
  available for at least the maximum receipt lifetime so restart or key rotation
  cannot change an in-window replay.
- AEAD associated data binds the receipt ID, old-session fingerprint, operation,
  idempotency key, request hash, replacement-session ID and token hash, cookie
  profile, encryption/signing-key IDs, fixed cookie timestamps, receipt
  timestamps, response status/content type/serializer version, and response-byte
  hash. After decryption, the route constant-time compares the derived token
  hash to the receipt before any cookie is signed and verifies the stored
  response bytes against their bound hash before returning them; ciphertext or
  response substitution between receipts therefore fails closed.
- Local-data mode derives a fixed local workspace on the server and does not
  issue guest sessions.
- Unknown resources and cross-workspace resources share one HTTP 404 response.
- Connector route stubs are registered so denial can be tested. In
  `public-demo`, they return `capability_disabled` before reading or parsing any
  body byte, resolving targets, or invoking persistence, filesystem, network,
  queue, or vector clients. This decision remains pre-body even when the
  advertised or transmitted body exceeds the ordinary request limit.
- CORS permits only the configured web origin. Untrusted `Forwarded` and
  `X-Forwarded-*` headers cannot change the trusted origin, scheme, host,
  client, upstream target, or workspace context.
- Ordinary JSON requests are limited to 256 KiB at both the Next.js proxy and
  FastAPI boundary and fail before JSON parsing or proxy forwarding with HTTP
  413 and stable `request_too_large`.
- Every HTML response uses a fresh nonce for executable scripts and sends a CSP
  that permits only the nonce-bearing scripts and includes
  `frame-ancestors 'none'`. Responses also send
  `X-Content-Type-Options: nosniff` and `Referrer-Policy: no-referrer`.
- Logs, OpenTelemetry traces, and OpenTelemetry metrics use manual,
  allowlisted instrumentation. Allowed fields are limited to route templates,
  methods, statuses, durations, event counts, run states, job outcomes, and
  bounded workspace-safe correlation identifiers. Raw paths, workspace IDs,
  request or response bodies, cookies, authorization headers, UI payloads,
  decision text, and other user-authored content are never captured.

## Persistence and concurrency

- Time-ordered UUIDv7 identifiers are generated server-side with the pinned
  backend UUID implementation; the API accepts only canonical lowercase UUIDv7.
- Timestamps are timezone-aware UTC values supplied by the database.
- Decision revisions use a unique `(decision_id, revision)` constraint.
- A revision stores each criterion's exact bounded decimal-string
  `entered_weight` and integer-derived four-place-string `normalized_weight`;
  normalized values total exactly `100.0000`. Normalization converts the
  validated strings to common-scale integer coefficients, uses integer division
  and remainder for exact one-million-unit quotas, then distributes remaining
  units by descending remainder and ascending criterion ID, so browser numeric
  conversion, input ordering, and decimal arithmetic context cannot change the
  result.
- Run events use a unique `(run_id, sequence)` constraint.
- Idempotency uniqueness is `(workspace_id, operation, key)`, with a normalized
  request hash to detect conflicting reuse.
- Reset replay uses a separate uniqueness key
  `(old_session_fingerprint, operation, key)`. Its request hash excludes the
  cookie and idempotency header but includes the versioned operation, method,
  path, query, and canonical body. Receipts expire ten minutes after the
  original commit and are purged independently of guest-workspace deletion.
  The receipt persists the exact serialized response bytes, content type,
  serializer version, and response hash rather than reserializing JSON on retry.
- Jobs have `available_at`, `lease_owner`, `lease_expires_at`, `attempt_count`,
  and terminal status. A partial worker attempt resumes by reading the run event
  watermark.
- Guest reset creates the replacement guest session, revokes the old session,
  inserts a deletion job, and inserts its replay receipt in one transaction.

## Contract generation

`services/backend/src/ai_cto_cockpit/contracts/` is canonical. The backend
generation command deterministically writes
`contracts/generated/openapi.json` and
`contracts/generated/ui-envelope.schema.json`; repeated generation from the same
inputs is byte-stable. The web generation command writes
`apps/web/src/contracts/generated.ts` and validates that its runtime schema is
semantically equivalent to the checked-in JSON Schema.

The design-time files in this feature directory are binding inputs. Production
generation must be semantically equivalent; ordering and descriptive prose may
differ.

The frontend closed-parser suite includes generated unknown-version, kind,
field, action, markup, script, URL, prototype, oversize, and recursive
payloads. Every malicious case returns the safe typed failure and produces zero
HTML, JavaScript, route, or network action execution.

## Tooling maintenance boundaries

Dependency-lock changes are isolated, reviewed, and applied immediately before
the owning task. Each update regenerates the affected lockfile, updates only the
governance hashes changed by that maintenance packet, reruns bootstrap
verification, and preserves the previously recorded RED evidence.

| Owning task | Locked maintenance |
|---|---|
| T005 | `uv_build==0.11.16` and direct `pyyaml==6.0.3`; convert the backend to an installable `src` package |
| T007 | `eslint==9.39.2`; applied early by `IM-001` because the pre-T005 blocking `make check`/CI gate owns the same compatibility boundary; confirm the pin and retain every accepted Next.js lint rule |
| T009 | `uuid6==2025.0.1` and `cryptography==49.0.0`; AES-256-GCM with a fresh random 96-bit nonce and the `data-model.md` associated data |
| T014 | `hypothesis==6.160.0` |
| T021 | `opentelemetry-sdk==1.44.0` and `opentelemetry-exporter-otlp-proto-http==1.44.0`; manual allowlisted instrumentation |
| T024 | `jsdom==29.1.1`, `@testing-library/react==16.3.2`, `@testing-library/dom==10.4.1`, and `@testing-library/user-event==14.6.1` |

## Verification commands

| Purpose | Command |
|---|---|
| Bootstrap packet | `./scripts/verify-bootstrap.sh` |
| Static quality gates | `make check` |
| Backend unit and contract tests | `uv run --project services/backend pytest services/backend/tests/unit services/backend/tests/contracts` |
| Backend integration and security tests | `uv run --project services/backend pytest services/backend/tests/integration services/backend/tests/api services/backend/tests/security services/backend/tests/property` |
| Frontend unit tests | `pnpm --dir apps/web test` |
| Frontend type and lint checks | `pnpm --dir apps/web check` |
| Compose readiness | `docker compose -f infra/compose.yaml up --build --wait` |
| End-to-end tests | `pnpm --dir apps/web test:e2e` |
| Contract drift | `make contracts-check` |
| Feature evaluation | `make eval-feature FEATURE=001` |

The Compose-readiness acceptance test owns a uniquely named Compose project:
it performs `up --build --wait`, inspects dependencies inside the isolated
network, and always performs `down --volumes`. This makes its single documented
pytest command reproducible and prevents it from touching another local stack.

## Delivery order

1. Repository toolchain, service skeletons, Compose topology, and test harness.
2. Canonical contracts and drift checks.
3. Database migration and persistence primitives.
4. Server-derived context, configuration, and capability denial.
5. Decision revision and idempotency behavior.
6. Durable run, leased worker, fake graph, event persistence, and replay.
7. Web proxy, decision form, event consumer, and controlled component.
8. Isolation, redaction, accessibility, restart, and load evidence.
9. Documentation, clean-room quickstart, traceability evidence, and convergence.

After T005, the `[P]` T006–T007 web-contract lane and `[P]` T008–T009
persistence lane may run concurrently, but each keeps its RED-before-GREEN
order and receives a separate review. After T029, the `[P]` T030–T031
accessibility lane and `[P]` T032–T033 performance lane follow the same rule.
No other task range is parallel.

## Operational evidence

Feature convergence records:

- Compose health and readiness output;
- migration head and schema hash;
- contract-generation diff result;
- unit, integration, property, security, frontend, and end-to-end results;
- reference-Linux five-user load-test p50, p95, p99, sample count, browser/span
  correlation, error rate, and duplicate-effect results after 20 warm-up and at
  least 200 completed measured turns, including 100-event replay;
- automated and manual accessibility reports covering every approved state,
  keyboard and focus-return, reduced motion, 200% zoom, one supported desktop
  screen reader, 360/768/1280/1440-pixel viewports, semantic comparison,
  meaningful announcements, and automated violations;
- configured-origin CORS, untrusted-forwarded-header, 256 KiB API/proxy limit,
  pre-body capability denial, and response-security-header results;
- allowlisted log, trace, and metric capture results;
- feature evaluation manifest containing commit, fixture, schema, and fake-model
  versions.
- immutable clean-clone quickstart and Compose results from macOS and the
  four-vCPU/eight-GiB reference Linux environment.
