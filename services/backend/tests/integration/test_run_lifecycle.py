from __future__ import annotations

import asyncio
import importlib
import json
import re
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import cast

import pytest
from fastapi import FastAPI
from pydantic import TypeAdapter
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_cto_cockpit.contracts.run import RunEvent as RunEventContract
from ai_cto_cockpit.contracts.run import RunView
from ai_cto_cockpit.contracts.ui import UiEnvelope
from ai_cto_cockpit.main import create_app
from ai_cto_cockpit.persistence.models import (
    DecisionRevision,
    GuestSession,
    IdempotencyRecord,
    Job,
    JobKind,
    JobStatus,
    Run,
    RunEvent,
    RunEventKind,
    RunStatus,
)
from ai_cto_cockpit.security.guest_session import GuestSessionCodec
from ai_cto_cockpit.settings import Settings
from tests.support.asgi import AsgiResponse, asgi_request

NOW = datetime(2026, 8, 17, 11, 0, 0, 123456, tzinfo=UTC)
SIGNING_KEY = "t016-session-signing-key-with-more-than-thirty-two-bytes"
SEED_ID = uuid.UUID("0198b0f0-0000-7000-8000-000000000001")
LOCAL_ID = uuid.UUID("0198b0f0-0000-7000-8000-000000000002")
MISSING_DECISION_ID = "0198b0f0-0000-7000-8000-00000000d016"
RUN_OPERATION = "create-run-v1"
FIXTURE_VERSION = "walking-skeleton-v1"
LOWERCASE_SHA256 = re.compile(r"^[0-9a-f]{64}$")

type JsonObject = dict[str, object]
type SessionFactory = async_sessionmaker[AsyncSession]
type ProcessOneJob = Callable[..., Awaitable[bool]]


def _settings(database_url: str) -> Settings:
    return Settings(
        app_mode="public-demo",
        database_url=database_url,
        qdrant_url="http://127.0.0.1:6333",
        session_signing_key=SIGNING_KEY,
        session_signing_key_id="cookie-key-v1",
        session_retained_signing_keys={},
        cookie_secure=False,
        local_compose=True,
        seed_workspace_id=SEED_ID,
        local_workspace_id=LOCAL_ID,
    )


def _cookie_value(set_cookie: str) -> str:
    name, value = set_cookie.split(";", 1)[0].split("=", 1)
    assert name == "ai_cto_guest"
    return value


def _frame(*, marker: str = "fixture-only-marker") -> JsonObject:
    return {
        "schemaVersion": "1.0",
        "question": f"Which bounded option should we inspect? {marker}",
        "context": f"User-authored context must not become fixture copy: {marker}",
        "options": [
            {
                "id": "managed-platform",
                "label": "Managed platform",
                "description": "Prefer managed operations.",
            },
            {
                "id": "self-hosted",
                "label": "Self hosted",
                "description": "Retain operational control.",
            },
        ],
        "criteria": [
            {
                "id": "cost",
                "label": "Cost",
                "enteredWeight": "1.0000",
            },
            {
                "id": "operability",
                "label": "Operability",
                "enteredWeight": "2.0000",
            },
        ],
        "constraints": [],
    }


def _json_body(payload: JsonObject) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


async def _new_guest(
    app: FastAPI,
    factory: SessionFactory,
) -> tuple[str, uuid.UUID, datetime]:
    response = await asgi_request(app, method="GET", path="/api/v1/config")
    assert response.status == 200
    set_cookie = response.header("set-cookie")
    assert set_cookie is not None
    cookie = _cookie_value(set_cookie)
    codec = cast(GuestSessionCodec, app.state.guest_session_codec)
    claims = codec.verify(cookie, now=NOW)
    async with factory() as session:
        guest = await session.get(GuestSession, claims.session_id)
        assert guest is not None
    return cookie, guest.workspace_id, guest.expires_at


async def _app_and_guest(
    database_url: str,
    factory: SessionFactory,
) -> tuple[FastAPI, str, uuid.UUID, datetime]:
    app = create_app(
        settings=_settings(database_url),
        session_factory=factory,
        clock=lambda: NOW,
    )
    cookie, workspace_id, expires_at = await _new_guest(app, factory)
    return app, cookie, workspace_id, expires_at


