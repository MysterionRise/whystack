# AI CTO Cockpit

AI CTO Cockpit is a portfolio-grade, evidence-backed architecture decision
workspace. It helps a technical founder frame a decision, inspect relevant
project evidence, compare viable options, record an outcome, and see how that
outcome changes a later recommendation.

This repository is the active implementation workspace. BMAD owns the accepted
product, experience, architecture, and quality baseline; Spec Kit owns every
implementation slice.

## Product promise

The product is a persistent decision workspace, not a chat wrapper:

- recommendations cite immutable source revisions and expose uncertainty;
- typed hard constraints and final scoring are enforced by deterministic code;
- the model may populate reviewed UI components but may not emit executable UI;
- accepted outcomes become durable facts, while inferred preferences require
  confirmation;
- every memory influence on a recommendation is inspectable and correctable;
- the hosted demo uses only an original synthetic corpus, while local-data mode
  can connect to real private material with explicit inference-egress disclosure.

The canonical demonstration contains two related architecture decisions. The
visitor accepts or edits the first recommendation and can then see precisely
why the second recommendation changed.

## How the lifecycle works

1. The signed inception baseline is recorded in
   [`.ai-sdlc/inception-baseline.yaml`](.ai-sdlc/inception-baseline.yaml).
2. BMAD artifacts under [`_bmad-output/`](_bmad-output/) define the product,
   user experience, architecture spine, epics, and system quality contract.
3. The Spec Kit constitution and feature directories translate that baseline
   into small, testable delivery slices.
4. A cross-cutting product, UX, or architectural discovery must become a
   baseline change request before feature work continues.
5. A slice-local implementation discovery stays within its active Spec Kit
   feature.

The complete ownership and change-control rules live in
[`.ai-sdlc/WORKFLOW.md`](.ai-sdlc/WORKFLOW.md).

## Current walking skeleton

Feature `001-walking-skeleton` currently provides a trusted-session,
contract, and persistence walking skeleton on the five-process Compose topology:

- a Next.js web process with a health endpoint;
- a FastAPI process with separate liveness and dependency-readiness endpoints;
- a non-HTTP Python worker with a process health check, PostgreSQL job leases,
  attempt fencing, and restart-safe execution;
- PostgreSQL as the canonical store;
- Qdrant as a derived, rebuildable store that is readiness-only in feature 001;
- canonical Pydantic public contracts with deterministic checked OpenAPI and
  controlled-UI JSON Schema artifacts;
- deterministic generated TypeScript types plus a fail-closed runtime parser
  that accepts only `recommendation-summary@1.0` and the disabled
  `view-evidence` action;
- Alembic migration `0001_walking_skeleton`, applied before API readiness, for
  the workspace, session, decision, run/event, job, idempotency, and bounded
  reset-replay records;
- workspace-scoped persistence primitives and caller-owned transaction
  boundaries, with exact reset-response bytes and AES-256-GCM-protected
  replacement-token material;
- startup-frozen deployment configuration, stable server-owned seed/local
  workspace shells, and opaque signed guest sessions that never expose or
  accept workspace scope;
- atomic guest reset with revocation, deletion-job creation, and ten-minute
  byte-exact replay across process restart and retained-key rotation;
- pre-body 403/501 capability boundaries for uploads and the reserved
  `local-git`, `github`, and `web` connector routes;
- atomic, idempotent run creation bound to an immutable decision revision,
  with a queued event and durable execute-run job committed together;
- an explicit three-node LangGraph deterministic fixture that persists the
  closed `recommendation-summary@1.0` envelope and a single terminal event;
- workspace-scoped run snapshots and PostgreSQL-backed SSE replay with
  persisted sequence IDs, `Last-Event-ID` recovery, heartbeats, and terminal
  close across API or worker restart;
- atomic reset-deletion execution that retains only the non-sensitive
  completion receipt after the guest workspace and owned job cascade;
- isolated Compose networks and persistent service volumes.

No retrieval, provider calls, recommendation intelligence, long-term memory,
live connectors, or model-generated executable UI are implemented in this
slice. Provider credentials are not required.

The current Spec Kit status is:

- T001–T003 are complete: locked workspace, preserved readiness RED evidence,
  and the GREEN Compose topology.
- T004–T005 are complete: preserved contract-generation RED evidence,
  fail-closed canonical Pydantic contracts, and deterministic generated
  artifacts.
- T006–T007 are complete: retained frontend-contract RED evidence, generated
  TypeScript contracts, a strict runtime validator, and closed-parser fuzz
  coverage.
- T008–T009 are complete: retained migration/model RED evidence, the canonical
  PostgreSQL schema, scoped repositories, reset-replay cryptographic primitives,
  and exact migration-head readiness at `0001_walking_skeleton`.
- The structured T006–T009 execution record is
  [`specs/001-walking-skeleton/evidence/t006-t009-execution.md`](specs/001-walking-skeleton/evidence/t006-t009-execution.md).
- T010–T012 are complete: retained configuration/session and capability-boundary
  RED evidence, server-derived context, signed guest sessions, atomic exact
  reset replay, and closed reserved routes.
- The structured T010–T012 execution record is
  [`specs/001-walking-skeleton/evidence/t010-t012-execution.md`](specs/001-walking-skeleton/evidence/t010-t012-execution.md).
