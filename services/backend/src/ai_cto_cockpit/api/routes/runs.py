from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Annotated, cast

from fastapi import APIRouter, Header, Path, Query, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_cto_cockpit.api.dependencies.context import (
    WorkspaceContext,
    WorkspaceContextUnauthorized,
    resolve_workspace_context,
)
from ai_cto_cockpit.api.errors import api_error_response
from ai_cto_cockpit.api.headers import ExpectedRevision, IdempotencyKey
from ai_cto_cockpit.contracts._base import UUID7_PATTERN
from ai_cto_cockpit.contracts.run import RunView
from ai_cto_cockpit.domain.idempotency import (
    advisory_lock_id,
    canonical_json,
    normalized_request_hash,
    request_hash_matches,
)
from ai_cto_cockpit.domain.ids import new_uuid7, parse_uuid7
from ai_cto_cockpit.persistence.models import (
    DecisionRevision,
    IdempotencyRecord,
    Job,
    JobKind,
    JobStatus,
    Run,
    RunEvent,
    RunEventKind,
    RunStatus,
)
from ai_cto_cockpit.persistence.repositories import (
    DecisionRepository,
    IdempotencyRepository,
    WorkspaceRepository,
)
from ai_cto_cockpit.runs.fake_graph import FIXTURE_VERSION
from ai_cto_cockpit.runs.service import (
    RunStreamPolicy,
    event_payload_hash,
    load_run_projection,
    revision_snapshot_document,
    run_view_document,
    stream_persisted_events,
    validated_event_document,
)
from ai_cto_cockpit.security.guest_session import COOKIE_NAME, GuestSessionCodec
from ai_cto_cockpit.settings import Settings

router = APIRouter(tags=["runs"])

_CREATE_OPERATION = "create-run-v1"
_PERSISTENT_EXPIRY = datetime.max.replace(tzinfo=UTC)

type Clock = Callable[[], datetime]
type DatabaseClock = Callable[[AsyncSession], Awaitable[datetime]]
type JsonObject = dict[str, object]
type SessionFactory = async_sessionmaker[AsyncSession]
type DecisionPathId = Annotated[str, Path(pattern=UUID7_PATTERN)]
type RunPathId = Annotated[str, Path(pattern=UUID7_PATTERN)]
type AfterSequence = Annotated[int, Query(alias="afterSequence", ge=0)]
type LastEventId = Annotated[int | None, Header(alias="Last-Event-ID", ge=0)]


class _IdempotencyConflict(ValueError):
    pass


class _RevisionConflict(ValueError):
    pass


class _ResourceNotFound(LookupError):
    pass


def _json_response(
    document: JsonObject,
    *,
    status: int,
    location: str | None = None,
) -> Response:
    headers = {"Location": location} if location is not None else None
    return Response(
        content=canonical_json(document),
        status_code=status,
        media_type="application/json",
        headers=headers,
    )


def _idempotency_error() -> JSONResponse:
    return api_error_response(
        409,
        code="idempotency_conflict",
        message="The idempotency key was already used for a different request.",
    )


def _revision_error() -> JSONResponse:
    return api_error_response(
        409,
        code="revision_conflict",
        message="The decision revision changed; fetch the current decision.",
    )


def _not_found_error() -> JSONResponse:
    return api_error_response(
        404,
        code="resource_not_found",
        message="The requested resource was not found.",
    )


def _unauthorized_error() -> JSONResponse:
    return api_error_response(
        401,
        code="session_unauthorized",
        message="A valid workspace session is required.",
    )


def _context_time(request: Request) -> datetime:
    value = cast(Clock, request.app.state.clock)()
    if value.tzinfo is None or value.utcoffset() is None:
        raise RuntimeError("Application clock must be timezone-aware")
    return value


async def _database_time(request: Request, session: AsyncSession) -> datetime:
    provider = cast(DatabaseClock | None, request.app.state.database_clock)
    value = (
        await provider(session)
        if provider is not None
        else await session.scalar(select(func.clock_timestamp()))
    )
    if value is None or value.tzinfo is None or value.utcoffset() is None:
        raise RuntimeError("PostgreSQL must supply a timezone-aware timestamp")
    return value


