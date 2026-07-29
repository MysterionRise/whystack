---
artifact: epics
baseline: IB-001
status: accepted
date: 2026-07-27
---

# Delivery Epics

## Sequencing rule

Epics express product outcomes and dependencies. Spec Kit decomposes each epic
into independently testable vertical features and is the only authority for
implementation tasks. A later epic may begin only when its required predecessor
contracts are accepted and stable enough to consume.

## EPIC-001 — Walking skeleton

### Outcome

A clean deployment can create a public-demo guest workspace, persist a
versioned decision and run, execute a deterministic fake-model workflow, stream
one validated controlled recommendation component, reconnect and replay its
events, and expose truthful readiness.

### Requirements

FR-001, FR-003, FR-006, and the seeded workspace boundary of FR-011.

### Quality coverage

NFR-002, NFR-004, NFR-007, NFR-008, NFR-009, and NFR-011. Initial gates:
QUALITY-UI-001, QUALITY-PERF-001, and relevant portions of QUALITY-SEC-001 and
QUALITY-OPS-001.

### Required product behavior

- Common Docker Compose topology for web, API, worker, PostgreSQL, and Qdrant.
- Next.js/CopilotKit BFF with no provider key or domain persistence.
- FastAPI/Pydantic canonical schemas and generated TypeScript contracts.
- Server-derived signed guest workspace and mode capability response.
- Versioned decision frame and optimistic concurrency.
- Explicit fixture-only LangGraph stages using deterministic output.
- Persisted run snapshot and semantic event stream with cursor replay.
- Reviewed UI-envelope component and action registries that reject unknowns.
- Public-demo denial of uploads and live connectors.
- Redacted trace correlation and live/ready health endpoints.

### Acceptance outcome

From a clean clone, one command starts the stack; the browser can create the
fixture run, render the controlled component, reconnect from a cursor, and see
the same terminal result without duplicate state. Contract drift,
cross-workspace access, schema-invalid UI, replay duplication, or secret
exposure fails the epic.

### Exclusions

Real provider calls, hybrid retrieval, model-generated recommendations, live
connectors, long-term memory, recommendation scoring, and ADR export.

## EPIC-002 — Grounded decisions

### Outcome

A user can frame a decision against the seeded corpus, retrieve and inspect
scoped evidence, compare alternatives with typed constraint results, receive a
deterministically selected recommendation, close call, or abstention.

### Requirements

FR-002, FR-004, FR-005, and evidence portions of FR-012.

### Dependencies

EPIC-001 contracts, run replay, workspace policy, and canonical storage.

### Quality coverage

NFR-001, NFR-002, NFR-003, NFR-004, NFR-005, NFR-006, NFR-008, NFR-009,
NFR-011, and NFR-012. Gates: QUALITY-RET-001, QUALITY-RET-002,
QUALITY-GRD-001, QUALITY-REC-001, QUALITY-SEC-001, QUALITY-PERF-001,
QUALITY-COST-001, and relevant QUALITY-OPS-001.

### Required product behavior

- Original seed artifacts become immutable source revisions.
- PostgreSQL full-text and Qdrant dense retrieval follow the bounded fusion,
  reranking, diversity, and citation policy.
- Model output supplies only schema-valid cited assessments.
- Deterministic code handles hard constraints, coverage, weights, scores, and
  result type.
- Evidence inspector resolves exact revisions and locators.
- Run fingerprints record code, provider/model, prompt, schema, retrieval,
  reranker, and evaluation dataset versions.

### Acceptance outcome

All seeded decision cases produce expected evidence and result types, every
citation resolves, no failed/unknown hard constraint is recommended, and
retrieval, groundedness, recommendation, security, performance, and cost gates
pass on the pinned corpus.

### Exclusions

The durable outcome ledger, accepted-decision export, personalization from
outcomes, and real user connectors.

## EPIC-003 — Outcome-to-memory loop

### Outcome

An explicit decision outcome produces traceable durable facts; inferred
preferences remain proposals until confirmed; a later decision can use relevant
memory and explain its exact ranking effect; the user can export the accepted
outcome as an ADR and JSON bundle and can correct, supersede, or delete memory.

### Requirements

FR-007, FR-008, FR-009, memory and delta portions of FR-012, and the
second-decision portion of FR-011.

### Dependencies

EPIC-002’s canonical recommendations, deterministic scoring, citations, and
run fingerprints.

### Quality coverage

NFR-002, NFR-003, NFR-004, NFR-007, NFR-008, NFR-010, and NFR-011. Gates:
QUALITY-MEM-001, QUALITY-UI-001, QUALITY-SEC-001, and QUALITY-OPS-001.

### Required product behavior

- Append-only outcome events for accept, edit-and-accept, dismiss, revisit, and
  supersede.
- Active explicit facts and inactive inferred proposals with provenance.
- Confirmation, rejection, correction, supersession, and deletion commands.
- Priority and section-budgeted memory context with conflict handling.
- Run-level memory usage and calculated score-delta records.
- `MemoryInfluence` and `DecisionDelta` controlled components.
- The original public corpus’s connected second decision.
- Markdown ADR and JSON exports generated from the canonical accepted outcome,
  recommendation, citations, memory influence, and version fingerprints.

