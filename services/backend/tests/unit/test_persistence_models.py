from __future__ import annotations

import inspect
import json
import uuid
from dataclasses import fields, replace
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.exceptions import InvalidTag
from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects import postgresql

from ai_cto_cockpit.persistence.models import (
    Base,
    DecisionRevision,
    DeletionCompletion,
    JobStatus,
    RunEventKind,
    RunStatus,
    WorkspaceKind,
    new_uuid7,
)
from ai_cto_cockpit.persistence.repositories import (
    DecisionRepository,
    JobRepository,
    ResetReplayAad,
    ResetReplayIntegrityError,
    ResetReplayRepository,
    RunRepository,
    assert_contiguous_event_sequence,
    assert_run_transition,
    canonical_reset_replay_aad,
    decrypt_replacement_token,
    encrypt_replacement_token,
    hash_reset_replay_idempotency_key,
    sha256_bytes,
    validate_workspace_shape,
)

EXPECTED_TABLE_COLUMNS = {
    "workspaces": {
        "id",
        "kind",
        "status",
        "seed_parent_id",
        "expires_at",
        "created_at",
        "updated_at",
    },
    "guest_sessions": {
        "id",
        "workspace_id",
        "token_hash",
        "expires_at",
        "revoked_at",
        "created_at",
    },
    "decisions": {
        "id",
        "workspace_id",
        "current_revision",
        "created_at",
        "updated_at",
    },
    "decision_revisions": {
        "id",
        "workspace_id",
        "decision_id",
        "revision",
        "frame_schema_version",
        "question",
        "context",
        "options",
        "criteria",
        "constraints",
        "snapshot_hash",
        "created_at",
    },
    "runs": {
        "id",
        "workspace_id",
        "decision_id",
        "decision_revision_id",
        "status",
        "fixture_version",
        "input_snapshot",
        "input_snapshot_hash",
        "last_event_sequence",
        "terminal_event_sequence",
        "error_code",
        "created_at",
        "started_at",
        "completed_at",
    },
    "run_events": {
        "id",
        "workspace_id",
        "run_id",
        "sequence",
        "kind",
        "payload_schema_version",
        "payload",
        "payload_hash",
        "created_at",
    },
    "jobs": {
        "id",
        "workspace_id",
        "kind",
        "payload",
        "status",
        "available_at",
        "lease_owner",
        "lease_expires_at",
        "attempt_count",
        "last_error_code",
        "created_at",
        "updated_at",
        "completed_at",
    },
    "deletion_completions": {
        "id",
        "workspace_id",
        "operation",
        "job_id",
        "completed_at",
    },
    "idempotency_records": {
        "id",
        "workspace_id",
        "operation",
        "key",
        "request_hash",
        "response_status",
        "response_body",
        "resource_id",
        "expires_at",
        "created_at",
    },
    "reset_replay_receipts": {
        "id",
        "old_session_fingerprint",
        "operation",
        "key_hash",
        "request_hash",
        "replacement_session_id",
        "replacement_token_hash",
        "replacement_token_ciphertext",
        "encryption_key_id",
        "aad_version",
        "cookie_profile_version",
        "cookie_signing_key_id",
        "cookie_issued_at",
        "cookie_expires_at",
        "response_status",
        "response_content_type",
        "response_serializer_version",
        "response_body_bytes",
        "response_body_hash",
        "expires_at",
        "created_at",
    },
}

EXPECTED_AAD_FIELDS = {
    "id",
    "old_session_fingerprint",
    "operation",
    "key_hash",
    "request_hash",
    "replacement_session_id",
    "replacement_token_hash",
    "encryption_key_id",
    "aad_version",
    "cookie_profile_version",
    "cookie_signing_key_id",
    "cookie_issued_at",
    "cookie_expires_at",
    "response_status",
    "response_content_type",
    "response_serializer_version",
    "response_body_hash",
    "created_at",
    "expires_at",
}

ForeignKeySignature = tuple[tuple[str, ...], str, str | None]