async def _workspace_context(request: Request) -> WorkspaceContext:
    settings = cast(Settings, request.app.state.settings)
    session_factory = cast(SessionFactory, request.app.state.session_factory)
    codec = cast(GuestSessionCodec, request.app.state.guest_session_codec)
    return await resolve_workspace_context(
        cookie_value=request.cookies.get(COOKIE_NAME),
        settings=settings,
        session_factory=session_factory,
        codec=codec,
        now=_context_time(request),
    )


async def _lock_workspace(
    session: AsyncSession,
    *,
    context: WorkspaceContext,
    now: datetime,
) -> None:
    workspace = await WorkspaceRepository(session).lock_active(
        workspace_id=context.workspace_id,
        kind=context.kind,
        now=now,
    )
    if workspace is None:
        raise WorkspaceContextUnauthorized("Workspace is no longer active")


def _record_expiry(context: WorkspaceContext) -> datetime:
    return context.expires_at or _PERSISTENT_EXPIRY


@router.post(
    "/api/v1/decisions/{decision_id}/runs",
    status_code=202,
    response_model=RunView,
)
async def create_run(
    request: Request,
    decision_id: DecisionPathId,
    idempotency_key: IdempotencyKey,
    expected_revision: ExpectedRevision,
) -> Response:
    parsed_decision_id = parse_uuid7(decision_id)
    try:
        context = await _workspace_context(request)
        now = _context_time(request)
        path = f"/api/v1/decisions/{parsed_decision_id}/runs"
        request_hash = normalized_request_hash(
            operation=_CREATE_OPERATION,
            method="POST",
            path=path,
            body={},
            expected_revision=expected_revision,
        )
        factory = cast(SessionFactory, request.app.state.session_factory)
        result_body: JsonObject
        result_id: uuid.UUID
        async with factory.begin() as session:
            idempotency = IdempotencyRepository(session)
            await idempotency.acquire_transaction_lock(
                lock_id=advisory_lock_id(
                    workspace_id=context.workspace_id,
                    operation=_CREATE_OPERATION,
                    key=idempotency_key,
                )
            )
            await _lock_workspace(session, context=context, now=now)
            existing = await idempotency.get(
                workspace_id=context.workspace_id,
                operation=_CREATE_OPERATION,
                key=idempotency_key,
                now=now,
            )
            if existing is not None:
                if not request_hash_matches(existing.request_hash, request_hash):
                    raise _IdempotencyConflict
                if existing.resource_id is None:
                    raise RuntimeError("Stored run replay has no resource identity")
                result_body = existing.response_body
                result_id = existing.resource_id
            else:
                decision = await DecisionRepository(session).get(
                    workspace_id=context.workspace_id,
                    decision_id=parsed_decision_id,
                    for_update=True,
                )
                if decision is None:
                    raise _ResourceNotFound
                if decision.current_revision != expected_revision:
                    raise _RevisionConflict
                revision = await session.scalar(
                    select(DecisionRevision).where(
                        DecisionRevision.workspace_id == context.workspace_id,
                        DecisionRevision.decision_id == parsed_decision_id,
                        DecisionRevision.revision == expected_revision,
                    )
                )
                if revision is None:
                    raise RuntimeError("Decision current revision is unavailable")

                database_now = await _database_time(request, session)
                snapshot = revision_snapshot_document(revision)
                run = Run(
                    id=new_uuid7(),
                    workspace_id=context.workspace_id,
                    decision_id=parsed_decision_id,
                    decision_revision_id=revision.id,
                    status=RunStatus.QUEUED,
                    fixture_version=FIXTURE_VERSION,
                    input_snapshot=snapshot,
                    input_snapshot_hash=revision.snapshot_hash,
                    last_event_sequence=1,
                    terminal_event_sequence=None,
                    error_code=None,
                    created_at=database_now,
                    started_at=None,
                    completed_at=None,
                )
                queued_payload: JsonObject = {"status": "queued"}
                queued_document = validated_event_document(
                    run_id=run.id,
                    sequence=1,
                    kind=RunEventKind.RUN_QUEUED,
                    payload=queued_payload,
                    created_at=database_now,
                )
                validated_queued_payload = cast(
                    JsonObject,
                    queued_document["payload"],
                )
                queued_event = RunEvent(
                    id=new_uuid7(),
                    workspace_id=context.workspace_id,
                    run_id=run.id,
                    sequence=1,
                    kind=RunEventKind.RUN_QUEUED,
                    payload_schema_version="1.0",
                    payload=validated_queued_payload,
                    payload_hash=event_payload_hash(validated_queued_payload),
                    created_at=database_now,
                )
                job = Job(
                    id=new_uuid7(),
                    workspace_id=context.workspace_id,
                    kind=JobKind.EXECUTE_RUN,
                    payload={"runId": str(run.id)},
                    status=JobStatus.AVAILABLE,
                    available_at=database_now,
                    lease_owner=None,
                    lease_expires_at=None,
                    attempt_count=0,
                    last_error_code=None,
                    created_at=database_now,
                    updated_at=database_now,
                    completed_at=None,
                )
                result_body = run_view_document(
                    run,
                    decision_revision=revision.revision,
                )
                result_id = run.id
                record = IdempotencyRecord(
                    id=new_uuid7(),
                    workspace_id=context.workspace_id,
                    operation=_CREATE_OPERATION,
                    key=idempotency_key,
                    request_hash=request_hash,
                    response_status=202,
                    response_body=result_body,
                    resource_id=run.id,
                    expires_at=_record_expiry(context),
                    created_at=database_now,
                )
                session.add_all((run, queued_event, job, record))
                await session.flush()

        location = f"/api/v1/runs/{result_id}"
        return _json_response(result_body, status=202, location=location)
    except WorkspaceContextUnauthorized:
        return _unauthorized_error()
    except _IdempotencyConflict:
        return _idempotency_error()
    except _RevisionConflict:
        return _revision_error()
    except _ResourceNotFound:
        return _not_found_error()


