# Tasks: Walking Skeleton

Feature: 001  
Baseline: IB-001  
Owning epic: EPIC-001

## Execution rules

- Complete tasks in numeric order unless a task is marked `[P]`.
- A `RED` task must be run and fail for the stated missing behavior before its
  paired implementation task begins.
- Do not broaden the feature into retrieval, real model calls, outcome memory,
  connectors, or export.
- Each commit records the task IDs it completes. Production source must not
  contain planning identifiers.
- After any contract change, rerun backend contract tests, frontend contract
  tests, and `make contracts-check`.

## Phase A — Reproducible skeleton

- [X] **T001 — VERIFY: create locked workspace manifests**
  - Create `Makefile`, `package.json`, `pnpm-workspace.yaml`,
    `services/backend/pyproject.toml`, `apps/web/package.json`,
    `apps/web/tsconfig.json`, `.node-version`, `.python-version`,
    `pnpm-lock.yaml`, and `services/backend/uv.lock` using
    `.ai-sdlc/toolchain.lock.yaml`. Set the root `packageManager` field to the
    locked pnpm version and keep the backend non-package-installable until
    T003 creates source.
  - Configure `uv` and `pnpm` lockfile generation, pytest, Vitest, Playwright,
    Ruff, Pyright, ESLint, and TypeScript checks.
  - Trace: `NFR-009`, `NFR-011`; `AS-001`, `AS-008`.
  - Verify from the repository root; each command must exit zero and report
    the version locked in `.ai-sdlc/toolchain.lock.yaml` where applicable:
    - `node --version`
    - `uv --version`
    - `corepack pnpm --version`
    - `corepack pnpm install --frozen-lockfile`
    - `uv lock --project services/backend --check --python 3.12.13 --managed-python`
    - `uv sync --project services/backend --locked --all-groups --no-install-project --python 3.12.13 --managed-python`
    - `uv run --project services/backend --no-sync pytest --version`
    - `uv run --project services/backend --no-sync ruff --version`
    - `corepack pnpm exec pyright --version`
    - `corepack pnpm --dir apps/web exec vitest --version`
    - `corepack pnpm --dir apps/web exec playwright --version`
    - `corepack pnpm --dir apps/web exec eslint --version`
    - `corepack pnpm --dir apps/web exec tsc --version`

- [X] **T002 — RED: specify Compose readiness**
  - Create `tests/e2e/test_compose_readiness.py` to assert service health,
    Postgres connectivity, exact equality between database and repository
    Alembic heads, Qdrant readiness, and the absence of a provider-key
    requirement. In this phase both Alembic head sets are empty.
  - Make the test self-contained: use a unique Compose project name, run
    `up --build --wait`, inspect Postgres and Qdrant from the isolated network,
    treat worker reachability as Compose process health, and always run
    `down --volumes` for only that project.
  - Trace: `F-009`, `NFR-004`, `NFR-009`, `QUALITY-OPS-001`; `AS-001`.
  - Verify:
    `uv run --project services/backend --no-sync pytest tests/e2e/test_compose_readiness.py`
    fails because the topology does not exist.
  - Depends on: T001.

- [X] **T003 — GREEN: implement the Compose process topology**
  - Create `infra/compose.yaml`, `infra/env/demo.env`, backend API and worker
    entry-point skeletons, a process-only web health route,
    `apps/web/Dockerfile`, `services/backend/Dockerfile`, and service health
    checks. The worker has no HTTP or job API.
  - Add an Alembic scaffold with no revision or domain table. Readiness must
    compare database current heads with repository heads truthfully; T009 owns
    the first `0001_walking_skeleton.py` revision.
  - Expose only the minimal versioned API liveness and dependency-readiness
    surfaces needed by T002. T021 later extracts and hardens those probes
    without changing their URLs or response contract.
  - Include Postgres and Qdrant persistent volumes, materialize the image
    digests locked in `.ai-sdlc/toolchain.lock.yaml`, and isolate services on
    the Compose network.
  - Trace: `F-009`, `NFR-004`, `NFR-009`, `QUALITY-OPS-001`; `AS-001`.
  - Verify:
    `uv run --project services/backend --no-sync pytest tests/e2e/test_compose_readiness.py`
    passes.
  - Depends on: T002.

## Phase B — Canonical contracts