EXPECTED_FOREIGN_KEYS: dict[str, set[ForeignKeySignature]] = {
    "workspaces": {(("seed_parent_id",), "workspaces.id", "RESTRICT")},
    "guest_sessions": {(("workspace_id",), "workspaces.id", "CASCADE")},
    "decisions": {(("workspace_id",), "workspaces.id", "CASCADE")},
    "decision_revisions": {
        (
            ("workspace_id", "decision_id"),
            "decisions.workspace_id,decisions.id",
            "CASCADE",
        ),
    },
    "runs": {
        (
            ("workspace_id", "decision_id"),
            "decisions.workspace_id,decisions.id",
            "CASCADE",
        ),
        (
            ("workspace_id", "decision_id", "decision_revision_id"),
            (
                "decision_revisions.workspace_id,"
                "decision_revisions.decision_id,decision_revisions.id"
            ),
            "CASCADE",
        ),
    },
    "run_events": {
        (
            ("workspace_id", "run_id"),
            "runs.workspace_id,runs.id",
            "CASCADE",
        ),
    },
    "jobs": {(("workspace_id",), "workspaces.id", "CASCADE")},
    "deletion_completions": set(),
    "idempotency_records": {(("workspace_id",), "workspaces.id", "CASCADE")},
    "reset_replay_receipts": set(),
}

EXPECTED_UNIQUE_COLUMNS = {
    "guest_sessions": {("workspace_id",), ("token_hash",)},
    "decisions": {("workspace_id", "id")},
    "decision_revisions": {
        ("decision_id", "revision"),
        ("workspace_id", "decision_id", "id"),
    },
    "runs": {("workspace_id", "id")},
    "run_events": {("run_id", "sequence")},
    "deletion_completions": {
        ("workspace_id", "operation"),
        ("job_id",),
    },
    "idempotency_records": {("workspace_id", "operation", "key")},
    "reset_replay_receipts": {
        ("old_session_fingerprint", "operation", "key_hash"),
    },
}


def _constraint_names(table_name: str) -> set[str]:
    return {
        str(constraint.name)
        for constraint in Base.metadata.tables[table_name].constraints
        if constraint.name is not None
    }


def _foreign_key_signature(
    table_name: str,
) -> set[tuple[tuple[str, ...], str, str | None]]:
    table = Base.metadata.tables[table_name]
    return {
        (
            tuple(str(element.parent.name) for element in constraint.elements),
            ",".join(element.target_fullname for element in constraint.elements),
            constraint.ondelete,
        )
        for constraint in table.foreign_key_constraints
    }


