---
artifact: product-requirements-document
baseline: IB-001
status: accepted
date: 2026-07-27
---

# Product Requirements Document

## Objective

Deliver a public, inspectable portfolio product and a local-data deployment
profile for evidence-backed architecture decisions. The product must distinguish
retrieved evidence, model judgment, deterministic policy, user decisions, and
durable memory at every boundary.

## Terminology

- **Workspace:** the server-derived isolation boundary for sources, decisions,
  runs, events, and memory.
- **Source artifact:** a logical document, repository item, issue, pull request,
  or web page.
- **Source revision:** immutable normalized content with checksum and locator
  metadata.
- **Decision frame:** a versioned question, context, candidate options, weighted
  criteria, and typed constraints.
- **Run:** an immutable execution snapshot for a decision revision.
- **Evidence reference:** an authorized pointer to an exact source revision and
  locator, with excerpt and retrieval metadata.
- **Outcome:** an explicit accept, edit-and-accept, dismiss, revisit, or
  supersede event.
- **Memory fact:** an active, typed durable fact backed by explicit provenance.
- **Memory proposal:** an inferred candidate that has no effect until confirmed.
- **UI envelope:** a versioned discriminated union of reviewed components and
  actions.
- **Useful UI:** the first meaningful evidence, progress, or decision component,
  excluding a spinner or generic status message.

## Functional requirements

### FR-001 — Deployment-aware workspace configuration

The system shall expose its server-derived runtime profile, enabled
capabilities, and workspace scope without returning secrets. Public-demo and
local-data restrictions shall be enforced at the API and worker boundaries,
not through prompts or hidden UI controls.

Acceptance:

- a public-demo session receives a signed guest workspace and its capability
  response excludes upload and live-connector actions;
- direct public-demo requests to disabled ingestion endpoints return a
  deterministic `403` response;
- a model response cannot select or alter `workspace_id`;
- local-data mode can enable approved connector types only after disclosure and
  explicit activation.

### FR-002 — Source ingestion and immutable revision provenance

The system shall normalize each permitted source into a logical artifact and
immutable checksum-addressed revision with origin, observed time, exact locator,
media type, parser version, access scope, and deletion state.

Acceptance:

- ingesting unchanged content is idempotent;
- changed content creates a new revision and retains prior cited revisions;
- citation text is recoverable from canonical storage without Qdrant;
- deletion removes the source from active retrieval and schedules derived index
  cleanup;
- malformed, oversized, unsupported, or out-of-scope sources fail with a typed
  reason and do not create a partial active revision.

### FR-003 — Versioned decision framing

The user shall create and revise a decision question, context, candidate
options, weighted criteria, and typed constraints. A revision shall not mutate
prior runs or outcomes.

Acceptance:

- weights are normalized visibly while preserving user-entered values;
- supported hard constraints include budget, deadline, required capability,
  forbidden vendor, license, residency, and deployment mode;
- free-form guidance is advisory and visually distinct from hard constraints;
- editing a frame with an existing run creates a new revision;
- concurrent mutation with a stale expected revision returns `409`.

### FR-004 — Scoped hybrid evidence retrieval

The system shall retrieve only authorized evidence using PostgreSQL full-text
search and Qdrant dense retrieval, fuse and rerank results, enforce source
diversity, and return a bounded evidence set with resolvable references.

Acceptance:

- every query and vector filter includes server-derived workspace scope;
- a run uses no more than twelve evidence units;
- each evidence reference resolves to the exact immutable revision and locator;
- Qdrant loss can be repaired from PostgreSQL and source blobs;
- evidence freshness and retrieval/rerank scores are inspectable;
- insufficient or conflicting evidence remains visible to recommendation logic.

### FR-005 — Deterministic option assessment and recommendation

The system shall use the model for cited option and criterion assessments, then
apply typed constraints and weighted scores in deterministic code. It shall
return a recommendation, close-call result, or abstention.

Acceptance:

- an option with a failed hard constraint cannot be recommended;
- an unknown hard constraint blocks recommendation until resolved or explicitly
  removed by the user;
- a recommendation requires at least 70% weighted evidence coverage and a
  five-point score lead on a 100-point scale;
- results below either threshold present a close call or abstention with the
  missing evidence;
- unsupported citation locators permit one repair attempt, after which the run
  fails closed;
- the persisted run records scoring inputs, outputs, provider/model, prompts,
  schema, retriever, reranker, dataset, and code revision fingerprints.

### FR-006 — Controlled streamed decision UI and replay

The system shall stream versioned UI envelopes containing only approved
component kinds, payloads, and actions. It shall persist run events so a client
can reconnect and replay without duplicating effects.

Acceptance:

- unknown component versions, kinds, fields, and actions fail closed;
- envelopes cannot contain executable HTML, JavaScript, route definitions, or
  arbitrary network actions;
- React owns layout, keyboard behavior, labels, and focus;
- reconnecting from a known event cursor replays subsequent events in order;
- repeated delivery cannot commit a second durable outcome;
- interrupted, degraded, and failed states provide an accessible recovery path.

### FR-007 — Explicit outcome event ledger

The system shall record accept, edit-and-accept, dismiss, revisit, and supersede
as append-only decision events linked to the exact decision and run revisions.

Acceptance:

- only an explicit authenticated or signed user action creates an outcome;
- every mutation requires an idempotency key and expected revision;
- an edited acceptance preserves both the recommendation and accepted form;
- supersession preserves historical provenance;
- the current decision state can be rebuilt from the event ledger.

### FR-008 — Provenance-backed long-term memory

The system shall convert explicit accepted outcomes and preferences into active
typed facts and keep inferred preferences inactive until confirmed. Users shall
inspect, confirm, correct, supersede, and delete memory.

Acceptance:

- each fact cites its source event and validity interval;
- inference produces a proposal, never an active fact;
- context priority is current frame, typed constraints, recent accepted
  outcomes, explicit preferences, confirmed inferred preferences, then older
  history;
- context is budgeted by section and omits low-priority entries deterministically;
- every run records memory fact identifiers and their ranking influence;
- deletion removes active fact references and derived vectors within the
  lifecycle limit while retaining only non-sensitive audit metadata required
  for integrity;
- a corrected or superseded fact no longer influences new runs.

### FR-009 — Auditable decision export

The user shall export an accepted decision as a readable Markdown ADR and a
machine-readable JSON bundle.

Acceptance:

- both formats include the frame revision, alternatives, constraint results,
  scores, recommendation, accepted outcome, risks, unknowns, citation locators,
  memory influences, and version fingerprints;
- exports are generated from canonical persisted state;
- a citation remains identifiable when its active source has later been
  deleted, without retaining deleted private text;
- filenames and contents are safe from path or markup injection.

### FR-010 — Read-only local-data connectors and resumable sync

Local-data mode shall provide read-only adapters for allowlisted local Git
files, uploaded Markdown/text/PDF/JSON/CSV, GitHub repositories/issues/pull
requests, and bounded web sources. Sync shall be resumable and observable.

Acceptance:

- connectors implement scan, fetch, and normalize boundaries;
- sync uses durable leased jobs with cursor, retry, idempotency, and dead-letter
  state;
- repository hooks, downloaded scripts, archives, path escapes, unsafe
  redirects, and private-network web destinations are rejected;
- incremental sync creates revisions and tombstones without rewriting history;
- credentials are stored server-side and redacted from logs;
- every connector has disconnect and wipe controls.

### FR-011 — Seeded public-demo journey and ephemeral reset

The public demo shall provide an original fixed corpus and two related
architecture decisions through a signed ephemeral guest overlay.

Acceptance:

- the journey works without visitor credentials or uploads;
- the first outcome creates an inspectable memory fact;
- the second recommendation shows whether and why that fact affected ranking;
- reset immediately creates a clean overlay;
- overlays expire within 24 hours;
- request, turn, concurrency, input, agent-step, and daily-spend limits are
  enforced server-side.

### FR-012 — Inspection and evaluation surfaces

The system shall expose evidence, constraint outcomes, scoring, memory
influences, execution versions, latency, cost, and evaluation status without
revealing provider secrets or raw private telemetry.

Acceptance:

- a user can move from a recommendation claim to its evidence locator;
- “why changed” distinguishes evidence, frame, constraint, scoring, and memory
  effects;
- run metadata identifies the exact versions needed for reproduction;
- public traces contain metadata and hashes, not raw private passages;
- maintainers can compare a candidate release against the accepted evaluation
  baseline.

## Non-functional requirements

### NFR-001 — Evidence integrity and groundedness

All externally verifiable recommendation claims require validated citations.
Release gates require 100% resolvable locators, citation precision of at least
0.95, weighted claim coverage of at least 0.90, and zero fabricated locators.

### NFR-002 — Tenant isolation and authorization

Every canonical and derived record carries a workspace scope derived from
signed or authenticated server context. Automated isolation tests must find
zero cross-workspace reads or writes across 10,000 randomized operations.

### NFR-003 — Untrusted-content and data-egress security

Retrieved content and model output are untrusted. Content cannot override
system policy, choose tools, reveal secrets, or cause consequential actions.
The attack suite permits zero secret, unauthorized-action, or cross-workspace
compromises. Remote inference egress must be disclosed and bounded.

### NFR-004 — Durability, idempotency, and recovery