- [X] **T004 — RED: specify backend contract generation**
  - Create `services/backend/tests/contracts/test_openapi.py` and
    `services/backend/tests/contracts/test_ui_schema.py`.
  - Assert semantic equivalence with this feature's OpenAPI and UI schema,
    rejection of unknown fields/kinds/versions/actions, and schema-version
    presence.
  - Trace: `F-007`, `F-010`, `NFR-011`, `QUALITY-UI-001`; `AS-008`.
  - Verify: `uv run --project services/backend pytest
    services/backend/tests/contracts` fails because canonical Pydantic models
    and generated artifacts are absent.
  - Depends on: T001.

- [ ] **T005 — GREEN: implement Pydantic contracts and generation**
  - Create `services/backend/src/ai_cto_cockpit/contracts/config.py`,
    `decision.py`, `errors.py`, `run.py`, and `ui.py`.
  - Create the contract generator and checked artifacts at
    `contracts/generated/openapi.json` and
    `contracts/generated/ui-envelope.schema.json`.
  - Add `contracts-generate` and `contracts-check` Make targets.
  - Trace: `F-007`, `F-010`, `NFR-011`, `QUALITY-UI-001`; `AS-008`.
  - Verify: backend contract tests and `make contracts-check` pass.
  - Depends on: T004.

- [ ] **T006 — RED: specify frontend contract enforcement**
  - Create `apps/web/tests/ui-envelope-contract.test.ts` with valid fixture,
    unknown component, unknown action, extra property, wrong version, malformed
    UUID, and enabled evidence-action cases.
  - Assert that invalid input returns the safe typed failure rather than a
    renderable component.
  - Trace: `F-007`, `F-010`, `NFR-007`, `NFR-011`, `QUALITY-UI-001`; `AS-008`.
  - Verify: `pnpm --dir apps/web test -- ui-envelope-contract.test.ts` fails
    because generated types and validators are absent.
  - Depends on: T005.

- [ ] **T007 — GREEN: implement generated TypeScript contracts**
  - Create `apps/web/src/contracts/generated.ts`,
    `apps/web/src/contracts/ui-envelope.ts`, and the frontend generation/check
    script.
  - Expose one exhaustive parser returning either
    `recommendation-summary@1.0` or a safe contract error.
  - Trace: `F-007`, `F-010`, `NFR-007`, `NFR-011`, `QUALITY-UI-001`; `AS-008`.
  - Verify: T006 tests, `pnpm --dir apps/web check`, and
    `make contracts-check` pass.
  - Depends on: T006.

## Phase C — Persistence and trusted context

- [ ] **T008 — RED: specify schema and aggregate invariants**
  - Create `services/backend/tests/integration/test_migrations.py` and
    `services/backend/tests/unit/test_persistence_models.py`.
  - Assert all tables, foreign keys, unique constraints, workspace-scoped
    indexes, terminal run transitions, immutable revisions, entered and
    normalized criterion weights, event sequence, job leases, ordinary
    idempotency uniqueness, and the non-cascading ten-minute
    `ResetReplayReceipt` invariants in `data-model.md`, including exact response
    bytes and context-bound authenticated encryption.
  - Trace: `F-002`, `F-003`, `F-004`, `F-006`, `NFR-004`; `AS-003`, `AS-005`.
  - Verify: the tests fail because migration `0001` and models are absent.
  - Depends on: T003, T005.

- [ ] **T009 — GREEN: implement migration, models, and transaction boundary**
  - Create `services/backend/migrations/versions/0001_walking_skeleton.py`,
    `persistence/models.py`, `persistence/session.py`, and
    `persistence/repositories.py`.
  - Implement state-transition guards, workspace-scoped repository methods,
    reset-receipt expiry/purge support, exact serialized response-byte storage,
    and authenticated encryption of replacement reset tokens with the specified
    receipt-context associated data.
  - Trace: `F-002`, `F-003`, `F-004`, `F-006`, `NFR-004`; `AS-003`, `AS-005`.
  - Verify: T008 tests pass against a disposable Postgres database.
  - Depends on: T008.