async def _create_decision(
    app: FastAPI,
    *,
    cookie: str,
    key: str,
    frame: JsonObject | None = None,
) -> AsgiResponse:
    payload = frame or _frame()
    return await asgi_request(
        app,
        method="POST",
        path="/api/v1/decisions",
        headers=(
            ("Content-Type", "application/json"),
            ("Cookie", f"ai_cto_guest={cookie}"),
            ("Idempotency-Key", key),
        ),
        body=_json_body(payload),
    )


async def _revise_decision(
    app: FastAPI,
    decision_id: str,
    *,
    cookie: str,
    key: str,
    expected_revision: int,
) -> AsgiResponse:
    return await asgi_request(
        app,
        method="POST",
        path=f"/api/v1/decisions/{decision_id}/revisions",
        headers=(
            ("Content-Type", "application/json"),
            ("Cookie", f"ai_cto_guest={cookie}"),
            ("Idempotency-Key", key),
            ("If-Match", str(expected_revision)),
        ),
        body=_json_body(_frame(marker=f"revision-{expected_revision + 1}")),
    )


async def _post_run(
    app: FastAPI,
    decision_id: str,
    *,
    cookie: str,
    idempotency_key: str | None,
    expected_revision: int | None,
) -> AsgiResponse:
    headers: list[tuple[str, str]] = [
        ("Cookie", f"ai_cto_guest={cookie}"),
    ]
    if idempotency_key is not None:
        headers.append(("Idempotency-Key", idempotency_key))
    if expected_revision is not None:
        headers.append(("If-Match", str(expected_revision)))
    return await asgi_request(
        app,
        method="POST",
        path=f"/api/v1/decisions/{decision_id}/runs",
        headers=headers,
    )


async def _get_run(
    app: FastAPI,
    run_id: str,
    *,
    cookie: str,
) -> AsgiResponse:
    return await asgi_request(
        app,
        method="GET",
        path=f"/api/v1/runs/{run_id}",
        headers=(("Cookie", f"ai_cto_guest={cookie}"),),
    )


def _uuid7(value: object) -> uuid.UUID:
    assert isinstance(value, str)
    parsed = uuid.UUID(value)
    assert parsed.version == 7
    assert str(parsed) == value
    return parsed


def _assert_api_error(
    response: AsgiResponse,
    *,
    status: int,
    code: str,
) -> JsonObject:
    assert response.status == status
    payload = response.json()
    assert set(payload) == {"code", "message", "correlationId", "fields"}
    assert payload["code"] == code
    assert isinstance(payload["message"], str)
    _uuid7(payload["correlationId"])
    assert isinstance(payload["fields"], list)
    return payload


async def _run_counts(factory: SessionFactory) -> tuple[int, int, int, int]:
    async with factory() as session:
        runs = await session.scalar(select(func.count(Run.id)))
        events = await session.scalar(select(func.count(RunEvent.id)))
        jobs = await session.scalar(
            select(func.count(Job.id)).where(Job.kind == JobKind.EXECUTE_RUN)
        )
        idempotency = await session.scalar(
            select(func.count(IdempotencyRecord.id)).where(
                IdempotencyRecord.operation == RUN_OPERATION
            )
        )
    return (
        int(runs or 0),
        int(events or 0),
        int(jobs or 0),
        int(idempotency or 0),
    )


def _process_one_job() -> ProcessOneJob:
    """Resolve the T018 worker seam only when a lifecycle test executes."""

    module = importlib.import_module("ai_cto_cockpit.worker")
    candidate = module.process_one_job
    assert callable(candidate)
    return cast(ProcessOneJob, candidate)


def _event_document(event: RunEvent) -> JsonObject:
    return {
        "runId": str(event.run_id),
        "sequence": event.sequence,
        "kind": event.kind.value,
        "schemaVersion": event.payload_schema_version,
        "payload": event.payload,
        "createdAt": event.created_at,
    }


async def _events_for_run(
    factory: SessionFactory,
    run_id: uuid.UUID,
) -> list[RunEvent]:
    async with factory() as session:
        return list(
            (
                await session.scalars(
                    select(RunEvent)
                    .where(RunEvent.run_id == run_id)
                    .order_by(RunEvent.sequence)
                )
            ).all()
        )


