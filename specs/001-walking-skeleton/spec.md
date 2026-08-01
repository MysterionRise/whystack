---
feature_id: "001"
title: "Walking skeleton"
status: "implementation-in-progress"
inception_baseline: "IB-002"
bmad_epics:
  - EPIC-001
bmad_requirements:
  - FR-001
  - FR-003
  - FR-006
  - FR-011
bmad_nonfunctional_requirements:
  - NFR-002
  - NFR-004
  - NFR-007
  - NFR-008
  - NFR-009
  - NFR-011
bmad_quality_requirements:
  - QUALITY-UI-001
  - QUALITY-SEC-001
  - QUALITY-PERF-001
  - QUALITY-OPS-001
---

# Feature Specification: Walking Skeleton

## Outcome

A visitor can open a seeded public-demo workspace, create and revise a decision
frame, start a deterministic fake-model run, and watch a versioned controlled
recommendation component arrive through the same durable streaming boundary that
later AI features will use. If the stream disconnects, the visitor can resume
from the last acknowledged event. Public-demo users cannot activate uploads or
live connectors.

This slice proves deployment modes, workspace isolation, canonical persistence,
contract generation, controlled Generative UI, run durability, replay, and
redacted observability before real retrieval or model behavior is introduced.

## Quality-gate applicability

EPIC-001 assigns the full `QUALITY-UI-001` and `QUALITY-PERF-001` gates to this
slice and only the relevant portions of `QUALITY-SEC-001` and
`QUALITY-OPS-001`.

- `QUALITY-SEC-001` applies here to server-derived workspace isolation,
  public-demo capability denial, controlled UI input, request/proxy boundaries,
  and telemetry redaction. Source-ingestion, retrieval, model-output, live
  connector, export, and memory attack stages remain with their owning features.
- `QUALITY-OPS-001` applies here to canonical decision/run durability,
  idempotency, leased jobs, ordered replay, restart recovery, guest-session
  expiry, and reset deletion jobs. Outcome/memory/source preservation,
  backup/restore, blob deletion, and canonical-to-Qdrant reconciliation remain
  with features that create those records and vectors. Qdrant is
  readiness-only in feature 001.

This allocation follows the accepted EPIC-001 wording; it does not waive a gate
for any behavior present in this slice.

## Baseline boundary

- `FR-001`: the API exposes server-derived mode and capabilities; the client
  cannot select or elevate a workspace.
- `FR-003`: decision edits create immutable revisions with weighted criteria and
  typed constraints.
- `FR-006`: a persisted run produces ordered, replayable, versioned
  `UiEnvelope` events.
- `FR-011`: the public demo uses an original seed workspace and an expiring guest
  overlay; private ingestion paths are denied.
- `EPIC-001` owns this outcome. The feature does not change the accepted product
  audience, experience authority, storage ownership, or service topology.

## Actors

- **Guest visitor:** uses the public-demo journey without an account.
- **Local operator:** runs local-data mode and owns the single local workspace.
- **API service:** derives workspace and capabilities from trusted deployment and
  session context.
- **Worker:** claims a durable job and emits deterministic fake-model events.

## User journeys and acceptance scenarios

### AS-001 — Deployment readiness

- Given the Compose stack has started with its documented public-demo settings
- When `/api/v1/health/live` and `/api/v1/health/ready` are queried
- Then web, API, and worker report healthy Compose process state
- And Postgres and Qdrant are reachable inside the isolated Compose network
- And the database's current Alembic heads exactly equal the repository heads
- And before T009 the matching head sets are empty, while after T009 a fresh
  stack applies migration `0001_walking_skeleton` before reporting readiness
- And liveness remains distinct from dependency readiness
- And no provider credential is required for this feature

### AS-002 — Server-derived public-demo configuration

- Given a new signed guest session
- When the web application loads configuration
- Then the response reports `public-demo`
- And it reports decision and replay capabilities as enabled
- And it reports uploads, live Git, GitHub, and web connectors as disabled
- And it never returns a workspace identifier, signing secret, database
  credential, or model-provider credential to browser code
- And browser traffic uses the same-origin web proxy with a nonced content
  security policy, `frame-ancestors 'none'`, `X-Content-Type-Options: nosniff`,
  and `Referrer-Policy: no-referrer`