- [ ] **T010 — RED: specify server-derived configuration and sessions**
  - Create `services/backend/tests/api/test_config.py`,
    `services/backend/tests/security/test_guest_session.py`, and
    `services/backend/tests/api/test_session_reset.py`.
  - Cover public-demo and local-data capability documents, cookie flags,
    tampering, expiry, revocation, overlay lifetime, absence of workspace and
    secrets, and deletion-job creation.
  - Simulate loss of the first successful reset response. Assert that the
    cryptographically valid revoked old cookie plus the same key and request hash
    within ten minutes returns the byte-equivalent body and exact original
    content type and `Set-Cookie` value without a second workspace or job, even
    across restart and serializer-version change. Assert same-key hash mismatch
    is HTTP 409, while a different key, expired or missing receipt, and every
    non-reset use of the revoked cookie are HTTP 401.
  - Swap receipt ciphertexts and mutate each associated-data field; assert
    authenticated decryption fails closed. Assert a decrypted token whose hash
    does not match the bound replacement token/session is never signed. Mutate
    or swap stored response bytes and assert response-hash verification fails
    closed. Assert receipt purge and that no receipt field contains workspace,
    source, decision, run, event, UI, or other user-authored content.
  - Race reset requests: identical key/hash calls collapse to one commit and one
    replay, while a different-key loser cannot reset the already-revoked session.
  - Trace: `F-001`, `F-002`, `NFR-002`, `NFR-008`; `AS-002`, `AS-007`.
  - Verify: these tests fail because settings, session verification, context,
    and routes are absent.
  - Depends on: T009.

- [ ] **T011 — RED: specify capability denial before side effects**
  - Create `services/backend/tests/security/test_demo_capabilities.py`.
  - Instrument repositories, filesystem, network client, Qdrant client, and job
    dispatch; assert every public-demo upload and connector request returns
    `capability_disabled` without invoking them.
  - Cover local-data's `capability_not_implemented` response for feature 001.
  - Trace: `F-008`, `FR-011`, `NFR-002`, `NFR-008`, `QUALITY-SEC-001`; `AS-006`.
  - Verify: the test fails because reserved routes and denial middleware are
    absent.
  - Depends on: T009.

- [ ] **T012 — GREEN: implement trusted context, configuration, reset, and denial**
  - Create `settings.py`, `security/guest_session.py`,
    `api/dependencies/context.py`, `api/routes/config.py`, and reserved source
    and connector routes.
  - Implement the guest-workspace transaction, opaque signed cookie, hashed
    session lookup, local singleton context, pre-side-effect capability guard,
    and the reset transaction that creates the replacement session, revokes the
    old one, queues deletion, and writes its encrypted ten-minute replay receipt.
  - Restrict revoked-cookie verification to the reset replay branch. Match its
    fingerprint, operation, key, and request hash in constant time; reproduce the
    original response bytes/content type and deterministic cookie serialization
    from fixed receipt fields.
  - Bind token ciphertext through AEAD associated data to every immutable
    security-relevant receipt field in `data-model.md`; after decrypting,
    constant-time verify the token hash against the receipt before signing.
    Purge expired receipts.
  - Trace: `F-001`, `F-002`, `F-008`, `NFR-002`, `NFR-008`,
    `QUALITY-SEC-001`; `AS-002`, `AS-006`, `AS-007`.
  - Verify: T010 and T011 tests pass.
  - Depends on: T010, T011.

## Phase D — Versioned decisions

- [ ] **T013 — RED: specify decision API behavior**
  - Create `services/backend/tests/api/test_decisions.py`.
  - Cover create/get/revise, validation limits, unique slugs, all typed
    constraint variants, immutable revision retrieval, stale `If-Match`, missing
    idempotency key, same-request replay, conflicting key reuse, and uniform 404.
  - Accept bounded lossless decimal-string entered weights that do not total
    100. Assert the response and stored revision preserve every exact string,
    including trailing zeros, and expose four-place normalized strings totaling
    exactly `100.0000`, including unequal rounding and an equal-fraction tie
    resolved by ascending criterion ID.
  - Cover lexical boundaries: accept `0.00000001` and
    `9999999999.99999999`; reject zero, signs, exponents, leading zeros, more
    than ten integer digits, more than eight fractional digits, non-string JSON
    values, and any out-of-range value before coefficient expansion.
  - Trace: `F-003`, `FR-003`, `NFR-002`, `NFR-004`, `NFR-011`; `AS-003`,
    `AS-007`.
  - Verify: the test fails because decision services and routes are absent.
  - Depends on: T012.

- [ ] **T014 — RED: specify revision and idempotency properties**
  - Create
    `services/backend/tests/property/test_revision_idempotency.py`.
  - Generate concurrent and sequential request sequences; assert one immutable
    revision per accepted mutation, contiguous revisions, original responses
    for identical keys, and conflicts for mismatched hashes.
  - Generate valid bounded decimal-string weight vectors and input permutations.
    Assert common-scale integer `divmod` normalization allocates exactly
    1,000,000 units, preserves all entered strings, is independent of input
    order, browser-number behavior, and decimal context, and assigns remainder
    ties by ascending criterion ID.
  - Trace: `F-003`, `NFR-004`, `QUALITY-OPS-001`; `AS-003`.
  - Verify: the property test fails against the missing implementation.
  - Depends on: T013.

