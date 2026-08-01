from __future__ import annotations

import enum
import uuid
from datetime import datetime

import sqlalchemy as sa
import uuid6
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_uuid7() -> uuid.UUID:
    """Return a server-generated, time-ordered UUIDv7."""

    return uuid6.uuid7()


class WorkspaceKind(enum.StrEnum):
    SEED = "seed"
    GUEST = "guest"
    LOCAL = "local"


class WorkspaceStatus(enum.StrEnum):
    ACTIVE = "active"
    DELETING = "deleting"
    DELETED = "deleted"


class RunStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RunEventKind(enum.StrEnum):
    RUN_QUEUED = "run.queued"
    RUN_STARTED = "run.started"
    UI_ENVELOPE = "ui.envelope"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"


class JobKind(enum.StrEnum):
    EXECUTE_RUN = "execute-run"
    DELETE_WORKSPACE = "delete-workspace"


class JobStatus(enum.StrEnum):
    AVAILABLE = "available"
    LEASED = "leased"
    COMPLETED = "completed"
    FAILED = "failed"


def _enum_values(members: type[enum.Enum]) -> list[str]:
    return [str(member.value) for member in members]


def _enum_type(enum_type: type[enum.Enum], name: str) -> sa.Enum:
    return sa.Enum(
        enum_type,
        name=name,
        values_callable=_enum_values,
        validate_strings=True,
    )


UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB()
TIMESTAMP = sa.DateTime(timezone=True)


class Base(DeclarativeBase):
    pass


class Workspace(Base):
    __tablename__ = "workspaces"
    __table_args__ = (
        sa.CheckConstraint(
            "(kind = 'guest' AND seed_parent_id IS NOT NULL AND "
            "expires_at IS NOT NULL) "
            "OR (kind IN ('seed', 'local') AND seed_parent_id IS NULL "
            "AND expires_at IS NULL)",
            name="ck_workspaces_shape",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=new_uuid7)
    kind: Mapped[WorkspaceKind] = mapped_column(
        _enum_type(WorkspaceKind, "workspace_kind"), nullable=False
    )
    status: Mapped[WorkspaceStatus] = mapped_column(
        _enum_type(WorkspaceStatus, "workspace_status"),
        nullable=False,
        default=WorkspaceStatus.ACTIVE,
        server_default=WorkspaceStatus.ACTIVE.value,
    )
    seed_parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID,
        sa.ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=True,
    )
    expires_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=sa.func.now()
    )


