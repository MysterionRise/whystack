# T013 execution evidence

Status: retained from the live, explicitly scoped Spec Kit T013 transcript on
2026-08-15.

Branch: `codex/001-walking-skeleton`

Base revision: `38f50e10ad8a6e32fa5c5a211a6711cd1926aabb`. The RED snapshot is the
commit containing this evidence file.

Commands ran on macOS arm64 with Node.js `24.18.0`, Corepack pnpm `11.17.0`,
Python `3.12.13`, uv `0.11.16`, Docker Engine `29.6.2`, and Docker Compose
`5.3.1`. Node.js and uv were used from checksum-verified temporary copies of
the exact repository pins; no host-global runtime was changed.

## Spec Kit analysis and packet repair

Repository-local cross-artifact analysis covered the active specification,
plan, data model, OpenAPI contract, tasks, constitution, and BMAD traceability.
Before the test was accepted, the packet was reconciled so that:

- stale revision conflicts use stable code `revision_conflict` in the closed
  `ApiError` shape and clients recover current state through the authorized
  current-decision GET;
- historical immutability is inspected directly in canonical PostgreSQL rather
  than through an uncontracted historical-revision endpoint;
- submitted questions preserve surrounding whitespace but require at least one
  non-whitespace character in canonical Pydantic, design OpenAPI, and generated
  artifacts; and
- feature 001 structurally validates bounded currency, SPDX, and country-code
  inputs without claiming external registry membership lookup.

No critical or high inconsistency remained after these repairs.

## T013 RED — decision routes and services absent

Command:

```console
uv run --project services/backend --locked pytest \
  services/backend/tests/api/test_decisions.py -q
```

Observed result: exit 1 with 63 failed cases. The disposable PostgreSQL database
started successfully and migrated to `0001_walking_skeleton`; public-demo and
local-data configuration setup also succeeded. Every acceptance case then
reached the contracted decision path and observed HTTP 404 because no decision
router or service is registered. Representative expected-201 create requests
received the framework response `{"detail":"Not Found"}`, while validation and
conflict cases likewise received route-level 404 before their expected closed
responses. This is the required T013 RED boundary, not a fixture, collection,
lint, type, or database failure.

The 63 cases cover:

- public-demo and local-data server-derived scope;
- create, current GET, revise, direct immutable-revision inspection, and all
  seven typed constraint variants;
- request cardinality/length limits, closed objects, unique slugs, required
  mutation headers, and uniform missing/cross-workspace 404 behavior;
- lossless entered-weight strings, non-100 totals, lexical extrema, rejected
  signs/exponents/zeros/leading zeros/precision/magnitude/non-string values,
  deterministic unequal rounding, and ascending-ID remainder ties; and
- identical create/revise replay, conflicting key reuse, and stale `If-Match`
  recovery without mutation.

No Hypothesis dependency, property/concurrency test, input-permutation matrix,
decimal-context manipulation, decision route, decision service, repository
behavior, or other T014/T015 work was added.

## Non-RED regression gates

Fresh commands:

```console
uv run --project services/backend --locked pytest services/backend/tests \
  --ignore=services/backend/tests/api/test_decisions.py -q
make check
make contracts-check
uv run scripts/verify_traceability.py --root .
./scripts/verify-bootstrap.sh
```

Observed results:

- the pre-existing backend suite passed 133 of 133 tests;
- `make check` passed Ruff lint/format, strict Pyright including the new test,
  frontend ESLint, and frontend TypeScript;
- `make contracts-check` found no generated drift and passed all 27 backend
  contract tests;
- traceability validation passed; and
- bootstrap verification passed all 37 packet tests plus packet and
  traceability validation.

## Deferred boundary

Decision property tests and the task-owned Hypothesis lock update remain T014.
All decision services/routes, integer normalization, transaction and aggregate
locking, request hashing, idempotency persistence/replay, and revision append
behavior remain T015. Explicit per-operation OpenAPI enumeration of the global
unauthorized response remains a non-blocking contract-convergence item. No
retrieval, model-provider, recommendation, memory, connector, Qdrant-write, or
UI behavior entered this batch. The next unstarted task is T014.
