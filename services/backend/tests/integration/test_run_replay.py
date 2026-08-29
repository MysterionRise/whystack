from __future__ import annotations

import importlib
import json
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

import pytest
from fastapi import FastAPI
from pydantic import TypeAdapter
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_cto_cockpit.contracts.run import RunEvent as RunEventContract
from ai_cto_cockpit.main import create_app
from ai_cto_cockpit.persistence.models import (
    DecisionRevision,
    GuestSession,
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
from tests.support.streaming import AsgiStreamResponse, asgi_stream_request

NOW = datetime(2026, 8, 15, 9, 30, tzinfo=UTC)
SIGNING_KEY = "t017-session-signing-key-with-more-than-thirty-two-bytes"
SEED_ID = uuid.UUID("0198b0f0-0000-7000-8000-000000000001")
LOCAL_ID = uuid.UUID("0198b0f0-0000-7000-8000-000000000002")
MISSING_RUN_ID = "0198b0f0-0000-7000-8000-00000000d017"
EXPECTED_EVENT_KINDS = (
    "run.queued",
    "run.started",
    "ui.envelope",
    "run.completed",
)

type JsonObject = dict[str, object]
type SessionFactory = async_sessionmaker[AsyncSession]


@dataclass(frozen=True, slots=True)
class SseFrame:
    raw: bytes
    event_id: int | None
    event: str | None
    data: JsonObject | None
    comment: str | None


@dataclass(frozen=True, slots=True)
class RunEffects:
    status: RunStatus
    last_event_sequence: int
    terminal_event_sequence: int | None
    events: tuple[tuple[int, RunEventKind], ...]
    job_status: JobStatus
    revision_count: int


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


def _frame(question: str) -> JsonObject:
    return {
        "schemaVersion": "1.0",
        "question": question,
        "context": "Exercise durable replay without retrieval or a model provider.",
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
            {"id": "cost", "label": "Cost", "enteredWeight": "1.00"},
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


def _uuid7(value: object) -> uuid.UUID:
    assert isinstance(value, str)
    parsed = uuid.UUID(value)
    assert parsed.version == 7
    assert str(parsed) == value
    return parsed


async def _new_guest(
    app: FastAPI,
    factory: SessionFactory,
) -> tuple[str, uuid.UUID]:
    response = await asgi_request(app, method="GET", path="/api/v1/config")
    assert response.status == 200
    set_cookie = response.header("set-cookie")
    assert set_cookie is not None
    cookie = _cookie_value(set_cookie)
    codec = cast(GuestSessionCodec, app.state.guest_session_codec)
    claims = codec.verify(cookie, now=NOW)
    async with factory() as session:
        guest_session = await session.get(GuestSession, claims.session_id)
        assert guest_session is not None
        workspace_id = guest_session.workspace_id
    return cookie, workspace_id


async def _create_decision(app: FastAPI, *, cookie: str, key: str) -> JsonObject:
    response = await asgi_request(
        app,
        method="POST",
        path="/api/v1/decisions",
        headers=(
            ("Content-Type", "application/json"),
            ("Cookie", f"ai_cto_guest={cookie}"),
            ("Idempotency-Key", key),
        ),
        body=_json_body(_frame("Which replay-safe architecture should we choose?")),
    )
    assert response.status == 201
    return response.json()


async def _create_run(
    app: FastAPI,
    *,
    cookie: str,
    decision_id: str,
    revision: int,
    key: str,
) -> AsgiResponse:
    return await asgi_request(
        app,
        method="POST",
        path=f"/api/v1/decisions/{decision_id}/runs",
        headers=(
            ("Cookie", f"ai_cto_guest={cookie}"),
            ("Idempotency-Key", key),
            ("If-Match", str(revision)),
        ),
    )


async def _new_run(
    app: FastAPI,
    *,
    cookie: str,
    key_suffix: str,
) -> tuple[str, int]:
    decision = await _create_decision(
        app,
        cookie=cookie,
        key=f"replay-decision-{key_suffix}",
    )
    decision_id = cast(str, decision["id"])
    revision = cast(int, decision["currentRevision"])
    response = await _create_run(
        app,
        cookie=cookie,
        decision_id=decision_id,
        revision=revision,
        key=f"replay-run-{key_suffix}",
    )
    assert response.status == 202
    payload = response.json()
    run_id = payload.get("id")
    _uuid7(run_id)
    assert payload["status"] == "queued"
    assert payload["lastEventSequence"] == 1
    return cast(str, run_id), revision


def _runtime_symbol(module_name: str, symbol_name: str) -> object:
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as error:
        pytest.fail(
            f"T017 RED: runtime module {module_name!r} is not implemented: {error}"
        )
    symbol = getattr(module, symbol_name, None)
    assert symbol is not None, (
        f"T017 RED: runtime symbol {module_name}.{symbol_name} is not implemented"
    )
    return symbol


async def _process_one_job(
    factory: SessionFactory,
    *,
    worker_id: str,
) -> None:
    process = cast(
        Callable[..., Awaitable[object]],
        _runtime_symbol("ai_cto_cockpit.worker", "process_one_job"),
    )
    await process(session_factory=factory, worker_id=worker_id, now=NOW)


def _fast_stream_policy() -> object:
    policy_type = cast(
        Callable[..., object],
        _runtime_symbol("ai_cto_cockpit.runs.service", "RunStreamPolicy"),
    )
    return policy_type(
        poll_interval_seconds=0.001,
        heartbeat_interval_seconds=0.001,
    )


def _app(
    database_url: str,
    factory: SessionFactory,
    *,
    run_stream_policy: object | None = None,
) -> FastAPI:
    factory_function = cast(Callable[..., FastAPI], create_app)
    arguments: dict[str, object] = {
        "settings": _settings(database_url),
        "session_factory": factory,
        "clock": lambda: NOW,
    }
    if run_stream_policy is not None:
        arguments["run_stream_policy"] = run_stream_policy
    return factory_function(**arguments)


def _parse_sse(body: bytes) -> tuple[SseFrame, ...]:
    if not body:
        return ()
    assert b"\r" not in body
    assert body.endswith(b"\n\n")
    raw_frames = body[:-2].split(b"\n\n")
    frames: list[SseFrame] = []
    for raw in raw_frames:
        lines = raw.split(b"\n")
        if lines[0].startswith(b":"):
            assert lines == [b": heartbeat"]
            frames.append(
                SseFrame(
                    raw=raw,
                    event_id=None,
                    event=None,
                    data=None,
                    comment="heartbeat",
                )
            )
            continue

        assert len(lines) == 3
        assert lines[0].startswith(b"id: ")
        assert lines[1].startswith(b"event: ")
        assert lines[2].startswith(b"data: ")
        event_id = int(lines[0].removeprefix(b"id: "))
        event = lines[1].removeprefix(b"event: ").decode("ascii")
        value = json.loads(lines[2].removeprefix(b"data: "))
        assert isinstance(value, dict)
        frames.append(
            SseFrame(
                raw=raw,
                event_id=event_id,
                event=event,
                data=cast(JsonObject, value),
                comment=None,
            )
        )
    return tuple(frames)


def _assert_stream_headers(response: AsgiStreamResponse) -> None:
    assert response.status == 200
    content_type = response.header("content-type")
    assert content_type is not None
    assert content_type.split(";", 1)[0] == "text/event-stream"
    assert response.header("cache-control") == "no-cache, no-transform"


def _assert_valid_events(
    frames: tuple[SseFrame, ...],
    *,
    run_id: str,
    expected_sequences: tuple[int, ...],
) -> None:
    assert tuple(frame.event_id for frame in frames) == expected_sequences
    adapter: TypeAdapter[RunEventContract] = TypeAdapter(RunEventContract)
    for frame in frames:
        assert frame.comment is None
        assert frame.data is not None
        assert set(frame.data) == {
            "runId",
            "sequence",
            "kind",
            "schemaVersion",
            "payload",
            "createdAt",
        }
        event = adapter.validate_python(frame.data)
        assert event.run_id == run_id
        assert event.sequence == frame.event_id
        assert event.kind == frame.event
        assert event.schema_version == "1.0"

    for frame in frames:
        if frame.event != "ui.envelope":
            continue
        assert frame.data is not None
        payload = cast(JsonObject, frame.data["payload"])
        meta = cast(JsonObject, payload["meta"])
        assert payload["schemaVersion"] == "1.0"
        assert cast(JsonObject, payload["component"])["kind"] == (
            "recommendation-summary"
        )
        assert meta["runId"] == run_id
        assert meta["eventSequence"] == frame.event_id


async def _stream(
    app: FastAPI,
    *,
    cookie: str,
    run_id: str,
    after_sequence: int,
    last_event_id: int | None = None,
    disconnect_after_body_chunks: int | None = None,
) -> AsgiStreamResponse:
    headers = [
        ("Accept", "text/event-stream"),
        ("Cookie", f"ai_cto_guest={cookie}"),
    ]
    if last_event_id is not None:
        headers.append(("Last-Event-ID", str(last_event_id)))
    return await asgi_stream_request(
        app,
        path=f"/api/v1/runs/{run_id}/events",
        query=f"afterSequence={after_sequence}",
        headers=headers,
        disconnect_after_body_chunks=disconnect_after_body_chunks,
    )


async def _run_effects(factory: SessionFactory, run_id: str) -> RunEffects:
    parsed_run_id = uuid.UUID(run_id)
    async with factory() as session:
        run = await session.get(Run, parsed_run_id)
        assert run is not None
        events = tuple(
            (
                event.sequence,
                event.kind,
            )
            for event in (
                await session.scalars(
                    select(RunEvent)
                    .where(RunEvent.run_id == parsed_run_id)
                    .order_by(RunEvent.sequence)
                )
            ).all()
        )
        job = await session.scalar(
            select(Job).where(
                Job.workspace_id == run.workspace_id,
                Job.kind == JobKind.EXECUTE_RUN,
            )
        )
        assert job is not None
        revision_count = int(
            await session.scalar(select(func.count(DecisionRevision.id))) or 0
        )
        return RunEffects(
            status=run.status,
            last_event_sequence=run.last_event_sequence,
            terminal_event_sequence=run.terminal_event_sequence,
            events=events,
            job_status=job.status,
            revision_count=revision_count,
        )


def _error_projection(response: AsgiResponse) -> JsonObject:
    assert response.status == 404
    payload = response.json()
    assert set(payload) == {"code", "message", "correlationId", "fields"}
    _uuid7(payload["correlationId"])
    return {
        "code": payload["code"],
        "message": payload["message"],
        "fields": payload["fields"],
    }


@pytest.mark.asyncio
async def test_terminal_run_replays_every_cursor_and_survives_api_restart(
    t010_postgres_url: str,
    t010_session_factory: SessionFactory,
) -> None:
    app = _app(t010_postgres_url, t010_session_factory)
    cookie, _workspace_id = await _new_guest(app, t010_session_factory)
    run_id, _revision = await _new_run(
        app,
        cookie=cookie,
        key_suffix="cursor-017",
    )
    await _process_one_job(t010_session_factory, worker_id="replay-worker-017")

    full = await _stream(
        app,
        cookie=cookie,
        run_id=run_id,
        after_sequence=0,
    )
    _assert_stream_headers(full)
    full_frames = _parse_sse(full.body)
    assert tuple(frame.event for frame in full_frames) == EXPECTED_EVENT_KINDS
    _assert_valid_events(
        full_frames,
        run_id=run_id,
        expected_sequences=(1, 2, 3, 4),
    )

    for cursor in range(5):
        replay = await _stream(
            app,
            cookie=cookie,
            run_id=run_id,
            after_sequence=cursor,
        )
        _assert_stream_headers(replay)
        frames = _parse_sse(replay.body)
        expected_sequences = tuple(range(cursor + 1, 5))
        _assert_valid_events(
            frames,
            run_id=run_id,
            expected_sequences=expected_sequences,
        )
        assert tuple(frame.raw for frame in frames) == tuple(
            frame.raw for frame in full_frames[cursor:]
        )

    restarted = _app(t010_postgres_url, t010_session_factory)
    after_restart = await _stream(
        restarted,
        cookie=cookie,
        run_id=run_id,
        after_sequence=1,
    )
    _assert_stream_headers(after_restart)
    restarted_frames = _parse_sse(after_restart.body)
    assert tuple(frame.raw for frame in restarted_frames) == tuple(
        frame.raw for frame in full_frames[1:]
    )
    assert await _run_effects(t010_session_factory, run_id) == RunEffects(
        status=RunStatus.COMPLETED,
        last_event_sequence=4,
        terminal_event_sequence=4,
        events=(
            (1, RunEventKind.RUN_QUEUED),
            (2, RunEventKind.RUN_STARTED),
            (3, RunEventKind.UI_ENVELOPE),
            (4, RunEventKind.RUN_COMPLETED),
        ),
        job_status=JobStatus.COMPLETED,
        revision_count=1,
    )


@pytest.mark.asyncio
async def test_last_event_id_precedes_query_and_terminal_replay_is_empty(
    t010_postgres_url: str,
    t010_session_factory: SessionFactory,
) -> None:
    app = _app(t010_postgres_url, t010_session_factory)
    cookie, _workspace_id = await _new_guest(app, t010_session_factory)
    run_id, _revision = await _new_run(
        app,
        cookie=cookie,
        key_suffix="precedence-017",
    )
    await _process_one_job(t010_session_factory, worker_id="precedence-worker-017")

    precedence = await _stream(
        app,
        cookie=cookie,
        run_id=run_id,
        after_sequence=0,
        last_event_id=2,
    )
    _assert_stream_headers(precedence)
    precedence_frames = _parse_sse(precedence.body)
    assert tuple(frame.event for frame in precedence_frames) == (
        "ui.envelope",
        "run.completed",
    )
    _assert_valid_events(
        precedence_frames,
        run_id=run_id,
        expected_sequences=(3, 4),
    )

    empty = await _stream(
        app,
        cookie=cookie,
        run_id=run_id,
        after_sequence=0,
        last_event_id=4,
    )
    _assert_stream_headers(empty)
    assert empty.body == b""
    assert _parse_sse(empty.body) == ()


@pytest.mark.asyncio
async def test_heartbeat_disconnect_has_no_effect_and_does_not_cancel_run(
    t010_postgres_url: str,
    t010_session_factory: SessionFactory,
) -> None:
    app = _app(
        t010_postgres_url,
        t010_session_factory,
        run_stream_policy=_fast_stream_policy(),
    )
    cookie, _workspace_id = await _new_guest(app, t010_session_factory)
    run_id, _revision = await _new_run(
        app,
        cookie=cookie,
        key_suffix="disconnect-017",
    )
    before_disconnect = await _run_effects(t010_session_factory, run_id)

    waiting_stream = await _stream(
        app,
        cookie=cookie,
        run_id=run_id,
        after_sequence=1,
        disconnect_after_body_chunks=1,
    )
    _assert_stream_headers(waiting_stream)
    assert waiting_stream.client_disconnected is True
    assert _parse_sse(waiting_stream.body) == (
        SseFrame(
            raw=b": heartbeat",
            event_id=None,
            event=None,
            data=None,
            comment="heartbeat",
        ),
    )
    assert await _run_effects(t010_session_factory, run_id) == before_disconnect

    await _process_one_job(t010_session_factory, worker_id="disconnect-worker-017")
    after_worker = await _run_effects(t010_session_factory, run_id)
    assert after_worker.status == RunStatus.COMPLETED
    assert after_worker.last_event_sequence == 4
    assert after_worker.terminal_event_sequence == 4
    assert tuple(sequence for sequence, _kind in after_worker.events) == (1, 2, 3, 4)
    assert after_worker.job_status == JobStatus.COMPLETED
    assert after_worker.revision_count == before_disconnect.revision_count


@pytest.mark.asyncio
async def test_run_stream_and_snapshot_use_uniform_cross_scope_not_found(
    t010_postgres_url: str,
    t010_session_factory: SessionFactory,
) -> None:
    app = _app(t010_postgres_url, t010_session_factory)
    owner_cookie, _owner_workspace_id = await _new_guest(
        app,
        t010_session_factory,
    )
    other_cookie, _other_workspace_id = await _new_guest(
        app,
        t010_session_factory,
    )
    run_id, _revision = await _new_run(
        app,
        cookie=owner_cookie,
        key_suffix="scope-017",
    )
    before = await _run_effects(t010_session_factory, run_id)

    responses: list[AsgiResponse] = []
    for candidate in (run_id, MISSING_RUN_ID):
        responses.append(
            await asgi_request(
                app,
                method="GET",
                path=f"/api/v1/runs/{candidate}",
                headers=(("Cookie", f"ai_cto_guest={other_cookie}"),),
            )
        )
        responses.append(
            await asgi_request(
                app,
                method="GET",
                path=f"/api/v1/runs/{candidate}/events",
                query="afterSequence=0",
                headers=(
                    ("Accept", "text/event-stream"),
                    ("Cookie", f"ai_cto_guest={other_cookie}"),
                ),
            )
        )

    projections = tuple(_error_projection(response) for response in responses)
    assert (
        projections
        == (
            {
                "code": "resource_not_found",
                "message": "The requested resource was not found.",
                "fields": [],
            },
        )
        * 4
    )
    assert await _run_effects(t010_session_factory, run_id) == before
