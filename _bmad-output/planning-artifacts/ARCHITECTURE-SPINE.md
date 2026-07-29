---
artifact: architecture-spine
baseline: IB-001
status: accepted
date: 2026-07-27
---

# Architecture Spine

## Architectural objective

Support a replayable, evidence-backed decision workflow in which canonical
state, derived retrieval state, model judgment, deterministic policy, user
authority, and UI rendering are visibly separated. The architecture optimizes
for inspectability and a credible single-VM public portfolio deployment without
blocking later managed-service migration.

## Decision summary

| Decision | Selected approach | Reason |
|---|---|---|
| Product topology | TypeScript web plus Python API/worker | Best fit for controlled Generative UI and the repository’s AI workflow assets |
| UI | Next.js, React, CopilotKit, AG-UI | React retains authority while the agent streams typed decision components |
| API and contracts | FastAPI and Pydantic v2 | Typed Python boundary and generated OpenAPI/JSON Schema |
| Workflow | Explicit LangGraph state graph | Inspectable stages, checkpoints, and bounded model calls |
| Canonical store | PostgreSQL | Transactions, revisions, event ledger, jobs, full-text search, and audit state |
| Vector index | Qdrant | Filtered dense retrieval with rebuildable payloads |
| Durable work | PostgreSQL leased job/outbox tables | Avoids an additional Redis dependency in version one |
| Model access | OpenRouter-compatible adapter | Provider/model flexibility behind one server-side interface |
| Deployment | Docker Compose on local machines and one Linux VM | Reproducible portfolio operation with a straightforward migration path |
| UI generation | Versioned controlled component envelopes | Prevents arbitrary executable model output |
| Memory | Event-derived typed facts and inactive proposals | Makes provenance, confirmation, correction, and deletion enforceable |

## System context

### Actors

- **Public visitor:** uses a signed guest workspace and fixed synthetic corpus.
- **Local operator:** controls a single-user local-data deployment, provider
  credentials, connectors, retention, and wipe actions.
- **Remote inference provider:** receives only the bounded context selected for
  a run.
- **GitHub:** supplies read-only repository, issue, and pull-request evidence in
  local-data mode.
- **Public web sources:** supply allowlisted HTTP content through a bounded safe
  fetcher.

### Trust boundaries

1. Browser input crosses into the web BFF and API.
2. Connector content crosses from untrusted repositories, files, GitHub, and
   the web into normalization.
3. Selected evidence crosses from local services to the remote model provider.
4. Model output crosses back into strict schema validation.
5. UI envelopes cross from the API stream into a reviewed React renderer.
6. Derived vectors cross from PostgreSQL-owned source revisions into Qdrant.

No model output is trusted with workspace identity, authorization, persistence,
scoring, connector selection, or UI action authority.

## Containers and responsibilities

### Web application

The Next.js application owns routing, responsive layout, forms, stateful client
interaction, accessibility semantics, and the reviewed component catalog. Its
server-side BFF owns secure session cookies, same-origin API access, AG-UI
adaptation, and omission of provider credentials from the browser.

It does not own domain persistence, recommendation policy, memory activation,
or connector execution.

### API service

FastAPI owns:

- mode and capability enforcement;
- signed/authenticated workspace derivation;
- REST resources and mutation concurrency;
- Pydantic domain validation and canonical schemas;
- run creation, status, and event replay;
- LangGraph invocation;
- deterministic constraint, coverage, and score policy;
- citation validation;
- outcome and memory commands;
- export generation;
- health and readiness.

The API can serve canonical reads when Qdrant is unavailable. Retrieval-dependent
new runs require a ready index.

### Decision workflow

LangGraph expresses these named stages:

1. validate and snapshot frame;
2. assemble prioritized memory context;
3. create bounded search queries;
4. retrieve full-text and dense candidates;
5. fuse, rerank, and diversify evidence;
6. generate or normalize candidate options;
7. evaluate typed hard constraints;
8. obtain cited criterion assessments;
9. validate citations and perform at most one repair;
10. calculate evidence coverage and deterministic weighted scores;
11. select recommendation, close call, or abstention;
12. produce controlled UI envelopes;
13. persist immutable completion and version fingerprints.

Every stage emits a persisted semantic event. A run has explicit pending,
running, completed, abstained, interrupted, or failed state. LangGraph state is
not the source of truth for accepted outcomes.

### Worker

The Python worker leases PostgreSQL jobs for:

- source scan, fetch, normalize, and revision creation;
- text segmentation and embedding;
- Qdrant upsert, tombstone, and reconciliation;
- memory proposal derivation;
- deletion and retention processing;
- scheduled demo-overlay expiry.

