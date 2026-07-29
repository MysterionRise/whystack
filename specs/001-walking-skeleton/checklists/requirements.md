# Requirements Checklist: Walking Skeleton

Reviewed against inception baseline `IB-001` and constitution `1.0.0`.

## Product and scope

- [x] The user outcome is observable without a real model provider.
- [x] `FR-001`, `FR-003`, `FR-006`, and `FR-011` have feature requirements and
  acceptance scenarios.
- [x] `EPIC-001` is the sole owning epic.
- [x] Retrieval, recommendation policy, memory, live connectors, and export are
  explicitly deferred.
- [x] Public-demo and local-data behavior are distinct and server-derived.
- [x] No product, experience, or cross-cutting architecture decision is
  redefined.

## Scenario quality

- [x] Every scenario has a concrete initial state, action, and observable result.
- [x] Happy path, invalid input, stale revision, duplicate request, denial,
  cross-workspace access, disconnect, restart, and malformed UI are covered.
- [x] Each scenario maps to an exact future test path.
- [x] Terminal run, replay, and reset semantics are defined.
- [x] No scenario depends on hidden model judgment.

## Contracts and data

- [x] Canonical Pydantic ownership is recorded.
- [x] OpenAPI uses versioned paths, stable errors, idempotency, and revision
  headers.
- [x] `UiEnvelope` is a closed, versioned discriminated schema.
- [x] Durable entities, fields, relationships, uniqueness, and state transitions
  are defined.
- [x] Workspace scope and immutable revision rules are explicit.
- [x] Future domain model names are reserved without inventing behavior.

## Security and privacy

- [x] Workspace identity comes only from verified server context.
- [x] Cross-workspace access returns the same 404 shape as a missing resource.
- [x] Public-demo capability denial occurs before persistence, filesystem,
  network, queue, or vector side effects.
- [x] Guest cookies, token hashing, expiry, revocation, and reset are defined.
- [x] Model and UI payloads are untrusted and validated before persistence or
  rendering.
- [x] Logs and traces use allowlisted metadata and exclude content and secrets.
- [x] Negative tests cover isolation, capability bypass, cookie tampering, and
  telemetry redaction.

## Reliability and operations

- [x] Liveness and dependency readiness are separate.
- [x] Run input, job, events, and terminal state are durable.
- [x] Event sequence, stream heartbeat, reconnect, and replay semantics are
  defined.
- [x] Worker leases, retry, resume, and duplicate-terminal prevention are
  defined.
- [x] Contract drift and migration state block readiness or continuous
  integration.
- [x] Five-user first-useful-UI performance evidence is required.

## Accessibility and presentation

- [x] React owns presentation and action semantics.
- [x] Only `recommendation-summary@1.0` is accepted in this slice.
- [x] Unknown versions, kinds, actions, and properties fail closed.
- [x] Loading, reconnect, terminal, and safe-error states are specified.
- [x] Keyboard operation and axe serious/critical checks are blocking.

## Implementation readiness

- [x] Runtime topology and exact future source paths are listed.
- [x] Every behavior task is preceded by a failing test task.
- [x] Dependencies and execution order are explicit.
- [x] Verification commands cover backend, frontend, Compose, contracts,
  security, accessibility, performance, and evaluation.
- [x] The clarification record contains no unresolved decision.
- [x] No placeholder marker remains in the feature packet.
