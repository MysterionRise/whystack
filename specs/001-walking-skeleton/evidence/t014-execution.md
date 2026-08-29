# T014 execution evidence

Status: retained from the live, explicitly scoped Spec Kit T014 transcript on
2026-08-29.

Branch: `codex/001-walking-skeleton`

Base revision: `6e7cb73720f30476c8abdcaa0662d4e8b276588e`. The RED snapshot is
the commit containing this evidence file.

Commands ran on macOS arm64 with Node.js `24.18.0`, Corepack pnpm `11.17.0`,
Python `3.12.13`, uv `0.11.16`, Hypothesis `6.160.0`, Docker Engine `29.6.2`,
and Docker Compose `5.3.1`. Node.js and uv were used from checksum-verified
temporary copies of the exact repository pins; no host-global runtime was
changed.

## Spec Kit analysis

Repository-local cross-artifact analysis covered the active specification,
plan, data model, OpenAPI contract, tasks, constitution, and BMAD traceability.
It found no critical or high inconsistency after T013. T014 deliberately tests
observable normalized-request behavior rather than prescribing an
uncontracted internal request-hash byte encoding, and it inspects immutable
history directly in canonical PostgreSQL rather than adding a historical API.

The task-owned dependency maintenance was isolated before test work in
`.ai-sdlc/maintenance/IM-004-t014-hypothesis.md` and committed separately. It
added only `hypothesis==6.160.0` and required transitive
`sortedcontainers==2.4.0`; no application behavior entered that packet.

## T014 RED — decision revision implementation absent

Command:

```console
uv run --project services/backend --locked pytest \
  services/backend/tests/property/test_revision_idempotency.py -q
```

Observed result: exit 1 with all 6 collected cases failing in 3.86 seconds.
The disposable PostgreSQL database started successfully and migrated to
`0001_walking_skeleton`; public-demo configuration and signed guest setup also
succeeded. Every property then reached `POST /api/v1/decisions` and received
HTTP 404 instead of the contracted HTTP 201 because no decision router or
service is registered. This is the required T014 RED boundary, not a fixture,
collection, dependency, async, Hypothesis, lint, type, or database failure.

The bounded, deterministic properties preserve shrinking and cover:

- generated sequential revision sequences with accepted appends, exact replay
  of normalized equivalent requests, body/`If-Match` mismatches, fresh-key
  stale writes, contiguous immutable rows, and no rejected side effects;
- generated concurrent fanout for identical requests sharing a key,
  different requests sharing a key, and distinct keys sharing one expected
  revision, with winner-agnostic exactly-once assertions;
- valid 2–10-item decimal-string vectors and non-identity input permutations,
  including `0.00000001`, `9999999999.99999999`, trailing-zero preservation,
  and a coefficient above `2^53` that changes under browser-style floating
  conversion;
- an integer-only common-scale `divmod` oracle allocating exactly 1,000,000
  units independently of low/high decimal contexts; and
- explicit and generated equal-remainder cases of sizes 3, 6, 7, and 9,
  proving ascending criterion IDs receive the remaining units.

Shared PostgreSQL fixtures were promoted from the API-only subtree and the
direct-ASGI client moved to typed test support so API and property suites use
one disposable container without copying infrastructure. No production module
or public contract changed.

## Non-RED regression gates

Fresh commands:

```console
uv run --project services/backend --locked pytest services/backend/tests \
  --ignore=services/backend/tests/api/test_decisions.py \
  --ignore=services/backend/tests/property/test_revision_idempotency.py -q
uv run --project services/backend --locked pytest \
  services/backend/tests/api/test_config.py \
  services/backend/tests/api/test_session_reset.py \
  services/backend/tests/security/test_demo_capabilities.py \
  services/backend/tests/security/test_guest_session.py -q
uv run --project services/backend --locked pytest \
  services/backend/tests/api/test_decisions.py -q
make check
make contracts-check
uv run scripts/verify_traceability.py --root .
./scripts/verify-bootstrap.sh
```

Observed results:

- the non-RED backend suite passed 133 of 133 tests;
- the fixture-refactor API/security focus passed 54 of 54 tests;
- the unchanged T013 suite retained its 63 route-level HTTP 404 failures;
- `make check` passed Ruff lint/format, strict Pyright including all backend
  tests, frontend ESLint, and frontend TypeScript;
- contract drift, traceability, and bootstrap gates passed; and
- bootstrap verification passed all 37 packet tests plus packet and
  traceability validation.

## Deferred boundary

All decision routes/services, UUID creation, integer normalization,
transaction and aggregate locking, request hashing, idempotency
persistence/replay, and revision append behavior remain T015. No retrieval,
model-provider, recommendation, memory, connector, Qdrant-write, UI, run, or
worker behavior entered T014. The next unstarted task is T015.