A job has kind, workspace, payload reference, cursor, attempt count, available
time, lease owner/expiry, terminal state, and redacted failure category.
Effects are idempotent. Expired leases are reclaimable. Irrecoverable jobs move
to a visible dead-letter state.

### PostgreSQL

PostgreSQL is authoritative for:

- deployment/workspace state;
- logical sources and immutable source revisions;
- normalized citation text and locators;
- decision frames and revisions;
- run snapshots, events, recommendation results, and version fingerprints;
- outcome event ledger;
- memory facts, proposals, supersession, and usage;
- connector configuration metadata and sync cursors;
- durable jobs and outbox;
- evaluation manifests;
- deletion audit state.

All workspace-owned tables include `workspace_id`. Database constraints enforce
revision uniqueness, idempotency, valid state transitions, and referential
integrity. Application queries always include workspace scope; randomized
isolation tests exercise every access path.

### Raw blob storage

Raw local uploads use a content-addressed filesystem volume behind a blob-store
interface. Metadata and normalized citation text remain in PostgreSQL. Public
seed assets are read-only packaged files with a provenance manifest. Blob paths
are generated from checksums, never user filenames. The interface permits a
future S3-compatible adapter without changing domain contracts; object storage
is not a version-one deployment dependency.

### Qdrant

Qdrant contains chunk vectors and minimal filter payload:

- workspace ID;
- source artifact and revision IDs;
- chunk ID;
- active/deleted state;
- source kind and observed date;
- embedding version.

Canonical text and access decisions do not depend on Qdrant. Index rows are
version-fingerprinted and fully reconstructable from PostgreSQL and the blob
store.

## Canonical domain model

All identifiers are opaque UUIDv7 values generated by the server. Timestamps
are UTC. Mutable resources carry an integer revision used for optimistic
concurrency.

### Evidence domain

- `Workspace`: profile, capability policy, retention state, expiry.
- `SourceArtifact`: stable logical origin, source kind, display metadata,
  connector, scope, active state.
- `SourceRevision`: checksum, observed time, parser and schema versions, raw blob
  reference, normalized text, locator map, active/deleted state.
- `SourceChunk`: stable locator within a revision, text span, token count,
  embedding version and index state.
- `EvidenceRef`: run-scoped reference to revision and chunk/locator, excerpt,
  freshness, retrieval and rerank scores.

### Decision domain

- `Decision`: logical decision identity, workspace, lifecycle state.
- `DecisionRevision`: question, context, alternatives, criteria, constraints,
  advisory guidance, parent revision and creation actor.
- `Criterion`: label, rationale, entered weight, normalized weight.
- `Constraint`: a discriminated value for budget, deadline, capability,
  forbidden vendor, license, residency, or deployment mode.
- `RunSnapshot`: decision revision, context snapshot, run state, event cursor,
  timestamps, result, and version fingerprints.
- `OptionAssessment`: constraint outcomes and cited criterion assessments.
- `Recommendation`: recommendation, close call, or abstention; score table,
  coverage, claims, risks, unknowns, and citations.
- `DecisionEvent`: idempotent accept, edit-and-accept, dismiss, revisit, or
  supersede event.

### Memory domain

- `MemoryFact`: typed value, category, provenance event, active interval,
  explicit or confirmed-inference origin, supersession, deletion state.
- `MemoryProposal`: candidate typed value, inference rationale and source
  events, inactive status, confirmation/rejection state.
- `MemoryUsage`: run, fact, priority, context position, affected option or
  criterion, and calculated score delta.

### Delivery and audit domain

- `RunEvent`: ordered semantic stream event with schema version and cursor.
- `IdempotencyRecord`: workspace, operation, key, request hash, result reference
  and expiry.
- `Job`: durable leased worker operation.
- `EvaluationManifest`: code, model, prompt, retriever, reranker, schema, dataset,
  metrics, latency, cost and decision.
- `DeletionRecord`: request scope, stages, completion time and non-sensitive
  integrity evidence.

## API boundary

The public version-one API is namespaced under `/api/v1`.

### Resource groups

- `GET /config` returns profile and enabled capabilities.
- `/decisions` manages logical decisions and immutable revisions.
- `/decisions/{decision_id}/runs` creates and lists runs.
- `/runs/{run_id}` reads a snapshot.
- `/runs/{run_id}/events` streams or replays ordered AG-UI-compatible events
  from a cursor.
- `/decisions/{decision_id}/outcomes` records explicit outcomes.
- `/evidence/{evidence_id}` resolves an authorized citation.
- `/memory/facts` and `/memory/proposals` inspect and command memory.
- `/sources` manages permitted source configuration and canonical state.
- `/sources/{source_id}/sync-jobs` starts and observes sync.
- `/decisions/{decision_id}/exports` returns Markdown ADR or JSON.
- `/evaluations` exposes safe release and run metadata.
- `/health/live` reports process liveness.
- `/health/ready` reports migrations, canonical store, mode configuration,
  worker lease health, and Qdrant index fingerprint.

