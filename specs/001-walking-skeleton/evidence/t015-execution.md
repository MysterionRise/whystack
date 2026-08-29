# T015 execution evidence

Status: retained from the live, explicitly scoped Spec Kit T015 transcript on
2026-08-29.

Branch: `codex/001-walking-skeleton`

Base revision: `232f767def496791612891e44dd64996e8eab7ed`.

Commands ran on macOS arm64 with Node.js `24.18.0`, Corepack pnpm `11.17.0`,
Python `3.12.13`, uv `0.11.16`, Hypothesis `6.160.0`, Docker Engine `29.6.2`,
and Docker Compose `5.3.1`. Node.js and uv were used from checksum-verified
temporary copies of the exact repository pins; no host-global runtime changed.

## Spec Kit analysis

Repository-local `speckit-analyze` covered the active specification, plan,
data model, OpenAPI contract, tasks, constitution, and BMAD traceability before
implementation. It found no critical or high inconsistency, and confirmed that
T013 and T014 were complete RED dependencies and T015 was the next bounded
task.

The implementation follows the analyzed concurrency order: acquire a
transaction-scoped advisory lock for the workspace/operation/idempotency-key
tuple, revalidate and lock the active trusted workspace, check stored replay
before current-revision state, then lock the scoped decision aggregate. This
makes identical retries collapse to the original response, changed requests
using the same key fail with `idempotency_conflict`, and different keys racing
on one expected revision produce one winner plus `revision_conflict` losers.

Ordinary request-hash bytes remain an internal versioned profile, as the
accepted packet specifies observable equivalence rather than a public encoding.
The hash covers validated aliased input, operation, method, canonical path, and
revision `If-Match`, while excluding credentials and the idempotency key.
Local-data records use the maximum finite timezone-aware Python timestamp as an
effectively persistent expiry because their workspace has no expiry; no public
contract or migration changed.

## Preserved RED boundary

T015 consumed, without weakening, both prior RED records:

```console
uv run --project services/backend --locked pytest \
  services/backend/tests/api/test_decisions.py -q
uv run --project services/backend --locked pytest \
  services/backend/tests/property/test_revision_idempotency.py -q
```

The retained T013 observation was 63 failed cases after successful disposable
PostgreSQL migration and guest/local setup; every request received route-level
HTTP 404 because decision behavior was absent. The retained T014 observation
was 6 failed bounded property cases at the same absent create route. Full
details remain in `t013-execution.md` and `t014-execution.md`.

## T015 GREEN

Fresh focused commands:

```console
uv run --project services/backend --locked pytest \
  services/backend/tests/api/test_decisions.py -q
uv run --project services/backend --locked pytest \
  services/backend/tests/property/test_revision_idempotency.py -q
```

Observed results:

- all 63 T013 API acceptance cases passed in 5.62 seconds; and
- all 6 T014 bounded Hypothesis cases passed in 7.11 seconds, including all
  three concurrent fanout modes and both normalization properties.

The implementation adds only the decision slice: server-owned UUIDv7 IDs,
validated exact decimal-string preservation, common-scale integer coefficient
expansion, `divmod` allocation of exactly 1,000,000 units, descending-remainder
and ascending-ID tie ordering, canonical snapshot/request hashes, closed API
errors, current-decision retrieval, immutable revision append, and atomic
idempotency persistence/replay. PostgreSQL remains canonical and workspace
scope comes only from the signed or local server context.

## Regression and governance gates

Fresh commands:

```console
uv run --project services/backend --locked pytest services/backend/tests -q
make check
make contracts-check
uv run scripts/verify_traceability.py --root .
make test-compose-readiness
./scripts/verify-bootstrap.sh
```

Observed results:

- the complete backend suite passed 202 of 202 tests in 14.25 seconds;
- `make check` passed Ruff lint/format, strict Pyright including backend tests,
  frontend ESLint, and frontend TypeScript;
- contract drift checks reported every generated artifact current and all 27
  backend contract tests passed;
- traceability validation passed after T015 status/evidence reconciliation;
- Compose readiness passed its one end-to-end topology test in 28.03 seconds,
  including exact `0001_walking_skeleton` repository/database head equality;
  and
- bootstrap passed all 37 verifier tests plus packet and traceability
  validation.

## Deferred boundary

No run lifecycle, worker, retrieval, provider, recommendation, memory,
connector, Qdrant-write, UI, telemetry, or later-task behavior entered T015.
T016, the run lifecycle RED task, is the next unstarted task.
