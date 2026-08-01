# Requirements Checklist: Walking Skeleton

Reviewed against inception baseline `IB-002` and constitution `2.0.0`.

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
- [x] Public-demo capability denial occurs before reading request bodies or
  invoking persistence, filesystem, network, queue, or vector side effects.
- [x] Guest cookies, token hashing, expiry, revocation, and reset are defined.
- [x] Model and UI payloads are untrusted and validated before persistence or
  rendering.
- [x] Logs, OpenTelemetry traces, and OpenTelemetry metrics use allowlisted
  metadata and exclude content, workspace IDs, and secrets.
- [x] Negative tests cover isolation, capability bypass, cookie tampering, and
  telemetry redaction.
- [x] Configured-origin CORS, untrusted forwarded headers, the 256 KiB API and
  web-proxy JSON limit, and pre-body connector denial have exact negative tests.
- [x] Oversized ordinary JSON requests have a canonical HTTP 413
  `request_too_large` error across Pydantic, OpenAPI, generated artifacts, API,
  and web proxy.
- [x] Nonced CSP, `frame-ancestors 'none'`, `nosniff`, and strict referrer
  policy have exact frontend acceptance tests.

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
- [x] Generated markup, script, URL, prototype, oversize, and recursive
  envelopes fail closed with zero arbitrary execution.
- [x] Loading, empty, partial-evidence, abstention, error, reconnect, and
  completed product-owned states are specified without broadening the closed
  envelope or adding recommendation intelligence.
- [x] Keyboard, focus-return, reduced-motion, 200% zoom, semantic comparison,
  meaningful announcements, and axe serious/critical checks are blocking.
- [x] Manual accessibility evidence requires one supported desktop screen
  reader and 360, 768, 1280, and 1440-pixel viewport checks.

## Implementation readiness

- [x] Runtime topology and exact future source paths are listed.
- [x] Every behavior task is preceded by a failing test task.
- [x] Dependencies and execution order are explicit.
- [x] Verification commands cover backend, frontend, Compose, contracts,
  security, accessibility, performance, and evaluation.
- [x] `make check` blocks on Ruff lint and formatting, Pyright over backend
  source and tests, and frontend lint and type checking.
- [x] The backend is an installable `src` package and production operation does
  not rely on `PYTHONPATH`.
- [x] Task-owned dependency updates are isolated immediately before their
  owning task and regenerate locks and affected governance hashes.
- [x] `QUALITY-PERF-001` retains the four-vCPU/eight-GiB Linux profile, five
  users, 20 warm-up turns, at least 200 measured completions, browser/span
  correlation, every latency/replay threshold, and the sub-one-percent error
  gate.
- [x] T032 owns a deterministic `make eval-feature FEATURE=001` target using the
  already pinned Node.js and Playwright toolchain.
- [x] T034 records full clean-clone quickstart and Compose evidence on both
  macOS and the four-vCPU/eight-GiB reference Linux environment.
- [x] The clarification record contains no unresolved decision.
- [x] No placeholder marker remains in the feature packet.