The walking skeleton implements only the minimum groups declared in its active
feature; later epics add the remaining groups without renaming them.

### Mutation protocol

Every mutation:

- derives workspace and actor from server context;
- requires an idempotency key;
- requires `expected_revision` for an existing mutable aggregate;
- validates request and capability before work;
- writes domain state and outbox event in one transaction;
- returns the current resource revision;
- returns `409` with current revision metadata for a stale write;
- returns the stored result for an identical replay and a conflict for reuse
  with a different request hash.

### Streaming protocol

Runs stream semantic events rather than raw tokens. Each event has run ID,
strictly increasing cursor, type, schema version, timestamp, and validated
payload. The server persists an event before delivery. A reconnect supplies the
last acknowledged cursor and receives later events. Terminal state is
idempotent. Retention preserves events for at least the life of the associated
run.

## Contract ownership

Pydantic models are canonical. Their OpenAPI and JSON Schemas generate
TypeScript request/response types and UI-envelope validators. CI compares
generated artifacts with committed contracts and rejects drift.

Contracts use explicit version fields for UI envelopes, run events, exports,
and evaluation manifests. Additive optional fields are permitted within a
version. Removing, renaming, narrowing, or changing meaning requires a new
version and compatibility/migration policy.

## Retrieval architecture

### Initial local baseline

- Dense embedding model: `BAAI/bge-small-en-v1.5`.
- Cross-encoder reranker: `cross-encoder/ms-marco-MiniLM-L-6-v2`.
- PostgreSQL full-text and Qdrant dense searches each return at most forty
  scoped candidates.
- Reciprocal-rank fusion uses rank constant sixty.
- The reranker scores at most thirty fused candidates.
- Diversity limits a final evidence set to no more than three units per logical
  source and twelve units total.

Exact model revisions, preprocessing, dimensions, chunk strategy, and query
prompts are pinned in the implementation release manifest. A replacement must
beat the accepted baseline on both retrieval gates without regressing security,
latency, or cost.

### Retrieval invariants

- Filtering by workspace and active revision precedes result use.
- Retrieved text is data, never instruction.
- Citation locators resolve against canonical normalized content.
- Freshness is visible and can be a criterion but does not silently override
  relevance.
- Search queries, candidate identifiers, fusion ranks, rerank scores, and final
  evidence IDs are recorded for evaluation.

## Recommendation policy

Each criterion is assessed on a zero-to-one-hundred scale with cited reasoning.
The application multiplies the assessment by the normalized user weight and
sums the results. The model cannot supply the final weighted score.

Evidence coverage is the sum of criterion weights supported by at least one
validated citation divided by the total criterion weight. A viable
recommendation requires:

- no hard constraint in fail or unknown state;
- weighted evidence coverage of at least 70%;
- a leading score at least five points above the next viable option;
- successfully validated citations.

If viable options fall within five points, the result is a close call. If no
option is viable, a hard constraint is unknown, coverage is below threshold, or
citation validation fails after one repair, the result abstains. Risks and
missing evidence remain visible for every result type.

## Memory architecture

The append-only outcome ledger is the source for durable memory. Explicit
accepted facts can become active in the same transaction as their event.
Generalized or inferred preferences enter an inactive proposal queue.

A memory context assembler:

1. filters by workspace, active state, validity interval, and decision
   relevance;
2. detects conflicts;
3. orders current frame, typed constraints, recent outcomes, explicit
   preferences, confirmed inferred preferences, and older history;
4. enforces per-section token budgets;
5. records included and excluded identifiers with reasons.

The scoring service records any memory-derived criterion or option adjustment
as `MemoryUsage`. The UI can therefore explain both inclusion and numerical
effect. Correction creates a superseding fact. Deletion invalidates future use,
removes derived vectors, and completes within the lifecycle gate.

## Connector boundary

Each connector implements three conceptual operations:

- scan from a durable cursor and return source references;
- fetch one authorized reference as bytes plus origin metadata;
- normalize it into a revision candidate and locators.

Connectors cannot call model tools or persist domain state directly. The worker
validates size, type, path, URL, checksum, scope, and mode before accepting a
revision.

Local Git ingestion reads allowlisted files from a user-selected root without
checkout, hook execution, submodule execution, archive expansion, or path
escape. GitHub uses read-only tokens and explicit repository allowlists. Web
fetching permits HTTPS public destinations only, resolves and checks every
redirect, rejects any redirect that changes to a non-HTTPS scheme, blocks
loopback/link-local/private ranges, limits bytes and time, and stores the final
URL and observed time.