- [ ] **T015 — GREEN: implement decision revisions and idempotency**
  - Create `domain/ids.py`, `domain/idempotency.py`, `domain/revisions.py`,
    `api/routes/decisions.py`, and the required repository methods.
  - Validate the bounded decimal-string grammar and limits before expansion,
    preserve the strings exactly, convert them to common-scale integer
    coefficients, normalize with the specified integer `divmod`
    largest-remainder algorithm, format normalized strings to four places,
    normalize request hashes, lock aggregate rows, append revisions, and persist
    idempotent responses in the same transaction.
  - Trace: `F-003`, `FR-003`, `NFR-002`, `NFR-004`, `NFR-011`,
    `QUALITY-OPS-001`; `AS-003`, `AS-007`.
  - Verify: T013 and T014 tests pass.
  - Depends on: T013, T014.

## Phase E — Durable run and replay

- [ ] **T016 — RED: specify run creation and deterministic lifecycle**
  - Create `services/backend/tests/integration/test_run_lifecycle.py`.
  - Assert atomic snapshot/job creation, exact fixture version, queued/running/UI
    envelope/completed order, deterministic payload, terminal state, malformed
    envelope failure, and duplicate-run idempotency.
  - Trace: `F-004`, `F-005`, `F-007`, `FR-006`, `NFR-004`,
    `QUALITY-UI-001`, `QUALITY-OPS-001`; `AS-004`.
  - Verify: the test fails because run services, graph, and worker are absent.
  - Depends on: T015.

- [ ] **T017 — RED: specify leases, restart, and replay**
  - Create `services/backend/tests/integration/test_run_replay.py` and
    `services/backend/tests/integration/test_job_leases.py`.
  - Cover reconnect from every sequence, terminal replay, API restart, worker
    restart, lease expiry, competing workers, contiguous sequence, heartbeat,
    and exactly one terminal event.
  - Trace: `F-004`, `F-005`, `F-006`, `NFR-004`, `QUALITY-OPS-001`; `AS-005`.
  - Verify: the tests fail because job leasing and stream replay are absent.
  - Depends on: T016.

- [ ] **T018 — GREEN: implement the deterministic graph, worker, and stream**
  - Create `runs/fake_graph.py`, `runs/jobs.py`, `runs/service.py`, `worker.py`,
    `api/routes/runs.py`, and the associated repository transactions.
  - Validate before event insertion, lease and resume jobs, persist each event,
    expose snapshots, and stream SSE from the persisted watermark.
  - Trace: `F-004`, `F-005`, `F-006`, `F-007`, `FR-006`, `NFR-004`,
    `QUALITY-UI-001`, `QUALITY-OPS-001`; `AS-004`, `AS-005`.
  - Verify: T016 and T017 tests pass.
  - Depends on: T016, T017.

## Phase F — Health, isolation, and observability

- [ ] **T019 — RED: specify health and readiness**
  - Create `services/backend/tests/integration/test_health.py`.
  - Cover unauthenticated liveness, Postgres failure, migration lag, Qdrant
    failure, recovery, and the exact readiness-check map.
  - Trace: `F-009`, `NFR-004`, `NFR-009`, `QUALITY-OPS-001`; `AS-001`.
  - Verify: the test fails because the Phase A probes do not yet implement the
    complete dependency-degradation, migration-lag, and recovery semantics.
  - Depends on: T009.

- [ ] **T020 — RED: specify isolation and telemetry redaction**
  - Create `services/backend/tests/security/test_workspace_isolation.py` and
    `services/backend/tests/security/test_telemetry_redaction.py`.
  - Generate 10,000 cross-workspace reads and mutations spanning decisions,
    runs, event streams, idempotency records, jobs, reset, and guessed IDs.
  - Capture logs and spans containing canary secrets and decision text; require
    zero canary value and only allowlisted attributes.
  - Trace: `F-009`, `NFR-002`, `NFR-008`, `QUALITY-SEC-001`; `AS-007`.
  - Verify: tests fail until every query and telemetry path is scoped/redacted.
  - Depends on: T012, T015, T018.