- And the API accepts only the configured web origin and ignores forwarded
  origin, host, scheme, and client-address headers from untrusted peers

### AS-003 — Versioned decision framing

- Given the seeded public-demo workspace
- When the guest creates a decision frame
- Then revision 1 is persisted with a server-derived workspace scope
- And every accepted user-entered criterion weight string is preserved exactly
- And the response visibly exposes deterministic normalized weights whose total
  is exactly `100.0000`
- And the response includes a stable decision identifier and current revision
- When the guest updates the frame using revision 1
- Then revision 2 is created without mutating revision 1
- And a request using stale revision 1 returns HTTP 409
- And repeating either mutation with the same idempotency key returns the
  original result without creating another revision

### AS-004 — Controlled streamed recommendation

- Given a valid current decision revision
- When the guest starts a run
- Then the API persists the immutable input snapshot before dispatch
- And the worker emits ordered run events using the deterministic fake model
- And the terminal event contains a `UiEnvelope` with kind
  `recommendation-summary`, schema version `1.0`, and only approved actions
- And the browser renders the reviewed React component rather than arbitrary
  model markup
- And the completed run snapshot remains queryable

### AS-005 — Resume after disconnect

- Given a run has emitted at least one persisted event
- When the event stream is reconnected with the last acknowledged event
  sequence
- Then only later events are replayed in increasing sequence order
- And no run, event, decision revision, or side effect is duplicated
- And a terminal run can be replayed after API or worker restart

### AS-006 — Public-demo data boundary

- Given public-demo mode
- When a guest calls an upload, local Git, GitHub, or web-connector endpoint
- Then the API returns HTTP 403 with the stable error code
  `capability_disabled`
- And it decides that denial without reading or parsing the request body,
  including when `Content-Length` exceeds the ordinary JSON request limit
- And it creates no source, sync job, blob, vector, outbound network request, or
  background task

### AS-007 — Workspace isolation, reset replay, and redacted observability

- Given two independently signed guest sessions
- When either session requests the other session's decision or run identifier
- Then the API returns HTTP 404 without revealing whether the identifier exists
- And database and stream queries contain the server-derived workspace scope
- And logs, traces, and metrics contain only allowlisted route templates,
  methods, statuses, durations, event counts, run states, and job outcomes
- And no telemetry signal contains workspace identifiers, decision text,
  session tokens, secrets, raw UI payloads, or user-authored content
- And ordinary JSON requests larger than 256 KiB are rejected at both the web
  proxy and API without parsing or application side effects, using HTTP 413 and
  stable error code `request_too_large`
- Given a guest reset committed but its HTTP response was lost
- When the revoked old cookie retries reset within ten minutes with the same
  idempotency key and normalized request hash
- Then the API returns the original response body and exact `Set-Cookie` value
- And a different key, different request hash, expired receipt, or use of that
  cookie on any other endpoint is rejected

### AS-008 — Contract and accessibility integrity

- Given the canonical Pydantic contracts
- When OpenAPI, JSON Schema, and TypeScript artifacts are generated and checked
- Then semantic drift causes continuous integration to fail
- And an unknown `UiEnvelope` version, component kind, action, or property is
  rejected
- And generated markup, script, URL, prototype, oversize, and recursive
  envelope payloads fail closed with zero HTML, JavaScript, route, or network
  action execution
- And product-owned presentation state handles loading, empty, partial-evidence,
  abstention, error, reconnect, and completed outcomes without accepting a new
  model-controlled component kind
- And the walking-skeleton journey is keyboard operable
- And focus returns predictably after transient state, reduced motion is
  respected, the journey remains usable at 200% zoom, comparisons stay
  semantic, and stream announcements remain meaningful
- And manual canonical-journey evidence records keyboard-only navigation,
  reduced motion, 200% zoom, one supported desktop screen reader, and 360,
  768, 1280, and 1440-pixel viewport checks
- And automated accessibility checks report no serious or critical violation

## Functional requirements

### F-001 — Runtime configuration

The API must expose a versioned configuration document derived from deployment
mode and trusted session context. It must enumerate enabled capabilities without
exposing credentials or raw workspace scope. Traces to `FR-001` and `FR-011`.

