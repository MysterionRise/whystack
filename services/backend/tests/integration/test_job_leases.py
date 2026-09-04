from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Protocol, cast

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_cto_cockpit.api.dependencies.context import (
    WorkspaceContextUnauthorized,
    resolve_workspace_context,
)
from ai_cto_cockpit.contracts.ui import UiEnvelope
from ai_cto_cockpit.persistence.models import (
    Decision,
    DecisionRevision,
    DeletionCompletion,
    GuestSession,
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
from ai_cto_cockpit.security.guest_session import GuestSessionCodec, SessionKeyRing
from ai_cto_cockpit.settings import Settings

NOW = datetime(2026, 8, 18, 10, 0, 0, 123456, tzinfo=UTC)
LEASE_DURATION = timedelta(seconds=30)
SIGNING_KEY = "t017-session-signing-key-with-more-than-thirty-two-bytes"
SEED_ID = uuid.UUID("019a1000-0000-7000-8000-000000000001")
LOCAL_ID = uuid.UUID("019a1000-0000-7000-8000-000000000002")
GUEST_ID = uuid.UUID("019a1000-0000-7000-8000-000000000003")
SESSION_ID = uuid.UUID("019a1000-0000-7000-8000-000000000004")
DECISION_ID = uuid.UUID("019a1000-0000-7000-8000-000000000005")
REVISION_ID = uuid.UUID("019a1000-0000-7000-8000-000000000006")
RUN_ID = uuid.UUID("019a1000-0000-7000-8000-000000000007")
JOB_ID = uuid.UUID("019a1000-0000-7000-8000-000000000008")

type JsonObject = dict[str, object]
type SessionFactory = async_sessionmaker[AsyncSession]


class _JobLease(Protocol):
    job_id: uuid.UUID
    workspace_id: uuid.UUID
    kind: JobKind
    payload: JsonObject
    worker_id: str
    attempt_count: int
    lease_expires_at: datetime


class _JobsModule(Protocol):
    async def claim_job(
        self,
        *,
        session_factory: SessionFactory,
        worker_id: str,
        now: datetime,
        lease_duration: timedelta,
    ) -> _JobLease | None: ...

    async def renew_job_lease(
        self,
        *,
        session_factory: SessionFactory,
        lease: _JobLease,
        now: datetime,
        lease_duration: timedelta,
    ) -> _JobLease | None: ...


class _WorkerModule(Protocol):
    async def process_one_job(
        self,
        *,
        session_factory: SessionFactory,
        worker_id: str,
        now: datetime,
    ) -> object | None: ...


def _jobs_module() -> _JobsModule:
    # T017 must collect before T018 creates this production module.
    return cast(
        _JobsModule,
        importlib.import_module("ai_cto_cockpit.runs.jobs"),
    )


def _worker_module() -> _WorkerModule:
    # The Phase-A process skeleton exists, but T018 adds the worker entry point.
    return cast(_WorkerModule, importlib.import_module("ai_cto_cockpit.worker"))


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


def _canonical_hash(value: JsonObject) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _frame() -> JsonObject:
    return {
        "schemaVersion": "1.0",
        "question": "Which bounded architecture should the fixture demonstrate?",
        "context": "T017 durable worker restart fixture.",
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
                "enteredWeight": "1.0",
                "normalizedWeight": "50.0000",
            },
            {
                "id": "operability",
                "label": "Operability",
                "enteredWeight": "1.00",
                "normalizedWeight": "50.0000",
            },
        ],
        "constraints": [],
    }


def _workspace(
    workspace_id: uuid.UUID,
    *,
    kind: WorkspaceKind,
    status: WorkspaceStatus = WorkspaceStatus.ACTIVE,
) -> Workspace:
    is_guest = kind is WorkspaceKind.GUEST
    return Workspace(
        id=workspace_id,
        kind=kind,
        status=status,
        seed_parent_id=SEED_ID if is_guest else None,
        expires_at=NOW + timedelta(hours=24) if is_guest else None,
        created_at=NOW,
        updated_at=NOW,
    )