@pytest.mark.asyncio
async def test_create_run_atomically_persists_snapshot_outbox_and_queued_event(
    t010_postgres_url: str,
    t010_session_factory: SessionFactory,
) -> None:
    app, cookie, workspace_id, guest_expires_at = await _app_and_guest(
        t010_postgres_url,
        t010_session_factory,
    )
    decision_response = await _create_decision(
        app,
        cookie=cookie,
        key="create-decision-for-run-016",
    )
    assert decision_response.status == 201
    decision = decision_response.json()
    decision_id = _uuid7(decision["id"])

    response = await _post_run(
        app,
        str(decision_id),
        cookie=cookie,
        idempotency_key="create-run-atomic-016",
        expected_revision=1,
    )

    assert response.status == 202
    assert response.header("content-type") == "application/json"
    payload = response.json()
    RunView.model_validate(payload)
    run_id = _uuid7(payload["id"])
    assert payload == {
        "id": str(run_id),
        "decisionId": str(decision_id),
        "decisionRevision": 1,
        "status": "queued",
        "lastEventSequence": 1,
        "fixtureVersion": FIXTURE_VERSION,
        "createdAt": payload["createdAt"],
        "startedAt": None,
        "completedAt": None,
        "errorCode": None,
    }
    assert response.header("location") == f"/api/v1/runs/{run_id}"
    assert "workspaceId" not in response.body.decode("utf-8")

    current = await _get_run(app, str(run_id), cookie=cookie)
    assert current.status == 200
    assert current.json() == payload

    async with t010_session_factory() as session:
        run = await session.get(Run, run_id)
        revision = await session.scalar(
            select(DecisionRevision).where(
                DecisionRevision.workspace_id == workspace_id,
                DecisionRevision.decision_id == decision_id,
                DecisionRevision.revision == 1,
            )
        )
        events = list(
            (
                await session.scalars(
                    select(RunEvent)
                    .where(RunEvent.run_id == run_id)
                    .order_by(RunEvent.sequence)
                )
            ).all()
        )
        jobs = list(
            (
                await session.scalars(
                    select(Job).where(
                        Job.workspace_id == workspace_id,
                        Job.kind == JobKind.EXECUTE_RUN,
                    )
                )
            ).all()
        )
        records = list(
            (
                await session.scalars(
                    select(IdempotencyRecord).where(
                        IdempotencyRecord.workspace_id == workspace_id,
                        IdempotencyRecord.operation == RUN_OPERATION,
                    )
                )
            ).all()
        )

    assert run is not None
    assert revision is not None
    assert run.workspace_id == workspace_id
    assert run.decision_id == decision_id
    assert run.decision_revision_id == revision.id
    assert run.status is RunStatus.QUEUED
    assert run.fixture_version == FIXTURE_VERSION
    assert run.input_snapshot == decision["frame"]
    assert run.input_snapshot_hash == revision.snapshot_hash
    assert LOWERCASE_SHA256.fullmatch(run.input_snapshot_hash)
    assert run.last_event_sequence == 1
    assert run.terminal_event_sequence is None
    assert run.started_at is None
    assert run.completed_at is None
    assert run.error_code is None

    assert len(events) == 1
    queued = events[0]
    assert queued.workspace_id == workspace_id
    assert queued.sequence == 1
    assert queued.kind is RunEventKind.RUN_QUEUED
    assert queued.payload_schema_version == "1.0"
    assert queued.payload == {"status": "queued"}
    assert LOWERCASE_SHA256.fullmatch(queued.payload_hash)
    TypeAdapter(RunEventContract).validate_python(_event_document(queued))

    assert len(jobs) == 1
    job = jobs[0]
    assert job.payload == {"runId": str(run_id)}
    assert job.status is JobStatus.AVAILABLE
    assert job.available_at == NOW
    assert job.lease_owner is None
    assert job.lease_expires_at is None
    assert job.attempt_count == 0
    assert job.last_error_code is None
    assert job.completed_at is None

    assert len(records) == 1
    record = records[0]
    assert record.key == "create-run-atomic-016"
    assert LOWERCASE_SHA256.fullmatch(record.request_hash)
    assert record.response_status == 202
    assert record.response_body == payload
    assert record.resource_id == run_id
    assert record.expires_at >= guest_expires_at
    assert await _run_counts(t010_session_factory) == (1, 1, 1, 1)


