from __future__ import annotations

import asyncio
import copy
import os
import signal
import sys
import threading
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import cast

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_cto_cockpit.contracts.ui import UiEnvelope
from ai_cto_cockpit.domain.ids import new_uuid7, parse_uuid7
from ai_cto_cockpit.persistence.models import (
    DeletionCompletion,
    Job,
    JobKind,
    JobStatus,
    Run,
    RunEvent,
    RunEventKind,
    RunStatus,
    Workspace,
    WorkspaceKind,
    WorkspaceStatus,
)
from ai_cto_cockpit.persistence.repositories import assert_run_transition
from ai_cto_cockpit.persistence.session import (
    create_database_engine,
    create_session_factory,
)
from ai_cto_cockpit.runs.fake_graph import deterministic_envelope
from ai_cto_cockpit.runs.jobs import (
    JobLease,
    claim_job,
    renew_job_lease,
    transaction_time,
)
from ai_cto_cockpit.runs.service import (
    event_payload_hash,
    validated_event_document,
)
from ai_cto_cockpit.settings import Settings

PID_FILE = Path("/tmp/ai-cto-cockpit-worker.pid")
POLL_INTERVAL_SECONDS = 0.25
INVALID_UI_ENVELOPE = "invalid_ui_envelope"

type JsonObject = dict[str, object]
type SessionFactory = async_sessionmaker[AsyncSession]
type EnvelopeFactory = Callable[..., JsonObject]


def _require_aware(value: datetime | None) -> None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError("Worker time must be timezone-aware")


def _job_uuid(payload: JsonObject, *, field: str) -> uuid.UUID:
    if set(payload) != {field}:
        raise ValueError(f"Job payload must contain only {field}")
    value = payload[field]
    if not isinstance(value, str):
        raise ValueError(f"Job payload {field} must be a UUIDv7 string")
    return parse_uuid7(value)


def _lease_matches(job: Job, lease: JobLease, *, now: datetime) -> bool:
    return (
        job.id == lease.job_id
        and job.workspace_id == lease.workspace_id
        and job.kind is lease.kind
        and job.status is JobStatus.LEASED
        and job.lease_owner == lease.worker_id
        and job.attempt_count == lease.attempt_count
        and job.lease_expires_at is not None
        and job.lease_expires_at > now
    )


async def _lock_fenced_job(
    session: AsyncSession,
    *,
    lease: JobLease,
    now: datetime | None,
) -> tuple[Job, datetime] | None:
    effective_now = await transaction_time(session, override=now)
    job = await session.scalar(
        select(Job)
        .where(
            Job.id == lease.job_id,
            Job.workspace_id == lease.workspace_id,
        )
        .with_for_update()
    )
    if job is None or not _lease_matches(job, lease, now=effective_now):
        return None
    return job, effective_now


async def _locked_run(
    session: AsyncSession,
    *,
    lease: JobLease,
) -> Run:
    run_id = _job_uuid(lease.payload, field="runId")
    run = await session.scalar(
        select(Run)
        .where(
            Run.workspace_id == lease.workspace_id,
            Run.id == run_id,
        )
        .with_for_update()
    )
    if run is None:
        raise LookupError("Execute-run job target is unavailable")
    return run


async def _event_prefix(
    session: AsyncSession,
    *,
    run: Run,
) -> list[RunEvent]:
    events = list(
        (
            await session.scalars(
                select(RunEvent)
                .where(
                    RunEvent.workspace_id == run.workspace_id,
                    RunEvent.run_id == run.id,
                )
                .order_by(RunEvent.sequence)
            )
        ).all()
    )
    if [event.sequence for event in events] != list(
        range(1, run.last_event_sequence + 1)
    ):
        raise RuntimeError("Persisted run event prefix is not contiguous")
    return events