- T013 is complete in RED: 63 decision API acceptance cases specify scoped
  create/get/revise behavior, immutable persisted revisions, closed validation,
  exact decimal-string normalization, idempotency, stale-write recovery, and
  uniform cross-workspace 404 responses.
- The structured T013 execution record is
  [`specs/001-walking-skeleton/evidence/t013-execution.md`](specs/001-walking-skeleton/evidence/t013-execution.md).
- T014 is complete in RED: bounded Hypothesis properties specify sequential
  and concurrent revision/idempotency behavior, exact integer weight
  normalization across permutations and decimal contexts, lossless
  browser-sensitive decimal strings, and ascending-ID remainder ties.
- The structured T014 execution record is
  [`specs/001-walking-skeleton/evidence/t014-execution.md`](specs/001-walking-skeleton/evidence/t014-execution.md).
- T015 is complete in GREEN: the scoped decision API now persists immutable,
  contiguous PostgreSQL revisions; normalizes lossless decimal strings with an
  integer-only largest-remainder algorithm; and atomically records canonical
  idempotent responses behind transaction and aggregate locks. The structured
  execution record is
  [`specs/001-walking-skeleton/evidence/t015-execution.md`](specs/001-walking-skeleton/evidence/t015-execution.md).
- T016–T018 are complete: their retained RED proves the run, stream, lease, and
  worker seams were absent; the GREEN implementation now provides atomic run
  creation, deterministic LangGraph execution, fenced worker recovery,
  persisted SSE replay, and atomic guest deletion. The structured execution
  record is
  [`specs/001-walking-skeleton/evidence/t016-t018-execution.md`](specs/001-walking-skeleton/evidence/t016-t018-execution.md).
- T019, the health/readiness RED task, is the next unstarted task.

## Developer workflow

Use the versions pinned in [`.node-version`](.node-version),
[`.python-version`](.python-version), and
[`.ai-sdlc/toolchain.lock.yaml`](.ai-sdlc/toolchain.lock.yaml). Docker Desktop
or another Docker Compose v2 environment is required for the topology test.
Select Node.js `24.18.0` with your version manager before invoking Make; the
Make gates fail early unless Node.js `24.18.0` and Corepack pnpm `11.17.0` are
active.

Install only from committed locks:

```bash
make install
```

Run the packet and static quality gates:

```bash
./scripts/verify-bootstrap.sh
make node-toolchain-check
make check
make contracts-check
```

`make contracts-generate` regenerates the backend artifacts first and then the
frontend bindings. `make contracts-check` verifies semantic equivalence with
the binding feature contracts plus byte-for-byte backend and frontend drift.

Inspect pinned tool versions and run the self-cleaning Compose acceptance test:

```bash
make toolchain-check
make test-compose-readiness
```

`make check` runs Ruff linting and formatting checks over backend source and
tests, strict Pyright including backend tests, and the frontend ESLint and
TypeScript checks. The Compose test creates a unique project, builds and waits
for every process, verifies PostgreSQL/Alembic and Qdrant readiness, and removes
only that project's containers and volumes.

The task-owned contract, persistence, and trusted-session suites can also be
run directly:

```bash
corepack pnpm --dir apps/web test -- ui-envelope-contract.test.ts
uv run --project services/backend --locked pytest \
  services/backend/tests/integration/test_migrations.py \
  services/backend/tests/unit/test_persistence_models.py
uv run --project services/backend --locked pytest \
  services/backend/tests/api/test_config.py \
  services/backend/tests/security/test_guest_session.py \
  services/backend/tests/api/test_session_reset.py \
  services/backend/tests/security/test_demo_capabilities.py
uv run --project services/backend --locked pytest \
  services/backend/tests/integration/test_run_lifecycle.py \
  services/backend/tests/integration/test_run_replay.py \
  services/backend/tests/integration/test_job_leases.py
```

## Start here

Before a new explicitly scoped Spec Kit batch, read these artifacts in order:

1. [`_bmad-output/planning-artifacts/product-brief.md`](_bmad-output/planning-artifacts/product-brief.md)
2. [`_bmad-output/planning-artifacts/prd.md`](_bmad-output/planning-artifacts/prd.md)
3. [`_bmad-output/planning-artifacts/EXPERIENCE.md`](_bmad-output/planning-artifacts/EXPERIENCE.md)
4. [`_bmad-output/planning-artifacts/ARCHITECTURE-SPINE.md`](_bmad-output/planning-artifacts/ARCHITECTURE-SPINE.md)
5. [`_bmad-output/planning-artifacts/implementation-readiness.md`](_bmad-output/planning-artifacts/implementation-readiness.md)
6. [`_bmad-output/test-artifacts/ai-quality-contract.md`](_bmad-output/test-artifacts/ai-quality-contract.md)
7. The Spec Kit constitution and `specs/001-walking-skeleton/`.
8. The active task range in
   [`specs/001-walking-skeleton/tasks.md`](specs/001-walking-skeleton/tasks.md).

Run the repository bootstrap verifier before each batch, preserve the named RED
evidence, and stop after the authorized task range. Do not run a BMAD
implementation loop for this feature.

## Licensing and provenance

The bootstrap packet and future original implementation are released under the
[MIT License](LICENSE). Course notebooks and lab assets are sources of learning,
not redistribution inputs. Every borrowed idea must be re-expressed in original
project code and tests; every seed artifact must have documented provenance and
permission for public use. Vendored framework notices and exact license texts
are recorded in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