@pytest.mark.asyncio
async def test_run_headers_revision_and_idempotency_conflicts_are_side_effect_free(
    t010_postgres_url: str,
    t010_session_factory: SessionFactory,
) -> None:
    app, cookie, _, _ = await _app_and_guest(
        t010_postgres_url,
        t010_session_factory,
    )
    decision_response = await _create_decision(
        app,
        cookie=cookie,
        key="create-decision-conflicts-016",
    )
    assert decision_response.status == 201
    decision_id = cast(str, decision_response.json()["id"])

    missing_key = await _post_run(
        app,
        decision_id,
        cookie=cookie,
        idempotency_key=None,
        expected_revision=1,
    )
    missing_revision = await _post_run(
        app,
        decision_id,
        cookie=cookie,
        idempotency_key="missing-revision-run-016",
        expected_revision=None,
    )
    _assert_api_error(missing_key, status=422, code="request_validation_failed")
    _assert_api_error(
        missing_revision,
        status=422,
        code="request_validation_failed",
    )
    assert await _run_counts(t010_session_factory) == (0, 0, 0, 0)

    stale_before_first_run = await _post_run(
        app,
        decision_id,
        cookie=cookie,
        idempotency_key="stale-before-run-016",
        expected_revision=2,
    )
    _assert_api_error(
        stale_before_first_run,
        status=409,
        code="revision_conflict",
    )
    assert await _run_counts(t010_session_factory) == (0, 0, 0, 0)

    accepted = await _post_run(
        app,
        decision_id,
        cookie=cookie,
        idempotency_key="run-idempotency-016",
        expected_revision=1,
    )
    assert accepted.status == 202
    revision_two = await _revise_decision(
        app,
        decision_id,
        cookie=cookie,
        key="revise-after-run-016",
        expected_revision=1,
    )
    assert revision_two.status == 201

    replay = await _post_run(
        app,
        decision_id,
        cookie=cookie,
        idempotency_key="run-idempotency-016",
        expected_revision=1,
    )
    assert replay.status == 202
    assert replay.body == accepted.body
    assert replay.header("content-type") == accepted.header("content-type")
    assert replay.header("location") == accepted.header("location")

    changed_same_key = await _post_run(
        app,
        decision_id,
        cookie=cookie,
        idempotency_key="run-idempotency-016",
        expected_revision=2,
    )
    _assert_api_error(
        changed_same_key,
        status=409,
        code="idempotency_conflict",
    )
    fresh_stale_key = await _post_run(
        app,
        decision_id,
        cookie=cookie,
        idempotency_key="fresh-stale-run-016",
        expected_revision=1,
    )
    _assert_api_error(
        fresh_stale_key,
        status=409,
        code="revision_conflict",
    )
    assert await _run_counts(t010_session_factory) == (1, 1, 1, 1)


@pytest.mark.asyncio
async def test_run_create_is_scoped_and_unknown_resources_fail_closed(
    t010_postgres_url: str,
    t010_session_factory: SessionFactory,
) -> None:
    app, owner_cookie, owner_workspace, _ = await _app_and_guest(
        t010_postgres_url,
        t010_session_factory,
    )
    owner_decision = await _create_decision(
        app,
        cookie=owner_cookie,
        key="owner-decision-run-016",
    )
    assert owner_decision.status == 201
    owner_decision_id = cast(str, owner_decision.json()["id"])
    owner_run = await _post_run(
        app,
        owner_decision_id,
        cookie=owner_cookie,
        idempotency_key="workspace-run-key-016",
        expected_revision=1,
    )
    assert owner_run.status == 202
    owner_run_id = cast(str, owner_run.json()["id"])

    other_cookie, other_workspace, _ = await _new_guest(
        app,
        t010_session_factory,
    )
    assert other_workspace != owner_workspace
    cross_workspace_create = await _post_run(
        app,
        owner_decision_id,
        cookie=other_cookie,
        idempotency_key="cross-workspace-run-016",
        expected_revision=1,
    )
    missing_create = await _post_run(
        app,
        MISSING_DECISION_ID,
        cookie=owner_cookie,
        idempotency_key="missing-decision-run-016",
        expected_revision=1,
    )
    cross_workspace_get = await _get_run(
        app,
        owner_run_id,
        cookie=other_cookie,
    )
    for response in (cross_workspace_create, missing_create, cross_workspace_get):
        payload = _assert_api_error(
            response,
            status=404,
            code="resource_not_found",
        )
        assert payload["fields"] == []
    assert await _run_counts(t010_session_factory) == (1, 1, 1, 1)

    other_decision = await _create_decision(
        app,
        cookie=other_cookie,
        key="other-decision-run-016",
        frame=_frame(marker="other-workspace-marker"),
    )
    assert other_decision.status == 201
    other_decision_id = cast(str, other_decision.json()["id"])
    other_run = await _post_run(
        app,
        other_decision_id,
        cookie=other_cookie,
        idempotency_key="workspace-run-key-016",
        expected_revision=1,
    )
    assert other_run.status == 202
    assert other_run.json()["id"] != owner_run_id
    assert await _run_counts(t010_session_factory) == (2, 2, 2, 2)