- [ ] **T021 — GREEN: implement readiness and redacted telemetry**
  - Extract the Phase A probes into `api/routes/health.py`, harden their
    dependency failure and recovery behavior, and create `telemetry.py` plus
    correlation middleware; register all routes and middleware in `main.py`.
  - Apply explicit workspace predicates to every repository and stream query.
  - Trace: `F-009`, `NFR-002`, `NFR-004`, `NFR-008`, `NFR-009`,
    `QUALITY-SEC-001`, `QUALITY-OPS-001`; `AS-001`, `AS-007`.
  - Verify: T019 and T020 tests plus the Compose readiness test pass.
  - Depends on: T019, T020.

## Phase G — Controlled web experience

- [ ] **T022 — RED: specify web configuration boundary**
  - Create `apps/web/tests/config-boundary.test.ts`.
  - Assert server-proxy usage, no raw API base URL in browser bundles, no
    workspace or secret field, capability-driven controls, and safe handling of
    configuration failure.
  - Trace: `F-001`, `F-008`, `NFR-002`, `NFR-008`; `AS-002`, `AS-006`.
  - Verify: the test fails because the proxy, API client, and configuration
    adapter are absent.
  - Depends on: T007, T012.

- [ ] **T023 — GREEN: implement the web proxy and configuration adapter**
  - Create `apps/web/app/api/backend/[...path]/route.ts`,
    `apps/web/src/lib/api-client.ts`, `apps/web/src/lib/config.ts`, and the root
    layout/page.
  - Forward allowed methods, signed cookie, SSE body, correlation header,
    idempotency header, and revision header without logging payloads.
  - Trace: `F-001`, `F-008`, `NFR-002`, `NFR-008`; `AS-002`, `AS-006`.
  - Verify: T022 and frontend type checks pass.
  - Depends on: T022.

- [ ] **T024 — RED: specify decision-frame interaction**
  - Create `apps/web/tests/decision-frame-form.test.tsx`.
  - Cover create, revise, client-side schema feedback, bounded entered-weight
    string validation, lossless preservation (including trailing zeros),
    rejection of sign/exponent/precision/scale/magnitude violations, visible
    four-place normalized strings totaling `100.0000`, stale revision recovery,
    duplicate submission idempotency, keyboard flow, and disabled connector
    controls. Entered weights are not required to total 100, and no JavaScript
    `number` conversion may occur.
  - Trace: `F-003`, `F-008`, `NFR-007`; `AS-003`, `AS-006`, `AS-008`.
  - Verify: the test fails because form and decision pages are absent.
  - Depends on: T023.

- [ ] **T025 — GREEN: implement decision pages and frame form**
  - Create `apps/web/src/components/decision/decision-frame-form.tsx`,
    `apps/web/app/decisions/new/page.tsx`, and
    `apps/web/app/decisions/[decisionId]/page.tsx`.
  - Generate idempotency keys per user intent, preserve them across transport
    retry, submit the exact `enteredWeight` string without browser numeric
    coercion, preserve it across responses and retries, display the server's
    already-four-place `normalizedWeight` string, and show stale-revision and
    validation states without data loss.
  - Trace: `F-003`, `F-008`, `NFR-007`; `AS-003`, `AS-006`, `AS-008`.
  - Verify: T024 and frontend type checks pass.
  - Depends on: T024.

- [ ] **T026 — RED: specify run stream and controlled component**
  - Create `apps/web/tests/recommendation-summary.test.tsx` and
    `apps/web/tests/run-stream.test.ts`.
  - Cover loading, ordered events, disconnect, resume sequence, terminal
    snapshot fallback, deterministic disclaimer, disabled evidence action,
    unknown envelope, and duplicate event suppression.
  - Trace: `F-006`, `F-007`, `FR-006`, `NFR-007`, `QUALITY-UI-001`; `AS-004`,
    `AS-005`, `AS-008`.
  - Verify: tests fail because the stream client and component are absent.
  - Depends on: T025.

- [ ] **T027 — GREEN: implement resumable stream and controlled rendering**
  - Create `apps/web/src/lib/run-stream.ts` and
    `apps/web/src/components/recommendation/recommendation-summary.tsx`.
  - Integrate the component catalog with CopilotKit/AG-UI presentation state;
    validate before rendering and map only the approved disabled action.
  - Trace: `F-006`, `F-007`, `FR-006`, `NFR-007`, `QUALITY-UI-001`; `AS-004`,
    `AS-005`, `AS-008`.
  - Verify: T026 tests and frontend checks pass.
  - Depends on: T026.

## Phase H — End-to-end quality evidence

