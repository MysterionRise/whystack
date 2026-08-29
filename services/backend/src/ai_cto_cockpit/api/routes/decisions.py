from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Annotated, cast

from fastapi import APIRouter, Path, Request
from fastapi.responses import JSONResponse, Response
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
from ai_cto_cockpit.contracts.decision import (
    DecisionFrameInput,
    DecisionFrameView,
    DecisionView,
)
from ai_cto_cockpit.domain.idempotency import (
    advisory_lock_id,
    canonical_json,
    normalized_request_hash,
    request_hash_matches,
)
from ai_cto_cockpit.domain.ids import new_uuid7, parse_uuid7
from ai_cto_cockpit.domain.revisions import normalize_frame, snapshot_hash
from ai_cto_cockpit.persistence.models import (
    Decision,
    DecisionRevision,
    IdempotencyRecord,
)
from ai_cto_cockpit.persistence.repositories import (
    DecisionRepository,
    IdempotencyRepository,
    WorkspaceRepository,
)
from ai_cto_cockpit.security.guest_session import COOKIE_NAME, GuestSessionCodec
from ai_cto_cockpit.settings import Settings

router = APIRouter(prefix="/api/v1/decisions", tags=["decisions"])

_CREATE_OPERATION = "create-decision-v1"
_REVISE_OPERATION = "revise-decision-v1"
_PERSISTENT_EXPIRY = datetime.max.replace(tzinfo=UTC)

type Clock = Callable[[], datetime]
type DatabaseClock = Callable[[AsyncSession], Awaitable[datetime]]
type JsonObject = dict[str, object]
type SessionFactory = async_sessionmaker[AsyncSession]
type DecisionPathId = Annotated[str, Path(pattern=UUID7_PATTERN)]


class _IdempotencyConflict(ValueError):
    pass


class _RevisionConflict(ValueError):
    pass


class _ResourceNotFound(LookupError):
    pass


def _json_response(document: JsonObject, *, status: int) -> Response:
    return Response(
        content=canonical_json(document),
        status_code=status,
        media_type="application/json",
    )


def _view_document(view: DecisionView) -> JsonObject:
    return cast(JsonObject, view.model_dump(mode="json", by_alias=True))


def _frame_document(frame: DecisionFrameInput) -> JsonObject:
    return cast(JsonObject, frame.model_dump(mode="json", by_alias=True))


def _stored_frame(revision: DecisionRevision) -> DecisionFrameView:
    return DecisionFrameView.model_validate(
        {
            "schemaVersion": revision.frame_schema_version,
            "question": revision.question,
            "context": revision.context,
            "options": revision.options,
            "criteria": revision.criteria,
            "constraints": revision.constraints,
        }
    )


def _decision_view(
    decision: Decision,
    *,
    frame: DecisionFrameView,
) -> DecisionView:
    return DecisionView.model_validate(
        {
            "id": str(decision.id),
            "currentRevision": decision.current_revision,
            "frame": frame.model_dump(mode="json", by_alias=True),
            "createdAt": decision.created_at,
            "updatedAt": decision.updated_at,
        }
    )


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
    clock = cast(Clock, request.app.state.clock)
    return await resolve_workspace_context(
        cookie_value=request.cookies.get(COOKIE_NAME),
        settings=settings,
        session_factory=session_factory,
        codec=codec,
        now=clock(),
    )


def _context_time(request: Request) -> datetime:
    value = cast(Clock, request.app.state.clock)()
    if value.tzinfo is None or value.utcoffset() is None:
        raise RuntimeError("Application clock must be timezone-aware")
    return value


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


