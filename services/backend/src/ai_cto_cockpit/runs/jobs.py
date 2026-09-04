from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_cto_cockpit.persistence.models import Job, JobKind, JobStatus
from ai_cto_cockpit.persistence.repositories import JobRepository

type JsonObject = dict[str, object]
type SessionFactory = async_sessionmaker[AsyncSession]

DEFAULT_LEASE_DURATION = timedelta(seconds=30)


@dataclass(frozen=True, slots=True)
class JobLease:
    """Immutable ownership fence for one durable job attempt."""

    job_id: uuid.UUID
    workspace_id: uuid.UUID
    kind: JobKind
    payload: JsonObject
    worker_id: str
    attempt_count: int
    lease_expires_at: datetime


def _validate_lease_request(
    *,
    worker_id: str,
    now: datetime | None,
    lease_duration: timedelta,
) -> None:
    if not worker_id or len(worker_id) > 120:
        raise ValueError("Worker ID must contain 1 to 120 characters")
    if now is not None and (now.tzinfo is None or now.utcoffset() is None):
        raise ValueError("Job lease time must be timezone-aware")
    if lease_duration <= timedelta(0):
        raise ValueError("Job lease duration must be positive")


async def transaction_time(
    session: AsyncSession,
    *,
    override: datetime | None,
) -> datetime:
    """Use PostgreSQL time in production while retaining deterministic tests."""

    value = override
    if value is None:
        value = await session.scalar(select(func.clock_timestamp()))
    if value is None or value.tzinfo is None or value.utcoffset() is None:
        raise RuntimeError("PostgreSQL must supply a timezone-aware timestamp")
    return value


def _lease_from_job(job: Job) -> JobLease:
    if (
        job.status is not JobStatus.LEASED
        or job.lease_owner is None
        or job.lease_expires_at is None
    ):
        raise RuntimeError("A JobLease can only be created from a leased job")
    return JobLease(
        job_id=job.id,
        workspace_id=job.workspace_id,
        kind=job.kind,
        payload=copy.deepcopy(job.payload),
        worker_id=job.lease_owner,
        attempt_count=job.attempt_count,
        lease_expires_at=job.lease_expires_at,
    )


async def claim_job(
    *,
    session_factory: SessionFactory,
    worker_id: str,
    now: datetime | None,
    lease_duration: timedelta = DEFAULT_LEASE_DURATION,
) -> JobLease | None:
    """Claim the oldest eligible job with one committed attempt fence."""

    _validate_lease_request(
        worker_id=worker_id,
        now=now,
        lease_duration=lease_duration,
    )
    async with session_factory.begin() as session:
        transaction_now = await transaction_time(session, override=now)
        job = await session.scalar(JobRepository.claim_statement(now=transaction_now))
        if job is None:
            return None
        job.status = JobStatus.LEASED
        job.lease_owner = worker_id
        job.lease_expires_at = transaction_now + lease_duration
        job.attempt_count += 1
        job.updated_at = transaction_now
        await session.flush()
        return _lease_from_job(job)


async def renew_job_lease(
    *,
    session_factory: SessionFactory,
    lease: JobLease,
    now: datetime | None,
    lease_duration: timedelta = DEFAULT_LEASE_DURATION,
) -> JobLease | None:
    """Renew only the exact unexpired owner/attempt/expiry fence."""

    _validate_lease_request(
        worker_id=lease.worker_id,
        now=now,
        lease_duration=lease_duration,
    )
    async with session_factory.begin() as session:
        transaction_now = await transaction_time(session, override=now)
        job = await session.scalar(
            select(Job)
            .where(
                Job.id == lease.job_id,
                Job.workspace_id == lease.workspace_id,
            )
            .with_for_update()
        )
        lease_expires_at = job.lease_expires_at if job is not None else None
        if (
            job is None
            or job.status is not JobStatus.LEASED
            or job.lease_owner != lease.worker_id
            or job.attempt_count != lease.attempt_count
            or lease_expires_at != lease.lease_expires_at
            or lease_expires_at is None
            or lease_expires_at <= transaction_now
        ):
            return None
        job.lease_expires_at = transaction_now + lease_duration
        job.updated_at = transaction_now
        await session.flush()
        return _lease_from_job(job)