@router.get("/api/v1/runs/{run_id}", response_model=RunView)
async def get_run(request: Request, run_id: RunPathId) -> Response:
    try:
        context = await _workspace_context(request)
    except WorkspaceContextUnauthorized:
        return _unauthorized_error()

    factory = cast(SessionFactory, request.app.state.session_factory)
    async with factory() as session:
        projection = await load_run_projection(
            session,
            workspace_id=context.workspace_id,
            run_id=parse_uuid7(run_id),
        )
    if projection is None:
        return _not_found_error()
    return _json_response(
        run_view_document(
            projection.run,
            decision_revision=projection.decision_revision,
        ),
        status=200,
    )


@router.get("/api/v1/runs/{run_id}/events")
async def stream_run_events(
    request: Request,
    run_id: RunPathId,
    after_sequence: AfterSequence = 0,
    last_event_id: LastEventId = None,
) -> Response:
    try:
        context = await _workspace_context(request)
    except WorkspaceContextUnauthorized:
        return _unauthorized_error()

    parsed_run_id = parse_uuid7(run_id)
    factory = cast(SessionFactory, request.app.state.session_factory)
    async with factory() as session:
        projection = await load_run_projection(
            session,
            workspace_id=context.workspace_id,
            run_id=parsed_run_id,
        )
    if projection is None:
        return _not_found_error()

    policy = cast(
        RunStreamPolicy,
        getattr(request.app.state, "run_stream_policy", RunStreamPolicy()),
    )
    cursor = last_event_id if last_event_id is not None else after_sequence

    async def authorize_stream() -> bool:
        try:
            current = await _workspace_context(request)
        except WorkspaceContextUnauthorized:
            return False
        return current.workspace_id == context.workspace_id

    return StreamingResponse(
        stream_persisted_events(
            session_factory=factory,
            workspace_id=context.workspace_id,
            run_id=parsed_run_id,
            after_sequence=cursor,
            policy=policy,
            authorize=authorize_stream,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