@pytest.mark.asyncio
async def test_run_create_rolls_back_snapshot_event_and_idempotency_when_outbox_fails(
    t010_postgres_url: str,
    t010_session_factory: SessionFactory,
) -> None:
    app, cookie, _, _ = await _app_and_guest(
        t010_postgres_url,
        t010_session_factory,
    )
    decision = await _create_decision(
        app,
        cookie=cookie,
        key="rollback-decision-run-016",
    )
    assert decision.status == 201
    decision_id = cast(str, decision.json()["id"])

    install_trigger = text(
        """
        CREATE OR REPLACE FUNCTION t016_reject_execute_run_job()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.kind = 'execute-run' THEN
                RAISE EXCEPTION 'T016 forced outbox failure';
            END IF;
            RETURN NEW;
        END;
        $$;
        CREATE TRIGGER t016_reject_execute_run_job
        BEFORE INSERT ON jobs
        FOR EACH ROW EXECUTE FUNCTION t016_reject_execute_run_job();
        """
    )
    drop_trigger = text(
        """
        DROP TRIGGER IF EXISTS t016_reject_execute_run_job ON jobs;
        DROP FUNCTION IF EXISTS t016_reject_execute_run_job();
        """
    )
    async with t010_session_factory.begin() as session:
        await session.execute(install_trigger)

    failed_response: AsgiResponse | None = None
    try:
        try:
            failed_response = await _post_run(
                app,
                decision_id,
                cookie=cookie,
                idempotency_key="rollback-run-key-016",
                expected_revision=1,
            )
        except Exception:
            # An unhandled database failure is acceptable at this RED boundary;
            # the invariant under test is that its transaction leaves no effects.
            pass
    finally:
        async with t010_session_factory.begin() as session:
            await session.execute(drop_trigger)

    if failed_response is not None:
        assert failed_response.status >= 500
    assert await _run_counts(t010_session_factory) == (0, 0, 0, 0)


@pytest.mark.asyncio
async def test_concurrent_duplicate_run_requests_replay_exactly_once(
    t010_postgres_url: str,
    t010_session_factory: SessionFactory,
) -> None:
    app, cookie, _, _ = await _app_and_guest(
        t010_postgres_url,
        t010_session_factory,
    )
    decision = await _create_decision(
        app,
        cookie=cookie,
        key="concurrent-decision-run-016",
    )
    assert decision.status == 201
    decision_id = cast(str, decision.json()["id"])
    gate = asyncio.Event()

    async def contender() -> AsgiResponse:
        await gate.wait()
        return await _post_run(
            app,
            decision_id,
            cookie=cookie,
            idempotency_key="concurrent-run-key-016",
            expected_revision=1,
        )

    contenders = [asyncio.create_task(contender()) for _ in range(6)]
    await asyncio.sleep(0)
    gate.set()
    responses = await asyncio.wait_for(asyncio.gather(*contenders), timeout=10)

    assert {response.status for response in responses} == {202}
    assert len({response.body for response in responses}) == 1
    assert len({response.header("content-type") for response in responses}) == 1
    assert len({response.header("location") for response in responses}) == 1
    assert await _run_counts(t010_session_factory) == (1, 1, 1, 1)