def _revision_model(
    *,
    workspace_id: uuid.UUID,
    decision_id: uuid.UUID,
    revision: int,
    frame: DecisionFrameView,
    created_at: datetime,
) -> DecisionRevision:
    document = cast(JsonObject, frame.model_dump(mode="json", by_alias=True))
    return DecisionRevision(
        id=new_uuid7(),
        workspace_id=workspace_id,
        decision_id=decision_id,
        revision=revision,
        frame_schema_version=cast(str, document["schemaVersion"]),
        question=cast(str, document["question"]),
        context=cast(str, document["context"]),
        options=cast(list[JsonObject], document["options"]),
        criteria=cast(list[JsonObject], document["criteria"]),
        constraints=cast(list[JsonObject], document["constraints"]),
        snapshot_hash=snapshot_hash(frame),
        created_at=created_at,
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


@router.post("", status_code=201, response_model=DecisionView)
async def create_decision(
    request: Request,
    frame: DecisionFrameInput,
    idempotency_key: IdempotencyKey,
) -> Response:
    try:
        context = await _workspace_context(request)
        now = _context_time(request)
        normalized = normalize_frame(frame)
        request_hash = normalized_request_hash(
            operation=_CREATE_OPERATION,
            method="POST",
            path="/api/v1/decisions",
            body=_frame_document(frame),
        )
        factory = cast(SessionFactory, request.app.state.session_factory)
        result_status: int
        result_body: JsonObject
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
                result_status = existing.response_status
                result_body = existing.response_body
            else:
                database_now = await _database_time(request, session)
                decision = Decision(
                    id=new_uuid7(),
                    workspace_id=context.workspace_id,
                    current_revision=1,
                    created_at=database_now,
                    updated_at=database_now,
                )
                revision = _revision_model(
                    workspace_id=context.workspace_id,
                    decision_id=decision.id,
                    revision=1,
                    frame=normalized,
                    created_at=database_now,
                )
                await DecisionRepository(session).add_initial(
                    decision=decision,
                    revision=revision,
                )
                result_status = 201
                result_body = _view_document(_decision_view(decision, frame=normalized))
                await idempotency.add(
                    IdempotencyRecord(
                        id=new_uuid7(),
                        workspace_id=context.workspace_id,
                        operation=_CREATE_OPERATION,
                        key=idempotency_key,
                        request_hash=request_hash,
                        response_status=result_status,
                        response_body=result_body,
                        resource_id=decision.id,
                        expires_at=_record_expiry(context),
                        created_at=database_now,
                    )
                )
        return _json_response(result_body, status=result_status)
    except WorkspaceContextUnauthorized:
        return _unauthorized_error()
    except _IdempotencyConflict:
        return _idempotency_error()


@router.get("/{decision_id}", response_model=DecisionView)
async def get_decision(
    request: Request,
    decision_id: DecisionPathId,
) -> Response:
    try:
        context = await _workspace_context(request)
    except WorkspaceContextUnauthorized:
        return _unauthorized_error()

    factory = cast(SessionFactory, request.app.state.session_factory)
    async with factory() as session:
        current = await DecisionRepository(session).get_current(
            workspace_id=context.workspace_id,
            decision_id=parse_uuid7(decision_id),
        )
    if current is None:
        return _not_found_error()
    decision, revision = current
    return _json_response(
        _view_document(_decision_view(decision, frame=_stored_frame(revision))),
        status=200,
    )


@router.post("/{decision_id}/revisions", status_code=201, response_model=DecisionView)
async def revise_decision(
    request: Request,
    decision_id: DecisionPathId,
    frame: DecisionFrameInput,
    idempotency_key: IdempotencyKey,
    expected_revision: ExpectedRevision,
) -> Response:
    parsed_decision_id = parse_uuid7(decision_id)
    try:
        context = await _workspace_context(request)
        now = _context_time(request)
        normalized = normalize_frame(frame)
        request_hash = normalized_request_hash(
            operation=_REVISE_OPERATION,
            method="POST",
            path=f"/api/v1/decisions/{parsed_decision_id}/revisions",
            body=_frame_document(frame),
            expected_revision=expected_revision,
        )
        factory = cast(SessionFactory, request.app.state.session_factory)
        result_status: int
        result_body: JsonObject
        async with factory.begin() as session:
            idempotency = IdempotencyRepository(session)
            await idempotency.acquire_transaction_lock(
                lock_id=advisory_lock_id(
                    workspace_id=context.workspace_id,
                    operation=_REVISE_OPERATION,
                    key=idempotency_key,
                )
            )
            await _lock_workspace(session, context=context, now=now)
            existing = await idempotency.get(
                workspace_id=context.workspace_id,
                operation=_REVISE_OPERATION,
                key=idempotency_key,
                now=now,
            )
            if existing is not None:
                if not request_hash_matches(existing.request_hash, request_hash):
                    raise _IdempotencyConflict
                result_status = existing.response_status
                result_body = existing.response_body
            else:
                decisions = DecisionRepository(session)
                decision = await decisions.get(
                    workspace_id=context.workspace_id,
                    decision_id=parsed_decision_id,
                    for_update=True,
                )
                if decision is None:
                    raise _ResourceNotFound
                if decision.current_revision != expected_revision:
                    raise _RevisionConflict

                database_now = await _database_time(request, session)
                revision = _revision_model(
                    workspace_id=context.workspace_id,
                    decision_id=decision.id,
                    revision=decision.current_revision + 1,
                    frame=normalized,
                    created_at=database_now,
                )
                await decisions.append_locked(
                    decision=decision,
                    revision=revision,
                    updated_at=database_now,
                )
                result_status = 201
                result_body = _view_document(_decision_view(decision, frame=normalized))
                await idempotency.add(
                    IdempotencyRecord(
                        id=new_uuid7(),
                        workspace_id=context.workspace_id,
                        operation=_REVISE_OPERATION,
                        key=idempotency_key,
                        request_hash=request_hash,
                        response_status=result_status,
                        response_body=result_body,
                        resource_id=decision.id,
                        expires_at=_record_expiry(context),
                        created_at=database_now,
                    )
                )
        return _json_response(result_body, status=result_status)
    except WorkspaceContextUnauthorized:
        return _unauthorized_error()
    except _IdempotencyConflict:
        return _idempotency_error()
    except _RevisionConflict:
        return _revision_error()
    except _ResourceNotFound:
        return _not_found_error()
