# AI CTO Cockpit Constitution

Version: 1.0.0  
Ratified: 2026-07-27  
Inception baseline: IB-001  
Status: Binding

## Purpose and authority

This constitution governs implementation of AI CTO Cockpit after the BMAD
inception baseline has passed readiness review. BMAD owns product intent, user
experience, cross-cutting architecture, epics, and portfolio-level quality
strategy. Spec Kit owns feature clarification, implementation planning, tasks,
delivery, and convergence.

When implementation exposes a product, experience, or cross-cutting
architecture conflict, the feature stops. The team records a change request in
`docs/changes/`, updates the BMAD artifacts, issues a new hashed inception
baseline, and then replans the affected Spec Kit feature. A feature specification
may refine an accepted baseline but may not silently override it.

## Article I — Evidence is inspectable

Every externally verifiable claim in a recommendation must reference authorized
evidence captured as an immutable source revision. A citation must preserve its
source identifier, exact locator, excerpt, and retrieval metadata. Missing,
stale, contradictory, or insufficient evidence must remain visible to the user.
The product abstains rather than fabricating a locator or presenting unsupported
certainty.

Implications:

- Postgres is the canonical store for source text, source revisions, decisions,
  run snapshots, outcomes, memory, and citation records.
- Qdrant is a derived, workspace-scoped index that can be rebuilt from canonical
  records.
- Release evaluation must fail on any fabricated or unresolved citation.

## Article II — Models propose; deterministic code decides

Model output is untrusted input. Pydantic validates every model-produced
structure. Deterministic application code enforces authorization, workspace
scope, typed hard constraints, revision checks, idempotency, and final weighted
scores. A model must never select a workspace, relax a hard constraint, execute
an unapproved action, or directly commit a durable outcome.

The implementation must return an explicit abstention or typed failure whenever
a required invariant cannot be established.

## Article III — Interfaces are typed and versioned

Pydantic models are the canonical application contracts. OpenAPI and JSON Schema
are generated or checked from the same semantic definitions; TypeScript clients
and frontend validators must match them in continuous integration.

Public contracts use explicit version fields and discriminated unions. Changes
that remove or reinterpret an existing field require a migration plan and a
deliberate contract-version change. Unknown Generative UI component kinds,
actions, schema versions, and payload fields fail closed.

## Article IV — The user owns durable decisions and memory

Only an explicit user action may accept, edit, dismiss, revisit, or supersede a
recommendation. Accepted decisions and explicitly supplied preferences may
become active memory facts. Inferred preferences remain inactive proposals until
the user confirms them.

Every memory fact carries provenance, validity state, supersession history, and
deletion state. The interface must reveal which memory facts influenced a
recommendation and allow correction or deletion. Context precedence is:

1. current decision frame;
2. typed hard constraints;
3. recent accepted outcomes;
4. explicit preferences;
5. confirmed inferred preferences;
6. older relevant history.

## Article V — Presentation authority stays in the product

React owns layout, navigation, accessibility, action semantics, and the approved
component catalog. The model may populate versioned component payloads but must
not emit arbitrary HTML, JavaScript, routes, executable styles, or action
handlers. All consequential actions require a visible user control and
server-side authorization.

Every component state must define loading, empty, partial-evidence, abstention,
error, reconnect, and completed behavior. Keyboard and screen-reader operation
are release requirements rather than optional polish.

## Article VI — Privacy and workspace scope are server-derived

Every durable record, job, event, and vector payload carries `workspace_id`.
Workspace scope is derived from trusted server context and is never accepted
from model output. Retrieval, replay, export, deletion, and background jobs must
enforce the same scope.

The public demo permits only the bundled synthetic corpus and an expiring guest
overlay. Uploads and live connectors are denied. Local-data mode permits
persistent local sources, but OpenRouter inference can transmit selected context
off-device; the product must disclose that boundary before enabling a provider.
Secrets and raw private passages are excluded from logs and traces.

## Article VII — Tests and evaluations precede production behavior

Each behavior change starts with a failing automated test or a failing,
versioned evaluation case. Feature work uses the sequence:

`specify → clarify → checklist → plan → tasks → analyze → failing tests → bounded implementation → deterministic tests → targeted AI evaluations → converge → human review`

Unit and integration tests cover deterministic behavior. Evaluation datasets
cover retrieval, grounding, recommendation quality, memory, Generative UI,
security, performance, cost, and durability. A model, prompt, retriever, schema,
or dataset change must record its version in the release manifest and must pass
the applicable regression gates.

## Article VIII — Runs are durable, replayable, and observable

Every decision run has a stable identifier, immutable input snapshot, ordered
event sequence, terminal status, and version fingerprints. Mutations require an
idempotency key and expected revision. Duplicate requests produce the original
result; stale revisions return a conflict.

The system emits structured, redacted traces and metrics for run state,
retrieval, model usage, latency, token cost, background jobs, and index lag.
Readiness checks distinguish process liveness from dependency readiness.
Interrupted streams can resume from the last acknowledged event without
repeating committed effects.

## Article IX — Performance and spend are product constraints

Feature plans must state latency, token, and spend budgets for affected paths.
The canonical target is first useful UI at p95 within four seconds and a
completed recommendation at p95 within fifteen seconds under the documented
five-user demo load. The canonical cost ceiling is USD 0.05 per ordinary turn
and USD 0.15 for the complete two-decision demonstration.

Rate limits, concurrency limits, input bounds, agent-step bounds, and a daily
spend circuit breaker are mandatory before public deployment.

## Article X — Delivery remains reproducible and portable

The supported baseline is Python 3.12, a Node.js active LTS release, Docker
Compose, Postgres, and Qdrant. Exact dependencies and model identifiers are
locked before implementation and changed in isolated maintenance work.

The repository must build and validate without access to the originating course
repository. Synthetic fixtures must be original and license-safe. Secrets,
credentials, private URLs, absolute developer paths, copied course labs, and
unapproved binary assets are prohibited.

## Feature evidence required for convergence

A feature may converge only when:

- all requirement and quality identifiers resolve to the accepted baseline;
- clarification contains no unresolved decision;
- contracts and migrations match runtime behavior;
- acceptance tests and targeted evaluations pass;
- security and privacy boundaries are exercised by negative tests;
- operational budgets have measured evidence or an approved baseline waiver;
- documentation explains user-visible behavior and failure modes;
- traceability reaches from baseline requirement to acceptance scenario, task,
  and verification evidence.

## Governance

Amendments require:

1. a written rationale and affected baseline identifiers;
2. review for product, architecture, security, data, and evaluation impact;
3. a migration statement for active features and stored data;
4. a version increment under semantic versioning;
5. updated hashes in the active inception baseline.

Editorial clarification increments the patch version. New or materially expanded
principles increment the minor version. A backward-incompatible change to
authority, privacy, or governance increments the major version.
