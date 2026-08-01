from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import Select, and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    Decision,
    DecisionRevision,
    Job,
    JobStatus,
    ResetReplayReceipt,
    Run,
    RunEvent,
    RunEventKind,
    RunStatus,
    WorkspaceKind,
)


class ResetReplayIntegrityError(ValueError):
    """Authenticated reset-replay material failed a post-decryption check."""


@dataclass(frozen=True, slots=True)
class ResetReplayAad:
    id: uuid.UUID
    old_session_fingerprint: bytes
    operation: str
    key: str
    request_hash: str
    replacement_session_id: uuid.UUID
    replacement_token_hash: bytes
    encryption_key_id: str
    aad_version: str
    cookie_profile_version: str
    cookie_signing_key_id: str
    cookie_issued_at: datetime
    cookie_expires_at: datetime
    response_status: int
    response_content_type: str
    response_serializer_version: str
    response_body_hash: str
    created_at: datetime
    expires_at: datetime


def sha256_bytes(value: bytes) -> bytes:
    return hashlib.sha256(value).digest()


def _canonical_datetime(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("AAD timestamps must be timezone-aware")
    normalized = value.astimezone(UTC)
    return normalized.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def canonical_reset_replay_aad(aad: ResetReplayAad) -> bytes:
    """Encode the bounded receipt context using its RFC-8785-compatible profile."""

    document: dict[str, str | int] = {}
    for name, value in asdict(aad).items():
        if isinstance(value, bytes):
            document[name] = value.hex()
        elif isinstance(value, uuid.UUID):
            document[name] = str(value)
        elif isinstance(value, datetime):
            document[name] = _canonical_datetime(value)
        elif isinstance(value, (str, int)):
            document[name] = value
        else:  # pragma: no cover - dataclass field types make this unreachable
            raise TypeError(f"Unsupported AAD value for {name}")
    return json.dumps(
        document,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _aes_256_gcm(key: bytes) -> AESGCM:
    if len(key) != 32:
        raise ValueError("AES-256-GCM requires a 32-byte key")
    return AESGCM(key)


def encrypt_replacement_token(
    token: bytes,
    *,
    key: bytes,
    aad: ResetReplayAad,
) -> bytes:
    """Encrypt only replacement token material with a fresh 96-bit nonce."""

    nonce = os.urandom(12)
    encrypted = _aes_256_gcm(key).encrypt(
        nonce,
        token,
        canonical_reset_replay_aad(aad),
    )
    return nonce + encrypted


def decrypt_replacement_token(
    ciphertext: bytes,
    *,
    key: bytes,
    aad: ResetReplayAad,
    expected_token_hash: bytes,
    response_body_bytes: bytes,
) -> bytes:
    """Authenticate, decrypt, and verify replay material before returning it."""

    if len(ciphertext) < 12 + 16:
        raise ValueError("Reset replay ciphertext is too short")
    nonce, encrypted = ciphertext[:12], ciphertext[12:]
    token = _aes_256_gcm(key).decrypt(
        nonce,
        encrypted,
        canonical_reset_replay_aad(aad),
    )
    calculated_token_hash = sha256_bytes(token)
    if not hmac.compare_digest(calculated_token_hash, aad.replacement_token_hash):
        raise ResetReplayIntegrityError("Replacement token does not match receipt")
    if not hmac.compare_digest(calculated_token_hash, expected_token_hash):
        raise ResetReplayIntegrityError("Replacement token does not match session")
    calculated_response_hash = sha256_bytes(response_body_bytes).hex()
    if not hmac.compare_digest(calculated_response_hash, aad.response_body_hash):
        raise ResetReplayIntegrityError("Stored reset response bytes were modified")
    return token


def validate_workspace_shape(
    kind: WorkspaceKind,
    seed_parent_id: uuid.UUID | None,
    created_at: datetime,
    expires_at: datetime | None,
) -> None:
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ValueError("Workspace timestamps must be timezone-aware")
    if kind is WorkspaceKind.GUEST:
        if seed_parent_id is None or expires_at != created_at + timedelta(hours=24):
            raise ValueError(
                "Guest workspace requires a seed parent and 24-hour expiry"
            )
        return
    if seed_parent_id is not None or expires_at is not None:
        raise ValueError("Seed and local workspaces cannot have parent or expiry")


_RUN_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.QUEUED: frozenset({RunStatus.RUNNING, RunStatus.FAILED}),
    RunStatus.RUNNING: frozenset({RunStatus.COMPLETED, RunStatus.FAILED}),
    RunStatus.COMPLETED: frozenset(),
    RunStatus.FAILED: frozenset(),
}


def assert_run_transition(current: RunStatus, target: RunStatus) -> None:
    if target not in _RUN_TRANSITIONS[current]:
        raise ValueError(f"Invalid run transition: {current.value} -> {target.value}")


def assert_contiguous_event_sequence(*, last_sequence: int, next_sequence: int) -> None:
    if last_sequence < 0 or next_sequence < 1 or next_sequence != last_sequence + 1:
        raise ValueError("Run event sequence must be positive and contiguous")


class DecisionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self,
        *,
        workspace_id: uuid.UUID,
        decision_id: uuid.UUID,
        for_update: bool = False,
    ) -> Decision | None:
        statement = select(Decision).where(
            Decision.workspace_id == workspace_id,
            Decision.id == decision_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return await self._session.scalar(statement)

    async def append_revision(
        self,
        *,
        workspace_id: uuid.UUID,
        decision_id: uuid.UUID,
        revision: DecisionRevision,
    ) -> DecisionRevision:
        decision = await self.get(
            workspace_id=workspace_id,
            decision_id=decision_id,
            for_update=True,
        )
        if decision is None:
            raise LookupError("Decision is missing from trusted workspace")
        if revision.workspace_id != workspace_id or revision.decision_id != decision_id:
            raise ValueError("Revision scope must match its parent decision")
        self._session.add(revision)
        await self._session.flush()
        return revision


class RunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self,
        *,
        workspace_id: uuid.UUID,
        run_id: uuid.UUID,
        for_update: bool = False,
    ) -> Run | None:
        statement = select(Run).where(
            Run.workspace_id == workspace_id,
            Run.id == run_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return await self._session.scalar(statement)

    async def append_event(
        self,
        *,
        workspace_id: uuid.UUID,
        run_id: uuid.UUID,
        event: RunEvent,
    ) -> RunEvent:
        run = await self.get(
            workspace_id=workspace_id,
            run_id=run_id,
            for_update=True,
        )
        if run is None:
            raise LookupError("Run is missing from trusted workspace")
        if event.workspace_id != workspace_id or event.run_id != run_id:
            raise ValueError("Run event scope must match its parent run")
        if run.terminal_event_sequence is not None:
            raise ValueError("Terminal run cannot receive another event")
        assert_contiguous_event_sequence(
            last_sequence=run.last_event_sequence,
            next_sequence=event.sequence,
        )
        run.last_event_sequence = event.sequence
        if event.kind in {RunEventKind.RUN_COMPLETED, RunEventKind.RUN_FAILED}:
            run.terminal_event_sequence = event.sequence
        self._session.add(event)
        await self._session.flush()
        return event


class JobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def claim_statement(*, now: datetime) -> Select[tuple[Job]]:
        return (
            select(Job)
            .where(
                Job.available_at <= now,
                or_(
                    Job.status == JobStatus.AVAILABLE,
                    and_(
                        Job.status == JobStatus.LEASED,
                        Job.lease_expires_at <= now,
                    ),
                ),
            )
            .order_by(Job.available_at, Job.created_at, Job.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )


class ResetReplayRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self,
        *,
        old_session_fingerprint: bytes,
        operation: str,
        key: str,
        now: datetime,
    ) -> ResetReplayReceipt | None:
        return await self._session.scalar(
            select(ResetReplayReceipt).where(
                ResetReplayReceipt.old_session_fingerprint == old_session_fingerprint,
                ResetReplayReceipt.operation == operation,
                ResetReplayReceipt.key == key,
                ResetReplayReceipt.expires_at > now,
            )
        )

    async def purge_expired(self, *, now: datetime) -> int:
        deleted_ids = await self._session.scalars(
            delete(ResetReplayReceipt)
            .where(ResetReplayReceipt.expires_at <= now)
            .returning(ResetReplayReceipt.id)
        )
        return len(deleted_ids.all())