@pytest.mark.asyncio
async def test_worker_emits_deterministic_fixture_lifecycle_and_terminal_snapshot(
    t010_postgres_url: str,
    t010_session_factory: SessionFactory,
) -> None:
    marker = "must-not-appear-in-demonstration-output"
    app, cookie, workspace_id, _ = await _app_and_guest(
        t010_postgres_url,
        t010_session_factory,
    )
    decision = await _create_decision(
        app,
        cookie=cookie,
        key="worker-decision-run-016",
        frame=_frame(marker=marker),
    )
    assert decision.status == 201
    decision_id = cast(str, decision.json()["id"])
    run_responses = [
        await _post_run(
            app,
            decision_id,
            cookie=cookie,
            idempotency_key=f"deterministic-run-{index}-016",
            expected_revision=1,
        )
        for index in range(2)
    ]
    assert [response.status for response in run_responses] == [202, 202]
    run_ids = [_uuid7(response.json()["id"]) for response in run_responses]

    process_one_job = _process_one_job()
    assert await process_one_job(
        session_factory=t010_session_factory,
        worker_id="t016-worker",
        now=NOW,
    )
    assert await process_one_job(
        session_factory=t010_session_factory,
        worker_id="t016-worker",
        now=NOW,
    )
    assert not await process_one_job(
        session_factory=t010_session_factory,
        worker_id="t016-worker",
        now=NOW,
    )

    envelopes: list[JsonObject] = []
    for run_id in run_ids:
        events = await _events_for_run(t010_session_factory, run_id)
        assert [event.sequence for event in events] == [1, 2, 3, 4]
        assert [event.kind for event in events] == [
            RunEventKind.RUN_QUEUED,
            RunEventKind.RUN_STARTED,
            RunEventKind.UI_ENVELOPE,
            RunEventKind.RUN_COMPLETED,
        ]
        assert events[0].payload == {"status": "queued"}
        assert events[1].payload == {"status": "running"}
        assert events[3].payload == {"status": "completed"}
        for event in events:
            TypeAdapter(RunEventContract).validate_python(_event_document(event))
            assert event.workspace_id == workspace_id
            assert event.payload_schema_version == "1.0"
            assert LOWERCASE_SHA256.fullmatch(event.payload_hash)

        envelope = events[2].payload
        UiEnvelope.model_validate(envelope)
        serialized = json.dumps(envelope, ensure_ascii=False, sort_keys=True)
        assert marker not in serialized
        for disallowed_key in ('"citations"', '"html"', '"script"', '"url"'):
            assert disallowed_key not in serialized
        component = cast(JsonObject, envelope["component"])
        assert component["kind"] == "recommendation-summary"
        assert component["status"] == "demonstration"
        assert "demonstration" in cast(str, component["disclaimer"]).lower()
        assert component["selectedOptionId"] in {
            "managed-platform",
            "self-hosted",
        }
        option_scores = cast(list[JsonObject], component["optionScores"])
        assert {score["optionId"] for score in option_scores} == {
            "managed-platform",
            "self-hosted",
        }
        actions = cast(list[JsonObject], envelope["actions"])
        assert all(
            action["kind"] == "view-evidence" and action["enabled"] is False
            for action in actions
        )
        meta = cast(JsonObject, envelope["meta"])
        assert meta == {
            "runId": str(run_id),
            "eventSequence": 3,
            "generatedBy": "deterministic-fixture",
            "fixtureVersion": FIXTURE_VERSION,
        }
        envelopes.append(envelope)

        snapshot = await _get_run(app, str(run_id), cookie=cookie)
        assert snapshot.status == 200
        RunView.model_validate(snapshot.json())
        assert snapshot.json()["status"] == "completed"
        assert snapshot.json()["lastEventSequence"] == 4
        assert snapshot.json()["fixtureVersion"] == FIXTURE_VERSION
        assert snapshot.json()["startedAt"] is not None
        assert snapshot.json()["completedAt"] is not None
        assert snapshot.json()["errorCode"] is None

    first = envelopes[0]
    second = envelopes[1]
    assert first["component"] == second["component"]
    assert first["actions"] == second["actions"]

    async with t010_session_factory() as session:
        runs = list(
            (
                await session.scalars(
                    select(Run).where(Run.id.in_(run_ids)).order_by(Run.id)
                )
            ).all()
        )
        jobs = list(
            (
                await session.scalars(
                    select(Job).where(
                        Job.workspace_id == workspace_id,
                        Job.kind == JobKind.EXECUTE_RUN,
                    )
                )
            ).all()
        )
    assert len(runs) == 2
    assert all(run.status is RunStatus.COMPLETED for run in runs)
    assert all(run.last_event_sequence == 4 for run in runs)
    assert all(run.terminal_event_sequence == 4 for run in runs)
    assert all(run.started_at == NOW for run in runs)
    assert all(run.completed_at == NOW for run in runs)
    assert all(run.error_code is None for run in runs)
    assert len(jobs) == 2
    assert all(job.status is JobStatus.COMPLETED for job in jobs)
    assert all(job.attempt_count == 1 for job in jobs)
    assert all(job.lease_owner is None for job in jobs)
    assert all(job.lease_expires_at is None for job in jobs)
    assert all(job.last_error_code is None for job in jobs)
    assert all(job.completed_at == NOW for job in jobs)


