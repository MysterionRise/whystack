# T010–T012 execution evidence

Status: retained from the live, explicitly scoped Spec Kit task-batch transcript
on 2026-08-14.

Branch: `codex/001-walking-skeleton`

Base revision: `799f7d549f0534a9dbc301ab4a2a47b7ca1cf140`. The implementation snapshot is
the commit containing this evidence file.

Final commands ran on macOS arm64 with Node.js `24.18.0`, Corepack pnpm
`11.17.0`, Python `3.12.13`, uv `0.11.16`, Docker Engine `29.6.2`, and Docker
Compose `5.3.1`. Node.js and uv were used from checksum-verified temporary
copies of the exact repository pins; no host-global runtime was changed.

This file records the commands and observed results from the active
implementation run. The RED commands were not rerun after production behavior
existed. Results are described faithfully where the original command was not
redirected to a raw log.

## T010 RED — trusted configuration and sessions absent

Command:

```console
uv run --project services/backend --locked pytest \
  services/backend/tests/api/test_config.py \
  services/backend/tests/security/test_guest_session.py \
  services/backend/tests/api/test_session_reset.py -q
```

Observed result: exit 2 with three collection errors. The configuration tests
could not import `create_app`; the guest-session tests could not import the
security package; and the reset tests could not import the trusted API context.
This was the expected absence before any T012 production behavior was added.

## T011 RED — reserved capability boundary absent

Command:

```console
uv run --project services/backend --locked pytest \
  services/backend/tests/security/test_demo_capabilities.py -q
```

Observed result: exit 1 with 16 failed cases because the settings module and
reserved route factory were absent. The direct-ASGI test matrix already covered
all four reserved routes, both deployment modes, and ordinary plus over-256-KiB
bodies. Its receive object and persistence, filesystem, network, job, and Qdrant
tripwires were installed in the test packet before T012 behavior existed and
were retained unchanged for GREEN.

## T012 GREEN — trusted context, reset, and denial

An adversarial T012 audit identified four boundary regressions before the final
implementation was accepted. The following focused selection was added and run
before those fixes:

```console
uv run --project services/backend --locked pytest \
  services/backend/tests/security/test_guest_session.py::test_retained_key_reconstructs_its_original_cookie_security_profile \
  services/backend/tests/security/test_guest_session.py::test_insecure_cookie_is_rejected_outside_explicit_local_compose \
  services/backend/tests/api/test_config.py::test_database_time_is_canonical_when_process_clock_is_skewed \
  services/backend/tests/api/test_session_reset.py::test_reset_rejects_non_visible_ascii_idempotency_key_before_mutation \
  services/backend/tests/security/test_demo_capabilities.py::test_reserved_capabilities_validate_idempotency_header_pre_body -q
```

Observed result: exit 1 with eight failed cases. The failures proved that replay
cookie policy was not retained per signing key, insecure cookies were not
restricted to explicit local Compose, persisted security windows used the
process clock, reset accepted a non-visible-ASCII idempotency key, and the four
reserved-route mode cases did not validate the required header. After the
bounded T012 corrections, the same selection passed all eight cases.

A final cross-artifact analysis then added seven focused regression cases before
the remaining T012 corrections:

```console
uv run --project services/backend --locked pytest \
  services/backend/tests/api/test_config.py::test_config_maps_database_failure_to_contracted_service_unavailable \
  services/backend/tests/api/test_config.py::test_concurrent_first_config_requests_bootstrap_one_seed_shell \
  services/backend/tests/api/test_session_reset.py::test_reset_rejects_non_visible_ascii_idempotency_key_before_mutation \
  services/backend/tests/security/test_demo_capabilities.py::test_reserved_capabilities_validate_idempotency_header_pre_body -q
```

Observed result: exit 1 with seven failed cases. Database failure escaped instead
of returning the contracted 503, concurrent first-use shell creation raised a
unique-key conflict, and the five reset/reserved-route validation cases returned
the framework's open error body instead of the closed `ApiError` contract. After
the bounded fixes, the same selection passed all seven cases.

Fresh commands:

```console
uv run --project services/backend --locked pytest \
  services/backend/tests/api/test_config.py \
  services/backend/tests/security/test_guest_session.py \
  services/backend/tests/api/test_session_reset.py \
  services/backend/tests/security/test_demo_capabilities.py -q
uv run --project services/backend --locked pytest services/backend/tests -q
make check
make contracts-check
make test-compose-readiness
uv run scripts/verify_traceability.py --root .
./scripts/verify-bootstrap.sh
```

Observed results:

- combined T010–T011 acceptance suite: 54 of 54 passed, including genuine
  concurrent resets and direct-ASGI unread-body/side-effect assertions;
- full backend suite: 133 of 133 passed against disposable PostgreSQL where
  required;
- `make check`: Ruff lint and formatting, strict Pyright including backend
  tests, frontend ESLint, and frontend TypeScript all passed;
- `make contracts-check`: every generated artifact was current and 27 of 27
  backend contract tests passed;
- Compose readiness: 1 of 1 passed, with database and repository Alembic heads
  exactly equal at `0001_walking_skeleton`;
- repository-local Spec Kit analysis found no critical inconsistency across the
  active specification, plan, contracts, tasks, constitution, and traceability;
- traceability validation passed;
- bootstrap verification passed all 37 packet tests plus packet and
  traceability validation.

No OpenAPI, generated schema, dependency lock, migration, Qdrant-write,
retrieval, model-provider, recommendation, long-term-memory, connector, or UI
behavior was added.

## Deferred boundary

Deletion-job execution, seed-content loading, request-size/CORS/proxy and
telemetry hardening, and web integration remain assigned to later feature-001
tasks. Expired replay receipts are purged by a later reset request; cleanup when
no reset traffic arrives remains an operational risk for a later task. The next
unstarted task is T013.