Accepted outcomes, memory changes, and source revisions survive process and
container restarts. Duplicate requests and stream replay do not duplicate
effects. PostgreSQL jobs recover expired leases, and Qdrant can be reconciled
from canonical state.

### NFR-005 — Interactive performance

At five concurrent demo users on the reference deployment, first useful UI
shall be at or below four seconds p95 and a completed recommendation at or below
fifteen seconds p95. Non-model API reads shall be at or below 300 ms p95.

### NFR-006 — Cost containment

The p95 inference cost shall not exceed USD 0.05 per decision turn, and the
canonical two-decision journey shall not exceed USD 0.15. The system stops new
generations before its configured daily spend ceiling.

### NFR-007 — Accessible controlled UI

Core journeys shall meet WCAG 2.2 AA, support keyboard-only use, honor reduced
motion, retain visible focus, announce streamed state changes appropriately,
and contain zero serious or critical automated accessibility violations.
One hundred percent of UI envelopes must validate.

### NFR-008 — Privacy-preserving observability

Metrics and OpenTelemetry traces shall include scoped identifiers, versions,
durations, token counts, costs, result states, and hashes. Raw private passages,
credentials, and full prompts are excluded by default. Redaction failures block
release.

### NFR-009 — Reproducible portable operation

A clean clone shall start the seeded system through its documented Docker
Compose workflow on macOS and Linux. Release manifests pin code, schema,
provider/model, prompt, retriever, reranker, and dataset versions. External
service dependencies have health and readiness checks.

### NFR-010 — Data lifecycle and deletion

Public guest overlays expire within 24 hours. A local deletion request removes
active relational, vector, and blob references within 60 seconds and produces
an auditable completion record without retaining deleted content.

### NFR-011 — Versioned contract compatibility

OpenAPI, UI envelope, event, export, and durable schema changes are versioned.
Pydantic is canonical; generated TypeScript and runtime validators must match in
CI. Breaking persisted-state changes require forward migration, tested
rollback or restore, and documented compatibility behavior.

### NFR-012 — License-safe provenance and supply chain

Public fixtures and shipped assets must have recorded origin and redistribution
rights. Course lab assets and unclear-license content are excluded. Dependencies
are pinned, scanned, and attributable; secrets and private repository locations
are absent from committed artifacts.

## Canonical user journeys

### Journey A — Public portfolio demonstration

The visitor enters a ready synthetic workspace, reviews the source manifest,
opens a preframed architecture decision, adjusts a criterion, runs the
comparison, inspects evidence and constraints, edits and accepts the result,
confirms the resulting memory, opens the related decision, inspects “why
changed,” and exports the ADR.

### Journey B — Local evidence workspace

The user selects local-data mode, reads the remote-inference disclosure,
configures an allowlisted repository and optional GitHub token, watches
resumable ingestion, frames a decision, reviews cited private and public
evidence, accepts an outcome, and later deletes a source and confirms index
reconciliation.

### Journey C — Honest abstention

The user frames a decision whose required residency constraint is unsupported
by available evidence. The system marks the constraint unknown, does not
recommend an option, identifies the missing evidence, and permits a new run
after the user supplies it or explicitly revises the frame.

## Global state and failure behavior

- Empty workspaces explain what sources and decisions are needed.
- Loading states expose meaningful progress without fabricating completion.
- A provider timeout preserves the frame and retrieved evidence and offers a
  safe retry with the same idempotency scope.
- A stale client receives conflict information and must refresh before
  mutating.
- Qdrant unavailability makes retrieval-dependent runs unavailable but does not
  make canonical decisions or exports unreadable.
- A worker restart resumes leased jobs after expiry.
- A partially streamed run is marked interrupted until replay or a new run.
- Unsupported model output fails schema validation and allows at most one
  bounded repair attempt.

## Epic mapping

| Epic | Primary requirements |
|---|---|
| EPIC-001 — Walking skeleton | FR-001, FR-003, FR-006, FR-011 |
| EPIC-002 — Grounded decisions | FR-002, FR-004, FR-005 |
| EPIC-003 — Outcome-to-memory loop | FR-007, FR-008, FR-009, FR-012 |
| EPIC-004 — Local-data connectors | FR-002, FR-010 |
| EPIC-005 — Portfolio experience | FR-006, FR-011, FR-012 |
| EPIC-006 — Public OSS release | all requirements and NFRs |

## Release boundary

Version one is accepted only when EPIC-001 through EPIC-006 meet their outcomes,
all blocking quality gates pass on the pinned release corpus, the two-decision
journey works in a clean deployment, local-data deletion is verified, and
documentation traces visible behavior to requirements, features, tests, and
evaluations.
