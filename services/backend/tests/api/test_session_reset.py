from __future__ import annotations

import asyncio
import copy
import uuid
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from conftest import AsgiResponse, asgi_request
from fastapi import FastAPI
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_cto_cockpit.api.dependencies.context import (
    WorkspaceContextUnauthorized,
    resolve_workspace_context,
)
from ai_cto_cockpit.api.routes.config import (
    ResetReplayFailure,
    canonical_reset_request_hash,
    replay_reset_receipt,
)
from ai_cto_cockpit.main import create_app
from ai_cto_cockpit.persistence.models import (
    GuestSession,
    Job,
    JobKind,
    JobStatus,
    ResetReplayReceipt,
    Workspace,
    WorkspaceStatus,
)
from ai_cto_cockpit.security.guest_session import GuestSessionCodec, SessionKeyRing
from ai_cto_cockpit.settings import Settings

NOW = datetime(2026, 8, 14, 12, 0, 0, 123456, tzinfo=UTC)
SIGNING_KEY = "t010-reset-signing-key-with-more-than-thirty-two-bytes"
ROTATED_SIGNING_KEY = "t010-rotated-signing-key-with-more-than-thirty-two-bytes"
SEED_ID = uuid.UUID("0198b0f0-0000-7000-8000-000000000001")
LOCAL_ID = uuid.UUID("0198b0f0-0000-7000-8000-000000000002")
IDEMPOTENCY_KEY = "reset-request-key-v1"


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


def _rotated_settings(database_url: str) -> Settings:
    return Settings(
        app_mode="public-demo",
        database_url=database_url,
        qdrant_url="http://127.0.0.1:6333",
        session_signing_key=ROTATED_SIGNING_KEY,
        session_signing_key_id="cookie-key-v2",
        session_retained_signing_keys={"cookie-key-v1": SIGNING_KEY},
        session_retained_cookie_secure={"cookie-key-v1": False},
        cookie_secure=True,
        local_compose=True,
        seed_workspace_id=SEED_ID,
        local_workspace_id=LOCAL_ID,
    )


def _cookie_value(response: AsgiResponse) -> str:
    set_cookie = response.header("set-cookie")
    assert set_cookie is not None
    name_value = set_cookie.split(";", 1)[0]
    name, value = name_value.split("=", 1)
    assert name == "ai_cto_guest"
    return value


async def _new_guest_cookie(app: FastAPI) -> str:
    response = await asgi_request(app, method="GET", path="/api/v1/config")
    assert response.status == 200
    return _cookie_value(response)


async def _reset(
    app: FastAPI,
    cookie: str,
    *,
    key: str = IDEMPOTENCY_KEY,
    query: str = "",
) -> AsgiResponse:
    return await asgi_request(
        app,
        method="POST",
        path="/api/v1/session/reset",
        query=query,
        headers=(
            ("Cookie", f"ai_cto_guest={cookie}"),
            ("Idempotency-Key", key),
        ),
    )


async def _row_counts(
    factory: async_sessionmaker[AsyncSession],
) -> tuple[int, int, int, int]:
    async with factory() as session:
        workspaces = int(await session.scalar(select(func.count(Workspace.id))) or 0)
        sessions = int(await session.scalar(select(func.count(GuestSession.id))) or 0)
        jobs = int(await session.scalar(select(func.count(Job.id))) or 0)
        receipts = int(
            await session.scalar(select(func.count(ResetReplayReceipt.id))) or 0
        )
    return workspaces, sessions, jobs, receipts


