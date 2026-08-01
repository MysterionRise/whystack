"""Create the walking-skeleton canonical persistence schema.

Revision ID: 0001_walking_skeleton
Revises:
Create Date: 2026-08-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_walking_skeleton"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB()
TIMESTAMP = sa.DateTime(timezone=True)

ENUMS = (
    postgresql.ENUM("seed", "guest", "local", name="workspace_kind"),
    postgresql.ENUM("active", "deleting", "deleted", name="workspace_status"),
    postgresql.ENUM("queued", "running", "completed", "failed", name="run_status"),
    postgresql.ENUM(
        "run.queued",
        "run.started",
        "ui.envelope",
        "run.completed",
        "run.failed",
        name="run_event_kind",
    ),
    postgresql.ENUM("execute-run", "delete-workspace", name="job_kind"),
    postgresql.ENUM("available", "leased", "completed", "failed", name="job_status"),
)


def _enum(name: str) -> postgresql.ENUM:
    values = next(item.enums for item in ENUMS if item.name == name)
    return postgresql.ENUM(*values, name=name, create_type=False)


def _created_at() -> sa.Column[object]:
    return sa.Column(
        "created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()
    )


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in ENUMS:
        enum_type.create(bind, checkfirst=False)

    op.create_table(
        "workspaces",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("kind", _enum("workspace_kind"), nullable=False),
        sa.Column(
            "status",
            _enum("workspace_status"),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "seed_parent_id",
            UUID,
            sa.ForeignKey("workspaces.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("expires_at", TIMESTAMP, nullable=True),
        _created_at(),
        sa.Column(
            "updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "(kind = 'guest' AND seed_parent_id IS NOT NULL AND "
            "expires_at IS NOT NULL) "
            "OR (kind IN ('seed', 'local') AND seed_parent_id IS NULL "
            "AND expires_at IS NULL)",
            name="ck_workspaces_shape",
        ),
    )

    op.create_table(
        "guest_sessions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "workspace_id",
            UUID,
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("expires_at", TIMESTAMP, nullable=False),
        sa.Column("revoked_at", TIMESTAMP, nullable=True),
        _created_at(),
        sa.UniqueConstraint("workspace_id", name="uq_guest_sessions_workspace_id"),
        sa.UniqueConstraint("token_hash", name="uq_guest_sessions_token_hash"),
    )

    op.create_table(
        "decisions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "workspace_id",
            UUID,
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("current_revision", sa.Integer(), nullable=False, server_default="1"),
        _created_at(),
        sa.Column(
            "updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("workspace_id", "id", name="uq_decisions_workspace_id_id"),
        sa.CheckConstraint(
            "current_revision >= 1", name="ck_decisions_current_revision_positive"
        ),
    )
    op.create_index("ix_decisions_workspace_id", "decisions", ["workspace_id"])

    op.create_table(
        "decision_revisions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("workspace_id", UUID, nullable=False),
        sa.Column("decision_id", UUID, nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "frame_schema_version", sa.String(16), nullable=False, server_default="1.0"
        ),
        sa.Column("question", sa.String(500), nullable=False),
        sa.Column("context", sa.String(10000), nullable=False),
        sa.Column("options", JSONB, nullable=False),
        sa.Column("criteria", JSONB, nullable=False),
        sa.Column("constraints", JSONB, nullable=False),
        sa.Column("snapshot_hash", sa.String(64), nullable=False),
        _created_at(),
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
    )
    op.create_index(
        "ix_decision_revisions_workspace_decision",
        "decision_revisions",
        ["workspace_id", "decision_id"],
    )

    op.create_table(
        "runs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("workspace_id", UUID, nullable=False),
        sa.Column("decision_id", UUID, nullable=False),
        sa.Column("decision_revision_id", UUID, nullable=False),
        sa.Column(
            "status", _enum("run_status"), nullable=False, server_default="queued"
        ),
        sa.Column(
            "fixture_version",
            sa.String(80),
            nullable=False,
            server_default="walking-skeleton-v1",
        ),
        sa.Column("input_snapshot", JSONB, nullable=False),
        sa.Column("input_snapshot_hash", sa.String(64), nullable=False),
        sa.Column(
            "last_event_sequence", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("terminal_event_sequence", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(80), nullable=True),
        _created_at(),
        sa.Column("started_at", TIMESTAMP, nullable=True),
        sa.Column("completed_at", TIMESTAMP, nullable=True),
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
    )
    op.create_index("ix_runs_workspace_id", "runs", ["workspace_id"])

    op.create_table(
        "run_events",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("workspace_id", UUID, nullable=False),
        sa.Column("run_id", UUID, nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("kind", _enum("run_event_kind"), nullable=False),
        sa.Column(
            "payload_schema_version",
            sa.String(16),
            nullable=False,
            server_default="1.0",
        ),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        _created_at(),
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
    )
    op.create_index(
        "ix_run_events_workspace_run_sequence",
        "run_events",
        ["workspace_id", "run_id", "sequence"],
    )

    op.create_table(
        "jobs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "workspace_id",
            UUID,
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", _enum("job_kind"), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column(
            "status", _enum("job_status"), nullable=False, server_default="available"
        ),
        sa.Column("available_at", TIMESTAMP, nullable=False),
        sa.Column("lease_owner", sa.String(120), nullable=True),
        sa.Column("lease_expires_at", TIMESTAMP, nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error_code", sa.String(80), nullable=True),
        _created_at(),
        sa.Column(
            "updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()
        ),
        sa.Column("completed_at", TIMESTAMP, nullable=True),
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
    )
    op.create_index("ix_jobs_workspace_id", "jobs", ["workspace_id"])

    op.create_table(
        "idempotency_records",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "workspace_id",
            UUID,
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("operation", sa.String(120), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=False),
        sa.Column("response_body", JSONB, nullable=False),
        sa.Column("resource_id", UUID, nullable=True),
        sa.Column("expires_at", TIMESTAMP, nullable=False),
        _created_at(),
        sa.UniqueConstraint(
            "workspace_id",
            "operation",
            "key",
            name="uq_idempotency_records_workspace_operation_key",
        ),
        sa.CheckConstraint(
            "char_length(key) BETWEEN 8 AND 128", name="ck_idempotency_records_key"
        ),
    )
    op.create_index(
        "ix_idempotency_records_workspace_id",
        "idempotency_records",
        ["workspace_id"],
    )

    op.create_table(
        "reset_replay_receipts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("old_session_fingerprint", sa.LargeBinary(), nullable=False),
        sa.Column(
            "operation",
            sa.String(80),
            nullable=False,
            server_default="reset-guest-session-v1",
        ),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("replacement_session_id", UUID, nullable=False),
        sa.Column("replacement_token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("replacement_token_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("encryption_key_id", sa.String(120), nullable=False),
        sa.Column(
            "aad_version",
            sa.String(40),
            nullable=False,
            server_default="reset-replay-aad-v1",
        ),
        sa.Column(
            "cookie_profile_version",
            sa.String(40),
            nullable=False,
            server_default="public-demo-v1",
        ),
        sa.Column("cookie_signing_key_id", sa.String(120), nullable=False),
        sa.Column("cookie_issued_at", TIMESTAMP, nullable=False),
        sa.Column("cookie_expires_at", TIMESTAMP, nullable=False),
        sa.Column(
            "response_status", sa.Integer(), nullable=False, server_default="202"
        ),
        sa.Column(
            "response_content_type",
            sa.String(80),
            nullable=False,
            server_default="application/json",
        ),
        sa.Column(
            "response_serializer_version",
            sa.String(40),
            nullable=False,
            server_default="canonical-json-v1",
        ),
        sa.Column("response_body_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("response_body_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", TIMESTAMP, nullable=False),
        _created_at(),
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

    op.execute(
        """
        CREATE FUNCTION reject_decision_revision_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF TG_OP = 'UPDATE' OR pg_trigger_depth() <= 1 THEN
                RAISE EXCEPTION 'decision revisions are immutable';
            END IF;
            RETURN OLD;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_decision_revisions_immutable
        BEFORE UPDATE OR DELETE ON decision_revisions
        FOR EACH ROW EXECUTE FUNCTION reject_decision_revision_mutation()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_decision_revisions_immutable ON decision_revisions"
    )
    op.execute("DROP FUNCTION IF EXISTS reject_decision_revision_mutation()")
    for table_name in (
        "reset_replay_receipts",
        "idempotency_records",
        "jobs",
        "run_events",
        "runs",
        "decision_revisions",
        "decisions",
        "guest_sessions",
        "workspaces",
    ):
        op.drop_table(table_name)
    bind = op.get_bind()
    for enum_type in reversed(ENUMS):
        enum_type.drop(bind, checkfirst=False)