class GuestSession(Base):
    __tablename__ = "guest_sessions"
    __table_args__ = (
        sa.UniqueConstraint("workspace_id", name="uq_guest_sessions_workspace_id"),
        sa.UniqueConstraint("token_hash", name="uq_guest_sessions_token_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=new_uuid7)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID,
        sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[bytes] = mapped_column(sa.LargeBinary, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=sa.func.now()
    )


class Decision(Base):
    __tablename__ = "decisions"
    __table_args__ = (
        sa.UniqueConstraint("workspace_id", "id", name="uq_decisions_workspace_id_id"),
        sa.CheckConstraint(
            "current_revision >= 1", name="ck_decisions_current_revision_positive"
        ),
        sa.Index("ix_decisions_workspace_id", "workspace_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=new_uuid7)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID,
        sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    current_revision: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=1, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=sa.func.now()
    )


class DecisionRevision(Base):
    __tablename__ = "decision_revisions"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["workspace_id", "decision_id"],
            ["decisions.workspace_id", "decisions.id"],
            ondelete="CASCADE",
            name="fk_decision_revisions_workspace_decision",
        ),
        sa.UniqueConstraint(
            "decision_id",
            "revision",
            name="uq_decision_revisions_decision_revision",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "decision_id",
            "id",
            name="uq_decision_revisions_workspace_decision_id",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_decision_revisions_revision"),
        sa.CheckConstraint(
            "frame_schema_version = '1.0'",
            name="ck_decision_revisions_schema_version",
        ),
        sa.CheckConstraint(
            "char_length(btrim(question)) BETWEEN 1 AND 500",
            name="ck_decision_revisions_question",
        ),
        sa.CheckConstraint(
            "char_length(context) <= 10000", name="ck_decision_revisions_context"
        ),
        sa.Index(
            "ix_decision_revisions_workspace_decision",
            "workspace_id",
            "decision_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=new_uuid7)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID, nullable=False)
    decision_id: Mapped[uuid.UUID] = mapped_column(UUID, nullable=False)
    revision: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    frame_schema_version: Mapped[str] = mapped_column(
        sa.String(16), nullable=False, default="1.0", server_default="1.0"
    )
    question: Mapped[str] = mapped_column(sa.String(500), nullable=False)
    context: Mapped[str] = mapped_column(sa.String(10000), nullable=False)
    options: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    criteria: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    constraints: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=sa.func.now()
    )


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["workspace_id", "decision_id"],
            ["decisions.workspace_id", "decisions.id"],
            ondelete="CASCADE",
            name="fk_runs_workspace_decision",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "decision_id", "decision_revision_id"],
            [
                "decision_revisions.workspace_id",
                "decision_revisions.decision_id",
                "decision_revisions.id",
            ],
            ondelete="CASCADE",
            name="fk_runs_workspace_decision_revision",
        ),
        sa.UniqueConstraint("workspace_id", "id", name="uq_runs_workspace_id_id"),
        sa.CheckConstraint(
            "last_event_sequence >= 0", name="ck_runs_last_event_sequence"
        ),
        sa.CheckConstraint(
            "terminal_event_sequence IS NULL OR terminal_event_sequence >= 1",
            name="ck_runs_terminal_event_sequence",
        ),
        sa.CheckConstraint(
            "fixture_version = 'walking-skeleton-v1'", name="ck_runs_fixture_version"
        ),
        sa.Index("ix_runs_workspace_id", "workspace_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=new_uuid7)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID, nullable=False)
    decision_id: Mapped[uuid.UUID] = mapped_column(UUID, nullable=False)
    decision_revision_id: Mapped[uuid.UUID] = mapped_column(UUID, nullable=False)
    status: Mapped[RunStatus] = mapped_column(
        _enum_type(RunStatus, "run_status"),
        nullable=False,
        default=RunStatus.QUEUED,
        server_default=RunStatus.QUEUED.value,
    )
    fixture_version: Mapped[str] = mapped_column(
        sa.String(80),
        nullable=False,
        default="walking-skeleton-v1",
        server_default="walking-skeleton-v1",
    )
    input_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    input_snapshot_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    last_event_sequence: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default="0"
    )
    terminal_event_sequence: Mapped[int | None] = mapped_column(
        sa.Integer, nullable=True
    )
    error_code: Mapped[str | None] = mapped_column(sa.String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=sa.func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, nullable=True)


class RunEvent(Base):
    __tablename__ = "run_events"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["workspace_id", "run_id"],
            ["runs.workspace_id", "runs.id"],
            ondelete="CASCADE",
            name="fk_run_events_workspace_run",
        ),
        sa.UniqueConstraint("run_id", "sequence", name="uq_run_events_run_sequence"),
        sa.CheckConstraint("sequence >= 1", name="ck_run_events_sequence_positive"),
        sa.CheckConstraint(
            "payload_schema_version = '1.0'",
            name="ck_run_events_payload_schema_version",
        ),
        sa.Index(
            "ix_run_events_workspace_run_sequence",
            "workspace_id",
            "run_id",
            "sequence",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=new_uuid7)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID, nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID, nullable=False)
    sequence: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    kind: Mapped[RunEventKind] = mapped_column(
        _enum_type(RunEventKind, "run_event_kind"), nullable=False
    )
    payload_schema_version: Mapped[str] = mapped_column(
        sa.String(16), nullable=False, default="1.0", server_default="1.0"
    )
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    payload_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=sa.func.now()
    )


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        sa.CheckConstraint(
            "attempt_count >= 0", name="ck_jobs_attempt_count_non_negative"
        ),
        sa.CheckConstraint(
            "(status = 'leased' AND lease_owner IS NOT NULL "
            "AND lease_expires_at IS NOT NULL) OR "
            "(status <> 'leased' AND lease_owner IS NULL "
            "AND lease_expires_at IS NULL)",
            name="ck_jobs_lease_shape",
        ),
        sa.Index("ix_jobs_workspace_id", "workspace_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=new_uuid7)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID,
        sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[JobKind] = mapped_column(
        _enum_type(JobKind, "job_kind"), nullable=False
    )
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        _enum_type(JobStatus, "job_status"),
        nullable=False,
        default=JobStatus.AVAILABLE,
        server_default=JobStatus.AVAILABLE.value,
    )
    available_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(sa.String(120), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, nullable=True)
    attempt_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default="0"
    )
    last_error_code: Mapped[str | None] = mapped_column(sa.String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=sa.func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, nullable=True)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        sa.UniqueConstraint(
            "workspace_id",
            "operation",
            "key",
            name="uq_idempotency_records_workspace_operation_key",
        ),
        sa.CheckConstraint(
            "char_length(key) BETWEEN 8 AND 128", name="ck_idempotency_records_key"
        ),
        sa.Index("ix_idempotency_records_workspace_id", "workspace_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=new_uuid7)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID,
        sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    operation: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    key: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    response_status: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    response_body: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=sa.func.now()
    )


