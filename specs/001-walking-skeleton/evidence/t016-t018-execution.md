# T016–T018 execution evidence

Status: retained from the live, explicitly scoped Spec Kit T016–T018 transcript
on 2026-08-29.

Branch: `codex/001-walking-skeleton`

Base revision: `74472d12bfed1eb8e28bbcb0a4d87da2eab2b172`.

Commands ran on macOS arm64 with Node.js `24.18.0`, Corepack pnpm `11.17.0`,
Python `3.12.13`, uv `0.11.16`, Hypothesis `6.160.0`, Docker Engine `29.6.2`,
and Docker Compose `5.3.1`. Node.js and uv were the checksum-verified copies of
the exact repository pins; no host-global runtime changed.

## Spec Kit analysis

Repository-local `speckit-analyze` covered the active specification, plan,
data model, OpenAPI and Pydantic contracts, tasks, constitution, and BMAD
traceability before implementation. It found no critical inconsistency and
confirmed that T015 was complete and T016 was the next bounded task.

The analysis resolved two high-priority execution ambiguities in the acceptance
tests without changing the public contract: run creation binds `If-Match` into
the idempotency hash and checks an existing idempotency record before current
revision state; the fake result is fixed demonstration output rather than
recommendation or scoring intelligence. Closing reconciliation also maps the
run-isolation and delete-workspace evidence to `AS-007`; T016 is no longer
incorrectly mapped to the reconnect-only `AS-005` scenario.

An independent implementation review then identified one high durability issue
and two medium boundary issues. Before final verification, production claims,
fences, renewals, and worker writes were changed to use fresh PostgreSQL
`clock_timestamp()` values while retaining explicit deterministic time only in
tests; the worker now renews and propagates its immutable lease before graph
work. Every event variant is validated through the discriminated Pydantic
`RunEvent` contract before insertion, and an open SSE stream re-resolves its
signed session and active workspace on every poll and before heartbeat output.
The focused suite remained 15 of 15 green after these corrections, and the
review re-audit found no remaining blocker.

## T016–T017 RED — run, stream, lease, and worker behavior absent

The following command ran after the three acceptance files collected cleanly
and before any T018 production behavior was added:

```console
uv run --project services/backend --locked pytest \
  services/backend/tests/integration/test_run_lifecycle.py \
  services/backend/tests/integration/test_run_replay.py \
  services/backend/tests/integration/test_job_leases.py -q
```

Observed result: `15 failed in 2.98s` after Alembic
`0001_walking_skeleton`, disposable PostgreSQL, guest-session setup, and
decision creation succeeded.

- All 7 T016 lifecycle cases failed at the absent run POST route with HTTP 404.
- Three T017 replay cases failed at that same absent route, while the heartbeat
  case failed at the absent `RunStreamPolicy` seam.
- One T017 lease case failed because `ai_cto_cockpit.runs.jobs` was absent, and
  three failed because `worker.process_one_job` was absent.

This is the intended behavior-level RED boundary. No collection error, Docker
fixture failure, migration failure, or weakened assertion caused the result.
Ruff, Ruff formatting, strict Pyright, and focused collection passed for all
new tests before implementation.

## T018 GREEN

The bounded implementation adds only the feature-001 run territory:

- atomic, workspace-scoped run creation bound to the current immutable decision
  revision, with `run.queued`, an available execute-run job, and the canonical
  idempotent response in one PostgreSQL transaction;
- exact same-key replay and closed idempotency, revision, validation, and
  uniform missing/cross-workspace errors;
- an explicit three-node LangGraph
  `load-snapshot -> emit-demonstration -> complete-run` that emits the closed,
  visibly non-authoritative `recommendation-summary@1.0` fixture;
- ordered validated event persistence, monotonic terminal snapshots, malformed
  envelope rejection before insertion, and one safe `invalid_ui_envelope`
  failure event;
- ordered `FOR UPDATE SKIP LOCKED` claims, renewable attempt-fenced leases,
  prefix-driven restart recovery, and one terminal event under competing
  workers;
- persisted-watermark SSE with scoped preflight, fresh short database sessions,
  canonical `id`/`event`/`data` frames, `Last-Event-ID` precedence, heartbeat,
  terminal close, disconnect safety, and API restart replay; and
- one deletion transaction that records only the non-sensitive completion,
  marks the claimed attempt successful, and deletes the guest workspace so its
  session, content, and owned job cascade. An injected deferred commit failure
  rolls back both completion and deletion and leaves the lease reclaimable.

Fresh focused command:

```console
uv run --project services/backend --locked pytest \
  services/backend/tests/integration/test_run_lifecycle.py \
  services/backend/tests/integration/test_run_replay.py \
  services/backend/tests/integration/test_job_leases.py -q
```

Final observed result after review corrections: `15 passed in 4.08s`.

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

- the complete backend suite passed 217 of 217 tests in 16.52 seconds;
- `make check` passed Ruff lint and format checks, strict Pyright over source and
  backend tests, frontend ESLint, and frontend TypeScript checking;
- generated OpenAPI, UI JSON Schema, and TypeScript artifacts were current, and
  all 27 backend contract tests passed;
- traceability validation passed after T016–T018 task, scenario, test, and
  evidence reconciliation;
- the self-cleaning five-process Compose readiness test passed in 21.64 seconds,
  including the real polling worker and exact `0001_walking_skeleton`
  repository/database head equality; and
- bootstrap passed all 37 verifier tests plus packet and traceability
  validation.

## Deferred boundary and remaining risks

No retrieval, evidence search, provider call, recommendation intelligence,
long-term memory, connector, Qdrant write, arbitrary UI, web application, CORS,
request-limit, or telemetry behavior entered this batch. Qdrant remains
readiness-only and PostgreSQL remains canonical.

The remaining accepted risks are deliberately task-owned: T019–T021 harden
dependency degradation, exhaustive workspace isolation, telemetry redaction,
metrics, CORS, proxy trust, and request limits; T022–T027 add the same-origin
web experience; T028–T029 add seed content and the browser restart journey.
The data model's missing mutable `Run.updated_at` field remains a convergence
item because correcting it requires a reviewed migration rather than an
unplanned T018 schema change.

T019, the health/readiness RED task, is the next unstarted task.
