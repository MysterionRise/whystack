# Research Decisions: Walking Skeleton

Date: 2026-07-27  
Baseline: IB-002
Status: Resolved

## R-001 — Separate TypeScript web and Python backend

**Decision:** Use Next.js and React for the portfolio interface, with
CopilotKit/AG-UI at the presentation boundary, and FastAPI, Pydantic, and
LangGraph for the application and agent workflow.

**Reason:** The split exercises the product's intended Generative UI protocol
while preserving Python-native retrieval, evaluation, and orchestration. An
OpenAPI/JSON Schema boundary makes the integration inspectable.

**Rejected:** A full-stack TypeScript implementation would reduce language
boundaries but abandon the strongest reusable Python course assets. Chainlit or
Gradio would shorten the first demo but would not demonstrate the intended
controlled, portfolio-grade interface.

## R-002 — Thin Next.js server proxy

**Decision:** Browser requests pass through a thin Next.js route handler. It
forwards signed session context and streams events but owns no domain state,
authorization decision, or provider key.

**Reason:** This keeps browser deployment simple while ensuring FastAPI remains
the single application authority.

**Rejected:** Direct browser-to-FastAPI access duplicates session and CORS
complexity. Putting domain logic into both Next.js and FastAPI would create
competing authorities.

## R-003 — Postgres event persistence before streaming

**Decision:** Persist run events in Postgres, then expose them over
server-sent events with sequence-based replay.

**Reason:** The event log supports reconnect, restart, audit, and later
evaluation without introducing a second durable stream system.

**Rejected:** Ephemeral in-process streaming loses state on restart. WebSockets
add bidirectional protocol complexity that this server-to-client flow does not
need. Redis Streams would duplicate infrastructure before evidence demonstrates
a scaling need.

## R-004 — Postgres job table with leases

**Decision:** Use a Postgres outbox/job table, worker leases, and
`SKIP LOCKED` claims.

**Reason:** It preserves atomic run creation and work dispatch while keeping the
first deployable stack small.

**Rejected:** Celery plus Redis introduces another stateful service and
eventual-consistency edge. In-process background tasks do not survive API
restart.

## R-005 — Deterministic LangGraph fixture

**Decision:** Exercise an explicit three-node LangGraph with a versioned,
deterministic fixture rather than calling OpenRouter in feature 001.

**Reason:** It proves orchestration, durability, controlled streaming, and
testing without cost, network variance, or prompt uncertainty.

**Rejected:** A real model would make infrastructure failures indistinguishable
from model variance and would weaken repeatable acceptance tests. Skipping
LangGraph would postpone proof of the accepted orchestration boundary.

## R-006 — Pydantic as contract source

**Decision:** Pydantic models are canonical. OpenAPI, JSON Schema, generated
TypeScript types, and runtime validators must remain semantically equivalent.

**Reason:** Backend validation is an authority boundary, while checked
cross-language artifacts prevent silent contract drift.

**Rejected:** Hand-maintaining separate Python and TypeScript models invites
semantic divergence. Making TypeScript canonical would require duplicative
backend validation adapters.

## R-007 — Controlled Generative UI catalog

**Decision:** Feature 001 supports only `recommendation-summary@1.0` with the
non-consequential `view-evidence` action.

**Reason:** A single discriminated component proves generative composition while
keeping rendering, accessibility, and action authority in reviewed code.

**Rejected:** Arbitrary HTML or model-authored component code is unsafe and
unverifiable. A broad initial component catalog expands testing without proving
the core boundary more clearly.

## R-008 — Build-time deployment mode

**Decision:** Mode is process configuration, not a browser setting. Public demo
uses signed, expiring guest overlays; local-data uses a fixed server-derived
workspace.

**Reason:** Capabilities cannot be elevated by client input, and both data
profiles exercise the same application contracts.

**Rejected:** Runtime client switching risks cross-mode state and authorization
errors. Accounts are deliberately outside v1.

## R-009 — Qdrant is readiness-only in feature 001

**Decision:** Include Qdrant in Compose and readiness checks without writing
vectors until feature 002.

**Reason:** The walking skeleton proves the accepted deploy topology without
inventing premature retrieval behavior.

**Rejected:** Omitting Qdrant would postpone deployment integration. Writing
dummy vectors would create behavior with no user requirement.

## R-010 — UUIDv7 and database UTC timestamps

**Decision:** Generate canonical lowercase UUIDv7 identifiers on the server with
the pinned `uuid6` backend dependency and use database-supplied timezone-aware
UTC timestamps.

**Reason:** The approach is portable and opaque while preserving time ordering
for database index locality and event-heavy aggregates.

**Rejected:** Sequential identifiers leak resource counts. UUIDv4 is portable
but produces poorer insertion locality for the durable event stream.

## R-011 — Header semantics

**Decision:** Every mutation requires `Idempotency-Key`; revision-changing
operations also require `If-Match` with the expected integer revision.

**Reason:** Standard request metadata keeps replay safety separate from the
domain payload and permits consistent proxy behavior.

**Rejected:** Body-level idempotency and revision fields pollute domain
contracts. Last-write-wins would violate immutable decision history.

## R-012 — No unresolved implementation choice

Python 3.12, the active Node.js LTS recorded in the toolchain lock, `uv`, `pnpm`,
Docker Compose, Postgres, and Qdrant form the supported environment. Dependency
patch versions and container digests are captured by lockfiles during the
toolchain task; upgrades are isolated maintenance changes rather than feature
work.