## Deployment profiles

### Common Compose topology

The web, API, worker, PostgreSQL, and Qdrant run as separate containers on an
internal network. Only the web entrypoint is public by default. Caddy terminates
TLS for the single-VM public deployment. Persistent volumes hold PostgreSQL,
Qdrant, and local blobs.

### Public demo

- Seed sources are read-only and shared.
- User decisions, outcomes, and memory reside in an isolated guest overlay.
- The BFF sets an HTTP-only, secure, same-site signed session cookie.
- The API derives a random guest workspace from the verified session.
- A keyed hash of IP address supports abuse throttling and is retained no
  longer than the guest overlay.
- Background expiry removes overlays after 24 hours.
- Server policy limits five requests per minute, fifty turns per day, two
  concurrent runs, context size, model calls, and daily spend.

### Local data

The stack binds to loopback by default and has one operator. Remote access
requires the documented TLS reverse-proxy profile and a separately configured
authentication boundary. Connector and provider keys enter server-side
environment or secret mounts. Public-demo quotas are optional, but context,
step, timeout, and cost guards remain active.

## Security architecture

- Validate browser and connector input before canonical writes.
- Parameterize database queries and escape export content.
- Derive all access scope server-side and filter canonical plus vector reads.
- Keep provider and connector credentials out of browser bundles and model
  context.
- Separate system instructions, structured context, and untrusted source text.
- Permit no consequential tools or writable connectors in version one.
- Validate every model response against a strict schema with unknown fields
  rejected.
- Map UI actions from a reviewed registry; the envelope carries an action
  identifier, not a route or command.
- Apply URL parsing, DNS resolution checks, redirect checks, response-size
  bounds, MIME validation, and timeouts to web fetching.
- Redact secrets and source passages before logs and traces leave the service.
- Scan dependencies, containers, commits, fixtures, and generated artifacts in
  CI.

## Observability

OpenTelemetry spans correlate HTTP request, run, workflow stages, model calls,
retrieval, reranking, canonical writes, jobs, and stream delivery. Safe fields
include opaque IDs, versions, counts, durations, token use, cost, result state,
coverage, and hashes.

Raw private passages, connector credentials, provider keys, full prompts, and
model responses are excluded by default. A local operator may enable short-lived
debug capture only through an explicit setting that shows scope and retention;
public demo never enables it.

Dashboards track readiness, run outcomes, abstention reasons, citation failures,
retrieval latency, provider latency/error, replay, job leases, index lag, token
use, estimated spend, deletion completion, and quality-manifest status.

## Failure and recovery

- PostgreSQL failure makes the API unready and prevents mutation.
- Qdrant failure disables new retrieval runs but preserves canonical reads,
  outcomes, memory inspection, and exports.
- Provider failure preserves the frame and evidence snapshot and marks the run
  failed or interrupted without a recommendation.
- Worker failure leaves jobs recoverable after lease expiry.
- Stream disconnect replays from the last cursor.
- Schema-invalid model output gets one bounded repair, then fails closed.
- A migration failure prevents readiness; database backup/restore is the
  version-one rollback boundary for irreversible data changes.
- Index fingerprint mismatch triggers reconciliation before retrieval readiness.

## Migration and evolution

Alembic owns PostgreSQL migrations. Each durable change states forward
migration, rollback or restore behavior, expected duration, and compatibility
window. Workers and API tolerate one prior additive schema version during a
rolling restart; breaking migrations require a maintenance window in the
single-VM profile.

Qdrant collection names include embedding generation. Re-embedding writes a new
generation, verifies completeness and evaluation quality, switches an atomic
active-generation reference in PostgreSQL, then retires the old collection.

## Rejected architectural alternatives

- **Next.js-only TypeScript backend:** rejected because the project’s strongest
  reusable memory, retrieval, evaluation, and LangGraph assets are Python-based.
- **Chainlit or Gradio UI:** rejected because the flagship requires a
  portfolio-grade controlled component system and deliberate responsive UX.
- **Redis/Celery for jobs:** rejected for version one because PostgreSQL leases
  meet the expected workload and reduce operational surface.
- **pgvector as the only search store:** viable but rejected initially to
  demonstrate an explicit rebuildable vector boundary and Qdrant filtering
  patterns already represented in the learning repository.
- **Free-form generated HTML:** rejected because it weakens accessibility,
  authorization, testing, and content-security guarantees.
- **Model-authored final scores:** rejected because constraints and ranking must
  be reproducible and stable.
- **Automatic inferred memory:** rejected because personalization must remain
  inspectable and user-governed.
- **Hosted ingestion of private visitor data:** rejected from the public demo to
  avoid an account, retention, and abuse surface that does not strengthen the
  portfolio thesis.