class ResetReplayReceipt(Base):
    __tablename__ = "reset_replay_receipts"
    __table_args__ = (
        sa.UniqueConstraint(
            "old_session_fingerprint",
            "operation",
            "key",
            name="uq_reset_replay_receipts_fingerprint_operation_key",
        ),
        sa.CheckConstraint(
            "expires_at = created_at + INTERVAL '10 minutes'",
            name="ck_reset_replay_receipts_expiry",
        ),
        sa.CheckConstraint(
            "operation = 'reset-guest-session-v1'",
            name="ck_reset_replay_receipts_operation",
        ),
        sa.CheckConstraint(
            "aad_version = 'reset-replay-aad-v1'",
            name="ck_reset_replay_receipts_aad_version",
        ),
        sa.CheckConstraint(
            "cookie_profile_version = 'public-demo-v1'",
            name="ck_reset_replay_receipts_cookie_profile",
        ),
        sa.CheckConstraint(
            "response_status = 202", name="ck_reset_replay_receipts_status"
        ),
        sa.CheckConstraint(
            "response_content_type = 'application/json'",
            name="ck_reset_replay_receipts_content_type",
        ),
        sa.CheckConstraint(
            "response_serializer_version = 'canonical-json-v1'",
            name="ck_reset_replay_receipts_serializer",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=new_uuid7)
    old_session_fingerprint: Mapped[bytes] = mapped_column(
        sa.LargeBinary, nullable=False
    )
    operation: Mapped[str] = mapped_column(
        sa.String(80),
        nullable=False,
        default="reset-guest-session-v1",
        server_default="reset-guest-session-v1",
    )
    key: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    replacement_session_id: Mapped[uuid.UUID] = mapped_column(UUID, nullable=False)
    replacement_token_hash: Mapped[bytes] = mapped_column(
        sa.LargeBinary, nullable=False
    )
    replacement_token_ciphertext: Mapped[bytes] = mapped_column(
        sa.LargeBinary, nullable=False
    )
    encryption_key_id: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    aad_version: Mapped[str] = mapped_column(
        sa.String(40),
        nullable=False,
        default="reset-replay-aad-v1",
        server_default="reset-replay-aad-v1",
    )
    cookie_profile_version: Mapped[str] = mapped_column(
        sa.String(40),
        nullable=False,
        default="public-demo-v1",
        server_default="public-demo-v1",
    )
    cookie_signing_key_id: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    cookie_issued_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False)
    cookie_expires_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False)
    response_status: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=202, server_default="202"
    )
    response_content_type: Mapped[str] = mapped_column(
        sa.String(80),
        nullable=False,
        default="application/json",
        server_default="application/json",
    )
    response_serializer_version: Mapped[str] = mapped_column(
        sa.String(40),
        nullable=False,
        default="canonical-json-v1",
        server_default="canonical-json-v1",
    )
    response_body_bytes: Mapped[bytes] = mapped_column(sa.LargeBinary, nullable=False)
    response_body_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=sa.func.now()
    )