async def _seed_execute_job(
    factory: SessionFactory,
    *,
    partially_started: bool = False,
    crashed_worker: str = "worker-crashed",
) -> None:
    frame = _frame()
    async with factory.begin() as session:
        session.add(_workspace(SEED_ID, kind=WorkspaceKind.SEED))
        await session.flush()
        session.add(_workspace(GUEST_ID, kind=WorkspaceKind.GUEST))
        await session.flush()
        session.add(
            Decision(
                id=DECISION_ID,
                workspace_id=GUEST_ID,
                current_revision=1,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        await session.flush()
        session.add(
            DecisionRevision(
                id=REVISION_ID,
                workspace_id=GUEST_ID,
                decision_id=DECISION_ID,
                revision=1,
                frame_schema_version="1.0",
                question=cast(str, frame["question"]),
                context=cast(str, frame["context"]),
                options=cast(list[JsonObject], frame["options"]),
                criteria=cast(list[JsonObject], frame["criteria"]),
                constraints=cast(list[JsonObject], frame["constraints"]),
                snapshot_hash=_canonical_hash(frame),
                created_at=NOW,
            )
        )
        await session.flush()
        session.add(
            Run(
                id=RUN_ID,
                workspace_id=GUEST_ID,
                decision_id=DECISION_ID,
                decision_revision_id=REVISION_ID,
                status=(RunStatus.RUNNING if partially_started else RunStatus.QUEUED),
                fixture_version="walking-skeleton-v1",
                input_snapshot=frame,
                input_snapshot_hash=_canonical_hash(frame),
                last_event_sequence=2 if partially_started else 1,
                terminal_event_sequence=None,
                error_code=None,
                created_at=NOW,
                started_at=NOW if partially_started else None,
                completed_at=None,
            )
        )
        await session.flush()
        queued_payload: JsonObject = {"status": "queued"}
        session.add(
            RunEvent(
                workspace_id=GUEST_ID,
                run_id=RUN_ID,
                sequence=1,
                kind=RunEventKind.RUN_QUEUED,
                payload_schema_version="1.0",
                payload=queued_payload,
                payload_hash=_canonical_hash(queued_payload),
                created_at=NOW,
            )
        )
        if partially_started:
            started_payload: JsonObject = {"status": "running"}
            session.add(
                RunEvent(
                    workspace_id=GUEST_ID,
                    run_id=RUN_ID,
                    sequence=2,
                    kind=RunEventKind.RUN_STARTED,
                    payload_schema_version="1.0",
                    payload=started_payload,
                    payload_hash=_canonical_hash(started_payload),
                    created_at=NOW,
                )
            )
        session.add(
            Job(
                id=JOB_ID,
                workspace_id=GUEST_ID,
                kind=JobKind.EXECUTE_RUN,
                payload={"runId": str(RUN_ID)},
                status=(JobStatus.LEASED if partially_started else JobStatus.AVAILABLE),
                available_at=NOW,
                lease_owner=crashed_worker if partially_started else None,
                lease_expires_at=NOW if partially_started else None,
                attempt_count=1 if partially_started else 0,
                last_error_code=None,
                created_at=NOW,
                updated_at=NOW,
                completed_at=None,
            )
        )


async def _seed_delete_job(
    factory: SessionFactory,
    *,
    with_session_and_content: bool,
) -> str | None:
    cookie: str | None = None
    async with factory.begin() as session:
        session.add(_workspace(SEED_ID, kind=WorkspaceKind.SEED))
        await session.flush()
        session.add(
            _workspace(
                GUEST_ID,
                kind=WorkspaceKind.GUEST,
                status=WorkspaceStatus.DELETING,
            )
        )
        await session.flush()

        if with_session_and_content:
            settings = _settings("postgresql+psycopg://unused")
            codec = GuestSessionCodec(
                SessionKeyRing.from_settings(settings),
                cookie_secure=settings.cookie_secure,
                clock=lambda: NOW,
            )
            token = b"\x17" * 32
            cookie = codec.issue(
                session_id=SESSION_ID,
                token=token,
                issued_at=NOW,
                expires_at=NOW + timedelta(hours=24),
            ).value
            session.add(
                GuestSession(
                    id=SESSION_ID,
                    workspace_id=GUEST_ID,
                    token_hash=codec.token_hash(token),
                    expires_at=NOW + timedelta(hours=24),
                    revoked_at=None,
                    created_at=NOW,
                )
            )
            session.add(
                Decision(
                    id=DECISION_ID,
                    workspace_id=GUEST_ID,
                    current_revision=1,
                    created_at=NOW,
                    updated_at=NOW,
                )
            )

        session.add(
            Job(
                id=JOB_ID,
                workspace_id=GUEST_ID,
                kind=JobKind.DELETE_WORKSPACE,
                payload={"workspaceId": str(GUEST_ID)},
                status=JobStatus.AVAILABLE,
                available_at=NOW,
                lease_owner=None,
                lease_expires_at=None,
                attempt_count=0,
                last_error_code=None,
                created_at=NOW,
                updated_at=NOW,
                completed_at=None,
            )
        )
    return cookie


async def _event_rows(factory: SessionFactory) -> list[RunEvent]:
    async with factory() as session:
        return list(
            (
                await session.scalars(
                    select(RunEvent)
                    .where(
                        RunEvent.workspace_id == GUEST_ID,
                        RunEvent.run_id == RUN_ID,
                    )
                    .order_by(RunEvent.sequence)
                )
            ).all()
        )


def _assert_completed_event_log(events: list[RunEvent]) -> None:
    assert [event.sequence for event in events] == [1, 2, 3, 4]
    assert [event.kind for event in events] == [
        RunEventKind.RUN_QUEUED,
        RunEventKind.RUN_STARTED,
        RunEventKind.UI_ENVELOPE,
        RunEventKind.RUN_COMPLETED,
    ]
    assert (
        sum(
            event.kind in {RunEventKind.RUN_COMPLETED, RunEventKind.RUN_FAILED}
            for event in events
        )
        == 1
    )
    envelope = UiEnvelope.model_validate(events[2].payload)
    assert envelope.meta.run_id == str(RUN_ID)
    assert envelope.meta.event_sequence == 3


async def _install_deferred_deletion_failure(factory: SessionFactory) -> None:
    async with factory.begin() as session:
        await session.execute(
            text(
                "DROP TRIGGER IF EXISTS t017_abort_deletion_commit "
                "ON deletion_completions"
            )
        )
        await session.execute(
            text("DROP FUNCTION IF EXISTS t017_abort_deletion_commit()")
        )
        await session.execute(
            text(
                """
                CREATE FUNCTION t017_abort_deletion_commit()
                RETURNS trigger
                LANGUAGE plpgsql
                AS $t017$
                BEGIN
                    RAISE EXCEPTION 't017 injected pre-commit deletion failure';
                END;
                $t017$
                """
            )
        )
        await session.execute(
            text(
                """
                CREATE CONSTRAINT TRIGGER t017_abort_deletion_commit
                AFTER INSERT ON deletion_completions
                DEFERRABLE INITIALLY DEFERRED
                FOR EACH ROW
                EXECUTE FUNCTION t017_abort_deletion_commit()
                """
            )
        )


async def _remove_deferred_deletion_failure(factory: SessionFactory) -> None:
    async with factory.begin() as session:
        await session.execute(
            text(
                "DROP TRIGGER IF EXISTS t017_abort_deletion_commit "
                "ON deletion_completions"
            )
        )
        await session.execute(
            text("DROP FUNCTION IF EXISTS t017_abort_deletion_commit()")
        )


@pytest.mark.asyncio
async def test_claim_renew_and_expired_reclaim_use_attempt_fence(
    t010_session_factory: SessionFactory,
) -> None:
    await _seed_delete_job(
        t010_session_factory,
        with_session_and_content=False,
    )
    jobs = _jobs_module()

    first = await jobs.claim_job(
        session_factory=t010_session_factory,
        worker_id="worker-a",
        now=NOW,
        lease_duration=LEASE_DURATION,
    )
    assert first is not None
    assert first.job_id == JOB_ID
    assert first.workspace_id == GUEST_ID
    assert first.kind is JobKind.DELETE_WORKSPACE
    assert first.payload == {"workspaceId": str(GUEST_ID)}
    assert first.worker_id == "worker-a"
    assert first.attempt_count == 1
    assert first.lease_expires_at == NOW + LEASE_DURATION

    renewed_at = NOW + timedelta(seconds=10)
    renewed = await jobs.renew_job_lease(
        session_factory=t010_session_factory,
        lease=first,
        now=renewed_at,
        lease_duration=LEASE_DURATION,
    )
    assert renewed is not None
    assert renewed.attempt_count == first.attempt_count
    assert renewed.lease_expires_at == renewed_at + LEASE_DURATION

    assert (
        await jobs.claim_job(
            session_factory=t010_session_factory,
            worker_id="worker-b",
            now=renewed.lease_expires_at - timedelta(microseconds=1),
            lease_duration=LEASE_DURATION,
        )
        is None
    )
    reclaimed = await jobs.claim_job(
        session_factory=t010_session_factory,
        worker_id="worker-b",
        now=renewed.lease_expires_at,
        lease_duration=LEASE_DURATION,
    )
    assert reclaimed is not None
    assert reclaimed.job_id == renewed.job_id
    assert reclaimed.worker_id == "worker-b"
    assert reclaimed.attempt_count == 2

    stale_renewal = await jobs.renew_job_lease(
        session_factory=t010_session_factory,
        lease=renewed,
        now=renewed.lease_expires_at + timedelta(microseconds=1),
        lease_duration=LEASE_DURATION,
    )
    assert stale_renewal is None

    async with t010_session_factory() as session:
        row = await session.get(Job, JOB_ID)
        assert row is not None
        assert row.status is JobStatus.LEASED
        assert row.lease_owner == "worker-b"
        assert row.attempt_count == 2
        assert row.lease_expires_at == reclaimed.lease_expires_at


@pytest.mark.asyncio
async def test_competing_workers_execute_one_job_and_one_terminal_event(
    t010_session_factory: SessionFactory,
) -> None:
    await _seed_execute_job(t010_session_factory)
    worker = _worker_module()

    await asyncio.gather(
        worker.process_one_job(
            session_factory=t010_session_factory,
            worker_id="worker-a",
            now=NOW,
        ),
        worker.process_one_job(
            session_factory=t010_session_factory,
            worker_id="worker-b",
            now=NOW,
        ),
    )

    events = await _event_rows(t010_session_factory)
    _assert_completed_event_log(events)
    async with t010_session_factory() as session:
        run = await session.get(Run, RUN_ID)
        job = await session.get(Job, JOB_ID)
        assert run is not None and job is not None
        assert run.status is RunStatus.COMPLETED
        assert run.last_event_sequence == 4
        assert run.terminal_event_sequence == 4
        assert run.completed_at is not None
        assert job.status is JobStatus.COMPLETED
        assert job.attempt_count == 1
        assert job.lease_owner is None
        assert job.lease_expires_at is None
        assert job.completed_at is not None


@pytest.mark.asyncio
async def test_worker_restart_resumes_partial_events_without_second_terminal(
    t010_session_factory: SessionFactory,
) -> None:
    await _seed_execute_job(t010_session_factory, partially_started=True)
    worker = _worker_module()
    resumed_at = NOW + timedelta(microseconds=1)

    await worker.process_one_job(
        session_factory=t010_session_factory,
        worker_id="worker-restarted",
        now=resumed_at,
    )
    await worker.process_one_job(
        session_factory=t010_session_factory,
        worker_id="worker-restarted",
        now=resumed_at + timedelta(seconds=1),
    )

    events = await _event_rows(t010_session_factory)
    _assert_completed_event_log(events)
    async with t010_session_factory() as session:
        run = await session.get(Run, RUN_ID)
        job = await session.get(Job, JOB_ID)
        assert run is not None and job is not None
        assert run.status is RunStatus.COMPLETED
        assert run.last_event_sequence == 4
        assert run.terminal_event_sequence == 4
        assert job.status is JobStatus.COMPLETED
        assert job.attempt_count == 2
        assert (
            int(
                await session.scalar(
                    select(func.count(RunEvent.id)).where(
                        RunEvent.run_id == RUN_ID,
                        RunEvent.kind.in_(
                            [RunEventKind.RUN_COMPLETED, RunEventKind.RUN_FAILED]
                        ),
                    )
                )
                or 0
            )
            == 1
        )


@pytest.mark.asyncio
async def test_delete_workspace_precommit_failure_retries_atomically_once(
    t010_postgres_url: str,
    t010_session_factory: SessionFactory,
) -> None:
    cookie = await _seed_delete_job(
        t010_session_factory,
        with_session_and_content=True,
    )
    assert cookie is not None
    worker = _worker_module()
    await _install_deferred_deletion_failure(t010_session_factory)
    try:
        try:
            await worker.process_one_job(
                session_factory=t010_session_factory,
                worker_id="worker-crashed-before-commit",
                now=NOW,
            )
        except DBAPIError:
            # A worker may surface the database failure or record it operationally;
            # the durable postcondition below is identical in either case.
            pass
    finally:
        await _remove_deferred_deletion_failure(t010_session_factory)

    async with t010_session_factory() as session:
        workspace = await session.get(Workspace, GUEST_ID)
        job = await session.get(Job, JOB_ID)
        assert workspace is not None and job is not None
        assert workspace.status is WorkspaceStatus.DELETING
        assert job.status is JobStatus.LEASED
        assert job.lease_owner == "worker-crashed-before-commit"
        assert job.attempt_count == 1
        assert job.lease_expires_at is not None
        retry_at = job.lease_expires_at + timedelta(microseconds=1)
        assert await session.get(GuestSession, SESSION_ID) is not None
        assert await session.get(Decision, DECISION_ID) is not None
        assert (
            int(await session.scalar(select(func.count(DeletionCompletion.id))) or 0)
            == 0
        )

    await worker.process_one_job(
        session_factory=t010_session_factory,
        worker_id="worker-retry",
        now=retry_at,
    )
    await worker.process_one_job(
        session_factory=t010_session_factory,
        worker_id="worker-retry",
        now=retry_at + timedelta(seconds=1),
    )

    async with t010_session_factory() as session:
        assert await session.get(Workspace, GUEST_ID) is None
        assert await session.get(GuestSession, SESSION_ID) is None
        assert await session.get(Decision, DECISION_ID) is None
        assert await session.get(Job, JOB_ID) is None
        completions = list((await session.scalars(select(DeletionCompletion))).all())
        assert len(completions) == 1
        completion = completions[0]
        assert completion.workspace_id == GUEST_ID
        assert completion.job_id == JOB_ID
        assert completion.operation == "delete-guest-workspace-v1"
        assert completion.completed_at is not None
        assert set(completion.__dict__).difference({"_sa_instance_state"}) == {
            "id",
            "workspace_id",
            "operation",
            "job_id",
            "completed_at",
        }

    settings = _settings(t010_postgres_url)
    codec = GuestSessionCodec(
        SessionKeyRing.from_settings(settings),
        cookie_secure=settings.cookie_secure,
        clock=lambda: retry_at,
    )
    with pytest.raises(WorkspaceContextUnauthorized):
        await resolve_workspace_context(
            cookie_value=cookie,
            settings=settings,
            session_factory=t010_session_factory,
            codec=codec,
            now=retry_at,
        )