### F-002 — Guest workspace lifecycle

Public-demo mode must issue a tamper-resistant guest session whose overlay has a
24-hour expiry and can be reset. Reset must atomically create the replacement
guest session, revoke the old session, queue old-overlay deletion, and write a
ten-minute reset replay receipt outside the deletable overlay. A
cryptographically valid revoked old cookie is accepted only by the reset route,
only for the receipt's same idempotency key and normalized request hash, and
only before receipt expiry; signature and immutable-claim validation establish
cookie authenticity, while the receipt's ten-minute expiry is the replay
deadline. That retry must reproduce the original response and exact cookie.
Seed records are immutable; guest-created decisions and runs reside only in the
scoped overlay. Traces to `FR-011`.

### F-003 — Decision revisions

The API must create a decision and append immutable revisions. A revision
contains the question, context, options, typed constraints, each accepted
user-entered criterion weight, its deterministic normalized percentage, and
creation metadata. User-entered weights do not need to total 100 and must remain
unchanged in the persisted revision and response. The API represents an entered
weight as its lossless decimal string: no sign, exponent, or leading zero; at
most ten integer digits and eight fractional digits; and numeric value greater
than zero and less than `10^10`. Server-computed normalized weights are
four-decimal strings, must be visible, and total exactly `100.0000`. Updates
require `expected_revision`; all mutations require an idempotency key. Traces
to `FR-003`.

### F-004 — Durable run creation

Starting a run must atomically persist the run, its decision-revision snapshot,
and an outbox job before returning HTTP 202. Duplicate idempotency keys return
the original run. Traces to `FR-006`.

### F-005 — Deterministic fake-model execution

The worker must claim the job through a renewable database lease and emit the
same approved event sequence for the same fixture version and normalized input.
The final recommendation is visibly labeled as demonstration output. Traces to
`FR-006`.

### F-006 — Ordered event streaming and replay

Each run event must have a monotonically increasing sequence unique within its
run. The API must stream persisted events and accept a last-event sequence for
resume. A terminal snapshot must remain available through a normal JSON
endpoint. Traces to `FR-006`.

### F-007 — Controlled component rendering

The terminal payload must validate against `UiEnvelope` schema version `1.0`.
The frontend must map its discriminated component kind and action kinds to
reviewed React implementations and fail closed for unknown input. Loading,
empty, partial-evidence, abstention, error, reconnect, and completed states are
product-owned view state around the closed envelope; they do not add component
kinds or recommendation intelligence. Traces to `FR-006` and `NFR-007`.

### F-008 — Capability denial

Public-demo mode must deny uploads and all live connectors at the API boundary
before any persistence, queueing, vector indexing, filesystem access, or network
access. Traces to `FR-001`, `FR-011`, `NFR-002`, and `NFR-008`.

### F-009 — Health and observability

The API must expose separate `/api/v1/health/live` and
`/api/v1/health/ready` endpoints. Services must emit structured redacted logs,
metrics, and OpenTelemetry traces correlated by workspace-safe session,
decision, run, and job identifiers. Telemetry attributes and metric labels use
an explicit allowlist and never contain workspace IDs or user-authored content.
The API accepts only the configured web origin, does not trust forwarded
headers unless the peer is explicitly configured, and rejects ordinary JSON
bodies larger than 256 KiB before parsing. Traces to `NFR-002`, `NFR-004`,
`NFR-008`, and `NFR-009`.

### F-010 — Contract generation

Pydantic definitions must produce the OpenAPI and JSON Schema artifacts from
which the TypeScript client and frontend validators are generated. Checked-in
artifacts must match generation output. Traces to `NFR-011`.

## Quality requirements

- **Isolation (`NFR-002`, `QUALITY-SEC-001`):** 10,000 randomized cross-workspace
  data operations produce zero disclosed or mutated records.
- **Durability (`NFR-004`, `QUALITY-OPS-001`):** restart, replay, duplicate
  idempotency, lease expiry, and stale-revision tests pass without duplicate
  effects.