def _unique_column_signature(table_name: str) -> set[tuple[str, ...]]:
    table = Base.metadata.tables[table_name]
    return {
        tuple(str(column.name) for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def _aad() -> ResetReplayAad:
    return ResetReplayAad(
        id=uuid.UUID("01890f9a-7bcd-7abc-8def-0123456789ab"),
        old_session_fingerprint=bytes.fromhex("11" * 32),
        operation="reset-guest-session-v1",
        key_hash=bytes.fromhex("55" * 32),
        request_hash="22" * 32,
        replacement_session_id=uuid.UUID("01890f9a-7bcd-7abc-8def-0123456789ac"),
        replacement_token_hash=bytes.fromhex("33" * 32),
        encryption_key_id="receipt-key-v1",
        aad_version="reset-replay-aad-v1",
        cookie_profile_version="public-demo-v1",
        cookie_signing_key_id="cookie-key-v1",
        cookie_issued_at=datetime(2026, 8, 1, 12, 30, 0, 123456, tzinfo=UTC),
        cookie_expires_at=datetime(2026, 8, 2, 12, 30, 0, 123456, tzinfo=UTC),
        response_status=202,
        response_content_type="application/json",
        response_serializer_version="canonical-json-v1",
        response_body_hash="44" * 32,
        created_at=datetime(2026, 8, 1, 12, 30, 0, 123456, tzinfo=UTC),
        expires_at=datetime(2026, 8, 1, 12, 40, 0, 123456, tzinfo=UTC),
    )


def test_metadata_declares_every_table_and_column() -> None:
    assert set(Base.metadata.tables) == set(EXPECTED_TABLE_COLUMNS)
    for table_name, expected_columns in EXPECTED_TABLE_COLUMNS.items():
        assert set(Base.metadata.tables[table_name].columns.keys()) == expected_columns


def test_every_foreign_key_has_the_required_scope_and_delete_behavior() -> None:
    assert set(Base.metadata.tables) == set(EXPECTED_FOREIGN_KEYS)
    for table_name, expected in EXPECTED_FOREIGN_KEYS.items():
        assert _foreign_key_signature(table_name) == expected


def test_uniqueness_and_scoped_indexes_encode_aggregate_invariants() -> None:
    for table_name, expected in EXPECTED_UNIQUE_COLUMNS.items():
        assert _unique_column_signature(table_name) == expected

    expected_index_columns = {
        "decisions": {("workspace_id",)},
        "decision_revisions": {("workspace_id", "decision_id")},
        "runs": {("workspace_id",)},
        "run_events": {("workspace_id", "run_id", "sequence")},
        "jobs": {("workspace_id",)},
        "idempotency_records": {("workspace_id",)},
    }
    for table_name, expected in expected_index_columns.items():
        actual = {
            tuple(column.name for column in index.columns)
            for index in Base.metadata.tables[table_name].indexes
        }
        assert expected <= actual

    all_constraint_names = {
        name
        for table_name in Base.metadata.tables
        for name in _constraint_names(table_name)
    }
    assert {
        "ck_workspaces_shape",
        "ck_jobs_attempt_count_non_negative",
        "ck_jobs_lease_shape",
        "ck_reset_replay_receipts_expiry",
    } <= all_constraint_names


def test_reset_receipt_is_non_cascading_and_has_no_workspace_scope() -> None:
    table = Base.metadata.tables["reset_replay_receipts"]
    assert "workspace_id" not in table.columns
    assert "key" not in table.columns
    assert "key_hash" in table.columns
    assert "ck_reset_replay_receipts_key_hash_length" in _constraint_names(
        "reset_replay_receipts"
    )
    assert not table.foreign_key_constraints


def test_deletion_completion_is_non_sensitive_and_survives_parent_deletion() -> None:
    table = Base.metadata.tables["deletion_completions"]
    column_names = {str(column.name) for column in table.columns}

    assert not table.foreign_key_constraints
    assert column_names == EXPECTED_TABLE_COLUMNS["deletion_completions"]
    assert (
        not {
            "payload",
            "request_body",
            "response_body",
            "source_data",
            "decision_data",
        }
        & column_names
    )
    assert DeletionCompletion.operation.default.arg == "delete-guest-workspace-v1"


def test_reset_replay_idempotency_key_is_domain_separated_before_storage() -> None:
    raw_key = "caller-authored-retry-key"
    digest = hash_reset_replay_idempotency_key(raw_key)

    assert len(digest) == 32
    assert digest.hex() == (
        "671a13e75f4ec916a1f5ddfb85040685b4157d1777a995c20c342639987efaed"
    )
    assert raw_key.encode() not in digest
    assert digest != sha256_bytes(raw_key.encode())
    assert digest == hash_reset_replay_idempotency_key(raw_key)
    assert digest != hash_reset_replay_idempotency_key(f"{raw_key}-other")


@pytest.mark.parametrize(
    ("raw_key", "valid"),
    [
        ("a" * 7, False),
        ("a" * 8, True),
        ("a" * 128, True),
        ("a" * 129, False),
    ],
)
def test_reset_replay_idempotency_key_length_is_bounded(
    raw_key: str, valid: bool
) -> None:
    if valid:
        assert len(hash_reset_replay_idempotency_key(raw_key)) == 32
    else:
        with pytest.raises(ValueError):
            hash_reset_replay_idempotency_key(raw_key)


def test_server_ids_are_canonical_uuid7() -> None:
    generated = new_uuid7()
    assert generated.version == 7
    assert str(generated) == str(generated).lower()


@pytest.mark.parametrize(
    ("kind", "seed_parent_id", "expires_delta", "valid"),
    [
        (WorkspaceKind.SEED, None, None, True),
        (WorkspaceKind.LOCAL, None, None, True),
        (WorkspaceKind.GUEST, uuid.uuid4(), timedelta(hours=24), True),
        (WorkspaceKind.GUEST, None, timedelta(hours=24), False),
        (WorkspaceKind.GUEST, uuid.uuid4(), timedelta(hours=23), False),
        (WorkspaceKind.SEED, uuid.uuid4(), None, False),
        (WorkspaceKind.LOCAL, None, timedelta(hours=24), False),
    ],
)
def test_workspace_shape_guard(
    kind: WorkspaceKind,
    seed_parent_id: uuid.UUID | None,
    expires_delta: timedelta | None,
    valid: bool,
) -> None:
    created_at = datetime(2026, 8, 1, tzinfo=UTC)
    expires_at = created_at + expires_delta if expires_delta is not None else None
    if valid:
        validate_workspace_shape(kind, seed_parent_id, created_at, expires_at)
    else:
        with pytest.raises(ValueError):
            validate_workspace_shape(kind, seed_parent_id, created_at, expires_at)


def test_lossless_weight_strings_remain_json_strings() -> None:
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
    revision = DecisionRevision(criteria=criteria)
    assert revision.criteria == criteria
    assert all(isinstance(item["enteredWeight"], str) for item in revision.criteria)
    assert all(isinstance(item["normalizedWeight"], str) for item in revision.criteria)


def test_run_transition_matrix_is_closed_and_terminal_states_are_final() -> None:
    allowed = {
        (RunStatus.QUEUED, RunStatus.RUNNING),
        (RunStatus.QUEUED, RunStatus.FAILED),
        (RunStatus.RUNNING, RunStatus.COMPLETED),
        (RunStatus.RUNNING, RunStatus.FAILED),
    }
    for current in RunStatus:
        for target in RunStatus:
            if (current, target) in allowed:
                assert_run_transition(current, target)
            else:
                with pytest.raises(ValueError):
                    assert_run_transition(current, target)


def test_event_sequences_are_positive_and_contiguous() -> None:
    assert_contiguous_event_sequence(last_sequence=0, next_sequence=1)
    assert_contiguous_event_sequence(last_sequence=41, next_sequence=42)
    with pytest.raises(ValueError):
        assert_contiguous_event_sequence(last_sequence=1, next_sequence=1)
    with pytest.raises(ValueError):
        assert_contiguous_event_sequence(last_sequence=1, next_sequence=3)


def test_job_claim_is_ordered_skip_locked_and_attempts_are_non_negative() -> None:
    now = datetime(2026, 8, 1, tzinfo=UTC)
    statement = JobRepository.claim_statement(now=now).compile(
        dialect=postgresql.dialect()
    )
    sql = " ".join(str(statement).upper().split())
    assert "WHERE JOBS.AVAILABLE_AT <=" in sql
    assert "JOBS.STATUS =" in sql
    assert "JOBS.LEASE_EXPIRES_AT <=" in sql
    assert "ORDER BY JOBS.AVAILABLE_AT, JOBS.CREATED_AT, JOBS.ID" in sql
    assert "LIMIT" in sql
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert now in statement.params.values()
    assert JobStatus.AVAILABLE in statement.params.values()
    assert JobStatus.LEASED in statement.params.values()
    assert 1 in statement.params.values()
    assert "ck_jobs_attempt_count_non_negative" in _constraint_names("jobs")


def test_scoped_repository_methods_require_trusted_workspace_id() -> None:
    for method in (
        DecisionRepository.get,
        DecisionRepository.append_revision,
        RunRepository.get,
        RunRepository.append_event,
    ):
        assert "workspace_id" in inspect.signature(method).parameters
    assert "workspace_id" not in inspect.signature(ResetReplayRepository.get).parameters
    assert (
        "old_session_fingerprint"
        in inspect.signature(ResetReplayRepository.get).parameters
    )
    assert not hasattr(DecisionRepository, "update_revision")
    assert not hasattr(DecisionRepository, "delete_revision")


def test_canonical_aad_has_every_exact_bound_field() -> None:
    aad = _aad()
    encoded = canonical_reset_replay_aad(aad)
    decoded = json.loads(encoded)
    assert {field.name for field in fields(ResetReplayAad)} == EXPECTED_AAD_FIELDS
    assert set(decoded) == EXPECTED_AAD_FIELDS
    assert decoded["old_session_fingerprint"] == "11" * 32
    assert decoded["key_hash"] == "55" * 32
    assert decoded["replacement_token_hash"] == "33" * 32
    assert decoded["cookie_issued_at"] == "2026-08-01T12:30:00.123456Z"
    assert decoded["expires_at"] == "2026-08-01T12:40:00.123456Z"
    assert (
        encoded
        == json.dumps(
            decoded,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    )


def test_aes_256_gcm_round_trip_uses_a_fresh_96_bit_nonce() -> None:
    token = b"replacement-token-material"
    key = bytes.fromhex("55" * 32)
    aad = replace(_aad(), replacement_token_hash=sha256_bytes(token))
    body = b'{"status":"reset-queued"}'
    aad = replace(aad, response_body_hash=sha256_bytes(body).hex())

    first = encrypt_replacement_token(token, key=key, aad=aad)
    second = encrypt_replacement_token(token, key=key, aad=aad)
    assert first != second
    assert first[:12] != second[:12]
    assert len(first) == 12 + len(token) + 16
    assert (
        decrypt_replacement_token(
            first,
            key=key,
            aad=aad,
            expected_token_hash=sha256_bytes(token),
            response_body_bytes=body,
        )
        == token
    )


@pytest.mark.parametrize("field_name", sorted(EXPECTED_AAD_FIELDS))
def test_ciphertext_is_bound_to_every_aad_field(field_name: str) -> None:
    token = b"replacement-token-material"
    key = bytes.fromhex("66" * 32)
    body = b"{}"
    aad = replace(
        _aad(),
        replacement_token_hash=sha256_bytes(token),
        response_body_hash=sha256_bytes(body).hex(),
    )
    ciphertext = encrypt_replacement_token(token, key=key, aad=aad)
    current = getattr(aad, field_name)
    if isinstance(current, bytes):
        changed = b"\xff" + current[1:]
    elif isinstance(current, uuid.UUID):
        changed = uuid.UUID("01890f9a-7bcd-7abc-8def-0123456789ad")
    elif isinstance(current, datetime):
        changed = current + timedelta(microseconds=1)
    elif isinstance(current, int):
        changed = current + 1
    else:
        changed = f"{current}-changed"
    with pytest.raises(InvalidTag):
        decrypt_replacement_token(
            ciphertext,
            key=key,
            aad=replace(aad, **{field_name: changed}),
            expected_token_hash=sha256_bytes(token),
            response_body_bytes=body,
        )


def test_reset_replay_integrity_failures_are_closed() -> None:
    token = b"replacement-token-material"
    key = bytes.fromhex("77" * 32)
    body = b"{}"
    aad = replace(
        _aad(),
        replacement_token_hash=sha256_bytes(token),
        response_body_hash=sha256_bytes(body).hex(),
    )
    ciphertext = encrypt_replacement_token(token, key=key, aad=aad)

    with pytest.raises((InvalidTag, ValueError)):
        decrypt_replacement_token(
            ciphertext,
            key=bytes.fromhex("78" * 32),
            aad=aad,
            expected_token_hash=sha256_bytes(token),
            response_body_bytes=body,
        )
    tampered = bytearray(ciphertext)
    tampered[-1] ^= 1
    with pytest.raises(InvalidTag):
        decrypt_replacement_token(
            bytes(tampered),
            key=key,
            aad=aad,
            expected_token_hash=sha256_bytes(token),
            response_body_bytes=body,
        )
    with pytest.raises(ResetReplayIntegrityError):
        decrypt_replacement_token(
            ciphertext,
            key=key,
            aad=aad,
            expected_token_hash=b"\x00" * 32,
            response_body_bytes=body,
        )
    with pytest.raises(ResetReplayIntegrityError):
        decrypt_replacement_token(
            ciphertext,
            key=key,
            aad=aad,
            expected_token_hash=sha256_bytes(token),
            response_body_bytes=b'{"changed":true}',
        )

    receipt_mismatch_aad = replace(aad, replacement_token_hash=b"\x00" * 32)
    receipt_mismatch_ciphertext = encrypt_replacement_token(
        token,
        key=key,
        aad=receipt_mismatch_aad,
    )
    with pytest.raises(ResetReplayIntegrityError):
        decrypt_replacement_token(
            receipt_mismatch_ciphertext,
            key=key,
            aad=receipt_mismatch_aad,
            expected_token_hash=sha256_bytes(token),
            response_body_bytes=body,
        )
    with pytest.raises(ValueError):
        encrypt_replacement_token(token, key=b"too-short", aad=aad)


def test_run_event_enum_keeps_ui_payload_closed() -> None:
    assert {kind.value for kind in RunEventKind} == {
        "run.queued",
        "run.started",
        "ui.envelope",
        "run.completed",
        "run.failed",
    }
