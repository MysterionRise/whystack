from __future__ import annotations

import asyncio
import hashlib
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from pydantic import TypeAdapter
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_cto_cockpit.contracts.decision import DecisionFrameView
from ai_cto_cockpit.contracts.run import RunEvent as RunEventContract
from ai_cto_cockpit.contracts.run import RunView
from ai_cto_cockpit.domain.idempotency import canonical_json
from ai_cto_cockpit.persistence.models import (
    DecisionRevision,
    Run,
    RunEvent,
    RunEventKind,
)

type JsonObject = dict[str, object]
type SessionFactory = async_sessionmaker[AsyncSession]
type StreamAuthorizer = Callable[[], Awaitable[bool]]

_EVENT_ADAPTER: TypeAdapter[RunEventContract] = TypeAdapter(RunEventContract)


@dataclass(frozen=True, slots=True)
class RunStreamPolicy:
    poll_interval_seconds: float = 0.25
    heartbeat_interval_seconds: float = 15.0

    def __post_init__(self) -> None:
        if self.poll_interval_seconds <= 0:
            raise ValueError("Run stream poll interval must be positive")
        if self.heartbeat_interval_seconds <= 0:
            raise ValueError("Run stream heartbeat interval must be positive")


@dataclass(frozen=True, slots=True)
class RunProjection:
    run: Run
    decision_revision: int


def revision_snapshot_document(revision: DecisionRevision) -> JsonObject:
    """Reconstruct and validate the exact immutable normalized revision frame."""

    frame = DecisionFrameView.model_validate(
        {
            "schemaVersion": revision.frame_schema_version,
            "question": revision.question,
            "context": revision.context,
            "options": revision.options,
            "criteria": revision.criteria,
            "constraints": revision.constraints,
        }
    )
    return cast(JsonObject, frame.model_dump(mode="json", by_alias=True))


def run_view_document(run: Run, *, decision_revision: int) -> JsonObject:
    view = RunView.model_validate(
        {
            "id": str(run.id),
            "decisionId": str(run.decision_id),
            "decisionRevision": decision_revision,
            "status": run.status.value,
            "lastEventSequence": run.last_event_sequence,
            "fixtureVersion": run.fixture_version,
            "createdAt": run.created_at,
            "startedAt": run.started_at,
            "completedAt": run.completed_at,
            "errorCode": run.error_code,
        }
    )
    return cast(JsonObject, view.model_dump(mode="json", by_alias=True))


def validated_event_document(
    *,
    run_id: uuid.UUID,
    sequence: int,
    kind: RunEventKind,
    payload: JsonObject,
    created_at: datetime,
) -> JsonObject:
    """Validate the complete discriminated event before storage or streaming."""

    document: JsonObject = {
        "runId": str(run_id),
        "sequence": sequence,
        "kind": kind.value,
        "schemaVersion": "1.0",
        "payload": payload,
        "createdAt": created_at,
    }
    validated = _EVENT_ADAPTER.validate_python(document)
    return cast(JsonObject, validated.model_dump(mode="json", by_alias=True))


def event_document(event: RunEvent) -> JsonObject:
    return validated_event_document(
        run_id=event.run_id,
        sequence=event.sequence,
        kind=event.kind,
        payload=event.payload,
        created_at=event.created_at,
    )


def event_payload_hash(payload: JsonObject) -> str:
    return hashlib.sha256(canonical_json(payload)).hexdigest()


async def load_run_projection(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    run_id: uuid.UUID,
    for_update: bool = False,
) -> RunProjection | None:
    statement = (
        select(Run, DecisionRevision.revision)
        .join(
            DecisionRevision,
            and_(
                DecisionRevision.workspace_id == Run.workspace_id,
                DecisionRevision.decision_id == Run.decision_id,
                DecisionRevision.id == Run.decision_revision_id,
            ),
        )
        .where(
            Run.workspace_id == workspace_id,
            Run.id == run_id,
        )
    )
    if for_update:
        statement = statement.with_for_update(of=Run)
    result = (await session.execute(statement)).one_or_none()
    if result is None:
        return None
    run, decision_revision = result
    return RunProjection(
        run=run,
        decision_revision=decision_revision,
    )


async def _load_stream_batch(
    session_factory: SessionFactory,
    *,
    workspace_id: uuid.UUID,
    run_id: uuid.UUID,
    after_sequence: int,
) -> tuple[list[RunEvent], int | None] | None:
    async with session_factory() as session:
        projection = await load_run_projection(
            session,
            workspace_id=workspace_id,
            run_id=run_id,
        )
        if projection is None:
            return None
        events = list(
            (
                await session.scalars(
                    select(RunEvent)
                    .where(
                        RunEvent.workspace_id == workspace_id,
                        RunEvent.run_id == run_id,
                        RunEvent.sequence > after_sequence,
                    )
                    .order_by(RunEvent.sequence)
                )
            ).all()
        )
        return events, projection.run.terminal_event_sequence


def sse_event(event: RunEvent) -> bytes:
    document = event_document(event)
    return b"".join(
        (
            f"id: {event.sequence}\n".encode("ascii"),
            f"event: {event.kind.value}\n".encode("ascii"),
            b"data: ",
            canonical_json(document),
            b"\n\n",
        )
    )


async def stream_persisted_events(
    *,
    session_factory: SessionFactory,
    workspace_id: uuid.UUID,
    run_id: uuid.UUID,
    after_sequence: int,
    policy: RunStreamPolicy,
    authorize: StreamAuthorizer,
) -> AsyncIterator[bytes]:
    """Replay stored events, heartbeat while waiting, and close at terminal state."""

    cursor = after_sequence
    loop = asyncio.get_running_loop()
    heartbeat_at = loop.time() + policy.heartbeat_interval_seconds
    while True:
        if not await authorize():
            return
        batch = await _load_stream_batch(
            session_factory,
            workspace_id=workspace_id,
            run_id=run_id,
            after_sequence=cursor,
        )
        if batch is None:
            return
        events, terminal_sequence = batch
        for event in events:
            yield sse_event(event)
            cursor = event.sequence
            heartbeat_at = loop.time() + policy.heartbeat_interval_seconds

        if terminal_sequence is not None and cursor >= terminal_sequence:
            return

        delay = min(
            policy.poll_interval_seconds,
            max(0.0, heartbeat_at - loop.time()),
        )
        if delay:
            await asyncio.sleep(delay)
        if not await authorize():
            return
        if loop.time() >= heartbeat_at:
            yield b": heartbeat\n\n"
            heartbeat_at = loop.time() + policy.heartbeat_interval_seconds