def _append_event(
    session: AsyncSession,
    *,
    run: Run,
    sequence: int,
    kind: RunEventKind,
    payload: JsonObject,
    now: datetime,
) -> None:
    if sequence != run.last_event_sequence + 1:
        raise RuntimeError("Worker attempted a non-contiguous event append")
    document = validated_event_document(
        run_id=run.id,
        sequence=sequence,
        kind=kind,
        payload=payload,
        created_at=now,
    )
    validated_payload = cast(JsonObject, document["payload"])
    session.add(
        RunEvent(
            id=new_uuid7(),
            workspace_id=run.workspace_id,
            run_id=run.id,
            sequence=sequence,
            kind=kind,
            payload_schema_version="1.0",
            payload=validated_payload,
            payload_hash=event_payload_hash(validated_payload),
            created_at=now,
        )
    )
    run.last_event_sequence = sequence


def _finish_job(
    job: Job,
    *,
    status: JobStatus,
    now: datetime,
    error_code: str | None,
) -> None:
    if status not in {JobStatus.COMPLETED, JobStatus.FAILED}:
        raise ValueError("Worker may finish a job only as completed or failed")
    job.status = status
    job.lease_owner = None
    job.lease_expires_at = None
    job.last_error_code = error_code
    job.updated_at = now
    job.completed_at = now


async def _start_run(
    *,
    session_factory: SessionFactory,
    lease: JobLease,
    now: datetime | None,
) -> bool:
    async with session_factory.begin() as session:
        locked = await _lock_fenced_job(session, lease=lease, now=now)
        if locked is None:
            return False
        _job, transaction_now = locked
        run = await _locked_run(session, lease=lease)
        events = await _event_prefix(session, run=run)
        if run.last_event_sequence != 1:
            return True
        if (
            run.status is not RunStatus.QUEUED
            or len(events) != 1
            or events[0].kind is not RunEventKind.RUN_QUEUED
        ):
            raise RuntimeError("Queued run does not have its canonical event prefix")
        assert_run_transition(run.status, RunStatus.RUNNING)
        run.status = RunStatus.RUNNING
        run.started_at = transaction_now
        _append_event(
            session,
            run=run,
            sequence=2,
            kind=RunEventKind.RUN_STARTED,
            payload={"status": "running"},
            now=transaction_now,
        )
        await session.flush()
        return True


async def _snapshot_for_envelope(
    *,
    session_factory: SessionFactory,
    lease: JobLease,
    now: datetime | None,
) -> tuple[uuid.UUID, JsonObject] | None:
    async with session_factory.begin() as session:
        locked = await _lock_fenced_job(session, lease=lease, now=now)
        if locked is None:
            return None
        run = await _locked_run(session, lease=lease)
        events = await _event_prefix(session, run=run)
        if run.last_event_sequence != 2:
            return None
        if (
            run.status is not RunStatus.RUNNING
            or len(events) != 2
            or events[-1].kind is not RunEventKind.RUN_STARTED
        ):
            raise RuntimeError("Running run does not have its canonical event prefix")
        return run.id, copy.deepcopy(run.input_snapshot)


def _validated_envelope(
    *,
    factory: EnvelopeFactory,
    run_id: uuid.UUID,
    input_snapshot: JsonObject,
) -> JsonObject:
    candidate = factory(
        run_id=run_id,
        event_sequence=3,
        input_snapshot=input_snapshot,
    )
    validated = UiEnvelope.model_validate(candidate)
    if validated.meta.run_id != str(run_id) or validated.meta.event_sequence != 3:
        raise ValueError("UI envelope metadata does not match its run event")
    return cast(JsonObject, validated.model_dump(mode="json", by_alias=True))