- **Accessibility (`NFR-007`, `QUALITY-UI-001`):** all UI envelopes validate;
  unknown and generated markup, script, URL, prototype, oversize, and recursive
  payloads fail closed with zero arbitrary execution; every product-owned
  presentation state is keyboard and screen-reader operable; focus-return,
  reduced-motion, 200% zoom, semantic comparison, and meaningful stream
  announcements pass; manual evidence covers one supported desktop screen
  reader and 360, 768, 1280, and 1440-pixel viewports; axe reports zero serious
  or critical violations for the complete journey.
- **Observability (`NFR-008`):** automated capture tests find no decision text,
  UI payload, workspace ID, tokens, credentials, or environment-secret values
  in logs, traces, metric labels, or metric attributes.
- **Request boundary (`NFR-002`, `NFR-008`, `QUALITY-SEC-001`):** hostile
  origins and untrusted forwarded headers cannot change trusted context;
  ordinary JSON bodies over 256 KiB fail before parsing at both boundaries;
  ordinary oversized requests return HTTP 413 with `request_too_large`;
  public-demo source and connector denials still return
  `capability_disabled` without reading their bodies.
- **Portability (`NFR-009`):** the documented quickstart and test commands pass
  from clean clones on macOS and the four-vCPU/eight-GiB reference Linux
  environment with Docker Compose; immutable T034 evidence records both runs.
- **Contract compatibility (`NFR-011`):** generated-artifact drift and breaking
  changes without a schema-version increment fail continuous integration.
- **Performance (`QUALITY-PERF-001`):** on the four-vCPU, eight-GiB reference
  Linux deployment, five concurrent guests complete at least 200 measured turns
  after a 20-turn warm-up. Browser timings correlate with server spans; first
  useful UI p95 is at most four seconds, the feature-local fake terminal target
  is at most five seconds and therefore also satisfies the accepted
  completed-recommendation limit of fifteen seconds, non-model API read p95 is
  at most 300 milliseconds, replay of 100 persisted events p95 is at most one
  second, and the error rate is below one percent. Duplicate effects remain
  zero.

## Domain rules

1. A workspace identifier is always derived from a verified session or local
   deployment context.
2. Seed records cannot be updated or deleted through guest APIs.
3. A decision revision is immutable after insertion.
4. Each `enteredWeight` is a lossless decimal string with no sign, exponent, or
   leading zero, at most ten integer digits and eight fractional digits, and
   numeric value in `[0.00000001, 9999999999.99999999]`. The exact submitted
   string, including trailing fractional zeros, is preserved in the immutable
   revision. Entered weights do not need to sum to 100.
5. Normalization converts each bounded decimal string to a positive integer
   coefficient at the common maximum fractional scale, with `W = sum(w)`. One
   unit is `0.0001` percentage point. For each criterion, integer `divmod` of
   `w[i] * 1_000_000` by `W` yields its floor allocation and exact remainder.
   The server assigns the still-unallocated units in descending remainder order,
   breaking ties by ascending criterion ID. Dividing allocated units by
   `10_000` and formatting exactly four fractional digits yields the
   `normalizedWeight` string. No floating-point or rounded intermediate
   participates; the result is independent of input order and totals exactly
   `100.0000`.
6. Typed constraints are versioned discriminated unions; unsupported kinds are
   rejected.
7. The feature accepts only `recommendation-summary` version `1.0`, with
   `view-evidence` as the sole non-consequential action kind.
8. Run event sequences begin at 1, increase by 1, and are unique per run.
9. Completed and failed runs are terminal.
10. A worker lease expiry permits another worker to resume from persisted state;
   it does not permit a second terminal event.
11. An API denial is authoritative even if a client hides or displays a control
    incorrectly.
12. A reset replay receipt expires ten minutes after the original reset. It is
    not workspace-owned and may contain only one-way session and idempotency-key
    hashes, fixed operational metadata, encrypted replacement-session material
    needed to reconstruct the cookie, fixed cookie issue/expiry values, the
    server-authored original reset response, and receipt timestamps—never the
    raw idempotency key, source, decision, run, or other raw user content.
13. Receipt encryption uses authenticated associated data binding the receipt
    identity, old-session fingerprint, operation, idempotency-key hash, request hash,
    replacement-session identity and token hash, encryption/signing key IDs,
    cookie profile and fixed timestamps, receipt timestamps, response status,
    content type, serializer version, and response-byte hash. Decrypted
    replacement material is never used until its token hash matches the receipt
    in constant time, and response bytes are never returned until their hash
    matches.