@pytest.mark.asyncio
async def test_reset_is_atomic_and_lost_response_replays_exact_bytes_after_restart(
    t010_postgres_url: str,
    t010_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    settings = _settings(t010_postgres_url)
    app = create_app(
        settings=settings,
        session_factory=t010_session_factory,
        clock=lambda: NOW,
    )
    old_cookie = await _new_guest_cookie(app)
    original = await _reset(app, old_cookie)

    assert original.status == 202
    assert original.header("content-type") == "application/json"
    assert original.json() == {
        "guestExpiresAt": "2026-08-15T12:00:00.123456Z",
        "resetAccepted": True,
    }
    original_set_cookie = original.header("set-cookie")
    assert original_set_cookie is not None
    assert await _row_counts(t010_session_factory) == (3, 2, 1, 1)

    async with t010_session_factory() as session:
        old_session = await session.scalar(
            select(GuestSession).where(GuestSession.revoked_at.is_not(None))
        )
        assert old_session is not None
        old_workspace = await session.get(Workspace, old_session.workspace_id)
        job = await session.scalar(select(Job))
        receipt = await session.scalar(select(ResetReplayReceipt))
        assert old_workspace is not None and job is not None and receipt is not None
        assert old_session.revoked_at == NOW
        assert old_workspace.status == WorkspaceStatus.DELETING
        assert job.kind == JobKind.DELETE_WORKSPACE
        assert job.status == JobStatus.AVAILABLE
        assert job.workspace_id == old_workspace.id
        assert job.payload == {"workspaceId": str(old_workspace.id)}
        assert receipt.expires_at == receipt.created_at + timedelta(minutes=10)

    restarted = create_app(
        settings=_rotated_settings(t010_postgres_url),
        session_factory=t010_session_factory,
        clock=lambda: NOW + timedelta(minutes=1),
        reset_response_serializer=lambda _response: b'{"serializer":"changed"}',
    )
    replay = await _reset(restarted, old_cookie)
    assert replay.status == original.status
    assert replay.body == original.body
    assert replay.header("content-type") == original.header("content-type")
    assert replay.header("set-cookie") == original_set_cookie
    assert await _row_counts(t010_session_factory) == (3, 2, 1, 1)


@pytest.mark.asyncio
async def test_reset_conflict_and_revoked_cookie_error_matrix(
    t010_postgres_url: str,
    t010_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    settings = _settings(t010_postgres_url)
    app = create_app(
        settings=settings,
        session_factory=t010_session_factory,
        clock=lambda: NOW,
    )
    old_cookie = await _new_guest_cookie(app)
    assert (await _reset(app, old_cookie)).status == 202

    mismatch = await _reset(app, old_cookie, query="shape=changed")
    assert mismatch.status == 409
    assert mismatch.json()["code"] == "idempotency_conflict"
    different_key = await _reset(app, old_cookie, key="another-reset-key")
    assert different_key.status == 401
    assert different_key.json()["code"] == "session_unauthorized"

    codec = GuestSessionCodec(
        SessionKeyRing.from_settings(settings),
        cookie_secure=settings.cookie_secure,
        clock=lambda: NOW,
    )
    with pytest.raises(WorkspaceContextUnauthorized):
        await resolve_workspace_context(
            cookie_value=old_cookie,
            settings=settings,
            session_factory=t010_session_factory,
            codec=codec,
            now=NOW,
        )


@pytest.mark.asyncio
async def test_reset_rejects_non_visible_ascii_idempotency_key_before_mutation(
    t010_postgres_url: str,
    t010_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    app = create_app(
        settings=_settings(t010_postgres_url),
        session_factory=t010_session_factory,
        clock=lambda: NOW,
    )
    cookie = await _new_guest_cookie(app)

    response = await _reset(app, cookie, key="contains space")

    assert response.status == 422
    payload = response.json()
    assert payload == {
        "code": "request_validation_failed",
        "message": "Request validation failed.",
        "correlationId": payload["correlationId"],
        "fields": [
            {
                "path": "header.Idempotency-Key",
                "code": "invalid_format",
            }
        ],
    }
    assert uuid.UUID(cast(str, payload["correlationId"])).version == 7
    assert await _row_counts(t010_session_factory) == (2, 1, 0, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("receipt_state", ["missing", "expired"])
async def test_revoked_cookie_without_live_receipt_is_unauthorized(
    t010_postgres_url: str,
    t010_session_factory: async_sessionmaker[AsyncSession],
    receipt_state: str,
) -> None:
    app = create_app(
        settings=_settings(t010_postgres_url),
        session_factory=t010_session_factory,
        clock=lambda: NOW,
    )
    old_cookie = await _new_guest_cookie(app)
    assert (await _reset(app, old_cookie)).status == 202
    async with t010_session_factory.begin() as session:
        receipt = await session.scalar(select(ResetReplayReceipt))
        assert receipt is not None
        if receipt_state == "missing":
            await session.execute(delete(ResetReplayReceipt))
        else:
            receipt.created_at = NOW - timedelta(minutes=11)
            receipt.expires_at = NOW - timedelta(minutes=1)

    response = await _reset(app, old_cookie)
    assert response.status == 401
    assert response.header("set-cookie") is None
    async with t010_session_factory() as session:
        assert await session.scalar(select(func.count(ResetReplayReceipt.id))) == 0


def test_reset_request_hash_excludes_cookie_and_idempotency_header() -> None:
    expected = canonical_reset_request_hash(
        method="POST",
        path="/api/v1/session/reset",
        query_string="b=2&a=1",
    )
    reordered = canonical_reset_request_hash(
        method="POST",
        path="/api/v1/session/reset",
        query_string="a=1&b=2",
    )
    changed = canonical_reset_request_hash(
        method="POST",
        path="/api/v1/session/reset",
        query_string="a=1&b=3",
    )
    assert expected == reordered
    assert expected != changed
    assert len(expected) == 64


@pytest.mark.asyncio
async def test_reset_replay_integrity_failures_never_emit_a_cookie(
    t010_postgres_url: str,
    t010_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    settings = _settings(t010_postgres_url)
    app = create_app(
        settings=settings,
        session_factory=t010_session_factory,
        clock=lambda: NOW,
    )
    old_cookie = await _new_guest_cookie(app)
    assert (await _reset(app, old_cookie)).status == 202
    codec = GuestSessionCodec(
        SessionKeyRing.from_settings(settings),
        cookie_secure=settings.cookie_secure,
        clock=lambda: NOW,
    )

    async with t010_session_factory() as session:
        receipt = await session.scalar(select(ResetReplayReceipt))
        assert receipt is not None
        replacement = await session.get(GuestSession, receipt.replacement_session_id)
        assert replacement is not None
        original_ciphertext = receipt.replacement_token_ciphertext
        receipt.replacement_token_ciphertext = original_ciphertext[:-1] + bytes(
            [original_ciphertext[-1] ^ 1]
        )
        with pytest.raises(ResetReplayFailure):
            replay_reset_receipt(receipt, replacement, codec)
        receipt.replacement_token_ciphertext = original_ciphertext
        receipt.response_body_bytes += b" "
        with pytest.raises(ResetReplayFailure):
            replay_reset_receipt(receipt, replacement, codec)


@pytest.mark.asyncio
async def test_every_aad_field_and_session_hash_is_bound_before_signing(
    t010_postgres_url: str,
    t010_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    settings = _settings(t010_postgres_url)
    app = create_app(
        settings=settings,
        session_factory=t010_session_factory,
        clock=lambda: NOW,
    )
    old_cookie = await _new_guest_cookie(app)
    assert (await _reset(app, old_cookie)).status == 202
    codec = GuestSessionCodec(
        SessionKeyRing.from_settings(settings),
        cookie_secure=settings.cookie_secure,
        clock=lambda: NOW,
    )

    async with t010_session_factory() as session:
        stored = await session.scalar(select(ResetReplayReceipt))
        assert stored is not None
        replacement = await session.get(GuestSession, stored.replacement_session_id)
        assert replacement is not None

        mutations: dict[str, object] = {
            "id": uuid.uuid4(),
            "old_session_fingerprint": b"f" * 32,
            "operation": "reset-guest-session-v2",
            "key_hash": b"k" * 32,
            "request_hash": "1" * 64,
            "replacement_session_id": uuid.uuid4(),
            "replacement_token_hash": b"t" * 32,
            "encryption_key_id": "unknown-encryption-key",
            "aad_version": "reset-replay-aad-v2",
            "cookie_profile_version": "public-demo-v2",
            "cookie_signing_key_id": "unknown-cookie-key",
            "cookie_issued_at": stored.cookie_issued_at + timedelta(seconds=1),
            "cookie_expires_at": stored.cookie_expires_at + timedelta(seconds=1),
            "response_status": 203,
            "response_content_type": "application/problem+json",
            "response_serializer_version": "canonical-json-v2",
            "response_body_hash": "2" * 64,
            "created_at": stored.created_at + timedelta(seconds=1),
            "expires_at": stored.expires_at + timedelta(seconds=1),
        }
        for field, value in mutations.items():
            receipt = copy.copy(stored)
            setattr(receipt, field, value)
            with pytest.raises(ResetReplayFailure, match="integrity"):
                replay_reset_receipt(receipt, replacement, codec)

        mismatched_session = copy.copy(replacement)
        mismatched_session.token_hash = b"x" * 32
        with pytest.raises(ResetReplayFailure):
            replay_reset_receipt(stored, mismatched_session, codec)


@pytest.mark.asyncio
async def test_receipt_is_content_minimized_and_purge_is_independent(
    t010_postgres_url: str,
    t010_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    app = create_app(
        settings=_settings(t010_postgres_url),
        session_factory=t010_session_factory,
        clock=lambda: NOW,
    )
    old_cookie = await _new_guest_cookie(app)
    assert (await _reset(app, old_cookie, key="raw-key-must-not-persist")).status == 202

    forbidden_columns = {
        "workspace_id",
        "idempotency_key",
        "source",
        "decision",
        "run",
        "event",
        "ui_payload",
        "request_body",
    }
    assert forbidden_columns.isdisjoint(ResetReplayReceipt.__table__.columns.keys())
    async with t010_session_factory() as session:
        receipt = await session.scalar(select(ResetReplayReceipt))
        assert receipt is not None
        serialized = "|".join(
            str(getattr(receipt, column.name))
            for column in ResetReplayReceipt.__table__.columns
        )
        assert "raw-key-must-not-persist" not in serialized


@pytest.mark.asyncio
@pytest.mark.parametrize("same_key", [True, False])
async def test_competing_resets_commit_once_and_only_identical_retry_replays(
    t010_postgres_url: str,
    t010_session_factory: async_sessionmaker[AsyncSession],
    same_key: bool,
) -> None:
    app = create_app(
        settings=_settings(t010_postgres_url),
        session_factory=t010_session_factory,
        clock=lambda: NOW,
    )
    cookie = await _new_guest_cookie(app)
    second_key = IDEMPOTENCY_KEY if same_key else "different-race-key"
    first, second = await asyncio.gather(
        _reset(app, cookie, key=IDEMPOTENCY_KEY),
        _reset(app, cookie, key=second_key),
    )
    if same_key:
        assert first.status == second.status == 202
        assert first.body == second.body
        assert first.header("set-cookie") == second.header("set-cookie")
    else:
        assert sorted((first.status, second.status)) == [202, 401]
    assert await _row_counts(t010_session_factory) == (3, 2, 1, 1)