async def _append_envelope(
    *,
    session_factory: SessionFactory,
    lease: JobLease,
    now: datetime | None,
    envelope: JsonObject,
) -> bool:
    async with session_factory.begin() as session:
        locked = await _lock_fenced_job(session, lease=lease, now=now)
        if locked is None:
            return False
        _job, transaction_now = locked
        run = await _locked_run(session, lease=lease)
        events = await _event_prefix(session, run=run)
        if run.last_event_sequence != 2:
            return True
        if (
            run.status is not RunStatus.RUNNING
            or len(events) != 2
            or events[-1].kind is not RunEventKind.RUN_STARTED
        ):
            raise RuntimeError("Run cannot accept a UI envelope at this watermark")
        _append_event(
            session,
            run=run,
            sequence=3,
            kind=RunEventKind.UI_ENVELOPE,
            payload=envelope,
            now=transaction_now,
        )
        await session.flush()
        return True


async def _fail_invalid_envelope(
    *,
    session_factory: SessionFactory,
    lease: JobLease,
    now: datetime | None,
) -> bool:
    async with session_factory.begin() as session:
        locked = await _lock_fenced_job(session, lease=lease, now=now)
        if locked is None:
            return False
        job, transaction_now = locked
        run = await _locked_run(session, lease=lease)
        events = await _event_prefix(session, run=run)
        if run.terminal_event_sequence is not None:
            return True
        if (
            run.status is not RunStatus.RUNNING
            or run.last_event_sequence != 2
            or len(events) != 2
        ):
            raise RuntimeError("Run cannot fail at the UI validation boundary")
        assert_run_transition(run.status, RunStatus.FAILED)
        _append_event(
            session,
            run=run,
            sequence=3,
            kind=RunEventKind.RUN_FAILED,
            payload={"status": "failed", "errorCode": INVALID_UI_ENVELOPE},
            now=transaction_now,
        )
        run.status = RunStatus.FAILED
        run.terminal_event_sequence = 3
        run.error_code = INVALID_UI_ENVELOPE
        run.completed_at = transaction_now
        _finish_job(
            job,
            status=JobStatus.FAILED,
            now=transaction_now,
            error_code=INVALID_UI_ENVELOPE,
        )
        await session.flush()
        return True


async def _complete_run(
    *,
    session_factory: SessionFactory,
    lease: JobLease,
    now: datetime | None,
) -> bool:
    async with session_factory.begin() as session:
        locked = await _lock_fenced_job(session, lease=lease, now=now)
        if locked is None:
            return False
        job, transaction_now = locked
        run = await _locked_run(session, lease=lease)
        events = await _event_prefix(session, run=run)
        if run.terminal_event_sequence is not None:
            _finish_job(
                job,
                status=(
                    JobStatus.COMPLETED
                    if run.status is RunStatus.COMPLETED
                    else JobStatus.FAILED
                ),
                now=transaction_now,
                error_code=run.error_code,
            )
            await session.flush()
            return True
        if (
            run.status is not RunStatus.RUNNING
            or run.last_event_sequence != 3
            or len(events) != 3
            or events[-1].kind is not RunEventKind.UI_ENVELOPE
        ):
            raise RuntimeError("Run cannot complete before its UI envelope")
        assert_run_transition(run.status, RunStatus.COMPLETED)
        _append_event(
            session,
            run=run,
            sequence=4,
            kind=RunEventKind.RUN_COMPLETED,
            payload={"status": "completed"},
            now=transaction_now,
        )
        run.status = RunStatus.COMPLETED
        run.terminal_event_sequence = 4
        run.completed_at = transaction_now
        run.error_code = None
        _finish_job(
            job,
            status=JobStatus.COMPLETED,
            now=transaction_now,
            error_code=None,
        )
        await session.flush()
        return True