- [ ] **T028 — RED: specify the browser journey and restart recovery**
  - Create `apps/web/e2e/walking-skeleton.spec.ts`.
  - Cover guest creation, seeded landing state, decision revision, run start,
    forced stream disconnect, replay, page reload, API restart, worker restart,
    guest reset, simulated lost reset response with exact same-key replay, and
    old-session denial on all other requests.
  - Trace: `FR-001`, `FR-003`, `FR-006`, `FR-011`, `QUALITY-OPS-001`;
    `AS-002` through `AS-007`.
  - Verify: Playwright fails until the full browser path and seed fixture are
    wired.
  - Depends on: T021, T027.

- [ ] **T029 — GREEN: implement seed wiring and complete browser journey**
  - Create the seed loader for `seed/sample-project/manifest.yaml`, mount the
    immutable seed workspace, finish decision/run page wiring, and add
    restart-safe Playwright controls.
  - Trace: `FR-001`, `FR-003`, `FR-006`, `FR-011`, `QUALITY-OPS-001`;
    `AS-002` through `AS-007`.
  - Verify: `pnpm --dir apps/web test:e2e -- walking-skeleton.spec.ts` passes.
  - Depends on: T028.

- [ ] **T030 — RED: specify accessibility**
  - Create `apps/web/e2e/walking-skeleton-accessibility.spec.ts`.
  - Assert keyboard-only completion, visible focus, status announcements,
    reconnect announcement, semantic score table, disabled-action explanation,
    reduced-motion behavior, and zero serious or critical axe violations.
  - Trace: `F-007`, `NFR-007`, `QUALITY-UI-001`; `AS-008`.
  - Verify: the test reports any unimplemented semantics or accessibility defect.
  - Depends on: T029.

- [ ] **T031 — GREEN: close accessibility findings**
  - Change only the reviewed React components and styles needed for T030.
  - Record the axe report as feature evidence.
  - Trace: `F-007`, `NFR-007`, `QUALITY-UI-001`; `AS-008`.
  - Verify: T030 and all frontend tests pass.
  - Depends on: T030.

- [ ] **T032 — RED: specify the five-user performance gate**
  - Create `evals/feature-001/load_test.js` and
    `evals/feature-001/quality.yaml`.
  - Measure configuration, decision creation, run acceptance, first persisted UI
    envelope, terminal snapshot, errors, and duplicate effects for five
    concurrent guests.
  - Trace: `QUALITY-PERF-001`, `QUALITY-OPS-001`; `AS-001`, `AS-004`, `AS-005`.
  - Verify: `make eval-feature FEATURE=001` fails until measured p95 first useful
    UI is at most four seconds, fake terminal p95 is at most five seconds, and
    duplicate effects are zero.
  - Depends on: T029.

- [ ] **T033 — GREEN: meet and record performance evidence**
  - Bound polling intervals, database queries, connection pools, stream flush,
    and worker lease timing without changing contracts.
  - Generate `evals/results/feature-001/manifest.json` with commit, fixture,
    schema, migration, fake-model, environment, latency, error, and duplicate
    effect data.
  - Trace: `QUALITY-PERF-001`, `QUALITY-OPS-001`; `AS-001`, `AS-004`, `AS-005`.
  - Verify: `make eval-feature FEATURE=001` passes twice from clean data.
  - Depends on: T032.

- [ ] **T034 — VERIFY: run the feature convergence suite**
  - Execute contract drift, all backend tests, all frontend checks/tests,
    Compose readiness, Playwright, accessibility, security/property tests, and
    feature evaluation from a clean clone.
  - Update `.ai-sdlc/traceability.yaml` with immutable evidence paths and the
    feature commit.
  - Trace: all feature requirements and quality identifiers; `AS-001` through
    `AS-008`.
  - Verify: every command in `quickstart.md` passes and Spec Kit analysis reports
    no critical inconsistency.
  - Depends on: T003 through T033.

## Parallel work boundaries

After T005:

- T006–T007 may proceed in the web contract territory.
- T008–T009 may proceed in the persistence territory.

After T012:

- T013–T015 own decision behavior.
- T019–T021 own production health hardening and telemetry; T003 owns only the
  minimum Compose-readiness probes.
- T022–T023 own the web proxy and configuration behavior.

The run territory starts only after T015 because it snapshots an accepted
decision revision. End-to-end and quality tasks start only after the API and web
territories are integrated.

## Completion evidence

Feature 001 is complete only when T034 records passing evidence for all scenarios
and `QUALITY-UI-001`, `QUALITY-SEC-001`, `QUALITY-PERF-001`, and
`QUALITY-OPS-001`. Passing unit tests alone is insufficient.