## Data and contract impact

The slice introduces `Workspace`, `GuestSession`, `Decision`,
`DecisionRevision`, `Run`, `RunEvent`, `Job`, `DeletionCompletion`, and
`IdempotencyRecord`. Their fields and invariants are defined in `data-model.md`.
It also introduces the short-lived, raw-user-content-free
`ResetReplayReceipt`, which deliberately lives outside the guest overlay so
deletion of the old workspace cannot destroy reset replay semantics.

The executable API contract is `contracts/openapi.yaml`. The controlled component
contract is `contracts/ui-envelope.schema.json`. Later feature contracts for
evidence, recommendations, outcomes, memory, sources, and exports are reserved
by name in the data model but do not gain endpoints in this slice.

## Failure and recovery behavior

- Invalid contracts return HTTP 422 with stable machine-readable error codes and
  field locations.
- Missing or out-of-scope resources return the same HTTP 404 shape.
- Stale revisions return HTTP 409 with the current revision number.
- For non-reset mutations, reused idempotency keys with the same normalized
  request return the original status and resource; reuse with a different
  request returns HTTP 409.
- A reset retry made with the cryptographically valid revoked old cookie, the
  same key, and the same request hash within ten minutes returns the original
  HTTP 202 body and exact `Set-Cookie` value. The same key with a different hash
  returns HTTP 409. A different key, an expired or missing receipt, or any
  non-reset use of the revoked cookie returns HTTP 401.
- Reset replay receipts are purged after expiry independently of workspace
  deletion and retain no raw idempotency key, source, decision, run, or other
  raw user-authored content.
- Successful guest-overlay deletion removes the workspace plus its
  workspace-owned content and operational rows, including the deletion job,
  while retaining one non-sensitive audit row,
  `DeletionCompletion` containing only server-derived workspace/job IDs, a fixed
  operation, and completion time. It cannot authorize or reconstruct the
  deleted workspace.
- A database or migration failure makes readiness fail and prevents mutations.
- Qdrant unavailability makes readiness fail because the deployment topology is
  being proven, although this feature does not write vectors.
- A worker failure retains the leased job; lease expiry makes it claimable.
- A malformed fake-model event fails the run without streaming unvalidated UI.
- Stream disconnect does not cancel the durable run.
- Guest reset immediately revokes the old session and queues scoped overlay
  deletion; subsequent access with that session is unauthorized except for the
  exact, time-bounded reset replay described above.

## Out of scope

- OpenRouter calls or any real language-model behavior.
- Source normalization, embeddings, retrieval, reranking, citations, or Qdrant
  writes.
- Deterministic option scoring, recommendation policy, close calls, or
  abstention.
- Outcome events, long-term memory, and memory influence.
- Upload, local Git, GitHub, or web connector implementations.
- ADR or JSON decision export.
- Accounts, invitations, collaboration, and autonomous write actions.

## Verification

| Scenario | Primary automated evidence |
|---|---|
| `AS-001` | `services/backend/tests/integration/test_health.py`; `tests/e2e/test_compose_readiness.py` |
| `AS-002` | `services/backend/tests/api/test_config.py`; `services/backend/tests/security/test_request_boundaries.py`; `apps/web/tests/config-boundary.test.ts`; `apps/web/tests/security-boundary.test.ts` |
| `AS-003` | `services/backend/tests/api/test_decisions.py`; `services/backend/tests/property/test_revision_idempotency.py` |
| `AS-004` | `services/backend/tests/integration/test_run_lifecycle.py`; `apps/web/tests/recommendation-summary.test.tsx` |
| `AS-005` | `services/backend/tests/integration/test_run_replay.py`; `apps/web/e2e/walking-skeleton.spec.ts` |
| `AS-006` | `services/backend/tests/security/test_demo_capabilities.py`; `services/backend/tests/security/test_request_boundaries.py` |
| `AS-007` | `services/backend/tests/api/test_session_reset.py`; `services/backend/tests/security/test_workspace_isolation.py`; `services/backend/tests/security/test_telemetry_redaction.py`; `services/backend/tests/security/test_telemetry_metrics.py` |
| `AS-008` | `services/backend/tests/contracts/test_openapi.py`; `apps/web/tests/ui-envelope-contract.test.ts`; `apps/web/tests/recommendation-summary.test.tsx`; `apps/web/e2e/walking-skeleton-accessibility.spec.ts`; `evals/results/feature-001/accessibility-manual.md` |

