from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import uuid
from collections.abc import Generator, Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, delete, inspect, select, update
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.engine.reflection import Inspector
from sqlalchemy.exc import DBAPIError
from sqlalchemy.sql.base import Executable

from ai_cto_cockpit.persistence.models import (
    Base,
    Decision,
    DecisionRevision,
    GuestSession,
    ResetReplayReceipt,
    Run,
    RunEvent,
    RunEventKind,
    RunStatus,
    Workspace,
    WorkspaceKind,
    WorkspaceStatus,
)
from ai_cto_cockpit.persistence.repositories import (
    DecisionRepository,
    ResetReplayRepository,
    RunRepository,
    sha256_bytes,
)
from ai_cto_cockpit.persistence.session import (
    create_database_engine,
    create_session_factory,
    transaction_session,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
ALEMBIC_CONFIG = REPOSITORY_ROOT / "services" / "backend" / "alembic.ini"
POSTGRES_IMAGE = (
    "postgres:17.10-bookworm@sha256:"
    "4f736ae292687621d4dbe0d499ffd024a36bd2ee7d8ca6f2ccd4c800f047b394"
)
EXPECTED_HEAD = "0001_walking_skeleton"
EXPECTED_TABLES = {
    "workspaces",
    "guest_sessions",
    "decisions",
    "decision_revisions",
    "runs",
    "run_events",
    "jobs",
    "idempotency_records",
    "reset_replay_receipts",
}
NOW = datetime(2026, 8, 1, 12, 30, tzinfo=UTC)

ForeignKeySignature = tuple[tuple[str, ...], str, tuple[str, ...], str | None]

EXPECTED_FOREIGN_KEYS: dict[str, set[ForeignKeySignature]] = {
    "workspaces": {
        (("seed_parent_id",), "workspaces", ("id",), "RESTRICT"),
    },
    "guest_sessions": {
        (("workspace_id",), "workspaces", ("id",), "CASCADE"),
    },
    "decisions": {
        (("workspace_id",), "workspaces", ("id",), "CASCADE"),
    },
    "decision_revisions": {
        (
            ("workspace_id", "decision_id"),
            "decisions",
            ("workspace_id", "id"),
            "CASCADE",
        ),
    },
    "runs": {
        (
            ("workspace_id", "decision_id"),
            "decisions",
            ("workspace_id", "id"),
            "CASCADE",
        ),
        (
            ("workspace_id", "decision_id", "decision_revision_id"),
            "decision_revisions",
            ("workspace_id", "decision_id", "id"),
            "CASCADE",
        ),
    },
    "run_events": {
        (
            ("workspace_id", "run_id"),
            "runs",
            ("workspace_id", "id"),
            "CASCADE",
        ),
    },
    "jobs": {
        (("workspace_id",), "workspaces", ("id",), "CASCADE"),
    },
    "idempotency_records": {
        (("workspace_id",), "workspaces", ("id",), "CASCADE"),
    },
    "reset_replay_receipts": set(),
}

EXPECTED_UNIQUES = {
    "guest_sessions": {("workspace_id",), ("token_hash",)},
    "decisions": {("workspace_id", "id")},
    "decision_revisions": {
        ("decision_id", "revision"),
        ("workspace_id", "decision_id", "id"),
    },
    "runs": {("workspace_id", "id")},
    "run_events": {("run_id", "sequence")},
    "idempotency_records": {("workspace_id", "operation", "key")},
    "reset_replay_receipts": {
        ("old_session_fingerprint", "operation", "key"),
    },
}

EXPECTED_INDEX_COLUMNS = {
    "decisions": {("workspace_id",)},
    "decision_revisions": {("workspace_id", "decision_id")},
    "runs": {("workspace_id",)},
    "run_events": {("workspace_id", "run_id", "sequence")},
    "jobs": {("workspace_id",)},
    "idempotency_records": {("workspace_id",)},
}


def _run(command_line: Sequence[str], *, timeout: int = 60) -> str:
    result = subprocess.run(
        list(command_line),
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        check=False,
        text=True,
        timeout=timeout,
    )
    assert result.returncode == 0, (
        f"Command exited {result.returncode}: {' '.join(command_line)}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    return result.stdout.strip()


@contextmanager
def _database_environment(database_url: str) -> Generator[None]:
    previous_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = database_url
    try:
        yield
    finally:
        if previous_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_url


@pytest.fixture(scope="module")
def postgres_url() -> Iterator[str]:
    assert shutil.which("docker"), "Docker CLI is required for migration tests"
    _run(["docker", "info", "--format", "{{.ServerVersion}}"])
    container = f"cockpit_t008_{uuid.uuid4().hex[:12]}"
    password = uuid.uuid4().hex
    _run(
        [
            "docker",
            "run",
            "--detach",
            "--rm",
            "--name",
            container,
            "--env",
            "POSTGRES_DB=ai_cto",
            "--env",
            "POSTGRES_USER=ai_cto",
            "--env",
            f"POSTGRES_PASSWORD={password}",
            "--health-cmd",
            "pg_isready -U ai_cto -d ai_cto",
            "--health-interval",
            "1s",
            "--health-timeout",
            "3s",
            "--health-retries",
            "60",
            "--publish",
            "127.0.0.1::5432",
            POSTGRES_IMAGE,
        ],
        timeout=120,
    )
    try:
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            state = json.loads(
                _run(["docker", "inspect", container, "--format", "{{json .State}}"])
            )
            if state.get("Health", {}).get("Status") == "healthy":
                break
            time.sleep(0.25)
        else:
            raise AssertionError("PostgreSQL container did not become healthy")
        port_text = _run(["docker", "port", container, "5432/tcp"])
        port = int(port_text.rsplit(":", 1)[1])
        yield (f"postgresql+psycopg://ai_cto:{password}@127.0.0.1:{port}/ai_cto")
    finally:
        subprocess.run(
            ["docker", "rm", "--force", container],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            check=False,
            text=True,
            timeout=30,
        )


@pytest.fixture()
def migrated_engine(postgres_url: str) -> Iterator[Engine]:
    config = Config(str(ALEMBIC_CONFIG))
    with _database_environment(postgres_url):
        command.downgrade(config, "base")
        command.upgrade(config, "head")
    engine = create_engine(postgres_url)
    try:
        yield engine
    finally:
        engine.dispose()


def _heads(engine: Engine) -> tuple[list[str], list[str]]:
    with engine.connect() as connection:
        database_heads = sorted(
            MigrationContext.configure(connection).get_current_heads()
        )
    repository_heads = sorted(
        ScriptDirectory.from_config(Config(str(ALEMBIC_CONFIG))).get_heads()
    )
    return database_heads, repository_heads


def _uuid7(number: int) -> uuid.UUID:
    return uuid.UUID(f"01890f9a-7bcd-7abc-8def-{number:012x}")


def _foreign_key_signatures(
    inspector: Inspector,
    table_name: str,
) -> set[tuple[tuple[str, ...], str, tuple[str, ...], str | None]]:
    signatures: set[ForeignKeySignature] = set()
    for item in inspector.get_foreign_keys(table_name):
        ondelete = item.get("options", {}).get("ondelete")
        signatures.add(
            (
                tuple(item["constrained_columns"]),
                str(item["referred_table"]),
                tuple(item["referred_columns"]),
                str(ondelete).upper() if ondelete is not None else None,
            )
        )
    return signatures


def _unique_signatures(
    inspector: Inspector,
    table_name: str,
) -> set[tuple[str, ...]]:
    return {
        tuple(item["column_names"])
        for item in inspector.get_unique_constraints(table_name)
    }


def _expect_database_rejection(
    connection: Connection,
    statement: Executable,
) -> None:
    savepoint = connection.begin_nested()
    with pytest.raises(DBAPIError):
        connection.execute(statement)
    savepoint.rollback()


def _workspace(workspace_id: uuid.UUID) -> Workspace:
    return Workspace(
        id=workspace_id,
        kind=WorkspaceKind.LOCAL,
        status=WorkspaceStatus.ACTIVE,
        seed_parent_id=None,
        expires_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _revision(
    *,
    workspace_id: uuid.UUID,
    decision_id: uuid.UUID,
    revision_id: uuid.UUID,
    revision: int = 1,
) -> DecisionRevision:
    return DecisionRevision(
        id=revision_id,
        workspace_id=workspace_id,
        decision_id=decision_id,
        revision=revision,
        frame_schema_version="1.0",
        question=f"Question revision {revision}?",
        context="Context",
        options=[{"id": "yes", "label": "Yes"}],
        criteria=[
            {
                "id": "latency",
                "label": "Latency",
                "enteredWeight": "0.00000001",
                "normalizedWeight": "33.3334",
            },
            {
                "id": "cost",
                "label": "Cost",
                "enteredWeight": "9999999999.99999999",
                "normalizedWeight": "66.6666",
            },
        ],
        constraints=[],
        snapshot_hash=f"{revision:064x}",
        created_at=NOW,
    )


def _run_record(
    *,
    workspace_id: uuid.UUID,
    decision_id: uuid.UUID,
    revision_id: uuid.UUID,
    run_id: uuid.UUID,
) -> Run:
    return Run(
        id=run_id,
        workspace_id=workspace_id,
        decision_id=decision_id,
        decision_revision_id=revision_id,
        status=RunStatus.QUEUED,
        fixture_version="walking-skeleton-v1",
        input_snapshot={"decisionRevision": 1},
        input_snapshot_hash="a1" * 32,
        last_event_sequence=0,
        terminal_event_sequence=None,
        error_code=None,
        created_at=NOW,
        started_at=None,
        completed_at=None,
    )


def _receipt(
    *,
    receipt_id: uuid.UUID,
    fingerprint: bytes,
    key: str,
    response_body: bytes,
    created_at: datetime,
) -> ResetReplayReceipt:
    return ResetReplayReceipt(
        id=receipt_id,
        old_session_fingerprint=fingerprint,
        operation="reset-guest-session-v1",
        key=key,
        request_hash="b2" * 32,
        replacement_session_id=_uuid7(900),
        replacement_token_hash=sha256_bytes(b"replacement-token"),
        replacement_token_ciphertext=b"ciphertext",
        encryption_key_id="receipt-key-v1",
        aad_version="reset-replay-aad-v1",
        cookie_profile_version="public-demo-v1",
        cookie_signing_key_id="cookie-key-v1",
        cookie_issued_at=created_at,
        cookie_expires_at=created_at + timedelta(hours=24),
        response_status=202,
        response_content_type="application/json",
        response_serializer_version="canonical-json-v1",
        response_body_bytes=response_body,
        response_body_hash=sha256_bytes(response_body).hex(),
        created_at=created_at,
        expires_at=created_at + timedelta(minutes=10),
    )


def test_upgrade_downgrade_upgrade_round_trip_has_exact_head(
    postgres_url: str,
) -> None:
    config = Config(str(ALEMBIC_CONFIG))
    engine = create_engine(postgres_url)
    try:
        with _database_environment(postgres_url):
            command.upgrade(config, "head")
            assert _heads(engine) == ([EXPECTED_HEAD], [EXPECTED_HEAD])
            command.downgrade(config, "base")
            assert _heads(engine) == ([], [EXPECTED_HEAD])
            assert set(inspect(engine).get_table_names()) == {"alembic_version"}
            command.upgrade(config, "head")
            assert _heads(engine) == ([EXPECTED_HEAD], [EXPECTED_HEAD])
    finally:
        engine.dispose()


def test_migration_matches_model_tables_columns_and_native_types(
    migrated_engine: Engine,
) -> None:
    inspector = inspect(migrated_engine)
    assert set(inspector.get_table_names()) - {"alembic_version"} == EXPECTED_TABLES
    for table_name in EXPECTED_TABLES:
        migrated_columns = {
            column["name"] for column in inspector.get_columns(table_name)
        }
        assert migrated_columns == set(Base.metadata.tables[table_name].columns.keys())

    for table_name in EXPECTED_TABLES:
        for column in inspector.get_columns(table_name):
            if column["name"] == "id" or column["name"].endswith("_id"):
                if column["name"] not in {"encryption_key_id", "cookie_signing_key_id"}:
                    assert column["type"].__class__.__name__ == "UUID"
            if column["name"].endswith("_at"):
                assert getattr(column["type"], "timezone", False) is True


def test_migration_declares_complete_keys_indexes_and_delete_behavior(
    migrated_engine: Engine,
) -> None:
    inspector = inspect(migrated_engine)
    assert set(EXPECTED_FOREIGN_KEYS) == EXPECTED_TABLES
    for table_name, expected in EXPECTED_FOREIGN_KEYS.items():
        assert _foreign_key_signatures(inspector, table_name) == expected

    for table_name, expected in EXPECTED_UNIQUES.items():
        assert _unique_signatures(inspector, table_name) == expected

    for table_name, expected in EXPECTED_INDEX_COLUMNS.items():
        actual = {
            tuple(item["column_names"]) for item in inspector.get_indexes(table_name)
        }
        assert expected <= actual

    receipt_columns = {
        column["name"] for column in inspector.get_columns("reset_replay_receipts")
    }
    assert "workspace_id" not in receipt_columns
    assert inspector.get_foreign_keys("reset_replay_receipts") == []


def test_database_enforces_duplicate_immutability_weight_and_shape_invariants(
    migrated_engine: Engine,
) -> None:
    workspaces = Base.metadata.tables["workspaces"]
    decisions = Base.metadata.tables["decisions"]
    revisions = Base.metadata.tables["decision_revisions"]
    runs = Base.metadata.tables["runs"]
    events = Base.metadata.tables["run_events"]
    idempotency = Base.metadata.tables["idempotency_records"]
    receipts = Base.metadata.tables["reset_replay_receipts"]
    jobs = Base.metadata.tables["jobs"]

    workspace_id = _uuid7(1)
    decision_id = _uuid7(2)
    revision_id = _uuid7(3)
    run_id = _uuid7(4)
    other_decision_id = _uuid7(50)
    other_revision_id = _uuid7(51)
    criteria = [
        {
            "id": "latency",
            "label": "Latency",
            "enteredWeight": "0.00000001",
            "normalizedWeight": "33.3334",
        },
        {
            "id": "cost",
            "label": "Cost",
            "enteredWeight": "9999999999.99999999",
            "normalizedWeight": "66.6666",
        },
    ]
    revision_values = {
        "id": revision_id,
        "workspace_id": workspace_id,
        "decision_id": decision_id,
        "revision": 1,
        "frame_schema_version": "1.0",
        "question": "Which option should we choose?",
        "context": "Context",
        "options": [{"id": "yes", "label": "Yes"}],
        "criteria": criteria,
        "constraints": [],
        "snapshot_hash": "c3" * 32,
        "created_at": NOW,
    }
    receipt_body = b'{"status":"reset-queued","note":"\xe2\x98\x83"}'
    receipt_values = {
        "id": _uuid7(30),
        "old_session_fingerprint": b"old-fingerprint-0000000000000001",
        "operation": "reset-guest-session-v1",
        "key": "retry-key-0001",
        "request_hash": "d4" * 32,
        "replacement_session_id": _uuid7(31),
        "replacement_token_hash": sha256_bytes(b"replacement-token"),
        "replacement_token_ciphertext": b"ciphertext",
        "encryption_key_id": "receipt-key-v1",
        "aad_version": "reset-replay-aad-v1",
        "cookie_profile_version": "public-demo-v1",
        "cookie_signing_key_id": "cookie-key-v1",
        "cookie_issued_at": NOW,
        "cookie_expires_at": NOW + timedelta(hours=24),
        "response_status": 202,
        "response_content_type": "application/json",
        "response_serializer_version": "canonical-json-v1",
        "response_body_bytes": receipt_body,
        "response_body_hash": sha256_bytes(receipt_body).hex(),
        "created_at": NOW,
        "expires_at": NOW + timedelta(minutes=10),
    }
    run_values = {
        "id": run_id,
        "workspace_id": workspace_id,
        "decision_id": decision_id,
        "decision_revision_id": revision_id,
        "status": RunStatus.QUEUED,
        "fixture_version": "walking-skeleton-v1",
        "input_snapshot": {"decisionRevision": 1},
        "input_snapshot_hash": "e5" * 32,
        "last_event_sequence": 0,
        "terminal_event_sequence": None,
        "error_code": None,
        "created_at": NOW,
        "started_at": None,
        "completed_at": None,
    }

    with migrated_engine.begin() as connection:
        connection.execute(
            workspaces.insert().values(
                id=workspace_id,
                kind=WorkspaceKind.LOCAL,
                status=WorkspaceStatus.ACTIVE,
                seed_parent_id=None,
                expires_at=None,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        connection.execute(
            decisions.insert().values(
                id=decision_id,
                workspace_id=workspace_id,
                current_revision=1,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        connection.execute(revisions.insert().values(**revision_values))

        stored_criteria = connection.scalar(
            select(revisions.c.criteria).where(revisions.c.id == revision_id)
        )
        assert stored_criteria is not None
        assert stored_criteria == criteria
        assert all(isinstance(item["enteredWeight"], str) for item in stored_criteria)
        assert sum(
            Decimal(item["normalizedWeight"]) for item in stored_criteria
        ) == Decimal("100.0000")

        _expect_database_rejection(
            connection,
            revisions.insert().values(**{**revision_values, "id": _uuid7(5)}),
        )
        _expect_database_rejection(
            connection,
            update(revisions)
            .where(revisions.c.id == revision_id)
            .values(question="Mutated question"),
        )
        _expect_database_rejection(
            connection,
            delete(revisions).where(revisions.c.id == revision_id),
        )
        assert (
            connection.scalar(
                select(revisions.c.question).where(revisions.c.id == revision_id)
            )
            == revision_values["question"]
        )

        connection.execute(
            decisions.insert().values(
                id=other_decision_id,
                workspace_id=workspace_id,
                current_revision=1,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        connection.execute(
            revisions.insert().values(
                **{
                    **revision_values,
                    "id": other_revision_id,
                    "decision_id": other_decision_id,
                    "question": "Other decision?",
                    "snapshot_hash": "d4" * 32,
                }
            )
        )
        _expect_database_rejection(
            connection,
            runs.insert().values(
                **{
                    **run_values,
                    "id": _uuid7(52),
                    "decision_revision_id": other_revision_id,
                }
            ),
        )

        connection.execute(runs.insert().values(**run_values))
        event_values = {
            "id": _uuid7(6),
            "workspace_id": workspace_id,
            "run_id": run_id,
            "sequence": 1,
            "kind": RunEventKind.RUN_QUEUED,
            "payload_schema_version": "1.0",
            "payload": {"runId": str(run_id)},
            "payload_hash": "f6" * 32,
            "created_at": NOW,
        }
        connection.execute(events.insert().values(**event_values))
        _expect_database_rejection(
            connection,
            events.insert().values(**{**event_values, "id": _uuid7(7)}),
        )
        _expect_database_rejection(
            connection,
            events.insert().values(**{**event_values, "id": _uuid7(8), "sequence": 0}),
        )

        idempotency_values = {
            "id": _uuid7(9),
            "workspace_id": workspace_id,
            "operation": "create-decision-v1",
            "key": "retry-key-0002",
            "request_hash": "17" * 32,
            "response_status": 201,
            "response_body": {"decisionId": str(decision_id)},
            "resource_id": decision_id,
            "expires_at": NOW + timedelta(hours=24),
            "created_at": NOW,
        }
        connection.execute(idempotency.insert().values(**idempotency_values))
        _expect_database_rejection(
            connection,
            idempotency.insert().values(**{**idempotency_values, "id": _uuid7(10)}),
        )

        connection.execute(receipts.insert().values(**receipt_values))
        _expect_database_rejection(
            connection,
            receipts.insert().values(**{**receipt_values, "id": _uuid7(32)}),
        )
        _expect_database_rejection(
            connection,
            receipts.insert().values(
                **{
                    **receipt_values,
                    "id": _uuid7(33),
                    "old_session_fingerprint": b"other-fingerprint-00000000000001",
                    "key": "retry-key-0003",
                    "expires_at": NOW + timedelta(minutes=9, seconds=59),
                }
            ),
        )

        common_job = {
            "workspace_id": workspace_id,
            "kind": "execute-run",
            "payload": {"runId": str(run_id)},
            "available_at": NOW,
            "attempt_count": 0,
            "created_at": NOW,
            "updated_at": NOW,
            "completed_at": None,
            "last_error_code": None,
        }
        _expect_database_rejection(
            connection,
            jobs.insert().values(
                id=_uuid7(40),
                status="leased",
                lease_owner=None,
                lease_expires_at=None,
                **common_job,
            ),
        )
        _expect_database_rejection(
            connection,
            jobs.insert().values(
                id=_uuid7(41),
                status="available",
                lease_owner="worker-1",
                lease_expires_at=NOW + timedelta(minutes=1),
                **common_job,
            ),
        )
        _expect_database_rejection(
            connection,
            jobs.insert().values(
                id=_uuid7(42),
                status="available",
                lease_owner=None,
                lease_expires_at=None,
                **{**common_job, "attempt_count": -1},
            ),
        )


async def test_repositories_enforce_scope_and_transaction_commit_rollback(
    migrated_engine: Engine,
    postgres_url: str,
) -> None:
    del migrated_engine
    async_engine = create_database_engine(postgres_url)
    factory = create_session_factory(async_engine)
    workspace_a = _uuid7(100)
    workspace_b = _uuid7(101)
    decision_a = _uuid7(110)
    decision_b = _uuid7(111)
    revision_a = _uuid7(120)
    revision_b = _uuid7(121)
    run_a = _uuid7(130)
    run_b = _uuid7(131)

    try:
        async with transaction_session(factory) as session:
            session.add_all([_workspace(workspace_a), _workspace(workspace_b)])
            await session.flush()
            session.add_all(
                [
                    Decision(
                        id=decision_a,
                        workspace_id=workspace_a,
                        current_revision=1,
                        created_at=NOW,
                        updated_at=NOW,
                    ),
                    Decision(
                        id=decision_b,
                        workspace_id=workspace_b,
                        current_revision=1,
                        created_at=NOW,
                        updated_at=NOW,
                    ),
                ]
            )
            await session.flush()
            session.add_all(
                [
                    _revision(
                        workspace_id=workspace_a,
                        decision_id=decision_a,
                        revision_id=revision_a,
                    ),
                    _revision(
                        workspace_id=workspace_b,
                        decision_id=decision_b,
                        revision_id=revision_b,
                    ),
                ]
            )
            await session.flush()
            session.add_all(
                [
                    _run_record(
                        workspace_id=workspace_a,
                        decision_id=decision_a,
                        revision_id=revision_a,
                        run_id=run_a,
                    ),
                    _run_record(
                        workspace_id=workspace_b,
                        decision_id=decision_b,
                        revision_id=revision_b,
                        run_id=run_b,
                    ),
                ]
            )

        async with transaction_session(factory) as session:
            decisions_repo = DecisionRepository(session)
            runs_repo = RunRepository(session)
            assert (
                await decisions_repo.get(
                    workspace_id=workspace_a,
                    decision_id=decision_a,
                )
                is not None
            )
            assert (
                await decisions_repo.get(
                    workspace_id=workspace_a,
                    decision_id=decision_b,
                )
                is None
            )
            assert (
                await runs_repo.get(workspace_id=workspace_a, run_id=run_a) is not None
            )
            assert await runs_repo.get(workspace_id=workspace_a, run_id=run_b) is None

            with pytest.raises(LookupError):
                await decisions_repo.append_revision(
                    workspace_id=workspace_a,
                    decision_id=decision_b,
                    revision=_revision(
                        workspace_id=workspace_b,
                        decision_id=decision_b,
                        revision_id=_uuid7(122),
                        revision=2,
                    ),
                )
            with pytest.raises(LookupError):
                await runs_repo.append_event(
                    workspace_id=workspace_a,
                    run_id=run_b,
                    event=RunEvent(
                        id=_uuid7(132),
                        workspace_id=workspace_b,
                        run_id=run_b,
                        sequence=1,
                        kind=RunEventKind.RUN_QUEUED,
                        payload_schema_version="1.0",
                        payload={"runId": str(run_b)},
                        payload_hash="19" * 32,
                        created_at=NOW,
                    ),
                )

        class RollbackProbe(Exception):
            pass

        rolled_back_revision_id = _uuid7(123)
        with pytest.raises(RollbackProbe):
            async with transaction_session(factory) as session:
                await DecisionRepository(session).append_revision(
                    workspace_id=workspace_a,
                    decision_id=decision_a,
                    revision=_revision(
                        workspace_id=workspace_a,
                        decision_id=decision_a,
                        revision_id=rolled_back_revision_id,
                        revision=2,
                    ),
                )
                raise RollbackProbe

        async with transaction_session(factory) as session:
            assert (
                await session.scalar(
                    select(DecisionRevision.id).where(
                        DecisionRevision.id == rolled_back_revision_id
                    )
                )
                is None
            )
    finally:
        await async_engine.dispose()


async def test_reset_receipt_survives_session_deletion_and_purges_only_expired(
    migrated_engine: Engine,
    postgres_url: str,
) -> None:
    del migrated_engine
    async_engine = create_database_engine(postgres_url)
    factory = create_session_factory(async_engine)
    seed_id = _uuid7(200)
    guest_id = _uuid7(201)
    session_id = _uuid7(202)
    live_fingerprint = sha256_bytes(b"live-old-session")
    expired_fingerprint = sha256_bytes(b"expired-old-session")
    live_body = b'{"status":"reset-queued","note":"\xe2\x98\x83"}'
    expired_body = b'{"status":"expired"}'
    live_receipt_id = _uuid7(210)
    expired_receipt_id = _uuid7(211)

    try:
        async with transaction_session(factory) as session:
            session.add(
                Workspace(
                    id=seed_id,
                    kind=WorkspaceKind.SEED,
                    status=WorkspaceStatus.ACTIVE,
                    seed_parent_id=None,
                    expires_at=None,
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
            await session.flush()
            session.add(
                Workspace(
                    id=guest_id,
                    kind=WorkspaceKind.GUEST,
                    status=WorkspaceStatus.ACTIVE,
                    seed_parent_id=seed_id,
                    expires_at=NOW + timedelta(hours=24),
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
            await session.flush()
            session.add(
                GuestSession(
                    id=session_id,
                    workspace_id=guest_id,
                    token_hash=sha256_bytes(b"guest-token"),
                    expires_at=NOW + timedelta(hours=24),
                    revoked_at=None,
                    created_at=NOW,
                )
            )
            session.add_all(
                [
                    _receipt(
                        receipt_id=live_receipt_id,
                        fingerprint=live_fingerprint,
                        key="retry-key-live",
                        response_body=live_body,
                        created_at=NOW,
                    ),
                    _receipt(
                        receipt_id=expired_receipt_id,
                        fingerprint=expired_fingerprint,
                        key="retry-key-expired",
                        response_body=expired_body,
                        created_at=NOW - timedelta(minutes=11),
                    ),
                ]
            )

        async with transaction_session(factory) as session:
            await session.execute(delete(Workspace).where(Workspace.id == guest_id))

        async with transaction_session(factory) as session:
            assert (
                await session.scalar(
                    select(GuestSession.id).where(GuestSession.id == session_id)
                )
                is None
            )
            repository = ResetReplayRepository(session)
            live_receipt = await repository.get(
                old_session_fingerprint=live_fingerprint,
                operation="reset-guest-session-v1",
                key="retry-key-live",
                now=NOW,
            )
            assert live_receipt is not None
            assert live_receipt.id == live_receipt_id
            assert live_receipt.response_body_bytes == live_body
            assert live_receipt.response_body_hash == sha256_bytes(live_body).hex()
            assert live_receipt.expires_at - live_receipt.created_at == timedelta(
                minutes=10
            )
            assert (
                await repository.get(
                    old_session_fingerprint=expired_fingerprint,
                    operation="reset-guest-session-v1",
                    key="retry-key-expired",
                    now=NOW,
                )
                is None
            )
            assert await repository.purge_expired(now=NOW) == 1

        async with transaction_session(factory) as session:
            assert await session.get(ResetReplayReceipt, expired_receipt_id) is None
            surviving = await session.get(ResetReplayReceipt, live_receipt_id)
            assert surviving is not None
            assert surviving.response_body_bytes == live_body
    finally:
        await async_engine.dispose()