class _MalformedEnvelopeFactory:
    def __call__(self, *_args: object, **_kwargs: object) -> JsonObject:
        return {
            "schemaVersion": "1.0",
            "component": {
                "kind": "arbitrary-html",
                "html": "<script>must-never-be-persisted</script>",
            },
            "actions": [],
            "validatorDiagnostics": "must-never-be-persisted",
        }


@pytest.mark.asyncio
async def test_worker_rejects_malformed_envelope_before_insertion_and_fails_closed(
    t010_postgres_url: str,
    t010_session_factory: SessionFactory,
) -> None:
    app, cookie, workspace_id, _ = await _app_and_guest(
        t010_postgres_url,
        t010_session_factory,
    )
    decision = await _create_decision(
        app,
        cookie=cookie,
        key="malformed-envelope-decision-016",
    )
    assert decision.status == 201
    decision_id = cast(str, decision.json()["id"])
    created = await _post_run(
        app,
        decision_id,
        cookie=cookie,
        idempotency_key="malformed-envelope-run-016",
        expected_revision=1,
    )
    assert created.status == 202
    run_id = _uuid7(created.json()["id"])

    process_one_job = _process_one_job()
    assert await process_one_job(
        session_factory=t010_session_factory,
        worker_id="t016-malformed-worker",
        now=NOW,
        envelope_factory=_MalformedEnvelopeFactory(),
    )

    events = await _events_for_run(t010_session_factory, run_id)
    assert [event.sequence for event in events] == [1, 2, 3]
    assert [event.kind for event in events] == [
        RunEventKind.RUN_QUEUED,
        RunEventKind.RUN_STARTED,
        RunEventKind.RUN_FAILED,
    ]
    assert events[-1].payload == {
        "status": "failed",
        "errorCode": "invalid_ui_envelope",
    }
    assert all(event.kind is not RunEventKind.UI_ENVELOPE for event in events)
    assert "must-never-be-persisted" not in json.dumps(
        [event.payload for event in events],
        sort_keys=True,
    )
    for event in events:
        TypeAdapter(RunEventContract).validate_python(_event_document(event))

    async with t010_session_factory() as session:
        run = await session.get(Run, run_id)
        job = await session.scalar(
            select(Job).where(
                Job.workspace_id == workspace_id,
                Job.kind == JobKind.EXECUTE_RUN,
                Job.payload == {"runId": str(run_id)},
            )
        )
    assert run is not None
    assert run.status is RunStatus.FAILED
    assert run.last_event_sequence == 3
    assert run.terminal_event_sequence == 3
    assert run.started_at == NOW
    assert run.completed_at == NOW
    assert run.error_code == "invalid_ui_envelope"
    assert job is not None
    assert job.status is JobStatus.FAILED
    assert job.attempt_count == 1
    assert job.lease_owner is None
    assert job.lease_expires_at is None
    assert job.last_error_code == "invalid_ui_envelope"
    assert job.completed_at == NOW

    snapshot = await _get_run(app, str(run_id), cookie=cookie)
    assert snapshot.status == 200
    assert snapshot.json()["status"] == "failed"
    assert snapshot.json()["lastEventSequence"] == 3
    assert snapshot.json()["errorCode"] == "invalid_ui_envelope"