async def _execute_run(
    *,
    session_factory: SessionFactory,
    lease: JobLease,
    now: datetime | None,
    envelope_factory: EnvelopeFactory,
) -> None:
    if not await _start_run(
        session_factory=session_factory,
        lease=lease,
        now=now,
    ):
        return
    renewed_lease = await renew_job_lease(
        session_factory=session_factory,
        lease=lease,
        now=now,
    )
    if renewed_lease is None:
        return
    snapshot = await _snapshot_for_envelope(
        session_factory=session_factory,
        lease=renewed_lease,
        now=now,
    )
    if snapshot is not None:
        run_id, input_snapshot = snapshot
        try:
            envelope = _validated_envelope(
                factory=envelope_factory,
                run_id=run_id,
                input_snapshot=input_snapshot,
            )
        except (TypeError, ValueError, ValidationError):
            await _fail_invalid_envelope(
                session_factory=session_factory,
                lease=renewed_lease,
                now=now,
            )
            return
        if not await _append_envelope(
            session_factory=session_factory,
            lease=renewed_lease,
            now=now,
            envelope=envelope,
        ):
            return
    await _complete_run(
        session_factory=session_factory,
        lease=renewed_lease,
        now=now,
    )


async def _delete_workspace(
    *,
    session_factory: SessionFactory,
    lease: JobLease,
    now: datetime | None,
) -> None:
    workspace_id = _job_uuid(lease.payload, field="workspaceId")
    if workspace_id != lease.workspace_id:
        raise ValueError("Deletion job cannot authorize another workspace")
    async with session_factory.begin() as session:
        locked = await _lock_fenced_job(session, lease=lease, now=now)
        if locked is None:
            return
        job, transaction_now = locked
        workspace = await session.scalar(
            select(Workspace).where(Workspace.id == workspace_id).with_for_update()
        )
        if (
            workspace is None
            or workspace.kind is not WorkspaceKind.GUEST
            or workspace.status is not WorkspaceStatus.DELETING
        ):
            raise ValueError("Deletion job requires its deleting guest workspace")
        session.add(
            DeletionCompletion(
                id=new_uuid7(),
                workspace_id=workspace_id,
                operation="delete-guest-workspace-v1",
                job_id=job.id,
                completed_at=transaction_now,
            )
        )
        _finish_job(
            job,
            status=JobStatus.COMPLETED,
            now=transaction_now,
            error_code=None,
        )
        await session.flush()
        await session.delete(workspace)
        await session.flush()


async def process_one_job(
    *,
    session_factory: SessionFactory,
    worker_id: str,
    now: datetime | None = None,
    envelope_factory: EnvelopeFactory | None = None,
) -> bool:
    """Claim and advance one durable job; return whether work was claimed."""

    _require_aware(now)
    lease = await claim_job(
        session_factory=session_factory,
        worker_id=worker_id,
        now=now,
    )
    if lease is None:
        return False
    if lease.kind is JobKind.EXECUTE_RUN:
        await _execute_run(
            session_factory=session_factory,
            lease=lease,
            now=now,
            envelope_factory=envelope_factory or deterministic_envelope,
        )
    elif lease.kind is JobKind.DELETE_WORKSPACE:
        await _delete_workspace(
            session_factory=session_factory,
            lease=lease,
            now=now,
        )
    else:  # pragma: no cover - closed database enum
        raise RuntimeError("Worker claimed an unsupported job kind")
    return True


def _healthy() -> bool:
    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
        os.kill(pid, 0)
    except (OSError, ValueError):
        return False
    return True


async def _serve(stopped: threading.Event) -> None:
    settings = Settings()  # pyright: ignore[reportCallIssue]
    engine = create_database_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    worker_id = f"worker-{os.getpid()}"
    try:
        while not stopped.is_set():
            try:
                handled = await process_one_job(
                    session_factory=session_factory,
                    worker_id=worker_id,
                )
            except Exception:
                # The durable lease preserves retry state. Redacted telemetry and
                # explicit operational metrics are introduced by T021.
                handled = False
            if not handled:
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
    finally:
        await engine.dispose()


def _run() -> None:
    stopped = threading.Event()

    def stop(_signum: int, _frame: object) -> None:
        stopped.set()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    try:
        asyncio.run(_serve(stopped))
    finally:
        PID_FILE.unlink(missing_ok=True)


def main() -> int:
    if sys.argv[1:] == ["--healthcheck"]:
        return 0 if _healthy() else 1
    if sys.argv[1:]:
        return 2
    _run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