### Acceptance outcome

The canonical two-decision journey exposes why a relevant accepted fact changed
or did not change the later ranking. No inactive proposal affects a run,
unrelated memory remains stable, correction takes effect, and deletion clears
active canonical and derived references within the lifecycle gate. The accepted
decision exports as a safe, attributable Markdown ADR and round-trippable JSON
bundle from canonical state.

### Exclusions

Automatic activation of inferred preferences, opaque vector-only memory, and
cross-user personalization.

## EPIC-004 — Local-data connectors

### Outcome

A local operator can disclose egress, configure approved read-only sources,
observe resumable incremental synchronization, use their evidence in decisions,
and disconnect or wipe it safely.

### Requirements

FR-002 and FR-010, with local-mode policy from FR-001.

### Dependencies

EPIC-002 source/retrieval contracts and EPIC-003 deletion semantics.

### Quality coverage

NFR-002, NFR-003, NFR-004, NFR-008, NFR-009, NFR-010, NFR-011, and NFR-012.
Gates: QUALITY-RET-001, QUALITY-GRD-001, QUALITY-SEC-001, and
QUALITY-OPS-001.

### Required product behavior

- Egress disclosure and explicit connector activation.
- Allowlisted local Git file and supported upload ingestion.
- Read-only GitHub repository, issue, and pull-request ingestion.
- Bounded public web fetch with redirect and private-network protection.
- Durable leased jobs, cursors, retry, dead-letter visibility, tombstones, and
  index reconciliation.
- Connector disconnect and source wipe with completion evidence.

### Acceptance outcome

Each connector passes its contract, failure, injection, path/URL, resumption,
incremental revision, tombstone, and deletion suites. No connector can write to
an external system, execute retrieved material, escape scope, or leak a
credential.

### Exclusions

Writable tools, arbitrary browser automation, repository checkout, hook or
script execution, archive expansion, and hosted visitor ingestion.

## EPIC-005 — Portfolio experience

### Outcome

The complete product communicates its system boundaries and quality visibly,
works across supported viewports and assistive technology, and guides a visitor
through the two-decision story without facilitation.

### Requirements

FR-006, FR-011, and FR-012.

### Dependencies

EPIC-001 through EPIC-004 product flows.

### Quality coverage

NFR-005, NFR-007, NFR-008, and NFR-009. Gates: QUALITY-UI-001,
QUALITY-PERF-001, QUALITY-COST-001, and applicable QUALITY-MEM-001.

### Required product behavior

- Responsive decision workspace and evidence inspector.
- Complete approved component catalog and all lifecycle/error states.
- Guided synthetic project introduction and optional tour.
- Memory ledger, why-changed view, source provenance, evaluation view, and
  technical version details.
- Keyboard, screen-reader, reduced-motion, contrast, zoom, and responsive
  acceptance.
- Architecture and evaluation documentation, screenshots, and repeatable demo
  script.

### Acceptance outcome

At least four of five moderated target users complete both decisions, identify
evidence and a hard constraint, explain memory influence, correct or delete
memory, identify the inference-egress boundary, and export the ADR without
facilitator correction. Automated accessibility has zero serious or critical
violations and manual supported-path review passes.

### Exclusions

Unbounded theme customization, arbitrary dashboards, mobile-native clients, and
collaborative editing.

## EPIC-006 — Public OSS release

### Outcome

The project can be cloned, validated, deployed publicly within its abuse and
cost envelope, operated through documented recovery procedures, and evaluated
against an attributable release manifest.

### Requirements

All FRs and NFRs.

### Dependencies

EPIC-001 through EPIC-005.

### Quality coverage

Every `QUALITY-*` gate.

### Required product behavior

- CI for contracts, unit, property, integration, browser, accessibility,
  security, secret/dependency/container scanning, deterministic fake-model
  evaluation, and protected live-provider evaluation.
- Caddy/TLS single-VM profile, health/readiness, backup/restore, retention,
  reconciliation, spend stop, and incident runbooks.
- Public rate, turn, concurrency, input, context, step, timeout, and daily-spend
  enforcement.
- MIT license, provenance manifest, security policy, contribution guide,
  architecture explanation, evaluation results, and tagged release.
- Clean-room clone and seeded-journey verification on macOS and Linux.

### Acceptance outcome

The release corpus, attack corpus, operations suite, clean deployment, canonical
user journey, provenance scan, and full traceability check pass. A release
manifest ties the tag to exact code, contract, model, prompt, retrieval,
reranker, and dataset versions.

### Exclusions

Enterprise service-level agreements, multi-region deployment, compliance
certification, paid multi-tenant service, and production support guarantees.

## Cross-epic release criteria

- No severity-P0 risk is open.
- No requirement lacks a feature, acceptance scenario, task, and test/evaluation
  path.
- All blocking quality gates pass without lowering an accepted threshold.
- Public-demo and local-data capability boundaries are independently tested.
- The canonical two-decision journey and honest-abstention journey pass.
- Every shipped source, fixture, asset, model, and dependency has recorded
  provenance.