## Clarification record

- The product has two build-time deployment profiles: `public-demo` and
  `local-data`; a browser cannot switch them.
- Public-demo overlay expiry is 24 hours.
- Feature 001 uses only a deterministic fake model and requires no model key.
- Server-sent events carry durable run events; normal JSON returns snapshots.
- Postgres-backed jobs and leases are sufficient for v1; Redis is not part of
  the accepted architecture.
- Phase A health paths are `/api/v1/health/live` and
  `/api/v1/health/ready`; later health tasks harden these same endpoints.
- Before T009 introduces migration `0001_walking_skeleton`, the preserved Phase
  A evidence proves that both Alembic head sets are empty. T009 updates fresh
  Compose startup to apply that migration; the permanent readiness assertion is
  exact database/repository head equality rather than an empty-set assertion.
- The Compose-readiness acceptance test owns and cleans up a uniquely named
  Compose project; worker reachability in Phase A means healthy process state,
  not an HTTP or job API.
- The Node 24 frontend toolchain locks `@types/node` at `24.13.3`; Next.js
  requires those runtime typings for a reproducible production build.
- Ordinary JSON requests are limited to 256 KiB at both the web proxy and API.
  Oversized ordinary requests return HTTP 413 with stable code
  `request_too_large`.
  Public-demo source and connector routes decide their fixed capability denial
  before reading a body, so an oversized denied upload cannot consume parser or
  downstream resources.
- Loading, empty, partial-evidence, abstention, error, reconnect, and completed
  are deterministic product-owned view states. They do not expand
  `UiEnvelope`, authorize arbitrary UI, or add recommendation logic.
- `QUALITY-UI-001` remains whole in this slice: generated markup, script, URL,
  prototype, oversize, and recursive payloads are included in the closed-parser
  fuzz suite, while focus-return and 200% zoom remain blocking browser checks.
- In that closed-parser suite, markup, script, URL, and route payloads mean
  attempts to introduce unauthorized executable or transport-bearing fields or
  action kinds. Character sequences inside approved text fields remain inert
  text and are never interpreted as markup, script, or a destination. A parser
  failure exposes only `invalid_ui_envelope`, never raw input or validator
  diagnostics.
- `QUALITY-PERF-001` uses the accepted four-vCPU/eight-GiB Linux profile, five
  concurrent users, 20 warm-up turns, and at least 200 completed measured
  turns. The feature-local five-second fake-terminal target is stricter than
  the accepted fifteen-second completed-recommendation ceiling; all other
  accepted latency, replay, correlation, and error-rate gates remain blocking.
- T034 requires full quickstart and Compose evidence from clean clones on both
  macOS and the reference Linux environment; a single-platform run cannot
  satisfy the portability claim.
- Qdrant participates in readiness to prove deployment topology but is unused by
  business behavior until feature 002.
- Guest reset revokes access synchronously and performs physical cleanup through
  a durable background job. A raw-user-content-free reset replay receipt survives that
  cleanup for ten minutes so a lost response can be retried exactly. It is the
  bounded non-workspace operational-receipt exception defined by Constitution
  Article VI: it carries no `workspace_id` or raw caller content, cannot recover
  the triggering or revoked workspace, and cannot itself authorize any
  workspace. It is reachable only from a separately verified old-session
  fingerprint and may reproduce only the already-committed replacement
  response; ordinary replacement-session verification derives its workspace.
- Every workspace-owned persistence row, including decision revisions and run
  events, carries the server-derived `workspace_id`; child-row scope must match
  its parent aggregate.
- Decision requests carry bounded lossless decimal-string entered weights; the
  server preserves each exact string and visibly returns deterministic
  four-decimal-string normalized percentages totaling `100.0000`.
- All product and implementation decisions needed for this slice are resolved.
